"""Azure OpenAI adapter.

Azure routes per-deployment with an `api-version` query parameter. The
caller-requested ``model`` becomes the deployment name.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .base import ProviderAdapter, UpstreamRequest, UpstreamResponse


class AzureOpenAIAdapter(ProviderAdapter):
    name = "azure-openai"

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        api_version: str = "2024-10-21",
        timeout: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._api_version = api_version
        self._client = httpx.AsyncClient(timeout=timeout)

    def _build_url(self, body: dict, path_suffix: str) -> str:
        deployment = body.get("model") or body.get("deployment") or "default"
        # Azure URL: {base}/openai/deployments/{dep}/{op}?api-version=…
        return (
            f"{self._base}/openai/deployments/{deployment}/{path_suffix}"
            f"?api-version={self._api_version}"
        )

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json"}
        if self._key:
            h["api-key"] = self._key
        return h

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse:
        op = "chat/completions"
        if req.path.endswith("/completions") and "chat" not in req.path:
            op = "completions"
        elif req.path.endswith("/embeddings"):
            op = "embeddings"
        url = self._build_url(req.body, op)
        if req.stream:
            return self._stream(url, req.body)
        r = await self._client.post(url, json=req.body, headers=self._headers())
        return UpstreamResponse(
            status_code=r.status_code, headers=dict(r.headers), body=r.content
        )

    async def _stream(self, url: str, body: dict) -> AsyncIterator[bytes]:
        async with self._client.stream("POST", url, json=body, headers=self._headers()) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                if chunk:
                    yield chunk

    async def close(self) -> None:
        await self._client.aclose()
