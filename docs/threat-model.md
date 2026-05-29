# Threat Model

Framework: STRIDE per trust boundary, plus a dedicated AI-specific column
inspired by OWASP LLM Top 10 (2025) and MITRE ATLAS.

## 1. Assets

| Asset | Sensitivity |
|---|---|
| Customer prompts and outputs | up to *Restricted* |
| Token vault contents (originals during reversal TTL) | *Restricted* |
| Audit log | *Confidential* (operational), *Restricted* if it contained raw PII (it doesn't — by design) |
| Policy bundles | *Confidential* — disclosure helps an attacker craft bypasses |
| Vault key, FPE key, audit signing key | *Critical* |
| Upstream LLM API keys | *Critical* |

## 2. Actors

| Actor | Capability assumed |
|---|---|
| End user | authenticated, may attempt to bypass policy |
| Malicious user / insider | full credentials, may attempt to exfiltrate via crafted prompts |
| Compromised endpoint | can issue any request the user can; may also inject into IDE assistant |
| Adversarial LLM provider | may log, replay, or train on submitted data |
| Adversarial tool / MCP server | may attempt prompt injection on agent outputs |
| Cluster admin | full Kubernetes / DB access |
| Network attacker (passive / active MITM) | can observe / tamper unless TLS |

## 3. Trust boundaries

```
[user] ──TLS──► [gateway] ──mTLS──► [upstream LLM]
                    │
                    ├──TLS──► [Postgres]
                    ├──TLS──► [Redis]
                    └────────► [policy bundle source]
```

## 4. STRIDE × component

### Gateway

| Threat | Mitigation |
|---|---|
| **S**poofing — caller pretends to be another user | OIDC + per-tenant API keys; mTLS for service-to-service; principal hash in every audit row |
| **T**ampering — request modified in flight | TLS 1.3 mandatory; HSTS; request digest in audit |
| **R**epudiation — user denies sending request | Audit chain hash + signed batch terminal; principal binding |
| **I**nformation disclosure — error pages leak data | Errors are structured codes; no body echo in 5xx |
| **D**oS — flood inspection | Per-tenant token-bucket rate limits; circuit breaker on DLP pipeline; horizontal scale |
| **E**oP — bypass DLP via streaming/encoding tricks | Canonicalisation (NFKC), peel base64/hex/rot-N, detect multi-language, scan tool args |

### Policy engine

| Threat | Mitigation |
|---|---|
| Malicious policy bundle | cosign signature required; bundle digest in every audit row |
| Misconfigured rule allows everything | Simulation mode + canary required before promotion; UI shows decision impact diff |
| Rule complexity DoS | CEL evaluator with deadline + depth limits |

### DLP

| Threat | Mitigation |
|---|---|
| FP fatigue → analysts whitelist everything | per-policy thresholds, allow-list governance, FP rate dashboards |
| Adversarial obfuscation (zero-width chars, homoglyphs, ROT, base64) | preprocessor strips zero-width, normalises homoglyphs, peels common encodings before detect |
| Inference attacks on findings | findings store hashes not text |

### Anonymiser / vault

| Threat | Mitigation |
|---|---|
| Vault key compromise | per-tenant key derivation; KMS-backed; key rotation with 2×TTL keyring |
| Placeholder collision / inference | per-request scope default; tenant scope opt-in only; `xxxx` salt includes tenant |
| Replay (old vault contents leak) | TTL ≤ 24h hard cap; vault wiped on tenant offboarding |
| FPE distinguishability | FF3-1 per NIST, with per-tenant tweak |

### Audit

| Threat | Mitigation |
|---|---|
| Admin deletes/edits rows | hash chain breaks on tamper; periodic terminal hash signed and externally anchored |
| Audit sink down → events lost | local WAL queue with bounded backlog and at-least-once retry; degraded marker |
| Audit reveals PII | by-construction: hashes, not text; tenant-scoped RLS |

### Admin API surface (`/admin/simulate`, `/admin/detokenise`, `/admin/policy/reload`)

These endpoints are operator-only and carry elevated risk: detokenise
reverses anonymisation, simulate echoes prompt content back through
the pipeline, and policy/reload mutates effective enforcement.

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S**poofing | Attacker calls `/admin/*` with leaked API key | Admin keys are a separate keyspace from data-plane keys; OIDC required when `PRAESIDIO_ADMIN_REQUIRE_OIDC=1`; per-endpoint RBAC scope (`admin:simulate`, `admin:detokenise`, `admin:policy`) |
| **T**ampering | Manipulated reload payload installs malicious bundle | `/admin/policy/reload` only re-reads from configured `PRAESIDIO_POLICY_BUNDLE`; signature verification (cosign) is enforced before swap; rejected bundles leave the previous active set untouched |
| **R**epudiation | Operator denies running a detokenise | Every `/admin/*` call writes a dedicated audit row with principal, reason, request digest, and (for detokenise) the placeholder + originating event id; rows are part of the hash chain |
| **I**nfo disclosure | `/admin/simulate` returns transforms that include masked secrets | Simulate honours the live policy: any transform/block applies to its response too; raw originals never leave the gateway. `/admin/detokenise` requires a `reason` string ≥ 10 chars and is rate-limited per principal |
| **D**oS | Reload loop pins CPU | Reload is debounced server-side (≥ 5s between accepted calls); simulate is rate-limited per API key |
| **E**oP | Detokenise used to enumerate the vault | Per-principal rate-limit + alert on >N detokenise calls/hour; detokenise rejects unknown placeholders without revealing which were "close"; SIEM sink emits a high-severity event for every detokenise call |

### SIEM webhook egress

The gateway can forward audit events to a customer-owned SIEM via
HTTPS webhook (`PRAESIDIO_SIEM_WEBHOOK_URL`).

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S**poofing | A misconfigured URL exfiltrates events to an attacker domain | URL must resolve to an explicit allow-list of host suffixes (`PRAESIDIO_SIEM_ALLOWED_HOSTS`); HTTPS required; mTLS option for production |
| **T**ampering | Events modified in transit | TLS 1.3 + HMAC-SHA256 over the JSON body using a shared signing secret; receiver verifies before ingest |
| **R**epudiation | "We never received that event" | Each delivery is retried with idempotency key; gateway records delivery receipts in `audit_egress` |
| **I**nfo disclosure | Webhook leaks via DNS rebinding / SSRF to internal network | Resolver pre-checks block RFC1918 / link-local / metadata IPs unless `PRAESIDIO_SIEM_ALLOW_PRIVATE=1`; outbound NetworkPolicy in Helm restricts gateway egress to the allow-list |
| **D**oS | Slow receiver back-pressures the gateway | Egress runs on a bounded async queue with timeout; on overflow events spill to local WAL and a degraded marker is flagged in `/healthz` |
| **E**oP | Webhook source can replay events to bypass deduplication | Receiver-side replay protection via the idempotency key + monotonic event id; mandated in the integration doc |

### UI tenant switcher (cookie tampering risk)

The admin UI persists the active tenant in a signed cookie so the user
sees the same context across reloads. The gateway *never* trusts this
cookie alone.

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S**poofing | User edits cookie to view another tenant's data | Cookie is signed (HMAC) and `HttpOnly`, `Secure`, `SameSite=Lax`; the gateway validates that the requested tenant id is within the OIDC token's `tenant_ids` claim before any query |
| **T**ampering | Replay an old cookie after RBAC revocation | Cookie carries a `tid` (token id) bound to the current session; revoked sessions invalidate the cookie server-side |
| **R**epudiation | "I never switched to tenant X" | Tenant-switch events are audited (`event=ui.tenant.switch`, principal + from/to) |
| **I**nfo disclosure | Browser extensions read the cookie | `HttpOnly` prevents JS access; CSP blocks third-party scripts on the admin UI origin |
| **D**oS | Rapid switching triggers many cache misses | Per-principal switch rate-limit in the UI middleware (≤ 30/min) |
| **E**oP | Switching to a tenant the user does not belong to | Server-side authorisation check on every request, not just on switch; failure returns 403 + audited |

### Shadow-mode / simulation bypass risk

Shadow mode evaluates a policy but does not enforce it. It is critical
for safe rollout; it is also the most common operator footgun.

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S**poofing | Operator marks a policy "shadow" to silently disable it | Shadow status is part of the signed policy bundle; flipping requires a new signed bundle (cannot be done from the UI alone) |
| **T**ampering | Shadow flag stripped between sign and load | Bundle digest is verified at load time; running config exposes which rules are in shadow via `/admin/policy/active` so audits can detect drift |
| **R**epudiation | "We thought it was enforcing" | Every audit row records `policy.mode = shadow\|enforce`; UI Events table highlights shadow rows with a distinct badge; weekly digest shows shadow coverage |
| **I**nfo disclosure | Shadow rule still triggers DLP and stores findings | Same data minimisation as enforce mode: findings are hashed, not stored as text |
| **D**oS | Shadow evaluation doubles CPU on every request | Shadow rules share the pipeline pass with enforcing rules; bounded total evaluation budget per request |
| **E**oP | All rules silently in shadow → fail-open | Startup check warns and emits a high-severity audit event if 100% of `block` rules for the default policy are in shadow; `PRAESIDIO_FORBID_FULL_SHADOW=1` (recommended for prod) makes this a fatal config error |

### Agent broker (architected)

| Threat | Mitigation |
|---|---|
| Prompt injection from tool output | injection classifier + `<UNTRUSTED_CONTENT>` wrapping + system-prompt convention |
| Capability escalation | signed capability tokens; revocation stream; per-invocation count limits |
| Lateral movement via tool composition | network namespace per capability; egress allow-list; sandbox |
| Memory poisoning | write filter through DLP; mandatory TTL; semantic expiry |

### Tool-call allowlist enforcement (G6 — runtime)

Praesidio inspects every upstream response for `tool_calls` (OpenAI) /
`tool_use` blocks (Anthropic) and applies the active policy's
`tool_allowlist`. The enforcement module
(`praesidio_gateway.policy.tool_calls`) is pure Python and is shared
with the `praesidio-policy lint` CLI so the static check and the
runtime check cannot drift.

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S** | Attacker crafts a prompt that elicits a renamed tool ("Search" vs "search") | Match is case-sensitive glob; allow lists are explicit; `*` only as last-resort |
| **T** | Tool name field tampered post-upstream | Body parsing happens inside the gateway; chain-hash covers the rewritten response |
| **R** | Operator denies disallowing a tool | Every denied call increments `policy.tool_calls.blocked_total{tenant,policy,tool}` and writes an audit row with the offending name |
| **I** | Deny reason leaks tool catalogue | Deny reason is generic ("not in allowlist") to the caller; full reason only in the audit row |
| **D** | Adversary spams disallowed tool calls to flood the counter | Counter is bounded by Prometheus label cardinality limits; per-tenant audit rate-limit |
| **E** | Tool with `*` wildcard accidentally permits a dangerous tool | `praesidio-policy lint` warns on `allow: ["*"]` without a non-empty `deny`; recommended deploy pattern is allow-list-with-glob |

### Detokenise hardening (G7)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S** | Stolen admin key reveals vault contents | Detokenise now requires `ticket_id` and `justification` (≥ 16 chars), both stored in the audit row; per-tenant token bucket (default 10/min) |
| **R** | Operator denies a reveal | Audit row records `event_type=admin.detokenise`, `ticket_id`, `justification`, principal, source IP, placeholder |
| **I** | Brute-force placeholder enumeration | 429 on bucket exhaustion; unknown placeholders return 404 with no "did you mean" hint |

### Vector DB connectors (V3 — pgvector + Qdrant)

The gateway exposes `/v1/vectors/{store}/upsert` and
`/v1/vectors/{store}/query`. Both go through `scan_on_write` (DLP +
vault-backed placeholder substitution; secrets block the upsert
entirely) and `validate_retrieval` (per-principal/per-group ACL filter
on returned documents).

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S** | Caller upserts as a different principal | Tenant + principal derived from validated auth; never from the request body |
| **T** | Stored vector tampered to evade later DLP | DLP runs at write time and rejects secrets; metadata column carries the policy version that scanned it |
| **R** | "Who indexed this document?" | Every upsert/query is audited with principal, store, document id digest, and ACL outcome |
| **I** | Cross-tenant retrieval via crafted query | `documents_acl` table joined on every query; Postgres RLS on `vector_documents` for the `pgvector` backend; in-memory ACL for Qdrant (callers MUST configure a real ACL backend in prod) |
| **D** | Mass-upsert exhausts embedding budget | Per-tenant RPM applies; per-store TPM bucket configurable |
| **E** | Disallowed model embedded into vault-backed restore on read | `validate_retrieval` is mandatory; restore only fires when the response is on a route that owns those placeholders |

### Policy hot-reload (G3)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **T** | Reloaded bundle is partial (file replaced mid-write) | Loader requires complete signed bundle; atomic swap after validation; on failure the previous active set remains in force |
| **R** | "Reload happened, who triggered it?" | Reload writes a dedicated audit row with `bundle_digest_before/after`, principal, source (`signal\|api\|watcher`) |
| **D** | Reload-loop pins CPU | Server-side debounce (≥ 5s between accepted reloads), file-watcher batches inotify events on a 250ms window |

### Per-key + per-model rate-limits (G4)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **D** | One leaked API key consumes the entire tenant quota | Per-key RPM bucket (`PRAESIDIO_RATE_LIMIT_PER_KEY_RPM`) on top of the tenant bucket |
| **E** | Caller routes around per-key limit by switching models | Per-(tenant, model) TPM bucket charged after the upstream response so cost-based throttling is honest |
| **I** | Counter labels leak tenant identity in metrics | Tenant label is the hash from the principal fingerprint, not the raw tenant id |

### Bedrock adapter (G10 — AWS SigV4)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **S** | Wrong region in URL routes traffic to attacker-controlled endpoint | Region is taken from the configured `models.yaml`, not request-controlled; SigV4 signature is region-bound |
| **I** | AWS keys leak via log | Adapter never logs request headers; lazy-imports botocore and defers credential resolution to the default chain in production |
| **T** | Stripped `anthropic_version` causes silent fallback to a weaker model | Adapter sets `anthropic_version=bedrock-2023-05-31` if the caller omits it; reject if caller provides a non-Bedrock version |

### Cost / token metering (G5)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **T** | Operator inflates `PRAESIDIO_PRICE_BOOK_JSON` to hide cost overruns | Price book is loaded at boot and its digest is included in the metering audit row; Grafana panel surfaces price-book version |
| **I** | Metering exposes per-prompt token counts to other tenants | Counters are labelled `{tenant, model, route}`; Prometheus RBAC by namespace; admin UI scope checks |

### Alembic migrations (D1)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **T** | Two gateway replicas race the same migration on first deploy | `alembic upgrade head` runs in the entrypoint with an advisory lock (Postgres) or table-lock (SQLite); only one replica wins, others wait |
| **D** | Long-running migration blocks new connections | Migrations use `CREATE INDEX CONCURRENTLY` where supported; production runbook documents maintenance window |
| **R** | "Which migration shipped with which release?" | Alembic version stamped into `alembic_version`; release notes link to migration ids |

### Kubernetes admission (D6)

A `ValidatingAdmissionPolicy` (k8s ≥1.30) and a Gatekeeper
`ConstraintTemplate` are shipped so cluster admins can refuse Pod
manifests that target an LLM endpoint without routing through Praesidio.

| STRIDE | Threat | Mitigation |
|---|---|---|
| **E** | Pod bypasses gateway by setting `OPENAI_BASE_URL` directly | Admission policy denies any container whose env contains an LLM provider host not on `praesidio-allowed-llm-endpoints` ConfigMap |
| **T** | Constraint disabled by editing the policy live | Policy is shipped as a GitOps artifact; `kubectl auth can-i` matrix restricts mutation to platform team |

### Release supply chain (D4)

| STRIDE | Threat | Mitigation |
|---|---|---|
| **T** | Tampered release artifact published as `latest` | Images and Helm chart are signed with cosign keyless (Sigstore); release workflow attaches SLSA-3 provenance |
| **R** | "Where did this binary come from?" | CycloneDX SBOM published alongside every release; checksum manifest is itself signed |
| **I** | CodeQL findings disclosed before patch | Security policy in `SECURITY.md` directs reporters to GitHub Private Vulnerability Reporting; 90-day disclosure SLA |

## 5. AI-specific risks (OWASP LLM Top 10 — 2025 mapping)

| OWASP LLM | Praesidio control |
|---|---|
| LLM01 Prompt Injection | injection detector + agent-broker `<UNTRUSTED_CONTENT>` wrapper |
| LLM02 Sensitive Information Disclosure | semantic DLP + anonymiser + output DLP |
| LLM03 Supply Chain | signed policy bundles; signed MCP tool manifests |
| LLM04 Data & Model Poisoning | vector ingest DLP; memory write filter |
| LLM05 Improper Output Handling | output DLP + de-anonymiser |
| LLM06 Excessive Agency | capability tokens (scoped, time-bound, revocable) |
| LLM07 System Prompt Leakage | output DLP detects prompt-echo |
| LLM08 Vector / Embedding Weaknesses | ACL-mediated retrieval; embedding ACLs; tenant isolation |
| LLM09 Misinformation | n/a (Praesidio is not a fact-checker) |
| LLM10 Unbounded Consumption | rate limits + cost budgets in model router |

## 6. Out of scope

- Model alignment / safety tuning of upstream LLMs.
- Endpoint compromise that bypasses Praesidio entirely (user pastes into
  a personal account on a personal device).
- Cryptographic attacks on AES-256-GCM / Ed25519 / FF3-1 within their
  documented parameter ranges.

## 7. Red-team plan

Documented in `docs/redteam/playbook.md` (roadmap). Includes:
- adversarial-prompt suites against detectors,
- payload-encoding bypass attempts,
- streaming-boundary injection,
- agent capability-escalation chains.
