"""Curated prompt-injection signature detector.

Detects common attack patterns in inbound prompts. Peeks at base64-decoded
sub-strings (one level) to catch trivial obfuscation. This is a defensive
control — it raises a finding so the policy engine can decide what to do.
"""
from __future__ import annotations

import base64
import re

from ..types import Finding, make_finding

VERSION = "1"

_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("behavior.injection_ignore_previous",
     re.compile(r"(?i)\b(ignore|disregard|forget)\b[^.]{0,30}\b(previous|above|prior|earlier|system)\b[^.]{0,30}\b(instruction|prompt|rule|message|directive)s?\b"),
     0.85),
    ("behavior.injection_role_swap",
     re.compile(r"(?i)\byou are now\b[^.]{0,40}"),
     0.7),
    ("behavior.injection_jailbreak",
     re.compile(r"(?i)\bact as\b\s+(an?\s+)?(?:DAN|jailbreak|unrestricted|developer mode|admin)"),
     0.9),
    ("behavior.injection_system_override",
     re.compile(r"(?i)\b(system|admin|root)\b[^.]{0,15}(override|bypass|disable|escalate)\b"),
     0.85),
    ("behavior.injection_prompt_exfil",
     re.compile(r"(?i)(print|reveal|show|leak|dump)\s+(?:your|the)\s+(?:system|initial|hidden)\s+(?:prompt|instructions?)"),
     0.9),
    ("behavior.injection_base64_tool_abuse",
     re.compile(r"(?i)\bbase64\b[^.]{0,30}(decode|execute|run)"),
     0.6),
]

_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")


def _peek_base64(text: str) -> str:
    """Decode every long base64 run we find and concatenate the printable bits."""
    out: list[str] = []
    for m in _BASE64_RE.finditer(text):
        try:
            raw = base64.b64decode(m.group(0) + "==", validate=False)
        except Exception:
            continue
        try:
            s = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        printable = "".join(c for c in s if c.isprintable())
        if len(printable) >= 8:
            out.append(printable)
    return "\n".join(out)


def _scan_text(text: str, *, base_offset: int, source: str) -> list[Finding]:
    out: list[Finding] = []
    for label, pat, conf in _PATTERNS:
        for m in pat.finditer(text):
            s, e = m.span()
            out.append(
                make_finding(
                    label=label,
                    start=base_offset + s,
                    end=base_offset + e,
                    matched=m.group(0),
                    confidence=conf,
                    detector="prompt_injection",
                    detector_version=VERSION,
                    meta={"source": source},
                )
            )
    return out


async def detect(text: str) -> list[Finding]:
    findings = _scan_text(text, base_offset=0, source="raw")
    decoded = _peek_base64(text)
    if decoded:
        findings.extend(_scan_text(decoded, base_offset=0, source="base64_peek"))
    return findings
