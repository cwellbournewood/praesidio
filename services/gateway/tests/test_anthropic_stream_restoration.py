"""Anthropic SSE streaming — placeholder restoration across the full event grammar.

Anthropic's `/v1/messages` streaming API emits these event types:

  - ``message_start``        / ``message_delta``     / ``message_stop``
  - ``content_block_start``  / ``content_block_delta`` (text_delta | input_json_delta)
                              / ``content_block_stop``
  - ``ping``                 (heartbeat — must be passed through unchanged)
  - optional empty / comment lines (``: keepalive``)

The gateway wraps the upstream byte stream with :class:`RestoreStream`,
which substitutes placeholder tokens byte-wise across event boundaries
*and* across the JSON string boundary inside each ``data:`` payload. These
tests pin that behaviour for every Anthropic event variant we care about.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from section_gateway.anonymize.stream import RestoreStream
from section_gateway.anonymize.tokenizer import ReversalEntry, ReversalMap

EMAIL_PH = "<EMAIL_A2B3>"
EMAIL_ORIG = "alice@example.com"
PHONE_PH = "<PHONE_C4D5>"
PHONE_ORIG = "+15551234567"


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


# ---------------------------------------------------------------------------
# 1. text_delta restoration (the common case)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_delta_restoration() -> None:
    """A ``content_block_delta`` carrying ``text_delta`` JSON."""
    chunks = [
        b"event: message_start\ndata: {\"type\":\"message_start\"}\n\n",
        (
            b"event: content_block_delta\n"
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"sending mail to ' + EMAIL_PH.encode() + b' now"}}'
            b"\n\n"
        ),
        b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n",
    ]
    out = await _collect(RestoreStream(_feed(chunks), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out
    # Wrapping SSE framing preserved.
    assert "event: content_block_delta" in out
    assert "event: message_stop" in out


# ---------------------------------------------------------------------------
# 2. input_json_delta — tool args restoration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_input_json_delta_tool_arg_restoration() -> None:
    """Tool-use ``input_json_delta`` payloads carry placeholders inside JSON
    string values; restoration is byte-level so we still substitute correctly.
    """
    payload = (
        b'data: {"type":"content_block_delta","index":1,'
        b'"delta":{"type":"input_json_delta","partial_json":'
        b'"{\\"to\\":\\"' + EMAIL_PH.encode() + b'\\",\\"body\\":\\"hi\\"}"}}'
        b"\n\n"
    )
    chunks = [b"event: content_block_delta\n", payload]
    out = await _collect(RestoreStream(_feed(chunks), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out


# ---------------------------------------------------------------------------
# 3. Split inside the JSON string itself (the brittle case)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_split_inside_json_string() -> None:
    """The placeholder straddles two writes *inside* a JSON string."""
    full = (
        b'data: {"type":"content_block_delta","delta":'
        b'{"type":"text_delta","text":"contact ' + EMAIL_PH.encode() + b' urgently"}}'
        b"\n\n"
    )
    # Split right in the middle of `<EMAIL_A2B3>`.
    cut = full.index(EMAIL_PH.encode()) + 4  # mid-placeholder
    chunks = [full[:cut], full[cut:]]
    out = await _collect(RestoreStream(_feed(chunks), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out


# ---------------------------------------------------------------------------
# 4. Split across two distinct SSE events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_split_across_two_events() -> None:
    """The TCP boundary lands between two SSE events. The first event ends
    just before the start of a placeholder that lives in the second event.

    This is the common case where the upstream flushes after each event but
    the client receives them back-to-back with the boundary mid-stream.
    """
    ev1 = (
        b'event: content_block_delta\n'
        b'data: {"type":"content_block_delta","delta":'
        b'{"type":"text_delta","text":"first chunk no email here"}}\n\n'
    )
    ev2 = (
        b'event: content_block_delta\n'
        b'data: {"type":"content_block_delta","delta":'
        b'{"type":"text_delta","text":"second event has ' + EMAIL_PH.encode() + b' inside"}}\n\n'
    )
    out = await _collect(RestoreStream(_feed([ev1, ev2]), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out


# ---------------------------------------------------------------------------
# 5. Mixed text + tool_use stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_text_and_tool_use_stream() -> None:
    """A realistic stream: text block first, then a tool_use block. Each
    block contains a different placeholder; both must be restored.
    """
    chunks = [
        b"event: message_start\ndata: {\"type\":\"message_start\"}\n\n",
        b"event: content_block_start\ndata: {\"type\":\"content_block_start\",\"index\":0,"
        b"\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n",
        b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
        b'"delta":{"type":"text_delta","text":"I will call ' + PHONE_PH.encode() + b'"}}\n\n',
        b"event: content_block_stop\ndata: {\"type\":\"content_block_stop\",\"index\":0}\n\n",
        b"event: content_block_start\ndata: {\"type\":\"content_block_start\",\"index\":1,"
        b"\"content_block\":{\"type\":\"tool_use\",\"id\":\"toolu_1\",\"name\":\"send\",\"input\":{}}}\n\n",
        b'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,'
        b'"delta":{"type":"input_json_delta","partial_json":"{\\"to\\":\\"'
        + EMAIL_PH.encode() + b'\\"}"}}\n\n',
        b"event: content_block_stop\ndata: {\"type\":\"content_block_stop\",\"index\":1}\n\n",
        b"event: message_delta\ndata: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":5}}\n\n",
        b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n",
    ]
    rev = _reversal({EMAIL_PH: EMAIL_ORIG, PHONE_PH: PHONE_ORIG})
    out = await _collect(RestoreStream(_feed(chunks), rev))
    assert EMAIL_ORIG in out
    assert PHONE_ORIG in out
    assert EMAIL_PH not in out
    assert PHONE_PH not in out


# ---------------------------------------------------------------------------
# 6. ping / empty / comment events pass through unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping_and_empty_events_tolerated() -> None:
    """Heartbeat/keepalive events should not corrupt the substitution state."""
    chunks = [
        b": keepalive\n\n",  # SSE comment line
        b"event: ping\ndata: {\"type\":\"ping\"}\n\n",
        b"\n",  # truly empty SSE separator
        b"event: content_block_delta\ndata: {\"type\":\"content_block_delta\","
        b'"delta":{"type":"text_delta","text":"meet ' + EMAIL_PH.encode() + b' at noon"}}\n\n',
        b": keepalive\n\n",
    ]
    out = await _collect(RestoreStream(_feed(chunks), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out
    # Both keepalive markers preserved.
    assert out.count(": keepalive") == 2
    assert "event: ping" in out


# ---------------------------------------------------------------------------
# 7. Byte-per-chunk Anthropic stream (worst case)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_byte_per_chunk_anthropic_stream() -> None:
    """Even when the upstream forwards one byte at a time, restoration works."""
    full = (
        b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":'
        b'{"type":"text_delta","text":"' + EMAIL_PH.encode() + b'"}}\n\n'
    )
    chunks = [bytes([b]) for b in full]
    out = await _collect(RestoreStream(_feed(chunks), _reversal({EMAIL_PH: EMAIL_ORIG})))
    assert EMAIL_ORIG in out
    assert EMAIL_PH not in out
