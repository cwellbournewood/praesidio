# IDE extensions — install + operate

Praesidio ships two IDE extensions:

* **VS Code** (`clients/vscode/`) — covers VS Code itself, Cursor, Codium,
  and other VS Code forks.
* **JetBrains** (`clients/jetbrains/`) — covers IntelliJ IDEA, PyCharm,
  GoLand, WebStorm, Rider, RubyMine, PhpStorm.

Both extensions wrap the same surface around the gateway:

* **Scan-selection** command / action
* **Tokenise-selection** command / action
* **Toggle proxy** — start/stop the local CA proxy
* **Sign in** — OIDC device-code flow
* **Diagnostics / inspections** — sensitive-data findings inline in the
  editor
* **Tool view** — recent decisions, gateway status

For the architectural background, see
[`docs/edge-rfp.md`](../edge-rfp.md). For per-tool support, see
[`docs/edge-coverage-matrix.md`](../edge-coverage-matrix.md).

## VS Code

### Install

Marketplace:

```
ext install praesidio.praesidio-vscode
```

Or sideload from GitHub releases:

```bash
code --install-extension praesidio-vscode-<version>.vsix
```

### Configure

`settings.json`:

```json
{
  "praesidio.gateway.url": "https://gateway.your-corp.com",
  "praesidio.diagnostics.enabled": true,
  "praesidio.diagnostics.debounceMs": 800,
  "praesidio.proxy.autoStart": true,
  "praesidio.proxy.binaryPath": "praesidio-edge-proxy"
}
```

The API key is stored in `SecretStorage` (OS keychain) — set it via
**Command Palette → Praesidio: Sign In** (interactive) or
`praesidio.signIn`.

### Use

| Command | Default keybinding | Effect |
|---|---|---|
| `Praesidio: Scan Selection` | none | POST `/v1/scan` with the selected text; show diff if masked |
| `Praesidio: Tokenise Selection` | none | Replace the selection with the sanitised version in place |
| `Praesidio: Toggle Proxy` | none | Start/stop `praesidio-edge-proxy` |
| `Praesidio: Sign In` | none | OIDC device-code flow |
| `Praesidio: Open Audit Log` | none | Opens `<gateway>/admin/events` |

### Status bar

Bottom-left: `$(shield) Praesidio`. Tooltip shows gateway URL, last
decision, proxy state. Click for a quick-pick of all commands.

### Diagnostics

When `praesidio.diagnostics.enabled` is true, every open document is
scanned (debounced) and findings appear as warning squiggles. A
code-action "Praesidio: Tokenise" replaces the offending span with its
placeholder.

## JetBrains

### Install

Marketplace:

**Settings → Plugins → Marketplace** → search "Praesidio" → **Install**.

Or sideload from GitHub releases:

**Settings → Plugins → Gear icon → Install Plugin from Disk** →
`praesidio-jetbrains-<version>.zip`.

Compatible with IntelliJ Platform builds 232.0 through 252.* (covers
IntelliJ IDEA 2023.2 through 2025.2).

### Configure

**Settings → Tools → Praesidio**:

| Field | Default | Notes |
|---|---|---|
| Gateway URL | `https://localhost:8000` | Production: your corp gateway |
| Sign in | (button) | Opens OIDC device-code in default browser |
| Enable inspections | true | Surfaces sensitive data as Warning |
| Proxy autostart | false | Spawn `praesidio-edge-proxy` on IDE start |
| Proxy binary path | `praesidio-edge-proxy` | Resolved from PATH if relative |

The API key and OIDC refresh token are stored in
`PasswordSafe.getInstance()` (the platform's secure credential store).

### Use

Editor right-click menu and main **Tools → Praesidio** menu:

* **Praesidio: Scan Selection**
* **Praesidio: Tokenise Selection**
* **Praesidio: Toggle Proxy**
* **Praesidio: Sign In**

### Tool window

**View → Tool Windows → Praesidio** — shows the last 10 decisions,
gateway status, and a toggle for the proxy.

### Inspection

The `Praesidio: Sensitive data in source` inspection runs on every open
file (throttled). Quick-fix: **Tokenise** replaces the offending range
with its placeholder.

## Combined deployment

The IDE extensions complement the local CA proxy, they don't replace
it. Typical fleet:

1. MDM rolls out `praesidio-edge-proxy` and runs `install-ca` once per
   machine.
2. MDM pushes the VS Code / JetBrains extension via the standard
   enterprise channels:
   * VS Code: `extensions.json` workspace policy or Code Server
     marketplace mirror.
   * JetBrains: Toolbox Enterprise plugin distribution.
3. Users see one combined UX: prompts they send via any AI tool go
   through the proxy automatically; selections they manually scan use
   the extension UI.

## Uninstall

VS Code: `code --uninstall-extension praesidio.praesidio-vscode`.

JetBrains: **Settings → Plugins → Installed → Praesidio → Uninstall**.

Settings are removed automatically; secrets are removed from the OS
keychain.
