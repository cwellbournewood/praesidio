# ADR-0005 · Identity, auth, and tenancy

Date: 2026-05-27 · Status: Accepted

## Context

Three principals must be authenticated: end users (via IDE/app/SDK calling
the gateway), admins (UI/admin API), and services (sidecars, the agent
broker).

## Decision

- **End users**: OIDC bearer (preferred) or per-tenant API keys hashed in
  Postgres. OIDC claims map to principal groups for policy evaluation.
- **Admins**: OIDC only (no admin API keys). RBAC roles
  `viewer | analyst | policy-author | admin | tenant-admin` with ABAC
  attributes (tenant, region) overlaying.
- **Services**: mTLS via SPIFFE-style identities (`spiffe://praesidio/...`).

Multi-tenancy is row-level in Postgres (RLS), key-prefixed in Redis, and
policy-scoped in the gateway.

## Consequences

- ➕ Plays well with Okta, Entra ID, Auth0, Keycloak out of the box.
- ➕ mTLS service identity is the right long-term answer for zero trust.
- ➖ Initial setup is heavier than "just an API key" — docs include a
  zero-config dev mode for `make dev`.
