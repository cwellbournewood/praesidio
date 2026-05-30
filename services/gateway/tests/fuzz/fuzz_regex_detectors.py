"""Atheris harness — fuzz every regex detector with arbitrary byte input.

We feed UTF-8-decoded input (errors='ignore') to each registered detector
and assert only that they do not raise. Any uncaught exception is a fuzz
finding the runner will report.

Run with::

    pip install -e '.[fuzz]'
    python -m atheris tests/fuzz/fuzz_regex_detectors.py

Or with a corpus directory::

    python -m atheris tests/fuzz/fuzz_regex_detectors.py corpus/
"""
from __future__ import annotations

import asyncio
import sys

from section_gateway.dlp.detectors import regex as det_regex
from section_gateway.dlp.detectors import secrets as det_secrets

_DETECTORS = [det_regex.detect, det_secrets.detect]


def TestOneInput(data: bytes) -> None:
    """Atheris entrypoint. Must accept ``bytes`` and return ``None``."""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return
    for fn in _DETECTORS:
        try:
            asyncio.run(fn(text))
        except Exception:
            # Re-raise so atheris records a fuzz finding.
            raise


if __name__ == "__main__":  # pragma: no cover - external runner
    import atheris

    atheris.Setup(sys.argv, TestOneInput, enable_python_coverage=True)
    atheris.Fuzz()
