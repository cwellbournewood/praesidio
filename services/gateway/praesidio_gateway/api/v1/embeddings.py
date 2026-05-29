"""POST /v1/embeddings — pass through with optional DLP scan of input."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth import PrincipalDep
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import build_audit_row, prepare

router = APIRouter(tags=["openai"])


@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    inp = body.get("input", "")
    if isinstance(inp, list):
        joined = "\n".join(str(x) for x in inp)
    else:
        joined = str(inp)
    synthetic = {"messages": [{"role": "user", "content": joined}], **body}

    request_id = request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/v1/embeddings",
        body=synthetic,
        extract="chat",
    )

    if prep.decision.action == "block":
        return Response(
            content=json.dumps(
                {"error": {"type": "praesidio_blocked", "message": prep.decision.reason}}
            ),
            status_code=403,
            media_type="application/json",
        )

    sanitised = prep.body["messages"][0]["content"]
    out_body = {**body, "input": sanitised}
    assert prep.route is not None
    t0 = time.perf_counter()
    upstream_obj = await prep.route.adapter.chat_completion(
        UpstreamRequest(path="/embeddings", body=out_body, stream=False)
    )
    assert isinstance(upstream_obj, UpstreamResponse)
    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}",
            response_bytes=len(upstream_obj.body),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        | {"route": "/v1/embeddings"}
    )
    return Response(content=upstream_obj.body, status_code=upstream_obj.status_code, media_type="application/json")
