# OIDC integration

Praesidio uses OpenID Connect for human authentication to the admin UI
and the privileged `/admin/*` API. API keys remain the mechanism for
data-plane traffic (LLM calls). This page documents the integration
for the two most commonly deployed identity providers — **Keycloak**
(self-hosted, OSS) and **Microsoft Entra ID** (Azure AD).

## Required claims

Praesidio expects the following claims on the ID token / userinfo
response, regardless of provider:

| Claim | Type | Purpose |
|---|---|---|
| `sub` | string | Stable principal identifier; written to every audit row |
| `email` | string | Display only |
| `groups` | array of string | Mapped to Praesidio RBAC roles |
| `tenant_id` | string | The active Praesidio tenant; gates row-level data access |

`groups` is mapped to roles via `PRAESIDIO_RBAC_GROUP_MAP`, a JSON
object like:

```json
{
  "praesidio-admins":   ["admin"],
  "praesidio-ops":      ["operator", "viewer"],
  "praesidio-auditors": ["auditor", "viewer"],
  "praesidio-viewers":  ["viewer"]
}
```

Praesidio's built-in roles:

| Role | Capability |
|---|---|
| `admin` | All `/admin/*` endpoints, tenant management |
| `operator` | `/admin/policy/reload`, `/admin/simulate`, dashboards |
| `auditor` | `/admin/events` (read), `/admin/detokenise` (with reason, audited) |
| `viewer` | dashboards, read-only events |

## Redirect URI

Default: `http://localhost:3000/api/auth/callback`

For production set both:

- `OIDC_REDIRECT_URI` (env)
- the matching "Valid redirect URIs" in your IdP client config

## Scopes

Request `openid profile email groups`. If your IdP gates `groups`
behind a separate scope (Keycloak default: `groups` scope must be
added to the client), add it explicitly.

---

## Keycloak

### Local dev (Docker Compose overlay)

This repo ships a Keycloak overlay with a pre-seeded realm AND a custom
`praesidio` login theme so you can exercise the full SSO flow without a
separate IdP install:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.oidc.yml \
  up -d keycloak              # just the IdP
# or
docker compose \
  -f docker-compose.yml \
  -f docker-compose.oidc.yml \
  up --build                  # the full stack
```

The Keycloak container mounts `./deploy/keycloak/themes/praesidio` at
`/opt/keycloak/themes/praesidio` (read-only). The realm export sets
`loginTheme: praesidio`, so every authentication flow renders in the
Instrument aesthetic (bone canvas + ink + vermillion, Instrument Serif
headline, JetBrains Mono labels, hairline borders, signal squares).
Edit the CSS at `deploy/keycloak/themes/praesidio/login/resources/css/login.css`
and refresh — Keycloak picks up theme changes without a restart.

| URL | Credentials |
|---|---|
| Keycloak admin: <http://localhost:8081> | `admin / admin` |
| Pre-seeded realm: `praesidio` | imported from `deploy/keycloak/realm-export.json` |
| Demo users | see realm file below |

Pre-seeded users (passwords match usernames for dev convenience):

| Username | Groups | Role mapped |
|---|---|---|
| `alice` | `praesidio-admins` | admin |
| `bob` | `praesidio-ops` | operator |
| `carol` | `praesidio-auditors` | auditor |
| `dan` | `praesidio-viewers` | viewer |

`.env` values for the gateway / UI when using this overlay:

```ini
OIDC_ISSUER=http://keycloak:8080/realms/praesidio
OIDC_CLIENT_ID=praesidio
OIDC_CLIENT_SECRET=praesidio-demo-secret
OIDC_REDIRECT_URI=http://localhost:3000/api/auth/callback
PRAESIDIO_RBAC_GROUP_MAP={"praesidio-admins":["admin"],"praesidio-ops":["operator","viewer"],"praesidio-auditors":["auditor","viewer"],"praesidio-viewers":["viewer"]}
```

### Production Keycloak

1. Create a confidential client `praesidio` in your realm.
2. **Settings**:
   - Client type: `OpenID Connect`
   - Standard flow enabled, Direct access grants **disabled**.
   - Valid redirect URIs: `https://ui.praesidio.example/api/auth/callback`
   - Web origins: `https://ui.praesidio.example`
3. **Client scopes**: add `groups` (built-in or via the *groups*
   mapper). Make it `default`.
4. **Mappers**: ensure a Group Membership mapper writes `groups`
   without the leading `/` and a User Attribute mapper writes
   `tenant_id` from a per-user attribute.
5. Copy the client secret into `OIDC_CLIENT_SECRET` (via
   ExternalSecrets in production).

---

## Microsoft Entra ID (Azure AD)

1. **App registration** -> *New registration*.
   - Name: `Praesidio`
   - Redirect URI: Web, `https://ui.praesidio.example/api/auth/callback`
2. **Authentication** -> enable ID tokens. Disable implicit grant.
3. **Certificates & secrets** -> New client secret. Copy to
   `OIDC_CLIENT_SECRET`.
4. **Token configuration**:
   - Add optional claim: `groups` (Groups assigned to the user; emit
     as group **names**, not object IDs, if your AAD edition allows
     — otherwise map IDs in `PRAESIDIO_RBAC_GROUP_MAP`).
   - Add optional claim: `tid` (already present). Praesidio maps
     `tid` (Azure tenant) to its own `tenant_id` claim via the
     gateway-side `PRAESIDIO_OIDC_TENANT_CLAIM=tid` override.
5. **API permissions**: `openid`, `profile`, `email`,
   `User.Read`. Grant admin consent.
6. **Env**:
   ```ini
   OIDC_ISSUER=https://login.microsoftonline.com/<tenant-uuid>/v2.0
   OIDC_CLIENT_ID=<application-id>
   OIDC_CLIENT_SECRET=<secret>
   OIDC_REDIRECT_URI=https://ui.praesidio.example/api/auth/callback
   PRAESIDIO_OIDC_TENANT_CLAIM=tid
   ```

### Group claim caveat (Entra ID)

If a user is in more than ~200 groups, Entra emits a `_claim_names`
overage indicator instead of `groups`. The gateway treats this as
"no group claim" and falls back to the `viewer` role. To avoid the
overage, restrict the **Groups assigned to the user** claim to "Groups
assigned to the application" in *Token configuration*.

---

## End-to-end test approach

The CI workflow `quickstart.yml` does not yet bring up Keycloak (it
would push the workflow past its 15-minute budget). For OIDC-specific
e2e there are two approaches:

1. **Compose-based local test**. With the OIDC overlay running, use
   the Keycloak Admin REST API to obtain a token for `alice`, then
   call `/admin/policy/reload` directly:

   ```bash
   TOKEN=$(curl -s -X POST \
     "http://localhost:8081/realms/praesidio/protocol/openid-connect/token" \
     -d "grant_type=password" -d "client_id=praesidio" \
     -d "client_secret=praesidio-demo-secret" \
     -d "username=alice" -d "password=alice" \
     -d "scope=openid profile email groups" \
     | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

   curl -X POST http://localhost:8080/admin/policy/reload \
     -H "Authorization: Bearer ${TOKEN}"
   ```

   The gateway must accept this token (role `admin` derived from
   `groups: ["praesidio-admins"]`) and refuse the equivalent call
   from `dan` (role `viewer`).

2. **Playwright UI flow**. The lane-B UI tests include an opt-in
   `OIDC=1 pnpm test:e2e` mode that drives the full browser flow
   through Keycloak. This is run nightly, not on every PR.

## Threat model linkage

OIDC integration replaces shared API keys for human access — see the
"Admin API surface" STRIDE entry in [`docs/threat-model.md`](../threat-model.md).
Combined with the audited tenant switcher and the cookie protections
documented there, the result is: every privileged action traces back
to an identity, a tenant, and a moment in time.
