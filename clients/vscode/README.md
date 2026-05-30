# Praesidio for VS Code

> Scan and mask sensitive data in your editor before it reaches
> Copilot Chat, Cursor, Continue, or any LLM.

Praesidio is an open-source AI security control plane. This extension
is the VS Code surface for the Praesidio gateway: it runs the editor's
selection (and, optionally, every open document) through the gateway's
`/v1/scan` endpoint, then either rewrites prompts in place or flags
findings with an inline quick-fix.

The whole flow stays inside your machine and the operator-configured
gateway. No third-party endpoints, no telemetry. Source: [Apache-2.0,
github.com/cwellbournewood/praesidio](https://github.com/cwellbournewood/praesidio).

## What you get

```
┌────────────────────────────────────────────────────────────────┐
│  src/api/client.ts                                  ● 2 ⚠       │
│  ─────────────────────────────────────────────────────────────  │
│   18  const apiKey = "praes_live_8b1c2…";    ⚠ Praesidio        │
│   19  const userEmail = "alice@acme.com";    ⚠ Praesidio        │
│   20                                                            │
│       💡 Quick-fix: Praesidio: Tokenise → <API_KEY_…>, <EMAIL_…>│
└────────────────────────────────────────────────────────────────┘
$(shield) Praesidio • mask          ←  status bar (bottom-left)
```

- **Scan selection** (`Praesidio: Scan Selection`) — runs the highlighted
  text through `/v1/scan` and shows a diff: original vs sanitised, with a
  one-click "Replace" button.
- **Inline diagnostics** — open any file and Praesidio surfaces every DLP
  finding as a warning (debounced, configurable severity).
- **Quick-fix tokenise** — one keystroke replaces a flagged span with its
  vault-backed placeholder (`<EMAIL_A2B3>`, `<API_KEY_K7M2>`, …).
- **Local proxy toggle** — start `praesidio-edge-proxy` from the command
  palette to MITM-cover every CLI that honours `HTTPS_PROXY` (Copilot CLI,
  Cursor, Continue, aider, Cline, Zed AI, ...).
- **Audit visibility** — every scan + restore writes an audit row tagged
  `upstream="edge-client"` + `client="vscode"`; the "Open Audit Trail"
  command takes you straight to `/admin/events`.

## Install

### From the Marketplace

```
ext install praesidio.praesidio-vscode
```

Also published on [Open VSX](https://open-vsx.org/) for VSCodium and
forks that don't ship the Microsoft Marketplace.

### Sideload `.vsix`

```
code --install-extension praesidio-vscode-1.1.0.vsix
```

You can build the `.vsix` yourself from this directory with

```
npm install
npm run build
npm run package
```

The Makefile target `make vscode-package` does the same from the repo
root.

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `praesidio.gateway.url` | `http://localhost:8080` | Praesidio gateway base URL. |
| `praesidio.gateway.tenantId` | `""` | Optional tenant id sent as `X-Praesidio-Tenant`. JWT claims win when signed in via OIDC. |
| `praesidio.diagnostics.enabled` | `true` | Surface DLP findings as warnings. |
| `praesidio.diagnostics.debounceMs` | `800` | Debounce before rescanning an edited document. |
| `praesidio.diagnostics.severity` | `warning` | `error` \| `warning` \| `information` \| `hint`. |
| `praesidio.diagnostics.maxBytes` | `262144` | Chunk size for large documents. |
| `praesidio.proxy.autoStart` | `false` | Spawn the local proxy on activation. |
| `praesidio.proxy.binaryPath` | `praesidio-edge-proxy` | Path to the proxy binary (looked up on PATH by default). |
| `praesidio.proxy.port` | `8889` | Port the local proxy binds to. |
| `praesidio.statusBar.enabled` | `true` | Show the status-bar pill. |
| `praesidio.oidc.deviceCodeEndpoint` | `""` | OIDC device authorisation endpoint. Falls back to `{gateway.url}/oidc/device_authorization`. |
| `praesidio.oidc.tokenEndpoint` | `""` | OIDC token endpoint. Falls back to `{gateway.url}/oidc/token`. |
| `praesidio.oidc.clientId` | `praesidio-vscode` | OIDC client id. |
| `praesidio.oidc.scopes` | `openid profile praesidio.edge` | OIDC scopes requested. |

> The deprecated `praesidio.gateway.apiKey` setting is left in the
> schema for compatibility but **should be empty**. Real API keys are
> stored in VS Code SecretStorage via `Praesidio: Sign In`.

## Commands

| Command | Default keybinding | What it does |
|---|---|---|
| `Praesidio: Scan Selection` | _none_ | Scan the editor selection, diff + replace. |
| `Praesidio: Tokenise Selection` | _none_ | Silent companion — replace without the diff. Also fires from the diagnostic quick-fix. |
| `Praesidio: Toggle Local Proxy` | _none_ | Start / stop `praesidio-edge-proxy`. |
| `Praesidio: Sign In` | _none_ | API key or OIDC device-code. |
| `Praesidio: Sign Out` | _none_ | Clear stored credentials. |
| `Praesidio: Open Audit Trail` | _none_ | Open `/admin/events` in the default browser. |

All commands are also available via the status-bar quick-pick (click
the `$(shield) Praesidio` pill).

## Authentication

Two flows. Both store secrets in VS Code's `SecretStorage`, which is
backed by the OS keychain (Windows Credential Manager, macOS Keychain,
libsecret on Linux). Secrets never touch `settings.json`.

1. **API key.** Paste an `X-API-Key` value into the prompt that opens
   from `Praesidio: Sign In → API Key`. Use this for single-machine
   dev workflows.
2. **OIDC device code (RFC 8628).** Choose `Praesidio: Sign In → OIDC
   Device Code`. The extension opens a verification URL in your
   default browser; once you approve, the access token is stored and
   automatically attached as `Authorization: Bearer …`. The tenant id
   is read from the JWT claim — any `gateway.tenantId` setting is
   ignored.

## Local proxy

The "Toggle Proxy" command spawns the `praesidio-edge-proxy` binary
from your `PATH` (configurable via `praesidio.proxy.binaryPath`).

```
$ export HTTPS_PROXY=http://localhost:8889
$ cursor .                  # or aider, continue, copilot, cline, ...
```

While the proxy is running, every API call to a supported provider
(OpenAI, Anthropic, Google, Cohere, Mistral, Perplexity, Groq,
DeepSeek) is intercepted, scanned, and replayed against the upstream
with placeholders in place. Responses are walked for placeholders and
restored before the tool sees them.

The status bar pill shows `proxy: running`/`stopped`/`error`.

## Development

```
# Clone the repo and cd into this folder
cd clients/vscode
npm install
npm run typecheck            # tsc --noEmit
npm run lint                 # eslint
npm test                     # node --test tests/*.test.ts
npm run build                # tsc → out/
npm run package              # @vscode/vsce → .vsix
```

To run the extension under a real VS Code dev host, open `clients/vscode/`
in VS Code and hit `F5`. A second window opens with the extension loaded.

## Telemetry, privacy, security

- **No telemetry.** The extension communicates only with the
  operator-configured `praesidio.gateway.url`.
- **No third-party endpoints.** Even the icon is shipped in-tree.
- **Audit-first.** Every `/v1/scan` and `/v1/restore` call writes an
  audit row server-side. The "Open Audit Trail" command shows them.
- **CSP-style egress.** The bundled JavaScript imports `fetch` only;
  no `XMLHttpRequest`, no `WebSocket`, no embedded analytics.
- **Reproducible builds.** Apache-2.0 source, cosign-signed `.vsix`
  attached to GitHub releases (see `.github/workflows/edge.yml`).

For the threat model, see [`docs/threat-model.md`](../../docs/threat-model.md).

## License

Apache License 2.0 — see [`LICENSE`](./LICENSE) and the root
[`LICENSE`](../../LICENSE).
