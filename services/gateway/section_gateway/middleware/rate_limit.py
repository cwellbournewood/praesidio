"""Per-tenant + per-API-key + per-(tenant, model) rate limiting (G4).

Three independent token-bucket scopes are checked in order, all backed by
the same Redis instance (with an in-memory fallback for tests):

1. ``tenant`` — N requests-per-minute per tenant (the original Task 2.8
   bucket). Always on when the limiter is enabled.
2. ``apikey`` — N requests-per-minute per API-key fingerprint, controlled
   by ``SECTION_RATE_LIMIT_PER_KEY_RPM`` (0 disables). Useful when a
   single tenant has many keys and a misbehaving key shouldn't burn the
   tenant's whole budget.
3. ``model`` — TPM (tokens-per-minute) bucket keyed by ``(tenant, model)``,
   consumed *after* the upstream response by
   :func:`consume_tpm_after_upstream` based on ``usage.total_tokens``.
   The default is ``SECTION_RATE_LIMIT_TPM_DEFAULT``;
   ``SECTION_RATE_LIMIT_TPM_PER_MODEL`` (a JSON map) overrides per
   model. The request-path check only refuses *new* requests when the
   bucket is already empty — in-flight requests are never aborted.

Excluded paths: ``/healthz``, ``/livez``, ``/readyz``, ``/metrics`` —
liveness/observability surfaces must never be throttled.

When the limit is exceeded we return a JSON ``429`` with a ``Retry-After``
header and increment ``section_rate_limit_blocked_total{tenant,scope}``.
The response carries ``X-Section-RateLimit-Scope: tenant|apikey|model``
so SREs can debug which bucket fired. The implementation fails-open on
Redis errors: a transient Redis outage must never break DLP / audit.
"""
from __future__ import annotations

import json
import logging
import math
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..auth import api_key_fingerprint
from ..obs.metrics import RATE_LIMIT_BLOCKED_TOTAL

_log = logging.getLogger(__name__)

# Paths the limiter should never touch.
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/healthz", "/livez", "/readyz", "/metrics"}
)

# Lua script: atomic token-bucket refill+consume. Generic over capacity
# and cost so the same script backs RPM (cost=1) and TPM (cost=N) buckets.
# Returns (allowed, retry_after_ms).
_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local now_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local refill_per_ms = capacity / 60000.0

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now_ms
end
local elapsed = math.max(0, now_ms - ts)
tokens = math.min(capacity, tokens + elapsed * refill_per_ms)

local allowed = 0
local retry_ms = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_ms = math.ceil((cost - tokens) / refill_per_ms)
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now_ms)
-- TTL bounded so idle buckets get reclaimed.
redis.call('PEXPIRE', key, 120000)
return {allowed, retry_ms}
"""


class _InMemoryLimiter:
    """Fallback used when Redis is unreachable. Process-local, not cross-worker.

    The bucket is generic: each ``consume`` call passes the capacity it
    wants enforced and the cost. This lets one limiter back all three
    scopes (tenant rpm, apikey rpm, per-(tenant, model) tpm) without
    duplicating state.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    def consume(self, key: str, capacity: int, cost: float = 1.0) -> tuple[bool, int]:
        """Atomically refill+consume ``cost`` units. Returns (allowed, retry_ms)."""
        cap = max(1, int(capacity))
        cost = max(0.0, float(cost))
        now = time.monotonic() * 1000.0
        tokens, ts = self._buckets.get(key, (float(cap), now))
        elapsed = max(0.0, now - ts)
        refill = cap / 60_000.0
        tokens = min(float(cap), tokens + elapsed * refill)
        if tokens >= cost:
            tokens -= cost
            self._buckets[key] = (tokens, now)
            return True, 0
        retry_ms = int(math.ceil((cost - tokens) / refill)) if refill > 0 else 60_000
        self._buckets[key] = (tokens, now)
        return False, retry_ms

    def peek(self, key: str, capacity: int) -> float:
        """Return tokens currently in the bucket without consuming."""
        cap = max(1, int(capacity))
        now = time.monotonic() * 1000.0
        tokens, ts = self._buckets.get(key, (float(cap), now))
        elapsed = max(0.0, now - ts)
        refill = cap / 60_000.0
        return min(float(cap), tokens + elapsed * refill)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limit covering tenant, API-key, and (tenant, model) TPM.

    Parameters
    ----------
    rpm:
        Maximum sustained requests-per-minute per tenant. Always on when
        the middleware is mounted.
    redis_url:
        Redis connection URL. If ``None`` or unreachable, falls back to a
        process-local in-memory bucket (suitable for tests / single-worker
        dev). Production deployments MUST configure Redis.
    per_key_rpm:
        Optional per-API-key bucket. 0 disables. When set, a request that
        is *allowed* by the tenant bucket can still be 429'd if the
        specific API key has exhausted its share.
    tpm_default:
        Default per-(tenant, model) tokens-per-minute. 0 disables the TPM
        check entirely. The request path only refuses *new* requests when
        the model bucket is already at zero; the *cost* (actual token
        usage) is consumed after the upstream response via
        :func:`consume_tpm_after_upstream`.
    tpm_per_model:
        Optional ``{model: tpm}`` overrides for tpm_default.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        rpm: int,
        redis_url: str | None,
        per_key_rpm: int = 0,
        tpm_default: int = 0,
        tpm_per_model: dict[str, int] | None = None,
    ) -> None:
        super().__init__(app)
        self.rpm = max(1, int(rpm))
        self.per_key_rpm = max(0, int(per_key_rpm))
        self.tpm_default = max(0, int(tpm_default))
        self.tpm_per_model = dict(tpm_per_model or {})
        self.redis_url = redis_url
        self._redis = None
        self._sha: str | None = None
        self._fallback = _InMemoryLimiter()
        if redis_url:
            try:
                from redis.asyncio import from_url

                self._redis = from_url(redis_url, decode_responses=True)
            except Exception:  # pragma: no cover
                _log.warning("rate_limit: redis init failed, using in-memory fallback")
                self._redis = None

    # --- helpers ----------------------------------------------------------
    def _tenant_for(self, request: Request) -> str:
        # Prefer explicit tenant header; falls back to source IP, then "anonymous".
        t = request.headers.get("x-section-tenant")
        if t:
            return t.strip() or "anonymous"
        client = request.client.host if request.client else None
        return client or "anonymous"

    def _api_key_for(self, request: Request) -> str | None:
        """Return the API-key fingerprint, or None if no key is present."""
        raw = request.headers.get("x-api-key")
        if not raw:
            auth = request.headers.get("authorization") or ""
            parts = auth.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw = parts[1].strip()
        if not raw:
            return None
        return api_key_fingerprint(raw)

    def tpm_capacity_for(self, model: str | None) -> int:
        """Resolve TPM capacity for ``model`` (0 means disabled)."""
        if not self.tpm_default and not self.tpm_per_model:
            return 0
        if model and model in self.tpm_per_model:
            return self.tpm_per_model[model]
        return self.tpm_default

    async def _consume(self, key: str, capacity: int, cost: float = 1.0) -> tuple[bool, int]:
        """Consume ``cost`` units from the bucket at ``key`` with ``capacity``."""
        if self._redis is not None:
            try:
                if self._sha is None:
                    self._sha = await self._redis.script_load(_LUA)
                now_ms = int(time.time() * 1000)
                result = await self._redis.evalsha(
                    self._sha, 1, key, str(int(capacity)), str(now_ms), str(cost)
                )
                allowed = int(result[0]) == 1
                retry_ms = int(result[1])
                return allowed, retry_ms
            except Exception:
                _log.warning("rate_limit: redis call failed, using in-memory fallback")
        return self._fallback.consume(key, capacity, cost)

    def _block_response(
        self,
        *,
        scope: str,
        tenant: str,
        limit: int,
        retry_ms: int,
        message: str,
        extra_headers: dict[str, str] | None = None,
    ) -> Response:
        RATE_LIMIT_BLOCKED_TOTAL.labels(tenant=tenant, scope=scope).inc()
        retry_after_s = max(1, math.ceil(retry_ms / 1000))
        body = json.dumps(
            {
                "error": {
                    "type": "rate_limited",
                    "scope": scope,
                    "message": message,
                    "tenant": tenant,
                }
            }
        ).encode("utf-8")
        headers = {
            "Retry-After": str(retry_after_s),
            "X-Section-RateLimit-Limit": str(limit),
            "X-Section-RateLimit-Tenant": tenant,
            "X-Section-RateLimit-Scope": scope,
        }
        if extra_headers:
            headers.update(extra_headers)
        return Response(
            content=body,
            status_code=429,
            media_type="application/json",
            headers=headers,
        )

    async def precheck_model_tpm(self, tenant: str, model: str) -> tuple[bool, int]:
        """Check (without consuming) whether the (tenant, model) bucket has
        at least one token left. Used at request-admission time so we
        don't accept a new request once the bucket is fully drained.

        Returns ``(allowed, retry_ms)``. ``allowed=False`` only when the
        bucket has strictly < 1 token after refill — i.e. no useful work
        can be done. The actual cost is debited later by
        :meth:`consume_model_tpm` after the upstream returns.
        """
        cap = self.tpm_capacity_for(model)
        if cap <= 0:
            return True, 0
        key = f"rl:model:{tenant}:{model}"
        # Redis path: HMGET the stored tokens/ts and apply the same
        # refill formula. No mutation, no probe-token side effects.
        if self._redis is not None:
            try:
                data = await self._redis.hmget(key, "tokens", "ts")
                stored_tokens = float(data[0]) if data[0] is not None else float(cap)
                stored_ts = float(data[1]) if data[1] is not None else float(
                    time.time() * 1000
                )
                now_ms = time.time() * 1000.0
                elapsed = max(0.0, now_ms - stored_ts)
                refill = cap / 60_000.0
                tokens = min(float(cap), stored_tokens + elapsed * refill)
                if tokens >= 1.0:
                    return True, 0
                retry_ms = int(math.ceil((1.0 - tokens) / refill)) if refill > 0 else 60_000
                return False, retry_ms
            except Exception:
                _log.warning("rate_limit: redis tpm precheck failed, falling back")
        # Fallback: pure read of the in-memory bucket.
        tokens = self._fallback.peek(key, cap)
        if tokens >= 1.0:
            return True, 0
        refill = cap / 60_000.0
        retry_ms = int(math.ceil((1.0 - tokens) / refill)) if refill > 0 else 60_000
        return False, retry_ms

    async def consume_model_tpm(self, tenant: str, model: str, tokens: int) -> None:
        """Consume ``tokens`` from the (tenant, model) bucket post-upstream.

        Best-effort: failures are swallowed because TPM accounting must
        never break a request that the upstream already completed.
        """
        cap = self.tpm_capacity_for(model)
        if cap <= 0 or tokens <= 0:
            return
        try:
            await self._consume(f"rl:model:{tenant}:{model}", cap, cost=float(tokens))
        except Exception:  # pragma: no cover - defensive
            _log.warning("rate_limit: model TPM consume failed", exc_info=True)

    # --- middleware entry --------------------------------------------------
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        tenant = self._tenant_for(request)

        # 1) per-tenant RPM
        allowed, retry_ms = await self._consume(f"rl:tenant:{tenant}", self.rpm)
        if not allowed:
            return self._block_response(
                scope="tenant",
                tenant=tenant,
                limit=self.rpm,
                retry_ms=retry_ms,
                message=(
                    f"per-tenant rate limit exceeded ({self.rpm} rpm); "
                    f"retry in {max(1, math.ceil(retry_ms / 1000))}s"
                ),
            )

        # 2) per-API-key RPM (if configured)
        if self.per_key_rpm > 0:
            fp = self._api_key_for(request)
            if fp is not None:
                allowed, retry_ms = await self._consume(
                    f"rl:apikey:{fp}", self.per_key_rpm
                )
                if not allowed:
                    return self._block_response(
                        scope="apikey",
                        tenant=tenant,
                        limit=self.per_key_rpm,
                        retry_ms=retry_ms,
                        message=(
                            f"per-API-key rate limit exceeded ({self.per_key_rpm} rpm); "
                            f"retry in {max(1, math.ceil(retry_ms / 1000))}s"
                        ),
                        extra_headers={"X-Section-RateLimit-Key": fp},
                    )

        # 3) per-(tenant, model) TPM pre-check. The downstream proxy reads
        # the model name from the request body and calls
        # ``consume_model_tpm`` after the upstream returns. Here we only
        # check that the bucket isn't already empty — we don't know the
        # cost yet at admission time.
        # (Pre-check is opt-in via a header so we don't have to parse the
        # body in middleware. The orchestrator can set
        # ``X-Section-Model-Hint`` from the parsed payload before the
        # upstream call, or simply rely on post-hoc consume.)
        model_hint = request.headers.get("x-section-model-hint")
        if model_hint and self.tpm_capacity_for(model_hint) > 0:
            allowed, retry_ms = await self.precheck_model_tpm(tenant, model_hint)
            if not allowed:
                cap = self.tpm_capacity_for(model_hint)
                return self._block_response(
                    scope="model",
                    tenant=tenant,
                    limit=cap,
                    retry_ms=retry_ms,
                    message=(
                        f"per-(tenant, model) TPM exceeded for {model_hint} "
                        f"({cap} tpm); retry in {max(1, math.ceil(retry_ms / 1000))}s"
                    ),
                    extra_headers={"X-Section-RateLimit-Model": model_hint},
                )

        # Stash a reference so handlers can call consume_model_tpm post-upstream.
        request.state.rate_limiter = self  # type: ignore[attr-defined]
        return await call_next(request)


async def consume_tpm_after_upstream(
    request: Request, model: str, total_tokens: int
) -> None:
    """Convenience helper for route handlers.

    Reads the rate limiter off ``request.state`` (set by the middleware)
    and consumes ``total_tokens`` from the (tenant, model) bucket. Safe
    to call when the middleware is disabled — it's a no-op.
    """
    limiter = getattr(request.state, "rate_limiter", None)
    if limiter is None:
        return
    tenant = request.headers.get("x-section-tenant", "anonymous").strip() or "anonymous"
    await limiter.consume_model_tpm(tenant, model, total_tokens)
