# EU Cyber Resilience Act — Praesidio mapping

Regulation (EU) 2024/2847. Praesidio is "a product with digital elements".

| Obligation | Praesidio |
|---|---|
| Essential cybersecurity requirements (Annex I) | Threat model + secure-by-default config + signed bundles |
| Vulnerability handling (Art. 13) | `SECURITY.md` with coordinated disclosure; CVE process; SBOM published with each release |
| SBOM | Generated at build via `syft`; published as a release artefact (CycloneDX) |
| Conformity assessment | Self-assessment for class I; CE marking pathway documented |
| Reporting actively exploited vulns (Art. 14) | 24h advisory + 72h notification — coordinated through GitHub Private Vulnerability Reporting per [`SECURITY.md`](../../SECURITY.md) |
| Secure by default | Default policy bundle is fail-closed for restricted classes; default redaction for secrets |
| Default automatic updates | OTA bundle hot-reload with signed verification |
