"""Shared per-request pipeline used by every chat-like endpoint.

Encapsulates: extract -> DLP -> policy -> anonymise -> upstream resolve
              -> audit row build. The endpoint module handles the actual
              forwarding (streaming vs buffered) since the response
              transports differ.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..anonymize.tokenizer import AnonymiseResult, ReversalMap, anonymise
from ..auth import Principal
from ..dlp.pipeline import PipelineResult, run_pipeline
from ..obs.metrics import DECISION_TOTAL
from ..policy.engine import evaluate as evaluate_policy
from ..policy.models import (
    Decision,
    DecisionContext,
    ModelRequestCtx,
    PrincipalCtx,
)
from ..proxy.registry import ResolvedRoute
from ..state import AppState


def _extract_text_chat(body: dict[str, Any]) -> str:
    """Concatenate user/system/assistant contents into a single scan string."""
    parts: list[str] = []
    for msg in body.get("messages", []) or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
    return "\n".join(parts)


def _extract_text_anthropic(body: dict[str, Any]) -> str:
    parts: list[str] = []
    sys = body.get("system")
    if isinstance(sys, str):
        parts.append(sys)
    for msg in body.get("messages", []) or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
    return "\n".join(parts)


def _rewrite_chat_with(text: str, body: dict[str, Any]) -> dict[str, Any]:
    """Reverse of _extract_text_chat: put the sanitised text back into messages.

    We replace each string content with the slice of sanitised text that
    corresponds to its position, preserving the conversation shape.
    """
    new_body = dict(body)
    new_msgs: list[dict[str, Any]] = []
    cursor = 0
    sep = "\n"
    msgs = body.get("messages", []) or []
    parts: list[str] = []
    for msg in msgs:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            joined = "\n".join(
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
            parts.append(joined)
        else:
            parts.append("")
    # Walk sanitised text by part length.
    sanitised_parts: list[str] = []
    for p in parts:
        slice_ = text[cursor : cursor + len(p)]
        sanitised_parts.append(slice_)
        cursor += len(p) + len(sep)
    for msg, sp in zip(msgs, sanitised_parts, strict=False):
        if isinstance(msg.get("content"), str):
            new_msgs.append({**msg, "content": sp})
        elif isinstance(msg.get("content"), list):
            new_content = []
            for c in msg["content"]:
                if isinstance(c, dict) and c.get("type") == "text":
                    new_content.append({**c, "text": sp})
                else:
                    new_content.append(c)
            new_msgs.append({**msg, "content": new_content})
        else:
            new_msgs.append(msg)
    new_body["messages"] = new_msgs
    return new_body


@dataclass
class PreparedRequest:
    """Output of `prepare()`. Ready to send upstream."""

    request_id: str
    principal: PrincipalCtx
    decision: Decision
    findings_pub: list[dict[str, Any]]
    pipeline: PipelineResult
    anonymise: AnonymiseResult | None
    body: dict[str, Any]
    text_in: str
    route: ResolvedRoute | None
    bundle_digest: str
    started_at: float = field(default_factory=time.perf_counter)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


async def prepare(
    *,
    app_state: AppState,
    principal: Principal,
    request_id: str,
    inbound_path: str,
    body: dict[str, Any],
    extract: str = "chat",
) -> PreparedRequest:
    """Run DLP + policy + anonymise + route resolution.

    Pure: no upstream call. Returns everything the endpoint needs.
    """
    extractor = _extract_text_chat if extract == "chat" else _extract_text_anthropic
    rewriter = _rewrite_chat_with if extract == "chat" else _rewrite_chat_with  # symmetric

    text_in = extractor(body)
    principal_ctx = PrincipalCtx(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        groups=list(principal.groups),
        country=principal.country,
        device_id=principal.device_id,
        ip=principal.source_ip,
    )
    requested_model = body.get("model")
    ctx = DecisionContext(
        principal=principal_ctx,
        route=inbound_path,
        model_request=ModelRequestCtx(model=requested_model),
        time=datetime.now(UTC),
        request_id=request_id,
    )

    bundle = app_state.policy_store.bundle
    # Discover the policy that applies to find detector set + thresholds.
    enable: list[str] = []
    thresholds: dict[str, float] = {}
    for p in bundle.policies:
        from ..policy.engine import policy_applies as _applies

        if _applies(p, ctx):
            enable.extend(p.spec.detect.enable)
            thresholds.update(p.spec.detect.thresholds)
    pr = await run_pipeline(
        text_in,
        enable=enable or None,
        thresholds=thresholds or None,
        deadline_s=app_state.settings.detector_timeout_seconds,
    )

    decision = evaluate_policy(bundle, ctx, pr.findings)
    DECISION_TOTAL.labels(
        decision=decision.action, policy_id=decision.policy_id or "-", tenant=principal.tenant_id
    ).inc()

    anonymised: AnonymiseResult | None = None
    new_body = body
    # Shadow mode short-circuits transforms and blocks: the decision is logged
    # as-is but the gateway always forwards the original request.
    effective = decision.effective_action
    if effective == "transform" and decision.transforms:
        anonymised = await anonymise(
            text=text_in,
            findings=pr.findings,
            transforms=decision.transforms,
            tenant_id=principal.tenant_id,
            request_id=request_id,
            vault=app_state.vault,
            default_ttl_seconds=app_state.settings.section_vault_ttl_seconds,
        )
        new_body = rewriter(anonymised.sanitised, body)

    # Route resolution — in shadow mode we always resolve a route even if the
    # underlying decision was "block", because we still need to call upstream.
    route: ResolvedRoute | None = None
    if effective != "block":
        route = app_state.providers.resolve(
            inbound_path=inbound_path,
            requested_model=requested_model,
            ctx=ctx,
            upstream_override=decision.upstream_override,
        )
        # Rewrite model id to provider's actual name.
        if route is not None and "model" in new_body:
            new_body = {**new_body, "model": route.model_id}

    findings_pub = [
        {
            "id": f.id, "label": f.label, "detector": f.detector,
            "confidence": round(f.confidence, 3),
            "start": f.start, "end": f.end,
            "text_hash": f.text_hash, "detector_version": f.detector_version,
            "meta": f.meta,
        }
        for f in pr.findings
    ]

    return PreparedRequest(
        request_id=request_id,
        principal=principal_ctx,
        decision=decision,
        findings_pub=findings_pub,
        pipeline=pr,
        anonymise=anonymised,
        body=new_body,
        text_in=text_in,
        route=route,
        bundle_digest=bundle.digest,
    )


def build_audit_row(
    prep: PreparedRequest,
    *,
    upstream: str,
    response_bytes: int,
    latency_ms: int,
    degraded: bool = False,
    response_text_for_digest: str | None = None,
    response_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request_digest = hashlib.sha256(
        (prep.anonymise.sanitised if prep.anonymise else prep.text_in).encode("utf-8")
    ).hexdigest()
    response_digest = (
        hashlib.sha256((response_text_for_digest or "").encode("utf-8")).hexdigest()
        if response_text_for_digest is not None
        else None
    )
    findings_for_audit = list(prep.findings_pub)
    if response_findings:
        findings_for_audit = findings_for_audit + [
            {**f, "phase": "response"} for f in response_findings
        ]
    return {
        "tenant_id": prep.principal.tenant_id,
        "request_id": prep.request_id,
        "occurred_at": prep.occurred_at,
        "principal_id": prep.principal.user_id,
        "principal_groups": list(prep.principal.groups),
        "source_ip": prep.principal.ip,
        "route": "",  # filled by caller
        "upstream": upstream,
        "decision": prep.decision.action,
        "rule_id": prep.decision.policy_id,
        "rule_index": prep.decision.rule_index,
        "policy_id": prep.decision.policy_id,
        "policy_version": prep.decision.policy_version,
        "bundle_digest": prep.bundle_digest,
        "findings": findings_for_audit,
        "transforms": prep.anonymise.applied if prep.anonymise else [],
        "request_digest": request_digest,
        "response_digest": response_digest,
        "latency_ms": latency_ms,
        "bytes_in": len(prep.text_in),
        "bytes_out": response_bytes,
        # Inherit any pipeline-level degradation (open circuit breakers, etc.).
        "degraded": degraded or prep.pipeline.degraded,
        "mode": prep.decision.mode,
        "reason": prep.decision.reason,
        "severity": prep.decision.severity,
    }


def restore_response_text(prep: PreparedRequest, text: str) -> str:
    """Walk a JSON response and replace placeholders with originals."""
    if not prep.anonymise:
        return text
    rev: ReversalMap = prep.anonymise.reversal
    out = text
    for placeholder, original in rev.by_placeholder.items():
        out = out.replace(placeholder, original)
    return out


# ---------------------------------------------------------------------------
# Response-side scanning (Task 2.3) and tool-call argument scanning (Task 2.5)
# ---------------------------------------------------------------------------


def _extract_openai_response_text(body: dict[str, Any]) -> tuple[str, list[str]]:
    """Return ``(joined_text, tool_arg_strings)`` from an OpenAI chat-completion JSON.

    Walks ``choices[].message.content`` plus ``choices[].message.tool_calls[]
    .function.arguments``. Tool arguments are returned as separate strings so
    callers can decide whether to redact them in-place.
    """
    parts: list[str] = []
    tool_args: list[str] = []
    for choice in body.get("choices", []) or []:
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
        for tc in msg.get("tool_calls", []) or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                tool_args.append(args)
            elif isinstance(args, dict):
                # Some SDKs pre-parse JSON arguments.
                import json as _json

                tool_args.append(_json.dumps(args))
    return "\n".join(parts), tool_args


def _extract_anthropic_response_text(body: dict[str, Any]) -> tuple[str, list[str]]:
    """Return ``(joined_text, tool_input_strings)`` from an Anthropic messages
    JSON response.

    Anthropic's response shape is ``content: [{type: "text" | "tool_use", ...}]``.
    """
    parts: list[str] = []
    tool_args: list[str] = []
    content = body.get("content")
    if isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            t = c.get("type")
            if t == "text":
                parts.append(c.get("text", ""))
            elif t == "tool_use":
                inp = c.get("input")
                if isinstance(inp, str):
                    tool_args.append(inp)
                elif isinstance(inp, dict):
                    import json as _json

                    tool_args.append(_json.dumps(inp))
    return "\n".join(parts), tool_args


def _reversed_originals_hashes(prep: PreparedRequest) -> set[str]:
    """Sha256 hashes of values that were anonymised on the request side.

    Used to suppress response-side DLP findings whose text matches a value
    the gateway itself reversed back into the response (legitimate
    round-trip). Without this filter, the response scanner would re-detect
    the user's own email and double-redact it.
    """
    if not prep.anonymise:
        return set()
    hashes: set[str] = set()
    for original in prep.anonymise.reversal.by_placeholder.values():
        hashes.add(hashlib.sha256(original.encode("utf-8")).hexdigest())
    return hashes


def _filter_reversed(
    findings: list[dict[str, Any]], reversed_hashes: set[str]
) -> list[dict[str, Any]]:
    if not reversed_hashes:
        return findings
    return [f for f in findings if f.get("text_hash") not in reversed_hashes]


async def scan_response_text(
    *,
    app_state: AppState,
    prep: PreparedRequest,
    text: str,
) -> list[dict[str, Any]]:
    """Re-run the DLP pipeline on a restored response text.

    Returns the publishable findings list (empty if none). Uses the same
    detector enable set and thresholds derived during request prep.
    """
    enable: list[str] = []
    thresholds: dict[str, float] = {}
    bundle = app_state.policy_store.bundle
    # Recover the per-policy detector config from the bundle (mirrors prep()).
    ctx = DecisionContext(
        principal=prep.principal,
        route=prep.route.endpoint_id if prep.route else "-",
        model_request=ModelRequestCtx(model=None),
        time=datetime.now(UTC),
        request_id=prep.request_id,
    )
    for p in bundle.policies:
        from ..policy.engine import policy_applies as _applies

        if _applies(p, ctx):
            enable.extend(p.spec.detect.enable)
            thresholds.update(p.spec.detect.thresholds)
    pr = await run_pipeline(
        text,
        enable=enable or None,
        thresholds=thresholds or None,
        deadline_s=app_state.settings.detector_timeout_seconds,
    )
    findings = [
        {
            "id": f.id, "label": f.label, "detector": f.detector,
            "confidence": round(f.confidence, 3),
            "start": f.start, "end": f.end,
            "text_hash": f.text_hash, "detector_version": f.detector_version,
            "meta": f.meta,
        }
        for f in pr.findings
    ]
    # Authorised round-trip: drop findings whose value the request itself
    # reversed back into the response.
    return _filter_reversed(findings, _reversed_originals_hashes(prep))


def redact_response_body(
    body_text: str,
    findings: list[dict[str, Any]],
) -> str:
    """Replace each finding span with ``[REDACTED_<LABEL>]`` in ``body_text``.

    Findings carry only spans + label; we resolve the original by indexing
    back into ``body_text``. This is best-effort: if a finding's span no
    longer aligns (because the body was already restored to original PII),
    we fall back to substring replace using the raw text at that span.
    """
    if not findings:
        return body_text
    # Sort descending by start so replacements don't shift later spans.
    sorted_f = sorted(findings, key=lambda f: -int(f.get("start", 0)))
    out = body_text
    for f in sorted_f:
        s = int(f.get("start", 0))
        e = int(f.get("end", 0))
        if 0 <= s < e <= len(out):
            label = str(f.get("label", "PII")).split(".", 1)[-1].upper()
            replacement = f"[REDACTED_{label}]"
            out = out[:s] + replacement + out[e:]
    return out
