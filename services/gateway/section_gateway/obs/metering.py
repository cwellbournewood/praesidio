"""Token / cost metering glue (G5).

One entry-point :func:`record_usage` that takes whatever the upstream
returned (an OpenAI-shaped ``usage`` dict, an Anthropic-shaped one, or a
raw ``(tokens_in, tokens_out)`` pair) and:

  * increments ``section_tokens_in_total{tenant,model,route}``
  * increments ``section_tokens_out_total{tenant,model,route}``
  * increments ``section_cost_usd_total{tenant,model}`` (from
    :mod:`section_gateway.obs.prices`)
  * debits the per-(tenant, model) TPM bucket via the rate-limit
    middleware (no-op when the limiter isn't mounted).

Failures are swallowed — metering must never break a request whose
upstream already returned successfully.
"""
from __future__ import annotations

import logging
from typing import Any

from starlette.requests import Request

from .metrics import COST_USD_TOTAL, TOKENS_IN_TOTAL, TOKENS_OUT_TOTAL
from .prices import estimate_cost

_log = logging.getLogger(__name__)


def extract_usage(payload: Any) -> tuple[int, int]:
    """Pull ``(tokens_in, tokens_out)`` out of various provider shapes.

    Supported:
      * OpenAI:    ``{"usage": {"prompt_tokens": N, "completion_tokens": M}}``
      * Anthropic: ``{"usage": {"input_tokens": N, "output_tokens": M}}``
      * Bedrock:   ``{"usage": {"inputTokens": N, "outputTokens": M}}``
      * Ollama:    ``{"prompt_eval_count": N, "eval_count": M}``

    Returns ``(0, 0)`` when the payload is missing or unrecognised.
    """
    if not isinstance(payload, dict):
        return 0, 0
    usage = payload.get("usage")
    if isinstance(usage, dict):
        # Try each known key family.
        in_keys = ("prompt_tokens", "input_tokens", "inputTokens")
        out_keys = ("completion_tokens", "output_tokens", "outputTokens")
        ti = next((int(usage[k]) for k in in_keys if isinstance(usage.get(k), (int, float))), 0)
        to = next((int(usage[k]) for k in out_keys if isinstance(usage.get(k), (int, float))), 0)
        if ti or to:
            return ti, to
        # Some providers only expose total_tokens.
        total = usage.get("total_tokens") or usage.get("totalTokens")
        if isinstance(total, (int, float)):
            return int(total), 0
    # Ollama-style flat fields.
    if isinstance(payload.get("prompt_eval_count"), int) or isinstance(
        payload.get("eval_count"), int
    ):
        return int(payload.get("prompt_eval_count", 0)), int(payload.get("eval_count", 0))
    return 0, 0


async def record_usage(
    *,
    request: Request | None,
    tenant: str,
    model: str,
    route: str,
    tokens_in: int,
    tokens_out: int,
) -> float:
    """Record usage counters and debit the TPM bucket. Returns USD cost.

    ``request`` is optional; when provided, the per-(tenant, model) TPM
    bucket attached to the rate-limit middleware is debited by
    ``tokens_in + tokens_out``.
    """
    ti = max(0, int(tokens_in))
    to = max(0, int(tokens_out))
    cost = 0.0
    try:
        TOKENS_IN_TOTAL.labels(tenant=tenant, model=model, route=route).inc(ti)
        TOKENS_OUT_TOTAL.labels(tenant=tenant, model=model, route=route).inc(to)
        cost = estimate_cost(model, ti, to)
        if cost > 0:
            COST_USD_TOTAL.labels(tenant=tenant, model=model).inc(cost)
    except Exception:  # pragma: no cover - metrics are best-effort
        _log.warning("record_usage: counter increment failed", exc_info=True)

    if request is not None and (ti + to) > 0:
        limiter = getattr(request.state, "rate_limiter", None)
        if limiter is not None:
            try:
                await limiter.consume_model_tpm(tenant, model, ti + to)
            except Exception:  # pragma: no cover
                _log.warning("record_usage: TPM consume failed", exc_info=True)
    return cost


def record_usage_from_payload(
    *,
    tenant: str,
    model: str,
    route: str,
    payload: Any,
) -> tuple[int, int, float]:
    """Sync convenience for handlers that already parsed the response JSON.

    Skips the async TPM debit step (callers in the async path should
    use :func:`record_usage` instead). Returns
    ``(tokens_in, tokens_out, cost_usd)``.
    """
    ti, to = extract_usage(payload)
    try:
        TOKENS_IN_TOTAL.labels(tenant=tenant, model=model, route=route).inc(ti)
        TOKENS_OUT_TOTAL.labels(tenant=tenant, model=model, route=route).inc(to)
        cost = estimate_cost(model, ti, to)
        if cost > 0:
            COST_USD_TOTAL.labels(tenant=tenant, model=model).inc(cost)
        return ti, to, cost
    except Exception:  # pragma: no cover
        _log.warning("record_usage_from_payload: counter increment failed", exc_info=True)
        return ti, to, 0.0
