# GDPR — Praesidio control mapping

Regulation (EU) 2016/679. Praesidio is a *processor* of personal data when
it inspects prompts. Mapping below is to the most commonly cited articles
in DPIA contexts.

| Article | Obligation | Praesidio control |
|---|---|---|
| Art. 5(1)(a) Lawfulness, fairness, transparency | Lawful basis recorded | Per-route policy carries lawful basis annotation; surfaced in audit |
| Art. 5(1)(c) Data minimisation | Process only what is necessary | Anonymiser strips/tokenises before forwarding upstream |
| Art. 5(1)(e) Storage limitation | Limited retention | Vault TTL ≤ 24h; per-tenant audit retention policy |
| Art. 5(1)(f) Integrity & confidentiality | Appropriate security | TLS, mTLS, AES-256-GCM vault, RLS, audit chain |
| Art. 17 Right to erasure | Subject deletion | Tenant-scoped subject delete RPC; chain preserved via tombstones |
| Art. 20 Right to portability | Export subject data | `POST /admin/subject/{id}/export` returns sanitised interaction history |
| Art. 25 Data protection by design and default | DPbD | Default fail-closed for restricted classes; default redaction for secrets |
| Art. 28 Processor obligations | DPA-grade contract terms | Self-host deployment removes processor relationship; SaaS mode publishes a DPA template |
| Art. 30 Records of processing | RoPA | Audit log + policy bundle digest = RoPA evidence |
| Art. 32 Security of processing | Technical & organisational measures | See `docs/threat-model.md` |
| Art. 33-34 Breach notification | Detect + notify | Output DLP detects regurgitation; SIEM sinks for SOC |
| Art. 35 DPIA | Required for high-risk processing | Praesidio supplies the inventory of processing operations and impacts |
| Art. 44-49 International transfers | SCCs, adequacy, etc. | Model router enforces jurisdiction-based routing (EU prompts → EU upstreams) |

## Sub-processor model

When Praesidio routes a prompt to an upstream LLM (OpenAI, Anthropic,
Azure), that upstream is a sub-processor. The audit log records which
sub-processor saw which (sanitised) payload, enabling per-vendor reporting.
