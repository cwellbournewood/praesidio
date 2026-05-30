"""POST /v1/chat/completions — OpenAI-compatible."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ...anonymize.stream import RestoreStream
from ...auth import PrincipalDep
from ...obs.metering import record_usage_from_payload
from ...obs.metrics import UPSTREAM_LATENCY
from ...policy.tool_calls import (
    enforce_tool_calls,
    extract_openai_tool_names,
    record_blocks,
    redact_openai_tool_calls,
)
from ...proxy.base import UpstreamRequest, UpstreamResponse
from ...state import AppState, get_state
from ..orchestrator import (
    PreparedRequest,
    _extract_openai_response_text,
    build_audit_row,
    prepare,
    redact_response_body,
    restore_response_text,
    scan_response_text,
)

router = APIRouter(tags=["openai"])


def _block_response(prep: PreparedRequest, *, status_code: int = 403) -> Response:
    """Render a Section block response with reason/severity headers.

    Headers always populated:
      x-section-decision: "block"
      x-section-request-id: <request id>
      x-section-policy: <matched policy id or "">
      X-Section-Reason: <human-readable reason or "blocked by policy">
      X-Section-Severity: <severity from rule or "high">
    """
    reason = prep.decision.reason or "blocked by policy"
    severity = prep.decision.severity or "high"
    payload = {
        "error": {
            "type": "section_blocked",
            "message": reason,
            "policy_id": prep.decision.policy_id,
            "request_id": prep.request_id,
            "severity": severity,
        }
    }
    return Response(
        content=json.dumps(payload),
        status_code=status_code,
        media_type="application/json",
        headers={
            "x-section-decision": "block",
            "x-section-request-id": prep.request_id,
            "x-section-policy": prep.decision.policy_id or "",
            "X-Section-Reason": reason,
            "X-Section-Severity": severity,
        },
    )


def _is_stream_request(body: dict[str, Any]) -> bool:
    return bool(body.get("stream"))


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "invalid json body") from exc

    request_id = request.headers.get("x-request-id") or request.state.request_id
    prep = await prepare(
        app_state=state,
        principal=principal,
        request_id=request_id,
        inbound_path="/v1/chat/completions",
        body=body,
        extract="chat",
    )

    if prep.decision.action == "block" and not prep.decision.is_shadow:
        # Write audit row even for blocks.
        await state.audit.submit(
            build_audit_row(prep, upstream="-", response_bytes=0, latency_ms=0)
            | {"route": "/v1/chat/completions"}
        )
        return _block_response(prep)

    assert prep.route is not None
    stream = _is_stream_request(prep.body)
    upstream_req = UpstreamRequest(
        path="/chat/completions",
        body=prep.body,
        stream=stream,
        headers=dict(request.headers),
    )

    t0 = time.perf_counter()
    try:
        upstream_obj = await prep.route.adapter.chat_completion(upstream_req)
    except Exception as exc:
        return await _handle_upstream_failure(state, prep, exc)

    if stream:
        return _streaming(state, prep, upstream_obj, t0)
    assert isinstance(upstream_obj, UpstreamResponse)
    UPSTREAM_LATENCY.labels(provider=prep.route.provider, model=prep.route.model_id).observe(
        time.perf_counter() - t0
    )
    text = upstream_obj.body.decode("utf-8", errors="replace")
    restored = restore_response_text(prep, text)

    # ---- Response-side DLP (Task 2.3) + tool-call argument scan (Task 2.5) ----
    response_findings: list[dict[str, Any]] = []
    try:
        parsed = json.loads(restored)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        # G5: token / cost metering off the upstream's usage block.
        try:
            record_usage_from_payload(
                tenant=prep.principal.tenant_id,
                model=prep.route.model_id,
                route="/v1/chat/completions",
                payload=parsed,
            )
        except Exception:  # pragma: no cover - metering is best-effort
            pass
        # G6: tool-call allowlist. If the matched policy carries one,
        # strip any tool_calls whose function.name is not allowed.
        allowlist = None
        pid = prep.decision.policy_id
        if pid:
            for _pol in state.policy_store.bundle.policies:
                if _pol.metadata.id == pid:
                    allowlist = _pol.spec.tool_allowlist
                    break
        if allowlist is not None:
            invoked = extract_openai_tool_names(parsed)
            if invoked:
                verdict = enforce_tool_calls(allowlist, invoked)
                if verdict.any_denied:
                    record_blocks(
                        tenant=prep.principal.tenant_id,
                        policy_id=prep.decision.policy_id or "unknown",
                        denied=verdict.denied,
                    )
                    redact_openai_tool_calls(parsed, set(verdict.denied))
        body_text, tool_args = _extract_openai_response_text(parsed)
        scan_targets = [body_text, *tool_args]
        for target in scan_targets:
            if target:
                response_findings.extend(
                    await scan_response_text(app_state=state, prep=prep, text=target)
                )
        # If we found anything, rewrite the response body (in-place redact text
        # spans on text blocks AND on tool-call argument strings).
        if response_findings:
            await _redact_openai_response_inplace(state, prep, parsed)
            restored = json.dumps(parsed)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}",
            response_bytes=len(restored.encode("utf-8")),
            latency_ms=latency_ms,
            response_text_for_digest=restored,
            response_findings=response_findings,
        )
        | {"route": "/v1/chat/completions"}
    )

    # Decision header is informational in shadow mode; the response itself is
    # always the (possibly-redacted) upstream output.
    decision_header = (
        f"{prep.decision.action}-shadow" if prep.decision.is_shadow else prep.decision.action
    )
    headers = {
        "x-section-decision": decision_header,
        "x-section-policy": prep.decision.policy_id or "",
        "x-section-request-id": prep.request_id,
        "x-section-route": f"{prep.route.provider}/{prep.route.model_id}",
        "x-section-mode": prep.decision.mode,
    }
    if response_findings:
        headers["x-section-response-findings"] = str(len(response_findings))
    return Response(
        content=restored,
        status_code=upstream_obj.status_code,
        media_type="application/json",
        headers=headers,
    )


async def _redact_openai_response_inplace(
    state: AppState, prep: PreparedRequest, body: dict[str, Any]
) -> None:
    """Re-scan each message content / tool_call argument and replace findings
    with ``[REDACTED_<LABEL>]`` markers.

    This mutates ``body`` in place so the caller can re-serialise it.
    """
    for choice in body.get("choices", []) or []:
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            findings = await scan_response_text(app_state=state, prep=prep, text=content)
            if findings:
                msg["content"] = redact_response_body(content, findings)
        elif isinstance(content, list):
            new_content = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    t = c.get("text", "")
                    findings = await scan_response_text(app_state=state, prep=prep, text=t)
                    new_content.append({**c, "text": redact_response_body(t, findings)})
                else:
                    new_content.append(c)
            msg["content"] = new_content
        for tc in msg.get("tool_calls", []) or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str) and args:
                findings = await scan_response_text(app_state=state, prep=prep, text=args)
                if findings:
                    fn["arguments"] = redact_response_body(args, findings)
            elif isinstance(args, dict):
                rendered = json.dumps(args)
                findings = await scan_response_text(app_state=state, prep=prep, text=rendered)
                if findings:
                    fn["arguments"] = redact_response_body(rendered, findings)


def _streaming(
    state: AppState,
    prep: PreparedRequest,
    upstream_iter: AsyncIterator[bytes],
    t0: float,
):
    async def _iter() -> AsyncIterator[bytes]:
        try:
            if prep.anonymise is not None:
                rs = RestoreStream(upstream_iter, prep.anonymise.reversal)
                bytes_out = 0
                async for chunk in rs:
                    bytes_out += len(chunk)
                    yield chunk
            else:
                bytes_out = 0
                async for chunk in upstream_iter:
                    bytes_out += len(chunk)
                    yield chunk
        finally:
            assert prep.route is not None
            UPSTREAM_LATENCY.labels(
                provider=prep.route.provider, model=prep.route.model_id
            ).observe(time.perf_counter() - t0)
            await state.audit.submit(
                build_audit_row(
                    prep,
                    upstream=f"{prep.route.provider}/{prep.route.model_id}",
                    response_bytes=bytes_out,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                )
                | {"route": "/v1/chat/completions"}
            )

    headers = {
        "x-section-decision": prep.decision.action,
        "x-section-policy": prep.decision.policy_id or "",
        "x-section-request-id": prep.request_id,
        "cache-control": "no-cache",
    }
    return StreamingResponse(_iter(), media_type="text/event-stream", headers=headers)


async def _handle_upstream_failure(state: AppState, prep: PreparedRequest, exc: Exception):
    fail_mode = prep.decision.fail_mode
    await state.audit.submit(
        build_audit_row(
            prep,
            upstream=f"{prep.route.provider}/{prep.route.model_id}" if prep.route else "-",
            response_bytes=0,
            latency_ms=0,
            degraded=True,
        )
        | {"route": "/v1/chat/completions", "reason": f"upstream_error: {exc.__class__.__name__}"}
    )
    if fail_mode == "open":
        return Response(
            content=json.dumps({"error": {"type": "section_degraded", "message": str(exc)}}),
            status_code=502,
            media_type="application/json",
            headers={"x-section-reason": "section_degraded"},
        )
    return Response(
        content=json.dumps({"error": {"type": "section_unavailable", "message": str(exc)}}),
        status_code=503,
        media_type="application/json",
        headers={"x-section-reason": "section_unavailable"},
    )
