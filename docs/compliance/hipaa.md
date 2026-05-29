# HIPAA — Praesidio control mapping

HIPAA Security Rule (45 CFR §164.302–318) and Privacy Rule selected items.
Praesidio is suitable as a control surface for covered entities and
business associates handling ePHI.

| Safeguard | Specification | Praesidio control |
|---|---|---|
| Administrative §164.308(a)(1) | Risk analysis & management | Policy bundles + audit + simulation |
| Administrative §164.308(a)(3) | Workforce security | RBAC roles; OIDC; admin actions audited |
| Administrative §164.308(a)(4) | Information access management | Per-principal policies; sensitivity-aware routing |
| Administrative §164.308(a)(5) | Security awareness | UI prompts & blocked-by-policy reasons act as point-of-use training |
| Administrative §164.308(a)(6) | Security incident procedures | Output DLP + SIEM sinks; incident-grade audit chain |
| Physical §164.310 | Physical safeguards | Inherited from hosting (KMS/HSM recommended) |
| Technical §164.312(a) | Access control, unique user ID, automatic logoff, encryption | OIDC, mTLS, per-tenant key derivation, session TTL |
| Technical §164.312(b) | Audit controls | Hash-chained immutable audit |
| Technical §164.312(c) | Integrity | Bundle signing; audit chain hash; row signatures optional |
| Technical §164.312(d) | Person/entity authentication | OIDC + mTLS |
| Technical §164.312(e) | Transmission security | TLS 1.3 mandatory; mTLS service-to-service |
| Privacy §164.514 | De-identification (Safe Harbor / Expert) | Tokenisation + redaction policies; per-entity transforms for the 18 identifier categories |

## ePHI-specific policy

`examples/policies/healthcare.yaml` is a starter policy: tokenises 17 of the
18 HIPAA Safe Harbor identifiers (the 18th — full-face photographs — is
routed for human review when image inputs are detected), routes all
inference to a BAA-covered upstream (Azure OpenAI with BAA, or local
Ollama), and forces `fail_mode: closed`.
