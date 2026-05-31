# Local CA proxy — install + operate

The local CA proxy (`section-edge-proxy`) is the single highest-leverage
edge component: every IDE assistant and CLI tool that respects
`HTTPS_PROXY` is covered, no per-tool integration required.

Per-provider / per-client status: [`docs/edge-coverage-matrix.md`](../edge-coverage-matrix.md).

## What it does

* Boots a local MITM proxy listening on `127.0.0.1:8888` (configurable).
* Generates a per-machine RSA root CA (4096-bit) on first install and
  installs it into the OS trust store.
* For each request to `api.openai.com`, `api.anthropic.com`, etc., it:
  1. Decrypts the TLS,
  2. Extracts the prompt text via a provider-specific extractor,
  3. POSTs to the gateway's `/v1/scan`,
  4. Rewrites the request body with the sanitised text (or blocks
     with a 403),
  5. Forwards to the real upstream,
  6. On response, POSTs to `/v1/restore` and re-injects the originals
     before returning to the client.

The CA's private key never leaves the machine.

## Install

### Windows

```powershell
# Install the wheel (or run from the published container)
pipx install section-edge-proxy

# One-time: generate + trust the CA (requires admin)
section-edge-proxy install-ca

# Start the proxy
section-edge-proxy start `
    --gateway https://gateway.your-corp.com `
    --api-key $env:SECTION_API_KEY `
    --listen 127.0.0.1:8888
```

Set `HTTPS_PROXY` system-wide via
**Settings → System → For developers → Use HTTPS proxy** or
`setx HTTPS_PROXY http://127.0.0.1:8888 /M`.

### macOS

```bash
brew tap section/tap
brew install section-edge-proxy

# Install the CA (will prompt for sudo)
section-edge-proxy install-ca

section-edge-proxy start \
    --gateway https://gateway.your-corp.com \
    --api-key "$SECTION_API_KEY"
```

Set `HTTPS_PROXY` in `~/.zshrc` / `~/.bash_profile`:

```bash
export HTTPS_PROXY=http://127.0.0.1:8888
export HTTP_PROXY=http://127.0.0.1:8888
```

### Linux

```bash
pipx install section-edge-proxy

# Debian / Ubuntu
sudo section-edge-proxy install-ca   # writes to /usr/local/share/ca-certificates/

# RHEL / Fedora
sudo section-edge-proxy install-ca   # writes to /etc/pki/ca-trust/source/anchors/

section-edge-proxy start \
    --gateway https://gateway.your-corp.com \
    --api-key "$SECTION_API_KEY"
```

## Per-tool configuration

### Cursor

`~/.cursor/settings.json`:
```json
{
  "http.proxy": "http://127.0.0.1:8888",
  "http.proxyStrictSSL": true
}
```

### Claude Code (CLI)

```bash
export HTTPS_PROXY=http://127.0.0.1:8888
claude
```

### Continue

`~/.continue/config.json`:
```json
{
  "requestOptions": {
    "proxy": "http://127.0.0.1:8888"
  }
}
```

### aider

aider auto-honours `HTTPS_PROXY`:
```bash
export HTTPS_PROXY=http://127.0.0.1:8888
aider
```

### Cline (VS Code)

VS Code settings:
```json
{
  "http.proxy": "http://127.0.0.1:8888"
}
```

### Copilot CLI / Codex CLI

```bash
export HTTPS_PROXY=http://127.0.0.1:8888
gh copilot suggest "list all my open PRs"
```

### Zed AI

`~/.config/zed/settings.json`:
```json
{
  "proxy": "http://127.0.0.1:8888"
}
```

## Operate

| Command | What it does |
|---|---|
| `section-edge-proxy status` | Print JSON: pid, listen, gateway, hosts_intercepted, last_decision |
| `section-edge-proxy stop` | Graceful stop via PID file |
| `section-edge-proxy install-ca` | Generate (if missing) + install the local CA |
| `section-edge-proxy uninstall-ca` | Remove from trust store and delete the key |

## Threat model

| Threat | Mitigation |
|---|---|
| Stolen private key | Key is on disk at mode 0600 in OS-protected app data dir. On Windows we use DPAPI when available. On macOS and Linux we set `chmod 0600` + restrictive ACL. |
| Attacker uses our CA to MITM other domains | The CA is install-time scoped to localhost-only proxy use; we recommend operators set `extendedKeyUsage = serverAuth` and pin via `nameConstraints` to the listed upstream hosts (`name_constraints.yaml`). |
| Proxy bypassed (user unsets `HTTPS_PROXY`) | Detected at the egress firewall / DNS RPZ layer — provider DNS resolves to the corp egress gateway which logs and rejects. Pair with the audit heartbeat from the browser extension to detect gaps. |

## Uninstall

```bash
section-edge-proxy uninstall-ca
pipx uninstall section-edge-proxy   # or brew uninstall, etc.
```

This removes the CA from the OS trust store **and** deletes the private
key. There is no undo — the key is regenerated from scratch on next
install.
