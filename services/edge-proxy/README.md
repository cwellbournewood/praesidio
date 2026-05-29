# Praesidio Edge Proxy

> Local CA MITM proxy that routes LLM-API traffic from CLIs / IDEs
> through the Praesidio gateway for scan, mask, and restore.

`praesidio-edge-proxy` is the **Lane E** piece of [Praesidio's edge
coverage](../../docs/edge-rfp.md). It runs as a local HTTPS proxy
on `127.0.0.1:8888` (configurable) and intercepts requests to a fixed
allowlist of LLM provider hosts. For each request, it:

1. Extracts the prompt text from the provider-specific JSON body.
2. POSTs the prompt to the gateway's `/v1/scan` endpoint.
3. Replaces sensitive data with placeholder tokens (or blocks the
   request entirely, returning the gateway's `praesidio_blocked` JSON
   to the upstream client).
4. Forwards the rewritten request to the real provider.
5. On the response side, walks the body for placeholders and calls
   `/v1/restore` to swap originals back in — including for streaming
   (SSE) responses, with chunk-boundary-safe placeholder handling.

The proxy is a thin client of the gateway — no DLP, anonymisation, or
audit logic runs in the proxy itself. Reuse of the gateway's
`/v1/scan` + `/v1/restore` API means edge audit rows are
indistinguishable from gateway-originated ones (modulo the
`upstream="edge-client"` tag and the `edge_source` transform entry).

## Threat model

See the edge-proxy row in [`docs/edge-rfp.md`](../../docs/edge-rfp.md#threat-model-deltas-vs-docsthreat-modelmd):

> **MITM proxy CA cert used by attacker** — Per-machine CA is
> generated locally and never leaves the machine; private key in OS
> keychain (Windows DPAPI / macOS Keychain / Linux libsecret). Cert is
> non-exportable. CA install requires admin on Windows and `sudo` on
> macOS/Linux.

## Intercepted hosts

| Host | Provider | Endpoints scanned |
|---|---|---|
| `api.openai.com` | OpenAI | `/v1/chat/completions`, `/v1/completions`, `/v1/responses` |
| `api.anthropic.com` | Anthropic | `/v1/messages` |
| `generativelanguage.googleapis.com` | Google | `:generateContent`, `:streamGenerateContent` |
| `api.cohere.ai` | Cohere | `/v1/chat`, `/v2/chat`, `/v1/generate` |
| `api.mistral.ai` | Mistral | `/v1/chat/completions`, `/v1/fim/completions` |
| `api.perplexity.ai` | Perplexity | `/chat/completions` |
| `api.groq.com` | Groq | `/openai/v1/chat/completions` |
| `api.deepseek.com` | DeepSeek | `/v1/chat/completions`, `/chat/completions` |

Any other host is passed through unmodified.

## Install

### Windows

```powershell
pip install praesidio-edge-proxy
# Open a NEW elevated PowerShell window:
praesidio-edge-proxy install-ca
```

`install-ca` mints a 4096-bit RSA root under `%LOCALAPPDATA%\Praesidio\`
(private key with `0600` ACL via `O_CREAT|O_WRONLY|O_TRUNC` + mode
`0600`; user-only by virtue of the path) and runs
`certutil -addstore -f Root` to add it to the LocalMachine trust
store.

### macOS

```sh
pip install praesidio-edge-proxy
sudo praesidio-edge-proxy install-ca
```

Stores the root under `~/Library/Application Support/Praesidio/` and
adds it to the System keychain via `security add-trusted-cert`.

### Linux (Debian / Ubuntu / Fedora / RHEL / openSUSE)

```sh
pip install praesidio-edge-proxy
sudo praesidio-edge-proxy install-ca
```

Stores the root under `$XDG_DATA_HOME/praesidio/` (default
`~/.local/share/praesidio/`) and either:

* copies into `/usr/local/share/ca-certificates/` + runs `update-ca-certificates`
  (Debian-family), or
* copies into `/etc/pki/ca-trust/source/anchors/` + runs `update-ca-trust`
  (Fedora-family).

## Run

```sh
praesidio-edge-proxy start \
    --gateway https://gateway.local:8000 \
    --api-key "$PRAESIDIO_API_KEY" \
    --listen 127.0.0.1:8888
```

Then point any CLI / IDE that respects `HTTPS_PROXY` at the proxy:

```sh
export HTTPS_PROXY=http://127.0.0.1:8888
export HTTP_PROXY=http://127.0.0.1:8888
# Now this goes through Praesidio:
aider --model claude-3-5-sonnet "explain ./auth.py"
```

VS Code / Cursor / Claude Code / Continue / Cline / Copilot CLI / Zed
AI all respect `HTTPS_PROXY` by default. JetBrains IDEs need
`Settings > Appearance & Behavior > System Settings > HTTP Proxy >
Manual proxy configuration`.

## Sample log output

```
$ praesidio-edge-proxy start --gateway https://gateway.local:8000 --api-key sk-...
Praesidio edge proxy v0.1.0
  listening on 127.0.0.1:8888
  gateway     https://gateway.local:8000
  hosts       api.openai.com, api.anthropic.com, generativelanguage.googleapis.com, api.cohere.ai, api.mistral.ai, api.perplexity.ai, api.groq.com, api.deepseek.com
  status      /home/op/.local/share/praesidio/edge-proxy-status.json

Proxy server listening at *:8888
[127.0.0.1:51220] HTTP(S) connect to api.openai.com:443
[127.0.0.1:51220] CONNECT api.openai.com:443 HTTP/1.1
[127.0.0.1:51220] POST https://api.openai.com/v1/chat/completions HTTP/1.1
  proxy.scan_decided host=api.openai.com action=mask request_id=9b2c1f...
[127.0.0.1:51220]  << 200 1.4kB
  proxy.restore_done request_id=9b2c1f... restored=2 missing=[]
```

## Status / stop

```sh
$ praesidio-edge-proxy status | jq
{
  "running": true,
  "pid": 12345,
  "listen": "127.0.0.1:8888",
  "gateway": "https://gateway.local:8000",
  "hosts_intercepted": ["api.openai.com", "..."],
  "decisions": 42,
  "blocks": 1,
  "masks": 17,
  "allows": 24,
  "last_decision": {"host": "api.openai.com", "action": "mask", "request_id": "9b2c..."}
}

$ praesidio-edge-proxy stop
```

## Uninstall

```sh
# (Windows: from elevated PowerShell)
# (macOS / Linux: with sudo)
praesidio-edge-proxy uninstall-ca
```

This removes the cert from the trust store and deletes the on-disk
private key + cert + combined PEM. Restart any process that loaded
the old cert (browsers, agents) so it picks up the new trust state.

## Container variant

Operators who want the gateway and proxy as a single sidecar can build
the included `Dockerfile`:

```sh
docker build -t praesidio-edge-proxy:dev .
docker run --rm -p 8888:8888 \
    -e PRAESIDIO_EDGE_GATEWAY_URL=https://gateway.local:8000 \
    -e PRAESIDIO_EDGE_API_KEY="$PRAESIDIO_API_KEY" \
    -e PRAESIDIO_EDGE_LISTEN_HOST=0.0.0.0 \
    -v praesidio-ca:/data \
    praesidio-edge-proxy:dev
```

The container expects the CA to be mounted in (`/data`) — in production
the operator generates the CA on a build-host or jumpbox and copies
just `praesidio-ca.crt` + `praesidio-ca.key` into the named volume.

## Development

```sh
cd services/edge-proxy
uv venv .venv
. .venv/bin/activate    # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

Apache-2.0. See [LICENSE](../../LICENSE) at the repo root.
