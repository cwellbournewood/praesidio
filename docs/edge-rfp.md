# Praesidio Edge coverage RFP

Status: **shipped in 1.0** (originally planned for 1.1; pulled forward 2026-05-28)
Owners: gateway, edge-proxy, browser, ide

## Why this exists

Praesidio 1.0 covers the **gateway path**: anything an enterprise's
backend or agent service sends through `/v1/chat/completions`,
`/v1/embeddings`, `/anthropic/v1/messages`, the Azure / Bedrock /
Ollama adapters. That covers ~all server-side and CI/CD AI traffic.

It does **not** cover the human at the keyboard:

* An employee opens chatgpt.com and pastes a customer email.
* A developer in VS Code asks Copilot Chat about a stack trace that
  contains a JWT.
* A solutions engineer pipes a Postgres dump into `claude.ai` to ask
  for schema feedback.
* A data scientist runs `aider` against a private repo and the
  prompt contains an AWS secret.

Without endpoint coverage the gateway is bypassable by every browser
tab and every `HTTPS_PROXY`-respecting CLI. That makes the entire
control plane unfit for purpose in any enterprise that takes DLP
seriously. **1.0 closes this gap.**

## Goals

1. **Browser coverage** for the six most-used consumer AI sites:
   chatgpt.com, claude.ai, gemini.google.com, copilot.microsoft.com,
   perplexity.ai, chat.mistral.ai. One Manifest V3 extension, ships
   to Chrome / Brave / Edge / Arc / Opera (all use the same store
   binary).
2. **IDE coverage via local CA proxy** for everything that respects
   `HTTPS_PROXY`: Cursor, Claude Code, Continue, aider, Cline,
   Copilot CLI, Zed AI. One MITM-style proxy that the gateway boots
   in `--proxy-mode`. Single feature → covers ~8 tools.
3. **First-class VS Code extension** with status bar, scan-selection
   command, sensitive-data diagnostics in open files, settings sync.
4. **First-class JetBrains plugin** with the same surface for the
   IntelliJ platform (IDEA, PyCharm, GoLand, WebStorm, Rider).
5. **No new attack surface** in the gateway itself: edge clients
   call `/v1/scan` and `/v1/restore`, both of which reuse the
   existing orchestrator, vault, audit chain, and policy engine.
6. **Audit coverage parity**: an edge-originated request shows up in
   `audit_events` with `upstream="edge-client"` plus a `transforms`
   entry tagging the client and origin URL. Existing dashboards,
   SIEM filters, and `praesidio-audit verify` all work unchanged.

## Non-goals (1.1)

* iOS / Android browsers (no MV3 host support; revisit in 1.3).
* Native desktop interception of ChatGPT desktop apps / Claude
  desktop apps (separate threat model — covered in 2.0 candidates).
* Endpoint DLP for non-AI traffic (Slack, Gmail, etc.). Out of
  charter; that's an EDR product.
* MDM-style forced install — operators ship the extension via their
  existing MDM (Jamf / Intune / Workspace) using the standard
  `ExtensionInstallForcelist` policy. We document but don't build.

## Architecture

```
                                   ┌───────────────────────────┐
   browser tab (chatgpt.com)  ───▶ │ content-script + page-    │
                                   │ world injector            │
                                   └────┬──────────────────────┘
                                        │ POST /v1/scan
                                        ▼
   VS Code / Cursor / aider  ────▶ ┌───────────────────────────┐
                                   │ Praesidio Gateway         │
                                   │  /v1/scan  /v1/restore    │
   Claude Code / Continue ───────▶ │  orchestrator → policy →  │
                       (via local  │  anonymise → vault → audit│
                        CA proxy)  └────┬──────────────────────┘
                                        │
                                        ▼
                                   ┌───────────────────────────┐
                                   │ audit_events              │
                                   │ upstream="edge-client"    │
                                   │ transforms[]:             │
                                   │   {method:"edge_source",  │
                                   │    client:"browser-       │
                                   │     extension",           │
                                   │    url:"...",             │
                                   │    model_hint:"..."}      │
                                   └───────────────────────────┘
```

The gateway is unchanged in shape — only two new endpoints. All edge
clients are thin: scan-and-rewrite on submit, walk-and-replace on
response.

## New gateway endpoints

### `POST /v1/scan`

Apply DLP + policy + anonymisation to a prompt string. Writes vault
+ audit. Does NOT forward to any LLM provider (the edge client does
that itself).

Request:
```json
{
  "text": "send the wire to acct 12345 john.doe@acme.com",
  "client": "browser-extension",
  "url": "https://chatgpt.com/c/abc-123",
  "model": "gpt-4o",
  "session_id": "tab-7c1f"
}
```

Response (mask):
```json
{
  "request_id": "9b2c...",
  "action": "mask",
  "sanitised": "send the wire to acct <ACCOUNT_NUMBER_A4F2> <EMAIL_K7M2>",
  "transforms": [
    {"label": "regex.account_number", "placeholder": "<ACCOUNT_NUMBER_A4F2>", "method": "tokenise", "scope": "request"},
    {"label": "pii.email", "placeholder": "<EMAIL_K7M2>", "method": "tokenise", "scope": "request"}
  ],
  "findings": [...],
  "decision": {"action":"transform","mode":"enforce","effective_action":"transform",...},
  "bundle_digest": "abc..."
}
```

Response (block) returns `action: "block"` with `reason`, `severity`,
and no `sanitised` — the client refuses to submit.

Auth: standard `X-API-Key` or `Authorization: Bearer` plus the usual
`X-Praesidio-Tenant` / -User / -Groups headers from the upstream
auth proxy.

### `POST /v1/restore`

Walk a model response for placeholders, swap them back in. Tenant +
request_id are AAD-bound at the vault layer; cross-tenant lookups
fail.

Request:
```json
{
  "request_id": "9b2c...",
  "text": "I'll send the wire to <ACCOUNT_NUMBER_A4F2> on Tuesday."
}
```

Response:
```json
{
  "request_id": "9b2c...",
  "text": "I'll send the wire to 12345 on Tuesday.",
  "restored": 1,
  "missing": []
}
```

Unlike `/admin/detokenise`, no `vault:detokenise` scope is required —
this is the prompt originator restoring their own response. Every
call is audited (`decision="restore"`).

## Auth federation

Edge clients all support two modes:

1. **API key** (developer / single-machine). Stored in OS keychain
   (`keytar` on Node; `Windows Credential Manager` / `macOS Keychain`
   / `libsecret`). Never in plaintext config.
2. **OIDC device code** (enterprise / fleet). Standard
   [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628) flow:
   extension opens a browser tab to the operator's IdP, user
   approves, refresh token stored in keychain. Tenant id is claimed
   from the JWT.

Both flows surface a `praesidio_edge_token` that is presented to the
gateway as `Authorization: Bearer …`. The token's tenant claim wins
over any caller-supplied `X-Praesidio-Tenant` header.

## Edge audit row schema

No schema changes to `audit_events`. We use existing fields:

| Field | Edge value |
|---|---|
| `route` | `/v1/scan` or `/v1/restore` |
| `upstream` | `"edge-client"` for scan, `"vault"` for restore |
| `decision` | `"allow"` \| `"transform"` \| `"block"` \| `"restore"` |
| `transforms[]` (one extra entry) | `{method:"edge_source", client:"browser-extension"\|"vscode"\|"jetbrains"\|"edge-proxy"\|"cli", url:"<origin>", model_hint:"<provider model>"}` |

SIEM filters that already split on `upstream` get edge traffic for
free. The `edge_source` transform entry lets Grafana panels split by
client without parsing JSON.

## Threat-model deltas (vs `docs/threat-model.md`)

| Threat | Mitigation |
|---|---|
| Compromised extension exfiltrates user prompts | (1) Extension only sends prompts to operator-configured gateway URL; CSP `connect-src` restricts to that URL. (2) Extension is open-source, reproducible-build, cosign-signed `.crx` published with a release-pinned SHA256. (3) Operators audit via Chrome Web Store admin "Force-installed extensions" list. |
| MITM proxy CA cert used by attacker | Per-machine CA is generated locally and never leaves the machine; private key in OS keychain (Windows DPAPI / macOS Keychain / Linux libsecret). Cert is non-exportable. CA install requires admin on Windows and `sudo` on macOS/Linux. |
| Edge client bypassed by malicious user | Detected in audit: any LLM API call NOT routed through gateway/edge-proxy is visible at the network layer (operators run DNS RPZ + egress-allow-list as standard control). Extension also pushes "heartbeat" audit rows (`decision="heartbeat"`) every 5 min — gap in heartbeats triggers SIEM alert. |
| Placeholders leak to LLM provider but original is still in vault when user closes laptop | Vault entries TTL at 1h (`PRAESIDIO_VAULT_TTL_SECONDS`); `/v1/restore` returns `missing:[...]` for expired tokens; UI shows "this response was generated with masked context — original no longer available". |
| Extension auto-update poisoning | Web Store auto-update model is trust-on-first-use of the Google review process. We add: signed update manifest (`update_url` points at our own server), cosign verification at install time of the `.crx`, SLSA-3 build provenance attestation per release. |

## Repo layout (new)

```
praesidio/
├── services/edge-proxy/          # Lane E
│   ├── pyproject.toml
│   ├── praesidio_edge_proxy/
│   │   ├── __init__.py
│   │   ├── ca.py                 # per-machine CA gen
│   │   ├── proxy.py              # mitmproxy addons
│   │   ├── upstream.py           # api.openai.com → gateway map
│   │   ├── cli.py                # praesidio-edge-proxy
│   │   └── install/
│   │       ├── windows.ps1
│   │       ├── macos.sh
│   │       └── linux.sh
│   └── tests/
├── clients/
│   ├── browser/                  # Lane B
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── manifest.json         # MV3
│   │   ├── src/
│   │   │   ├── background/      # service worker
│   │   │   ├── content/         # per-site content scripts
│   │   │   ├── page/            # page-world fetch hook
│   │   │   ├── popup/           # React popup
│   │   │   ├── lib/             # gateway client, vault, restore
│   │   │   └── locales/
│   │   ├── tests/               # vitest unit
│   │   └── e2e/                 # Playwright against fixtures
│   ├── vscode/                   # Lane V
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── src/
│   │   │   ├── extension.ts
│   │   │   ├── gateway.ts
│   │   │   ├── diagnostics.ts
│   │   │   └── commands.ts
│   │   └── tests/
│   └── jetbrains/                # Lane J
│       ├── build.gradle.kts
│       ├── settings.gradle.kts
│       ├── src/main/
│       │   ├── kotlin/io/praesidio/edge/
│       │   └── resources/META-INF/plugin.xml
│       └── src/test/
└── docs/
    ├── edge-rfp.md           # this file
    ├── edge-coverage-matrix.md   # provider × client support
    └── operations/
        ├── edge-proxy-install.md
        ├── browser-extension-install.md
        └── ide-extension-install.md
```

## Acceptance criteria

A 1.0 cut ships when ALL of the following are green:

1. `praesidio-gateway` exposes `/v1/scan` + `/v1/restore`. Tests pass.
2. `praesidio-edge-proxy start --gateway https://gateway.local` MITMs
   `api.openai.com` / `api.anthropic.com` / `generativelanguage.googleapis.com`
   / `api.cohere.ai` / `api.mistral.ai` / `api.perplexity.ai` /
   `api.groq.com` / `api.deepseek.com`, scanning each request and
   writing audit. Auto-CA install works on Win/Mac/Linux.
3. Browser extension loads under `chrome://extensions` in
   developer mode, intercepts submit on all six target sites,
   shows mask/block UI, restores placeholders in response. Web
   Store submission package built by CI.
4. VS Code extension installs from `.vsix`, registers "Praesidio:
   Scan Selection" + "Praesidio: Toggle Proxy" commands, shows
   diagnostics for known sensitive data in open editor.
5. JetBrains plugin installs from `.zip`, registers tool window
   with same surface.
6. `docs/edge-coverage-matrix.md` lists every provider × client
   cell with PASS/PARTIAL/N/A.
7. `.github/workflows/edge.yml` builds all four artifacts (CA proxy
   wheel, browser `.crx` + `.zip`, `.vsix`, plugin `.zip`), runs
   smoke tests, attaches to release.
8. `docs/rfp-traceability.md` extended with the edge coverage row.

## Distribution

| Artifact | Channel | Verification |
|---|---|---|
| `praesidio-edge-proxy` wheel | PyPI + GHCR container | cosign keyless + SLSA-3 |
| Browser extension `.crx` | Chrome Web Store + GHCR `.zip` for self-host | Web Store review + cosign on the `.zip` |
| VS Code extension `.vsix` | Marketplace + Open VSX + GHCR | cosign on the `.vsix` |
| JetBrains plugin `.zip` | Marketplace + GHCR | cosign on the `.zip` |

## Open questions for 1.2

* Should the browser extension also block paste events that contain
  sensitive data, not just submit? (Likely yes — see ADR-0023.)
* MCP-aware mode for the local proxy: detect MCP traffic to
  `127.0.0.1` STDIO bridges and scan tool calls. Depends on 1.1
  MCP server adapter landing.
* iOS Safari Web Extension port — same MV3 manifest, but no
  page-world script support. Probably means content-script only,
  reduced restore fidelity.
