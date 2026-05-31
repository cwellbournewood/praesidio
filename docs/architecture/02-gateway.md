# 02 · Gateway

The gateway is the data-plane process. It speaks LLM-vendor APIs on both sides:
inbound it accepts OpenAI-compatible (and Anthropic-compatible) requests so
existing SDKs work unchanged; outbound it forwards (transformed) requests to the
real upstream chosen by policy.

## Process model

- Stateless. Scale horizontally behind any L7 LB.
- One process per CPU core; async IO with `uvicorn` + `httpx`.
- Per-request lifecycle is fully traced with OpenTelemetry.
- Hot-reloads policy bundles via inotify or a poll loop on the bundle URL.

## Module layout

```
services/gateway/section_gateway/
├── main.py             FastAPI app, middleware, lifespan
├── config.py           pydantic-settings (env + file)
├── auth.py             API-key + OIDC + mTLS principal resolution
├── proxy/
│   ├── base.py         ProviderAdapter protocol
│   ├── openai.py       OpenAI chat/completions, embeddings, models
│   ├── anthropic.py    Anthropic messages, streaming
│   ├── azure.py        Azure OpenAI (api-version, deployments)
│   └── ollama.py       Ollama local
├── policy/
│   ├── models.py       Policy, Rule, Action, Transform (pydantic)
│   ├── engine.py       Evaluator: (Context, Findings) -> Decision
│   ├── loader.py       Bundle loader, signature verifier
│   └── dsl.py          condition expressions
├── dlp/
│   ├── pipeline.py     orchestrates detectors, returns Findings[]
│   ├── detectors/
│   │   ├── regex.py    fast PII / patterns
│   │   ├── secrets.py  detect-secrets + custom keys
│   │   ├── presidio.py spaCy + Presidio analyzer
│   │   ├── code.py     guesslang / heuristics
│   │   ├── prompt_injection.py
│   │   └── semantic.py embeddings-based classifier
│   └── ml/             ONNX models (sentence-transformers MiniLM)
├── anonymize/
│   ├── tokenizer.py    placeholder generator + vault writer
│   ├── vault.py        Redis-backed encrypted KV store
│   ├── fpe.py          FF3-1 format-preserving encryption
│   └── redactor.py     irreversible masking
├── audit/
│   ├── models.py       SQLModel tables
│   ├── writer.py       async batched writer
│   └── chain.py        hash-chain provenance
├── lineage/
│   └── tracker.py      DAG nodes per request
├── api/
│   ├── v1/             OpenAI-shaped routes
│   ├── anthropic/      Anthropic-shaped routes
│   └── admin/          policies, events, lineage, models, health
└── obs/
    ├── metrics.py      Prometheus
    └── tracing.py      OTel
```

## Inbound API surface

| Path | Source-compat | Notes |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI | Streaming via SSE; tool calls supported |
| `POST /v1/completions` | OpenAI | Legacy text completion |
| `POST /v1/embeddings` | OpenAI | Embedded text optionally scanned |
| `GET  /v1/models` | OpenAI | Returns *policy-visible* models for caller |
| `POST /anthropic/v1/messages` | Anthropic | Streaming via SSE |
| `POST /admin/*` | native | Policy, events, lineage, model registry |
| `GET  /healthz` | native | k8s probes |
| `GET  /readyz` | native | depends on DB/Redis/policy bundle |
| `GET  /metrics` | native | Prometheus |

## Streaming

SSE chunks pass through a small state machine that:
1. accumulates partial tokens until it has a re-anonymisation boundary
   (placeholder tokens never break across chunks),
2. restores placeholders with vault lookups,
3. optionally fires *output DLP* in a sidecar coroutine — if a leakage
   detector trips mid-stream, the gateway closes the stream and emits a final
   error chunk per the protocol's conventions.

## Fail modes

Per-route `fail_mode: open | closed` in policy controls behaviour when:
- DLP pipeline raises,
- token vault unreachable,
- upstream LLM 5xx.

`closed` returns `503 section_unavailable` with an explanation header.
`open` forwards the original request and **emits a high-severity audit
event marked `degraded`**. Even fail-open is observable.

## Multi-tenancy

Tenant is derived from the API key or OIDC claim and is part of every
policy lookup and every audit row. Postgres uses row-level security on
`tenant_id`. The token vault namespaces every key with the tenant.

## Performance targets

| Metric | Target | Notes |
|---|---|---|
| p50 inspection latency (no LLM) | < 15 ms | fast detectors only |
| p99 inspection latency (no LLM) | < 80 ms | with semantic classifier on |
| streaming overhead | < 5% added latency | SSE pass-through |
| throughput (single replica, m6i.2xlarge equivalent) | ≥ 5k req/s for short prompts | |
| horizontal scale | linear to ≥ 100k req/s aggregate | stateless |
