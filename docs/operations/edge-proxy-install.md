# Local CA proxy — install + operate

The local CA proxy (`praesidio-edge-proxy`) is the single highest-leverage
component in Praesidio 1.0: every IDE assistant and CLI tool that respects
`HTTPS_PROXY` is covered by it, no per-tool integration required.

For the architectural background, see
[`docs/edge-rfp.md`](../edge-rfp.md). For the per-provider /
per-client status, see [`docs/edge-coverage-matrix.md`](../edge-coverage-matrix.md).

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
pipx install praesidio-edge-proxy

# One-time: generate + trust the CA (requires admin)
praesidio-edge-proxy install-ca

# Start the proxy
praesidio-edge-proxy start `
    --gateway https://gateway.your-corp.com `
    --api-key $env:PRAESIDIO_API_KEY `
    --listen 127.0.0.1:8888
```

Set `HTTPS_PROXY` system-wide via
**Settings → System → For developers → Use HTTPS proxy** or
`setx HTTPS_PROXY http://127.0.0.1:8888 /M`.

### macOS

```bash
brew tap praesidio/tap
brew install praesidio-edge-proxy

# Install the CA (will prompt for sudo)
praesidio-edge-proxy install-ca

praesidio-edge-proxy start \
    --gateway https://gateway.your-corp.com \
    --api-key "$PRAESIDIO_API_KEY"
```

Set `HTTPS_PROXY` in `~/.zshrc` / `~/.bash_profile`:

```bash
export HTTPS_PROXY=http://127.0.0.1:8888
export HTTP_PROXY=http://127.0.0.1:8888
```

### Linux

```bash
pipx install praesidio-edge-proxy

# Debian / Ubuntu
sudo praesidio-edge-proxy install-ca   # writes to /usr/local/share/ca-certificates/

# RHEL / Fedora
sudo praesidio-edge-proxy install-ca   # writes to /etc/pki/ca-trust/source/anchors/

praesidio-edge-proxy start \
    --gateway https://gateway.your-corp.com \
    --api-key "$PRAESIDIO_API_KEY"
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
| `praesidio-edge-proxy status` | Print JSON: pid, listen, gateway, hosts_intercepted, last_decision |
| `praesidio-edge-proxy stop` | Graceful stop via PID file |
| `praesidio-edge-proxy install-ca` | Generate (if missing) + install the local CA |
| `praesidio-edge-proxy uninstall-ca` | Remove from trust store and delete the key |

## Threat model

| Threat | Mitigation |
|---|---|
| Stolen private key | Key is on disk at mode 0600 in OS-protected app data dir. On Windows we use DPAPI when available. On macOS and Linux we set `chmod 0600` + restrictive ACL. |
| Attacker uses our CA to MITM other domains | The CA is install-time scoped to localhost-only proxy use; we recommend operators set `extendedKeyUsage = serverAuth` and pin via `nameConstraints` to the listed upstream hosts (`name_constraints.yaml`). |
| Proxy bypassed (user unsets `HTTPS_PROXY`) | Detected at the egress firewall / DNS RPZ layer — provider DNS resolves to the corp egress gateway which logs and rejects. Pair with the audit heartbeat from the browser extension to detect gaps. |

## Uninstall

```bash
praesidio-edge-proxy uninstall-ca
pipx uninstall praesidio-edge-proxy   # or brew uninstall, etc.
```

This removes the CA from the OS trust store **and** deletes the private
key. There is no undo — the key is regenerated from scratch on next
install.
