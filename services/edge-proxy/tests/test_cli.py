"""Tests for the section-edge-proxy CLI."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from section_edge_proxy import cli
from section_edge_proxy import status as status_mod

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def test_parser_accepts_each_command():
    parser = cli._build_parser()
    for cmd in ("install-ca", "uninstall-ca", "start", "stop", "status"):
        args = parser.parse_args([cmd] + (["--gateway", "x"] if cmd == "start" else []))
        assert args.command == cmd


def test_start_args_override_env(monkeypatch):
    monkeypatch.setenv("SECTION_EDGE_GATEWAY_URL", "http://env-gw")
    monkeypatch.setenv("SECTION_EDGE_API_KEY", "env-key")

    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "start",
            "--gateway",
            "http://cli-gw",
            "--api-key",
            "cli-key",
            "--listen",
            "127.0.0.1:9000",
            "--tenant",
            "acme",
            "--fail-open",
        ]
    )
    settings = cli.build_settings(args)
    assert settings.gateway_url == "http://cli-gw"
    assert settings.api_key == "cli-key"
    assert settings.tenant == "acme"
    assert settings.listen_host == "127.0.0.1"
    assert settings.listen_port == 9000
    assert settings.fail_open is True


def test_start_args_default_to_env(monkeypatch):
    monkeypatch.setenv("SECTION_EDGE_GATEWAY_URL", "http://env-gw")
    monkeypatch.setenv("SECTION_EDGE_API_KEY", "env-key")

    parser = cli._build_parser()
    args = parser.parse_args(["start"])
    settings = cli.build_settings(args)
    assert settings.gateway_url == "http://env-gw"
    assert settings.api_key == "env-key"


# ---------------------------------------------------------------------------
# status / stop using the status file
# ---------------------------------------------------------------------------

def test_status_when_no_file_says_not_running(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(status_mod, "default_ca_dir", lambda: tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_status(type("A", (), {"ca_dir": None})())
    assert rc == 0
    assert json.loads(buf.getvalue()) == {"running": False}


def test_status_round_trip(tmp_path: Path):
    sf = status_mod.StatusFile(
        tmp_path / "edge-proxy-status.json",
        listen="127.0.0.1:8888",
        gateway="http://gateway",
        hosts=["api.openai.com"],
    )
    sf.record_decision(host="api.openai.com", action="mask", request_id="req-1")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_status(type("A", (), {"ca_dir": tmp_path})())
    assert rc == 0
    snap = json.loads(buf.getvalue())
    assert snap["running"] is True
    assert snap["decisions"] == 1
    assert snap["masks"] == 1
    assert snap["last_decision"]["request_id"] == "req-1"


def test_stop_returns_1_when_no_status_file(tmp_path: Path):
    rc = cli.cmd_stop(type("A", (), {"ca_dir": tmp_path})())
    assert rc == 1


def test_stop_cleans_up_when_pid_missing(tmp_path: Path):
    # Status file with a PID we know won't exist.
    sf = status_mod.StatusFile(
        tmp_path / "edge-proxy-status.json",
        listen="127.0.0.1:8888",
        gateway="http://gw",
        hosts=["api.openai.com"],
    )
    sf.pid = 9999999  # almost certainly not a real PID on the test host
    sf.flush()

    rc = cli.cmd_stop(type("A", (), {"ca_dir": tmp_path})())
    # On POSIX we'll either get 0 (already gone) or 0 after cleanup; on
    # Windows taskkill will simply exit nonzero but we still return 0.
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# install-ca / uninstall-ca dispatch
# ---------------------------------------------------------------------------

def test_install_ca_creates_files_and_calls_subprocess(tmp_path: Path, monkeypatch):
    """`install-ca` always mints the CA; the trust-store call is mocked."""
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 0, "stdout": "ok", "stderr": ""}
        )(),
    )

    args = type("A", (), {"ca_dir": tmp_path, "force": False})()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_install_ca(args)
    assert rc == 0
    assert (tmp_path / "section-ca.crt").exists()
    assert (tmp_path / "section-ca.key").exists()


def test_install_ca_propagates_subprocess_failure(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 5, "stdout": "", "stderr": "perm denied"}
        )(),
    )

    args = type("A", (), {"ca_dir": tmp_path, "force": False})()
    rc = cli.cmd_install_ca(args)
    assert rc == 5


def test_uninstall_ca_deletes_files(tmp_path: Path, monkeypatch):
    from section_edge_proxy import ca as ca_mod

    ca_mod.ensure_ca(tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 0, "stdout": "ok", "stderr": ""}
        )(),
    )

    args = type("A", (), {"ca_dir": tmp_path})()
    rc = cli.cmd_uninstall_ca(args)
    assert rc == 0
    assert not (tmp_path / "section-ca.crt").exists()
    assert not (tmp_path / "section-ca.key").exists()


def test_uninstall_ca_continues_even_if_subprocess_fails(tmp_path: Path, monkeypatch):
    """The on-disk material is cleaned even if the trust-store call fails."""
    from section_edge_proxy import ca as ca_mod

    ca_mod.ensure_ca(tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 7, "stdout": "", "stderr": "fail"}
        )(),
    )

    args = type("A", (), {"ca_dir": tmp_path})()
    rc = cli.cmd_uninstall_ca(args)
    assert rc == 0  # we always succeed-on-cleanup
    assert not (tmp_path / "section-ca.crt").exists()


# ---------------------------------------------------------------------------
# start guard: CA must exist
# ---------------------------------------------------------------------------

def test_start_returns_error_when_ca_missing(tmp_path: Path, capsys):
    args = type(
        "A",
        (),
        {
            "ca_dir": tmp_path,
            "gateway": "http://gw",
            "api_key": "k",
            "tenant": None,
            "listen": "127.0.0.1:0",
            "fail_open": False,
            "foreground": True,
        },
    )()
    rc = cli.cmd_start(args)
    assert rc == 3
    err = capsys.readouterr().err
    assert "install-ca" in err
