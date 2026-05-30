"""Ollama (local) provider adapter. Translates OpenAI-shaped chat calls to
Ollama's `/api/chat` endpoint when needed; otherwise passes through.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .base import ProviderAdapter, UpstreamRequest, UpstreamResponse


class OllamaAdapter(ProviderAdapter):
    name = "ollama"

    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse:
        # If the caller used the OpenAI shape, Ollama exposes a compatible
        # `/v1/chat/completions` endpoint as of 0.1.21+; otherwise route to
        # `/api/chat`.
        path = req.path if "/v1/" in req.path else "/api/chat"
        url = f"{self._base}{path}"
        headers = {"content-type": "application/json"}
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
