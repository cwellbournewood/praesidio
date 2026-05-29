"""``praesidio-edge-proxy`` command-line entry point.

Subcommands:

* ``install-ca`` — generate + install root CA into OS trust store.
* ``uninstall-ca`` — remove the trust-store entry and delete the key.
* ``start`` — boot mitmproxy with the Praesidio addon attached.
* ``stop`` — signal the running proxy via its PID file.
* ``status`` — print the JSON status file.

Examples::

    praesidio-edge-proxy install-ca
    praesidio-edge-proxy start \\
        --gateway https://gateway.local:8000 \\
        --api-key $PRAESIDIO_API_KEY \\
        --listen 127.0.0.1:8888
    praesidio-edge-proxy status
    praesidio-edge-proxy stop
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import structlog

from . import __version__
from . import ca as ca_mod
from . import status as status_mod
from .config import EdgeSettings
from .upstream import intercepted_hosts

log = structlog.get_logger(__name__)


# --- argparse builders ----------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="praesidio-edge-proxy",
        description="Local CA MITM proxy that routes LLM traffic through the Praesidio gateway.",
    )
    p.add_argument("--version", action="version", version=f"praesidio-edge-proxy {__version__}")
    p.add_argument(
        "--ca-dir",
        type=Path,
        default=None,
        help="Override directory for CA cert + key (default: per-OS application data).",
    )

    sub = p.add_subparsers(dest="command", required=True)

    s_install = sub.add_parser("install-ca", help="Generate + install root CA in OS trust store.")
    s_install.add_argument("--force", action="store_true", help="Regenerate CA even if one exists.")

    sub.add_parser("uninstall-ca", help="Remove root CA from trust store and delete the key.")

    s_start = sub.add_parser("start", help="Start the proxy.")
    s_start.add_argument("--gateway", required=False, help="Praesidio gateway base URL.")
    s_start.add_argument("--api-key", required=False, help="API key for the gateway.")
    s_start.add_argument(
        "--tenant",
        default=None,
        help="Praesidio tenant id (default: 'default').",
    )
    s_start.add_argument(
        "--listen",
        default=None,
        help="HOST:PORT to bind (default: 127.0.0.1:8888).",
    )
    s_start.add_argument(
        "--fail-open",
        action="store_true",
        help="Forward requests unscanned when the gateway is unreachable (UNSAFE).",
    )
    s_start.add_argument(
        "--foreground",
        action="store_true",
        help="Run in the foreground instead of forking (default in containers).",
    )

    sub.add_parser("stop", help="Stop a running proxy (reads PID file).")
    sub.add_parser("status", help="Print the current status as JSON.")

    return p


def build_settings(args: argparse.Namespace) -> EdgeSettings:
    """Build :class:`EdgeSettings` from CLI args (overriding env vars)."""
    settings = EdgeSettings()  # type: ignore[call-arg]
    if getattr(args, "gateway", None):
        settings = settings.model_copy(update={"gateway_url": args.gateway.rstrip("/")})
    if getattr(args, "api_key", None):
        settings = settings.model_copy(update={"api_key": args.api_key})
    if getattr(args, "tenant", None):
        settings = settings.model_copy(update={"tenant": args.tenant})
    if getattr(args, "listen", None):
        host, _, port = args.listen.partition(":")
        update: dict[str, object] = {}
        if host:
            update["listen_host"] = host
        if port:
            update["listen_port"] = int(port)
        if update:
            settings = settings.model_copy(update=update)
    if getattr(args, "fail_open", False):
        settings = settings.model_copy(update={"fail_open": True})
    if getattr(args, "ca_dir", None):
        settings = settings.model_copy(update={"ca_dir": args.ca_dir})
    return settings


# --- Subcommands ----------------------------------------------------------

def cmd_install_ca(args: argparse.Namespace) -> int:
    """Generate (if needed) + install the root CA into the OS trust store."""
    cert_path, key_path = ca_mod.ensure_ca(args.ca_dir, force=args.force)
    print(f"CA generated: {cert_path}")
    print(f"  private key: {key_path} (mode 0600)")

    argv, script = ca_mod.install_command(args.ca_dir)
    print(f"Installing into trust store via: {script.name}")
    try:
        # argv comes from ca_mod.install_command — a fixed per-OS path
        # to a script shipped inside this package. Not user-controlled.
        proc = subprocess.run(argv, check=False, capture_output=True, text=True)  # noqa: S603
    except FileNotFoundError as exc:
        print(f"  ERROR: helper script not runnable: {exc}", file=sys.stderr)
        return 2
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        print(
            "  trust-store install failed — re-run as administrator/root.",
            file=sys.stderr,
        )
        return proc.returncode
    print(proc.stdout)
    return 0


def cmd_uninstall_ca(args: argparse.Namespace) -> int:
    """Remove the root CA from the trust store and delete on-disk material."""
    argv, _ = ca_mod.uninstall_command(args.ca_dir)
    try:
        # argv comes from ca_mod.uninstall_command — fixed per-OS script path.
        proc = subprocess.run(argv, check=False, capture_output=True, text=True)  # noqa: S603
    except FileNotFoundError as exc:
        print(f"  ERROR: helper script not runnable: {exc}", file=sys.stderr)
        return 2
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print("  trust-store removal failed — continuing with on-disk cleanup.")

    ca_mod.remove_ca(args.ca_dir)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """Boot mitmproxy with the Praesidio addon attached."""
    settings = build_settings(args)
    if not settings.api_key:
        print(
            "  WARNING: starting without an API key (PRAESIDIO_EDGE_API_KEY unset). "
            "The gateway will reject all /v1/scan calls unless it is in dev mode.",
            file=sys.stderr,
        )

    # CA must exist; mitmproxy needs the combined .pem.
    cert_path, key_path = ca_mod.ca_paths(settings.ca_dir)
    if not cert_path.exists() or not key_path.exists():
        print(
            "  ERROR: root CA not found. Run `praesidio-edge-proxy install-ca` first.",
            file=sys.stderr,
        )
        return 3

    # Status file.
    status_path = status_mod.default_status_path(settings.ca_dir)
    status = status_mod.StatusFile(
        status_path,
        listen=f"{settings.listen_host}:{settings.listen_port}",
        gateway=settings.gateway_url,
        hosts=intercepted_hosts(),
    )
    status.flush()

    print(f"Praesidio edge proxy v{__version__}")
    print(f"  listening on {settings.listen_host}:{settings.listen_port}")
    print(f"  gateway     {settings.gateway_url}")
    print(f"  hosts       {', '.join(intercepted_hosts())}")
    print(f"  status      {status_path}")

    # Boot mitmproxy. Import is local so the rest of the CLI works on
    # boxes without mitmproxy (e.g. status/stop only).
    try:
        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster
    except ImportError as exc:
        print(
            f"  ERROR: mitmproxy is not installed: {exc}. "
            "Install with `pip install praesidio-edge-proxy`.",
            file=sys.stderr,
        )
        return 4

    from .proxy import PraesidioAddon
    from .scan_client import GatewayClient

    opts = Options(
        listen_host=settings.listen_host,
        listen_port=settings.listen_port,
        # Tell mitmproxy to mint leaves from our root.
        confdir=str(cert_path.parent),
        # Stream large bodies so SSE flows aren't buffered to disk.
        stream_large_bodies="1m",
    )
    master = DumpMaster(opts, with_termlog=True, with_dumper=False)
    addon = PraesidioAddon(settings, gateway=GatewayClient(settings), status=status)
    master.addons.add(addon)

    def _shutdown(*_: object) -> None:
        log.info("cli.shutdown_signal")
        status.remove()
        master.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        master.run()
    finally:
        status.remove()
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the proxy via the PID recorded in the status file."""
    snap = status_mod.read_status(status_mod.default_status_path(args.ca_dir))
    if snap is None:
        print("  No running proxy found (status file absent).", file=sys.stderr)
        return 1
    pid = int(snap.get("pid", 0))
    if pid <= 0:
        print("  Status file has no PID.", file=sys.stderr)
        return 1
    try:
        if os.name == "nt":
            # Windows has no SIGTERM-by-pid; use taskkill from
            # %WINDIR%\System32. The PID is read from our own status
            # file, not from user input.
            subprocess.run(  # noqa: S603
                ["taskkill.exe", "/PID", str(pid)],  # noqa: S607
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"  Process {pid} not found; cleaning up status file.", file=sys.stderr)
        status_mod.default_status_path(args.ca_dir).unlink(missing_ok=True)
        return 0
    print(f"  Sent stop signal to PID {pid}.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Print the current status as JSON."""
    snap = status_mod.read_status(status_mod.default_status_path(args.ca_dir))
    if snap is None:
        print(json.dumps({"running": False}))
        return 0
    snap["running"] = True
    print(json.dumps(snap, indent=2))
    return 0


# --- Entry point ----------------------------------------------------------

_DISPATCH = {
    "install-ca": cmd_install_ca,
    "uninstall-ca": cmd_uninstall_ca,
    "start": cmd_start,
    "stop": cmd_stop,
    "status": cmd_status,
}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    fn = _DISPATCH.get(args.command)
    if fn is None:
        parser.error(f"unknown command: {args.command}")
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
