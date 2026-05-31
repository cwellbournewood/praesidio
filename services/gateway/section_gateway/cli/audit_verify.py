"""``section-audit verify`` — walk the audit chain and detect tampering.

Reads ``audit_events`` rows (ordered by ``occurred_at``, then ``id``), then
recomputes the per-row ``chain_hash`` using the same algorithm as the live
gateway (:mod:`section_gateway.audit.chain`). Any mismatch is reported.

Exits ``0`` when the chain is intact, ``1`` when any row fails to verify.

Usage::

    section-audit verify --tenant acme --since 24h
    section-audit verify --tenant acme --since 1h --dsn $DATABASE_URL
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..audit.chain import compute_chain_hash
from ..audit.models import AuditEvent

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d)\s*$", re.IGNORECASE)


def parse_duration(s: str) -> timedelta:
    """Parse ``1h`` / ``24h`` / ``15m`` / ``7d`` / ``45s`` into a ``timedelta``."""
    m = _DURATION_RE.match(s)
    if not m:
        raise ValueError(
            f"invalid --since duration: {s!r} (expected e.g. '1h', '24h', '15m')"
        )
    value = int(m.group(1))
    unit = m.group(2).lower()
    factors = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=value * factors[unit])


def row_to_dict(ev: AuditEvent) -> dict[str, Any]:
    return {c.name: getattr(ev, c.name) for c in ev.__table__.columns}


def verify_rows(rows: Iterable[dict[str, Any]]) -> tuple[bool, int | None, str | None]:
    """Recompute the chain row-by-row.

    Returns ``(ok, first_bad_index, diagnostic)``.
    """
    prev: str | None = None
    for i, row in enumerate(rows):
        stored = row.get("chain_hash")
        # Exclude chain_hash from the computation input (same as the writer).
        row_for_hash = {k: v for k, v in row.items() if k != "chain_hash"}
        expected = compute_chain_hash(prev, row_for_hash)
        if stored != expected:
            return (
                False,
                i,
                f"row {i} id={row.get('id')} expected={expected[:12]}… stored={(stored or '')[:12]}…",
            )
        prev = stored
    return True, None, None


async def _verify_async(
    dsn: str,
    *,
    tenant: str,
    since: timedelta | None,
) -> tuple[bool, int | None, str | None, int]:
    engine = create_async_engine(dsn, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as s:
            stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant)
            if since is not None:
                cutoff = datetime.now(UTC) - since
                stmt = stmt.where(AuditEvent.occurred_at >= cutoff)
            stmt = stmt.order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
            res = await s.execute(stmt)
            rows = [row_to_dict(r) for r in res.scalars().all()]
    finally:
        await engine.dispose()
    ok, idx, diag = verify_rows(rows)
    return ok, idx, diag, len(rows)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="section-audit",
        description="Section audit-chain operator CLI.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser(
        "verify",
        help="Recompute the per-tenant audit hash chain and exit 1 on tamper.",
    )
    v.add_argument("--tenant", required=True, help="Tenant id to verify.")
    v.add_argument(
        "--since",
        default=None,
        help="Only verify rows newer than this duration (e.g. 1h, 24h, 7d).",
    )
    v.add_argument(
        "--dsn",
        default=None,
        help="SQLAlchemy DSN override (defaults to $DATABASE_URL).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "verify":  # pragma: no cover - argparse enforces
        parser.print_help()
        return 2

    dsn = args.dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: --dsn not given and DATABASE_URL not set", file=sys.stderr)
        return 2

    since = parse_duration(args.since) if args.since else None

    ok, idx, diag, n = asyncio.run(
        _verify_async(dsn, tenant=args.tenant, since=since)
    )
    if ok:
        print(f"OK: {n} row(s) verified for tenant={args.tenant!r}")
        return 0
    print(
        f"FAIL: chain broken for tenant={args.tenant!r} at row index {idx} ({diag})",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    sys.exit(main())
