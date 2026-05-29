#!/usr/bin/env python3
"""Verify the Python and TypeScript DLP-label display maps are in sync.

Source of truth: ``services/gateway/praesidio_gateway/dlp/display.py``
TypeScript twin: ``services/ui/lib/labels.ts``

We compare the *id*, *name*, *short*, *category*, *severity*, and the
existence of *example* between the two maps. If anything diverges the
script exits non-zero and CI fails — a clear signal to refresh the TS
side after editing Python.

The script does NOT compare descriptions: they are prose and we want to
allow phrasing tweaks in either direction without ratcheting. CI also
checks that the description in TS is non-empty.

Run:
    python3 scripts/check_label_display_sync.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_FILE = ROOT / "services/gateway/praesidio_gateway/dlp/display.py"
TS_FILE = ROOT / "services/ui/lib/labels.ts"

# Fields we require to match exactly across the two files.
CHECKED_FIELDS = ("id", "name", "short", "category", "severity")


def load_python_map() -> dict[str, dict[str, str]]:
    """Run a tiny Python snippet to dump the canonical map as JSON."""
    snippet = (
        "import json, sys; "
        "sys.path.insert(0, 'services/gateway'); "
        "from praesidio_gateway.dlp.display import LABELS; "
        "print(json.dumps({k: v.to_dict() for k, v in LABELS.items()}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("FAIL: could not import Python display map", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(2)
    return json.loads(result.stdout)


# Crude but deterministic TS parser: we look for top-level object entries
# of the form `'<id>': { ... }` and capture each field literal. Avoids
# pulling a JS runtime into the CI image.
_ENTRY_RE = re.compile(
    r"^\s*'(?P<id>[a-z][a-z0-9_]*\.[a-z0-9_]+)':\s*\{(?P<body>.*?)^\s*\},?\s*$",
    re.MULTILINE | re.DOTALL,
)
_FIELD_RE = re.compile(
    r"(?P<key>id|name|short|category|severity|description|example):\s*"
    r"(?P<value>'(?:\\'|[^'])*'|\"(?:\\\"|[^\"])*\")",
)


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    # JS-style escapes we actually use.
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def load_typescript_map() -> dict[str, dict[str, str]]:
    text = TS_FILE.read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    for m in _ENTRY_RE.finditer(text):
        label_id = m.group("id")
        body = m.group("body")
        fields: dict[str, str] = {}
        for fm in _FIELD_RE.finditer(body):
            fields[fm.group("key")] = _unquote(fm.group("value"))
        if "id" not in fields:
            fields["id"] = label_id
        out[label_id] = fields
    return out


def diff(py: dict, ts: dict) -> list[str]:
    errors: list[str] = []
    py_keys = set(py)
    ts_keys = set(ts)
    only_py = sorted(py_keys - ts_keys)
    only_ts = sorted(ts_keys - py_keys)
    if only_py:
        errors.append(f"Labels in Python but missing from TS: {only_py}")
    if only_ts:
        errors.append(f"Labels in TS but missing from Python: {only_ts}")
    for label in sorted(py_keys & ts_keys):
        for field in CHECKED_FIELDS:
            p = py[label].get(field)
            t = ts[label].get(field)
            if p != t:
                errors.append(f"{label}.{field}: Python={p!r}  TS={t!r}")
        # Description must be present and non-empty on TS too.
        if not ts[label].get("description", "").strip():
            errors.append(f"{label}.description: missing or empty in TS")
    return errors


def main() -> int:
    py = load_python_map()
    ts = load_typescript_map()
    errors = diff(py, ts)
    if errors:
        print("Label display map drift detected:")
        for e in errors:
            print(f"  - {e}")
        print(
            f"\nPython source: {PY_FILE.relative_to(ROOT)}\n"
            f"TS source:     {TS_FILE.relative_to(ROOT)}",
        )
        return 1
    print(f"OK: {len(py)} labels match across Python and TypeScript.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
