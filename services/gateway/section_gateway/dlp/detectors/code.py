"""Heuristic source-code detection.

Fast, dependency-free. Emits `code.block` for fenced blocks and `code.dense`
for high symbol-density regions. Operators replace with `guesslang` ONNX if
real language classification is needed.
"""
from __future__ import annotations

import re

from ..types import Finding, make_finding

VERSION = "1"

_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+\-]*)\n(?P<body>.*?)```", re.DOTALL)
_SYMBOL_RE = re.compile(r"[\{\}\[\]\(\);=<>/\\\|:!&\*]")
_PROPRIETARY_MARKERS = re.compile(
    r"(?i)(internal[\s_-]?use[\s_-]?only|do[\s_-]?not[\s_-]?distribute|"
    r"proprietary[\s_-]?and[\s_-]?confidential|company[\s_-]?confidential|"
    r"acme[\s_-]?confidential)"
)


def _symbol_density(s: str) -> float:
    if not s:
        return 0.0
    return len(_SYMBOL_RE.findall(s)) / max(1, len(s))


def _scan(text: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _FENCE_RE.finditer(text):
        body = m.group("body")
        lang = m.group("lang") or "unknown"
        s, e = m.span()
        out.append(
            make_finding(
                label="code.block",
                start=s,
                end=e,
                matched=body,
                confidence=0.9,
                detector="code",
                detector_version=VERSION,
                meta={"language_hint": lang, "lines": body.count("\n") + 1},
            )
        )
    if _symbol_density(text) > 0.07 and len(text) > 80:
        out.append(
            make_finding(
                label="code.dense",
                start=0,
                end=len(text),
                matched=text[:64],
                confidence=0.55,
                detector="code",
                detector_version=VERSION,
                meta={"density": round(_symbol_density(text), 3)},
            )
        )
    for m in _PROPRIETARY_MARKERS.finditer(text):
        s, e = m.span()
        out.append(
            make_finding(
                label="code.proprietary_marker",
                start=s,
                end=e,
                matched=m.group(0),
                confidence=0.9,
                detector="code",
                detector_version=VERSION,
            )
        )
    return out


async def detect(text: str) -> list[Finding]:
    return _scan(text)
