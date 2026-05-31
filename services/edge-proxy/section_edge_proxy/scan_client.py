"""HTTP client that talks to the Section gateway.

Wraps ``httpx.AsyncClient`` so the proxy addon can call ``/v1/scan`` and
``/v1/restore`` from inside mitmproxy's event loop. All gateway-facing
calls go through this module so the addon stays testable (the unit
tests mock this class, not mitmproxy's transport).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from .config import EdgeSettings

log = structlog.get_logger(__name__)


# Placeholder regex must match the gateway's grammar (see
# `section_gateway.anonymize.tokenizer._PLACEHOLDER_RE` and the
# scan.py copy). Keep in sync.
PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4})>")


@dataclass
class ScanResult:
    """Decoded `/v1/scan` response.

    Attributes:
        request_id: The gateway-minted (or session-derived) request id.
            Echoed back to ``/v1/restore`` so vault lookups land in the
            right scope.
        action: One of ``"allow"``, ``"mask"``, ``"block"``.
        sanitised: The rewrite-ready prompt (None when ``action=block``).
        transforms: List of ``{label,placeholder,method,scope}`` dicts.
        reason: Block reason (when ``action=block``).
        severity: Block severity (when ``action=block``).
        raw: Full decoded JSON for the audit/log path.
    """

    request_id: str
    action: str
    sanitised: str | None
    transforms: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    severity: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RestoreResult:
    """Decoded `/v1/restore` response."""

    text: str
    restored: int
    missing: list[str]


class GatewayClient:
    """Thin async wrapper around ``/v1/scan`` and ``/v1/restore``.

    Lifecycle: one instance per :class:`SectionAddon`. ``aclose()`` MUST
    be called from the addon's ``done`` hook so the underlying
    ``httpx.AsyncClient`` releases its pool.
    """

    def __init__(self, settings: EdgeSettings, *, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_s),
            # The gateway uses a self-signed cert in dev — but for the
            # edge proxy we trust the operator-supplied URL and either
            # verify against the OS trust store (default) or accept a
            # plain HTTP gateway on 127.0.0.1.
            verify=True,
        )

    def _headers(self) -> dict[str, str]:
        h = {
            "content-type": "application/json",
            "user-agent": "section-edge-proxy/0.1.0",
            "x-section-tenant": self.settings.tenant,
        }
        if self.settings.api_key:
            h["x-api-key"] = self.settings.api_key
        return h

    async def scan(
        self,
        *,
        text: str,
        client: str,
        url: str | None,
        model: str | None,
        session_id: str | None,
    ) -> ScanResult:
        """POST `/v1/scan`. Raises :class:`httpx.HTTPError` on transport failures.

        Args:
            text: Prompt text to scan.
            client: One of ``edge-proxy``, ``cli``, etc. (audit tag).
            url: Optional origin URL (audit only).
            model: Optional provider model id (audit hint).
            session_id: Optional caller-supplied id; lets multi-turn
                clients share placeholder aliases across calls.
        """
        payload: dict[str, Any] = {
            "text": text,
            "client": client,
        }
        if url is not None:
            payload["url"] = url
        if model is not None:
            payload["model"] = model
        if session_id is not None:
            payload["session_id"] = session_id

        resp = await self._client.post(
            self.settings.scan_url,
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return ScanResult(
            request_id=data.get("request_id", ""),
            action=data.get("action", "allow"),
            sanitised=data.get("sanitised"),
            transforms=list(data.get("transforms") or []),
            reason=data.get("reason"),
            severity=data.get("severity"),
            raw=data,
        )

    async def restore(self, *, request_id: str, text: str) -> RestoreResult:
        """POST `/v1/restore`. Same error surface as :meth:`scan`."""
        resp = await self._client.post(
            self.settings.restore_url,
            headers=self._headers(),
            json={"request_id": request_id, "text": text},
            timeout=self.settings.restore_timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        return RestoreResult(
            text=data.get("text", text),
            restored=int(data.get("restored", 0)),
            missing=list(data.get("missing") or []),
        )

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        await self._client.aclose()


__all__ = ["GatewayClient", "ScanResult", "RestoreResult", "PLACEHOLDER_RE"]
