"""AWS Bedrock provider adapter (G10).

Bedrock exposes a per-model HTTPS endpoint::

    POST https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/invoke

This adapter speaks the *converse-compatible* surface for the Anthropic
Claude models hosted on Bedrock — the request shape is the standard
Anthropic ``messages`` payload, which lets the gateway's existing
Anthropic request/response handling and SSE-streaming logic work
unchanged. Other model families (Titan, Cohere, AI21) are out of scope
for this adapter; operators can sub-class :class:`BedrockAdapter` to
support them.

Authentication
--------------
AWS SigV4. We lazy-import ``boto3``/``botocore`` for signing because
those packages are heavy and not every Praesidio deployment uses
Bedrock. The adapter degrades gracefully when ``boto3`` is missing —
it raises a clear ``RuntimeError`` at construction time so the
deploy-time misconfiguration is loud rather than silently wrong at
request time.

For testability we expose a ``signer`` hook so the unit tests can
swap in a stub signer and assert on the rendered request.

References
----------
* `Bedrock Runtime API <https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html>`_
* `Anthropic-on-Bedrock request schema <https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages.html>`_
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from .base import ProviderAdapter, UpstreamRequest, UpstreamResponse


class _Signer(Protocol):
    """Pluggable signer protocol (botocore-compatible subset)."""

    def sign(
        self,
        *,
        method: str,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, str]: ...


class _BotocoreSigner:
    """SigV4 signer using botocore. Lazy-imported."""

    def __init__(self, *, region: str, access_key: str, secret_key: str, session_token: str | None) -> None:
        try:
            from botocore.auth import SigV4Auth
            from botocore.awsrequest import AWSRequest
            from botocore.credentials import Credentials
        except ImportError as exc:  # pragma: no cover - covered by clear error
            raise RuntimeError(
                "boto3/botocore is required for the Bedrock adapter. "
                "Install with: pip install boto3"
            ) from exc
        self._SigV4Auth = SigV4Auth
        self._AWSRequest = AWSRequest
        self._creds = Credentials(access_key, secret_key, session_token)
        self._region = region

    def sign(
        self,
        *,
        method: str,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, str]:
        req = self._AWSRequest(method=method, url=url, data=body, headers=headers)
        self._SigV4Auth(self._creds, "bedrock", self._region).add_auth(req)
        return dict(req.headers.items())


class BedrockAdapter(ProviderAdapter):
    """Anthropic-on-Bedrock chat-completion provider.

    Parameters
    ----------
    region:
        AWS region (e.g. ``us-east-1``).
    model_id:
        Bedrock model identifier
        (e.g. ``anthropic.claude-3-5-sonnet-20241022-v2:0``).
    access_key / secret_key / session_token:
        AWS credentials. When all are ``None`` the adapter falls back to
        the default boto3 credential chain (env, profile, instance
        role). Mostly useful for tests.
    signer:
        Optional pre-built signer. Lets tests inject a stub without
        importing botocore.
    base_url:
        Optional override for the Bedrock runtime endpoint. Defaults to
        ``https://bedrock-runtime.{region}.amazonaws.com``.
    """

    name = "bedrock"

    def __init__(
        self,
        *,
        region: str,
        model_id: str,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        signer: _Signer | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not region:
            raise ValueError("BedrockAdapter: region is required")
        if not model_id:
            raise ValueError("BedrockAdapter: model_id is required")
        self._region = region
        self._model_id = model_id
        self._base = (
            base_url.rstrip("/")
            if base_url
            else f"https://bedrock-runtime.{region}.amazonaws.com"
        )
        self._client = httpx.AsyncClient(timeout=timeout)
        if signer is not None:
            self._signer: _Signer = signer
        else:
            if not (access_key and secret_key):
                # Defer credential resolution to botocore's default chain.
                try:
                    import boto3  # type: ignore[import-not-found]

                    creds = boto3.Session().get_credentials()
                    if creds is None:
                        raise RuntimeError(
                            "BedrockAdapter: no AWS credentials found in the "
                            "default chain; pass access_key/secret_key explicitly."
                        )
                    frozen = creds.get_frozen_credentials()
                    access_key = frozen.access_key
                    secret_key = frozen.secret_key
                    session_token = frozen.token
                except ImportError as exc:  # pragma: no cover
                    raise RuntimeError(
                        "boto3 is required for the Bedrock adapter when no "
                        "explicit credentials are passed."
                    ) from exc
            self._signer = _BotocoreSigner(
                region=region,
                access_key=access_key or "",
                secret_key=secret_key or "",
                session_token=session_token,
            )

    # -- ProviderAdapter ----------------------------------------------------

    def _payload_for(self, body: dict[str, Any]) -> dict[str, Any]:
        """Strip the ``model`` field — Bedrock derives it from the URL path."""
        out = dict(body)
        out.pop("model", None)
        # Anthropic-on-Bedrock REQUIRES anthropic_version.
        out.setdefault("anthropic_version", "bedrock-2023-05-31")
        return out

    def _url(self, *, stream: bool) -> str:
        op = "invoke-with-response-stream" if stream else "invoke"
        return f"{self._base}/model/{self._model_id}/{op}"

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse:
        import json as _json

        url = self._url(stream=req.stream)
        body = _json.dumps(self._payload_for(req.body)).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "accept": (
                "application/vnd.amazon.eventstream" if req.stream else "application/json"
            ),
        }
        signed = self._signer.sign(method="POST", url=url, body=body, headers=headers)
        if req.stream:
            return self._stream(url, body, signed)
        r = await self._client.post(url, content=body, headers=signed)
        return UpstreamResponse(
            status_code=r.status_code, headers=dict(r.headers), body=r.content
        )

    async def _stream(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> AsyncIterator[bytes]:
        async with self._client.stream(
            "POST", url, content=body, headers=headers
        ) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                if chunk:
                    yield chunk

    async def close(self) -> None:
        await self._client.aclose()
