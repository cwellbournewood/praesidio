"""Shadow-mode wiring (Task 4.7): decision logged but request always forwarded."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from section_gateway.audit.models import AuditEvent

os.environ["SECTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["SECTION_API_KEYS"] = "test-key"
os.environ["OPENAI_API_KEY"] = "sk-test"


def _shadow_bundle(tmp: Path) -> Path:
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: section/v1\nkind: Bundle\nmetadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (bundle / "models.yaml").write_text(
        "apiVersion: section/v1\nkind: ModelRegistry\nspec:\n"
        "  models:\n"
        "    - id: openai/gpt-4o-mini\n"
        "      provider: openai\n"
        "      endpoint_ref: openai-prod\n"
        "  endpoints:\n"
        "    - id: openai-prod\n"
        "      base_url: https://api.openai.com/v1\n"
        "      auth: {type: env, var: OPENAI_API_KEY}\n"
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec:\n"
        "  - inbound: {path: /v1/chat/completions, requested_model: gpt-4o-mini}\n"
        "    upstream: openai/gpt-4o-mini\n"
    )
    # mode: shadow — block decision logged but request forwarded.
    (bundle / "policies" / "0001-shadow.yaml").write_text(
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: shadow-sec, name: shadow-sec}\n"
        "spec:\n"
        "  match: {routes: ['/v1/chat/completions']}\n"
        "  mode: shadow\n"
        "  detect: {enable: [credential.aws_access_key]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: \"any(findings, .label == 'credential.aws_access_key')\"\n"
        "        action: block\n"
        "        reason: 'AWS credential'\n"
        "        severity: critical\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    return bundle


@pytest.mark.asyncio
async def test_shadow_mode_block_forwards_and_logs_decision():
    tmp = Path(tempfile.mkdtemp())
    bundle = _shadow_bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.main import create_app

    upstream_called: dict[str, bool] = {"hit": False}

    async def _handler(request: httpx.Request) -> httpx.Response:
        upstream_called["hit"] = True
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-shadow",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.openai.com/v1/chat/completions").mock(side_effect=_handler)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c, app.router.lifespan_context(app):
            r = await c.post(
                "/v1/chat/completions",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": "AKIAABCDEFGHIJKLMNOP"}
                    ],
                },
            )
            # Drain the audit queue so the row is flushed before we read.
            state = app.state.section
            import asyncio as _asyncio

            for _ in range(100):
                if state.audit._queue.empty():
                    break
                await _asyncio.sleep(0.02)
            # One more beat for the in-flight flush coroutine.
            await _asyncio.sleep(0.05)
            sm = async_sessionmaker(state.engine, expire_on_commit=False)
            async with sm() as s:
                res = await s.execute(select(AuditEvent))
                rows = res.scalars().all()

    # Shadow mode forwarded → 200 from upstream.
    assert r.status_code == 200, r.text
    assert upstream_called["hit"] is True
    # Informational decision header still surfaces "block" (annotated for shadow).
    decision_hdr = r.headers.get("x-section-decision", "")
    assert "block" in decision_hdr
    assert "shadow" in decision_hdr  # we emit "block-shadow"
    # Mode is reflected in the response header for observability.
    assert r.headers.get("x-section-mode") == "shadow"
    # Audit row mode column says "shadow".
    assert rows
    assert rows[0].mode == "shadow"
    assert rows[0].decision == "block"
