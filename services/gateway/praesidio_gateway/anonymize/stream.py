"""Restore-on-the-fly for SSE streams.

The tricky bit: a placeholder like ``<EMAIL_AB12>`` can span SSE chunk
boundaries — including being split across an arbitrary number (N) of
chunks. We hold back the trailing ``_TAIL`` bytes of the rolling buffer
and only emit the prefix we are certain does not contain a half-token.

Invariants
----------
- ``_TAIL`` MUST be at least ``max_placeholder_length - 1`` so the
  half-token regex can always see the leading ``<`` in any context. A
  complete placeholder for the current grammar fits in well under 32
  bytes (``<LABEL_XXXX>``); 64 gives ample headroom for nested or
  forward-extended forms.
- For very small chunks (e.g. 4 bytes at a time) the buffer is shorter
  than ``_TAIL`` and we hold the entire buffer until the next chunk.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator

from .tokenizer import ReversalMap

# Rolling-buffer tail size. MUST be >= max placeholder length - 1 so a
# split placeholder is always fully contained in the held-back tail.
_TAIL = 64
_PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4})>")
# Half-token: a `<` followed by 0+ placeholder-body chars at the end of buf.
# Anchored to end of buffer.
_HALF_TOKEN_RE = re.compile(r"<[A-Z0-9_]*$")
# Any `<` that COULD begin a placeholder. Used to back the cut up past any
# such `<` that lies within the held-back tail region, so that a complete
# placeholder straddling the would-be cut isn't bisected.
_OPEN_BRACKET_RE = re.compile(r"<")


def _substitute(buf: str, reversal: ReversalMap) -> str:
    def _sub(m: re.Match[str]) -> str:
        return reversal.by_placeholder.get(m.group(0), m.group(0))

    return _PLACEHOLDER_RE.sub(_sub, buf)


class RestoreStream:
    """Async iterator that consumes an upstream byte stream and yields the
    placeholder-restored byte stream chunk-by-chunk."""

    def __init__(
        self,
        upstream: AsyncIterator[bytes],
        reversal: ReversalMap,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self._upstream = upstream
        self._rev = reversal
        self._buffer = ""
        self._encoding = encoding

    def _emit_safe_prefix(self, force_all: bool = False) -> str:
        """Emit as much of the buffer as is safe (no half-token at the tail)."""
        if force_all:
            out, self._buffer = self._buffer, ""
            return _substitute(out, self._rev)

        buf_len = len(self._buffer)
        # Pick the safest possible cut. Default = keep last _TAIL bytes.
        cut = max(0, buf_len - _TAIL)
        # Two cases force the cut earlier:
        #   1. A half-token (`<[A-Z0-9_]*` anchored at end of buffer): cut
        #      right at that `<` so the next chunk can complete it.
        #   2. A bare `<` anywhere in the LAST _TAIL bytes that hasn't yet
        #      been closed by a matching `>` later in the buffer: cut at
        #      that `<` so a placeholder that straddles the would-be cut
        #      isn't bisected during emit. (This also handles the case
        #      where `<` is BEFORE the default cut but a complete `>` lies
        #      AFTER it — re.findall in the held-back zone.)
        m = _HALF_TOKEN_RE.search(self._buffer)
        if m is not None and (buf_len - m.start()) <= _TAIL:
            cut = min(cut, m.start())
        # Scan a slightly-larger zone for any `<` that could begin a
        # placeholder straddling the cut. Any `<` at position `pos` where
        # ``cut <= pos + max_placeholder_len`` could have its closing `>`
        # land at or after `cut`, which would bisect the placeholder. Back
        # the cut up to before any such `<` so the full token lives in the
        # held-back tail until the next chunk arrives.
        scan_from = max(0, cut - _TAIL)
        for lt in _OPEN_BRACKET_RE.finditer(self._buffer, scan_from):
            pos = lt.start()
            if pos >= cut:
                # `<` already in the held-back tail. If unclosed, must keep.
                rest = self._buffer[pos:]
                if ">" not in rest:
                    cut = min(cut, pos)
                    break
                continue
            # `<` is in the prefix zone (pos < cut). Check whether its
            # potential closing `>` could land at or after cut: i.e. if the
            # nearest `>` after `pos` is at index >= cut.
            gt = self._buffer.find(">", pos, pos + _TAIL + 1)
            if gt == -1 or gt >= cut:
                # Either no `>` in placeholder window (unclosed half-token),
                # or `>` lies in the tail (placeholder straddles the cut).
                # Either way, back the cut up.
                cut = pos
                break
            # Otherwise the whole `<...>` lives entirely in the prefix — safe.
        # Final clamp.
        if cut > buf_len:
            cut = buf_len

        if cut <= 0:
            return ""
        prefix, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return _substitute(prefix, self._rev)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._upstream:
            if not chunk:
                continue
            self._buffer += chunk.decode(self._encoding, errors="replace")
            out = self._emit_safe_prefix()
            if out:
                yield out.encode(self._encoding)
        flush = self._emit_safe_prefix(force_all=True)
        if flush:
            yield flush.encode(self._encoding)


async def restore_stream(
    upstream: AsyncIterator[bytes], reversal: ReversalMap
) -> AsyncIterator[bytes]:
    """Convenience wrapper around RestoreStream."""
    async for out in RestoreStream(upstream, reversal):
        yield out
