"""Anthropic messages API adapter."""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .base import ProviderAdapter, UpstreamRequest, UpstreamResponse


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        version: str = "2023-06-01",
        timeout: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._version = version
        self._client = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        h = {
            "content-type": "application/json",
            "anthropic-version": self._version,
        }
        if self._key:
            h["x-api-key"] = self._key
        return h

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse:
        url = f"{self._base}{req.path}"
        if req.stream:
            return self._stream(url, req.body)
        r = await self._client.post(url, json=req.body, headers=self._headers())
        return UpstreamResponse(
            status_code=r.status_code, headers=dict(r.headers), body=r.content
        )

    async def _stream(self, url: str, body: dict) -> AsyncIterator[bytes]:
        headers = self._headers()
        headers["accept"] = "text/event-stream"
        async with self._client.stream("POST", url, json=body, headers=headers) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                if chunk:
                    yield chunk

    async def close(self) -> None:
        await self._client.aclose()
