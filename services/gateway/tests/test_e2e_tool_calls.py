"""OpenAI tool_calls arguments scanning (Task 2.5)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport

os.environ["SECTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["SECTION_API_KEYS"] = "test-key"
os.environ["OPENAI_API_KEY"] = "sk-test"


def _bundle(tmp: Path) -> Path:
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
        "  match: {routes: ['/v1/chat/completions']}\n"
        "  detect: {enable: [pii.email]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    return bundle


@pytest.mark.asyncio
async def test_openai_tool_call_arguments_are_scanned_and_redacted():
    tmp = Path(tempfile.mkdtemp())
    bundle = _bundle(tmp)
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.main import create_app

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "send_email",
                                        # JSON string carrying an email leaf.
                                        "arguments": json.dumps(
                                            {"to": "victim@target.com", "body": "hi"}
                                        ),
                                    },
                                }
                            ],
                        },
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
                    "messages": [{"role": "user", "content": "send it"}],
                },
            )
    assert r.status_code == 200, r.text
    body = r.json()
    args_str = body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    # Email must be gone, replaced with the redaction marker.
    assert "victim@target.com" not in args_str
    assert "REDACTED_EMAIL" in args_str
    # Response-findings header must report at least one.
    assert int(r.headers.get("x-section-response-findings", "0")) >= 1
