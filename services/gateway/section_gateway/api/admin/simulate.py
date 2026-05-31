"""POST /admin/simulate — what-if policy evaluation (Task 4.2).

Runs DLP + policy evaluation against a supplied request body **without**
calling any upstream provider and **without** writing an audit row. The
intent is policy authoring & CI: give me a body and tell me what the
gateway *would* do.

Returns the synthetic decision (action, mode, reason, severity, matched
policy/rule), the publishable findings, the planned transforms, and a
``would_block_reason`` field that mirrors the user-facing block message
when ``action == "block"``.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...auth import Principal, require_admin
from ...state import AppState, get_state
from ..orchestrator import prepare

router = APIRouter(prefix="/admin", tags=["admin"])


class SimulateRequest(BaseModel):
    """Payload for `/admin/simulate`."""

    body: dict[str, Any] = Field(
        ...,
        description="The chat-completion / messages JSON to evaluate against the bundle.",
    )
    extract: Literal["chat", "anthropic"] = Field(
        "chat", description="Which extractor to use when scanning the body."
    )
    inbound_path: str = Field(
        "/v1/chat/completions",
        description="Inbound route used for policy `where` matching.",
    )


class SimulateResponse(BaseModel):
    decision: dict[str, Any]
    findings: list[dict[str, Any]]
    transforms: list[dict[str, Any]]
    matched_rule: dict[str, Any] | None
    would_block_reason: str | None
    bundle_digest: str


@router.post("/simulate", response_model=SimulateResponse)
async def simulate(
    payload: SimulateRequest,
    principal: Principal = Depends(require_admin),
    state: AppState = Depends(get_state),
) -> SimulateResponse:
    """Evaluate ``payload.body`` against the active bundle without side-effects.

    No upstream call is made. No audit row is written. No vault writes are
    issued (transforms are *described*, not applied). Useful for policy
    authors / CI guards.
    """
    try:
        prep = await prepare(
            app_state=state,
            principal=principal,
            request_id=f"simulate-{principal.user_id}",
            inbound_path=payload.inbound_path,
            body=payload.body,
            extract=payload.extract,
        )
    except Exception as exc:  # surface evaluation bugs to the operator
        raise HTTPException(500, f"simulate failed: {exc.__class__.__name__}") from exc

    d = prep.decision
    matched_rule = None
    if d.policy_id and d.rule_index is not None:
        matched_rule = {
            "policy_id": d.policy_id,
            "policy_version": d.policy_version,
            "rule_index": d.rule_index,
        }
    would_block = (
        d.reason or "blocked by policy" if d.action == "block" else None
    )
    return SimulateResponse(
        decision={
            "action": d.action,
            "mode": d.mode,
            "effective_action": d.effective_action,
            "is_shadow": d.is_shadow,
            "reason": d.reason,
            "severity": d.severity,
            "policy_id": d.policy_id,
            "policy_version": d.policy_version,
            "rule_index": d.rule_index,
            "upstream_override": d.upstream_override,
        },
        findings=prep.findings_pub,
        transforms=[
            {"label": t.label, "method": t.method, "scope": t.scope, "ttl": t.ttl}
            for t in (d.transforms or [])
        ],
        matched_rule=matched_rule,
        would_block_reason=would_block,
        bundle_digest=prep.bundle_digest,
    )
