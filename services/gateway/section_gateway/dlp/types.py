"""Shared types for the DLP package. Re-exports the Finding model."""
from __future__ import annotations

import hashlib

import ulid

from ..policy.models import Finding


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_finding(
    *,
    label: str,
    start: int,
    end: int,
    matched: str,
    confidence: float,
    detector: str,
    detector_version: str = "1",
    meta: dict | None = None,
) -> Finding:
    return Finding(
        id=str(ulid.new()),
        label=label,
        start=start,
        end=end,
        text_hash=sha256_hex(matched),
        confidence=confidence,
        detector=detector,
        detector_version=detector_version,
        meta=meta or {},
    )


__all__ = ["Finding", "make_finding", "sha256_hex"]
