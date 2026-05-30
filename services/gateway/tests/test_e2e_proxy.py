"""End-to-end: gateway receives a chat with an email, anonymises it before it
hits the (mocked) OpenAI upstream, restores in the response, writes an audit row.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport

# Test config — must be set before importing the app/config.
os.environ["SECTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""  # in-memory vault
os.environ["SECTION_API_KEYS"] = "test-key"
os.environ["OPENAI_API_KEY"] = "sk-test"


def _write_bundle(tmp: Path) -> Path:
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
    (bundle / "policies" / "0001-pii.yaml").write_text(
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: pii, name: pii}\n"
        "spec:\n"
        "  match: {routes: ['/v1/chat/completions'], tenants: ['*']}\n"
        "  detect:\n"
        "    enable: [pii.email]\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: \"any(findings, .label == 'pii.email')\"\n"
        "        action: transform\n"
        "        transforms:\n"
        "          - {label: pii.email, method: tokenise, scope: request, ttl: 1h}\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    return bundle


@pytest.mark.asyncio
async def test_e2e_email_round_trip():
    # Build a fresh bundle dir.
    tmp = Path(tempfile.mkdtemp())
    bundle = _write_bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)

    # IMPORTANT: clear cached settings before import.
    from section_gateway.config import get_settings
    get_settings.cache_clear()

    # Replace the postgres DSN with sqlite for the audit writer.
    from section_gateway.main import create_app

    captured: dict[str, str] = {}

    async def _openai_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["upstream_messages"] = body["messages"][0]["content"]
        # Echo a response that includes the placeholder, so we can verify the
        # gateway restores it on the way back.
        # Find the placeholder in the upstream content for use in the reply.
        import re

        m = re.search(r"<EMAIL_[A-Z2-7]{4}>", body["messages"][0]["content"])
        placeholder = m.group(0) if m else "EMAIL"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"I will email {placeholder} shortly.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()

    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.openai.com/v1/chat/completions").mock(side_effect=_openai_handler)

        # Manually init lifespan since httpx ASGITransport doesn't run it.
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Trigger lifespan manually
            async with app.router.lifespan_context(app):
                resp = await client.post(
                    "/v1/chat/completions",
                    headers={"x-api-key": "test-key", "x-section-tenant": "default"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "user", "content": "Email alice@example.com please."}
                        ],
                    },
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()
                client_text = body["choices"][0]["message"]["content"]

    # Upstream got a placeholder, not the real email.
    assert "alice@example.com" not in captured["upstream_messages"]
    assert "<EMAIL_" in captured["upstream_messages"]
    # Client got the real email back (placeholder restored).
    assert "alice@example.com" in client_text


@pytest.mark.asyncio
async def test_e2e_block_when_aws_secret():
    tmp = Path(tempfile.mkdtemp())
    bundle = _write_bundle(tmp)
    # Replace the policy with one that blocks credential.aws_access_key.
    (bundle / "policies" / "0001-pii.yaml").write_text(
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: sec, name: sec}\n"
        "spec:\n"
        "  match: {routes: ['/v1/chat/completions']}\n"
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
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings
    get_settings.cache_clear()
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            resp = await client.post(
                "/v1/chat/completions",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": "key AKIAABCDEFGHIJKLMNOP"}
                    ],
                },
            )
    assert resp.status_code == 403
    assert resp.headers.get("x-section-decision") == "block"
