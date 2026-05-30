#!/usr/bin/env python3
"""
Seed the Section gateway with a policy bundle.

Usage:
    python scripts/seed_policies.py [--bundle PATH] [--gateway URL] [--api-key KEY]

Behaviour:
    1. Walks --bundle and validates every *.yaml file is loadable YAML.
    2. If a JSON Schema is shipped at <bundle>/schema.json, validates each
       Policy file against it.
    3. POSTs to {gateway}/admin/policies/reload to trigger a hot reload.

Exit codes:
    0  success
    1  validation failure
    2  network / gateway error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed Section policies.")
    p.add_argument(
        "--bundle",
        type=Path,
        default=Path("./examples/policies"),
        help="Path to the policy bundle directory (default: ./examples/policies)",
    )
    p.add_argument(
        "--gateway",
        default=os.environ.get("SECTION_GATEWAY", "http://localhost:8080"),
        help="Gateway base URL (default: http://localhost:8080)",
    )
    p.add_argument(
        "--api-key",
        default=os.environ.get("SECTION_API_KEY", "section-demo-key"),
        help="Admin API key (default: env SECTION_API_KEY or 'section-demo-key')",
    )
    p.add_argument(
        "--no-reload",
        action="store_true",
        help="Validate only; do not POST to /admin/policies/reload.",
    )
    return p.parse_args()


def find_yaml_files(root: Path) -> list[Path]:
    if not root.exists():
        raise SystemExit(f"ERROR: bundle path does not exist: {root}")
    if root.is_file():
        return [root]
    files = sorted(p for p in root.rglob("*.yaml"))
    if not files:
        raise SystemExit(f"ERROR: no *.yaml files found under {root}")
    return files


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_against_schema(doc: dict, schema: dict, path: Path) -> list[str]:
    """Best-effort JSON Schema validation. Returns a list of error messages."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []  # silently skip
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as e:
        return [f"{path}: {e.message} (at {'/'.join(str(p) for p in e.path)})"]
    return []


def reload_gateway(gateway: str, api_key: str) -> None:
    url = gateway.rstrip("/") + "/admin/policies/reload"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        print(f"ERROR: gateway returned HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach gateway at {url}: {e.reason}", file=sys.stderr)
        sys.exit(2)
    print(f"  reload: HTTP {status} {body[:200]}")


def main() -> int:
    args = parse_args()
    bundle: Path = args.bundle.resolve()
    print(f"=> validating bundle at {bundle}")

    files = find_yaml_files(bundle)
    print(f"   {len(files)} YAML file(s) found")

    # Optional schema for Policy docs.
    schema_path = bundle / "schema.json"
    schema = None
    if schema_path.exists():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            print(f"   loaded schema: {schema_path.name}")
        except json.JSONDecodeError as e:
            print(f"ERROR: schema.json is not valid JSON: {e}", file=sys.stderr)
            return 1

    errors: list[str] = []
    for f in files:
        try:
            doc = load_yaml(f)
        except yaml.YAMLError as e:
            errors.append(f"{f}: YAML parse error: {e}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{f}: top-level must be a mapping")
            continue
        kind = doc.get("kind")
        if schema is not None and kind == "Policy":
            errors.extend(validate_against_schema(doc, schema, f))
        print(f"   ok: {f.relative_to(bundle)} (kind={kind})")

    if errors:
        print("\nVALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("=> validation OK")

    if args.no_reload:
        print("   --no-reload set; skipping POST")
        return 0

    print(f"=> posting reload to {args.gateway}/admin/policies/reload")
    reload_gateway(args.gateway, args.api_key)
    print("=> done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
