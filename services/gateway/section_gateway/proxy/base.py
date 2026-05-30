"""Provider adapter Protocol + small helpers."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class UpstreamRequest:
    """A normalised request — provider adapters render this to their wire format."""

    path: str                            # e.g. "/v1/chat/completions"
    body: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class UpstreamResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


@runtime_checkable
class ProviderAdapter(Protocol):
    name: str

    async def chat_completion(
        self, req: UpstreamRequest
    ) -> AsyncIterator[bytes] | UpstreamResponse: ...

    async def close(self) -> None: ...
