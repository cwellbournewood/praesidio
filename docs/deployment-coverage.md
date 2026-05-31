# Deployment & coverage

No single install point catches every way an employee, app, or agent might
call an AI system. Section's job is to make the *union* of enforcement
points cheap to deploy, easy to operate, and impossible to silently bypass.

This page explains how Section is installed across an enterprise, in
what order to roll the pieces out, and how the product is engineered for
sub-five-minute Time-To-First-Value (TTFV) on the first install.

## 1. First principles

1. **Coverage is a union, not a product.** Stack thin Policy Enforcement
   Points (PEPs) that share one control plane, so a gap in one layer is
   closed by another and policy is authored once.
2. **The control plane is the moat, not any single PEP.** Policy, vault,
   audit, lineage, and the DLP / anonymisation engine are centralised.
   PEPs are intentionally dumb — they call `/v1/scan` (or proxy through
   the gateway) and apply the verdict.
3. **Default-deny at the perimeter, default-allow at the desk.** The SWG
   / network egress denies *unsanctioned* AI domains; the sanctioned path
   is wide-open by default and gets narrower as policy is tuned.
4. **TTFV under five minutes, always.** A new operator must, on a single
   laptop, get from `git clone` to a verifiable blocked-prompt audit row
   in under 300 seconds.
5. **Universal detection, observation-led tuning.** Every tenant starts
   with the same default policy and detector catalogue. Industry overlays
   (healthcare, finance, vectors…) are recommended from observed traffic
   rather than picked from a settings screen.

## 2. The five enforcement layers

```
                       ┌───────────────────────────────────────┐
                       │          Section Control Plane       │
                       │  policy · vault · DLP · audit · lineage│
                       └───────────────────────────────────────┘
                                  ▲      ▲      ▲      ▲      ▲
                                  │      │      │      │      │
       ┌──────────────────────────┘      │      │      │      └──────────────────────┐
       │              ┌─────────────────┘      │      └────────────────┐              │
┌─────────────┐ ┌───────────────┐ ┌───────────────────┐ ┌─────────────────┐ ┌────────────────┐
│ 1. Gateway  │ │ 2. Forward    │ │ 3. Browser ext.   │ │ 4. IDE plugin   │ │ 5. MCP / agent │
│   (reverse  │ │   proxy / SWG │ │   + local CA      │ │   (VS Code /    │ │   middleware   │
│    proxy)   │ │   integration │ │   edge-proxy      │ │    JetBrains)   │ │                │
└─────────────┘ └───────────────┘ └───────────────────┘ └─────────────────┘ └────────────────┘
       │                │                   │                    │                    │
       ▼                ▼                   ▼                    ▼                    ▼
  internal apps,    employee web      consumer AI sites,     Cursor / Continue /  Claude Desktop,
  agents, RAG,      traffic to        Cursor / aider /       Cline / Copilot      Cursor agents,
  CI, batch jobs    chat.openai.com,  Claude Code            CLI / Zed            custom MCP apps
                    claude.ai, etc.
```

| # | PEP | Traffic shape | Install vector | Block point | Failure mode | Status |
|---|-----|---------------|----------------|-------------|--------------|--------|
| 1 | **Reverse-proxy gateway** | API SDK calls (`api.openai.com`-shaped) | env var swap (`OPENAI_BASE_URL`) | server-side, hard | fail-closed (configurable) | shipped |
| 2 | **Forward proxy / SWG** | TLS-MITM browser → AI web UI | MDM-pushed root CA + SWG rule | server-side, hard | fail-open (SWG-default) | alpha |
| 3 | **Browser extension + local CA edge-proxy** | client-side textarea + `HTTPS_PROXY` | Chrome Enterprise / Edge GPO; `pip install section-edge-proxy` | client-side, soft | telemetry-only fallback | shipped |
| 4 | **IDE plugin** | VS Code / JetBrains commands + diagnostics | VSIX / JetBrains marketplace | client-side, inline | telemetry-only fallback | shipped |
| 5 | **MCP / agent middleware** | MCP tool calls + agent prompts | install as MCP server, wrap agent runtime | server-side, hard | fail-closed | alpha (tool allowlist enforced; capability broker architected) |

### 2.1 PEP 1 — Reverse-proxy gateway *(canonical)*

The gateway is an OpenAI-API-compatible HTTPS server. Any code that uses
the OpenAI Python/JS SDK, the Anthropic SDK, LangChain, LlamaIndex, the
Bedrock client libraries, etc. is redirected by changing one environment
variable:

```bash
OPENAI_BASE_URL=https://section.corp/v1
OPENAI_API_KEY=<section-issued-key>
```

The gateway authenticates the principal, inspects the body, transforms
(tokenise / redact / FPE) or blocks, forwards to the real provider with
the operator's upstream key, de-tokenises the response, and writes a
signed audit row.

This is the highest-coverage, lowest-friction PEP for any organisation
whose AI usage flows through code. It is the first thing every install
turns on.

### 2.2 PEP 2 — Forward proxy / SWG integration

A `CONNECT`-aware HTTPS proxy with TLS-MITM. The corp root CA is pushed
via MDM / Intune / Jamf; the SWG (Zscaler, Netskope, Cisco Umbrella, Palo
Alto Prisma, in-house Squid) is configured to forward egress to a
curated list of AI domains through Section.

This is the only layer that catches employees pasting into consumer AI
web UIs without going through an SDK — and the politically hardest to
roll out because it requires MITM and SWG cooperation.

### 2.3 PEP 3 — Browser extension + local CA edge-proxy

For unmanaged devices, BYOD, contractors, and any population where a
network-side MITM is not viable. Two artefacts:

- **Manifest V3 browser extension** (`clients/browser/`) covering
  ChatGPT, Claude, Gemini, Copilot, Perplexity, and Mistral chat. Pushed
  via Chrome Enterprise / Edge `ExtensionInstallForcelist`.
- **`section-edge-proxy`** (`services/edge-proxy/`) — a local CA proxy
  that any `HTTPS_PROXY`-respecting tool can use. One install covers
  Cursor, Claude Code, Continue, aider, Cline, Copilot CLI, and Zed.

Failure mode is telemetry-only: if the client can't reach Section it
logs locally and lets the prompt through, because client-side blocking
that breaks the user's workflow is worse than a missed event.

### 2.4 PEP 4 — IDE plugin

VS Code (`clients/vscode/`) and JetBrains (`clients/jetbrains/`)
extensions add a native surface beyond what the proxy provides: status
bar, scan-selection, tokenise-selection, sensitive-data diagnostics, a
recent-decisions tool view, and OIDC device-code sign-in.

Source code is the #1 leakage category in every customer survey; the
plugin maps cleanly to commit history and reviewer identity.

### 2.5 PEP 5 — MCP / agent middleware

Section ships as an MCP server that wraps tool invocations and as
middleware for the Claude Agent SDK, OpenAI Agents SDK, and LangGraph.
Every tool call, prompt expansion, and inter-agent message is inspected.

The tool-call allowlist is enforced today; the capability-token broker
and sandboxed tool executor are
[architected](architecture/07-agent-governance.md).

## 3. Coverage matrix

The expected rollout: stack as many of these as your population mix
demands.

| Population | Day 1 PEP | Day 30 add | Day 90 add | Steady-state coverage |
|---|---|---|---|---|
| Internal apps, agents, batch jobs, RAG | **1. Gateway** | — | — | 100% (env-var pin in IaC) |
| Managed laptops, on-corp / VPN | — | **2. Forward proxy** | — | ~95% (SWG bypass = the gap) |
| Managed laptops, off-network | — | **3. Browser ext + edge-proxy** | — | ~80% (extension uninstall = the gap) |
| Engineering / IDE | **4. IDE plugin** | — | — | ~90% (assistant misconfig = the gap) |
| Sanctioned chat (e.g. ChatGPT Enterprise) | **1. Gateway (SSO-fronted)** | — | — | 100% |
| Unmanaged / BYOD | — | **3. Browser ext (opt-in)** + SWG block of unsanctioned | — | ~60% (best-effort) |
| Agentic workloads | **1. Gateway** | **5. MCP middleware** | — | 100% within sanctioned agent host |
| Shadow IT | — | **SWG deny-list** funnelling to sanctioned path | — | ~70% (DNS bypass = the gap) |

**Gaps to acknowledge openly.** No vendor catches:

- personal-device, personal-network, personal-account use,
- voice-mode in mobile apps that talk to AI providers over native sockets,
- on-device LLMs running fully offline,
- screenshot-to-LLM workflows where text never enters a textarea.

The honest answer to "what about those" is policy + training, not
technology. The **Coverage** dashboard surfaces the gaps rather than
hiding them.

## 4. Rollout sequence

```
Day 0   ──── single laptop, single curl ─────────────  TTFV: 5 min
Day 1   ──── one team, one repo, gateway in IaC ─────  TTFV: 1 hr
Day 7   ──── org-wide gateway, sanctioned AI only ───  TTFV: 1 day
Day 30  ──── edge-proxy + browser + IDE rollout ─────  TTFV: 1 week
Day 60  ──── SWG forward-proxy live, MITM rolled out  TTFV: 2 weeks
Day 180 ──── MCP + agent middleware in production ───  TTFV: 1 month
```

Each step is independently valuable. Stopping at Day 7 still catches
every API-mediated AI call in the org, which is already 70%+ of most
companies' leakage surface.

## 5. Five-minute Time-To-First-Value

The first install is the single highest-stakes moment in the product's
lifecycle. If it doesn't produce a "huh, that's neat" within five
minutes, the operator closes the tab.

### 5.1 What "first value" means

A single audit row in the UI showing that a real prompt with PII was
intercepted, transformed, and forwarded. Not a hello-world response — a
visible, signed, lineage-attached *decision*.

### 5.2 The 300-second budget

| Step | Budget | Mechanism |
|---|---|---|
| Clone repo | 20 s | `git clone --depth 1` |
| Bring up stack | 90 s | `docker compose up -d` against pre-built GHCR images |
| Health check | 10 s | `/healthz` polled by the onboarding wizard |
| First request | 30 s | one-liner `curl` against the gateway |
| Inspect audit row | 30 s | wizard auto-deep-links to the event |
| Demo script | 120 s | three scripted prompts: PII, secret, IBAN |
| **Total** | **≈ 300 s** | end-to-end, hands-on-keyboard |

### 5.3 Engineering choices that buy us the budget

- **Pre-built images on GHCR.** Local Dockerfile builds (Presidio +
  spaCy alone is ~2 GB) are the single largest enemy of TTFV. The
  `quickstart` profile pulls signed images instead of building.
- **One profile per intent.** `docker compose --profile quickstart`
  brings up gateway + Redis + UI only; postgres is replaced with SQLite
  in this profile so the migration step is skipped.
- **Mock-mode UI.** If the gateway is unreachable, the UI degrades to
  synthetic data so the operator can navigate the product while the
  gateway is still pulling images.
- **Single-tenant default key.** `SECTION_API_KEYS=section-demo-key`
  is baked into `.env.example`; the operator never has to mint a key for
  the quickstart.
- **Inline demo runner in the wizard.** The onboarding page POSTs the
  three demo prompts directly from the browser — no terminal required
  for the first round of value.
- **Deep-linked event drilldown.** Each demo prompt's resulting audit
  row is linked from the wizard to `/events?id=…` so the operator lands
  on *the* row they care about.

### 5.4 What the wizard does *not* do

- It does not configure SSO, RBAC, or tenants on the quickstart path.
  Those are Day-1+ concerns and live in `/settings`.
- It does not push to a cluster, run Terraform, or mint TLS certs. The
  quickstart is laptop-local by design; cloud deployment is a separate
  guided flow (§6).
- It does not silently rewrite shell config files. Every change is
  shown as a copy-pasteable block; the operator pastes it themselves.

## 6. Three deployment shapes

The onboarding wizard's first screen asks the operator which posture
they want and routes accordingly.

### 6.1 Local demo *(< 5 min)*

Single laptop, Docker Desktop or Colima. SQLite audit log, embedded
Redis, no TLS, demo API key. Used for evaluation, demos, local policy
development.

```bash
docker compose --profile quickstart up -d
```

### 6.2 Self-hosted *(< 30 min)*

Full `docker-compose.yml` with Postgres + Redis + Gateway + UI, TLS via
Caddy sidecar, OIDC backed by the operator's IdP, persistent volumes.
For small-team production, air-gapped environments, regulated workloads.
Same compose file, no `--profile` flag.

### 6.3 Cloud / Kubernetes *(< 4 hr)*

Helm chart with HA gateway, External-Secrets-backed vault,
NetworkPolicies, PodSecurity, HPA, PDBs, Prometheus + Grafana
dashboards. Terraform reference modules for AWS / Azure / GCP create
the cluster, KMS keys, RDS Postgres, ElastiCache Redis, and the
Section Helm release. For real production.

The onboarding wizard surfaces the right docs at the right time. It
does **not** try to be a cluster installer — Helm + Terraform are the
right tools for that.

## 7. Day-1+ operability

Once the gateway is up, the operator graduates from the wizard to the
console:

- **Coverage** — which PEPs are reporting events, last-seen timestamps,
  and gaps.
- **Connectors** (`/settings?tab=connectors`) — install scripts and
  download links for the forward proxy, browser extension, IDE plugin,
  and MCP middleware. Each connector verifies itself by sending a probe
  event the page auto-detects.
- **Identity** (`/settings?tab=identity`) — OIDC configuration once the
  operator is past the demo.
- **Bundles** — policy bundles are pulled from a signed (cosign) git
  repository; the onboarding wizard's last step is "point Section at
  your policy repo" but it ships with a sane default so this is
  optional.

## 7.5 Detector catalogue & recommendations

Classification is one of the genuinely hard parts of any DLP product —
what counts as "sensitive" varies by jurisdiction, industry, and team.
Section doesn't ask the operator to declare an industry up front,
because (a) most orgs span several, and (b) self-declaration is the
wrong shape of question to front-load on Day 0.

### 7.5.1 The detector catalogue

`examples/policies/detectors.yaml` is the single source of truth that
maps every stable detector ID (`financial.credit_card`,
`pii.nationality`, `credential.aws_access_key`, …) to:

- a human-readable display name,
- a data family (`personal_data`, `health_data`, `payment_data`,
  `financial_data`, `credentials`, `source_code`, `network`,
  `business_confidential`, `intent`),
- regulatory frameworks the finding typically falls under (GDPR, CCPA,
  HIPAA, PCI-DSS, SOX, GLBA, ISO 27001, SOC 2),
- a default sensitivity tier (`public`, `internal`, `confidential`,
  `restricted`),
- a default action (`observe`, `transform`, `redact`, `block`).

The catalogue is consumed by the UI and by the policy bundle compiler,
which refuses to ship a policy referencing an unknown ID.

### 7.5.2 The universal default policy

`examples/policies/policies/0000-universal-default.yaml` enables every
catalogued detector and routes its action off the sensitivity tier:

| Tier | Default action | Examples |
|---|---|---|
| `restricted` | `block` or `redact` | Cloud / SaaS API keys, private keys, SSN, payment cards, GDPR special-category |
| `confidential` | `transform` (tokenise / FPE / redact) | IBAN, JWT, MRN, NPI, ICD-10, CPT, lab values, DOB |
| `internal` | `transform` (reversible session tokens) | Email, phone, person names, locations, UUIDs |
| `public` | `observe` | Organisation names, generic dates |

Every tenant gets this on Day 0. A finance team catches IBANs; a clinic
catches MRNs; a startup catches AWS keys — all from the same bundle,
with no industry switch.

### 7.5.3 Observation-led recommendations

Industry-specific overlays exist (`0100-healthcare.yaml`,
`0005-vectors.yaml`, …) but they are not bundled by default. The
**Recommendations** page watches the audit stream and surfaces a card
the moment evidence warrants it:

> *We've seen 47 medical record numbers and 12 ICD-10 codes in the last
> 24h. The healthcare overlay tightens retention to 2,555 days and
> routes those prompts to a BAA-covered model.*
> **\[Adopt\]  \[Show examples\]  \[Dismiss\]**

A recommendation only appears with named evidence (click through to the
lineage rows that triggered it). Adopting opens a PR against the
operator's policy repo — never a silent change.

## 8. The onboarding wizard

A sequential, persisted-progress flow at `/onboarding`. Six steps; any
user without prior progress is redirected here on first load.

1. **Welcome · pick a path.** Local demo · self-hosted · cloud. The
   selection determines which copy-paste blocks the rest of the wizard
   shows.
2. **Bring it up.** One copy-paste command. The page polls `/healthz`
   and reflects status live (idle → connecting → healthy).
3. **Wire your first client.** Two copy-blocks: `OPENAI_BASE_URL` env
   vars + a `curl` request. A "Run it for me" button POSTs the same
   request from the browser.
4. **Watch it work.** Live event tape filtered to the operator's
   session, with a deep-link to lineage.
5. **Expand coverage.** Cards for PEPs 2–5 with install snippets and
   "remind me later" affordances.
6. **You're live.** Summary screen with next-step links: policy
   authoring, identity, audit export, observability.

Progress is persisted in localStorage so a refresh doesn't lose place.
The wizard can be re-opened from `/settings` any time.

## 9. Anti-patterns we explicitly avoid

- **The 10-step CLI quickstart.** Every additional command halves the
  audience. Section's quickstart is one compose command + one curl.
- **The "configure your tenant first" screen.** Tenancy, RBAC, and SSO
  are Day-1+ concerns; forcing them on Day-0 destroys TTFV.
- **The dark, illegible ops UI.** Section's console is light-first on
  every screen, including the onboarding wizard.
- **The hidden "what about consumer-AI" gap.** The Coverage page
  surfaces uninstrumented populations rather than letting them be
  invisible.
- **The proprietary agent stack.** Section integrates with whatever
  agent framework the customer already uses (Claude Agent SDK, OpenAI
  Agents, LangGraph, MCP). We do not require them to adopt a Section
  runtime.

## 10. Reading guide

- **Operator evaluating the product** → run the onboarding wizard at
  `/onboarding`.
- **Security architect planning rollout** → §§ 2, 3, 4.
- **Platform engineer integrating into IaC** → see
  [`deploy/helm/`](../deploy/helm/) and
  [`deploy/terraform/`](../deploy/terraform/).
- **Developer extending the product** → start with
  [`docs/architecture/00-overview.md`](architecture/00-overview.md).
