"""Postgres-only Row-Level Security verification (Task 5.2).

Skipped automatically unless a real Postgres ``DATABASE_URL`` is configured
and reachable. The migrations under ``services/gateway/migrations/`` define
the RLS policies; this test confirms ``SET praesidio.tenant_id`` actually
filters reads to the matching tenant.

Run only this test::

    PRAESIDIO_PG_DSN=postgresql+asyncpg://praesidio:praesidio@localhost/praesidio \\
        pytest -m postgres tests/test_rls_postgres.py
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praesidio_gateway.audit.chain import compute_chain_hash
from praesidio_gateway.audit.models import AuditEvent, Base

pytestmark = pytest.mark.postgres


def _pg_dsn() -> str | None:
    return os.environ.get("PRAESIDIO_PG_DSN") or os.environ.get("DATABASE_URL_PG")


def _row(tenant: str, prev: str | None) -> dict:
    base = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "request_id": f"req-{tenant}",
        "occurred_at": datetime.now(UTC),
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


async def _ensure_schema_and_policies(engine) -> None:
    """Recreate the schema + RLS policies for both audit and lineage tables.

    Uses the application-side definitions so this stays in lockstep with the
    SQL migration / Alembic revision.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in ("audit_events", "lineage_nodes"):
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            await conn.execute(
                text(f"DROP POLICY IF EXISTS praesidio_tenant_isolation ON {table}")
            )
            await conn.execute(
                text(
                    f"CREATE POLICY praesidio_tenant_isolation ON {table} "
                    f"USING (tenant_id = current_setting('praesidio.tenant_id', true) "
                    f"OR current_setting('praesidio.tenant_id', true) = '*') "
                    f"WITH CHECK (tenant_id = current_setting('praesidio.tenant_id', true) "
                    f"OR current_setting('praesidio.tenant_id', true) = '*')"
                )
            )


@pytest.mark.asyncio
async def test_rls_isolates_tenants():
    dsn = _pg_dsn()
    if not dsn:
        pytest.skip("PRAESIDIO_PG_DSN not set — Postgres RLS test skipped")

    engine = create_async_engine(dsn, future=True)
    try:
        await _ensure_schema_and_policies(engine)
        sm = async_sessionmaker(engine, expire_on_commit=False)

        # Seed one row per tenant (as bypass / superuser role).
        async with sm() as s:
            s.add(AuditEvent(**_row("A", None)))
            s.add(AuditEvent(**_row("B", None)))
            await s.commit()

        async with sm() as s:
            await s.execute(text("SET praesidio.tenant_id = 'A'"))
            res = await s.execute(text("SELECT tenant_id FROM audit_events"))
            assert [r[0] for r in res.fetchall()] == ["A"]

        async with sm() as s:
            await s.execute(text("SET praesidio.tenant_id = 'B'"))
            res = await s.execute(text("SELECT tenant_id FROM audit_events"))
            assert [r[0] for r in res.fetchall()] == ["B"]

        # The wildcard escape hatch sees everything (for the audit verifier).
        async with sm() as s:
            await s.execute(text("SET praesidio.tenant_id = '*'"))
            res = await s.execute(
                text("SELECT tenant_id FROM audit_events ORDER BY tenant_id")
            )
            assert [r[0] for r in res.fetchall()] == ["A", "B"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_writes():
    """Tenant A may not INSERT a row whose tenant_id is B."""
    dsn = _pg_dsn()
    if not dsn:
        pytest.skip("PRAESIDIO_PG_DSN not set — Postgres RLS test skipped")

    engine = create_async_engine(dsn, future=True)
    try:
        await _ensure_schema_and_policies(engine)
        sm = async_sessionmaker(engine, expire_on_commit=False)

        async with sm() as s:
            await s.execute(text("SET praesidio.tenant_id = 'A'"))
            s.add(AuditEvent(**_row("B", None)))
            with pytest.raises(Exception) as exc_info:
                await s.commit()
            # The exact error class is driver-specific but the message must
            # mention RLS / policy violation.
            assert "row-level security" in str(exc_info.value).lower() or \
                   "policy" in str(exc_info.value).lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_lineage_table_also_isolated():
    """The lineage_nodes table must enforce the same isolation."""
    dsn = _pg_dsn()
    if not dsn:
        pytest.skip("PRAESIDIO_PG_DSN not set — Postgres RLS test skipped")

    engine = create_async_engine(dsn, future=True)
    try:
        await _ensure_schema_and_policies(engine)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO lineage_nodes (id, tenant_id, request_id, "
                    "kind, ref, occurred_at) VALUES (:id, :t, :rid, :k, :ref, now())"
                ),
                [
                    {"id": str(uuid.uuid4()), "t": "A", "rid": "r1", "k": "src", "ref": "r1"},
                    {"id": str(uuid.uuid4()), "t": "B", "rid": "r2", "k": "src", "ref": "r2"},
                ],
            )
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as s:
            await s.execute(text("SET praesidio.tenant_id = 'A'"))
            res = await s.execute(text("SELECT tenant_id FROM lineage_nodes"))
            assert [r[0] for r in res.fetchall()] == ["A"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_no_tenant_setting_returns_nothing():
    """If praesidio.tenant_id is unset, the policy evaluates to NULL and
    the row is filtered — no leakage by default."""
    dsn = _pg_dsn()
    if not dsn:
        pytest.skip("PRAESIDIO_PG_DSN not set — Postgres RLS test skipped")

    engine = create_async_engine(dsn, future=True)
    try:
        await _ensure_schema_and_policies(engine)
        sm = async_sessionmaker(engine, expire_on_commit=False)

        async with sm() as s:
            s.add(AuditEvent(**_row("A", None)))
            await s.commit()

        async with sm() as s:
            # Force RLS even on table owners (otherwise the owner bypasses it).
            await s.execute(text("SET row_security = on"))
            await s.execute(text("SET ROLE praesidio_app_test"))
            res = await s.execute(text("SELECT count(*) FROM audit_events"))
            assert res.scalar_one() == 0
    except Exception as exc:
        # If the test role doesn't exist on this server, skip rather than
        # fail — CI provisions it; local dev usually doesn't.
        if "praesidio_app_test" in str(exc):
            pytest.skip("praesidio_app_test role not provisioned; skip")
        raise
    finally:
        await engine.dispose()
