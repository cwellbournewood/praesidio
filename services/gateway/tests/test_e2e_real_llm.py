"""Real-LLM cassette E2E tests.

Each cassette under ``tests/cassettes/*.json`` describes a single
end-to-end interaction:

* the inbound client request (headers + JSON body),
* the upstream LLM URL that should (or should not) be called,
* a templated upstream response that the gateway will see,
* a small set of post-conditions covering decision, restoration, and
  audit landing.

This gives us **realistic shapes** for OpenAI and Anthropic without
hammering the live providers in CI. To record / refresh a cassette,
follow ``docs/operations/recording-cassettes.md``.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport

# Test env — must be set before any section_gateway import.
os.environ["SECTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["SECTION_API_KEYS"] = "test-key"
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _list_cassettes() -> list[Path]:
    return sorted(p for p in CASSETTE_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Policy bundles — one per cassette policy id. We keep them small and inline
# so cassette → policy mapping is obvious.
# ---------------------------------------------------------------------------

_POLICIES: dict[str, str] = {
    "pii_tokenise_email": (
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: pii, name: pii}\n"
        "spec:\n"
        "  match: {tenants: ['*']}\n"
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
    ),
    "block_on_aws_secret": (
        "apiVersion: section/v1\n"
        "kind: Policy\n"
        "metadata: {id: sec, name: sec}\n"
        "spec:\n"
        "  match: {tenants: ['*']}\n"
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
    ),
}


def _write_bundle(cassette: dict, policy_id: str) -> Path:
    tmp = Path(tempfile.mkdtemp())
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: section/v1\n"
        "kind: Bundle\n"
        "metadata: {name: cassette, version: '0'}\n"
        "spec: {includes: []}\n"
    )
    provider = cassette["provider"]
    if provider == "openai":
        models = (
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
        routes = (
            "apiVersion: section/v1\nkind: Routes\nspec:\n"
            "  - inbound: {path: /v1/chat/completions, requested_model: gpt-4o-mini}\n"
            "    upstream: openai/gpt-4o-mini\n"
        )
    elif provider == "anthropic":
        models = (
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
        routes = (
            "apiVersion: section/v1\nkind: Routes\nspec:\n"
            "  - inbound: {path: /anthropic/v1/messages, requested_model: claude-3-haiku-20240307}\n"
            "    upstream: anthropic/claude-3-haiku-20240307\n"
        )
    else:  # pragma: no cover
        raise ValueError(f"unknown provider: {provider}")

    (bundle / "models.yaml").write_text(models)
    (bundle / "routes.yaml").write_text(routes)
    (bundle / "policies" / "0001.yaml").write_text(_POLICIES[policy_id])
    return bundle


def _build_app(bundle: Path):
    os.environ["SECTION_POLICY_BUNDLE"] = str(bundle)
    from section_gateway.config import get_settings

    get_settings.cache_clear()
    from section_gateway.main import create_app

    return create_app()


def _render_upstream(template: dict, placeholder: str) -> dict:
    """Substitute {EMAIL_PLACEHOLDER} -> the real <EMAIL_xxxx> the gateway used.

    Walks the template recursively and replaces in any string leaf.
    """
    def _walk(node):
        if isinstance(node, str):
            return node.replace("{EMAIL_PLACEHOLDER}", placeholder)
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        return node

    return _walk(template)


async def _wait_for_audit(app, *, tenant: str | None = None, timeout: float = 12.0) -> list[dict]:
    """Poll the audit table until at least one row exists or timeout elapses.

    The audit writer batches every ~1s, so we tolerate that worst-case latency
    and poll fast. We deliberately read **all** tenants (the cassette default
    flows under tenant ``default`` but ``block`` decisions are sometimes
    landed under whatever tenant the gateway derives — we don't want to
    couple the test to that detail).
    """
    from sqlalchemy import select

    from section_gateway.audit.models import AuditEvent

    state = app.state.section
    deadline = asyncio.get_event_loop().time() + timeout
    rows: list[dict] = []
    while asyncio.get_event_loop().time() < deadline:
        # Try to force a flush of the batched writer when the API exists.
        flush = getattr(state.audit, "flush", None)
        if callable(flush):
            try:
                await flush()
            except Exception:
                pass
        async with state.engine.connect() as conn:
            stmt = select(AuditEvent.tenant_id, AuditEvent.decision, AuditEvent.route)
            if tenant:
                stmt = stmt.where(AuditEvent.tenant_id == tenant)
            res = await conn.execute(stmt)
            rows = [
                {"tenant_id": r[0], "decision": r[1], "route": r[2]}
                for r in res.fetchall()
            ]
        if rows:
            return rows
        await asyncio.sleep(0.05)
    return rows


@pytest.mark.parametrize("cassette_path", _list_cassettes(), ids=lambda p: p.stem)
@pytest.mark.asyncio
async def test_cassette(cassette_path: Path):
    cassette = _load(cassette_path)
    policy_id = cassette["policy"]
    bundle = _write_bundle(cassette, policy_id)
    app = _build_app(bundle)

    expectations = cassette["expectations"]
    upstream_url = cassette["upstream"]["url"]
    upstream_seen: dict[str, str] = {}

    async def _upstream_handler(request: httpx.Request) -> httpx.Response:
        body_text = request.content.decode("utf-8")
        upstream_seen["body"] = body_text
        upstream_seen["count"] = str(int(upstream_seen.get("count", "0")) + 1)
        # If a placeholder appeared in the inbound prompt, mirror the first one
        # back in the upstream response so the gateway exercises restoration.
        import re

        m = re.search(r"<EMAIL_[A-Z2-7]{4}>", body_text)
        placeholder = m.group(0) if m else "<EMAIL_XXXX>"
        rendered = _render_upstream(cassette["upstream_response"]["body_template"], placeholder)
        return httpx.Response(
            cassette["upstream_response"]["status"],
            headers=cassette["upstream_response"].get("headers", {}),
            json=rendered,
        )

    with respx.mock(assert_all_called=False) as router:
        router.post(upstream_url).mock(side_effect=_upstream_handler)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client, app.router.lifespan_context(app):
            resp = await client.post(
                cassette["route"],
                headers=cassette["client_request"]["headers"],
                json=cassette["client_request"]["body"],
            )

            # ---------------- expectations ----------------
            assert resp.status_code == expectations["status_code"], resp.text

            if expectations.get("upstream_must_not_be_called"):
                assert upstream_seen.get("count", "0") == "0", (
                    f"upstream was called {upstream_seen.get('count')} times but cassette "
                    f"forbids it"
                )
            else:
                assert upstream_seen.get("count") == "1", (
                    f"expected exactly 1 upstream call, got {upstream_seen.get('count')}"
                )

            for needle in expectations.get("upstream_must_not_contain", []):
                assert needle not in upstream_seen.get("body", ""), (
                    f"upstream body still contains forbidden value {needle!r}"
                )
            for needle in expectations.get("upstream_must_contain", []):
                assert needle in upstream_seen.get("body", ""), (
                    f"upstream body missing required substring {needle!r}"
                )

            client_text = resp.text
            for needle in expectations.get("client_must_contain", []):
                assert needle in client_text, (
                    f"client response missing expected substring {needle!r}"
                )
            for needle in expectations.get("client_must_not_contain", []):
                assert needle not in client_text, (
                    f"client response still contains placeholder {needle!r}"
                )

            for header in expectations.get("response_headers_present", []):
                assert header in {k.lower() for k in resp.headers}, (
                    f"expected response header {header!r} missing"
                )

            # Audit landing — both transform and block paths must write a row.
            audit_rows = await _wait_for_audit(app)
            assert audit_rows, "no audit row landed within timeout"
            decisions = {r["decision"] for r in audit_rows}
            assert expectations["audit_decision"] in decisions, (
                f"expected audit decision {expectations['audit_decision']!r}, "
                f"got {decisions}"
            )
