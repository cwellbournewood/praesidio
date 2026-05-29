"""Presidio Analyzer wrapper.

Lazy-loads the analyzer on first call so unit tests that don't exercise
Presidio (and don't have spaCy models installed) stay fast and importable.
"""
from __future__ import annotations

import logging

from ..types import Finding, make_finding

VERSION = "1"

_log = logging.getLogger(__name__)
_analyzer = None
_unavailable_reason: str | None = None

# Map Presidio entity names to our canonical `<category>.<thing>` label
# space. The wire labels are stable: policies, audit history, SIEM rules
# and the UI all key off them. Human-readable display metadata lives in
# `praesidio_gateway.dlp.display`.
_ENTITY_TO_LABEL = {
    "PERSON": "pii.person",
    "LOCATION": "pii.location",
    "ORGANIZATION": "pii.organization",
    "EMAIL_ADDRESS": "pii.email",
    "PHONE_NUMBER": "pii.phone",
    "CREDIT_CARD": "financial.credit_card",
    "IBAN_CODE": "financial.iban",
    "IP_ADDRESS": "network.ip_address",
    "NRP": "pii.nationality",
    "US_SSN": "pii.us_ssn",
    "US_DRIVER_LICENSE": "pii.us_drivers_license",
    "MEDICAL_LICENSE": "healthcare.medical_license",
    "DATE_TIME": "pii.date",
    "URL": "pii.url",
}


def _get_analyzer():  # pragma: no cover - heavy import
    global _analyzer, _unavailable_reason
    if _analyzer is not None or _unavailable_reason is not None:
        return _analyzer
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Pin to en_core_web_sm — the model baked into the container image.
        # Without this, presidio defaults to en_core_web_lg and tries to
        # pip-download it at runtime (which SystemExits the worker).
        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        ).create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        _log.info("Presidio analyzer initialised")
    except (Exception, SystemExit) as exc:
        _unavailable_reason = f"presidio init failed: {exc}"
        _log.warning(_unavailable_reason)
    return _analyzer


async def detect(text: str) -> list[Finding]:  # pragma: no cover - heavy
    analyzer = _get_analyzer()
    if analyzer is None:
        return []
    try:
        results = analyzer.analyze(text=text, language="en")
    except Exception:
        _log.exception("presidio analyze failed")
        return []

    findings: list[Finding] = []
    for r in results:
        # Unknown Presidio entity types are wrapped in `pii.*` as a safe
        # default — most Presidio recognisers target PII. Operators add new
        # entries to `_ENTITY_TO_LABEL` and `dlp/display.py` as needed.
        label = _ENTITY_TO_LABEL.get(r.entity_type, f"pii.{r.entity_type.lower()}")
        findings.append(
            make_finding(
                label=label,
                start=r.start,
                end=r.end,
                matched=text[r.start : r.end],
                confidence=float(r.score),
                detector="presidio",
                detector_version=VERSION,
                meta={"entity_type": r.entity_type},
            )
        )
    return findings
