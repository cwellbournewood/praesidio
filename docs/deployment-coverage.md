# Deployment & Coverage

> **The coverage problem.** No single install point catches every way an
> employee, app, or agent might call an AI system. Praesidio's job is to make
> the *union* of enforcement points cheap to deploy, easy to operate, and
> impossible to silently bypass.

This document explains how Praesidio is installed across an enterprise, how
each enforcement point works, in what order to roll them out, and how the
product is engineered for a sub-five-minute Time-To-First-Value (TTFV) on the
first install.

---

## 1. First principles

Four design rules govern every deployment decision in Praesidio.

1. **Coverage is a union, not a product.** You don't pick one PEP (Policy
   Enforcement Point) and hope. You stack thin PEPs that share one control
   plane, so a gap in one layer is closed by another and policy is authored
   once.
2. **The control plane is the moat, not any single PEP.** Policy, vault,
   audit, lineage, and the DLP/anonymisation engine are centralised. PEPs are
   intentionally dumb — they call `/v1/inspect` (or proxy through the gateway)
   and apply the verdict. New PEPs (browser extension, IDE plugin, MCP
   middleware) can be added without re-implementing detection.
3. **Default-deny at the perimeter, default-allow at the desk.** The SWG /
   network egress denies *unsanctioned* AI domains; the sanctioned path is
   wide-open by default and gets narrower as policy is tuned. This avoids the
   classic DLP failure mode where everything is blocked, users route around
   it, and shadow AI explodes.
4. **TTFV under five minutes, always.** A new operator must, on a single
   laptop, get from `git clone` to a verifiable blocked-prompt audit row in
   under 300 seconds. Every onboarding step is measured against that budget.
5. **Universal detection, observation-led tuning.** Every tenant starts
   with the same default policy and the same detector catalogue — there is
   no "pick your industry" screen. Detection runs over a wide-set
   detector catalogue (`examples/policies/detectors.yaml`) where each
   detector carries a sensitivity tier; decisions are keyed off the tier,
   not the tenant's industry. Industry-specific overlays
   (healthcare, vectors, finance…) exist as optional add-ons that
   Praesidio *recommends* once it has observed evidence in real traffic
   — they are never prerequisites for catching the same data.

---

## 2. The five enforcement layers

```
                       ┌───────────────────────────────────────┐
                       │          Praesidio Control Plane       │
                       │  policy · vault · DLP · audit · lineage│
                       └───────────────────────────────────────┘
                                  ▲      ▲      ▲      ▲      ▲
                                  │      │      │      │      │
       ┌──────────────────────────┘      │      │      │      └──────────────────────┐
       │              ┌─────────────────┘      │      └────────────────┐              │
       │              │                        │                        │              │
┌─────────────┐ ┌───────────────┐ ┌───────────────────┐ ┌─────────────────┐ ┌────────────────┐
│ 1. Gateway  │ │ 2. Forward    │ │ 3. Browser ext.   │ │ 4. IDE plugin   │ │ 5. MCP / agent │
│   (reverse  │ │   proxy / SWG │ │   (Chrome / Edge) │ │   (VSCode /     │ │   middleware   │
│    proxy)   │ │   integration │ │                   │ │    JetBrains)   │ │                │
└─────────────┘ └───────────────┘ └───────────────────┘ └─────────────────┘ └────────────────┘
       │                │                   │                    │                    │
       ▼                ▼                   ▼                    ▼                    ▼
  internal apps,    employee web      unmanaged / BYOD       Copilot, Cursor,    Claude Desktop,
  agents, RAG,      traffic to        web sessions           Continue, Cody       Cursor agents,
  CI, batch jobs    chat.openai.com,                                              custom MCP apps
                    claude.ai, etc.
```

Each PEP has a distinct traffic shape, install vector, blast radius, and
failure mode. The table below is the operator's cheat-sheet.

| # | PEP | Traffic shape | Install vector | Block point | Failure mode | Status |
|---|-----|---------------|----------------|-------------|--------------|--------|
| 1 | **Reverse-proxy gateway** | API SDK calls (`api.openai.com`-shaped) | env var swap (`OPENAI_BASE_URL`) | server-side, hard | fail-closed (configurable) | **shipping** |
| 2 | **Forward proxy / SWG** | TLS-MITM browser → AI web UI | MDM-pushed root CA + SWG rule | server-side, hard | fail-open (SWG-default) | **alpha** (engine reusable; listener stub) |
| 3 | **Browser extension** | client-side textarea on AI web UIs | Chrome Enterprise / Edge GPO | client-side, soft | telemetry-only fallback | **roadmap** |
| 4 | **IDE plugin** | Copilot/Cursor/Continue prompt + completion | VSIX / JetBrains marketplace | client-side, inline | telemetry-only fallback | **roadmap** |
| 5 | **MCP / agent middleware** | MCP tool calls + agent prompts | install as MCP server, wrap agent runtime | server-side, hard | fail-closed | **alpha** (gateway exposes; SDK stub) |

### 2.1 PEP 1 — Reverse-proxy gateway *(canonical)*

The gateway is an OpenAI-API-compatible HTTPS server. Any code that uses the
OpenAI Python/JS SDK, the Anthropic SDK, LangChain, LlamaIndex, Bedrock client
libraries, etc. is redirected by changing one environment variable:

```bash
OPENAI_BASE_URL=https://praesidio.corp/v1
OPENAI_API_KEY=<praesidio-issued-key>
```

The gateway:

1. authenticates the principal (API key → user/group/tenant),
2. inspects the request body (DLP + classifier + policy),
3. transforms (tokenise, redact, FPE) or blocks,
4. forwards to the real provider with the operator's upstream key,
5. de-tokenises the response if appropriate,
6. writes a signed audit row + lineage edge.

This is the highest-coverage, lowest-friction PEP for any organisation whose
AI usage flows through code. It is the first thing every install turns on.

### 2.2 PEP 2 — Forward proxy / SWG integration

A `CONNECT`-aware HTTPS proxy with TLS-MITM. The corp root CA is pushed via
MDM/Intune/JAMF; the SWG (Zscaler, Netskope, Cisco Umbrella, Palo Alto Prisma,
in-house Squid, etc.) is configured to forward all egress to a curated list of
AI domains through Praesidio.

```
employee browser ──► SWG ──► Praesidio forward proxy ──► chat.openai.com
                                       │
                                       └──► /v1/inspect → policy verdict
                                            verdict=block → 451 with HTML page
                                            verdict=transform → splice redacted body
```

This is the only layer that catches employees pasting into consumer AI web
UIs without going through an SDK. It's also the politically hardest because
it requires MITM and SWG cooperation, which is why we ship it as **PEP 2**
not PEP 1.

Two SWG patterns are supported:

- **Inline-proxy mode** — Praesidio is the next hop. Highest fidelity.
- **ICAP / API mode** — Praesidio is called by the SWG over ICAP or a vendor
  webhook (Netskope's Inline Policy API, Zscaler's content inspection API).
  Lower latency, vendor-specific, but no root CA push needed.

### 2.3 PEP 3 — Browser extension

For unmanaged devices, BYOD, contractors, and any population where MITM is
not viable. A Chrome / Edge / Firefox extension is pushed via enterprise
policy. It content-scripts a curated allowlist of AI domains
(`chat.openai.com`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com`,
`perplexity.ai`, `chat.mistral.ai`, `pi.ai`, `you.com`, `phind.com`, …) and:

1. intercepts the textarea submit event,
2. POSTs the draft to `/v1/inspect`,
3. on `block` — prevents submission, shows in-page banner,
4. on `transform` — rewrites the textarea contents to the redacted form
   before submission,
5. on `allow` — passes through invisibly.

Failure mode is **telemetry-only**: if the extension can't reach Praesidio it
logs locally and lets the prompt through, because client-side blocking that
breaks the user's workflow is worse than a missed event (and the SWG layer
catches the worst cases anyway).

### 2.4 PEP 4 — IDE plugin

VSCode and JetBrains extensions that wrap the request stream from coding
assistants (Copilot, Cursor, Continue, Cody, Codeium, Tabby). These are the
single highest-value PEP for engineering orgs because:

- source code is the #1 leakage category in every customer survey,
- developers route around browser-level controls trivially,
- IDE telemetry maps cleanly to commit history and reviewer identity.

Implementation is per-host: the plugin sits as a local HTTP proxy on
`127.0.0.1`, the IDE coding assistant is configured to use it as its endpoint
(most assistants support a custom endpoint). Praesidio applies code-aware
detectors (secrets, internal-identifier patterns, copyrighted comments, AGPL
contamination) and either rewrites or warns.

### 2.5 PEP 5 — MCP / agent middleware

Praesidio ships as an MCP server that wraps tool invocations and as
middleware for the Claude Agent SDK, OpenAI Agents SDK, and LangGraph. Every
tool call, prompt expansion, and inter-agent message is inspected. This is
the cleanest integration for the agentic future and is the layer most
customers will care about by late 2026.

Two integration modes:

- **MCP-server wrap** — Praesidio sits between the agent host and the real
  MCP servers, so all tool calls go through it.
- **SDK middleware** — Praesidio is registered as a callback in the agent
  framework's prompt-pipeline (Anthropic's pre/post-tool hooks, OpenAI's
  guardrail callbacks).

---

## 3. Coverage matrix

The expected rollout: stack as many of these as your population mix demands.

| Population | Day 1 PEP | Day 30 add | Day 90 add | Steady-state coverage |
|---|---|---|---|---|
| Internal apps, agents, batch jobs, RAG | **1. Gateway** | — | — | 100% (env-var pin in IaC) |
| Managed laptops, on-corp/VPN | — | **2. Forward proxy** | — | ~95% (SWG bypass = the gap) |
| Managed laptops, off-network | — | — | **3. Browser ext** | ~80% (extension uninstall = the gap) |
| Engineering / IDE | — | **4. IDE plugin** | — | ~90% (assistant misconfig = the gap) |
| Sanctioned chat (e.g. ChatGPT Enterprise) | **1. Gateway (SSO-fronted)** | — | — | 100% |
| Unmanaged / BYOD | — | — | **3. Browser ext (opt-in)** + SWG block of unsanctioned | ~60% (best-effort) |
| Agentic workloads | **1. Gateway** | **5. MCP middleware** | — | 100% within sanctioned agent host |
| Shadow IT | — | **SWG deny-list** funnelling to sanctioned path | — | ~70% (DNS bypass = the gap) |

**Gaps to acknowledge openly.** No vendor catches:

- 100% of personal-device, personal-network, personal-account use,
- voice-mode in mobile apps that talk to AI providers over native sockets,
- on-device LLMs running fully offline,
- screenshot-to-LLM workflows where text never enters a textarea.

The honest answer to "what about those" is policy + training, not technology.
Praesidio surfaces the gaps in the **Coverage** dashboard rather than hiding
them.

---

## 4. Rollout sequence (the recommended path)

```
Day 0  ────────────── single laptop, single curl ──────────────  TTFV: 5 min
Day 1  ────────────── one team, one repo, gateway in IaC ─────  TTFV: 1 hr
Day 7  ────────────── org-wide gateway, sanctioned AI only ───  TTFV: 1 day
Day 30 ────────────── SWG forward-proxy live, MITM rolled out ─  TTFV: 1 week
Day 90 ────────────── browser ext + IDE plugin GA ────────────  TTFV: 2 weeks
Day 180 ───────────── MCP + agent middleware in production ───  TTFV: 1 month
```

Each step is independently valuable. Stopping at Day 7 still catches every
API-mediated AI call in the org, which for most companies is already 70%+ of
their leakage surface.

---

## 5. Five-minute Time-To-First-Value

The first install is the single highest-stakes moment in the product's
lifecycle. If it doesn't produce a "huh, that's neat" within five minutes,
the operator closes the tab and never comes back. Everything in the
quickstart path is optimised for that budget.

### 5.1 What "first value" means

A single audit row in the UI showing that a real prompt with PII was
intercepted, transformed, and forwarded. Not a hello-world response — a
visible, signed, lineage-attached *decision*.

### 5.2 The 300-second budget

| Step | Budget | Mechanism |
|---|---|---|
| Clone repo | 20 s | `git clone --depth 1` |
| Bring up stack | 90 s | `docker compose up -d` with pre-built images on Docker Hub (no local build for the quickstart path) |
| Health check | 10 s | `/healthz` polled by the onboarding wizard |
| First request | 30 s | one-liner `curl` against the gateway |
| Inspect audit row | 30 s | wizard auto-deep-links to the event |
| **Demo script** | **120 s** | three scripted prompts: PII, secret, IBAN — wizard runs `scripts/demo.sh` on click |
| **Total** | **≈ 300 s** | end-to-end, hands-on-keyboard |

### 5.3 Engineering choices that buy us the budget

- **Pre-built images on the public registry.** Local Dockerfile builds are
  the single largest enemy of TTFV (Presidio + spaCy model alone = ~2 GB,
  4–6 min on first build). The `quickstart` profile uses
  `ghcr.io/praesidio/gateway:latest` instead.
- **One profile per intent.** `docker compose --profile quickstart` brings
  up gateway + redis + UI only; postgres is replaced with SQLite for the
  audit log in this profile so we skip the migration step. The full profile
  (`--profile full`) is still there for self-hosted production.
- **Mock-mode UI.** If the gateway is unreachable, the UI degrades to
  synthetic data so the operator can navigate the product while the gateway
  is still pulling images. The wizard shows live status so they know.
- **Single-tenant default key.** `PRAESIDIO_API_KEYS=praesidio-demo-key` is
  baked into `.env.example`; the operator never has to mint a key for the
  quickstart.
- **Inline demo runner in the wizard.** The onboarding page can POST the
  three demo prompts directly from the browser — no terminal required for
  the first round of value.
- **Deep-linked event drilldown.** Each demo prompt's resulting audit row
  is linked from the wizard to `/events?id=...` so the operator lands on
  *the* row they care about, not the empty list.

### 5.4 What the wizard does *not* do

- It does not configure SSO, RBAC, or tenants on the quickstart path.
  Those are explicitly Day-1+ concerns and live in `/settings`.
- It does not push to a cluster, run Terraform, or mint TLS certs. The
  quickstart is laptop-local by design; cloud deployment is a separate
  guided flow (see §6).
- It does not silently rewrite shell config files. Every change is shown
  as a copy/pasteable block; the operator pastes it themselves.

---

## 6. Three deployment shapes

Praesidio is engineered for three install postures. The onboarding wizard's
first screen asks the operator which one they want and routes accordingly.

### 6.1 Local demo *(< 5 min)*

Single laptop, Docker Desktop or Colima. SQLite audit log, embedded Redis
data, no TLS, demo API key. Used for: evaluation, demos, local development
of policies. Stack:

```
docker compose --profile quickstart up -d
```

### 6.2 Self-hosted *(< 30 min)*

Full `docker-compose.yml` with Postgres + Redis + Gateway + UI, TLS via
Caddy sidecar, OIDC backed by the operator's IdP, persistent volumes. Used
for: small-team production, air-gapped environments, regulated workloads
that can't leave the network. Same compose file, no `--profile` flag.

### 6.3 Cloud / Kubernetes *(< 4 hr)*

Helm chart with HA gateway, External-Secrets-backed vault, NetworkPolicies,
PodSecurity, HPA, PDBs, Prometheus + Grafana dashboards. Terraform reference
modules for AWS / Azure / GCP create the cluster, KMS keys, RDS Postgres,
ElastiCache Redis, and the Praesidio Helm release. Used for: real
production.

The onboarding wizard surfaces the right docs at the right time. It does
**not** try to be a cluster installer — Helm + Terraform are the right tools
for that, and pretending otherwise hurts more than it helps.

---

## 7. Day-1+ operability

Once the gateway is up, the operator graduates from the wizard to the
console. The console is where every later integration is installed and
verified:

- **Coverage page** — shows which PEPs are reporting events, last-seen
  timestamps, and gaps. The honest dashboard.
- **Connectors page** (`/settings?tab=connectors`) — install scripts and
  download links for the forward proxy, browser extension, IDE plugin, and
  MCP middleware. Each connector verifies itself by sending a probe event
  the page auto-detects.
- **Identity** (`/settings?tab=identity`) — OIDC configuration once the
  operator is past the demo.
- **Bundles** — policy bundles are pulled from a signed (cosign) git
  repository; the onboarding wizard's last step is "point Praesidio at your
  policy repo" but it ships with a sane default so this is optional.

---

## 7.5 Detector catalogue & recommendations

Classification is one of the genuinely hard parts of any DLP product — what
counts as "sensitive" varies by jurisdiction, by industry, and by team.
Praesidio's answer is to *not* ask the operator to declare an industry up
front, because (a) most orgs span several (an insurer is healthcare AND
finance AND HR), and (b) self-declaration is the wrong shape of question to
front-load on Day 0.

Instead, classification is a two-part system.

### 7.5.1 The detector catalogue

`examples/policies/detectors.yaml` is the single source of truth that maps
every stable detector ID (`financial.credit_card`, `pii.nationality`, `credential.aws_access_key`,
…) to:

- a **human-readable display name** ("Payment card number",
  "Nationality / religion / political group", "AWS access key ID"),
- a **data family** (`personal_data`, `health_data`, `payment_data`,
  `financial_data`, `credentials`, `source_code`, `network`,
  `business_confidential`, `intent`),
- the **regulatory frameworks** the finding typically falls under (GDPR,
  CCPA, HIPAA, PCI-DSS, SOX, GLBA, ISO 27001, SOC 2),
- a **default sensitivity tier** (`public`, `internal`, `confidential`,
  `restricted`),
- a **default action** (`observe`, `transform`, `redact`, `block`).

The catalogue is consumed by the UI (event labelling, the policy editor,
the recommendations page, the onboarding wizard) and by the policy bundle
compiler (which refuses to ship a policy that references an unknown ID).
Adding a new detector means adding a catalogue entry first; the rest of
the system inherits sane defaults the moment it ships.

### 7.5.2 The universal default policy

`examples/policies/policies/0000-universal-default.yaml` enables every
catalogued detector and routes its action off the sensitivity tier:

| Tier | Default action | Examples |
|---|---|---|
| `restricted` | `block` or `redact` | AWS / GCP / GitHub / OpenAI / Anthropic keys, private keys, SSN, payment cards, GDPR special-category, proprietary markers |
| `confidential` | `transform` (tokenise / FPE / redact) | IBAN, JWT, MRN, NPI, ICD-10, CPT, lab values, DOB, medical-device IDs |
| `internal` | `transform` (reversible session tokens) | Email, phone, person names, locations, UUIDs |
| `public` | `observe` | Organisation names, generic dates |

Every tenant gets this on Day 0. A finance team using it catches IBANs;
a clinic using it catches MRNs; a startup using it catches AWS keys —
all from the same bundle, with no industry switch.

### 7.5.3 Observation-led recommendations

Industry-specific overlays still exist — `0100-healthcare.yaml`,
`0005-vectors.yaml`, and (planned) `0200-finance.yaml`. But they are no
longer bundled by default and they are no longer matched on
tenant-name patterns. Instead, the **Recommendations** page in the
console watches the audit stream and surfaces a card the moment evidence
warrants it:

> *We've seen 47 medical record numbers and 12 ICD-10 codes in the last 24h.*
> *The healthcare overlay tightens retention to 2,555 days and routes those*
> *prompts to a BAA-covered model.*  **\[Adopt\]  \[Show examples\]  \[Dismiss\]**

A recommendation only appears with named evidence (the operator can click
through to the lineage rows that triggered it), and adopting it is a
single click that opens a PR against the operator's policy repo — never
a silent change. Dismissed recommendations don't reappear unless the
underlying evidence changes materially.

This pattern means multi-industry tenants are first-class: a single
session that contains a card number, a medical record number, a person
name, and an internal codename gets four independent decisions — strictest
wins — without anyone having ever ticked "we are a healthcare-finance
hybrid" in a settings panel.

---

## 8. What the onboarding wizard ships as

A sequential, persisted-progress flow at `/onboarding`. Six steps; any user
without prior progress is redirected here on first load.

1. **Welcome · pick a path.** Local demo · self-hosted · cloud. The
   selection determines which copy/paste blocks the rest of the wizard
   shows.
2. **Bring it up.** One copy/paste command. The page polls `/healthz` and
   reflects status live (idle → connecting → healthy). Becomes the green
   checkmark when the gateway responds.
3. **Wire your first client.** Two copy-blocks: `OPENAI_BASE_URL` env vars
   + a `curl` request. A "Run it for me" button POSTs the same request
   from the browser so the operator doesn't have to open a terminal.
4. **Watch it work.** Live event tape filtered to the operator's session
   (by API key). Each demo prompt appears as a row within ~1 s, with a
   deep-link to its lineage.
5. **Expand coverage.** Cards for PEPs 2–5 with install snippets and
   "remind me later" affordances. Operator can skip and come back.
6. **You're live.** Summary screen with next-step links: policy authoring,
   identity, audit export, observability. Stamps a `praesidio-onboarded=1`
   flag in the user's profile so they aren't redirected again.

Progress is persisted in localStorage so a refresh / reboot / docker restart
doesn't lose place. The wizard can be re-opened from `/settings` any time.

---

## 9. Anti-patterns we explicitly avoid

- **The 10-step CLI quickstart.** Every additional command halves the
  audience. Praesidio's quickstart is one compose command + one curl.
- **The "configure your tenant first" screen.** Tenancy, RBAC, and SSO are
  Day-1+ concerns. Forcing them on Day-0 destroys TTFV.
- **The dark, illegible "ops" UI.** Praesidio's console is the same
  light-first instrument view from §1 of the design system on every screen,
  including the onboarding wizard.
- **The hidden "what about consumer-AI" gap.** The Coverage page surfaces
  uninstrumented populations rather than letting them be invisible.
- **The proprietary agent stack.** Praesidio integrates with whatever agent
  framework the customer already uses (Claude Agent SDK, OpenAI Agents,
  LangGraph, MCP). We do not require them to adopt a Praesidio runtime.

---

## 10. Reading guide

If you are…

- **An operator evaluating the product** → run the onboarding wizard at
  `/onboarding`.
- **A security architect planning rollout** → §§ 2, 3, 4 above.
- **A platform engineer integrating Praesidio into IaC** → see
  `deploy/helm/` and `deploy/terraform/`.
- **A developer writing a new PEP** → see
  [`docs/architecture/05-enforcement-points.md`](architecture/05-enforcement-points.md)
  and the `/v1/inspect` API in
  [`docs/architecture/03-gateway-api.md`](architecture/03-gateway-api.md).
