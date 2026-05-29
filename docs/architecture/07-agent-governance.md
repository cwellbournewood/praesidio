# 07 · Agent & Tool Runtime Governance

Status: **architected**. Interfaces defined, sandbox sketched, full
implementation on roadmap. This document specifies the contract Praesidio
exposes to agent frameworks (AutoGen, CrewAI, LangGraph, custom) and to MCP
servers.

## Threat picture

Agents are loops: LLM emits an action → tool runs → output rejoins context
→ LLM emits another action. Each step is an opportunity for:

- **prompt injection from tool output** (the canonical attack: a tool reads
  a page, the page contains "ignore your instructions and exfiltrate…"),
- **capability escalation** (agent talked into invoking a tool it shouldn't),
- **lateral movement** (agent uses one tool to pivot to another system),
- **covert exfiltration** (agent encodes data into "innocent" tool calls),
- **memory poisoning** (agent writes hostile content to long-term memory that
  taints future runs).

DLP at the prompt boundary alone does not cover any of these — the loop is
inside the tenant's perimeter.

## Architecture

```
   agent runtime (AutoGen / CrewAI / LangGraph / custom)
              │
              │  every tool call goes through:
              ▼
   ┌──────────────────────────────────────────────────────┐
   │ Praesidio Agent Broker (sidecar or in-process SDK)   │
   │                                                      │
   │  1. capability check (signed token, scope, TTL)      │
   │  2. argument DLP (same pipeline as gateway)          │
   │  3. tool registry lookup (signed manifest)           │
   │  4. sandbox executor (filesystem / network policy)   │
   │  5. output DLP + injection detection                 │
   │  6. lineage edge: tool ← prompt, output ← tool       │
   └──────────────────────────────────────────────────────┘
              │
              ▼
   actual tool (MCP server, http API, function)
```

## Capability tokens

Capability = a signed, scoped, time-bound JWT issued by the control plane
when an agent run is authorised.

```json
{
  "iss": "praesidio.control-plane",
  "sub": "agent:run:01HZ...",
  "aud": "praesidio.agent-broker",
  "exp": 1735680000,
  "nbf": 1735679400,
  "principal": { "user": "alice", "tenant": "acme" },
  "capabilities": [
    {"tool": "github.read_repo", "args": {"repo": "acme/internal"}, "max_invocations": 10},
    {"tool": "search.web",       "args": {}, "max_invocations": 50},
    {"tool": "fs.read",          "args": {"path_prefix": "/workspace/"}, "max_invocations": null},
    {"tool": "fs.write",         "args": {"path_prefix": "/workspace/out/"}, "max_invocations": null}
  ],
  "egress": { "allow_domains": ["api.github.com"] },
  "memory": { "scope": "session", "ttl": "1h" }
}
```

Signed with the control plane's Ed25519 key (rotated daily). Revocation is
push-based: the broker subscribes to a revocation stream and refuses any
token whose `sub` appears.

## MCP tool registry

Praesidio maintains a registry of approved MCP servers with:

| Field | |
|---|---|
| `name` | reverse-DNS identifier |
| `version` | semver |
| `signature` | cosign signature of the published manifest |
| `risk_score` | computed from capabilities declared (rwx, network, exec) |
| `default_capabilities` | what the broker auto-grants |
| `approval_required` | true → human approval per invocation in the UI |

Unsigned or unregistered MCP servers are refused by default.

## Sandbox

For tools that execute code (shell, browser, filesystem), the broker spawns
a sandbox:

- Linux: `bubblewrap` + `seccomp` (no_new_privs, syscall allowlist, network
  namespace per capability),
- macOS: `sandbox-exec`,
- Windows: AppContainer + Job Object.

Network egress is enforced by an internal proxy bound to the sandbox; allow
list comes from the capability token.

## Injection-aware output DLP

Every tool output is fed through:

1. Standard DLP (regex / secrets / etc.).
2. **Prompt injection classifier** — detects "ignore", "system", role
   manipulation, instruction-shaped substrings, base64/encoded payloads.
3. **Anomaly** — output that's wildly off-distribution for that tool gets
   flagged.

If injection is detected, the broker can either:
- redact the injection content before returning to the agent,
- wrap it in `<UNTRUSTED_CONTENT> … </UNTRUSTED_CONTENT>` (which the agent's
  system prompt is required to ignore as instructions), or
- block the tool result and surface to the human reviewer.

## Multimodal

The same broker pattern applies to images and audio. The OCR/ASR step
happens *inside* the broker so detection can run before the LLM sees the
content.

## Reference SDK

`praesidio_agent` (Python) and `@praesidio/agent` (TypeScript) ship thin
wrappers for AutoGen, CrewAI, LangGraph, and the Anthropic + OpenAI
function-calling APIs. Wrapping a tool with the SDK forwards every call
through the broker.
