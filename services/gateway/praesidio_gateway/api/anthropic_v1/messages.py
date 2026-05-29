"""POST /anthropic/v1/messages — Anthropic-compatible."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ...anonymize.stream import RestoreStream
from ...auth import PrincipalDep
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import (
    PreparedRequest,
    _extract_anthropic_response_text,
    build_audit_row,
    prepare,
    redact_response_body,
    restore_response_text,
    scan_response_text,
)

router = APIRouter(tags=["anthropic"])


def _block_response(prep: PreparedRequest, *, status_code: int = 403) -> Response:
    """Render an Anthropic-shaped block response with Praesidio headers.

    Mirrors the OpenAI block path: emits ``X-Praesidio-Reason`` and
    ``X-Praesidio-Severity`` so SOC tooling has a uniform shape across
    provider routes.
    """
    reason = prep.decision.reason or "blocked by policy"
    severity = prep.decision.severity or "high"
    payload = {
        "type": "error",
        "error": {
            "type": "praesidio_blocked",
            "message": reason,
            "policy_id": prep.decision.policy_id,
            "request_id": prep.request_id,
            "severity": severity,
        },
    }
    return Response(
        content=json.dumps(payload),
        status_code=status_code,
        media_type="application/json",
        headers={
            "x-praesidio-decision": "block",
            "x-praesidio-request-id": prep.request_id,
            "x-praesidio-policy": prep.decision.policy_id or "",
            "X-Praesidio-Reason": reason,
            "X-Praesidio-Severity": severity,
        },
    )


@router.post("/anthropic/v1/messages")
async def anthropic_messages(
    request: Request,
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    request_id = request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/anthropic/v1/messages",
        body=body,
        extract="anthropic",
    )

    # Shadow mode never blocks; the decision is logged but the request flows.
    if prep.decision.action == "block" and not prep.decision.is_shadow:
        await state.audit.submit(
            build_audit_row(prep, upstream="-", response_bytes=0, latency_ms=0)
            | {"route": "/anthropic/v1/messages"}
        )
        return _block_response(prep)

    assert prep.route is not None
    stream = bool(prep.body.get("stream"))
    t0 = time.perf_counter()
    upstream_obj = await prep.route.adapter.chat_completion(
        UpstreamRequest(path="/v1/messages", body=prep.body, stream=stream)
    )

    if stream:
        async def _iter():
            try:
                if prep.anonymise is not None:
                    rs = RestoreStream(upstream_obj, prep.anonymise.reversal)
                    async for chunk in rs:
                        yield chunk
                else:
                    async for chunk in upstream_obj:
                        yield chunk
            finally:
                await state.audit.submit(
                    build_audit_row(
                        prep,
                        upstream=f"{prep.route.provider}/{prep.route.model_id}",
                        response_bytes=0,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    | {"route": "/anthropic/v1/messages"}
                )

        decision_header = (
            f"{prep.decision.action}-shadow"
            if prep.decision.is_shadow
            else prep.decision.action
        )
        return StreamingResponse(
            _iter(),
            media_type="text/event-stream",
            headers={
                "x-praesidio-decision": decision_header,
                "x-praesidio-request-id": prep.request_id,
                "x-praesidio-policy": prep.decision.policy_id or "",
                "x-praesidio-mode": prep.decision.mode,
            },
        )

    assert isinstance(upstream_obj, UpstreamResponse)
    text = upstream_obj.body.decode("utf-8", errors="replace")
    restored = restore_response_text(prep, text)

    # ---- Response-side DLP (Task 2.3) + tool_use input scan (Task 2.5) ----
    response_findings: list[dict[str, Any]] = []
    try:
        parsed = json.loads(restored)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        body_text, tool_args = _extract_anthropic_response_text(parsed)
        for target in [body_text, *tool_args]:
            if target:
                response_findings.extend(
                    await scan_response_text(app_state=state, prep=prep, text=target)
                )
        if response_findings:
            await _redact_anthropic_response_inplace(state, prep, parsed)
            restored = json.dumps(parsed)

    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}",
            response_bytes=len(restored.encode("utf-8")),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            response_text_for_digest=restored,
            response_findings=response_findings,
        )
        | {"route": "/anthropic/v1/messages"}
    )

    decision_header = (
        f"{prep.decision.action}-shadow" if prep.decision.is_shadow else prep.decision.action
    )
    headers = {
        "x-praesidio-decision": decision_header,
        "x-praesidio-request-id": prep.request_id,
        "x-praesidio-policy": prep.decision.policy_id or "",
        "x-praesidio-route": f"{prep.route.provider}/{prep.route.model_id}",
        "x-praesidio-mode": prep.decision.mode,
    }
    if response_findings:
        headers["x-praesidio-response-findings"] = str(len(response_findings))
    return Response(
        content=restored,
        status_code=upstream_obj.status_code,
        media_type="application/json",
        headers=headers,
    )


async def _redact_anthropic_response_inplace(
    state: AppState, prep: PreparedRequest, body: dict[str, Any]
) -> None:
    """Walk an Anthropic ``content[]`` list and redact text and tool_use input."""
    content = body.get("content")
    if not isinstance(content, list):
        return
    new_content = []
    for c in content:
        if not isinstance(c, dict):
            new_content.append(c)
            continue
        t = c.get("type")
        if t == "text":
            txt = c.get("text", "")
            findings = await scan_response_text(app_state=state, prep=prep, text=txt)
            new_content.append({**c, "text": redact_response_body(txt, findings)})
        elif t == "tool_use":
            inp = c.get("input")
            if isinstance(inp, dict):
                rendered = json.dumps(inp)
                findings = await scan_response_text(
                    app_state=state, prep=prep, text=rendered
                )
                if findings:
                    redacted = redact_response_body(rendered, findings)
                    # Try to parse back to dict; on failure keep the redacted string.
                    try:
                        new_input: Any = json.loads(redacted)
                    except Exception:
                        new_input = redacted
                    new_content.append({**c, "input": new_input})
                else:
                    new_content.append(c)
            elif isinstance(inp, str):
                findings = await scan_response_text(app_state=state, prep=prep, text=inp)
                new_content.append({**c, "input": redact_response_body(inp, findings)})
            else:
                new_content.append(c)
        else:
            new_content.append(c)
    body["content"] = new_content
