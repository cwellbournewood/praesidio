"""``section-audit verify`` CLI tests (Task 5.3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from section_gateway.audit.chain import compute_chain_hash
from section_gateway.audit.models import Base
from section_gateway.cli.audit_verify import (
    _verify_async,
    parse_duration,
    verify_rows,
)


def _row_dict(i: int, prev: str | None, *, tenant: str = "acme") -> dict:
    base = {
        "id": f"00000000-0000-0000-0000-{i:012d}",
        "tenant_id": tenant,
        "request_id": f"req-{i}",
        "occurred_at": datetime(2026, 5, 27, 0, 0, i, tzinfo=UTC),
        "principal_id": "apikey:deadbeef",
        "principal_groups": ["admin"],
        "source_ip": "127.0.0.1",
        "route": "/v1/chat/completions",
        "upstream": "openai/gpt-4o-mini",
        "decision": "allow",
        "rule_id": None,
        "rule_index": None,
        "policy_id": None,
        "policy_version": None,
        "bundle_digest": "0" * 64,
        "findings": [],
        "transforms": [],
        "request_digest": "0" * 64,
        "response_digest": None,
        "latency_ms": 1,
        "bytes_in": 1,
        "bytes_out": 0,
        "degraded": False,
        "mode": "enforce",
        "reason": None,
        "severity": None,
        "prev_hash": prev,
        "signature": None,
    }
    base["chain_hash"] = compute_chain_hash(prev, base)
    return base


# ---------------------------------------------------------------------------
# Pure-Python chain verification
# ---------------------------------------------------------------------------


def test_verify_rows_happy_path():
    rows = []
    prev = None
    for i in range(3):
        r = _row_dict(i, prev)
        rows.append(r)
        prev = r["chain_hash"]
    ok, idx, diag = verify_rows(rows)
    assert ok is True
    assert idx is None
    assert diag is None


def test_verify_rows_detects_tampered_middle_row():
    rows = []
    prev = None
    for i in range(3):
        r = _row_dict(i, prev)
        rows.append(r)
        prev = r["chain_hash"]
    # Tamper row 1 — flip the decision but leave the (now-invalid) chain_hash.
    rows[1]["decision"] = "block"
    ok, idx, diag = verify_rows(rows)
    assert ok is False
    assert idx == 1
    assert diag and "row 1" in diag


def test_parse_duration_supported_units():
    assert parse_duration("45s") == timedelta(seconds=45)
    assert parse_duration("15m") == timedelta(minutes=15)
    assert parse_duration("1h") == timedelta(hours=1)
    assert parse_duration("24h") == timedelta(hours=24)
    assert parse_duration("7d") == timedelta(days=7)


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("forever")
    with pytest.raises(ValueError):
        parse_duration("10")


# ---------------------------------------------------------------------------
# DSN-backed end-to-end check via SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_verify_against_file_sqlite_round_trip(tmp_path):
    """End-to-end CLI verification against a real (file-backed) SQLite DB.

    Uses the live :class:`AuditWriter` to seed rows so the chain is built
    with the same code path the verifier will check, then asserts the CLI
    accepts the intact chain and rejects a tampered one.
    """
    from section_gateway.audit.writer import AuditWriter

    db_path = tmp_path / "audit.sqlite"
    dsn = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(dsn, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = AuditWriter(engine)

    # Seed 3 rows for tenant=acme using the writer (so chain_hash is
    # produced by the production code path).
    for i in range(3):
        await writer.write_one(
            {
                "tenant_id": "acme",
                "request_id": f"req-{i}",
                "principal_id": "apikey:deadbeef",
                "principal_groups": ["admin"],
                "source_ip": "127.0.0.1",
                "route": "/v1/chat/completions",
                "upstream": "openai/gpt-4o-mini",
                "decision": "allow",
                "rule_id": None,
                "rule_index": None,
                "policy_id": None,
                "policy_version": None,
                "bundle_digest": "0" * 64,
                "findings": [],
                "transforms": [],
                "request_digest": "0" * 64,
                "response_digest": None,
                "latency_ms": 1,
                "bytes_in": 1,
                "bytes_out": 0,
                "degraded": False,
                "mode": "enforce",
                "reason": None,
                "severity": None,
            }
        )
    await engine.dispose()

    ok, idx, diag, n = await _verify_async(dsn, tenant="acme", since=None)
    assert n == 3
    assert ok is True, f"verifier rejected an intact chain (diag={diag})"

    # Tamper row 1 and re-verify — must flag row index 1.
    import sqlite3

    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE audit_events SET decision='block' WHERE request_id=?",
        ("req-1",),
    )
    con.commit()
    con.close()

    ok, idx, diag, n = await _verify_async(dsn, tenant="acme", since=None)
    assert ok is False
    assert idx == 1
    assert diag and "row 1" in diag
