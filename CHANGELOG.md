# Changelog

All notable changes to Section will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [`docs/versioning.md`](docs/versioning.md) for the stable-surface definition
and deprecation policy.

## [Unreleased]

_Nothing yet — first commit after 1.0.0._

## [1.0.0] — 2026-05-28

The first stable release of Section. Server-side gateway, layered DLP,
reversible anonymisation, signed audit chain, K8s admission, signed release
pipeline, **and** edge coverage (browser extension, VS Code / JetBrains
plugins, local CA edge-proxy) shipping together.

### Changed — DLP label taxonomy (breaking from pre-1.0 alpha)

The wire labels emitted on every finding moved from
`<detector>.<entity>` (e.g. `presidio.ORG`, `regex.email`,
`secrets.aws_access_key`) to a category-prefixed taxonomy
(`pii.organization`, `pii.email`, `credential.aws_access_key`). Categories
are `pii`, `financial`, `healthcare`, `credential`, `network`, `code`,
`infra`, `behavior`. The category is the first dot-segment.

- **Placeholder grammar tracks the rename.** `<ORG_xxxx>` →
  `<ORGANIZATION_xxxx>`; `<CC_xxxx>` → `<CREDIT_CARD_xxxx>`;
  `<NRP_xxxx>` → `<NATIONALITY_xxxx>`; `<IP_xxxx>` → `<IP_ADDRESS_xxxx>`;
  `<MAC_xxxx>` → `<MAC_ADDRESS_xxxx>`; `<SSN_xxxx>` → `<US_SSN_xxxx>`;
  `<US_DRIVER_LICENSE_xxxx>` → `<US_DRIVERS_LICENSE_xxxx>`. All other
  shorts unchanged (`<EMAIL_xxxx>`, `<PHONE_xxxx>`, `<PERSON_xxxx>`,
  `<IBAN_xxxx>`, `<JWT_xxxx>`, `<UUID_xxxx>`, `<DATE_xxxx>`, etc.).
- **Source of truth: `services/gateway/section_gateway/dlp/display.py`**
  — a single Python module that owns every label's wire id, human name,
  placeholder short, category, default severity, description, and an
  optional example. The TypeScript twin
  (`services/ui/lib/labels.ts`) is held in sync by
  `scripts/check_label_display_sync.py`, wired into `ci.yml`.
- **Detectors emit canonical labels.** `regex.email` and
  `presidio.EMAIL_ADDRESS` now both produce `pii.email` — the policy
  engine's overlap-resolver deduplicates them naturally. The `detector`
  field on each `Finding` still records which engine fired, so
  observability and tuning stay intact.
- **Pipeline routing is now category-aware.** `_build_active` consults a
  category-to-detector map and only loads Presidio (heavy) when at
  least one enabled label is in the Presidio-exclusive set
  (`pii.person`, `pii.organization`, `pii.location`, `pii.nationality`,
  `pii.us_drivers_license`, `pii.date`, `pii.url`,
  `healthcare.medical_license`, `network.ip_address`).
- **Example policies, healthcare overlay, eval suites, and the Helm
  chart's bundled policies** all moved to the new label IDs in this
  release. Operators upgrading from a pre-1.0 alpha must rewrite any
  custom policies — there is no aliasing layer in the policy engine
  itself (a deliberate choice to keep the wire surface clean for
  publication). `examples/policies/detectors.yaml` keeps `aliases:`
  lists that translate Presidio's raw entity-type names (e.g.
  `presidio.EMAIL_ADDRESS`) for operators porting Presidio policies.

### Added — Label display API

- **`GET /admin/labels`** — operator-facing display catalogue. Returns
  the full taxonomy (id, name, short, category, severity, description,
  example) with an ETag and a 1-hour `Cache-Control`. Unauthenticated
  by design; the payload is static across tenants. Consumers: UI,
  SIEM enrichment pipelines, ad-hoc dashboards.
- **UI:** `FindingChip`, the simulator's inline highlight, and the
  recommendations overlay now render the human display name and put
  the wire id, category, severity, and description in the tooltip.
  `FindingChip` accepts `showWireLabel` for policy-authoring contexts
  where the operator needs the technical id.
- **CI:** `Label display sync (Python ↔ TS)` job runs
  `scripts/check_label_display_sync.py` on every push/PR. Fails the
  build if the Python source of truth and `services/ui/lib/labels.ts`
  drift on any of: `id`, `name`, `short`, `category`, `severity`, or
  if a TypeScript description is empty.

### Added — Edge coverage

- **`POST /v1/scan` + `POST /v1/restore`** (gateway) — scan-only endpoints
  for browser and IDE clients. Apply DLP + policy + anonymise, write
  audit row with `upstream="edge-client"` and an `edge_source` transforms
  entry tagging the client / origin URL / model hint. Restore is the
  response-side inverse — tenant + request_id are AAD-bound at the vault
  layer so cross-tenant lookups fail. Tests: `tests/test_v1_scan.py`
  (6 passing).
- **`services/edge-proxy/`** — `section-edge-proxy` — a local CA MITM
  proxy. Auto-generates per-machine 4096-bit RSA root CA on first
  `install-ca`, intercepts 8 upstream LLM provider hosts, scan-rewrites
  bodies via `/v1/scan`, restores via `/v1/restore`. Single feature that
  brings Cursor, Claude Code, Continue, aider, Cline, Copilot CLI, Zed
  into compliance.
- **`clients/browser/`** — Manifest V3 browser extension covering six
  consumer AI sites (chatgpt.com, claude.ai, gemini.google.com,
  copilot.microsoft.com, perplexity.ai, chat.mistral.ai). Page-world
  fetch hook + content-script submit interception. MutationObserver-
  driven response token restoration. OIDC device-code (RFC 8628) + API
  key. 5-minute heartbeat for gap detection in SIEM.
- **`clients/vscode/`** — VS Code extension. Status bar, scan-selection
  + tokenise-selection + toggle-proxy + sign-in commands, sensitive-data
  diagnostics with code-action tokenise quick-fix, recent-decisions tool
  view. SecretStorage for API key / OIDC refresh token.
- **`clients/jetbrains/`** — IntelliJ Platform plugin (covers IDEA,
  PyCharm, GoLand, WebStorm, Rider, RubyMine, PhpStorm, builds 232.0
  through 252.*). Same surface as VS Code via native Action and
  Inspection extensions. PasswordSafe for credentials.
- **`docs/edge-coverage-matrix.md`** — per-client × per-provider status
  grid; CI keeps the PASS cells honest.
- **`docs/operations/edge-proxy-install.md`**, **`browser-extension-install.md`**,
  **`ide-extension-install.md`** — install + operate runbooks.
- **`.github/workflows/edge.yml`** — builds edge-proxy wheel, browser
  `.zip`, VS Code `.vsix`, JetBrains plugin `.zip` on every change to
  `services/edge-proxy/`, `clients/**`, or `services/gateway/.../api/v1/scan.py`.

### Added

- **UI: keyboard-shortcuts help dialog** — press `?` from any page (outside
  form fields) to open a catalogue of every wired-up shortcut. Includes
  global (`?`, `Ctrl/⌘-K`, `Esc`), navigation chords (`G D/E/S/P/M`),
  event-detail finding navigation (`↑/↓/Home/End/Enter`), and lineage-graph
  navigation (`↑/↓/←/→`, `Enter`). Wired into `app/providers.tsx` so it
  travels with every route.
- **UI: `<ErrorCard/>` primitive** at `components/ui/error-card.tsx` —
  danger-toned inline error surface for SWR / fetch failures, complementing
  `<EmptyState/>` (which is reserved for "no data yet" cases).
- **UI: lineage detail route** at `app/lineage/[requestId]/` — DAG
  renderer with right-rail node inspector, lazy-loaded `LineageGraph`,
  keyboard navigation across nodes, link-through to the originating audit
  event when `audit_event_id` is set on the node. Smoke checklist at
  `app/lineage/[requestId]/LINEAGE.md`.

### Changed

- **UI: `DetokeniseModal` hardened** for SOC operator workflows:
  - `ticket_id` is now **required** (was optional) — every reveal must
    link to an open incident.
  - Justification minimum bumped from **10 → 16 characters**.
  - Auto-hide countdown lengthened from **10s → 30s** so operators can
    actually use the revealed value before it disappears.
  - Explicit **HTTP 429 branch** with `Retry-After` countdown — distinct
    from generic errors. Retry button is disabled until the cooldown
    expires.
  - Polite aria-live success string changed to "Reveal logged to audit
    trail." (was "Value revealed — auto-hiding in 10 seconds.").
  - Spanish (`es`) locale updated in lock-step.

### Added (1.0 sprint)

- Real-LLM E2E **cassette suite** (OpenAI + Anthropic, PII + block scenarios)
  driven by JSON fixtures in `services/gateway/tests/cassettes/`.
  Wired into `.github/workflows/e2e.yml`.
- **Alembic** schema migrations under `services/gateway/alembic/`, with
  auto-upgrade at container start (`SECTION_AUTO_MIGRATE=1`, default).
  Legacy SQL retained under `services/gateway/migrations/` only as the
  Postgres `docker-entrypoint-initdb.d` fallback.
- Production-shaped Helm overlay `deploy/helm/section/values.production.yaml`.
- Operations runbooks:
  - `docs/operations/secrets-aws-secrets-manager.md` (External Secrets + IRSA)
  - `docs/operations/secrets-vault.md` (External Secrets + HashiCorp Vault)
  - `docs/operations/secrets-sealed-secrets.md` (Bitnami Sealed Secrets)
  - `docs/operations/backup-restore.md` (Postgres PITR + Redis AOF)
  - `docs/operations/disaster-recovery.md` (vault-loss blast radius, HSM/KMS migration)
  - `docs/operations/recording-cassettes.md` (how to add new E2E fixtures)
- `docs/security/supply-chain.md` — full cosign + SLSA-3 + SBOM verification
  recipes.
- `docs/release-process.md` — step-by-step release procedure.
- `docs/versioning.md` — SemVer + stable-surface definition and deprecation
  policy (HTTP API, policy YAML `apiVersion`, OTel attribute names, env-var
  names, 12-month deprecation window).
- Kubernetes admission policy at `deploy/k8s/admission/`:
  - `ValidatingAdmissionPolicy` (CEL, k8s ≥ 1.30) and the equivalent
    OPA Gatekeeper `ConstraintTemplate` + `Constraint`.
  - Blocks Pods that mount cloud credentials AND set an env var pointing
    at a known LLM provider hostname (bypass via
    `section.dev/admission-bypass=true`).
  - Smoke-tested in CI by `.github/workflows/admission.yml` on kind v1.30.
- GitHub Actions workflows:
  - `.github/workflows/codeql.yml` (Python + JS/TS + Actions, security-extended)
  - `.github/workflows/scorecard.yml` (OpenSSF Scorecard)
  - `.github/workflows/rls.yml` (Postgres-16 service + cross-tenant
    isolation tests)
  - `.github/workflows/admission.yml` (kind + VAP + Gatekeeper)
  - `.github/workflows/helm-upgrade.yml` (install previous chart on kind,
    `helm upgrade` to HEAD, verify rollout + smoke request)
- README badges for CI, CodeQL, and OpenSSF Scorecard.
- Release pipeline signs the Helm chart OCI artefact with cosign keyless
  and attaches signed SHA-256 checksums alongside SBOMs.
- SLSA-3 build provenance attestations per image via
  `slsa-framework/slsa-github-generator`.

### Changed

- `SECURITY.md` rewritten to prefer GitHub Private Vulnerability Reporting,
  with explicit SLA targets, safe-harbour clause, and scope/out-of-scope
  lists.
- Helm chart README references the three secrets walkthroughs and the new
  production values overlay.
- Postgres RLS regression test expanded with cross-tenant write attempts,
  lineage-table coverage, wildcard-tenant verification, and a "no setting
  -> no rows" check via a separate app role.

### Security

- All release artefacts (gateway image, UI image, Helm chart, SBOMs,
  checksums) are now cosign keyless-signed with verifiable GitHub OIDC
  identity. See `docs/security/supply-chain.md`.

## [0.1.0] — 2026-05-27

Initial alpha cut. Gateway, UI, anonymisation, audit chain, lineage,
shadow mode, SIEM webhook, signed policy bundles, Helm chart, Terraform
modules, docs site, observability overlay, Keycloak OIDC overlay,
red-team harness, compliance report generator, kind smoke CI.

[Unreleased]: https://github.com/cwellbournewood/section/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/cwellbournewood/section/releases/tag/v1.0.0
[0.1.0]: https://github.com/cwellbournewood/section/releases/tag/v0.1.0
