# OIDC: Microsoft Entra ID (Azure AD)

Step-by-step wiring of **Microsoft Entra ID** (formerly Azure Active
Directory) as the identity provider for the Praesidio admin UI and the
privileged `/admin/*` API. This page expands on the abridged Entra section
in [`oidc.md`](oidc.md#microsoft-entra-id-azure-ad) — read that page first
for the role-mapping model.

## Prerequisites

* A Microsoft Entra tenant with `Application Administrator` or
  `Cloud Application Administrator` rights.
* The UI deployed at `https://ui.praesidio.example` (replace below).

## 1. App registration

1. Sign in to <https://entra.microsoft.com> → **Applications →
   App registrations → New registration**.
2. Fill in:
   - **Name**: `Praesidio`
   - **Supported account types**: `Accounts in this organizational
     directory only (Single tenant)` for most deployments.
   - **Redirect URI**: platform `Web`,
     `https://ui.praesidio.example/api/auth/callback/azure-ad`.
3. Click **Register**. Note the **Application (client) ID** and
   **Directory (tenant) ID** on the overview page.

## 2. Authentication settings

In the new app's **Authentication** blade:

* Under **Implicit grant and hybrid flows**, enable **ID tokens (used
  for implicit and hybrid flows)**. **Do not** enable Access tokens or
  Implicit grant.
* **Front-channel logout URL**: `https://ui.praesidio.example/api/auth/signout`
* **Allow public client flows**: `No`.

Save.

## 3. Client secret

**Certificates & secrets → Client secrets → New client secret**.

* Description: `praesidio-prod`
* Expires: `24 months` (rotate via your secret store; see
  [`secrets-management.md`](secrets-management.md))

Copy the **Value** column **before navigating away** — it is shown only
once. Store in your secret manager and reference as `OIDC_CLIENT_SECRET`.

## 4. Token configuration — the critical part

This is where Entra trips up most operators. Praesidio needs **group
names** (or stable GUIDs) on the ID token. By default Entra emits only
the `tid`/`oid`/`sub` set.

### 4a. Add the `groups` optional claim

1. **Token configuration → Add groups claim**.
2. Choose **Security groups** (or **Groups assigned to the application**
   if you want to limit the claim — see [Overage caveat](#overage-caveat)).
3. Under both **ID** and **Access** sub-panels:
   - Pick **Group ID** (default) **or** **sAMAccountName** /
     **NetBIOSDomain\sAMAccountName** if you have AD-synced groups and
     prefer names.
4. Save.

### 4b. Add `tenant_id` optional claim (multi-tenant deployments only)

1. **Token configuration → Add optional claim**.
2. Token type: `ID`.
3. Pick `tid` (Azure tenant) — this gives every token a stable Azure
   tenant ID that Praesidio maps to its own tenant via
   `PRAESIDIO_OIDC_TENANT_CLAIM=tid`.
4. (Optional) For a richer multi-tenancy model where you have multiple
   Praesidio tenants inside one Entra tenant, store a custom attribute
   `extensionAttribute1` on each user (via **Users → Edit attributes**)
   and map it as `Custom Claim` named `tenant_id`.

### 4c. API permissions

1. **API permissions → Add a permission → Microsoft Graph → Delegated**.
2. Add: `openid`, `profile`, `email`, `User.Read`,
   `GroupMember.Read.All` (the last is needed if you map names rather
   than IDs).
3. Click **Grant admin consent for <tenant>**.

## 5. Group → role mapping

Create Entra security groups, assign users, then mirror the GUIDs (or
names) into `PRAESIDIO_RBAC_GROUP_MAP`. Example with GUIDs:

```ini
PRAESIDIO_RBAC_GROUP_MAP={"d34db33f-…-admins":["admin"],"d34db33f-…-ops":["operator","viewer"],"d34db33f-…-auditors":["auditor","viewer"],"d34db33f-…-viewers":["viewer"]}
```

To get a group's object ID, open it under **Groups → All groups** and
copy **Object Id** from the overview.

## 6. UI env

```ini
OIDC_PROVIDER=azure-ad
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-uuid>/v2.0
OIDC_CLIENT_ID=<application-client-id>
OIDC_CLIENT_SECRET=<client-secret-value>
OIDC_REDIRECT_URI=https://ui.praesidio.example/api/auth/callback/azure-ad
OIDC_SCOPES=openid profile email
PRAESIDIO_OIDC_TENANT_CLAIM=tid
```

> Entra includes `groups` automatically when you've added the optional
> claim — you don't need a separate `groups` scope.

## 7. Smoke test (auth-code exchange)

```bash
TENANT=<tenant-uuid>
CLIENT_ID=<application-client-id>
CLIENT_SECRET=<client-secret>
REDIRECT=https://ui.praesidio.example/api/auth/callback/azure-ad
CODE=<auth-code-from-browser>

curl -sS -X POST "https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=${CODE}" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "redirect_uri=${REDIRECT}" \
  --data-urlencode "scope=openid profile email" | jq .
```

Decode the `id_token` middle segment (base64url, JSON) to confirm
`groups`, `tid`, and any custom claim are present.

## Overage caveat

If a user belongs to **more than ~200 security groups**, Entra omits
`groups` from the token and instead emits a `_claim_names` indicator
pointing to a Graph API endpoint. The gateway treats a missing `groups`
claim as zero memberships and falls back to the `viewer` role.

**Recommended fix**: in **Token configuration → groups claim**, pick
**Groups assigned to the application** instead of **All security groups**.
This caps the claim at the groups directly assigned to the Praesidio app
registration, well under the overage threshold.

## End-to-end UI login flow

1. User visits `https://ui.praesidio.example`.
2. UI redirects to `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize?…`.
3. User authenticates (password + Authenticator / FIDO2).
4. Entra redirects to `…/api/auth/callback/azure-ad?code=…`.
5. UI exchanges code, stores session cookie, forwards verified identity
   to the gateway as `X-Praesidio-User`, `X-Praesidio-Groups`,
   `X-Praesidio-Tenant` headers (signed by the reverse-proxy).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Admin gets `viewer` role | overage indicator on token | Section [Overage caveat](#overage-caveat) |
| `AADSTS50011` invalid redirect | host not registered exactly (incl. trailing slash) | Update Authentication → Redirect URIs |
| `AADSTS65001` consent required | API permissions not granted | Step 4c — click **Grant admin consent** |
| `tenant_id` empty | optional claim missing | Step 4b |
| Slow first login | spaCy + Presidio cold start, unrelated to Entra | unrelated; see [`observability.md`](observability.md) |
