"""SIEM webhook sink (Task 4.8) — fire-and-forget POST + HMAC signature."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from praesidio_gateway.audit.sinks.webhook import SiemWebhookSink, sign


def test_sign_matches_known_hmac_sha256():
    body = b'{"hello":"world"}'
    secret = "topsecret"
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sign(secret, body) == expected


@pytest.mark.asyncio
async def test_webhook_disabled_when_no_url():
    s = SiemWebhookSink(url=None)
    assert s.enabled is False
    # Calling emit on a disabled sink is a no-op (and safe).
    await s.emit([{"x": 1}])


@pytest.mark.asyncio
async def test_webhook_fires_with_signature():
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["sig"] = request.headers.get("x-praesidio-signature")
        captured["ct"] = request.headers.get("content-type")
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://siem.local/audit").mock(side_effect=_handler)
        sink = SiemWebhookSink(url="https://siem.local/audit", secret="topsecret")
        try:
            await sink.emit([{"tenant_id": "t1", "decision": "allow"}])
        finally:
            await sink.close()
        assert route.called

    assert captured["ct"] == "application/json"
    payload = json.loads(captured["body"])  # type: ignore[arg-type]
    assert payload == {"tenant_id": "t1", "decision": "allow"}
    expected_sig = (
        "sha256="
        + hmac.new(
            b"topsecret",
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    assert captured["sig"] == expected_sig


@pytest.mark.asyncio
async def test_webhook_emits_without_signature_when_no_secret():
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["sig"] = request.headers.get("x-praesidio-signature")
        return httpx.Response(200)

    with respx.mock(assert_all_called=True) as router:
        router.post("https://siem.local/audit").mock(side_effect=_handler)
        sink = SiemWebhookSink(url="https://siem.local/audit", secret=None)
        try:
            await sink.emit([{"foo": "bar"}])
        finally:
            await sink.close()
    assert captured["sig"] is None


@pytest.mark.asyncio
async def test_webhook_swallows_upstream_errors():
    """A 5xx from the SIEM must not propagate — sink is best-effort."""
    with respx.mock(assert_all_called=True) as router:
        router.post("https://siem.local/audit").mock(
            return_value=httpx.Response(500, text="server boom")
        )
        sink = SiemWebhookSink(url="https://siem.local/audit", secret="s")
        try:
            # Must not raise.
            await sink.emit([{"x": 1}])
        finally:
            await sink.close()
