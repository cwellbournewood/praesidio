"""Per-(tenant, model) TPM bucket (G4).

Verifies that:
  - ``consume_model_tpm`` debits actual token usage post-upstream;
  - the request-path pre-check refuses *new* requests once drained;
  - ``tpm_per_model`` overrides ``tpm_default``;
  - ``tpm_default=0`` disables the model bucket;
  - the 429 surfaces scope="model" and the model name.
"""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from section_gateway.middleware.rate_limit import (
    RateLimitMiddleware,
    _InMemoryLimiter,
)


def _make_app(**kw) -> tuple[Starlette, RateLimitMiddleware]:
    """Build an app whose RateLimitMiddleware instance we can also poke directly.

    We construct the middleware ourselves (so we can hold a reference to
    the instance for direct API calls like ``precheck_model_tpm``) and
    install it via a small ASGI shim.
    """
    async def ok(_request):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/echo", ok)])
    mw = RateLimitMiddleware(inner, rpm=10_000, redis_url=None, **kw)

    # Wrap so TestClient sees a Starlette app while the middleware lives
    # at the outermost layer.
    outer = Starlette()
    outer.mount("/", mw)
    return outer, mw


@pytest.mark.asyncio
async def test_consume_model_tpm_debits_bucket() -> None:
    app, mw = _make_app(tpm_default=1000)
    # Consume 600 tokens. Bucket should drop to ~400.
    await mw.consume_model_tpm("tA", "gpt-4o", 600)
    allowed, _ = await mw.precheck_model_tpm("tA", "gpt-4o")
    assert allowed  # bucket still has tokens
    # Now consume the rest.
    await mw.consume_model_tpm("tA", "gpt-4o", 400)
    # Next pre-check should fail-fast (bucket empty).
    # Pre-check uses cost=0 which always allows if the bucket has *any*
    # capacity left after refill. To make the check meaningful here we
    # check via direct fallback peek.
    tokens = mw._fallback.peek("rl:model:tA:gpt-4o", 1000)
    assert tokens < 1.0


@pytest.mark.asyncio
async def test_per_model_override_applies() -> None:
    app, mw = _make_app(
        tpm_default=1000,
        tpm_per_model={"gpt-4o": 100, "claude-sonnet-4": 5000},
    )
    assert mw.tpm_capacity_for("gpt-4o") == 100
    assert mw.tpm_capacity_for("claude-sonnet-4") == 5000
    assert mw.tpm_capacity_for("unknown-model") == 1000


@pytest.mark.asyncio
async def test_tpm_default_zero_disables() -> None:
    app, mw = _make_app(tpm_default=0)
    assert mw.tpm_capacity_for("any-model") == 0
    # Consume does nothing.
    await mw.consume_model_tpm("tA", "gpt-4o", 10_000_000)
    allowed, retry_ms = await mw.precheck_model_tpm("tA", "gpt-4o")
    assert allowed and retry_ms == 0


def test_request_path_model_hint_429s_when_drained() -> None:
    app, mw = _make_app(tpm_default=10)
    # Drain the bucket directly via the fallback.
    mw._fallback.consume("rl:model:tA:gpt-4o", 10, cost=10.0)
    client = TestClient(app)
    r = client.get(
        "/echo",
        headers={
            "X-API-Key": "k",
            "X-Section-Tenant": "tA",
            "X-Section-Model-Hint": "gpt-4o",
        },
    )
    assert r.status_code == 429
    assert r.headers.get("X-Section-RateLimit-Scope") == "model"
    assert r.headers.get("X-Section-RateLimit-Model") == "gpt-4o"
    body = r.json()["error"]
    assert body["scope"] == "model"
    assert "tpm" in body["message"].lower()


def test_request_path_no_hint_skips_model_check() -> None:
    """Without the hint header the middleware can't pre-check; allow through."""
    app, mw = _make_app(tpm_default=10)
    mw._fallback.consume("rl:model:tA:gpt-4o", 10, cost=10.0)
    client = TestClient(app)
    r = client.get(
        "/echo",
        headers={"X-API-Key": "k", "X-Section-Tenant": "tA"},
    )
    assert r.status_code == 200


def test_inmem_consume_n_returns_retry_ms_when_drained() -> None:
    """The fallback computes a sensible retry_ms when cost > tokens."""
    limiter = _InMemoryLimiter()
    # Drain.
    ok, _ = limiter.consume("k", 100, cost=100.0)
    assert ok
    ok, retry_ms = limiter.consume("k", 100, cost=10.0)
    assert not ok
    # 100 capacity / 60s = ~1.67 tok/s. To get 10 tokens back takes ~6s = 6000ms.
    assert 5_000 <= retry_ms <= 7_000, retry_ms


@pytest.mark.asyncio
async def test_consume_tpm_helper_is_noop_when_no_middleware() -> None:
    """``consume_tpm_after_upstream`` must not raise when middleware absent."""
    from starlette.requests import Request

    from section_gateway.middleware.rate_limit import consume_tpm_after_upstream

    # Build a minimal Starlette scope with no rate_limiter attached.
    scope = {
        "type": "http",
        "headers": [(b"x-section-tenant", b"tA")],
        "method": "POST",
        "path": "/x",
    }
    req = Request(scope)
    # Should not raise.
    await consume_tpm_after_upstream(req, "gpt-4o", 100)
