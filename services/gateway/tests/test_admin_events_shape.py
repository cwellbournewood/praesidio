"""/admin/events response-shape tests (Task 1.3)."""
from __future__ import annotations

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


def _empty_bundle(tmp: Path) -> Path:
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: section/v1\nkind: Bundle\nmetadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (bundle / "models.yaml").write_text(
        "apiVersion: section/v1\nkind: ModelRegistry\nspec: {models: [], endpoints: []}\n"
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec: []\n"
    )
    return bundle


async def _seed_one_row(state) -> None:
    """Write one audit row using the live writer."""
    row = {
        "tenant_id": "default",
        "request_id": "req-1",
        "principal_id": "apikey:abcdef12",
        "principal_groups": ["admin"],
        "source_ip": "127.0.0.1",
        "route": "/v1/chat/completions",
        "upstream": "openai/gpt-4o-mini",
        "decision": "allow",
        "rule_id": None,
        "rule_index": None,
        "policy_id": None,
        "policy_version": None,
        "bundle_digest": state.policy_store.bundle.digest,
        "findings": [],
        "transforms": [],
        "request_digest": "0" * 64,
        "response_digest": None,
        "latency_ms": 5,
        "bytes_in": 10,
        "bytes_out": 0,
        "degraded": False,
        "mode": "enforce",
        "reason": None,
        "severity": None,
    }
    await state.audit.write_one(row)


@pytest.mark.asyncio
async def test_events_default_returns_bare_array():
    tmp = Path(tempfile.mkdtemp())
    bundle = _empty_bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            await _seed_one_row(app.state.section)
            r = await c.get("/admin/events", headers={"x-api-key": "test-key"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert body and body[0]["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_events_paged_returns_envelope():
    tmp = Path(tempfile.mkdtemp())
    bundle = _empty_bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            await _seed_one_row(app.state.section)
            r = await c.get(
                "/admin/events?paged=true", headers={"x-api-key": "test-key"}
            )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert "items" in body and "next_cursor" in body
    assert isinstance(body["items"], list)
    assert body["items"][0]["request_id"] == "req-1"
