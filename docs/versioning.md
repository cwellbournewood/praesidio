# Versioning & deprecation policy

Praesidio follows [Semantic Versioning 2.0.0](https://semver.org). This
document defines what counts as **stable surface** (and therefore what
counts as a "breaking change" under SemVer), and the deprecation window
operators can rely on.

## Stable surface

A change to any of the following requires a **major version bump**:

### 1. HTTP API

* **Gateway proxy routes**: `/v1/chat/completions`,
  `/v1/completions`, `/v1/embeddings`, `/v1/models`,
  `/anthropic/v1/messages`, `/openai/deployments/{deployment}/...`,
  `/api/chat`.
* **Admin API**: `/admin/health`, `/admin/events`, `/admin/policies`,
  `/admin/lineage`, `/admin/models`, `/admin/simulate`,
  `/admin/detokenise`, `/admin/policy/reload`.
* **Operational endpoints**: `/healthz`, `/readyz`, `/metrics`.

For each route the contract is:

* HTTP method.
* URL path (including path parameters).
* Required headers (`Authorization`, `x-api-key`, `x-praesidio-tenant`).
* Request JSON schema (named fields, types, required-vs-optional).
* Response JSON schema for HTTP 2xx and 4xx classes.
* Response headers prefixed `x-praesidio-*` (see "Response headers"
  below).

**Non-breaking changes** (allowed in minor releases):

* Adding a new route.
* Adding a new optional request field.
* Adding a new field to the response body.
* Adding a new response header.
* Adding a new value to an enum **only if the documented behaviour
  preserves "ignore unknown values"** on the client side.

### 2. Policy YAML `apiVersion`

* `apiVersion: praesidio/v1` is the stable surface.
* Breaking changes to any policy/route/model field land under
  `apiVersion: praesidio/v2` with a parallel loader, and both versions
  are accepted for the full deprecation window.

### 3. OpenTelemetry attribute names

Every attribute on a gateway span or metric whose name starts with
`praesidio.*` is stable. Examples:

* `praesidio.tenant_id`, `praesidio.principal_id`,
  `praesidio.route`, `praesidio.upstream`,
  `praesidio.decision`, `praesidio.policy.id`,
  `praesidio.policy.version`, `praesidio.bundle.digest`,
  `praesidio.dlp.findings_count`.

Renaming or removing one of these is a breaking change. Adding new
`praesidio.*` attributes is not.

### 4. Environment variables

Every env var the gateway reads at startup whose name starts with
`PRAESIDIO_`, plus the conventional cross-ecosystem names
(`DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`AZURE_OPENAI_*`, `OLLAMA_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_SERVICE_NAME`), is stable. Renaming or removing one is a breaking
change; adding new ones is not.

### 5. Response headers

Headers emitted by the gateway whose name starts with `x-praesidio-`
are stable. Current set (non-exhaustive): `x-praesidio-decision`,
`x-praesidio-reason`, `x-praesidio-severity`,
`x-praesidio-latency-ms`, `x-praesidio-response-findings`,
`x-request-id`.

### 6. Helm chart values

The keys defined in `deploy/helm/praesidio/values.schema.json` are
stable. Adding new optional keys is non-breaking. Renaming, removing,
or changing the type of an existing key is breaking.

### 7. Container images

* `ghcr.io/cwellbournewood/gateway:<tag>` and `ghcr.io/cwellbournewood/ui:<tag>`
  tag scheme (`vX.Y.Z`, `vX.Y`, `sha-...`).
* The entrypoint binary (`praesidio-gateway`, `praesidio-audit`).
* The mount paths the gateway expects (`/etc/praesidio/policies`).
* The default ports (`8080` gateway, `3000` UI).

### 8. Database schema

The audit / lineage schema is stable in the sense that **Alembic
upgrades preserve data**. We may add columns, indexes, or even tables in
a minor release; we will not drop or rename anything in a minor release.
A drop / rename requires a major bump and a two-release window where
the old column is kept and dual-written, then removed.

## What is *not* stable

* Python module structure under `praesidio_gateway.*` (we may
  reorganise internally).
* The shape of internal CEL evaluation context (the inputs to policy
  CEL expressions are documented at `docs/policy/cel-context.md` and
  *are* stable; the internals are not).
* Test helpers, fixtures, and tooling under `scripts/`.

## Deprecation policy

When we plan to remove or rename a stable-surface element:

1. **Announce** in the next minor release CHANGELOG under a
   `### Deprecated` heading. Include the replacement, if any.
2. **Emit a runtime warning** at the affected code path (HTTP response
   header `x-praesidio-deprecation: <message>`, structured log entry
   with `deprecation=true`, or OTel attribute
   `praesidio.deprecated=true`).
3. **Wait at least 12 months** from the announcement before removing
   the element. The removal is always a major-version release.
4. **Document the migration** at
   `docs/migrations/from-<old>-to-<new>.md` before the removal release.

For security-driven removals (e.g. a weak cipher) we may shorten the
window with explicit notice in `SECURITY.md`.

## Version-skew tolerance

* **Gateway ↔ UI**: skew of one minor is supported in both directions.
  A UI from `v1.3.x` works with a gateway from `v1.2.x` or `v1.4.x`.
* **Gateway ↔ Helm chart**: the chart's `appVersion` should track the
  gateway image, but the chart's own `version` may step independently
  for chart-only changes.
* **Gateway ↔ policy bundle `apiVersion`**: the gateway accepts the
  current and the previous `apiVersion` simultaneously.

## Pre-1.0

We are currently in the `0.x.y` line. SemVer permits arbitrary breaking
changes in any `0.x` bump. **In practice, we treat `0.y.z → 0.(y+1).0`
as if it were a major bump under the policy above** — i.e. you get
the same announce-warn-12-month process. We will not silently break
your integration on a 0.x bump.

When we hit `1.0.0`, the full policy above applies without the "0.x
permits anything" caveat.
