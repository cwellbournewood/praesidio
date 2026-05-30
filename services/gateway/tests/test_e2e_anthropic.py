"""End-to-end Anthropic route: round-trip + tool_use input scanning (Task 2.3, 2.5)."""
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
os.environ["ANTHROPIC_API_KEY"] = "sk-test-ant"


def _bundle(tmp: Path, *, policy_yaml: str | None = None) -> Path:
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: section/v1\nkind: Bundle\nmetadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (bundle / "models.yaml").write_text(
        "apiVersion: section/v1\nkind: ModelRegistry\nspec:\n"
        "  models:\n"
        "    - id: anthropic/claude-3-haiku-20240307\n"
        "      provider: anthropic\n"
        "      endpoint_ref: anthropic-prod\n"
        "  endpoints:\n"
        "    - id: anthropic-prod\n"
        "      base_url: https://api.anthropic.com\n"
        "      auth: {type: env, var: ANTHROPIC_API_KEY}\n"
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec:\n"
        "  - inbound: {path: /anthropic/v1/messages, requested_model: claude-3-haiku-20240307}\n"
        "    upstream: anthropic/claude-3-haiku-20240307\n"
    )
    (bundle / "policies" / "0001-pii.yaml").write_text(
        policy_yaml
        or (
            "apiVersion: section/v1\n"
            "kind: Policy\n"
            "metadata: {id: pii, name: pii}\n"
            "spec:\n"
            "  match: {routes: ['/anthropic/v1/messages']}\n"
            "  detect: {enable: [pii.email]}\n"
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
    )
    return bundle


def _reload(bundle: Path) -> None:
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_anthropic_email_round_trip():
    bundle = _bundle(Path(tempfile.mkdtemp()))
    _reload(bundle)
    from section_gateway.main import create_app

    captured: dict[str, str] = {}

    async def _ant_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["upstream_user"] = body["messages"][0]["content"]
        import re

        m = re.search(r"<EMAIL_[A-Z2-7]{4}>", body["messages"][0]["content"])
        placeholder = m.group(0) if m else "EMAIL"
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-haiku-20240307",
                "content": [
                    {"type": "text", "text": f"reach {placeholder}"},
                ],
                "stop_reason": "end_turn",
            },
        )

    app = create_app()
    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.anthropic.com/v1/messages").mock(side_effect=_ant_handler)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c, app.router.lifespan_context(app):
            r = await c.post(
                "/anthropic/v1/messages",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "claude-3-haiku-20240307",
                    "messages": [
                        {"role": "user", "content": "mail alice@example.com"}
                    ],
                },
            )
    assert r.status_code == 200, r.text
    assert "alice@example.com" not in captured["upstream_user"]
    assert "<EMAIL_" in captured["upstream_user"]
    body = r.json()
    text = body["content"][0]["text"]
    assert "alice@example.com" in text


@pytest.mark.asyncio
async def test_anthropic_response_side_dlp_redacts_new_email():
    """Anthropic upstream returns a *new* email not seen in the request — the
    response scanner must catch and redact it (Task 2.3 parity)."""
    # Use a policy that doesn't anonymise; we want the response scan to fire
    # on a fresh email that wasn't part of any reversal map.
    policy = (
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: pii, name: pii}\n"
        "spec:\n"
        "  match: {routes: ['/anthropic/v1/messages']}\n"
        "  detect: {enable: [pii.email]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    bundle = _bundle(Path(tempfile.mkdtemp()), policy_yaml=policy)
    _reload(bundle)
    from section_gateway.main import create_app

    async def _ant_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-haiku-20240307",
                "content": [
                    {"type": "text", "text": "leaked: secret@hidden.com"},
                ],
                "stop_reason": "end_turn",
            },
        )

    app = create_app()
    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.anthropic.com/v1/messages").mock(side_effect=_ant_handler)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c, app.router.lifespan_context(app):
            r = await c.post(
                "/anthropic/v1/messages",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "claude-3-haiku-20240307",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
    assert r.status_code == 200, r.text
    body = r.json()
    text = body["content"][0]["text"]
    assert "secret@hidden.com" not in text
    assert "[REDACTED_EMAIL]" in text
    assert r.headers.get("x-section-response-findings") == "1"


@pytest.mark.asyncio
async def test_anthropic_tool_use_input_scanned():
    """Anthropic ``content[].type=='tool_use'`` ``input`` dict must be scanned
    and any PII leaf redacted."""
    policy = (
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: pii, name: pii}\n"
        "spec:\n"
        "  match: {routes: ['/anthropic/v1/messages']}\n"
        "  detect: {enable: [pii.email]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    bundle = _bundle(Path(tempfile.mkdtemp()), policy_yaml=policy)
    _reload(bundle)
    from section_gateway.main import create_app

    async def _ant_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-haiku-20240307",
                "content": [
                    {"type": "text", "text": "calling tool"},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "send_email",
                        "input": {"to": "leak@target.com", "body": "hi"},
                    },
                ],
                "stop_reason": "tool_use",
            },
        )

    app = create_app()
    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.anthropic.com/v1/messages").mock(side_effect=_ant_handler)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c, app.router.lifespan_context(app):
            r = await c.post(
                "/anthropic/v1/messages",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "claude-3-haiku-20240307",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    assert r.status_code == 200, r.text
    body = r.json()
    # tool_use input must no longer contain the raw email.
    rendered = json.dumps(body)
    assert "leak@target.com" not in rendered
    assert "REDACTED_EMAIL" in rendered
