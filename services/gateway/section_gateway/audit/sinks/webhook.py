"""Generic SIEM webhook sink.

POSTs each audit row as a single JSON document to ``SECTION_SIEM_WEBHOOK_URL``.

When ``SECTION_SIEM_WEBHOOK_SECRET`` is set, every POST carries an
``X-Section-Signature: sha256=<hex>`` header computed as
``HMAC-SHA256(secret, raw_request_body)``. Receivers verify the signature to
ensure the event came from a trusted Section instance.

This sink is **best-effort**: failures are logged and metered but never
propagate into the audit writer. It runs entirely asynchronously and never
blocks the request path.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

import httpx

_log = logging.getLogger(__name__)


def _jsonable(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, (bytes, bytearray)):
        return o.hex()
    if isinstance(o, (set, tuple, frozenset)):
        return list(o)
    raise TypeError(f"unserialisable type: {type(o).__name__}")


def sign(secret: str, body: bytes) -> str:
    """Return the ``sha256=<hex>`` HMAC of ``body`` keyed with ``secret``."""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


class SiemWebhookSink:
    """Async best-effort POST sink. Disabled when ``url`` is None or empty."""

    def __init__(
        self,
        url: str | None,
        secret: str | None = None,
        *,
        timeout: float = 5.0,
    ) -> None:
        self.url = url
        self.secret = secret
        self._enabled = bool(url)
        self._client = httpx.AsyncClient(timeout=timeout) if self._enabled else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def emit(self, rows: list[dict[str, Any]]) -> None:
        """POST each row as a JSON document. Errors are logged and swallowed."""
        if not self._enabled or self._client is None:
            return
        for row in rows:
            try:
                body = json.dumps(row, default=_jsonable, separators=(",", ":")).encode("utf-8")
                headers = {"content-type": "application/json"}
                if self.secret:
                    headers["x-section-signature"] = sign(self.secret, body)
                r = await self._client.post(
                    self.url,  # type: ignore[arg-type]
                    content=body,
                    headers=headers,
                )
                if r.status_code >= 400:
                    _log.warning("siem webhook %s: %s", r.status_code, r.text[:200])
            except Exception as exc:  # pragma: no cover - best-effort path
                _log.warning("siem webhook emit failed: %s", exc)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # pragma: no cover
                pass
