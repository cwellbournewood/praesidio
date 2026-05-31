"""Fast lexical detectors. Pure-regex; sub-millisecond on typical prompts.

All matched substrings are hashed (sha256) before they leave the function —
the Finding never carries raw text.
"""
from __future__ import annotations

import re

from ..types import Finding, make_finding

VERSION = "1"

# ---------------------------------------------------------------------------
# Pre-compiled patterns. Names follow the policy label convention `regex.<X>`.
# ---------------------------------------------------------------------------

# The regex detector emits canonical `<category>.<thing>` labels — the
# same labels Presidio uses for overlapping concepts (e.g. emails). That
# way the policy engine's overlap-resolution deduplicates them naturally
# rather than producing two findings with two different labels for one
# span. The `detector` field on each Finding records which engine fired,
# so observability stays intact.
#
# `_PATTERNS` keys are internal — `_scan` translates them to the wire
# label via `_INTERNAL_TO_LABEL`. We keep an internal name so the
# CC candidate pre-Luhn phase can be expressed without a "publish-able"
# label leaking out.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "phone": re.compile(
        r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}(?!\d)"
    ),
    # IBAN tolerates whitespace and hyphens between groups so that
    # `DE89 3704 0044 0532 0130 00` and `DE89-3704-...-00` both match.
    # We strip separators before length-checking inside `_scan`.
    "iban": re.compile(
        r"\b[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]){10,34}\b"
    ),
    "ipv4": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
    ),
    "ipv6": re.compile(
        r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b"
    ),
    "jwt": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    "ssn": re.compile(
        r"(?<!\d)(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)"
    ),
    "mac": re.compile(
        r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
    ),
    # Credit-card-shaped run of 13-19 digits with optional spaces/dashes.
    # Promoted to `financial.credit_card` only after Luhn passes.
    "cc_candidate": re.compile(
        r"(?<!\d)(?:\d[ -]?){13,19}\b"
    ),
}

# Internal pattern name -> canonical wire label.
_INTERNAL_TO_LABEL: dict[str, str] = {
    "email": "pii.email",
    "phone": "pii.phone",
    "iban": "financial.iban",
    "ipv4": "network.ipv4",
    "ipv6": "network.ipv6",
    "jwt": "credential.jwt",
    "uuid": "infra.uuid",
    "ssn": "pii.us_ssn",
    "mac": "network.mac_address",
    # cc_candidate is promoted in `_scan` only after Luhn validation.
}

_HIGH = 0.95
_MED = 0.7
_LOW = 0.55


def _luhn(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        if not ch.isdigit():
            continue
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s != 0 and s % 10 == 0


def _confidence_for(internal: str) -> float:
    if internal in {"email", "jwt", "uuid", "ipv4", "mac"}:
        return _HIGH
    if internal in {"iban", "ssn", "ipv6"}:
        return _MED
    return _LOW


def _scan(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen_spans: set[tuple[int, int, str]] = set()
    for internal, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            s, e = m.span()
            matched = m.group(0)

            if internal == "cc_candidate":
                digits = re.sub(r"\D", "", matched)
                if not (13 <= len(digits) <= 19) or not _luhn(digits):
                    continue
                emit_label = "financial.credit_card"
                conf = _HIGH
            elif internal == "iban":
                # Strip separators then validate length 15–34 (IBAN spec).
                core = re.sub(r"[ -]", "", matched)
                if not (15 <= len(core) <= 34):
                    continue
                emit_label = _INTERNAL_TO_LABEL[internal]
                conf = _confidence_for(internal)
            elif internal == "phone":
                digits = re.sub(r"\D", "", matched)
                # Phone: 7–15 digits AND not Luhn-valid (those are CCs).
                if not (7 <= len(digits) <= 15):
                    continue
                if 13 <= len(digits) <= 19 and _luhn(digits):
                    continue
                emit_label = _INTERNAL_TO_LABEL[internal]
                conf = _confidence_for(internal)
            else:
                emit_label = _INTERNAL_TO_LABEL[internal]
                conf = _confidence_for(internal)

            key = (s, e, emit_label)
            if key in seen_spans:
                continue
            seen_spans.add(key)
            findings.append(
                make_finding(
                    label=emit_label,
                    start=s,
                    end=e,
                    matched=matched,
                    confidence=conf,
                    detector="regex",
                    detector_version=VERSION,
                )
            )
    return findings


async def detect(text: str) -> list[Finding]:
    return _scan(text)
