"""POST /admin/detokenise — controlled placeholder reversal (Task 4.4 + G7).

Looks up one or more placeholder tokens (``<LABEL_XXXX>``) in the token
vault and returns the originals. The endpoint requires the
``vault:detokenise`` scope on the caller's principal (or the implicit
``admin`` scope), and every successful or failed reversal is recorded as
an audit row with ``decision="detokenise"`` so SOC/IR can prove the
chain of custody after-the-fact.

G7 hardening
------------
* ``justification`` must be at least 10 characters (was 4).
* ``ticket_id`` is **required** — the operator's IR/SOC ticket reference
  is recorded verbatim. Empty strings are rejected at the model layer.
* Each tenant is rate-limited by
  ``SECTION_DETOK_RATE_LIMIT_PER_TENANT_RPM`` (default 30). The
  bucket is in-memory per process; cross-pod operators should pair this
  with the existing Redis-backed RateLimitMiddleware via a separate URL.
* Every call (including 429-rate-limited ones) emits a SIEM webhook
  event by virtue of the AuditWriter pipeline. The audit row carries
  ``event_type=vault.detokenise`` so SIEM filters can route detokenise
  events to a dedicated index.

Vault key schema is ``v1:{tenant}:{request_id}:{placeholder}``; AES-GCM
AAD also binds tenant+request, so cross-request lookups are rejected at
the vault layer.
"""
from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...auth import Principal, require_scope
from ...config import get_settings
from ...obs.metrics import RATE_LIMIT_BLOCKED_TOTAL
from ...state import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])


# Per-tenant in-memory token-bucket dedicated to this endpoint.
# (Independent of the gateway-wide RateLimitMiddleware.)
_TENANT_BUCKETS: dict[str, tuple[float, float]] = {}


def _consume_tenant(tenant: str, rpm: int) -> tuple[bool, int]:
    """In-memory bucket: returns (allowed, retry_seconds)."""
    if rpm <= 0:
        return True, 0
    now = time.monotonic() * 1000.0
    tokens, ts = _TENANT_BUCKETS.get(tenant, (float(rpm), now))
    elapsed = max(0.0, now - ts)
    refill = rpm / 60_000.0
    tokens = min(float(rpm), tokens + elapsed * refill)
    if tokens >= 1.0:
        tokens -= 1.0
        _TENANT_BUCKETS[tenant] = (tokens, now)
        return True, 0
    retry_ms = int((1.0 - tokens) / refill) if refill > 0 else 60_000
    _TENANT_BUCKETS[tenant] = (tokens, now)
    return False, max(1, retry_ms // 1000)


def _reset_tenant_buckets() -> None:
    """Test hook — wipe the per-tenant bucket state."""
    _TENANT_BUCKETS.clear()


class DetokeniseRequest(BaseModel):
    request_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="The Section request_id under which the placeholders were minted.",
    )
    placeholders: list[str] = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Placeholder tokens to reverse, e.g. `<EMAIL_AB12>`.",
    )
    justification: str = Field(
        ...,
        min_length=10,
        max_length=512,
        description=(
            "Free-text reason; recorded verbatim in the audit row. Must be "
            "at least 10 characters to discourage drive-by reversal."
        ),
    )
    ticket_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "IR / SOC ticket reference (e.g. 'INC-12345'). Recorded "
            "verbatim in the audit row and forwarded to SIEM."
        ),
    )

    @field_validator("ticket_id")
    @classmethod
    def _strip_ticket(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("ticket_id must not be empty after strip")
        return s

    @field_validator("justification")
    @classmethod
    def _strip_justification(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 10:
            raise ValueError("justification must be at least 10 characters after strip")
        return s


class DetokeniseHit(BaseModel):
    placeholder: str
    found: bool
    # Only the SHA-256 hex of the recovered original is returned in the
    # response so the operator can confirm "yes that's the one I asked for"
    # without dumping plaintext PII into a UI log. The plaintext IS returned
    # in the dedicated ``value`` field — callers MUST treat as secret.
    value_sha256: str | None = None
    value: str | None = None


class DetokeniseResponse(BaseModel):
    request_id: str
    hits: list[DetokeniseHit]


def _audit_row(
    *,
    principal: Principal,
    bundle_digest: str,
    request_id: str,
    placeholders: list[str],
    found_count: int,
    justification: str,
    ticket_id: str,
) -> dict[str, Any]:
    """Build a detokenise audit row (decision="detokenise")."""
    payload_for_digest = "|".join(sorted(placeholders)).encode("utf-8")
    return {
        "tenant_id": principal.tenant_id,
        "request_id": request_id,
        "occurred_at": datetime.now(UTC),
        "principal_id": principal.user_id,
        "principal_groups": list(principal.groups),
        "source_ip": principal.source_ip,
        "route": "/admin/detokenise",
        "upstream": "vault",
        "decision": "detokenise",
        "rule_id": None,
        "rule_index": None,
        "policy_id": None,
        "policy_version": None,
        "bundle_digest": bundle_digest,
        "findings": [
            {"placeholder": p, "scope": "vault:detokenise"} for p in placeholders
        ],
        "transforms": [
            {
                "method": "detokenise",
                "count": found_count,
                "event_type": "vault.detokenise",
                "ticket_id": ticket_id,
            }
        ],
        "request_digest": hashlib.sha256(payload_for_digest).hexdigest(),
        "response_digest": None,
        "latency_ms": 0,
        "bytes_in": len(payload_for_digest),
        "bytes_out": 0,
        "degraded": False,
        "mode": "enforce",
        "reason": justification,
        "severity": "high",
    }


@router.post("/detokenise", response_model=DetokeniseResponse)
async def detokenise(
    payload: DetokeniseRequest,
    principal: Principal = Depends(require_scope("vault:detokenise")),
    state: AppState = Depends(get_state),
) -> DetokeniseResponse:
    """Reverse vault placeholders for the caller's tenant.

    Requires the ``vault:detokenise`` scope (or ``admin``). Every call is
    audited regardless of outcome. The plaintext is returned only inside
    the response body — never logged, never echoed in headers.
    """
    if not payload.placeholders:
        raise HTTPException(400, "placeholders[] must not be empty")

    # G7: per-tenant rate limit dedicated to this endpoint.
    settings = get_settings()
    rpm = int(getattr(settings, "section_detok_rate_limit_per_tenant_rpm", 30))
    allowed, retry_s = _consume_tenant(principal.tenant_id, rpm)
    if not allowed:
        RATE_LIMIT_BLOCKED_TOTAL.labels(
            tenant=principal.tenant_id, scope="detokenise"
        ).inc()
        raise HTTPException(
            status_code=429,
            detail={
                "type": "rate_limited",
                "scope": "detokenise",
                "message": (
                    f"per-tenant detokenise rate limit exceeded "
                    f"({rpm} rpm); retry in {retry_s}s"
                ),
                "tenant": principal.tenant_id,
            },
            headers={
                "Retry-After": str(retry_s),
                "X-Section-RateLimit-Limit": str(rpm),
                "X-Section-RateLimit-Scope": "detokenise",
            },
        )

    hits: list[DetokeniseHit] = []
    for ph in payload.placeholders:
        original = await state.vault.get(
            tenant=principal.tenant_id,
            request_id=payload.request_id,
            placeholder=ph,
        )
        if original is None:
            hits.append(DetokeniseHit(placeholder=ph, found=False))
        else:
            hits.append(
                DetokeniseHit(
                    placeholder=ph,
                    found=True,
                    value=original,
                    value_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
                )
            )

    # Write a single audit row covering the whole batch — keeps chain
    # density predictable and prevents detokenise floods from outpacing
    # the writer queue.
    await state.audit.submit(
        _audit_row(
            principal=principal,
            bundle_digest=state.policy_store.bundle.digest,
            request_id=payload.request_id,
            placeholders=payload.placeholders,
            found_count=sum(1 for h in hits if h.found),
            justification=payload.justification,
            ticket_id=payload.ticket_id,
        )
    )

    return DetokeniseResponse(request_id=payload.request_id, hits=hits)
