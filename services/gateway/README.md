# Section Gateway

The data-plane process for Section. FastAPI / asyncio. Accepts OpenAI- and
Anthropic-compatible requests, runs a DLP pipeline + policy engine, applies
anonymisation transforms, forwards to the chosen upstream LLM, restores
placeholders in the response, and writes a hash-chained audit row.

This README targets contributors. For the architectural background read
`../../docs/architecture/02-gateway.md`.

## Layout

```
services/gateway/
├── pyproject.toml          uv-managed; Python ≥3.11
├── Dockerfile              multi-stage (builder w/ uv → slim runtime)
├── migrations/
│   └── 0001_init.sql       audit_events + lineage_* tables (RLS)
├── section_gateway/
│   ├── main.py             FastAPI app + lifespan + middlewares
│   ├── config.py           pydantic-settings
│   ├── auth.py             Principal resolution from API key / OIDC headers
│   ├── state.py            composition root, injected via Depends
│   ├── policy/             models, loader (mtime poll), DSL, engine
│   ├── dlp/
│   │   ├── pipeline.py     concurrent detector orchestrator
│   │   └── detectors/      regex, secrets, code, prompt_injection, presidio
│   ├── anonymize/          tokenizer (placeholders + vault), stream restore,
│   │                       FPE (FF3-1 interface — backend pluggable),
│   │                       Redis-backed AES-256-GCM vault, redactor
│   ├── audit/              SQLAlchemy models, hash chain, batched writer,
│   │                       sinks/splunk_hec.py (no-op unless configured)
│   ├── lineage/            per-request DAG builder
│   ├── proxy/              ProviderAdapter Protocol + openai / anthropic /
│   │                       azure / ollama adapters + registry/router
│   ├── api/v1/             OpenAI-shaped routes (chat, completions, embeddings, models)
│   ├── api/anthropic_v1/   /anthropic/v1/messages
│   ├── api/admin/          health, readyz, metrics, events, policies, lineage, models
│   └── obs/                Prometheus, structlog, OTel
└── tests/                  pytest-asyncio; in-memory SQLite + in-memory vault
```

## Running locally (without Docker)

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
cd services/gateway

# Install deps into a venv.
uv venv .venv
source .venv/bin/activate    # PowerShell: .venv\Scripts\Activate.ps1
uv pip install -e '.[dev]'

# Generate local keys (dev only — production reads them from the env).
export SECTION_ENV=development
export SECTION_VAULT_KEY=$(openssl rand -base64 32)
export SECTION_FPE_KEY=$(openssl rand -hex 16)

# Point at the example bundle.
export SECTION_POLICY_BUNDLE=../../examples/policies

# In-process SQLite + in-memory vault are fine for local exploration:
export DATABASE_URL=sqlite+aiosqlite:///./section.db
export REDIS_URL=

# Run.
uv run section-gateway
# … or: uv run uvicorn section_gateway.main:app --port 8080 --reload
```

Sanity probes:

```bash
curl localhost:8080/healthz                   # liveness
curl localhost:8080/readyz                    # readiness
curl localhost:8080/metrics                   # Prometheus exposition
curl -H 'x-api-key: section-demo-key' localhost:8080/v1/models
```

Send a chat that contains PII:

```bash
curl -s localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'x-api-key: section-demo-key' \
  -d '{"model":"gpt-4o-mini",
       "messages":[{"role":"user","content":"Email alice@example.com"}]}'
```

The audit row should appear at `GET /admin/events`. Use `--print-config` to
dump the resolved settings (with secrets redacted):

```bash
uv run section-gateway --print-config
```

## Testing

```bash
uv run pytest -q
uv run ruff check section_gateway tests
uv run mypy section_gateway     # advisory
```

The tests use **fakeredis-style in-memory vault** and **aiosqlite in-memory**
DB — no external services needed. The e2e test mocks OpenAI with `respx`.

## Adding a detector

1. Drop a module in `section_gateway/dlp/detectors/` exposing
   `async def detect(text: str) -> list[Finding]`.
2. Build `Finding` objects with `section_gateway.dlp.types.make_finding(...)`
   so the sha256 hash discipline is enforced (raw text never persisted).
3. Register the detector in `dlp/pipeline.py` under `_DEFAULT_DETECTORS`
   and decide whether it should be in the always-on fast lane or the
   opt-in lane (set by the policy's `detect.enable` list).
4. Add a test in `tests/test_detectors_<name>.py`.

The pipeline runs every active detector concurrently behind a soft deadline
(`SECTION_DETECTOR_TIMEOUT_SECONDS`); slow detectors that miss the deadline
are skipped and the decision is marked `partial`.

## Adding a provider adapter

1. Implement the `ProviderAdapter` protocol from `proxy/base.py`:

   ```python
   class MyProviderAdapter(ProviderAdapter):
       name = "myprovider"
       async def chat_completion(self, req: UpstreamRequest):
           ...   # return UpstreamResponse, or AsyncIterator[bytes] when req.stream
       async def close(self): ...
   ```
2. Wire it into `proxy/registry.py`'s `_adapter_for()` switch.
3. Add an entry under `endpoints:` and `models:` in your policy bundle's
   `models.yaml` (see `examples/policies/models.yaml`).
4. Bind it to inbound paths via `routes.yaml`.

## Fail modes

Per-route `fail_mode: open|closed` in policy controls behaviour when the DLP
pipeline raises or the vault is unreachable. `closed` returns
`503 X-Section-Reason: section_unavailable`; `open` forwards the original
request and writes an audit row with `degraded=true`.

## Security notes

- The gateway never logs raw matched text — only sha256 hashes (see
  `dlp/types.py::make_finding`).
- The vault key (`SECTION_VAULT_KEY`) and FPE key (`SECTION_FPE_KEY`)
  must come from your KMS in production. In `SECTION_ENV=development` the
  gateway will auto-generate ephemeral keys and log a loud `RuntimeWarning`.
- The audit chain hash binds each row to the prior one per-tenant; tampering
  with any row breaks every subsequent hash.
- The Postgres schema enables RLS on `audit_events` and `lineage_nodes`. Apps
  must `SET section.tenant_id = '<tenant>'` per session.

## Wire format

Inbound is OpenAI-compatible (`/v1/chat/completions`, `/v1/completions`,
`/v1/embeddings`, `/v1/models`) and Anthropic-compatible
(`/anthropic/v1/messages`). All responses include:

- `X-Request-Id` — UUID echoed back for correlation
- `X-Section-Decision` — `allow | transform | block`
- `X-Section-Policy` — id of the policy whose rule fired
- `X-Section-Route` — chosen upstream (provider/model)
- `X-Section-Latency-Ms` — server-side processing latency
