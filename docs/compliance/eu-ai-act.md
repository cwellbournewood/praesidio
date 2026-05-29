# EU AI Act — Praesidio control mapping

Mapping is to Regulation (EU) 2024/1689 as adopted, focused on the obligations
that fall on **deployers** and **providers** of GPAI / high-risk AI systems
that Praesidio's customers will typically have. Praesidio itself is not an AI
system in the Act's sense; it is a governance control surface that supports
those obligations.

| Article | Obligation (paraphrased) | Praesidio control |
|---|---|---|
| Art. 9 (Risk management) | Continuous risk management across lifecycle | Policy bundles + simulation mode + per-route fail-mode + audit trail allow risk decisions to be made and revisited continuously. |
| Art. 10 (Data & governance) | Training/testing data governance; bias examination | n/a for inference-time controls, but the model registry records `training_provenance` and certifications per upstream model. |
| Art. 12 (Record-keeping) | Automatic logging of events over the lifetime of the system | Audit + lineage (`docs/architecture/06-audit-lineage.md`) — every interaction logged, hash-chained, exportable. |
| Art. 13 (Transparency) | Information to deployers on system capabilities and limitations | Model registry surfaces `privacy`, `retention`, `safety_certifications`. UI Model page shows this to the user issuing the prompt. |
| Art. 14 (Human oversight) | Effective oversight by natural persons | Agent broker approval workflows, simulation mode, decision diffs in the UI. |
| Art. 15 (Accuracy, robustness, cybersecurity) | Accuracy, robustness, attack resistance | DLP includes prompt-injection / jailbreak detectors; capability tokens; sandboxed tools; signed bundles. |
| Art. 26 (Deployer obligations) | Use as intended, monitor operation, human oversight, input data control | Praesidio *is* the input data control layer; outputs/logs power the monitoring. |
| Art. 27 (Fundamental rights impact assessment) | FRIA for high-risk deployments | Audit exports + lineage reconstruction enable FRIA evidence. |
| Art. 50 (Transparency obligations for certain AI systems) | Disclose AI interaction, mark synthetic content | Policy can require output annotation / disclaimers via output transforms. |
| Art. 53 (GPAI providers) | Technical documentation, copyright policy, training summary | n/a — Praesidio is a deployer-side control, but it records which GPAI model was used per request. |
| Art. 55 (Systemic-risk GPAI) | Adversarial testing, incident reporting | Detection engineering hooks (`docs/architecture/04-semantic-dlp.md#detector-taxonomy`) feed the SIEM. |

## Evidence pack

`POST /admin/exports/eu-ai-act` produces a date-ranged bundle containing:
- the active policy bundle digest history,
- per-model registry snapshot,
- audit log slice (sanitised),
- detector + classifier version manifest,
- key rotation log.
