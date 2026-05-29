"""Streaming RestoreStream — placeholder split across arbitrary chunk boundaries (Task 2.2).

The rolling-tail buffer must keep a half-token whole no matter where the
chunk boundary falls, including the very last byte of a placeholder.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from praesidio_gateway.anonymize.stream import RestoreStream
from praesidio_gateway.anonymize.tokenizer import ReversalEntry, ReversalMap


def _reversal(pairs: dict[str, str]) -> ReversalMap:
    r = ReversalMap(request_id="r", tenant_id="t")
    for k, v in pairs.items():
        r.add(ReversalEntry(k, v, "pii.email", "tokenise", "request", 60))
    return r


async def _feed(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


async def _collect(stream: RestoreStream) -> str:
    out = bytearray()
    async for c in stream:
        out.extend(c)
    return out.decode()


PLACEHOLDER = "<EMAIL_A2B3>"
ORIGINAL = "alice@example.com"


@pytest.mark.asyncio
async def test_split_between_open_bracket_and_label():
    """Boundary right after ``<``."""
    text = f"hello {PLACEHOLDER} world"
    # ...hello <|EMAIL_A1B2> world
    idx = text.index(PLACEHOLDER) + 1
    chunks = [text[:idx].encode(), text[idx:].encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out
    assert PLACEHOLDER not in out


@pytest.mark.asyncio
async def test_split_inside_label_specific():
    """Reproduces the exact example in the task: ``<EMAIL_a1`` then ``b2>``."""
    text = f"hello {PLACEHOLDER} world"
    # split inside the suffix
    idx = text.index(PLACEHOLDER) + len("<EMAIL_A2")
    chunks = [text[:idx].encode(), text[idx:].encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out


@pytest.mark.asyncio
async def test_split_right_before_closing_bracket():
    text = f"hello {PLACEHOLDER} world"
    idx = text.index(PLACEHOLDER) + len(PLACEHOLDER) - 1  # before final `>`
    chunks = [text[:idx].encode(), text[idx:].encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out


@pytest.mark.asyncio
async def test_split_across_three_chunks():
    """Placeholder split across THREE chunks, byte-by-byte chunks elsewhere."""
    text = f"data: x {PLACEHOLDER} y"
    a = text.index(PLACEHOLDER) + 2  # mid-prefix
    b = text.index(PLACEHOLDER) + len(PLACEHOLDER) - 2
    chunks = [text[:a].encode(), text[a:b].encode(), text[b:].encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out
    assert PLACEHOLDER not in out


@pytest.mark.asyncio
async def test_split_byte_per_chunk():
    """Worst case — one byte per chunk. Placeholder must still resolve."""
    text = f"q {PLACEHOLDER} r"
    chunks = [bytes([b]) for b in text.encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out
    assert PLACEHOLDER not in out


@pytest.mark.asyncio
async def test_multiple_placeholders_split():
    """Two placeholders, each split across the chunk boundary."""
    # Placeholder suffix grammar is base32 (A-Z + 2-7).
    p2 = "<EMAIL_C3D5>"
    o2 = "bob@example.org"
    text = f"a {PLACEHOLDER} b {p2} c"
    # Split right inside the first one
    idx = text.index(PLACEHOLDER) + 3
    chunks = [text[:idx].encode(), text[idx:].encode()]
    rev = _reversal({PLACEHOLDER: ORIGINAL, p2: o2})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert ORIGINAL in out and o2 in out
    assert "<EMAIL_" not in out
