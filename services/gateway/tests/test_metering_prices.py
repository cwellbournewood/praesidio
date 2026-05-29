"""Token / cost metering and price book (G5).

Covers:
  * Default price book values for common models;
  * Override via PRAESIDIO_PRICE_BOOK_JSON;
  * Unknown model returns 0.0 cost (and warns once);
  * extract_usage understands OpenAI / Anthropic / Bedrock / Ollama shapes;
  * record_usage_from_payload bumps the three Prometheus counters.
"""
from __future__ import annotations

import importlib

import pytest

from praesidio_gateway.obs import prices as prices_mod
from praesidio_gateway.obs.metering import (
    extract_usage,
    record_usage_from_payload,
)
from praesidio_gateway.obs.metrics import (
    COST_USD_TOTAL,
    TOKENS_IN_TOTAL,
    TOKENS_OUT_TOTAL,
)


def _counter(metric, labels: dict[str, str]) -> float:
    for fam in metric.collect():
        for s in fam.samples:
            if not s.name.endswith("_total"):
                continue
            if all(s.labels.get(k) == v for k, v in labels.items()):
                return s.value
    return 0.0


# ---- price book -----------------------------------------------------------

def test_default_prices_known_models() -> None:
    """Spot-check a couple of public list prices."""
    assert prices_mod.price_for("gpt-4o") is not None
    assert prices_mod.price_for("claude-3-5-sonnet-20241022") is not None
    # Case-insensitive lookup.
    assert prices_mod.price_for("GPT-4O") == prices_mod.price_for("gpt-4o")


def test_unknown_model_returns_zero_cost(caplog) -> None:
    prices_mod.reset_unknown_warned()
    with caplog.at_level("WARNING"):
        c = prices_mod.estimate_cost("totally-fake-model-xyz", 1_000_000, 1_000_000)
    assert c == 0.0
    # Warns once...
    assert any("totally-fake-model-xyz" in r.message for r in caplog.records)
    # ...and only once for the same key.
    caplog.clear()
    with caplog.at_level("WARNING"):
        prices_mod.estimate_cost("totally-fake-model-xyz", 100, 100)
    assert not any("totally-fake-model-xyz" in r.message for r in caplog.records)


def test_estimate_cost_math() -> None:
    p = prices_mod.price_for("gpt-4o")
    assert p is not None
    # 1000 in + 500 out at (0.0025, 0.010) = 0.0025 + 0.005 = 0.0075
    c = prices_mod.estimate_cost("gpt-4o", 1000, 500)
    assert abs(c - (1.0 * p.input_per_1k + 0.5 * p.output_per_1k)) < 1e-9


def test_price_book_json_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "PRAESIDIO_PRICE_BOOK_JSON",
        '{"my-private-model": {"input_per_1k": 0.5, "output_per_1k": 1.0}}',
    )
    # Force reload so the module re-reads the env.
    importlib.reload(prices_mod)
    p = prices_mod.price_for("my-private-model")
    assert p is not None
    assert p.input_per_1k == 0.5
    assert p.output_per_1k == 1.0
    # 1000 in + 1000 out = 0.5 + 1.0 = 1.5 USD
    assert abs(prices_mod.estimate_cost("my-private-model", 1000, 1000) - 1.5) < 1e-9


def test_price_book_malformed_json_ignored(monkeypatch, caplog) -> None:
    monkeypatch.setenv("PRAESIDIO_PRICE_BOOK_JSON", "{not json")
    with caplog.at_level("WARNING"):
        importlib.reload(prices_mod)
    # Default catalogue still works.
    assert prices_mod.price_for("gpt-4o") is not None


# ---- usage extraction -----------------------------------------------------

def test_extract_usage_openai_shape() -> None:
    assert extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 50}}) == (
        100,
        50,
    )


def test_extract_usage_anthropic_shape() -> None:
    assert extract_usage({"usage": {"input_tokens": 120, "output_tokens": 60}}) == (120, 60)


def test_extract_usage_bedrock_shape() -> None:
    assert extract_usage({"usage": {"inputTokens": 7, "outputTokens": 8}}) == (7, 8)


def test_extract_usage_ollama_shape() -> None:
    assert extract_usage({"prompt_eval_count": 11, "eval_count": 22}) == (11, 22)


def test_extract_usage_missing_returns_zeros() -> None:
    assert extract_usage({}) == (0, 0)
    assert extract_usage(None) == (0, 0)
    assert extract_usage({"usage": "not-a-dict"}) == (0, 0)


# ---- counter integration --------------------------------------------------

def test_record_usage_bumps_counters() -> None:
    tenant, model, route = "tenant-A", "gpt-4o", "/v1/chat/completions"
    before_in = _counter(TOKENS_IN_TOTAL, {"tenant": tenant, "model": model, "route": route})
    before_out = _counter(TOKENS_OUT_TOTAL, {"tenant": tenant, "model": model, "route": route})
    before_cost = _counter(COST_USD_TOTAL, {"tenant": tenant, "model": model})

    ti, to, cost = record_usage_from_payload(
        tenant=tenant,
        model=model,
        route=route,
        payload={"usage": {"prompt_tokens": 200, "completion_tokens": 80}},
    )
    assert ti == 200
    assert to == 80
    assert cost > 0  # known model

    after_in = _counter(TOKENS_IN_TOTAL, {"tenant": tenant, "model": model, "route": route})
    after_out = _counter(TOKENS_OUT_TOTAL, {"tenant": tenant, "model": model, "route": route})
    after_cost = _counter(COST_USD_TOTAL, {"tenant": tenant, "model": model})
    assert after_in == pytest.approx(before_in + 200)
    assert after_out == pytest.approx(before_out + 80)
    assert after_cost > before_cost
