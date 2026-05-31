"""Irreversible masking. No vault entry."""
from __future__ import annotations


def redact_label(label: str, replacement: str | None) -> str:
    if replacement:
        return replacement
    short = label.split(".", 1)[-1].upper()
    return f"[REDACTED_{short}]"


def redact_bullets(length: int) -> str:
    return "•" * length
