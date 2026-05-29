"""Inbound Azure-OpenAI chat-completion endpoint.

Mirrors Azure's path shape: ``POST /openai/deployments/{deployment}/chat/completions``.
The ``deployment`` becomes the body's ``model`` so the orchestrator and the
provider registry can resolve a route consistently with the OpenAI path.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from ...auth import PrincipalDep
from ...obs.metrics import UPSTREAM_LATENCY
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import build_audit_row, prepare, restore_response_text

router = APIRouter(tags=["azure-openai"])


@router.post("/openai/deployments/{deployment}/chat/completions")
async def azure_chat_completions(
    request: Request,
    principal: PrincipalDep,
    deployment: str = Path(..., min_length=1, description="Azure deployment name"),
    api_version: str | None = Query(None, alias="api-version"),
    state: AppState = Depends(get_state),
):
    """Azure-OpenAI compatible chat-completion proxy.

    The ``deployment`` path segment is folded into the body's ``model`` so the
    rest of the pipeline behaves identically to ``/v1/chat/completions``.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    # Use the deployment name as the requested model so route resolution can
    # match on it. Operators may override via routes.yaml ``requested_model``.
    body.setdefault("model", deployment)

    request_id = request.headers.get("x-request-id") or request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/openai/deployments/chat/completions",
        body=body,
        extract="chat",
    )

    if prep.decision.action == "block" and not prep.decision.is_shadow:
        await state.audit.submit(
            build_audit_row(prep, upstream="-", response_bytes=0, latency_ms=0)
            | {"route": f"/openai/deployments/{deployment}/chat/completions"}
        )
        return _block(prep)

    assert prep.route is not None
    out_body: dict[str, Any] = dict(prep.body)
    if api_version:
        out_body.setdefault("api-version", api_version)
    t0 = time.perf_counter()
    upstream_obj = await prep.route.adapter.chat_completion(
        UpstreamRequest(path="/chat/completions", body=out_body, stream=False)
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
        | {"route": f"/openai/deployments/{deployment}/chat/completions"}
    )
    return Response(
        content=restored,
        status_code=upstream_obj.status_code,
        media_type="application/json",
        headers={
            "x-praesidio-decision": prep.decision.action,
            "x-praesidio-request-id": prep.request_id,
            "x-praesidio-mode": prep.decision.mode,
        },
    )


def _block(prep) -> Response:
    reason = prep.decision.reason or "blocked by policy"
    severity = prep.decision.severity or "high"
    return Response(
        content=json.dumps(
            {
                "error": {
                    "code": "praesidio_blocked",
                    "message": reason,
                    "policy_id": prep.decision.policy_id,
                    "severity": severity,
                }
            }
        ),
        status_code=403,
        media_type="application/json",
        headers={
            "x-praesidio-decision": "block",
            "x-praesidio-request-id": prep.request_id,
            "X-Praesidio-Reason": reason,
            "X-Praesidio-Severity": severity,
        },
    )
