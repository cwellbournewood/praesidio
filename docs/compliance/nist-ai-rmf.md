# NIST AI Risk Management Framework — mapping

NIST AI RMF 1.0 (Jan 2023) + AI 600-1 GenAI Profile (Jul 2024).

## Core functions

| Function | Subcategory | Section |
|---|---|---|
| **GOVERN** | GV-1 Policies, processes | Policy bundles as code; PR review; signed |
| | GV-6 AI risk management roles | RBAC roles map to NIST role taxonomy |
| **MAP** | MP-1 Context established | Decision context recorded per request |
| | MP-3 Categorisation | Findings + sensitivity classification per request |
| **MEASURE** | MS-2 Risks identified | Per-tenant FP/decision dashboards; detector versioning |
| | MS-3 Methods documented | Detector spec in `04-semantic-dlp.md`; benchmarks in `docs/benchmarks/` |
| **MANAGE** | MN-1 Risks prioritised | Severity in audit; SOAR routes on severity |
| | MN-4 Responses to risk | Block / transform / route — chosen by policy |

## GenAI Profile (AI 600-1) controls

| Risk | Section response |
|---|---|
| Confabulation | n/a — Section is not a model. Output DLP detects regurgitation. |
| Dangerous / violent / hateful content | Output DLP can be extended with content classifiers via policy |
| Data privacy | Anonymiser + retention + DPIA evidence pack |
| Environmental impact | Cost & token telemetry; model router cost budgets |
| Harmful bias | Lineage allows post-hoc analysis per cohort |
| Human-AI configuration | Approval workflows in agent broker |
| Information integrity | Output DLP + lineage |
| Information security | Threat model + cryptography + audit chain |
| Intellectual property | Code detection + trade-secret lexicons |
| Obscene / abusive | Same as content classifiers |
| Value chain | Signed bundles, signed MCP manifests |
