"""Per-API-key rate limit bucket (G4).

Verifies that the apikey-scoped bucket trips independently of the
tenant bucket, surfaces the right ``X-Section-RateLimit-Scope`` and
``Retry-After`` headers, and increments
``section_rate_limit_blocked_total{scope="apikey"}``.
"""
from __future__ import annotations

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from section_gateway.middleware.rate_limit import RateLimitMiddleware
from section_gateway.obs.metrics import RATE_LIMIT_BLOCKED_TOTAL


def _make_app(*, rpm: int, per_key_rpm: int) -> Starlette:
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/echo", ok)])
    app.add_middleware(
        RateLimitMiddleware,
        rpm=rpm,
        redis_url=None,  # force in-memory fallback
        per_key_rpm=per_key_rpm,
    )
    return app


def _blocked_value(scope: str, tenant: str = "tA") -> float:
    for fam in RATE_LIMIT_BLOCKED_TOTAL.collect():
        for s in fam.samples:
            if (
                s.name.endswith("_total")
                and s.labels.get("scope") == scope
                and s.labels.get("tenant") == tenant
            ):
                return s.value
    return 0.0


def test_per_key_bucket_trips_before_tenant() -> None:
    """A misbehaving key should 429 even though tenant budget is large."""
    app = _make_app(rpm=10_000, per_key_rpm=3)
    client = TestClient(app)
    headers = {"X-API-Key": "secret-key-1", "X-Section-Tenant": "tA"}
    # 3 allowed, 4th blocked.
    for _ in range(3):
        r = client.get("/echo", headers=headers)
        assert r.status_code == 200, r.text
    r = client.get("/echo", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("X-Section-RateLimit-Scope") == "apikey"
    assert r.headers.get("Retry-After") is not None
    # Key fingerprint header surfaced for SRE debugging.
    assert r.headers.get("X-Section-RateLimit-Key")
    body = r.json()["error"]
    assert body["scope"] == "apikey"
    assert body["type"] == "rate_limited"


def test_different_keys_have_independent_buckets() -> None:
    app = _make_app(rpm=10_000, per_key_rpm=2)
    client = TestClient(app)
    h1 = {"X-API-Key": "key-aaa", "X-Section-Tenant": "tA"}
    h2 = {"X-API-Key": "key-bbb", "X-Section-Tenant": "tA"}
    for _ in range(2):
        assert client.get("/echo", headers=h1).status_code == 200
        assert client.get("/echo", headers=h2).status_code == 200
    # Both keys now empty.
    assert client.get("/echo", headers=h1).status_code == 429
    assert client.get("/echo", headers=h2).status_code == 429


def test_tenant_bucket_trips_independently_of_key() -> None:
    """If tenant bucket is the binding constraint, scope label is 'tenant'."""
    app = _make_app(rpm=2, per_key_rpm=1_000)
    client = TestClient(app)
    headers = {"X-API-Key": "k", "X-Section-Tenant": "tA"}
    for _ in range(2):
        assert client.get("/echo", headers=headers).status_code == 200
    r = client.get("/echo", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("X-Section-RateLimit-Scope") == "tenant"


def test_per_key_disabled_when_zero() -> None:
    """per_key_rpm=0 disables the apikey bucket entirely."""
    app = _make_app(rpm=10_000, per_key_rpm=0)
    client = TestClient(app)
    headers = {"X-API-Key": "k", "X-Section-Tenant": "tA"}
    for _ in range(50):
        assert client.get("/echo", headers=headers).status_code == 200


def test_per_key_uses_bearer_token() -> None:
    """Bearer auth also feeds the per-key bucket via fingerprint."""
    app = _make_app(rpm=10_000, per_key_rpm=2)
    client = TestClient(app)
    headers = {"Authorization": "Bearer bearer-key", "X-Section-Tenant": "tA"}
    for _ in range(2):
        assert client.get("/echo", headers=headers).status_code == 200
    r = client.get("/echo", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("X-Section-RateLimit-Scope") == "apikey"


def test_blocked_metric_increments_with_scope_label() -> None:
    app = _make_app(rpm=10_000, per_key_rpm=1)
    client = TestClient(app)
    headers = {"X-API-Key": "metric-key", "X-Section-Tenant": "tA"}
    before = _blocked_value("apikey")
    assert client.get("/echo", headers=headers).status_code == 200
    assert client.get("/echo", headers=headers).status_code == 429
    after = _blocked_value("apikey")
    assert after >= before + 1


@pytest.mark.asyncio
async def test_inmem_bucket_refills_over_time() -> None:
    """After waiting, a previously-exhausted bucket should let one request through."""
    from section_gateway.middleware.rate_limit import _InMemoryLimiter

    limiter = _InMemoryLimiter()
    # capacity=60 ⇒ refill rate 1 token / sec.
    for _ in range(60):
        ok, _ = limiter.consume("k", 60)
        assert ok
    ok, _retry = limiter.consume("k", 60)
    assert not ok
    # Sleep a hair over 1s so at least one token has refilled.
    await asyncio.sleep(1.05)
    ok, _ = limiter.consume("k", 60)
    assert ok
