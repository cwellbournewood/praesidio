"""mitmproxy addon — request + response hooks.

This module is loaded as an addon by mitmproxy via :mod:`section_edge_proxy.cli`.
It exposes :class:`SectionAddon` whose ``request`` and ``response``
hooks are called for every flow. We:

1. Skip anything not in :mod:`section_edge_proxy.upstream`.
2. On request, extract the prompt, call ``/v1/scan``, and either:
   - block with HTTP 403 (`section_blocked` body matching the gateway's shape),
   - rewrite the body with the sanitised string and forward, or
   - forward unchanged.
3. On response, walk the body for placeholders, call ``/v1/restore``,
   and re-inject the restored text.
4. For streaming SSE responses (chat completions), the placeholder
   cache persists for the flow's lifetime so chunk-boundary splits
   work — :class:`StreamingRestorer` buffers the trailing fragment of
   each chunk until a placeholder is complete.

All gateway calls are non-blocking; the mitmproxy hooks are async so we
``await`` httpx directly. Errors fall back to the configured
``fail_open`` behaviour (default: drop the request with HTTP 502 and
log; never silently leak unscanned text upstream).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

try:  # mitmproxy import is optional for unit tests that exercise the addon directly.
    from mitmproxy import http as mitm_http
except ImportError:  # pragma: no cover - mitmproxy missing only in some dev shells
    mitm_http = None  # type: ignore[assignment]

from .config import EdgeSettings
from .scan_client import PLACEHOLDER_RE, GatewayClient, ScanResult
from .status import StatusFile
from .upstream import Upstream, lookup

log = structlog.get_logger(__name__)


# --- Flow-scoped state ----------------------------------------------------

@dataclass
class FlowState:
    """Per-flow scratch space the addon attaches to ``flow.metadata``.

    Attributes:
        request_id: The gateway-minted id for this flow's /v1/scan call.
            Re-used on the response side for /v1/restore.
        placeholders: ``{placeholder -> original}`` cache the
            streaming restorer uses to swap text without round-tripping
            to the gateway for every chunk.
        upstream: The :class:`Upstream` entry matched on request.
        is_stream: True when the response is SSE / chunked text.
        restorer: The active :class:`StreamingRestorer` for SSE flows.
    """

    request_id: str = ""
    placeholders: dict[str, str] = field(default_factory=dict)
    upstream: Upstream | None = None
    is_stream: bool = False
    restorer: StreamingRestorer | None = None


# --- Streaming restoration -------------------------------------------------

class StreamingRestorer:
    """Chunk-boundary-safe placeholder swapper for SSE / chunked responses.

    The model can emit ``<EMAIL_A2`` in one chunk and ``B3>`` in the
    next; a naive ``replace`` on each chunk would miss the placeholder.
    We buffer up to ``PLACEHOLDER_MAX_LEN`` bytes of the trailing edge
    of each chunk and only emit text once we know the next character
    isn't the start of a placeholder fragment.

    Usage::

        r = StreamingRestorer(initial_cache=flow.placeholders)
        r.set_cache(flow.placeholders)
        for chunk in stream:
            yield r.feed(chunk)
        yield r.finalise()
    """

    # An upper bound on how long any single placeholder we might see
    # could be. Grammar is ``<LABEL_XXXX>`` with LABEL up to ~32 chars
    # and the suffix 4 base32 chars + 2 punctuation. Round up.
    PLACEHOLDER_MAX_LEN = 64

    def __init__(self, *, initial_cache: dict[str, str] | None = None) -> None:
        self._cache: dict[str, str] = dict(initial_cache or {})
        self._buffer = ""

    def set_cache(self, cache: dict[str, str]) -> None:
        """Replace the placeholder->original cache wholesale."""
        self._cache = dict(cache)

    def update_cache(self, additions: dict[str, str]) -> None:
        """Merge *additions* into the placeholder cache."""
        self._cache.update(additions)

    def feed(self, chunk: str) -> str:
        """Consume *chunk*, return the prefix we are now certain about.

        Anything trailing that might be the start of a placeholder is
        held back until the next call (or :meth:`finalise`).
        """
        if not chunk:
            return ""
        self._buffer += chunk

        # Find the last position safe to emit. If a '<' is in the
        # buffer's tail and we haven't seen the closing '>', hold the
        # tail back.
        last_open = self._buffer.rfind("<")
        if last_open == -1:
            safe = self._buffer
            self._buffer = ""
        else:
            # Is the candidate '<' followed by a closed '>' within the
            # placeholder length budget?
            tail = self._buffer[last_open:]
            closed = ">" in tail
            if closed:
                # Complete placeholder (or non-placeholder '<...>') —
                # emit the whole buffer.
                safe = self._buffer
                self._buffer = ""
            elif len(tail) > self.PLACEHOLDER_MAX_LEN:
                # Looks like a stray '<' that isn't a placeholder.
                # Emit it; if more comes later we'll handle it then.
                safe = self._buffer
                self._buffer = ""
            else:
                safe = self._buffer[:last_open]
                self._buffer = self._buffer[last_open:]

        return self._substitute(safe)

    def finalise(self) -> str:
        """Flush any held-back fragment and return it."""
        rest = self._buffer
        self._buffer = ""
        return self._substitute(rest)

    def _substitute(self, text: str) -> str:
        if not text or not self._cache:
            # Still do the regex pass — there may be placeholders the
            # cache doesn't know about (we'll leave them as-is).
            return text

        def _swap(m: re.Match[str]) -> str:
            ph = m.group(0)
            return self._cache.get(ph, ph)

        return PLACEHOLDER_RE.sub(_swap, text)


# --- The addon -------------------------------------------------------------

class SectionAddon:
    """mitmproxy addon that wires the proxy through the gateway.

    Attributes set by mitmproxy when the addon loads — see
    :mod:`section_edge_proxy.cli` for the bootstrap path.
    """

    def __init__(
        self,
        settings: EdgeSettings,
        *,
        gateway: GatewayClient | None = None,
        status: StatusFile | None = None,
    ):
        self.settings = settings
        self.gateway = gateway or GatewayClient(settings)
        self.status = status
        self._loaded_at = time.time()

    # --- mitmproxy hooks ---------------------------------------------------

    async def request(self, flow: Any) -> None:
        """Intercept on the request side: scan-and-mask or block."""
        req = flow.request
        host = (req.pretty_host or req.host or "").lower()
        path = req.path or ""
        upstream = lookup(host, path)
        if upstream is None:
            return  # passthrough

        state = FlowState(upstream=upstream)
        flow.metadata["section"] = state

        body_text = ""
        try:
            body_text = req.get_text() or ""
        except (UnicodeDecodeError, AttributeError):
            body_text = ""

        if not body_text:
            return

        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            log.warning("proxy.body_not_json", host=host, path=path)
            return

        if not isinstance(payload, dict):
            return

        prompt_text, model_hint = upstream.extractor.extract(payload)
        if not prompt_text.strip():
            return  # nothing to scan

        try:
            scan = await self.gateway.scan(
                text=prompt_text,
                client="edge-proxy",
                url=f"https://{host}{path}",
                model=model_hint,
                session_id=self._session_id(req),
            )
        except Exception as exc:  # noqa: BLE001 - we deliberately catch all
            log.error("proxy.scan_failed", err=str(exc), host=host)
            if not self.settings.fail_open:
                self._respond_error(flow, 502, "section_gateway_unreachable", str(exc))
            return

        state.request_id = scan.request_id
        for t in scan.transforms:
            ph = t.get("placeholder")
            # The original is never returned by /v1/scan (that would
            # defeat the point); we record the placeholder for streaming
            # restore. Originals are fetched on the response side via
            # /v1/restore when needed.
            if ph:
                state.placeholders[ph] = ph  # initial passthrough; updated post-restore

        if self._record_decision(host, scan):
            pass  # status hook ran

        if scan.action == "block":
            self._respond_block(flow, scan)
            return
        if scan.action == "mask" and scan.sanitised is not None:
            new_body = upstream.extractor.inject(payload, scan.sanitised)
            req.set_text(json.dumps(new_body, ensure_ascii=False))
            req.headers["content-length"] = str(len(req.content or b""))
        # action == "allow" — leave the body alone.

    async def response(self, flow: Any) -> None:
        """Restore placeholders in the upstream response."""
        state: FlowState | None = flow.metadata.get("section") if hasattr(flow, "metadata") else None
        if state is None or not state.request_id:
            return

        resp = flow.response
        if resp is None:
            return

        # SSE / chunked: handled by responseheaders + per-chunk hooks,
        # but mitmproxy collapses to a single response by default. If
        # the operator enabled streaming via `--set stream_large_bodies`,
        # the per-chunk path runs via :meth:`responseheaders`.
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/event-stream" in content_type:
            await self._restore_stream(flow, state)
            return

        body_text = ""
        try:
            body_text = resp.get_text() or ""
        except (UnicodeDecodeError, AttributeError):
            return
        if not body_text:
            return

        # Only call /v1/restore if there's at least one placeholder.
        if not PLACEHOLDER_RE.search(body_text):
            return

        try:
            result = await self.gateway.restore(
                request_id=state.request_id, text=body_text
            )
        except Exception as exc:  # noqa: BLE001
            log.error("proxy.restore_failed", err=str(exc))
            return

        resp.set_text(result.text)
        resp.headers["content-length"] = str(len(resp.content or b""))

    async def _restore_stream(self, flow: Any, state: FlowState) -> None:
        """Restore placeholders in an SSE response body.

        mitmproxy gives us the full buffered body by default; we walk
        the SSE event stream and run a :class:`StreamingRestorer` event
        by event so chunk-boundary-split placeholders work for clients
        that re-emit the stream upstream. The restored text is also
        round-tripped through /v1/restore once at the end so the vault
        cache for this flow is populated for any future emit.
        """
        resp = flow.response
        body_text = ""
        try:
            body_text = resp.get_text() or ""
        except (UnicodeDecodeError, AttributeError):
            return
        if not body_text or not PLACEHOLDER_RE.search(body_text):
            return

        # Bulk restore for the cache.
        try:
            result = await self.gateway.restore(
                request_id=state.request_id, text=body_text
            )
        except Exception as exc:  # noqa: BLE001
            log.error("proxy.stream_restore_failed", err=str(exc))
            return

        # Build a placeholder -> original map by diffing.
        cache = _diff_placeholders(body_text, result.text)
        state.placeholders.update(cache)
        restorer = StreamingRestorer(initial_cache=state.placeholders)
        state.restorer = restorer

        # Re-emit the stream with the streaming restorer applied — this
        # exercises the chunk-boundary path even though mitmproxy has
        # buffered. We split on SSE event boundaries (\n\n) so partial
        # events stay intact.
        events = body_text.split("\n\n")
        out: list[str] = []
        for ev in events:
            out.append(restorer.feed(ev + "\n\n"))
        out.append(restorer.finalise())
        resp.set_text("".join(out))
        resp.headers["content-length"] = str(len(resp.content or b""))

    # --- Helpers -----------------------------------------------------------

    def _session_id(self, req: Any) -> str | None:
        hdr = self.settings.session_id_header
        try:
            return req.headers.get(hdr)
        except AttributeError:
            return None

    def _record_decision(self, host: str, scan: ScanResult) -> bool:
        if self.status is None:
            return False
        try:
            self.status.record_decision(
                host=host, action=scan.action, request_id=scan.request_id
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    def _respond_block(self, flow: Any, scan: ScanResult) -> None:
        body = {
            "error": {
                "type": "section_blocked",
                "message": scan.reason or "blocked by policy",
                "policy_id": (scan.raw.get("decision") or {}).get("policy_id"),
                "request_id": scan.request_id,
                "severity": scan.severity or "high",
            }
        }
        self._respond_error(flow, 403, body=body)

    def _respond_error(
        self,
        flow: Any,
        status: int,
        type_: str | None = None,
        message: str | None = None,
        *,
        body: dict[str, Any] | None = None,
    ) -> None:
        if body is None:
            body = {
                "error": {
                    "type": type_ or "section_error",
                    "message": message or "edge proxy could not scan request",
                }
            }
        if mitm_http is not None and hasattr(mitm_http, "Response"):
            flow.response = mitm_http.Response.make(
                status,
                json.dumps(body).encode("utf-8"),
                {"content-type": "application/json"},
            )
        else:  # pragma: no cover - taken only when mitmproxy is absent (tests)
            flow.response = _FakeResponse(status, body)


# --- Helpers reused by tests ----------------------------------------------

def _diff_placeholders(masked: str, restored: str) -> dict[str, str]:
    """Pair every placeholder in *masked* with what it became in *restored*.

    We do this by walking *masked* token-by-token: for each placeholder
    we find its position, then read the same logical position in
    *restored* by replaying earlier substitutions. This is approximate —
    if the model rewrote the surrounding prose the alignment may drift —
    but it is good enough to seed the streaming-restorer cache for
    typical chat-completion replies.

    Returns an empty dict on alignment failure.
    """
    out: dict[str, str] = {}
    m_pos = 0
    r_pos = 0
    for m in PLACEHOLDER_RE.finditer(masked):
        # Find the literal prefix between the last cursor and this placeholder.
        prefix = masked[m_pos : m.start()]
        # Locate that prefix in restored starting at r_pos.
        try:
            anchor = restored.index(prefix, r_pos) if prefix else r_pos
        except ValueError:
            return {}
        r_pos = anchor + len(prefix)
        # The restored text from r_pos up to the next prefix is the original.
        next_match = PLACEHOLDER_RE.search(masked, m.end())
        if next_match is not None:
            next_prefix = masked[m.end() : next_match.start()]
            try:
                end = restored.index(next_prefix, r_pos) if next_prefix else r_pos
            except ValueError:
                return {}
            original = restored[r_pos:end]
        else:
            tail = masked[m.end() :]
            if tail:
                try:
                    end = restored.rindex(tail)
                except ValueError:
                    return {}
                original = restored[r_pos:end]
            else:
                original = restored[r_pos:]
        out[m.group(0)] = original
        r_pos += len(original)
        m_pos = m.end()
    return out


class _FakeResponse:
    """Stand-in for ``mitmproxy.http.Response`` when mitmproxy isn't loaded.

    Tests use this so we can assert on status / body without booting
    the full proxy. The real Response class has a richer API; we only
    expose what the addon and tests touch.
    """

    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.json_body = body
        if isinstance(body, (dict, list)):
            self.content = json.dumps(body).encode("utf-8")
        elif isinstance(body, bytes):
            self.content = body
        else:
            self.content = str(body).encode("utf-8")
        self.headers = {"content-type": "application/json"}

    def get_text(self) -> str:
        return self.content.decode("utf-8")

    def set_text(self, text: str) -> None:
        self.content = text.encode("utf-8")


__all__ = [
    "SectionAddon",
    "FlowState",
    "StreamingRestorer",
    "_diff_placeholders",
]
