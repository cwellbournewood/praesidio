"""OpenAI provider adapter. Pass-through with optional SSE streaming."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from .base import ProviderAdapter, UpstreamRequest, UpstreamResponse

_log = logging.getLogger(__name__)


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self, base_url: str, api_key: str | None, *, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    def _auth_headers(self, extra: dict[str, str]) -> dict[str, str]:
        h = {"content-type": "application/json"}
        if self._key:
            h["authorization"] = f"Bearer {self._key}"
        # Pass through caller's organization / project headers if present.
        for k, v in extra.items():
            if k.lower() in {"openai-organization", "openai-project", "user-agent"}:
                h[k.lower()] = v
        return h

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse:
        url = f"{self._base}{req.path}"
        headers = self._auth_headers(req.headers)

        if req.stream:
            return self._stream(url, req.body, headers)

        r = await self._client.post(url, json=req.body, headers=headers)
        return UpstreamResponse(
            status_code=r.status_code, headers=dict(r.headers), body=r.content
        )

    async def _stream(
        self, url: str, body: dict, headers: dict[str, str]
    ) -> AsyncIterator[bytes]:
        async with self._client.stream("POST", url, json=body, headers=headers) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                if chunk:
                    yield chunk

    async def close(self) -> None:
        await self._client.aclose()
