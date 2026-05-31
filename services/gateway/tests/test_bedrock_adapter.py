"""Bedrock provider adapter tests (G10).

Covers:
  * payload reshaping (``model`` stripped, ``anthropic_version`` set)
  * URL routing (invoke vs invoke-with-response-stream)
  * signer headers are forwarded to the wire
  * streaming yields raw upstream bytes
  * construction errors when region / model_id missing
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from section_gateway.proxy.base import UpstreamRequest
from section_gateway.proxy.bedrock import BedrockAdapter


class _StubSigner:
    """Recording signer — injects a sentinel header so tests can assert."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def sign(
        self,
        *,
        method: str,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, str]:
        self.calls.append({"method": method, "url": url, "body": body, "headers": dict(headers)})
        signed = dict(headers)
        signed["authorization"] = "AWS4-HMAC-SHA256 Credential=stub"
        signed["x-amz-date"] = "20260101T000000Z"
        return signed


def test_init_requires_region() -> None:
    with pytest.raises(ValueError, match="region"):
        BedrockAdapter(region="", model_id="anthropic.claude-3-haiku", signer=_StubSigner())


def test_init_requires_model_id() -> None:
    with pytest.raises(ValueError, match="model_id"):
        BedrockAdapter(region="us-east-1", model_id="", signer=_StubSigner())


def test_payload_strips_model_and_adds_anthropic_version() -> None:
    a = BedrockAdapter(
        region="us-east-1",
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        signer=_StubSigner(),
    )
    out = a._payload_for({"model": "claude-3-haiku", "messages": [{"role": "user", "content": "hi"}]})
    assert "model" not in out
    assert out["anthropic_version"] == "bedrock-2023-05-31"
    assert out["messages"] == [{"role": "user", "content": "hi"}]


def test_payload_respects_caller_anthropic_version() -> None:
    a = BedrockAdapter(region="us-east-1", model_id="m", signer=_StubSigner())
    out = a._payload_for({"anthropic_version": "custom-version"})
    assert out["anthropic_version"] == "custom-version"


def test_url_routes_invoke_and_stream() -> None:
    a = BedrockAdapter(region="us-west-2", model_id="anthropic.claude-3-haiku", signer=_StubSigner())
    assert a._url(stream=False).endswith("/model/anthropic.claude-3-haiku/invoke")
    assert a._url(stream=True).endswith("/model/anthropic.claude-3-haiku/invoke-with-response-stream")
    assert a._url(stream=False).startswith("https://bedrock-runtime.us-west-2.amazonaws.com")


def test_base_url_override() -> None:
    a = BedrockAdapter(
        region="us-east-1",
        model_id="m",
        signer=_StubSigner(),
        base_url="https://bedrock.example.test/",
    )
    assert a._url(stream=False) == "https://bedrock.example.test/model/m/invoke"


@pytest.mark.asyncio
async def test_chat_completion_signs_and_posts() -> None:
    signer = _StubSigner()
    model_id = "anthropic.claude-3-haiku-20240307-v1:0"
    a = BedrockAdapter(
        region="us-east-1",
        model_id=model_id,
        signer=signer,
        base_url="https://bedrock.test",
    )
    expected_url = f"https://bedrock.test/model/{model_id}/invoke"
    upstream_body = {"id": "msg_1", "content": [{"type": "text", "text": "hello"}]}
    with respx.mock(assert_all_called=True) as router:
        route = router.post(expected_url).mock(
            return_value=httpx.Response(200, json=upstream_body)
        )
        req = UpstreamRequest(
            path="/v1/messages",
            body={"model": "claude-3-haiku", "messages": [{"role": "user", "content": "hi"}]},
            stream=False,
        )
        resp = await a.chat_completion(req)
    # Response surface.
    assert hasattr(resp, "status_code")
    assert resp.status_code == 200
    assert json.loads(resp.body) == upstream_body
    # Signer was invoked with the rendered payload.
    assert len(signer.calls) == 1
    call = signer.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == expected_url
    sent = json.loads(call["body"].decode())
    assert "model" not in sent
    assert sent["anthropic_version"] == "bedrock-2023-05-31"
    # And the signed Authorization header reached httpx (visible on the request).
    sent_request = route.calls.last.request
    assert sent_request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256")
    assert sent_request.headers.get("accept") == "application/json"
    await a.close()


@pytest.mark.asyncio
async def test_stream_yields_chunks_and_sets_eventstream_accept() -> None:
    signer = _StubSigner()
    model_id = "anthropic.claude-3-haiku-20240307-v1:0"
    a = BedrockAdapter(
        region="us-east-1",
        model_id=model_id,
        signer=signer,
        base_url="https://bedrock.test",
    )
    expected_url = f"https://bedrock.test/model/{model_id}/invoke-with-response-stream"
    payload_chunks = [b"chunk-a", b"chunk-b", b"chunk-c"]
    with respx.mock(assert_all_called=True) as router:
        router.post(expected_url).mock(
            return_value=httpx.Response(200, content=b"".join(payload_chunks))
        )
        req = UpstreamRequest(
            path="/v1/messages",
            body={"model": "x", "messages": []},
            stream=True,
        )
        result = await a.chat_completion(req)
        collected = b""
        async for chunk in result:  # type: ignore[union-attr]
            collected += chunk
    assert collected == b"".join(payload_chunks)
    # Accept header signalled eventstream.
    assert signer.calls[0]["headers"]["accept"] == "application/vnd.amazon.eventstream"
    await a.close()


def test_missing_boto3_credentials_raises_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no signer and no creds are supplied, the adapter must fail loudly."""
    # Simulate a boto3-less environment by monkeypatching the import.
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "boto3":
            raise ImportError("no boto3 in this test env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="boto3"):
        BedrockAdapter(region="us-east-1", model_id="m")
