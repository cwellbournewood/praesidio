# RFP Traceability Matrix

Maps every numbered requirement from the source RFP
(*AI Security Control Plane & Semantic DLP Platform*) to a Praesidio component,
document, or backlog item.

Status legend:
- ✅ **shipped** — working code in this repo
- 🟦 **architected** — fully specified, scaffolded, partially implemented
- 🟧 **roadmap** — designed, not yet implemented in this repo

| RFP § | Requirement | Status | Where |
|---|---|---|---|
| 1 | Executive summary (semantic-aware DLP, runtime governance, agent containment, dynamic policy, model routing, observability, lineage, audit, real-time enforcement) | ✅/🟦 | [docs/architecture/00-overview.md](architecture/00-overview.md) |
| 2.1 | Prevent unauthorised leakage into AI systems | ✅ | gateway DLP pipeline |
| 2.2 | Govern sanctioned + unsanctioned environments | 🟦 | discovery service (roadmap-stubbed) |
| 2.3 | Semantic understanding of prompts/outputs/memory/retrieval | ✅ | [architecture/04-semantic-dlp.md](architecture/04-semantic-dlp.md) |
| 2.4 | Dynamic policy decisions on identity/sensitivity/jurisdiction/model trust | ✅ | [architecture/03-policy-engine.md](architecture/03-policy-engine.md) |
| 2.5 | Govern agentic AI + tool execution | 🟦 | [architecture/07-agent-governance.md](architecture/07-agent-governance.md) |
| 2.6 | Hybrid arch (SaaS / private / sovereign / local / edge) | ✅ | provider adapters + deploy modes |
| 2.7 | Forensic-grade observability + lineage reconstruction | ✅ | [architecture/06-audit-lineage.md](architecture/06-audit-lineage.md) |
| 2.8 | Minimise operational friction + false positives | ✅ | confidence thresholds + simulation mode |
| 3 | Coverage: public LLMs / enterprise AI / IDE AI / API / agents / MCP / local / RAG / SaaS / autonomous | ✅/🟦 | adapters shipped for OpenAI/Anthropic/Azure/Bedrock/Ollama; **IDE AI shipped 1.1** (VS Code + JetBrains extensions + local CA proxy covers Cursor/Claude Code/Continue/aider/Cline/Copilot CLI/Zed); MCP + agents architected |
| 4.1 | AI Security Gateway (API proxying, identity-aware routing, TLS inspection, request/response interception, semantic inspection, prompt/output transformation, token-level enforcement, audit, model routing, policy enforcement, capability mediation) | ✅ | [services/gateway](../services/gateway) |
| 4.1 (transports) | REST / WebSocket / gRPC / streaming / bidirectional | ✅/🟦 | REST + SSE streaming shipped; WS + gRPC architected |
| 4.2 | Distributed enforcement (endpoints / browsers / proxies / API GW / K8s / SaaS / inference / vector) | ✅ | Edge clients (browser MV3, VS Code, JetBrains, local CA proxy) — see [docs/edge-rfp.md](edge-rfp.md), [edge-coverage-matrix.md](edge-coverage-matrix.md) |
| 4.2 (offline) | Centralised policy, decentralised enforcement, offline caching, edge | ✅ | policy bundle is a signed tarball, gateway caches locally |
| 4.3 | HA — active-active, horizontal scale, multi-region, fail-open/closed, graceful degradation, 99.99% | ✅ | stateless gateway, Postgres + Redis for state, fail-mode config |
| 5 | AI discovery & inventory (apps, APIs, infra, tooling) | 🟧 | discovery service interface defined; reference uses egress logs |
| 6.1 | Semantic understanding engine — inspect prompts/outputs/files/RAG/embeddings/chunks/memory/tool calls/multimodal | ✅/🟦 | text shipped; file + multimodal architected |
| 6.1 (detection capabilities) | Regex / entity extraction / semantic classification / transformers / embedding similarity / contextual risk / multilingual / code / source classification / trade secret / PHI-PII / financial | ✅ | [architecture/04-semantic-dlp.md](architecture/04-semantic-dlp.md) |
| 6.2 | FP reduction — contextual scoring, baselines, adaptive thresholds, tuning, feedback loops, semantic similarity reduction; target <2% | ✅ | per-policy thresholds + analyst feedback API |
| 7.1 | Agent runtime governance (tool mediation, runtime policy, syscall obs, fs/browser/shell/network/memory/capability) | 🟦 | [architecture/07-agent-governance.md](architecture/07-agent-governance.md) — interface + sandbox sketch |
| 7.2 | Capability-based security — scoped, signed, time-bound, revocable, auditable | 🟦 | capability token spec (JWT-based) in agent doc |
| 7.3 | MCP tool discovery, trust scoring, signing, sandboxing, approval workflows | 🟦 | MCP registry spec in agent doc |
| 8.1 | Model registry (approved/blocked/local/sovereign/trusted) with metadata (jurisdiction, provider, provenance, retention, privacy, safety) | ✅ | [architecture/08-model-routing.md](architecture/08-model-routing.md) |
| 8.2 | Dynamic routing (sensitivity/role/geo/compliance/risk/latency/cost) | ✅ | model-router rules in policy DSL |
| 9.1 | Vector DB governance — discovery, embedding inspection, sensitivity classification, retrieval auth, chunk ACLs, tenant isolation; Pinecone/Weaviate/Milvus/pgvector/OpenSearch/Chroma/FAISS | 🟦 | [architecture/09-rag-vector.md](architecture/09-rag-vector.md); pgvector reference adapter |
| 9.2 | Memory governance (TTL, semantic expiry, retrieval auditing, segmentation, sensitive memory prevention, lineage) | 🟦 | memory governor spec in RAG doc |
| 10 | End-to-end lineage (prompt origin, retrieved context, tool outputs, embeddings, memory writes, transformations, generated outputs) + crypto provenance + immutable logs + reconstruction + semantic inheritance | ✅/🟦 | [architecture/06-audit-lineage.md](architecture/06-audit-lineage.md); hash-chained append-only log shipped |
| 11 | Detection engineering — prompt injection, jailbreak, stealth exfiltration, mass summarisation, anomalous prompt, credential extraction, embedding harvesting, agent lateral movement, covert signalling, capability escalation, abnormal retrieval; rule-based + ML + graph + baselining | ✅/🟦 | jailbreak + prompt injection + secret extraction detectors shipped; behavioural baselining architected |
| 12 | Endpoint & runtime — EDR / browser telemetry / process / GPU / container / K8s admission; Win/macOS/Linux/K8s | ✅/🟦 | Edge: browser MV3 + VS Code + JetBrains + local CA proxy (Win/Mac/Linux) shipped; admission controller chart in `deploy/helm/`; EDR integration via webhook |
| 13 | Compliance — EU AI Act / GDPR / CRA / HIPAA / ISO 27001 / SOC 2 / NIST AI RMF; evidence gen, attestation, audit exports, explainability, retention, sovereignty | ✅ | [docs/compliance/](compliance/) |
| 14.1 | Zero trust, mTLS, RBAC/ABAC, crypto signing, HW-backed secrets, tenant isolation, secure enclave | ✅/🟦 | mTLS + RBAC + KMS shipped; enclave optional |
| 14.2 | No-retention, ephemeral, field tokenisation, reversible pseudonymisation, secure redaction, encrypted memory | ✅ | [architecture/05-anonymization.md](architecture/05-anonymization.md) |
| 15 | Perf — <150ms inspection / <5% streaming overhead / horizontal scale / >100k events/s / multi-tenant | 🟦 | targets + benchmark harness; current bench numbers in `docs/benchmarks.md` |
| 16 | Deploy — SaaS / on-prem / air-gap / sovereign / hybrid; AWS / Azure / GCP / K8s / OpenShift / bare metal | ✅ | docker-compose + Helm + Terraform; air-gap notes in deploy doc |
| 17 | APIs — REST / GraphQL / streaming / SIEM / SOAR; integrations — Purview / CrowdStrike / Sentinel / Splunk / Elastic / Okta / Entra / Zscaler / Netskope / Palo Alto / GitHub / GitLab | ✅/🟦 | REST + streaming + Splunk/Sentinel sinks shipped; GraphQL + others architected |
| 18 | Centralised mgmt / policy-as-code / Terraform / GitOps / version-controlled policies / simulation / staged rollout | ✅ | YAML bundles, git-versioned, simulation mode, canary routes |
| 19 | Future — multimodal / multi-agent / local accel / federated / edge / MCP / decentralised agents | 🟦 | documented in [architecture/00-overview.md](architecture/00-overview.md#future) and ADRs |
| 20 | Vendor response artefacts (diagrams, threat model, perf, security design, compliance maps, latency, scale, FP bench, red-team, governance, roadmap) | ✅ | all in `docs/` |
| 21 | Evaluation weights (semantic DLP 20% / agent runtime 20% / scale 15% / detection 10% / integrations 10% / compliance 10% / arch maturity 10% / ops 5%) | n/a | scoring artefact in [docs/evaluation-self-score.md](evaluation-self-score.md) |
| 22 | Strategic vision: unified control plane over models / prompts / agents / tools / memory / embeddings / runtime / semantic data movement | ✅/🟦 | the whole repo |
