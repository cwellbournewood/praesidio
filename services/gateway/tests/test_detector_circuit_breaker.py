"""Detector circuit breaker wiring (Task 5.5).

After >5 errors in a 60s rolling window, the breaker opens for 30s. The
next pipeline run skips the failing detector entirely, marks the result
``degraded=True`` and bumps the
``section_detector_breaker_opens_total`` counter.
"""
from __future__ import annotations

import pytest

from section_gateway.dlp import pipeline as pl
from section_gateway.obs.metrics import DETECTOR_BREAKER_OPENS_TOTAL


@pytest.fixture(autouse=True)
def _reset_breakers():
    pl._reset_breakers_for_tests()
    yield
    pl._reset_breakers_for_tests()


def _counter_value(detector: str) -> float:
    sample = DETECTOR_BREAKER_OPENS_TOTAL.labels(detector=detector)
    # prometheus_client Counter exposes ._value.get()
    return sample._value.get()


@pytest.mark.asyncio
async def test_breaker_trips_after_threshold_errors(monkeypatch):
    """Simulate 6 errors in the regex detector → breaker opens, counter +1."""
    calls = {"n": 0}

    async def _boom(text: str):
        calls["n"] += 1
        raise RuntimeError("detector blew up")

    # Patch only the regex detector so we have a stable handle.
    monkeypatch.setitem(pl._DEFAULT_DETECTORS, "regex", _boom)
    before = _counter_value("regex")

    # Each call increments the breaker error count once.
    for _ in range(6):
        await pl.run_pipeline("anything", enable=["pii.email"])

    # 6th call (index 5) is the first to exceed the >5 threshold → trip.
    after = _counter_value("regex")
    assert after - before == pytest.approx(1.0)

    # The 7th call should skip the regex detector via the open breaker:
    # call count must stay at 6 (no new call into the failing detector).
    result = await pl.run_pipeline("more text", enable=["pii.email"])
    assert calls["n"] == 6
    assert "regex" in result.skipped
    assert result.degraded is True


@pytest.mark.asyncio
async def test_breaker_self_heals_after_open_window(monkeypatch):
    """Manually expire the open state and confirm the next run calls the detector again."""
    calls = {"n": 0}

    async def _boom(text: str):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setitem(pl._DEFAULT_DETECTORS, "regex", _boom)

    # Trip the breaker.
    for _ in range(6):
        await pl.run_pipeline("x", enable=["pii.email"])
    breaker = pl._breaker_for("regex")
    assert breaker.is_open(__import__("time").monotonic())

    # Fast-forward by clearing open-until.
    breaker._opened_until = 0.0
    breaker._errors.clear()

    # Detector is invoked again now.
    pre = calls["n"]
    await pl.run_pipeline("y", enable=["pii.email"])
    assert calls["n"] == pre + 1


@pytest.mark.asyncio
async def test_pipeline_clean_when_no_errors():
    """Sanity: a healthy run is not flagged degraded."""
    result = await pl.run_pipeline("hello world", enable=["pii.email"])
    assert result.degraded is False
    assert result.skipped == []
