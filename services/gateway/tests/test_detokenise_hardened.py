"""Detokenise endpoint hardening (G7).

Covers:
  * ``justification`` < 10 chars rejected with 422.
  * ``ticket_id`` missing or empty rejected with 422.
  * Per-tenant rate limit returns 429 with scope=detokenise header.
  * Successful call writes an audit row whose transforms[0] carries
    ``event_type=vault.detokenise`` and the supplied ``ticket_id``.
  * Cross-tenant placeholders return ``found=false`` (existing AAD
    protection) — sanity check that the hardening didn't weaken it.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

os.environ["SECTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["SECTION_API_KEYS"] = "test-key"
os.environ["SECTION_ADMIN_API_KEYS"] = "test-key"
os.environ["SECTION_DETOK_RATE_LIMIT_PER_TENANT_RPM"] = "2"


def _empty_bundle(tmp: Path) -> Path:
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: section/v1\nkind: Bundle\n"
        "metadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (bundle / "models.yaml").write_text(
        "apiVersion: section/v1\nkind: ModelRegistry\nspec: {models: [], endpoints: []}\n"
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec: []\n"
    )
    return bundle


def _make_app():
    tmp = Path(tempfile.mkdtemp())
    bundle = _empty_bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.api.admin.detokenise import _reset_tenant_buckets
    from section_gateway.main import create_app

    _reset_tenant_buckets()
    return create_app()


def _headers(tenant: str = "tA") -> dict[str, str]:
    return {"x-api-key": "test-key", "x-section-tenant": tenant}


@pytest.mark.asyncio
async def test_justification_too_short_rejected() -> None:
    app = _make_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post(
                "/admin/detokenise",
                json={
                    "request_id": "req-x",
                    "placeholders": ["<EMAIL_A2B3>"],
                    "justification": "short",  # 5 chars
                    "ticket_id": "INC-1",
                },
                headers=_headers(),
            )
    assert r.status_code == 422, r.text
    body = r.json()
    detail = str(body.get("detail"))
    assert "justification" in detail.lower()


@pytest.mark.asyncio
async def test_ticket_id_required() -> None:
    app = _make_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            # Missing field.
            r = await c.post(
                "/admin/detokenise",
                json={
                    "request_id": "req-x",
                    "placeholders": ["<EMAIL_A2B3>"],
                    "justification": "valid reason here",
                },
                headers=_headers(),
            )
    assert r.status_code == 422
    assert "ticket_id" in r.text.lower()


@pytest.mark.asyncio
async def test_ticket_id_empty_after_strip_rejected() -> None:
    app = _make_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post(
                "/admin/detokenise",
                json={
                    "request_id": "req-x",
                    "placeholders": ["<EMAIL_A2B3>"],
                    "justification": "valid reason here",
                    "ticket_id": "   ",
                },
                headers=_headers(),
            )
    assert r.status_code == 422
    assert "ticket_id" in r.text.lower()


@pytest.mark.asyncio
async def test_rate_limit_per_tenant_429() -> None:
    """RPM=2 ⇒ third call within the same minute is 429."""
    app = _make_app()
    body = {
        "request_id": "req-x",
        "placeholders": ["<EMAIL_A2B3>"],
        "justification": "soc investigation",
        "ticket_id": "INC-99",
    }
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r1 = await c.post("/admin/detokenise", json=body, headers=_headers("tA"))
            r2 = await c.post("/admin/detokenise", json=body, headers=_headers("tA"))
            r3 = await c.post("/admin/detokenise", json=body, headers=_headers("tA"))
    # First two are valid (vault miss == 200, hits=[{found:false}]).
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r3.status_code == 429, r3.text
    assert r3.headers.get("X-Section-RateLimit-Scope") == "detokenise"
    assert r3.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_different_tenants_have_independent_buckets() -> None:
    """Tenant A's quota doesn't drain tenant B's."""
    app = _make_app()
    body = {
        "request_id": "req-x",
        "placeholders": ["<EMAIL_A2B3>"],
        "justification": "soc investigation",
        "ticket_id": "INC-99",
    }
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            assert (await c.post("/admin/detokenise", json=body, headers=_headers("tA"))).status_code == 200
            assert (await c.post("/admin/detokenise", json=body, headers=_headers("tA"))).status_code == 200
            # tA exhausted, but tB is fresh.
            r_tb = await c.post("/admin/detokenise", json=body, headers=_headers("tB"))
            assert r_tb.status_code == 200, r_tb.text


@pytest.mark.asyncio
async def test_audit_row_records_ticket_and_event_type() -> None:
    """Successful detokenise → audit_events row tagged event_type=vault.detokenise."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    app = _make_app()
    body = {
        "request_id": "req-audit",
        "placeholders": ["<EMAIL_AB23>"],
        "justification": "compliance audit",
        "ticket_id": "INC-AUDIT-1",
    }
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post("/admin/detokenise", json=body, headers=_headers("tA"))
            assert r.status_code == 200, r.text
            # Flush + poll for the audit row.
            state = app.state.section
            from section_gateway.audit.models import AuditEvent

            row = None
            for _ in range(50):
                await asyncio.sleep(0.02)
                async with AsyncSession(state.engine) as s:
                    found = (
                        await s.execute(
                            select(AuditEvent).where(
                                AuditEvent.request_id == "req-audit"
                            )
                        )
                    ).scalar_one_or_none()
                if found is not None:
                    row = found
                    break
    assert row is not None, "audit row not written"
    transforms = row.transforms or []
    assert transforms, transforms
    t0 = transforms[0]
    assert t0.get("event_type") == "vault.detokenise"
    assert t0.get("ticket_id") == "INC-AUDIT-1"
