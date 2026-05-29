"""Provider price book — USD per 1K tokens, by model (G5).

Prices are operator-overridable via ``PRAESIDIO_PRICE_BOOK_JSON`` (a JSON
map of ``{"model_id": {"input_per_1k": float, "output_per_1k": float}}``).
The defaults below track public list prices as of 2026-05 — they're for
*estimation*, not billing. Operators wiring exact billing should source
prices from their cloud-provider contract.

The cost computation is intentionally simple::

    cost_usd = (tokens_in / 1000) * input_per_1k
             + (tokens_out / 1000) * output_per_1k

Unknown models cost 0 — we never *over*-charge in the metric. A WARN log
is emitted once per unknown model so operators can extend the book.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Price:
    """USD per 1K tokens for input (prompt) and output (completion)."""

    input_per_1k: float
    output_per_1k: float


# Default catalogue. Conservative public list prices, USD per 1K tokens.
# Keys are normalised: lowercased, no whitespace.
_DEFAULT_PRICES: dict[str, Price] = {
    # OpenAI
    "gpt-4o": Price(0.0025, 0.010),
    "gpt-4o-mini": Price(0.00015, 0.0006),
    "gpt-4-turbo": Price(0.010, 0.030),
    "gpt-4": Price(0.030, 0.060),
    "gpt-3.5-turbo": Price(0.0005, 0.0015),
    # Anthropic
    "claude-3-5-sonnet-20241022": Price(0.003, 0.015),
    "claude-3-5-sonnet": Price(0.003, 0.015),
    "claude-3-5-haiku-20241022": Price(0.0008, 0.004),
    "claude-3-opus-20240229": Price(0.015, 0.075),
    "claude-3-sonnet-20240229": Price(0.003, 0.015),
    "claude-3-haiku-20240307": Price(0.00025, 0.00125),
    "claude-sonnet-4": Price(0.003, 0.015),
    "claude-opus-4": Price(0.015, 0.075),
    # AWS Bedrock pass-throughs (same per-model prices, different routing).
    "anthropic.claude-3-5-sonnet-20241022-v2:0": Price(0.003, 0.015),
    "anthropic.claude-3-haiku-20240307-v1:0": Price(0.00025, 0.00125),
    # Local / open-weights — zero per-token cost.
    "llama3": Price(0.0, 0.0),
    "mistral": Price(0.0, 0.0),
}

_unknown_warned: set[str] = set()


def _normalise(model: str) -> str:
    return model.strip().lower()


def _load_overrides() -> dict[str, Price]:
    raw = os.environ.get("PRAESIDIO_PRICE_BOOK_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, Price] = {}
        for k, v in parsed.items():
            if not isinstance(v, dict):
                continue
            try:
                out[_normalise(str(k))] = Price(
                    input_per_1k=float(v.get("input_per_1k", 0.0)),
                    output_per_1k=float(v.get("output_per_1k", 0.0)),
                )
            except (TypeError, ValueError):
                continue
        return out
    except json.JSONDecodeError:
        _log.warning("PRAESIDIO_PRICE_BOOK_JSON is not valid JSON; ignoring overrides")
        return {}


_OVERRIDES = _load_overrides()


def price_for(model: str) -> Price | None:
    """Return the :class:`Price` for ``model`` or ``None`` if unknown.

    Override book wins over defaults. ``None`` causes :func:`estimate_cost`
    to return 0 and log once.
    """
    if not model:
        return None
    key = _normalise(model)
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    return _DEFAULT_PRICES.get(key)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for an interaction.

    Returns 0.0 for unknown models (one WARN log per unique unknown name).
    Negative token counts are clamped to zero.
    """
    p = price_for(model)
    if p is None:
        key = _normalise(model or "")
        if key and key not in _unknown_warned:
            _unknown_warned.add(key)
            _log.warning(
                "price_book: unknown model %r — cost metric will be 0. Set "
                "PRAESIDIO_PRICE_BOOK_JSON to override.",
                model,
            )
        return 0.0
    ti = max(0, int(tokens_in))
    to = max(0, int(tokens_out))
    return (ti / 1000.0) * p.input_per_1k + (to / 1000.0) * p.output_per_1k


def reset_unknown_warned() -> None:
    """Test hook — clear the dedup set so the same model warns again."""
    _unknown_warned.clear()
