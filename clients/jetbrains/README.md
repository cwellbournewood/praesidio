# Praesidio — JetBrains plugin

Semantic data-loss prevention for AI coding tools, inside your JetBrains IDE.

Works in IntelliJ IDEA, PyCharm, GoLand, WebStorm, Rider, RubyMine, PhpStorm,
DataGrip — anything on the IntelliJ Platform 2023.2 through 2025.2.

## What it does

| Capability | How |
|---|---|
| Scan editor selections for sensitive data | Right-click → **Praesidio: Scan Selection** |
| Replace sensitive spans with reversible placeholders | Right-click → **Praesidio: Tokenise Selection** |
| Highlight findings inline in any open file | Built-in **Sensitive data** inspection with **Tokenise** quick-fix |
| Manage the local MITM edge proxy | Tools → Praesidio → **Toggle Edge Proxy** |
| Authenticate the IDE to the gateway | Tools → Praesidio → **Sign In** (OIDC device-code) or **Settings → Tools → Praesidio** for API key |
| See your most-recent gateway decisions | Tool window on the right edge |

Everything routes through your operator's Praesidio gateway, so the same DLP
policy that governs server traffic also covers your IDE.

## Install

### Marketplace (recommended)

1. **File → Settings → Plugins → Marketplace** (macOS: **IntelliJ IDEA →
   Preferences → Plugins → Marketplace**).
2. Search for **Praesidio**.
3. Click **Install** and restart the IDE.

### Sideload a `.zip`

If your organisation pins a specific release or installs from an air-gapped
mirror:

1. Download `praesidio-jetbrains-<version>.zip` from your operator's
   distribution channel.
2. **File → Settings → Plugins → ⚙ (top-right) → Install Plugin from Disk…**
3. Select the `.zip`. Restart when prompted.

The released `.zip` is signed with cosign (keyless). Verify before
sideloading:

```bash
cosign verify-blob \
  --signature praesidio-jetbrains-<version>.zip.sig \
  --certificate-identity-regexp 'https://github.com/praesidio/praesidio/.*' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  praesidio-jetbrains-<version>.zip
```

## Configure

Open **Settings → Tools → Praesidio**:

| Field | Description |
|---|---|
| **Gateway URL** | Base URL of your Praesidio gateway, e.g. `https://gateway.acme.example/`. |
| **API key** | A per-user key, stored in the IDE PasswordSafe. Leave blank if signing in via OIDC. |
| **Tenant** | Optional `X-Praesidio-Tenant` header. Overridden by JWT claim when signed in via OIDC. |
| **Sign in via OIDC…** | Starts the RFC 8628 device-code flow against your operator's IdP. The IDE opens a browser tab; approve there and the refresh token lands in your OS keychain. |
| **Enable sensitive-data inspection** | Whether the inspection scans open files. Turn off if you want only on-demand scans. |
| **Inspection debounce (ms)** | Quiescence window between document changes before re-scanning. Default 750 ms. |
| **Start edge proxy on IDE launch** | Spawn `praesidio-edge-proxy` automatically. Requires the CLI to be installed and the CA cert trusted. |
| **Edge proxy binary path** | Optional path to the proxy CLI. Defaults to `praesidio-edge-proxy` on `$PATH`. |

Hit **Test connection** to verify the gateway is reachable.

### Authentication precedence

1. OIDC access token (if you signed in)
2. API key (from PasswordSafe)
3. Header-only (dev gateways with `--auth-mode dev`)

Both auth modes also send `X-Praesidio-Tenant`, `X-Praesidio-User`, and
`X-Praesidio-Groups` headers so a gateway behind a header-trusting reverse
proxy still works.

## Usage

### Scan selection

Highlight text in any editor, right-click → **Praesidio → Scan Selection**.

A balloon notification tells you the decision:
- **Allowed** — no findings, nothing to do.
- **Mask: N sensitive spans** — findings exist; choose **Tokenise** if you
  want to replace them.
- **Blocked: <reason>** — your operator's policy refused the content.

The selection is never modified by **Scan**. To replace, use **Tokenise
Selection** explicitly.

### Tokenise selection

Highlight text, right-click → **Praesidio → Tokenise Selection**. The
selection is replaced with the sanitised version in a single undoable edit.
Subsequent model responses containing the placeholders are restored via
`POST /v1/restore`; this plugin uses the same vault binding as the rest of
the platform, so the restore is tenant- and request-scoped.

### Sensitive-data inspection

Findings appear as warnings (yellow underline) in any open file. Hover for
the detector label and confidence; alt-enter to invoke the **Tokenise**
quick-fix.

The inspection is throttled in three ways:
- Only runs on files with at least 16 characters.
- Caches results by content hash, so unchanged files re-render the same
  warnings without re-hitting the gateway.
- Chunks long files at 256 kB UTF-8 boundaries, preferring paragraph >
  line > sentence > word > hard cuts.

Toggle off in **Settings** if you only want on-demand scans.

### Edge proxy

The bundled **Toggle Edge Proxy** action spawns or kills the local
`praesidio-edge-proxy` CLI. The proxy MITMs traffic from any AI CLI tool
that respects `HTTPS_PROXY` (Cursor, Claude Code, Continue, aider, Copilot
CLI, …) and scans every prompt through the same gateway.

The proxy keeps running on the loopback interface even if the IDE closes —
unless **Start edge proxy on IDE launch** is on, in which case the IDE owns
the lifecycle and kills the proxy on shutdown.

## Build from source

```bash
cd clients/jetbrains
./gradlew buildPlugin
```

Output lands at `build/distributions/praesidio-jetbrains-<version>.zip`.

The wrapper downloads Gradle 8.5 on first run; you need a JDK 17+ on
your PATH or `JAVA_HOME`.

### Tests

```bash
./gradlew test
```

Plain JUnit 5 + OkHttp `MockWebServer` — runs in seconds, no IntelliJ
platform boot. Heavy integration tests (against the platform test
harness) live behind `-PrunPlatformTests=true`.

### Lint

```bash
./gradlew ktlintCheck
```

Apply auto-fixes with `./gradlew ktlintFormat`.

### Run a sandbox IDE

```bash
./gradlew runIde
```

Launches a fresh IntelliJ IDEA Community sandbox with the plugin pre-installed.

## Distribution channel

Each tagged release ships:

- `praesidio-jetbrains-<version>.zip` — installable plugin.
- `praesidio-jetbrains-<version>.zip.sig` + `.pem` — cosign keyless
  signature and certificate.
- `praesidio-jetbrains-<version>.zip.intoto.jsonl` — SLSA-3 provenance.

The same artifact is pushed to the JetBrains Marketplace and to the
GitHub release.

## License

Apache-2.0. See [LICENSE](LICENSE).
