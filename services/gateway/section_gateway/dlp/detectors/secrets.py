"""Secret detectors for common cloud / SaaS / SCM credentials.

This is a curated, regex-only subset; for high-recall scans, operators can
wire in the full `detect-secrets` plugin set later. Patterns target known
prefixes (sk-, ghp_, AKIA…) and well-known structural shapes (private key
PEM headers, GCP service-account JSON).
"""
from __future__ import annotations

import math
import re

from ..types import Finding, make_finding

VERSION = "1"

# Each entry: canonical label -> (pattern, confidence). All secret-shape
# labels live under the `credential.*` category — see `dlp/display.py`
# for human metadata.
_PATTERNS: dict[str, tuple[re.Pattern[str], float]] = {
    "credential.aws_access_key": (
        re.compile(r"\b(?:AKIA|ASIA|AIDA|AROA)[A-Z0-9]{16}\b"),
        0.99,
    ),
    "credential.aws_secret_key": (
        # Heuristic: 40-char base64-ish after "aws_secret" keyword OR following
        # AKIA on the same line. We match the 40-char run that contains a mix
        # of upper/lower/digits, anchored to a common key context.
        re.compile(
            r"(?:aws_secret_access_key|aws_secret|secret_access_key)\s*[:=]\s*"
            r"['\"]?([A-Za-z0-9/+]{40})['\"]?"
        ),
        0.95,
    ),
    "credential.github_pat": (
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
        0.98,
    ),
    "credential.openai_api_key": (
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
        0.97,
    ),
    "credential.anthropic_api_key": (
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        0.99,
    ),
    "credential.slack_bot_token": (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        0.99,
    ),
    "credential.gcp_service_account": (
        # JSON shape — match the `"type": "service_account"` marker.
        re.compile(r'"type"\s*:\s*"service_account"'),
        0.95,
    ),
    "credential.azure_storage_key": (
        re.compile(r"DefaultEndpointsProtocol=https;AccountName=[A-Za-z0-9]+;AccountKey=[A-Za-z0-9+/=]{20,}"),
        0.99,
    ),
    "credential.private_key": (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        0.99,
    ),
    "credential.stripe_api_key": (
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b"),
        0.98,
    ),
}

# Generic high-entropy fallback (off by default in many policies — labelled
# `credential.generic_high_entropy`). We emit only when both length and entropy thresholds hit.
_GENERIC_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/_-]{32,}\b")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for c in s:
        counts[c] = counts.get(c, 0) + 1
    total = len(s)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _scan(text: str) -> list[Finding]:
    findings: list[Finding] = []

    for label, (pat, conf) in _PATTERNS.items():
        for m in pat.finditer(text):
            # If the pattern has a capture group, use it as the actual secret span;
            # otherwise the whole match.
            if m.groups():
                start, end = m.span(1)
                matched = m.group(1)
            else:
                start, end = m.span()
                matched = m.group(0)
            findings.append(
                make_finding(
                    label=label,
                    start=start,
                    end=end,
                    matched=matched,
                    confidence=conf,
                    detector="secrets",
                    detector_version=VERSION,
                )
            )

    # Generic high-entropy fallback. Suppress any span that overlaps a
    # higher-confidence specific finding.
    specific_spans = [(f.start, f.end) for f in findings]
    for m in _GENERIC_TOKEN_RE.finditer(text):
        s, e = m.span()
        tok = m.group(0)
        if any(not (e <= ss or s >= ee) for ss, ee in specific_spans):
            continue
        if _shannon_entropy(tok) < 3.5:
            continue
        findings.append(
            make_finding(
                label="credential.generic_high_entropy",
                start=s,
                end=e,
                matched=tok,
                confidence=0.6,
                detector="secrets",
                detector_version=VERSION,
                meta={"entropy": round(_shannon_entropy(tok), 3)},
            )
        )
    return findings


async def detect(text: str) -> list[Finding]:
    return _scan(text)
