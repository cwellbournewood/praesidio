"""Detector implementations. Each module exposes a ``detect(text)`` coroutine."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..types import Finding

DetectorFn = Callable[[str], Awaitable[list[Finding]]]
