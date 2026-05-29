"""POST /v1/completions — legacy OpenAI text completion (non-chat)."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth import PrincipalDep
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import build_audit_row, prepare, restore_response_text

router = APIRouter(tags=["openai"])


@router.post("/v1/completions")
async def completions(
    request: Request,
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    # /v1/completions uses `prompt` (str | list[str]). Wrap into a synthetic
    # messages list so we can reuse the chat extractor and rewriter.
    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt = "\n".join(str(p) for p in prompt)
    synthetic = {"messages": [{"role": "user", "content": prompt}], **body}

    request_id = request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/v1/completions",
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
            headers={"x-praesidio-decision": "block"},
        )

    # Re-extract the sanitised prompt back out of the synthetic shape.
    sanitised_prompt = prep.body["messages"][0]["content"]
    out_body = {**body, "prompt": sanitised_prompt}
    if prep.route is not None and "model" in out_body:
        out_body["model"] = prep.route.model_id

    assert prep.route is not None
    t0 = time.perf_counter()
    upstream_obj = await prep.route.adapter.chat_completion(
        UpstreamRequest(path="/completions", body=out_body, stream=False)
    )
    assert isinstance(upstream_obj, UpstreamResponse)
    text = upstream_obj.body.decode("utf-8", errors="replace")
    restored = restore_response_text(prep, text)
    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}",
            response_bytes=len(restored),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            response_text_for_digest=restored,
        )
        | {"route": "/v1/completions"}
    )
    return Response(content=restored, status_code=upstream_obj.status_code, media_type="application/json")
