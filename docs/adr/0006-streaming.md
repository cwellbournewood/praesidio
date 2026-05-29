# ADR-0006 · Streaming and de-anonymisation

Date: 2026-05-27 · Status: Accepted

## Context

LLM responses stream. We must restore placeholders inside a streaming
response without (a) breaking the SSE protocol, (b) corrupting placeholders
that span chunk boundaries, or (c) adding meaningful latency.

## Decision

A `RestoreStream` state machine wraps the upstream SSE iterator:

1. Buffers a small tail (default 64 bytes — longer than any placeholder
   token like `<EMAIL_xxxx>`).
2. On each chunk: append to tail; greedy-match placeholders; emit
   resolved prefix; keep tail as buffer for the next chunk.
3. On stream end, flush the tail (with one final placeholder pass).
4. Output DLP runs in a sidecar coroutine over the *resolved* stream
   (post-restoration) — if a leak is detected, the upstream is cancelled
   and a final SSE error event is emitted per protocol convention.

## Consequences

- ➕ User TTFB unaffected (single-chunk buffer, ~bytes-of-buffer worth of
  added latency).
- ➕ Placeholders never break across chunk boundaries.
- ➖ Tail buffer length is bounded; very long placeholders (which we don't
  emit by design) would be missed. Documented as a guarantee of the
  placeholder grammar.
