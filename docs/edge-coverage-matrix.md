# Edge coverage matrix

Status of Praesidio's endpoint coverage across the client × provider grid.
This is the canonical answer to "does Praesidio cover ChatGPT in the
browser? what about Cursor? Copilot CLI?" and is updated every release.

Status legend
-------------
- ✅ **PASS** — full scan + mask + restore round-trip tested in CI.
- 🟦 **PARTIAL** — scan + mask working; response-side restore is best-effort
  or not yet wired.
- 🟧 **PLANNED** — selectors / handlers stubbed in code with `TODO 1.1.1`;
  shipping behind a feature flag.
- ❌ **OUT OF SCOPE** — not on the roadmap.

## 1.0 — current

### Browser extension (`clients/browser/`)

| Provider site | Submit intercept | Response restore | Block UI | Status |
|---|---|---|---|---|
| chatgpt.com | ✅ | ✅ | ✅ | ✅ |
| claude.ai | ✅ | ✅ | ✅ | ✅ |
| gemini.google.com | ✅ (page-world fetch hook) | 🟦 | ✅ | 🟦 |
| copilot.microsoft.com | ✅ | 🟦 | ✅ | 🟦 |
| perplexity.ai | ✅ | 🟦 | ✅ | 🟦 |
| chat.mistral.ai | ✅ | 🟦 | ✅ | 🟦 |
| (others) | — | — | — | ❌ — file an issue |

### Local CA proxy (`services/edge-proxy/`)

The proxy intercepts these upstream hostnames at the network layer. Any tool
that respects `HTTPS_PROXY` works automatically — no per-tool integration
needed.

| Upstream host | Provider | Status |
|---|---|---|
| api.openai.com | OpenAI | ✅ |
| api.anthropic.com | Anthropic | ✅ |
| generativelanguage.googleapis.com | Google Gemini | ✅ |
| api.cohere.ai | Cohere | ✅ |
| api.mistral.ai | Mistral | ✅ |
| api.perplexity.ai | Perplexity | ✅ |
| api.groq.com | Groq | ✅ |
| api.deepseek.com | DeepSeek | ✅ |

### Coverage matrix — IDE / CLI clients via local proxy

The proxy is HTTP-layer; if a tool respects `HTTPS_PROXY` and uses one of the
upstream hosts above, it's covered. The matrix below documents which we have
hand-tested.

| Client | OpenAI | Anthropic | Gemini | Notes |
|---|---|---|---|---|
| Cursor | ✅ | ✅ | 🟦 | Set `HTTPS_PROXY` in `~/.cursor/settings.json` |
| Claude Code (CLI) | n/a | ✅ | n/a | `ANTHROPIC_BASE_URL=https://127.0.0.1:8888 claude` |
| Continue (VS Code / JetBrains) | ✅ | ✅ | 🟦 | Uses `OPENAI_API_BASE` |
| aider | ✅ | ✅ | n/a | Auto-honours `HTTPS_PROXY` |
| Cline (VS Code) | ✅ | ✅ | 🟦 | Honours `HTTPS_PROXY` |
| GitHub Copilot CLI | ✅ | n/a | n/a | Uses OpenAI-compatible endpoint |
| Zed AI | ✅ | ✅ | 🟦 | Honours `HTTPS_PROXY` |
| Codeium / Windsurf | 🟦 | 🟦 | 🟧 | TLS pinning suspected — confirm per version |

### VS Code extension (`clients/vscode/`)

Native UI surface beyond what the proxy provides:

| Feature | Status |
|---|---|
| Status bar: gateway connection + proxy state | ✅ |
| Command: Praesidio: Scan Selection | ✅ |
| Command: Praesidio: Tokenise Selection | ✅ |
| Command: Praesidio: Toggle Proxy | ✅ |
| Command: Praesidio: Sign In (OIDC) | ✅ |
| Diagnostic provider: sensitive data in open editor | ✅ |
| Code action: tokenise sensitive span | ✅ |
| Tool window: recent decisions | ✅ |

### JetBrains plugin (`clients/jetbrains/`)

Native UI surface beyond what the proxy provides:

| Feature | Status |
|---|---|
| Settings panel: gateway URL + sign-in | ✅ |
| Action: Praesidio: Scan Selection | ✅ |
| Action: Praesidio: Tokenise Selection | ✅ |
| Action: Praesidio: Toggle Proxy | ✅ |
| Inspection: SensitiveDataInspection (Warning) | ✅ |
| Tool window: recent decisions | ✅ |
| Quick-fix: tokenise | ✅ |

Verified against: IntelliJ IDEA 2023.2+, PyCharm 2023.2+, GoLand 2023.2+,
WebStorm 2023.2+, Rider 2023.2+, RubyMine 2023.2+, PhpStorm 2023.2+.

## 1.2 — planned

| Item | Notes |
|---|---|
| Safari Web Extension | Same MV3 manifest; reduced restore fidelity (no page-world script in iOS). |
| Firefox port | Manifest V2 fallback; track Mozilla's MV3 timeline. |
| MCP-aware proxy mode | Detect MCP STDIO bridges on 127.0.0.1 and scan tool-call args. |
| Paste-event blocking (browser) | Block paste of sensitive data, not just submit. See ADR-0023 (draft). |

## Out of scope (won't build)

- iOS / Android browser extensions on the consumer App Store (no MV3 host).
  Enterprise can ship via MDM-managed browsers (Edge for iOS supports
  extensions in some channels).
- Slack / Teams / Gmail DLP. Out of charter — that's an EDR product.
- Native desktop interception of ChatGPT / Claude desktop apps. Separate
  threat model; tracked as a 2.0 candidate.

## How we keep this honest

Every cell with ✅ has a passing test in CI. The browser PASS cells are
exercised by Playwright e2e specs against synthetic local fixtures (no
external traffic to live provider sites; selectors are pinned to a known
DOM snapshot). The CLI/IDE PASS cells are smoke-tested by the
`edge-proxy` integration tests using the gateway's
[cassette-driven real-LLM CI](operations/recording-cassettes.md) harness.
