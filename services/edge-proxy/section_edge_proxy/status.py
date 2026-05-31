"""Status + lock file management.

The CLI writes a short JSON status file on ``start`` so:

* ``stop`` knows which PID to signal.
* ``status`` can print live state without re-invoking mitmproxy.
* External tools (Grafana, SIEM scrapers, Section UI) can probe the
  current decision count without subscribing to logs.

File path: ``<ca_dir>/edge-proxy-status.json``. Written atomically by
writing to ``.tmp`` and renaming. Read-mostly, so contention is rare —
we don't bother with fcntl locking.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

from .ca import default_ca_dir

STATUS_FILENAME = "edge-proxy-status.json"


def default_status_path(ca_dir: Path | None = None) -> Path:
    """Return the per-OS status file path."""
    base = ca_dir or default_ca_dir()
    return base / STATUS_FILENAME


class StatusFile:
    """In-memory + on-disk status for a single proxy process.

    Thread-safe enough for the addon's single-threaded asyncio loop;
    callers from other threads should serialise externally.
    """

    def __init__(self, path: Path, *, listen: str, gateway: str, hosts: list[str]):
        self.path = path
        self.pid = os.getpid()
        self.listen = listen
        self.gateway = gateway
        self.hosts = list(hosts)
        self.started_at = time.time()
        self.decisions = 0
        self.blocks = 0
        self.masks = 0
        self.allows = 0
        self.last_decision: dict[str, Any] | None = None
        self._recent: deque[dict[str, Any]] = deque(maxlen=16)

    def record_decision(self, *, host: str, action: str, request_id: str) -> None:
        """Increment counters + persist the new state to disk."""
        self.decisions += 1
        if action == "block":
            self.blocks += 1
        elif action == "mask":
            self.masks += 1
        elif action == "allow":
            self.allows += 1
        entry = {
            "host": host,
            "action": action,
            "request_id": request_id,
            "at": time.time(),
        }
        self.last_decision = entry
        self._recent.append(entry)
        self.flush()

    def snapshot(self) -> dict[str, Any]:
        """Return the JSON-serialisable form of the file."""
        return {
            "pid": self.pid,
            "listen": self.listen,
            "gateway": self.gateway,
            "hosts_intercepted": self.hosts,
            "started_at": self.started_at,
            "uptime_s": int(time.time() - self.started_at),
            "decisions": self.decisions,
            "blocks": self.blocks,
            "masks": self.masks,
            "allows": self.allows,
            "last_decision": self.last_decision,
            "recent": list(self._recent),
        }

    def flush(self) -> None:
        """Atomically write the snapshot to ``self.path``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2))
        os.replace(str(tmp), str(self.path))

    def remove(self) -> None:
        """Remove the status file on shutdown."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def read_status(path: Path | None = None) -> dict[str, Any] | None:
    """Read the status file from disk, or ``None`` if it doesn't exist."""
    p = path or default_status_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


__all__ = ["StatusFile", "default_status_path", "read_status", "STATUS_FILENAME"]
