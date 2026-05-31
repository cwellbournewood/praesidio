"""Tool-call allowlist enforcement (G6).

Applied to the *response* of an LLM proxy call after the upstream
returns. Two evaluation surfaces are supported:

  * OpenAI-style ``choices[].message.tool_calls[]`` with
    ``function.name``.
  * Anthropic-style ``content[]`` items with ``type == "tool_use"`` and
    a ``name`` field.

The enforcement contract::

    decision = enforce_tool_calls(allowlist, tool_names)

returns a :class:`ToolEnforcementResult` carrying the per-name
allow/deny verdict and the set of names that should be stripped.
Callers (the v1/chat and anthropic_messages handlers) walk the parsed
response, remove or rewrite the offending entries, and audit the
violation via :data:`TOOL_CALLS_BLOCKED_TOTAL`.

The logic is deliberately pure-Python and dependency-free so the same
function backs both the runtime path and the :mod:`section_policy`
CLI's static linter.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from ..obs.metrics import TOOL_CALLS_BLOCKED_TOTAL
from .models import ToolAllowlist


@dataclass(slots=True)
class ToolEnforcementResult:
    """Outcome of evaluating a list of tool names against an allowlist."""

    allowed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    # Map of tool name -> reason it was denied (for the audit row).
    deny_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def any_denied(self) -> bool:
        return bool(self.denied)


def _match_any(name: str, patterns: list[str]) -> bool:
    """Glob-aware membership test (case-sensitive)."""
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def enforce_tool_calls(
    allowlist: ToolAllowlist | None,
    tool_names: list[str],
) -> ToolEnforcementResult:
    """Compute the allow/deny verdict for ``tool_names``.

    Rules:
      * If ``allowlist`` is None or empty (default ``allow=["*"]`` and
        empty ``deny``), every name is allowed.
      * ``deny`` patterns are evaluated first. A matching ``deny`` is
        terminal — the tool is rejected with reason
        ``"matches deny pattern '<pattern>'"``.
      * Then ``allow`` is checked. A name not matched by any allow
        pattern is rejected with ``"not in allowlist"``.

    Patterns use POSIX glob semantics (``*``, ``?``, ``[...]``) so an
    operator can write ``allow: ["search_*", "read_*"]``.
    """
    result = ToolEnforcementResult()
    if allowlist is None:
        result.allowed = list(tool_names)
        return result
    allow = allowlist.allow or ["*"]
    deny = allowlist.deny or []
    for name in tool_names:
        # 1) explicit deny wins.
        for pat in deny:
            if fnmatch.fnmatchcase(name, pat):
                result.denied.append(name)
                result.deny_reasons[name] = f"matches deny pattern '{pat}'"
                break
        else:
            # 2) must be on allowlist.
            if _match_any(name, allow):
                result.allowed.append(name)
            else:
                result.denied.append(name)
                result.deny_reasons[name] = "not in allowlist"
    return result


def record_blocks(tenant: str, policy_id: str, denied: list[str]) -> None:
    """Bump the Prometheus counter for each denied tool name.

    Safe to call with an empty list (no-op). Always called after
    :func:`enforce_tool_calls` whether or not the response is rewritten —
    we want the metric to reflect *attempted* invocations.
    """
    for name in denied:
        try:
            TOOL_CALLS_BLOCKED_TOTAL.labels(
                tenant=tenant, policy=policy_id, tool=name
            ).inc()
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Response surgery helpers
# ---------------------------------------------------------------------------


def extract_openai_tool_names(body: dict) -> list[str]:
    """Return the list of tool-call function names invoked in an OpenAI response."""
    names: list[str] = []
    for choice in body.get("choices", []) or []:
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            continue
        for tc in msg.get("tool_calls", []) or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            n = fn.get("name")
            if isinstance(n, str) and n:
                names.append(n)
    return names


def extract_anthropic_tool_names(body: dict) -> list[str]:
    """Return the list of tool_use names invoked in an Anthropic response."""
    names: list[str] = []
    content = body.get("content")
    if not isinstance(content, list):
        return names
    for c in content:
        if isinstance(c, dict) and c.get("type") == "tool_use":
            n = c.get("name")
            if isinstance(n, str) and n:
                names.append(n)
    return names


def redact_openai_tool_calls(body: dict, denied: set[str]) -> int:
    """Strip denied tool_calls from an OpenAI body in place. Returns count removed."""
    if not denied:
        return 0
    removed = 0
    for choice in body.get("choices", []) or []:
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            continue
        tcs = msg.get("tool_calls") or []
        if not tcs:
            continue
        kept = []
        for tc in tcs:
            if not isinstance(tc, dict):
                kept.append(tc)
                continue
            name = (tc.get("function") or {}).get("name")
            if isinstance(name, str) and name in denied:
                removed += 1
                continue
            kept.append(tc)
        msg["tool_calls"] = kept
    return removed


def redact_anthropic_tool_calls(body: dict, denied: set[str]) -> int:
    """Strip denied tool_use blocks from an Anthropic body in place."""
    if not denied:
        return 0
    removed = 0
    content = body.get("content")
    if not isinstance(content, list):
        return 0
    kept = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in denied:
            removed += 1
            continue
        kept.append(c)
    body["content"] = kept
    return removed
