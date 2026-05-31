# SOC 2 — Section Trust Services Criteria mapping

| TSC | Common criteria | Section control |
|---|---|---|
| Security (CC) | CC6 Logical & physical access | OIDC, RBAC/ABAC, mTLS, KMS-backed secrets |
| | CC7 System operations | SLOs, dashboards, structured logging, OTel traces |
| | CC8 Change management | Policy bundles via git PR; signed; canary; rollback |
| | CC9 Risk mitigation | Threat model + simulation mode |
| Availability (A) | A1 | HA topology; HPA; PDBs; graceful degradation; multi-region |
| Confidentiality (C) | C1 | Anonymisation, key management, tenant isolation, no-retention modes |
| Processing Integrity (PI) | PI1 | Audit chain; bundle digest; deterministic decision evaluation |
| Privacy (P) | P1-P8 | Lineage, retention controls, subject access RPC, GDPR mapping |

## Evidence

`POST /admin/exports/soc2` returns a date-ranged evidence pack:
- access reviews (role assignments + timestamps),
- change log (policy bundle history),
- incident timeline (audit events with severity ≥ warning),
- key rotation history,
- backup verification log.
