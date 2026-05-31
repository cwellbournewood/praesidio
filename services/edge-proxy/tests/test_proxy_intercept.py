"""Tests for the SectionAddon request + response hooks.

We exercise the hooks directly with :class:`FakeFlow` objects rather
than booting mitmproxy. Gateway calls are mocked via respx.
"""
from __future__ import annotations

import json

import httpx
import pytest

from section_edge_proxy.proxy import (
    SectionAddon,
    StreamingRestorer,
    _diff_placeholders,
)
from section_edge_proxy.scan_client import GatewayClient
from section_edge_proxy.status import StatusFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _addon(settings, gateway_mock):
    """Build a SectionAddon wired to respx via a fresh httpx client."""
    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(_via_respx(gateway_mock)))
    gateway = GatewayClient(settings, client=httpx_client)
    return SectionAddon(settings, gateway=gateway), httpx_client


def _via_respx(router):
    """Bridge respx's MockRouter to httpx's MockTransport handler signature."""

    def _handler(request: httpx.Request) -> httpx.Response:
        # respx routes via the AsyncClient's transport directly when
        # `mock()` is active; if not, we forward manually.
        return router.handler(request) or httpx.Response(404, text="no route")

    return _handler


# ---------------------------------------------------------------------------
# Pass-through behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_intercepted_host_is_passthrough(settings, gateway_mock, fake_flow_factory):
    """An unrelated host should not invoke the gateway at all."""
    addon = SectionAddon(settings, gateway=GatewayClient(settings))
    flow = fake_flow_factory(host="example.com", path="/api/foo", body={"x": 1})
    await addon.request(flow)
    # No metadata stamp, body untouched, no gateway call.
    assert flow.metadata == {}
    assert flow.request.json() == {"x": 1}
    assert not gateway_mock.routes[0].called
    await addon.gateway.aclose()


@pytest.mark.asyncio
async def test_non_json_body_is_passthrough(settings, gateway_mock, fake_flow_factory):
    addon = SectionAddon(settings, gateway=GatewayClient(settings))
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body=b"not json",
    )
    await addon.request(flow)
    # Metadata gets a state stamp but no rewrite happens.
    assert flow.request.content == b"not json"
    await addon.gateway.aclose()


# ---------------------------------------------------------------------------
# Scan + mask flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_mask_rewrites_request_body(settings, gateway_mock, fake_flow_factory):
    """When /v1/scan returns action=mask the request body is rewritten."""
    gateway_mock.post("http://gateway.test/v1/scan").respond(
        200,
        json={
            "request_id": "req-mask-1",
            "action": "mask",
            "sanitised": "you are helper\x1e\x1e--SECTION-SEP--\x1e\x1esend mail to <EMAIL_A2B3>",
            "transforms": [
                {
                    "label": "pii.email",
                    "placeholder": "<EMAIL_A2B3>",
                    "method": "tokenise",
                    "scope": "request",
                }
            ],
            "findings": [],
            "decision": {"policy_id": "pii"},
            "bundle_digest": "abc",
        },
    )

    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "you are helper"},
                {"role": "user", "content": "send mail to alice@example.com"},
            ],
        },
    )

    await addon.request(flow)

    # No HTTP response was substituted — the request was forwarded.
    assert flow.response is None
    new_body = json.loads(flow.request.content)
    assert new_body["messages"][1]["content"] == "send mail to <EMAIL_A2B3>"
    # System message preserved.
    assert new_body["messages"][0]["content"] == "you are helper"
    # Metadata records the request_id for /v1/restore on the response side.
    state = flow.metadata["section"]
    assert state.request_id == "req-mask-1"
    await gateway.aclose()


# ---------------------------------------------------------------------------
# Block flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_block_returns_403_with_section_blocked_body(
    settings, gateway_mock, fake_flow_factory
):
    """A block decision returns HTTP 403 with the gateway's standard body."""
    gateway_mock.post("http://gateway.test/v1/scan").respond(
        200,
        json={
            "request_id": "req-block",
            "action": "block",
            "sanitised": None,
            "transforms": [],
            "findings": [],
            "decision": {"policy_id": "sec"},
            "bundle_digest": "abc",
            "reason": "AWS credential not permitted",
            "severity": "high",
        },
    )

    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "deploy with AKIAIOSFODNN7EXAMPLE"}
            ],
        },
    )

    await addon.request(flow)

    assert flow.response is not None
    assert flow.response.status_code == 403
    body = json.loads(flow.response.content)
    assert body["error"]["type"] == "section_blocked"
    assert body["error"]["message"] == "AWS credential not permitted"
    assert body["error"]["severity"] == "high"
    assert body["error"]["policy_id"] == "sec"
    assert body["error"]["request_id"] == "req-block"
    await gateway.aclose()


# ---------------------------------------------------------------------------
# Allow flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_allow_leaves_body_unchanged(settings, gateway_mock, fake_flow_factory):
    # Default gateway_mock returns allow.
    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)
    original_body = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "what is 2 + 2"}],
    }
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body=original_body,
    )

    await addon.request(flow)
    assert flow.response is None
    assert json.loads(flow.request.content) == original_body
    await gateway.aclose()


# ---------------------------------------------------------------------------
# Gateway-unreachable fail-closed behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_unreachable_fails_closed(settings, gateway_mock, fake_flow_factory):
    """Without `fail_open`, a gateway error stops the request with 502."""
    gateway_mock.post("http://gateway.test/v1/scan").respond(503, text="oops")

    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    await addon.request(flow)

    assert flow.response is not None
    assert flow.response.status_code == 502
    body = json.loads(flow.response.content)
    assert body["error"]["type"] == "section_gateway_unreachable"
    await gateway.aclose()


@pytest.mark.asyncio
async def test_gateway_unreachable_fails_open_when_configured(
    settings, gateway_mock, fake_flow_factory
):
    """With `fail_open=true`, a gateway error still forwards the request."""
    gateway_mock.post("http://gateway.test/v1/scan").respond(503, text="oops")

    open_settings = settings.model_copy(update={"fail_open": True})
    gateway = GatewayClient(open_settings)
    addon = SectionAddon(open_settings, gateway=gateway)
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    await addon.request(flow)

    # No response substituted, body unchanged → mitmproxy will forward.
    assert flow.response is None
    await gateway.aclose()


# ---------------------------------------------------------------------------
# Response-side restoration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_restores_placeholders(
    settings, gateway_mock, fake_flow_factory
):
    """When the upstream reply contains a placeholder, /v1/restore is called."""
    gateway_mock.post("http://gateway.test/v1/restore").respond(
        200,
        json={
            "request_id": "req-1",
            "text": "I'll email alice@example.com soon.",
            "restored": 1,
            "missing": [],
        },
    )

    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)

    from tests.conftest import FakeResponse

    # Build a flow whose request was already scanned (mark metadata).
    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    flow.metadata["section"] = type("S", (), {"request_id": "req-1", "placeholders": {}})()
    flow.response = FakeResponse(
        status_code=200,
        body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "I'll email <EMAIL_A2B3> soon.",
                            "role": "assistant",
                        }
                    }
                ]
            }
        ),
        headers={"content-type": "application/json"},
    )

    await addon.response(flow)
    body = flow.response.get_text()
    assert "alice@example.com" in body
    assert "<EMAIL_A2B3>" not in body
    await gateway.aclose()


@pytest.mark.asyncio
async def test_response_with_no_placeholders_skips_gateway(
    settings, gateway_mock, fake_flow_factory
):
    """A clean response body should not trigger a /v1/restore round-trip."""
    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway)

    from tests.conftest import FakeResponse

    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    flow.metadata["section"] = type("S", (), {"request_id": "req-2", "placeholders": {}})()
    flow.response = FakeResponse(
        body=json.dumps({"choices": [{"message": {"content": "clean reply"}}]}),
        headers={"content-type": "application/json"},
    )

    await addon.response(flow)
    # restore route default is no-op, but we want to assert it wasn't called.
    restore_route = gateway_mock.routes[1]
    assert not restore_route.called
    await gateway.aclose()


# ---------------------------------------------------------------------------
# Streaming SSE restoration
# ---------------------------------------------------------------------------

def test_streaming_restorer_handles_chunk_boundary():
    """A placeholder split across two chunks is still restored correctly."""
    r = StreamingRestorer(
        initial_cache={"<EMAIL_A2B3>": "alice@example.com"}
    )
    out1 = r.feed("Hello! send to <EMAIL_A")
    out2 = r.feed("2B3> please.")
    out3 = r.finalise()
    combined = out1 + out2 + out3
    assert combined == "Hello! send to alice@example.com please."


def test_streaming_restorer_emits_safe_prefix_before_open_bracket():
    """Text before a '<' is emitted; the trailing fragment is held."""
    r = StreamingRestorer(initial_cache={"<EMAIL_A2B3>": "alice@example.com"})
    out1 = r.feed("clean prefix <EMAIL_A")
    # The 'clean prefix ' part should already be visible.
    assert out1.startswith("clean prefix ")
    # The '<EMAIL_A' fragment is held back until the close-angle arrives.
    assert "<" not in out1
    out2 = r.feed("2B3>")
    out_final = r.finalise()
    assert (out1 + out2 + out_final) == "clean prefix alice@example.com"


def test_streaming_restorer_leaves_unknown_placeholder_alone():
    """A placeholder not in the cache is emitted untouched."""
    r = StreamingRestorer(initial_cache={})
    out1 = r.feed("see <SECRET_A2B3>")
    out_final = r.finalise()
    assert (out1 + out_final) == "see <SECRET_A2B3>"


def test_streaming_restorer_handles_stray_open_bracket():
    """A stray '<' that isn't a placeholder eventually gets flushed."""
    r = StreamingRestorer(initial_cache={})
    out1 = r.feed("a < b ")
    out_final = r.feed("and c < d") + r.finalise()
    assert (out1 + out_final) == "a < b and c < d"


def test_streaming_restorer_byte_per_chunk():
    """One byte at a time still reconstructs the placeholder."""
    msg = "send to <EMAIL_A2B3> now"
    cache = {"<EMAIL_A2B3>": "alice@example.com"}
    r = StreamingRestorer(initial_cache=cache)
    out = ""
    for ch in msg:
        out += r.feed(ch)
    out += r.finalise()
    assert out == "send to alice@example.com now"


# ---------------------------------------------------------------------------
# _diff_placeholders helper
# ---------------------------------------------------------------------------

def test_diff_placeholders_basic():
    masked = "send <EMAIL_A2B3> to <NAME_C7D4>"
    restored = "send alice@example.com to alice"
    out = _diff_placeholders(masked, restored)
    assert out == {"<EMAIL_A2B3>": "alice@example.com", "<NAME_C7D4>": "alice"}


def test_diff_placeholders_single_at_start():
    out = _diff_placeholders("<EMAIL_A2B3> hi", "alice@example.com hi")
    assert out == {"<EMAIL_A2B3>": "alice@example.com"}


def test_diff_placeholders_single_at_end():
    out = _diff_placeholders("hi <EMAIL_A2B3>", "hi alice@example.com")
    assert out == {"<EMAIL_A2B3>": "alice@example.com"}


def test_diff_placeholders_no_placeholders():
    out = _diff_placeholders("no placeholders here", "no placeholders here")
    assert out == {}


# ---------------------------------------------------------------------------
# Status hook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_file_records_each_decision(
    settings, gateway_mock, fake_flow_factory, tmp_ca_dir
):
    """A status file is updated with the action of every scan."""
    gateway_mock.post("http://gateway.test/v1/scan").respond(
        200,
        json={
            "request_id": "req-stat",
            "action": "allow",
            "sanitised": None,
            "transforms": [],
            "findings": [],
            "decision": {},
            "bundle_digest": "abc",
        },
    )

    status = StatusFile(
        tmp_ca_dir / "edge-proxy-status.json",
        listen="127.0.0.1:8888",
        gateway=settings.gateway_url,
        hosts=["api.openai.com"],
    )
    gateway = GatewayClient(settings)
    addon = SectionAddon(settings, gateway=gateway, status=status)

    flow = fake_flow_factory(
        host="api.openai.com",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    await addon.request(flow)

    snap = json.loads((tmp_ca_dir / "edge-proxy-status.json").read_text())
    assert snap["decisions"] == 1
    assert snap["allows"] == 1
    assert snap["last_decision"]["host"] == "api.openai.com"
    await gateway.aclose()
