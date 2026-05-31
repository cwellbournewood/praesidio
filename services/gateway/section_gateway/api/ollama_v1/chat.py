"""Ollama-compatible inbound chat endpoint (``POST /api/chat``).

Ollama's request shape is similar to OpenAI's chat completion (messages
with role + content), but the route is unprefixed ``/api/chat``. We reuse
the chat extractor + orchestrator and hand the request to the Ollama
adapter (or whatever the policy routes the model to).
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth import PrincipalDep
from ...obs.metrics import UPSTREAM_LATENCY
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import build_audit_row, prepare, restore_response_text

router = APIRouter(tags=["ollama"])


@router.post("/api/chat")
async def ollama_chat(
    request: Request,
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    """Ollama-compatible chat endpoint.

    Accepts ``{model, messages, stream?}`` and proxies to the adapter
    resolved by the bundled routes/models config. DLP, policy and audit
    behave identically to the OpenAI surface.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    request_id = request.headers.get("x-request-id") or request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/api/chat",
        body=body,
        extract="chat",
    )

    if prep.decision.action == "block" and not prep.decision.is_shadow:
        await state.audit.submit(
            build_audit_row(prep, upstream="-", response_bytes=0, latency_ms=0)
            | {"route": "/api/chat"}
        )
        reason = prep.decision.reason or "blocked by policy"
        severity = prep.decision.severity or "high"
        return Response(
            content=json.dumps(
                {
                    "error": "section_blocked",
                    "message": reason,
                    "policy_id": prep.decision.policy_id,
                }
            ),
            status_code=403,
            media_type="application/json",
            headers={
                "x-section-decision": "block",
                "x-section-request-id": prep.request_id,
                "X-Section-Reason": reason,
                "X-Section-Severity": severity,
            },
        )

    assert prep.route is not None
    t0 = time.perf_counter()
    upstream_obj = await prep.route.adapter.chat_completion(
        UpstreamRequest(path="/api/chat", body=prep.body, stream=False)
    )
    assert isinstance(upstream_obj, UpstreamResponse)
    UPSTREAM_LATENCY.labels(provider=prep.route.provider, model=prep.route.model_id).observe(
        time.perf_counter() - t0
    )
    text = upstream_obj.body.decode("utf-8", errors="replace")
    restored = restore_response_text(prep, text)
    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}",
            response_bytes=len(restored.encode("utf-8")),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            response_text_for_digest=restored,
        )
        | {"route": "/api/chat"}
    )
    return Response(
        content=restored,
        status_code=upstream_obj.status_code,
        media_type="application/json",
        headers={
            "x-section-decision": prep.decision.action,
            "x-section-request-id": prep.request_id,
            "x-section-mode": prep.decision.mode,
        },
    )
