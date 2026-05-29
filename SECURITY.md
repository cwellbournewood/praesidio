# Security Policy

## Reporting a vulnerability

We strongly prefer **GitHub Private Vulnerability Reporting** (PVR) for all
security reports against Praesidio:

> https://github.com/cwellbournewood/praesidio/security/advisories/new

PVR routes the report directly to the maintainer security team, opens a
private draft advisory, and lets us coordinate the fix, CVE, and
disclosure timeline without ever creating a public issue.

If GitHub PVR is unavailable to you (e.g. you are reporting from an
account that cannot create advisories), email **security@praesidio.dev**
with the report encrypted to our PGP key:

* **Fingerprint:** `0000 0000 0000 0000 0000  0000 0000 0000 0000 0000`
* **Key:** `https://praesidio.dev/.well-known/pgp-key.txt`
  (also mirrored under `security/pgp.txt` in this repository).

Do not open public GitHub issues, public discussions, or pull requests
that demonstrate the vulnerability. If you have already done so, contact
us via PVR immediately and we will assist in coordinating remediation.

## What to include

Please share, at minimum:

1. Affected component (gateway, UI, Helm chart, Terraform module,
   policy bundle).
2. Version / commit SHA / container digest you tested.
3. Steps to reproduce, including any proof-of-concept payload or
   configuration.
4. Impact assessment (confidentiality, integrity, availability) — your
   best guess is fine; we will validate.
5. Suggested remediation, if you have one.

## Response targets

| Stage | Target |
|---|---|
| Acknowledge receipt | 2 business days |
| Initial triage + severity assignment (CVSS 3.1) | 5 business days |
| Remediation plan shared with reporter | 10 business days |
| Coordinated public disclosure window (default) | 90 days from acknowledgement |

We may shorten the disclosure window for actively-exploited or
trivially-exploitable critical issues, in coordination with the reporter.
We may extend it for issues that require a non-trivial upstream change
(e.g. in a dependency we do not maintain) — extensions are agreed with
the reporter in writing.

## Safe harbour

We will not pursue or support legal action against researchers who:

* Make a good-faith effort to avoid privacy violations, destruction of
  data, and interruption or degradation of our services.
* Only interact with accounts they own or with explicit permission of
  the account holder.
* Do not exploit a vulnerability beyond the minimum necessary to confirm
  it.
* Give us a reasonable time to remediate before publishing.
* Comply with all applicable laws.

## Supported versions

Pre-1.0 alpha: only the latest minor receives security fixes. After 1.0,
the two most recent minor versions receive security fixes; see
`docs/versioning.md` for the full policy.

## Scope

In scope:
- Praesidio gateway, UI, agent broker SDK, Helm chart, Terraform
  modules, official container images, policy bundle reference
  implementation.
- The default policy bundle and detector packs.
- The published documentation site insofar as it can be used to harm
  users (XSS, SSRF, etc.).

Out of scope:
- Vulnerabilities in upstream LLM providers (OpenAI, Anthropic, Azure
  OpenAI, etc.) — report those to the provider directly.
- Vulnerabilities in user-authored policy bundles or custom detectors.
- Social engineering against project maintainers or contributors.
- Issues that require a malicious local administrator on the host
  running the gateway.

## Cryptography

See [docs/threat-model.md](docs/threat-model.md) for the threat model and
[docs/architecture/05-anonymization.md](docs/architecture/05-anonymization.md)
for vault and key handling. The token vault uses AES-256-GCM with
per-tenant HKDF-derived keys; format-preserving encryption uses NIST
SP-800-38G FF3-1. Audit chains are SHA-256 hash-chained per tenant.

## SBOM and supply-chain artefacts

Each release publishes:

* CycloneDX SBOM per container image (gateway, UI).
* Cosign keyless signatures on every image and on the Helm chart OCI
  artefact.
* SLSA-3 build provenance attestation.
* Signed SHA-256 checksums for the chart tarball and SBOMs.

Verification commands and the full supply-chain model:
[`docs/security/supply-chain.md`](docs/security/supply-chain.md).
