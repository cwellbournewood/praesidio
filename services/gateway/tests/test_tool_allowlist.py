"""Tool-call allowlist enforcement (G6).

Covers:
  * Allow-all (default) lets every tool through.
  * Explicit allow with no deny enforces a strict whitelist.
  * Deny pattern wins over allow.
  * Glob patterns work (``search_*``, ``read_*``).
  * OpenAI and Anthropic response shapes are both stripped correctly.
  * The Prometheus counter increments per denied tool name.
"""
from __future__ import annotations

import copy

from section_gateway.obs.metrics import TOOL_CALLS_BLOCKED_TOTAL
from section_gateway.policy.models import ToolAllowlist
from section_gateway.policy.tool_calls import (
    enforce_tool_calls,
    extract_anthropic_tool_names,
    extract_openai_tool_names,
    record_blocks,
    redact_anthropic_tool_calls,
    redact_openai_tool_calls,
)


def _counter_value(tool: str, tenant: str = "tA", policy: str = "p1") -> float:
    for fam in TOOL_CALLS_BLOCKED_TOTAL.collect():
        for s in fam.samples:
            if (
                s.name.endswith("_total")
                and s.labels.get("tenant") == tenant
                and s.labels.get("policy") == policy
                and s.labels.get("tool") == tool
            ):
                return s.value
    return 0.0


def test_no_allowlist_allows_everything() -> None:
    r = enforce_tool_calls(None, ["weather", "delete_db", "exec_shell"])
    assert r.allowed == ["weather", "delete_db", "exec_shell"]
    assert r.denied == []


def test_strict_whitelist_blocks_unknown() -> None:
    al = ToolAllowlist(allow=["search_docs", "read_file"], deny=[])
    r = enforce_tool_calls(al, ["search_docs", "read_file", "delete_db"])
    assert r.allowed == ["search_docs", "read_file"]
    assert r.denied == ["delete_db"]
    assert r.deny_reasons["delete_db"] == "not in allowlist"


def test_deny_overrides_allow() -> None:
    al = ToolAllowlist(allow=["*"], deny=["exec_*", "delete_*"])
    r = enforce_tool_calls(al, ["read_file", "exec_shell", "delete_db", "search"])
    assert sorted(r.allowed) == ["read_file", "search"]
    assert sorted(r.denied) == ["delete_db", "exec_shell"]
    assert "exec_*" in r.deny_reasons["exec_shell"]
    assert "delete_*" in r.deny_reasons["delete_db"]


def test_glob_patterns_match() -> None:
    al = ToolAllowlist(allow=["read_*", "search_*"], deny=[])
    r = enforce_tool_calls(al, ["read_file", "read_url", "search_web", "write_file"])
    assert r.denied == ["write_file"]


def test_openai_response_redaction_strips_denied_tool_calls() -> None:
    body = {
        "choices": [
            {
                "message": {
                    "content": "I'll do that.",
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "search_docs", "arguments": "{}"},
                        },
                        {
                            "id": "2",
                            "type": "function",
                            "function": {"name": "exec_shell", "arguments": "{}"},
                        },
                    ],
                }
            }
        ]
    }
    names = extract_openai_tool_names(body)
    assert names == ["search_docs", "exec_shell"]
    al = ToolAllowlist(allow=["*"], deny=["exec_*"])
    decision = enforce_tool_calls(al, names)
    assert decision.denied == ["exec_shell"]
    removed = redact_openai_tool_calls(body, set(decision.denied))
    assert removed == 1
    remaining = [
        tc["function"]["name"]
        for tc in body["choices"][0]["message"]["tool_calls"]
    ]
    assert remaining == ["search_docs"]


def test_anthropic_response_redaction_strips_denied_tool_use() -> None:
    body = {
        "content": [
            {"type": "text", "text": "Calling tools..."},
            {"type": "tool_use", "id": "a", "name": "search_docs", "input": {}},
            {"type": "tool_use", "id": "b", "name": "delete_db", "input": {}},
        ]
    }
    names = extract_anthropic_tool_names(body)
    assert names == ["search_docs", "delete_db"]
    al = ToolAllowlist(allow=["search_*", "read_*"], deny=[])
    decision = enforce_tool_calls(al, names)
    assert decision.denied == ["delete_db"]
    removed = redact_anthropic_tool_calls(body, set(decision.denied))
    assert removed == 1
    types = [c.get("type") for c in body["content"]]
    assert types == ["text", "tool_use"]
    assert body["content"][1]["name"] == "search_docs"


def test_record_blocks_increments_per_tool() -> None:
    before_a = _counter_value("tool_a")
    before_b = _counter_value("tool_b")
    record_blocks(tenant="tA", policy_id="p1", denied=["tool_a", "tool_b", "tool_a"])
    after_a = _counter_value("tool_a")
    after_b = _counter_value("tool_b")
    assert after_a == before_a + 2
    assert after_b == before_b + 1


def test_redact_with_empty_denied_is_noop() -> None:
    body = {"choices": [{"message": {"tool_calls": [{"function": {"name": "x"}}]}}]}
    snapshot = copy.deepcopy(body)
    assert redact_openai_tool_calls(body, set()) == 0
    assert body == snapshot
