"""Streaming restore tests — placeholders that cross chunk boundaries."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from section_gateway.anonymize.stream import RestoreStream
from section_gateway.anonymize.tokenizer import ReversalEntry, ReversalMap


def _make_reversal(pairs: dict[str, str]) -> ReversalMap:
    r = ReversalMap(request_id="r", tenant_id="t")
    for k, v in pairs.items():
        r.add(ReversalEntry(k, v, "pii.email", "tokenise", "request", 60))
    return r


async def _feed(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


async def _collect(stream: RestoreStream) -> bytes:
    out = bytearray()
    async for c in stream:
        out.extend(c)
    return bytes(out)


@pytest.mark.asyncio
async def test_split_placeholder_across_chunks():
    rev = _make_reversal({"<EMAIL_ABCD>": "alice@example.com"})
    # Split mid-placeholder.
    chunks = [b"data: hello <EMA", b"IL_ABCD> world\n\n"]
    stream = RestoreStream(_feed(chunks), rev)
    result = (await _collect(stream)).decode()
    assert "alice@example.com" in result
    assert "<EMA" not in result


@pytest.mark.asyncio
async def test_no_placeholder_passthrough():
    rev = _make_reversal({})
    chunks = [b"data: plain ", b"text only\n\n"]
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert out == b"data: plain text only\n\n"


@pytest.mark.asyncio
async def test_unknown_placeholder_left_intact():
    rev = _make_reversal({"<EMAIL_ABCD>": "alice@example.com"})
    chunks = [b"data: see <PERSON_ZZZZ> and <EMAIL_ABCD>\n\n"]
    out = await _collect(RestoreStream(_feed(chunks), rev))
    s = out.decode()
    assert "alice@example.com" in s
    assert "<PERSON_ZZZZ>" in s  # untouched
