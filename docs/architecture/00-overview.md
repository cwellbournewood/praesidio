# 00 · Architecture Overview

## 1. What Praesidio is

Praesidio is an **AI Security Control Plane**: a policy decision point and policy
enforcement point that sits on the path between users / applications / agents and
the LLMs, embeddings stores, and tools they want to use.

It is deliberately *not* a model. It is the layer that decides, in real time:

- **Admit** the request as-is.
- **Transform** the request — anonymise PII, redact secrets, strip code, swap to
  a safer model.
- **Block** the request and tell the user why.
- **Log** what happened with cryptographic provenance so an auditor can
  reconstruct the entire interaction six months later.

## 2. Design tenets

| # | Tenet | Implication |
|---|---|---|
| 1 | **Semantic, not just lexical** | Detection must understand intent and entities, not only regex hits. |
| 2 | **Reversible by default** | Anonymisation must preserve answer quality — the user gets a real answer about *John* even if the model only ever saw `<PERSON_a1b2>`. |
| 3 | **Policy as code** | Every decision is reproducible from a YAML file in git. No clickops. |
| 4 | **Fail-closed for regulated data, fail-open for noise** | Configurable per route; defaults are safe. |
| 5 | **Audit must be useful in court** | Every decision links to the policy version, detector versions, and signed payload digest. |
| 6 | **Drop-in, not rip-and-replace** | OpenAI-compatible API surface. Existing SDKs work by changing one env var. |
| 7 | **Local-first option** | Operates fully air-gapped with local models, local embeddings, local detection. No phone-home. |
| 8 | **Observability is a feature, not an afterthought** | Every component emits structured logs, OTel traces, and Prometheus metrics. |

## 3. High-level component map

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE                                   │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────┐  │
│  │ Admin UI     │   │ Admin API    │   │ Policy bundle (git)          │  │
│  │ (Next.js)    │◄──┤ (FastAPI)    │◄──┤ YAML, signed, versioned      │  │
│  └──────────────┘   └──────────────┘   └──────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ pub/sub (policy hot-reload)
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        DATA PLANE — GATEWAY                              │
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │  Inbound (REST / SSE / WS / gRPC)                              │     │
│   │  OpenAI-compatible · Anthropic-compatible · native            │     │
│   └────────────────────┬───────────────────────────────────────────┘     │
│                        ▼                                                 │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│   │ Identity     │─►│ Policy       │─►│ DLP Pipeline │──┐                │
│   │ resolver     │  │ engine       │  │ (detect)     │  │                │
│   │ OIDC/mTLS/   │  │ (decide)     │  └──────────────┘  │                │
│   │  API key)    │  └──────┬───────┘                    │                │
│   └──────────────┘         │                            ▼                │
│                            │                   ┌──────────────────┐      │
│                            │                   │ Anonymiser       │      │
│                            │                   │ tokenise / FPE / │      │
│                            │                   │ redact / route   │      │
│                            │                   └────────┬─────────┘      │
│                            │                            │                │
│                            ▼                            ▼                │
│                   ┌─────────────────────────────────────────────┐        │
│                   │ Model router (per-policy upstream binding)  │        │
│                   └────────────────────┬────────────────────────┘        │
│                                        │                                 │
│                                        ▼                                 │
│                    ┌────────────────────────────────────┐                │
│                    │  Provider adapter (streaming aware)│                │
│                    │  OpenAI · Anthropic · Azure · Ollama                │
│                    └────────────────────┬────────────────────────────────┘
│                                         ▼                                │
│                          ┌──────────────────────────┐                    │
│                          │ De-anonymiser (response) │                    │
│                          └──────────────┬───────────┘                    │
│                                         ▼                                │
│                          ┌──────────────────────────┐                    │
│                          │ Audit + lineage emitter  │──► Postgres        │
│                          └──────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────┐
                  │ SIEM / SOAR / Splunk / Sentinel sink │
                  └──────────────────────────────────────┘
```

## 4. Request lifecycle (annotated)

```
1.  POST /v1/chat/completions arrives.
2.  Identity resolver pins a Principal { user, tenant, groups, device, network }.
3.  Policy engine builds a Decision Context:
       { principal, route, model_id, headers, jurisdiction_hint }
4.  Body is fed to the DLP pipeline:
       a. fast-path detectors (regex, secrets, code) — sub-ms
       b. NLP detectors (Presidio + spaCy) — entity spans
       c. semantic classifier (transformer or embedding) — labels + score
       d. policy-relevant findings emitted as Findings[]
5.  Policy engine evaluates rules against Decision Context + Findings:
       → action: allow | transform | block
       → transforms: { tokenise PERSON, FPE EMAIL, redact SSN, ... }
       → upstream: { provider, model, region }
       → fail_mode: open | closed
6.  Anonymiser applies transforms, producing:
       sanitised_payload + reversal_map (stored in token vault, TTL-bound)
7.  Model router forwards to chosen upstream (streaming preserved).
8.  Response chunks pass through de-anonymiser, which restores placeholders
       using reversal_map.
9.  Output may itself be re-scanned (output DLP), and may trigger a block on
       leakage attempts (e.g. model regurgitating training-set PII).
10. Audit event written with: request_id, policy_version, detector_versions,
       findings hashes, applied transforms, upstream model, latency, decision,
       signed digest of (sanitised input, restored output).
```

## 5. Trust boundaries

```
  ┌─ untrusted ─────────────────┐    ┌─ semi-trusted ──────────────┐
  │ user, browser, IDE, agent   │ ── │ Praesidio Gateway           │
  └─────────────────────────────┘    │  (TLS termination,          │
                                     │   identity binding,         │
  ┌─ trusted ──────┐                 │   DLP, vault)               │
  │ Policy bundle  │ ──────────────► │                             │
  │ (signed)       │                 └────────┬────────────────────┘
  └────────────────┘                          │ mTLS
                                              ▼
                                  ┌─ semi-trusted ─────────┐
                                  │ Upstream LLM provider  │
                                  └────────────────────────┘
```

The vault key, FPE key, and policy signing key are the three secrets whose
compromise breaks the security model. They live in KMS/HSM in production; the
gateway only ever holds short-lived data-encryption keys derived from them.

## 6. Where the rest of the docs live

| Topic | Doc |
|---|---|
| Data flow & sequence diagrams | [01-data-flow.md](01-data-flow.md) |
| Gateway internals | [02-gateway.md](02-gateway.md) |
| Policy engine & DSL | [03-policy-engine.md](03-policy-engine.md) |
| Semantic DLP | [04-semantic-dlp.md](04-semantic-dlp.md) |
| Anonymisation & token vault | [05-anonymization.md](05-anonymization.md) |
| Audit & lineage | [06-audit-lineage.md](06-audit-lineage.md) |
| Agent governance (architected) | [07-agent-governance.md](07-agent-governance.md) |
| Model registry & routing | [08-model-routing.md](08-model-routing.md) |
| RAG / vector DB controls | [09-rag-vector.md](09-rag-vector.md) |
| Deployment & operations | [10-deployment.md](10-deployment.md) |
| Threat model | [../threat-model.md](../threat-model.md) |
| RFP traceability | [../rfp-traceability.md](../rfp-traceability.md) |
| Compliance mappings | [../compliance/](../compliance/) |
| ADRs (decisions) | [../adr/](../adr/) |
