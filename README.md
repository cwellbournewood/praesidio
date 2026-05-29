# Praesidio

**The AI Security Control Plane.** Semantic DLP, reversible anonymization, and runtime
governance for every prompt, response, embedding, and agent action in the enterprise.

> Trustworthy AI, at enterprise scale.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-4F46E5.svg)](LICENSE)
[![Spec: RFP-mapped](https://img.shields.io/badge/spec-RFP--mapped-059669.svg)](docs/rfp-traceability.md)
[![Status: 1.0-ready](https://img.shields.io/badge/status-1.0--ready-059669.svg)](#status)
[![CI](https://github.com/cwellbournewood/praesidio/actions/workflows/ci.yml/badge.svg)](https://github.com/cwellbournewood/praesidio/actions/workflows/ci.yml)
[![CodeQL](https://github.com/cwellbournewood/praesidio/actions/workflows/codeql.yml/badge.svg)](https://github.com/cwellbournewood/praesidio/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/cwellbournewood/praesidio/badge)](https://securityscorecards.dev/viewer/?uri=github.com/cwellbournewood/praesidio)

---

## Why Praesidio

Traditional DLP looks for strings. AI leaks happen *semantically* — a developer
pastes a stack trace that names a customer; a copilot summarises a deal memo into a
RAG index; an agent quietly emails a vendor list. Praesidio sits in front of every
LLM call, every retrieval, and every tool invocation, and answers three questions
before any of them touch a model:

1. **What is in this payload?** — entities, secrets, source code, regulated data,
   intent.
2. **Is this user allowed to send this to this model in this jurisdiction?**
3. **Can we keep the request useful by anonymising sensitive parts and putting
   them back on the way out?**

Yes → forward, log, lineage.
No → block or transform, with a signed audit record.

## Architecture at a glance

```
   server-side                                 ┌─────────────────────────┐
   apps / agents / CI ─────────────────────►   │   Praesidio Gateway     │ ──► OpenAI / Anthropic
                                               │                         │ ──► Azure OpenAI / Bedrock
   Edge clients ──┬─► browser ext     ──►  │  ┌──────────┐  ┌─────┐  │ ──► Gemini / Cohere / Mistral
   (ChatGPT, Claude.ai,│  /v1/scan              │  │ Policy   │  │ DLP │  │ ──► Ollama / vLLM
   Gemini, Copilot...)│  /v1/restore           │  │ Engine   │◄─┤Engine│ │ ──► sovereign / local
                      │                        │  └────┬─────┘  └──┬──┘  │
   Cursor / Claude   ─┴─► local CA proxy  ──►  │       │           │     │
   Code / Continue /    (praesidio-edge-       │   ┌───▼───────────▼──┐  │
   aider / Copilot CLI  proxy, mitm-style,     │   │ Anonymizer +     │  │
   / Zed (via HTTPS_    per-machine CA)        │   │ Token Vault      │  │
   PROXY)                                      │   └────────┬─────────┘  │
                                               └────────────┼────────────┘
   VS Code / JetBrains ──► native extension                 │
   (scan-selection, ────► /v1/scan ────────────────────────┤
   diagnostics, tokenise)                                   │
                                          ┌────────────────┼────────────────┐
                                          ▼                ▼                ▼
                                    ┌──────────┐   ┌──────────────┐  ┌───────────┐
                                    │ Postgres │   │  Redis vault │  │  Admin UI │
                                    │ audit +  │   │ (placeholder │  │ (Next.js) │
                                    │ lineage  │   │  ↔ secret)   │  │           │
                                    └──────────┘   └──────────────┘  └───────────┘
```

Full diagrams: [`docs/architecture/`](docs/architecture/).
Edge clients: [`docs/edge-rfp.md`](docs/edge-rfp.md).

## Quick start

```bash
# 1. clone
git clone https://github.com/cwellbournewood/praesidio.git && cd praesidio

# 2. bring up the stack (gateway + postgres + redis + ui)
cp .env.example .env
docker compose up --build

# 3. point any OpenAI client at the gateway instead of api.openai.com
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=praesidio-demo-key

# 4. send a prompt with PII — watch it get tokenised
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user","content":"Email john.smith@acme.com about invoice 4471"}]
  }'

# 5. open the admin UI (events, policies, models, simulator)
open http://localhost:3000

# 6. (optional) full observability stack — Grafana on :3001
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# 7. (optional) Keycloak overlay for OIDC dev
docker compose -f docker-compose.yml -f docker-compose.oidc.yml up -d

# 8. run the smoke demo
bash scripts/demo.sh
```

## What's in the box

| Component | Status | Location |
|---|---|---|
| OpenAI-compatible proxy gateway | working | [`services/gateway`](services/gateway) |
| Anthropic / Azure / Ollama adapters | working | [`services/gateway/praesidio_gateway/proxy`](services/gateway/praesidio_gateway/proxy) |
| Policy engine (YAML, policy-as-code, hot-reload) | working | [`services/gateway/praesidio_gateway/policy`](services/gateway/praesidio_gateway/policy) |
| Shadow mode (decide-but-forward) | working | `policy.spec.mode: shadow` |
| Semantic DLP (regex + Presidio + secrets + code + ML classifier) | working | [`services/gateway/praesidio_gateway/dlp`](services/gateway/praesidio_gateway/dlp) |
| Reversible tokenisation + Redis token vault | working | [`services/gateway/praesidio_gateway/anonymize`](services/gateway/praesidio_gateway/anonymize) |
| Streaming response DLP (chunk-boundary safe) | working | same |
| Format-preserving encryption (FF3-1) | working | same |
| Per-tenant Redis token-bucket rate-limit | working | [`services/gateway/praesidio_gateway/middleware`](services/gateway/praesidio_gateway/middleware) |
| Audit log + lineage (Postgres, hash-chained) | working | [`services/gateway/praesidio_gateway/audit`](services/gateway/praesidio_gateway/audit) |
| `praesidio-audit verify` chain-tamper CLI | working | [`services/gateway/praesidio_gateway/cli`](services/gateway/praesidio_gateway/cli) |
| SIEM webhook + Splunk HEC egress (HMAC-signed) | working | [`services/gateway/praesidio_gateway/audit/sinks`](services/gateway/praesidio_gateway/audit/sinks) |
| Admin API (events, policies, simulate, detokenise, reload) | working | [`services/gateway/praesidio_gateway/api/admin`](services/gateway/praesidio_gateway/api/admin) |
| Admin UI (events, policies, models, lineage, simulator, settings) | working | [`services/ui`](services/ui) |
| Observability overlay (Tempo + Loki + Prometheus + Grafana) | working | [`docker-compose.observability.yml`](docker-compose.observability.yml) |
| Keycloak OIDC overlay | working | [`docker-compose.oidc.yml`](docker-compose.oidc.yml) |
| Helm chart (HA + NetworkPolicies + ExternalSecrets) | working | [`deploy/helm`](deploy/helm) |
| Terraform reference modules (AWS / Azure / GCP) | working | [`deploy/terraform`](deploy/terraform) |
| Signed policy bundles (cosign keyless + OCI distribution) | working | [`scripts/policy_publish.sh`](scripts/policy_publish.sh) |
| Red-team regression harness | working | [`scripts/redteam`](scripts/redteam) |
| Compliance report generator | working | [`scripts/compliance_report.py`](scripts/compliance_report.py) |
| Docs site (Astro Starlight) | working | [`docs-site/`](docs-site/) — `make docs` |
| **Alembic-managed schema migrations** | working | [`services/gateway/alembic`](services/gateway/alembic) |
| **AWS Bedrock adapter (SigV4)** | working | [`services/gateway/praesidio_gateway/proxy/bedrock.py`](services/gateway/praesidio_gateway/proxy/bedrock.py) |
| **Per-API-key + per-(tenant, model) TPM rate limits** | working | [`services/gateway/praesidio_gateway/middleware/rate_limit.py`](services/gateway/praesidio_gateway/middleware/rate_limit.py) |
| **Token + cost metering (Prometheus + audit; per-model price book)** | working | [`services/gateway/praesidio_gateway/obs/metering.py`](services/gateway/praesidio_gateway/obs/metering.py) |
| **Tool-call allowlist enforcement (agent governance)** | working | [`services/gateway/praesidio_gateway/policy/tool_calls.py`](services/gateway/praesidio_gateway/policy/tool_calls.py) |
| **Detokenise hardening (ticket id + justification + per-tenant 429)** | working | [`services/gateway/praesidio_gateway/api/admin`](services/gateway/praesidio_gateway/api/admin) |
| **Prompt-injection classifier** | working | [`services/gateway/praesidio_gateway/dlp/detectors/prompt_injection.py`](services/gateway/praesidio_gateway/dlp/detectors/prompt_injection.py) |
| **Race-safe policy hot-reload (watcher + atomic swap)** | working | [`services/gateway/praesidio_gateway/policy/loader.py`](services/gateway/praesidio_gateway/policy/loader.py) |
| **`praesidio-policy lint` CLI** | working | [`services/gateway/praesidio_gateway/cli`](services/gateway/praesidio_gateway/cli) |
| **Vector DB connectors (pgvector + Qdrant, scan-on-write + retrieval ACL)** | working | [`services/gateway/praesidio_gateway/vectors`](services/gateway/praesidio_gateway/vectors) |
| **K8s admission (ValidatingAdmissionPolicy + Gatekeeper)** | working | [`deploy/k8s/admission`](deploy/k8s/admission) |
| **Cassette-driven real-LLM CI** | working | [`services/gateway/tests/cassettes`](services/gateway/tests/cassettes) |
| **Signed release pipeline (cosign + CycloneDX SBOM + SLSA-3 provenance)** | working | [`.github/workflows/release.yml`](.github/workflows/release.yml) |
| **CodeQL + OpenSSF Scorecard + Private Vulnerability Reporting** | working | [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) · [`SECURITY.md`](SECURITY.md) |
| **Production Helm values + secrets runbooks (AWS SM / Vault / Sealed)** | working | [`deploy/helm/praesidio/values.production.yaml`](deploy/helm/praesidio/values.production.yaml) · [`docs/operations`](docs/operations) |
| **Backup / restore + disaster recovery runbooks** | working | [`docs/operations/backup-restore.md`](docs/operations/backup-restore.md) · [`docs/operations/disaster-recovery.md`](docs/operations/disaster-recovery.md) |
| **Edge: `/v1/scan` + `/v1/restore` endpoints** | working | [`services/gateway/praesidio_gateway/api/v1/scan.py`](services/gateway/praesidio_gateway/api/v1/scan.py) |
| **Edge: local CA MITM proxy** (`praesidio-edge-proxy`) — covers Cursor / Claude Code / Continue / aider / Cline / Copilot CLI / Zed | working | [`services/edge-proxy`](services/edge-proxy) · [`docs/operations/edge-proxy-install.md`](docs/operations/edge-proxy-install.md) |
| **Edge: browser extension** (MV3, Chrome/Brave/Edge/Arc) for 6 consumer AI sites | working | [`clients/browser`](clients/browser) · [`docs/operations/browser-extension-install.md`](docs/operations/browser-extension-install.md) |
| **Edge: VS Code extension** (status bar, scan-selection, diagnostics, tokenise quick-fix) | working | [`clients/vscode`](clients/vscode) · [`docs/operations/ide-extension-install.md`](docs/operations/ide-extension-install.md) |
| **Edge: JetBrains plugin** (IDEA / PyCharm / GoLand / WebStorm / Rider / RubyMine / PhpStorm) | working | [`clients/jetbrains`](clients/jetbrains) · [`docs/operations/ide-extension-install.md`](docs/operations/ide-extension-install.md) |
| Agent runtime governance (tool allowlist landed; broker still architected) | partial | [`docs/architecture/07-agent-governance.md`](docs/architecture/07-agent-governance.md) |

The full RFP-to-component traceability matrix lives at
[`docs/rfp-traceability.md`](docs/rfp-traceability.md).

## Documentation

- **[Getting started](docs/getting-started.md)** — install, first request, first policy
- **[Architecture overview](docs/architecture/00-overview.md)** — start here
- **[Operations guide](docs/operations/README.md)** — observability, signed bundles, OIDC
- **[Deployment & coverage](docs/deployment-coverage.md)** — five-PEP rollout, 5-min TTFV, onboarding wizard
- **[Threat model](docs/threat-model.md)** — what we defend, what we don't
- **[Architecture decision records](docs/adr/)** — the why
- **[Compliance mappings](docs/compliance/)** — EU AI Act, GDPR, HIPAA, SOC 2, ISO 27001, NIST AI RMF
- **[Market positioning](docs/market-research.md)** — vs. Microsoft Purview, Nightfall, Lakera, Protect AI, Prompt Security
- **[Design system](docs/design-system.md)** — tokens, components, voice
- **[Edge coverage RFP](docs/edge-rfp.md)** — browser + IDE + CLI rollout spec
- **[Edge coverage matrix](docs/edge-coverage-matrix.md)** — per-client × per-provider status grid
- Live docs site: `make docs` (Astro Starlight on `:4321`)

## Status

Praesidio is **1.0-ready**. The gateway, DLP pipeline, anonymisation, audit/lineage,
admin UI, vector connectors, K8s admission, signed release pipeline, and
backup/DR runbooks are real, tested, and deployable today. Tool-call
governance is enforced; the broader agent broker (signed capability
tokens, sandboxed tool execution) remains architected.

- **Tests**: 196 passing / 9 skipped (Postgres-only) in `services/gateway`;
  UI type-check + lint clean; `bash scripts/demo.sh` green.
- **CI**: CodeQL, OpenSSF Scorecard, Helm-upgrade compatibility, K8s
  admission, RLS, real-LLM cassette tests all gated on PR.
- **Releases**: cosign-signed images and Helm chart, CycloneDX SBOMs,
  SLSA-3 provenance. See [`CHANGELOG.md`](CHANGELOG.md) and
  [`docs/release-process.md`](docs/release-process.md).
- **Security**: vulnerability disclosure via GitHub PVR with 90-day
  SLA — see [`SECURITY.md`](SECURITY.md).

## License

Apache 2.0 — see [LICENSE](LICENSE). Built to be forked, audited, and self-hosted.
