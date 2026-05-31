# OIDC: Google Workspace

Short walkthrough for using **Google Workspace** (Cloud Identity) as the
identity provider for Section. Google's OIDC endpoint does **not**
return group memberships by default — you'll need an extra integration
step (see [Group claim](#group-claim)).

For the general OIDC model see [`oidc.md`](oidc.md); for the role-mapping
env var see [`oidc-okta.md#step-4-wire-the-ui`](oidc-okta.md).

## 1. Create the OAuth client

1. <https://console.cloud.google.com> → **APIs & Services → Credentials
   → Create credentials → OAuth client ID**.
2. **Application type**: `Web application`.
3. **Name**: `Section`.
4. **Authorized JavaScript origins**: `https://ui.section.example`.
5. **Authorized redirect URIs**:
   `https://ui.section.example/api/auth/callback/google`.
6. Click **Create**. Copy the **Client ID** and **Client secret**.

## 2. OAuth consent screen

* **User type**: `Internal` (limits the app to your Workspace tenant —
  required for production unless you want anyone with a Google account
  to log in).
* **Scopes**: add `openid`, `email`, `profile`.
* No app review needed for `Internal` user type.

## 3. Group claim

Google's standard OIDC response **does not** include group memberships.
Two options:

### Option A — Domain-wide delegation + Directory API (recommended)

A small claim-enrichment service queries the Admin SDK
`directory.groups.list` for the user at login time and adds a `groups`
claim to the session cookie before it ever reaches the gateway. This
keeps Google's token surface unchanged.

Steps:

1. Create a service account, enable **Domain-wide delegation**, grant it
   the OAuth scope `https://www.googleapis.com/auth/admin.directory.group.readonly`
   in your Workspace Admin console (Security → API controls → Domain-wide
   delegation).
2. In the UI's NextAuth callback (or your reverse-proxy), after the
   Google token exchange, call:

   ```http
   GET https://admin.googleapis.com/admin/directory/v1/groups?userKey=<user-email>
   Authorization: Bearer <service-account-jwt>
   ```

3. Map the returned group emails (e.g. `section-admins@example.com`)
   to roles via `SECTION_RBAC_GROUP_MAP`:

   ```ini
   SECTION_RBAC_GROUP_MAP={"section-admins@example.com":["admin"],"section-ops@example.com":["operator","viewer"],"section-auditors@example.com":["auditor","viewer"],"section-viewers@example.com":["viewer"]}
   ```

### Option B — Static role per user via hosted domain

For very small deployments, gate by Google **hosted domain** (`hd` claim,
present on Workspace tokens) and grant `admin` to a hard-coded allowlist
of email addresses. This is a stop-gap, not a production model.

```ini
SECTION_ADMIN_EMAILS=alice@example.com,bob@example.com
```

The UI reads this var and stamps `X-Section-Scopes: admin` (or empty)
on calls to the gateway accordingly.

## 4. UI env

```ini
OIDC_PROVIDER=google
OIDC_ISSUER=https://accounts.google.com
OIDC_CLIENT_ID=<client-id>.apps.googleusercontent.com
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://ui.section.example/api/auth/callback/google
OIDC_SCOPES=openid email profile
OIDC_GOOGLE_HD=example.com           # restrict to your Workspace domain
```

## 5. Smoke test

```bash
CLIENT_ID=<client-id>.apps.googleusercontent.com
CLIENT_SECRET=<client-secret>
REDIRECT=https://ui.section.example/api/auth/callback/google
CODE=<auth-code>

curl -sS -X POST "https://oauth2.googleapis.com/token" \
  -d "code=${CODE}" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "redirect_uri=${REDIRECT}" \
  -d "grant_type=authorization_code" | jq .
```

## Caveats

* Google's `iss` claim alternates between `https://accounts.google.com`
  and `accounts.google.com` (with and without scheme). Your OIDC library
  must accept both — `next-auth` and `pyjwt` do by default; some
  hand-rolled validators don't.
* Tokens expire fast (1 hour). Use the refresh token (request
  `access_type=offline`) for headless workflows.
* Google does not emit a `tenant_id` claim. For multi-tenant Section
  deployments use the email domain or a custom DB lookup.
