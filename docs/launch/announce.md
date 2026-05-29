# Launch announcement — Praesidio 1.0

> Drafts for the 1.0 cut. Tone is sober/instrumental — not hype.
> Pick the appropriate variant per channel; do **not** publish anything
> here until the `v1.0.0` tag is on the remote and the release workflow
> has produced signed artefacts (cosign + CycloneDX SBOM + SLSA-3
> provenance).

---

## Long form — blog post / docs landing

### Praesidio 1.0 — an open-source AI Security Control Plane

We're cutting Praesidio 1.0 today. It's an Apache-2.0 control plane that
sits in front of every LLM, vector store, and agent in your enterprise,
and applies the same DLP discipline your CASB applies to email and
SaaS — only it understands **semantics**, not just strings.

**What it does, concretely**

- **Inspects every prompt, response, embedding, and tool call** through a
  layered DLP pipeline: regex + Presidio NER + secrets detectors + a
  prompt-injection classifier + semantic rules.
- **Anonymises reversibly** — tokenisation (AES-256-GCM vault, HKDF
  per-tenant keys), FF3-1 format-preserving encryption, or redaction —
  policy-selectable per entity. Break-glass detokenise is a two-step
  audited action with a required ticket id and a 30-second auto-hide.
- **Enforces policy as code** — YAML + CEL, signed cosign bundles,
  git-versioned, race-safe hot-reload, lintable via
  `praesidio-policy lint`.
- **Routes to any LLM** — OpenAI, Anthropic, Azure OpenAI, Bedrock
  (SigV4), Ollama, Mistral, and any OpenAI-compatible endpoint. Per-key
  and per-`(tenant, model)` token-per-minute rate limits.
- **Writes a hash-chained audit log** — every decision keyed by request,
  Merkle-rootable, with a `praesidio-audit verify` CLI to prove integrity.
- **Ships a calm, instrument-like operator UI** — events, lineage DAGs,
  policy simulator, detokenise modal, command palette, keyboard
  shortcuts. Light-first ivory + indigo, Geist Sans/Mono, a11y AAA.

**Why now**

Traditional DLP looks for strings; AI leaks happen semantically. A
developer pastes a stack trace that names a customer. A copilot
summarises a deal memo into a Slack channel. An agent retrieves a
document that belonged to a different tenant. Praesidio is built for
exactly that class of risk, with the operator ergonomics of Linear and
the supply-chain hygiene of a modern open-source project.

**What 1.0 means**

- 196 gateway tests passing, real-LLM E2E cassette suite in CI.
- Signed release pipeline (cosign keyless + CycloneDX SBOM + SLSA-3
  provenance per image, per chart).
- Production Helm overlay, External Secrets / Vault / Sealed Secrets
  runbooks, backup + DR runbooks, SLO burn-rate alerting.
- K8s `ValidatingAdmissionPolicy` and Gatekeeper templates that block
  Pods which mount cloud credentials *and* set an env var pointing at a
  known LLM provider (bypass via an explicit annotation).
- Threat-model audit, SECURITY.md with disclosure SLA + safe-harbour,
  OpenSSF Scorecard, CodeQL on every PR.

**What's not in 1.0** (deliberate, called out in `docs/roadmap.md`)

- Signed agent capability tokens + sandboxed tool execution — the
  runtime half (tool-call allowlist) landed; the broker is architected.
- Production Qdrant ACL backend — the connector ships with an in-memory
  ACL, sufficient for evaluation; production deployments configure a
  real store.
- UI internationalisation beyond English + Spanish.

**Get started**

```bash
git clone https://github.com/<org>/praesidio
cd praesidio
docker compose up -d
bash scripts/demo.sh   # expect 6/6 PASS
```

The full docs site is at `docs/`, or run `make docs` to serve it
locally. The `docs/getting-started.md` walkthrough takes about 10
minutes from clone to first audited request.

Apache-2.0. Built in the open. Security disclosures go through GitHub
PVR per `SECURITY.md`.

---

## Short form — HN / Lobsters / Reddit r/netsec

> **Show HN: Praesidio — open-source AI Security Control Plane (Apache-2.0)**
>
> Drop-in OpenAI-compatible gateway that does semantic DLP, reversible
> tokenisation (FF3-1 + AES vault), policy-as-code (YAML + CEL, cosign
> signed), hash-chained audit, and routes to OpenAI / Anthropic / Azure
> / Bedrock / Ollama. 196 gateway tests, real-LLM cassette CI, signed
> releases (cosign + SBOM + SLSA-3), K8s admission policies, prod Helm
> chart, backup/DR runbooks. Light-first ivory+indigo UI inspired by
> Linear/Stripe Docs.
>
> Why we built it: traditional DLP looks for strings; AI leaks happen
> semantically. A copilot summarising a deal memo into Slack is the
> same risk class as an exfil email, but no existing tool will catch
> it. Praesidio does.
>
> `docker compose up -d && bash scripts/demo.sh` → audited prompt in
> under 5 minutes.
>
> Repo: https://github.com/<org>/praesidio · Docs: <docs-link>

---

## Tweet / X thread (5 posts)

1. Praesidio 1.0 is out. Apache-2.0, open-source AI Security Control
   Plane. Semantic DLP, reversible anonymisation, policy-as-code, audit
   chain, calm operator UI. Built for the world where every employee
   has 12 LLM tabs open. 🧵

2. The thesis: traditional DLP looks for strings. AI leaks happen
   semantically. A copilot summarising a customer deal memo into Slack
   is the same risk class as an exfil email — but your CASB can't see
   it. Praesidio can.

3. Under the hood: OpenAI-compatible gateway, Presidio NER + secrets +
   prompt-injection classifier, reversible tokenisation (AES-256-GCM
   vault, FF3-1 FPE), YAML+CEL policy, hash-chained audit, OpenAI /
   Anthropic / Azure / Bedrock / Ollama routing.

4. Operator UX is the part I'm proudest of. Light-first ivory canvas,
   indigo accent, Geist Sans/Mono. Lineage DAGs, policy simulator,
   detokenise modal with required ticket id + 30s auto-hide, command
   palette, `?` for keyboard shortcuts. a11y AAA pass.

5. 196 gateway tests, real-LLM cassette CI, signed releases (cosign +
   CycloneDX SBOM + SLSA-3), prod Helm chart, K8s admission, External
   Secrets runbooks, backup + DR runbooks. Apache-2.0.
   `docker compose up -d` and you're running.
   👉 https://github.com/<org>/praesidio

---

## GitHub Release notes — copy for the v1.0.0 release page

> # Praesidio 1.0.0
>
> The first stable release of the Praesidio AI Security Control Plane.
> Apache-2.0, production-shaped, signed end-to-end.
>
> ## Highlights
>
> - **Gateway**: OpenAI-compatible (chat, completions, embeddings,
>   Anthropic messages, Bedrock SigV4, Ollama). Per-key and per-(tenant,
>   model) TPM rate limits. Token + cost metering.
> - **DLP**: layered detection (regex + Presidio NER + secrets +
>   prompt-injection classifier + semantic rules). FF3-1 FPE,
>   AES-256-GCM tokenisation vault with HKDF per-tenant keys.
> - **Policy as code**: YAML + CEL, signed cosign bundles, race-safe
>   hot-reload, `praesidio-policy lint`.
> - **Audit**: hash-chained, Merkle-rootable, `praesidio-audit verify`
>   CLI. SIEM webhook (HMAC) + Splunk HEC sink.
> - **Vectors**: pgvector + Qdrant connectors with scan-on-write +
>   retrieval ACL.
> - **K8s admission**: ValidatingAdmissionPolicy + Gatekeeper templates
>   block Pods that mount cloud creds *and* point at an LLM provider.
> - **UI**: events table, lineage DAG view, policy simulator,
>   detokenise modal (ticket required, 16-char justification, 30s
>   auto-hide, explicit 429 / Retry-After branch), command palette,
>   `?`-triggered keyboard-shortcuts dialog, a11y AAA, EN + ES.
> - **Supply chain**: cosign keyless signatures, CycloneDX SBOM, SLSA-3
>   provenance attestations per image and per Helm chart. CodeQL +
>   OpenSSF Scorecard on every PR.
> - **Ops**: production Helm overlay, External Secrets / Vault /
>   Sealed Secrets runbooks, backup + DR runbooks, SLO burn-rate
>   alerts with linked runbooks.
>
> ## Verifying this release
>
> ```bash
> cosign verify-blob \
>   --certificate-identity-regexp 'https://github.com/<org>/praesidio/' \
>   --certificate-oidc-issuer https://token.actions.githubusercontent.com \
>   --signature praesidio-1.0.0.sig praesidio-1.0.0.tar.gz
>
> # SBOM
> syft praesidio:1.0.0 -o cyclonedx-json | jq .
>
> # SLSA-3 provenance
> slsa-verifier verify-image praesidio:1.0.0 \
>   --source-uri github.com/<org>/praesidio \
>   --source-tag v1.0.0
> ```
>
> Full recipe: [`docs/security/supply-chain.md`](docs/security/supply-chain.md).
>
> ## Known caveats (called out, not bugs)
>
> - Agent broker (signed capability tokens + sandboxed tool execution)
>   is architected; the runtime half (tool-call allowlist) landed.
>   See `docs/architecture/07-agent-governance.md`.
> - Qdrant connector ships an in-memory ACL backend by default;
>   production deployments must configure a real ACL store, documented
>   in the module docstring.
> - UI i18n covers English + Spanish; further locales deferred to 1.1
>   per `docs/roadmap.md`.
>
> ## Changelog
>
> See [`CHANGELOG.md`](CHANGELOG.md) for the full enumeration of every
> item that landed in 1.0.
>
> ## Disclosure
>
> Security issues: GitHub Private Vulnerability Reporting per
> [`SECURITY.md`](SECURITY.md). 90-day disclosure SLA, safe-harbour
> clause, explicit scope.
>
> ## Acknowledgements
>
> Built on the shoulders of Presidio, cosign, SLSA, OpenSSF Scorecard,
> CycloneDX, Alembic, FastAPI, Next.js, Geist, and the broader open
> security community.

---

## Pre-publish checklist

- [ ] `v1.0.0` tag pushed to the remote
- [ ] `release.yml` workflow green (cosign + SBOM + SLSA-3 all attached)
- [ ] `gh release view v1.0.0` shows signed artefacts and SBOMs
- [ ] `<org>` placeholder replaced in every variant
- [ ] `<docs-link>` placeholder replaced in the HN/Reddit short form
- [ ] Status badge in `README.md` flipped from `1.0-ready` to `1.0.0`
- [ ] `CHANGELOG.md` `[Unreleased]` promoted to `[1.0.0] — <date>`
- [ ] First-light verification by a fresh clone in a clean VM: full
      `docker compose up` boot and `bash scripts/demo.sh` 6/6
