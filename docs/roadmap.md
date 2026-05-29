# Praesidio roadmap

A rolling, public view of what's landing and what we're considering. The
canonical scrum board lives on
[GitHub Projects](https://github.com/orgs/praesidio-project/projects/1)
([placeholder URL] — replace with the real board on first release).

Items move right→left as scope is committed; items in **2.0 candidates**
are not promises.

## Conventions

| Stage | Meaning |
|---|---|
| **stable** | Public API, semver-protected. Breaking changes require a major. |
| **graduating** | API frozen this release, will be stable next release. |
| **preview** | Behind a feature flag. API may change. Not for production. |
| **experimental** | Under active design. May be removed. |
| **candidate** | On the table, not committed. |

## 1.0 — *now (stable surface)*

Released: target Q3 2026.

| Area | Status | Notes |
|---|---|---|
| OpenAI / Anthropic / Azure OpenAI / Ollama providers | stable | `/v1/chat/completions`, `/v1/embeddings`, `/anthropic/v1/messages`, `/openai/deployments/.../chat/completions`, `/api/chat` |
| DLP detectors: regex, secrets, code, prompt-injection | stable | full coverage matrix in [`docs/benchmarks/coverage.md`](benchmarks/coverage.md) |
| Anonymisation: tokenisation, FF3-1 FPE, redaction | stable | reversible per request scope or 1h TTL |
| Policy bundle: YAML + CEL, cosign-signed, OCI publish | stable | example bundles in `examples/policies/` |
| Audit log: append-only, sha256 hash-chained, `praesidio-audit verify` | stable | RLS-tested for multi-tenant isolation |
| OIDC integration | stable | Okta / Entra / Google walkthroughs in [`docs/operations/oidc-*.md`](operations/) |
| Observability: Prometheus, OTLP, Loki + Grafana dashboards (incl. SLO) | stable | `make observability` |
| Shadow mode | stable | per-policy `mode: shadow` to dry-run without enforcing |
| Streaming responses with span restoration | stable | chunk-boundary safe (6 split scenarios tested) |
| Deploy: Docker Compose (dev), Helm chart (prod), Terraform refs (AWS/Azure/GCP) | stable | HA + NetworkPolicies + ExternalSecrets in the chart |
| SIEM webhook + Splunk HEC sink | stable | HMAC-signed webhooks; HEC token via secret |
| Performance baseline | stable | committed numbers in [`docs/perf-baseline.md`](perf-baseline.md) |

## 1.1 — *next minor (Q4 2026)*

> **Edge coverage shipped in 1.0** (originally planned here, pulled
> forward 2026-05-28). See [`edge-rfp.md`](edge-rfp.md) for the spec
> and [`edge-coverage-matrix.md`](edge-coverage-matrix.md) for the
> per-client × per-provider grid.

Theme: **connectors graduate, agent governance graduates.**

| Area | Today | Plan | Owner |
|---|---|---|---|
| Vector-DB connectors (Pinecone, pgvector, Weaviate, Qdrant) | preview | Graduate to stable; add Milvus + Chroma; namespace-aware policies | TBA |
| Agent governance hooks (tool-call argument scan, response-side scan) | preview | Stable surface; native MCP server adapter; per-tool policy controls | TBA |
| Provider: Bedrock (Claude, Llama 3, Mistral via AWS) | shipped 1.0 | (graduated) | gateway |
| Per-tenant token vault key rotation CLI | preview | `praesidio-vault rotate --tenant <id> --new-key <ref>` with re-wrap audit row | TBA |
| Web UI: policy authoring (visual rule builder + CEL test pad) | experimental | Ship as default UI tab; preserve YAML round-trip | TBA |
| Custom detector SDK (Python plugin protocol) | experimental | Stable plugin ABI; example detector cookiecutter; `make plugin-sdk-test` | TBA |
| Rate limit: token-bucket per principal | stable | Add hierarchical buckets (tenant → group → user); export burst headroom metric | TBA |

## 1.2 — *(Q1 2027)*

Theme: **non-text data, non-HTTP ingress**.

| Area | Status | Notes |
|---|---|---|
| Image DLP (OCR + entity scan on `image_url` content) | candidate | hook into the chat-completions multimodal path; same Finding model |
| File-attachment DLP (PDF / DOCX / spreadsheet via Apache Tika or unstructured) | candidate | `/v1/files` scan endpoint + inline on chat attachments |
| gRPC ingress for high-throughput agents | candidate | bidi streaming chat over Connect / grpc-web; reuse same policy engine |
| Cohere / Mistral / Vertex AI providers | candidate | each is a thin adapter; mostly auth + response shape mapping |
| Kubernetes admission v1 webhook (block deploys that ship known-bad prompts in env) | candidate | reuses the redteam corpus + policy engine |

## 2.0 candidates *(not committed)*

| Area | Notes |
|---|---|
| Sandboxed JS / Python policy execution (today: CEL only) | wider expressiveness; needs hardened runtime |
| EDR-style local agents that intercept browser extensions / desktop LLM clients | new attack surface; separate threat model |
| Differential-privacy noise injection for analytics responses | research-grade; would need a real privacy budget tracker |
| FedRAMP / ISO 42001 attestation pack | depends on customer demand |
| Self-tuning thresholds via Bayesian optimisation on the eval harness | post-1.0 once we have enough real-world FPR/FNR telemetry |

## How to influence the roadmap

* Open a GitHub Discussion under the **Roadmap** category.
* Propose an ADR in `docs/adr/` for any item that would change a public
  contract (HTTP API, policy schema, audit row format).
* Vendor / sponsor escalations: see [`docs/maintainers.md`](maintainers.md)
  for the CoC enforcement chain — the same chain handles roadmap
  arbitration when consensus stalls.

## Release cadence

* **Minor**: every quarter, on the first Tuesday of the quarter's
  middle month (Feb / May / Aug / Nov).
* **Patch**: as needed; security patches within 7 days of triage.
* **Major**: ~yearly; coordinated with at least one full minor of
  deprecation warnings (see [`docs/versioning.md`](versioning.md)).
