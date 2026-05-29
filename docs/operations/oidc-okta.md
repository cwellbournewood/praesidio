# OIDC: Okta

This guide walks through wiring **Okta** as the identity provider for the
Praesidio admin UI and the privileged `/admin/*` API. The general OIDC
model is described in [`oidc.md`](oidc.md); this page only covers the
Okta-specific clicks and the claim mapping.

Praesidio expects the OIDC reverse-proxy (e.g. `oauth2-proxy`, an ingress
controller's `auth_request`, or the UI's NextAuth route) to **verify the
token and forward identity to the gateway via signed `X-Praesidio-*`
headers**. The gateway does not itself terminate the OIDC flow — keeping
identity verification out of the gateway lets it stay a small, auditable
data-plane component.

## Prerequisites

* An Okta tenant (free Developer edition is fine for evaluation).
* `okta-admin` permissions on the tenant.
* The UI deployed at `https://ui.praesidio.example` (replace below).

## 1. Create the OIDC application

In the Okta admin console:

1. **Applications → Applications → Create App Integration**.
2. **Sign-in method**: `OIDC - OpenID Connect`.
3. **Application type**: `Web Application`. Click **Next**.

### General settings

| Field | Value |
|---|---|
| App integration name | `Praesidio` |
| Logo (optional) | drop `docs/assets/praesidio-square.png` |
| Grant type | check `Authorization Code` only (refresh tokens optional) |
| **Sign-in redirect URIs** | `https://ui.praesidio.example/api/auth/callback/okta` |
| **Sign-out redirect URIs** | `https://ui.praesidio.example/` |
| Controlled access | `Allow everyone in your organization to access` (tighten later via group assignment) |

Click **Save**. Okta returns a **Client ID** and **Client Secret** — copy
both, you'll plug them into the UI's environment.

### Trusted origins

Under **Security → API → Trusted Origins**, add
`https://ui.praesidio.example` with both `CORS` and `Redirect` checked.

## 2. Configure the `groups` claim

Praesidio maps Okta groups to its RBAC roles via the
`PRAESIDIO_RBAC_GROUP_MAP` JSON env var (see [`oidc.md`](oidc.md#required-claims)).
For the `groups` array to appear on the ID token:

1. **Security → API → Authorization Servers → `default` → Claims → Add Claim**.
2. Fill in:
   - **Name**: `groups`
   - **Include in token type**: `ID Token` → `Always`
   - **Value type**: `Groups`
   - **Filter**: `Matches regex` `.*` (or `Starts with` `praesidio-` to
     restrict the claim to the relevant prefix)
   - **Include in**: `Any scope` (the default `openid` scope is enough)

3. Create matching Okta groups: `praesidio-admins`, `praesidio-ops`,
   `praesidio-auditors`, `praesidio-viewers`. Assign your real users.

## 3. (Optional) Pass tenant ID

If you operate Praesidio multi-tenant, add a custom user attribute
`tenant_id` on each user (Okta UD Schema → Profile Editor), then:

1. **Claims → Add Claim**.
2. Name `tenant_id`, value type `Expression`,
   expression `user.tenant_id`, include in ID token always.

The gateway reads `tenant_id` via the `X-Praesidio-Tenant` header set by
the reverse-proxy from this claim.

## 4. Wire the UI

In the UI's `.env` (or your secret store):

```ini
OIDC_PROVIDER=okta
OIDC_ISSUER=https://<your-okta-tenant>.okta.com/oauth2/default
OIDC_CLIENT_ID=<app-client-id>
OIDC_CLIENT_SECRET=<app-client-secret>
OIDC_REDIRECT_URI=https://ui.praesidio.example/api/auth/callback/okta
OIDC_SCOPES=openid profile email groups
```

In the gateway's `.env`:

```ini
PRAESIDIO_RBAC_GROUP_MAP={"praesidio-admins":["admin"],"praesidio-ops":["operator","viewer"],"praesidio-auditors":["auditor","viewer"],"praesidio-viewers":["viewer"]}
```

## 5. Smoke test the code exchange

A direct curl exchange against Okta's token endpoint, useful from CI:

```bash
OKTA_DOMAIN=<your-okta-tenant>.okta.com
CLIENT_ID=<client-id>
CLIENT_SECRET=<client-secret>
REDIRECT=https://ui.praesidio.example/api/auth/callback/okta
CODE=<auth-code-from-browser-redirect>

curl -sS -X POST "https://${OKTA_DOMAIN}/oauth2/default/v1/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -d "grant_type=authorization_code" \
  -d "code=${CODE}" \
  -d "redirect_uri=${REDIRECT}" | jq .
```

The response contains `id_token` (decode the middle segment as base64
JSON to confirm `groups` is present).

## 6. UI login flow (what a user sees)

1. User visits `https://ui.praesidio.example`.
2. UI redirects unauthenticated requests to
   `https://<okta>/oauth2/default/v1/authorize?…&scope=openid profile email groups`.
3. User authenticates with Okta (SSO or password + MFA).
4. Okta redirects back to `…/api/auth/callback/okta?code=…`.
5. The UI exchanges the code for tokens, stores the session cookie,
   and from then on attaches the verified identity as
   `X-Praesidio-User`, `X-Praesidio-Groups`, `X-Praesidio-Tenant` on
   every request to the gateway.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `viewer`-only role for an admin user | `groups` claim missing | Step 2 — claim not added to ID token |
| 400 `invalid_redirect_uri` | UI deployed on a host not registered with Okta | Add it under Sign-in redirect URIs |
| `tenant_id` empty in audit rows | custom claim not configured | Step 3 |
| MFA fails for the Okta API call | service account scoped to API only | Use a real user, not an API token, for the code flow |
