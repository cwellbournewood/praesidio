"""Splunk HTTP Event Collector sink. No-op unless SPLUNK_HEC_URL is configured."""
from __future__ import annotations

import logging
from typing import Any

import httpx

_log = logging.getLogger(__name__)


class SplunkHECSink:
    def __init__(self, url: str | None, token: str | None) -> None:
        self.url = url
        self.token = token
        self._enabled = bool(url and token)
        self._client = httpx.AsyncClient(timeout=5.0) if self._enabled else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def emit(self, events: list[dict[str, Any]]) -> None:
        if not self._enabled or self._client is None:
            return
        body = "\n".join(
            __import__("json").dumps({"event": e, "sourcetype": "section:audit"})
            for e in events
        )
        try:
            r = await self._client.post(
                self.url,  # type: ignore[arg-type]
                headers={"Authorization": f"Splunk {self.token}"},
                content=body,
            )
            if r.status_code >= 400:
                _log.warning("splunk HEC %s: %s", r.status_code, r.text[:200])
        except Exception:
            _log.exception("splunk HEC emit failed")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
