"""Block-response header coverage for both v1 OpenAI and Anthropic routes.

Asserts that every 403 block carries both ``X-Section-Reason`` AND
``X-Section-Severity`` (mixed-case spelling) plus the lowercase
``x-section-decision: block`` / ``x-section-policy`` companions.
"""
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
os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["ANTHROPIC_API_KEY"] = "sk-test-ant"


def _bundle(tmp: Path, *, route: str = "/v1/chat/completions") -> Path:
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
        "    - id: anthropic/claude-3-haiku-20240307\n"
        "      provider: anthropic\n"
        "      endpoint_ref: anthropic-prod\n"
        "  endpoints:\n"
        "    - id: openai-prod\n"
        "      base_url: https://api.openai.com/v1\n"
        "      auth: {type: env, var: OPENAI_API_KEY}\n"
        "    - id: anthropic-prod\n"
        "      base_url: https://api.anthropic.com\n"
        "      auth: {type: env, var: ANTHROPIC_API_KEY}\n"
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec:\n"
        "  - inbound: {path: /v1/chat/completions, requested_model: gpt-4o-mini}\n"
        "    upstream: openai/gpt-4o-mini\n"
        "  - inbound: {path: /anthropic/v1/messages, requested_model: claude-3-haiku-20240307}\n"
        "    upstream: anthropic/claude-3-haiku-20240307\n"
    )
    (bundle / "policies" / "0001-block-secret.yaml").write_text(
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: sec, name: sec}\n"
        "spec:\n"
        f"  match: {{routes: ['{route}']}}\n"
        "  detect: {enable: [credential.aws_access_key]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: \"any(findings, .label == 'credential.aws_access_key')\"\n"
        "        action: block\n"
        "        reason: 'AWS credential detected'\n"
        "        severity: critical\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    return bundle


def _reload_settings(bundle: Path) -> None:
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_openai_block_has_reason_and_severity_headers():
    bundle = _bundle(Path(tempfile.mkdtemp()), route="/v1/chat/completions")
    _reload_settings(bundle)
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post(
                "/v1/chat/completions",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": "leak: AKIAABCDEFGHIJKLMNOP"}
                    ],
                },
            )
    assert r.status_code == 403, r.text
    assert r.headers.get("x-section-decision") == "block"
    assert r.headers.get("X-Section-Reason") == "AWS credential detected"
    assert r.headers.get("X-Section-Severity") == "critical"
    assert r.headers.get("x-section-policy") == "sec"


@pytest.mark.asyncio
async def test_anthropic_block_has_reason_and_severity_headers():
    bundle = _bundle(Path(tempfile.mkdtemp()), route="/anthropic/v1/messages")
    _reload_settings(bundle)
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post(
                "/anthropic/v1/messages",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "claude-3-haiku-20240307",
                    "messages": [
                        {"role": "user", "content": "leak: AKIAABCDEFGHIJKLMNOP"}
                    ],
                },
            )
    assert r.status_code == 403, r.text
    assert r.headers.get("x-section-decision") == "block"
    assert r.headers.get("X-Section-Reason") == "AWS credential detected"
    assert r.headers.get("X-Section-Severity") == "critical"
    assert r.headers.get("x-section-policy") == "sec"


@pytest.mark.asyncio
async def test_openai_block_defaults_when_rule_has_no_reason_or_severity():
    """A block rule without explicit reason/severity should still emit headers."""
    tmp = Path(tempfile.mkdtemp())
    bundle = _bundle(tmp)
    (bundle / "policies" / "0001-block-secret.yaml").write_text(
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
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n"
    )
    _reload_settings(bundle)
    from section_gateway.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post(
                "/v1/chat/completions",
                headers={"x-api-key": "test-key"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "AKIAABCDEFGHIJKLMNOP"}],
                },
            )
    assert r.status_code == 403
    # Defaults: "blocked by policy" + "high"
    assert r.headers.get("X-Section-Reason") == "blocked by policy"
    assert r.headers.get("X-Section-Severity") == "high"
