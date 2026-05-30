# Edge coverage matrix

Status of Praesidio's endpoint coverage across the client × provider
grid. This is the canonical answer to "does Praesidio cover ChatGPT in
the browser? what about Cursor? Copilot CLI?".

Legend
- ✅ **PASS** — full scan + mask + restore round-trip tested in CI.
- 🟦 **PARTIAL** — scan + mask working; response-side restore is
  best-effort.

## Browser extension (`clients/browser/`)

| Provider site | Submit intercept | Response restore | Block UI | Status |
|---|---|---|---|---|
| chatgpt.com | ✅ | ✅ | ✅ | ✅ |
| claude.ai | ✅ | ✅ | ✅ | ✅ |
| gemini.google.com | ✅ (page-world fetch hook) | 🟦 | ✅ | 🟦 |
| copilot.microsoft.com | ✅ | 🟦 | ✅ | 🟦 |
| perplexity.ai | ✅ | 🟦 | ✅ | 🟦 |
| chat.mistral.ai | ✅ | 🟦 | ✅ | 🟦 |

## Local CA proxy (`services/edge-proxy/`)

The proxy intercepts these upstream hosts at the network layer. Any
tool that respects `HTTPS_PROXY` is covered — no per-tool integration
required.

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

### IDE / CLI clients via local proxy

| Client | OpenAI | Anthropic | Gemini | Notes |
|---|---|---|---|---|
| Cursor | ✅ | ✅ | 🟦 | Set `HTTPS_PROXY` in `~/.cursor/settings.json` |
| Claude Code (CLI) | n/a | ✅ | n/a | `ANTHROPIC_BASE_URL=https://127.0.0.1:8888 claude` |
| Continue (VS Code / JetBrains) | ✅ | ✅ | 🟦 | Uses `OPENAI_API_BASE` |
| aider | ✅ | ✅ | n/a | Auto-honours `HTTPS_PROXY` |
| Cline (VS Code) | ✅ | ✅ | 🟦 | Honours `HTTPS_PROXY` |
| GitHub Copilot CLI | ✅ | n/a | n/a | Uses OpenAI-compatible endpoint |
| Zed AI | ✅ | ✅ | 🟦 | Honours `HTTPS_PROXY` |

## VS Code extension (`clients/vscode/`)

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

## JetBrains plugin (`clients/jetbrains/`)

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

Verified against: IntelliJ IDEA 2023.2+, PyCharm 2023.2+, GoLand
2023.2+, WebStorm 2023.2+, Rider 2023.2+, RubyMine 2023.2+, PhpStorm
2023.2+.

## How we keep this honest

Every cell with ✅ has a passing test in CI. Browser PASS cells are
exercised by Playwright specs against synthetic local fixtures (no
external traffic to live provider sites; selectors are pinned to a
known DOM snapshot). CLI/IDE PASS cells are smoke-tested by the
edge-proxy integration tests using the gateway's [cassette-driven
real-LLM CI](operations/recording-cassettes.md) harness.
