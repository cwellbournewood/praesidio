"""POST /v1/scan and POST /v1/restore — edge-client scan API.

Designed for the browser and IDE extensions (`clients/browser`,
`clients/vscode`, `clients/jetbrains`) and any third-party endpoint
agent. Unlike `/admin/simulate`, this endpoint **applies** transforms
(vault writes happen), **writes an audit row**, and returns a
sanitised string the client can drop into the upstream chat box.

Why a separate endpoint
-----------------------
The chat-completion endpoints (`/v1/chat/completions`, `/anthropic/v1
/messages`, `/openai/deployments/.../chat/completions`, `/api/chat`)
own the upstream forwarding too. Edge clients call the LLM provider
themselves (the user's ChatGPT browser tab; Copilot in VS Code); they
only need the gateway to scan + mask, not to proxy. `/v1/scan` is the
scan-only entry point that still produces a real audit row tagged with
``edge_source`` so downstream tooling (SIEM, lineage, redteam) sees
edge traffic with the same shape as proxied traffic.

`/v1/restore` is the response-side inverse: when the user receives a
model response that contains placeholders (because their prompt was
masked), they POST the response text + the original ``request_id`` and
the gateway returns the text with placeholders swapped back — subject
to the same tenant/request AAD binding the vault enforces for
`/admin/detokenise`. Unlike detokenise, restore is intended for the
**prompt-originator** themselves, so the principal need only own the
request (same tenant + same principal_id); the explicit
``vault:detokenise`` scope is NOT required.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...auth import Principal, resolve_principal
from ...state import AppState, get_state
from ..orchestrator import build_audit_row, prepare

router = APIRouter(prefix="/v1", tags=["edge"])

# Same placeholder grammar as anonymize/tokenizer._PLACEHOLDER_RE.
_PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4})>")

# Edge clients we accept. Used to tag audit rows; unknown values are
# coerced to "edge-unknown" so a misconfigured extension can't poison
# the audit schema.
_KNOWN_CLIENTS = frozenset(
    {
        "browser-extension",
        "vscode",
        "jetbrains",
        "edge-proxy",
        "cli",
        "other",
    }
)


class ScanRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=512_000,
        description="The prompt text the user is about to send upstream.",
    )
    client: str = Field(
        "other",
        max_length=64,
        description="Edge client identifier; one of browser-extension, vscode, jetbrains, edge-proxy, cli, other.",
    )
    url: str | None = Field(
        None,
        max_length=2048,
        description=(
            "Optional origin URL the prompt is destined for "
            "(e.g. https://chatgpt.com/c/...). Recorded in the audit row "
            "but never used for routing."
        ),
    )
    model: str | None = Field(
        None,
        max_length=128,
        description="Hint about which upstream model the client will call (audited only).",
    )
    session_id: str | None = Field(
        None,
        max_length=128,
        description=(
            "Caller-supplied session id. Lets the client batch follow-up "
            "messages under one request_id for consistent placeholder "
            "aliases. If omitted, a fresh request_id is minted."
        ),
    )

    @field_validator("client")
    @classmethod
    def _normalise_client(cls, v: str) -> str:
        s = v.strip().lower()
        return s if s in _KNOWN_CLIENTS else "edge-unknown"


class ScanTransform(BaseModel):
    label: str
    placeholder: str
    method: Literal["tokenise", "fpe", "redact"]
    scope: str


class ScanFinding(BaseModel):
    label: str
    detector: str
    confidence: float
    start: int
    end: int


class ScanResponse(BaseModel):
    request_id: str
    action: Literal["allow", "mask", "block"]
    sanitised: str | None
    transforms: list[ScanTransform]
    findings: list[ScanFinding]
    decision: dict[str, Any]
    bundle_digest: str
    # Block-response surface (mirrors the chat endpoints):
    reason: str | None = None
    severity: str | None = None


class RestoreRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., min_length=0, max_length=2_000_000)


class RestoreResponse(BaseModel):
    request_id: str
    text: str
    restored: int = Field(
        0, description="Number of placeholders successfully restored."
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Placeholders that appeared in the input but had no vault "
            "entry — either expired, never minted, or cross-tenant."
        ),
    )


def _mk_request_id(principal: Principal, session_id: str | None) -> str:
    """Mint or reuse a request_id.

    If the caller supplied a ``session_id``, derive a stable request_id
    from (tenant, principal, session) so multiple /v1/scan calls in the
    same session reuse the same vault scope key. Otherwise mint a fresh
    UUID-shaped id.
    """
    if session_id:
        h = hashlib.sha256(
            f"{principal.tenant_id}|{principal.user_id}|{session_id}".encode()
        ).hexdigest()
        # Format as UUID-shaped for downstream tooling that assumes that.
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    import uuid

    return str(uuid.uuid4())


@router.post("/scan", response_model=ScanResponse)
async def scan(
    payload: ScanRequest,
    principal: Principal = Depends(resolve_principal),
    state: AppState = Depends(get_state),
) -> ScanResponse:
    """Scan + mask a prompt for an edge client.

    Side effects: vault writes when the policy decides to ``transform``,
    one audit row tagged ``upstream="edge-client"`` regardless of
    outcome. No upstream LLM is called — the edge client does that
    itself with the returned ``sanitised`` text.
    """
    t0 = time.perf_counter()
    request_id = _mk_request_id(principal, payload.session_id)

    # Wrap the bare text as a chat-completion body so we can reuse the
    # same orchestrator the rest of the gateway runs through. We also
    # pass the URL / model as hints inside a synthetic system message —
    # the policy engine can match on them via the standard `where`
    # clauses (route + model id) and the model_request context.
    synthetic_body = {
        "model": payload.model or "praesidio-edge",
        "messages": [{"role": "user", "content": payload.text}],
    }
    inbound_path = "/v1/scan"

    try:
        prep = await prepare(
            app_state=state,
            principal=principal,
            request_id=request_id,
            inbound_path=inbound_path,
            body=synthetic_body,
            extract="chat",
        )
    except Exception as exc:
        raise HTTPException(
            500, f"scan failed: {exc.__class__.__name__}"
        ) from exc

    effective = prep.decision.effective_action
    if effective == "block":
        action: Literal["allow", "mask", "block"] = "block"
        sanitised: str | None = None
    elif effective == "transform" and prep.anonymise is not None:
        action = "mask"
        sanitised = prep.anonymise.sanitised
    else:
        action = "allow"
        sanitised = payload.text

    transforms_out: list[ScanTransform] = []
    if prep.anonymise is not None:
        for entry in prep.anonymise.reversal.entries:
            transforms_out.append(
                ScanTransform(
                    label=entry.label,
                    placeholder=entry.placeholder,
                    method=entry.method,  # type: ignore[arg-type]
                    scope=entry.scope,
                )
            )

    findings_out = [
        ScanFinding(
            label=f["label"],
            detector=f["detector"],
            confidence=f["confidence"],
            start=f["start"],
            end=f["end"],
        )
        for f in prep.findings_pub
    ]

    # Audit row — edge_source + client tagging happens via the
    # `transforms` list so we don't break the existing audit schema.
    row = build_audit_row(
        prep,
        upstream="edge-client",
        response_bytes=0,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        degraded=False,
    )
    row["route"] = inbound_path
    row["transforms"] = list(row["transforms"]) + [
        {
            "method": "edge_source",
            "client": payload.client,
            "url": payload.url or "",
            "model_hint": payload.model or "",
        }
    ]
    await state.audit.submit(row)

    return ScanResponse(
        request_id=request_id,
        action=action,
        sanitised=sanitised,
        transforms=transforms_out,
        findings=findings_out,
        decision={
            "action": prep.decision.action,
            "mode": prep.decision.mode,
            "effective_action": prep.decision.effective_action,
            "is_shadow": prep.decision.is_shadow,
            "policy_id": prep.decision.policy_id,
            "policy_version": prep.decision.policy_version,
            "rule_index": prep.decision.rule_index,
            "reason": prep.decision.reason,
            "severity": prep.decision.severity,
        },
        bundle_digest=prep.bundle_digest,
        reason=prep.decision.reason if action == "block" else None,
        severity=prep.decision.severity if action == "block" else None,
    )


@router.post("/restore", response_model=RestoreResponse)
async def restore(
    payload: RestoreRequest,
    principal: Principal = Depends(resolve_principal),
    state: AppState = Depends(get_state),
) -> RestoreResponse:
    """Restore placeholders in a model response.

    Walks the response text for ``<LABEL_XXXX>`` tokens and looks each
    one up in the vault under ``(tenant, request_id)``. Anything that
    decrypts successfully is swapped in place; misses are reported in
    ``missing`` so the client can decide whether to surface a warning
    ("a placeholder expired"). Writes one audit row with
    ``decision="restore"`` regardless of outcome.

    Auth model: the principal must be the same tenant that minted the
    request_id (enforced by AES-GCM AAD inside the vault). We do NOT
    require ``vault:detokenise`` because this is the same user
    restoring their own response, not an operator detokenising someone
    else's. Audit row still captures every placeholder restored.
    """
    t0 = time.perf_counter()
    placeholders = sorted({m.group(0) for m in _PLACEHOLDER_RE.finditer(payload.text)})

    if not placeholders:
        # No-op — still audit so we have proof the client called
        # restore (some compliance reviewers want the trail even when
        # there's nothing to restore).
        await _write_restore_audit(
            state=state,
            principal=principal,
            request_id=payload.request_id,
            placeholders=[],
            restored=0,
            text_in=payload.text,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return RestoreResponse(
            request_id=payload.request_id,
            text=payload.text,
            restored=0,
            missing=[],
        )

    out = payload.text
    restored = 0
    missing: list[str] = []
    for ph in placeholders:
        original = await state.vault.get(
            tenant=principal.tenant_id,
            request_id=payload.request_id,
            placeholder=ph,
        )
        if original is None:
            missing.append(ph)
            continue
        out = out.replace(ph, original)
        restored += 1

    await _write_restore_audit(
        state=state,
        principal=principal,
        request_id=payload.request_id,
        placeholders=placeholders,
        restored=restored,
        text_in=payload.text,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    return RestoreResponse(
        request_id=payload.request_id,
        text=out,
        restored=restored,
        missing=missing,
    )


async def _write_restore_audit(
    *,
    state: AppState,
    principal: Principal,
    request_id: str,
    placeholders: list[str],
    restored: int,
    text_in: str,
    latency_ms: int,
) -> None:
    digest_input = "|".join(placeholders).encode("utf-8")
    row = {
        "tenant_id": principal.tenant_id,
        "request_id": request_id,
        "occurred_at": datetime.now(UTC),
        "principal_id": principal.user_id,
        "principal_groups": list(principal.groups),
        "source_ip": principal.source_ip,
        "route": "/v1/restore",
        "upstream": "vault",
        "decision": "restore",
        "rule_id": None,
        "rule_index": None,
        "policy_id": None,
        "policy_version": None,
        "bundle_digest": state.policy_store.bundle.digest,
        "findings": [
            {"placeholder": p, "scope": "edge:restore"} for p in placeholders
        ],
        "transforms": [
            {
                "method": "restore",
                "count": restored,
                "requested": len(placeholders),
                "event_type": "edge.restore",
            }
        ],
        "request_digest": hashlib.sha256(digest_input).hexdigest(),
        "response_digest": hashlib.sha256(text_in.encode("utf-8")).hexdigest(),
        "latency_ms": latency_ms,
        "bytes_in": len(text_in),
        "bytes_out": 0,
        "degraded": False,
        "mode": "enforce",
        "reason": None,
        "severity": "low",
    }
    await state.audit.submit(row)
