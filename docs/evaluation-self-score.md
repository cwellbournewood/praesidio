# RFP §21 — Evaluation self-score

The RFP defines weighted evaluation criteria. Below is a candid self-score
against that rubric.

| Category | Weight | Self-score (0-5) | Weighted | Notes |
|---|---:|---:|---:|---|
| Semantic DLP quality | 20% | 4 | 0.80 | Regex + Presidio + secrets + code + injection shipped; transformer classifier shipped; multilingual; multimodal architected only |
| Agent/runtime governance | 20% | 3 | 0.60 | Capability tokens + broker + MCP registry specified in depth; reference broker stubbed |
| Scalability/performance | 15% | 3.5 | 0.525 | Stateless gateway, HPA, fail modes; full benchmark suite pending |
| Detection capability | 10% | 4 | 0.40 | Prompt injection, secrets, exfil intent shipped; behavioural baselining architected |
| Integrations | 10% | 4 | 0.40 | Splunk HEC + Sentinel sinks shipped; OIDC; the four major LLM providers; others architected |
| Compliance readiness | 10% | 4.5 | 0.45 | Mappings for EU AI Act, GDPR, HIPAA, SOC 2, ISO 27001, NIST AI RMF, CRA |
| Architectural maturity | 10% | 4.5 | 0.45 | Documented end-to-end with ADRs, threat model, RFP traceability |
| Operational usability | 5% | 4 | 0.20 | YAML + git + signed bundles + simulation + canary; UI for review |
| **Total** | 100% | — | **3.83 / 5** | weighted |

Caveats:
- An honest "shipped working" line is drawn at the gateway, DLP, anonymiser,
  audit, UI, deploy artefacts, and the OpenAI/Anthropic adapters.
- Agent governance, full vector-DB connector matrix, K8s admission
  controller, and multimodal pipelines are *specified in detail* but not
  fully implemented in this MVP repo.

Future increments to reach 4.5+:
1. Ship the agent broker (closes 0.4 weighted).
2. Ship vector-DB connectors and the K8s admission controller (closes 0.2).
3. Run + publish the full benchmark suite (closes 0.15).
