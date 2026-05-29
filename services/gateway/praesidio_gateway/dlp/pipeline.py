"""Concurrent DLP pipeline.

Each detector runs as a coroutine with a soft per-detector deadline. Findings
from all detectors are merged; spans are deduplicated within a label by exact
(start, end) match. Heavy ML detectors that miss the deadline are skipped and
the pipeline reports `partial=True` so the caller can flag the audit row.

A per-detector circuit breaker tracks errors in a rolling 60-second window.
When a detector exceeds the open threshold (>5 errors in 60s) the breaker
opens for 30 seconds: the pipeline skips that detector for the duration,
emits :data:`praesidio_gateway.obs.metrics.DETECTOR_BREAKER_OPENS_TOTAL`,
and marks the result ``degraded=True`` so audit rows reflect the partial
scan.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from ..obs.metrics import DETECTOR_BREAKER_OPENS_TOTAL, DETECTOR_LATENCY
from .detectors import code as det_code
from .detectors import llm_classifier as det_llm_classifier
from .detectors import prompt_injection as det_pi
from .detectors import regex as det_regex
from .detectors import secrets as det_secrets
from .types import Finding

# Registered detectors. Operators can add more by importing here.
_DEFAULT_DETECTORS = {
    "regex": det_regex.detect,
    "secrets": det_secrets.detect,
    "code": det_code.detect,
    "prompt_injection": det_pi.detect,
    # G8: opt-in LLM classifier. Returns 0 findings when
    # PRAESIDIO_LLM_CLASSIFIER_URL is unset.
    "llm_classifier": det_llm_classifier.detect,
}


@dataclass
class PipelineResult:
    findings: list[Finding] = field(default_factory=list)
    partial: bool = False
    skipped: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    degraded: bool = False


# ---------------------------------------------------------------------------
# Per-detector circuit breaker
# ---------------------------------------------------------------------------

# Tunables (module-level so tests can monkeypatch without rebuilding state).
BREAKER_WINDOW_SECONDS = 60.0
BREAKER_ERROR_THRESHOLD = 5  # >5 errors in window opens the breaker
BREAKER_OPEN_SECONDS = 30.0


class _CircuitBreaker:
    """Rolling-window error counter with timed open state. Per-detector."""

    __slots__ = ("_errors", "_opened_until")

    def __init__(self) -> None:
        self._errors: deque[float] = deque()
        self._opened_until: float = 0.0

    def is_open(self, now: float) -> bool:
        return now < self._opened_until

    def record_error(self, now: float) -> bool:
        """Record an error; returns True if this call tripped the breaker."""
        self._errors.append(now)
        self._evict(now)
        if (
            len(self._errors) > BREAKER_ERROR_THRESHOLD
            and not self.is_open(now)
        ):
            self._opened_until = now + BREAKER_OPEN_SECONDS
            return True
        return False

    def record_success(self, now: float) -> None:
        # Successes age the window but don't reset it — the breaker self-heals
        # purely on time + absence of new errors.
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - BREAKER_WINDOW_SECONDS
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()


_BREAKERS: dict[str, _CircuitBreaker] = {}


def _breaker_for(name: str) -> _CircuitBreaker:
    b = _BREAKERS.get(name)
    if b is None:
        b = _CircuitBreaker()
        _BREAKERS[name] = b
    return b


def _reset_breakers_for_tests() -> None:
    """Test-only: clear all breaker state between cases."""
    _BREAKERS.clear()


# Map each label category to the detector engines that can produce it.
# Categories are the first segment of the canonical label (`pii.person` →
# `pii`). Multiple engines can cover the same category — the policy
# engine's overlap-resolver deduplicates within a label.
_CATEGORY_TO_DETECTORS: dict[str, tuple[str, ...]] = {
    "pii":         ("regex", "presidio"),
    "financial":   ("regex", "presidio"),
    "network":     ("regex", "presidio"),
    "credential":  ("secrets",),
    "code":        ("code",),
    "infra":       ("regex",),
    "behavior":    ("prompt_injection", "llm_classifier"),
    "healthcare":  ("presidio",),
}

# Labels that ONLY Presidio can detect. If none of `enable` falls inside
# this set, we skip loading the heavy spaCy model entirely.
_PRESIDIO_ONLY_LABELS: frozenset[str] = frozenset({
    "pii.person",
    "pii.location",
    "pii.organization",
    "pii.nationality",
    "pii.us_drivers_license",
    "pii.date",
    "pii.url",
    "healthcare.medical_license",
    "network.ip_address",  # Presidio's generic IP label; regex emits ipv4/ipv6 separately
})


def _build_active(enable: list[str] | None) -> dict[str, callable]:
    if not enable:
        # If a policy disabled detection, run only the always-on fast lane.
        return {"regex": _DEFAULT_DETECTORS["regex"], "secrets": _DEFAULT_DETECTORS["secrets"]}
    out: dict[str, callable] = {}
    for label in enable:
        category = label.split(".", 1)[0]
        for det_name in _CATEGORY_TO_DETECTORS.get(category, ()):
            # presidio is optional and heavy: only attach when the enable
            # set contains a label Presidio is the only source for.
            if det_name == "presidio":
                if label not in _PRESIDIO_ONLY_LABELS:
                    continue
                from .detectors import presidio as det_presidio  # local import: heavy

                out["presidio"] = det_presidio.detect
            elif det_name in _DEFAULT_DETECTORS:
                out[det_name] = _DEFAULT_DETECTORS[det_name]
    return out or {"regex": _DEFAULT_DETECTORS["regex"]}


def _filter_by_enabled(findings: list[Finding], enabled: set[str]) -> list[Finding]:
    if not enabled:
        return findings
    return [f for f in findings if f.label in enabled]


def _apply_thresholds(findings: list[Finding], thresholds: dict[str, float]) -> list[Finding]:
    if not thresholds:
        return findings
    out: list[Finding] = []
    for f in findings:
        cutoff = thresholds.get(f.label)
        if cutoff is None or f.confidence >= cutoff:
            out.append(f)
    return out


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, int, int]] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f.label, f.start, f.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


async def _run_with_deadline(
    name: str, fn, text: str, deadline_s: float
) -> tuple[str, list[Finding] | None, bool]:
    """Run a detector with deadline + circuit-breaker tracking.

    Returns ``(name, findings_or_None_if_timeout, errored)``.
    """
    t0 = time.perf_counter()
    breaker = _breaker_for(name)
    try:
        res = await asyncio.wait_for(fn(text), timeout=deadline_s)
    except TimeoutError:
        DETECTOR_LATENCY.labels(detector=name).observe(time.perf_counter() - t0)
        return name, None, False
    except Exception:
        DETECTOR_LATENCY.labels(detector=name).observe(time.perf_counter() - t0)
        if breaker.record_error(time.monotonic()):
            DETECTOR_BREAKER_OPENS_TOTAL.labels(detector=name).inc()
        return name, [], True
    DETECTOR_LATENCY.labels(detector=name).observe(time.perf_counter() - t0)
    breaker.record_success(time.monotonic())
    return name, res, False


async def run_pipeline(
    text: str,
    *,
    enable: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
    deadline_s: float = 0.08,
) -> PipelineResult:
    t_start = time.perf_counter()
    detectors = _build_active(enable)
    enabled_set = set(enable or [])

    # Skip any detector whose circuit breaker is currently open.
    now = time.monotonic()
    active: dict[str, callable] = {}
    skipped_by_breaker: list[str] = []
    for n, fn in detectors.items():
        if _breaker_for(n).is_open(now):
            skipped_by_breaker.append(n)
        else:
            active[n] = fn

    coros = [_run_with_deadline(n, fn, text, deadline_s) for n, fn in active.items()]
    raw = await asyncio.gather(*coros, return_exceptions=False)

    findings: list[Finding] = []
    skipped: list[str] = list(skipped_by_breaker)
    any_errored = False
    for name, result, errored in raw:
        if errored:
            any_errored = True
        if result is None:
            skipped.append(name)
            continue
        findings.extend(result)

    findings = _filter_by_enabled(findings, enabled_set)
    findings = _apply_thresholds(findings, thresholds or {})
    findings = _dedupe(findings)
    findings.sort(key=lambda f: (f.start, -f.end))

    return PipelineResult(
        findings=findings,
        partial=bool(skipped),
        skipped=skipped,
        elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
        degraded=bool(skipped_by_breaker) or any_errored,
    )
