/**
 * Credential management for the Section extension.
 *
 *  - Stores API keys + OIDC bearer tokens in `context.secrets`
 *    (VS Code SecretStorage — backed by the OS keychain).
 *  - Implements the RFC 8628 OIDC device-code flow for enterprise
 *    sign-in.
 *
 * SecretStorage keys (all under the "section.*" namespace):
 *
 *  section.apiKey      — raw X-API-Key value
 *  section.accessToken — OIDC access token (short TTL)
 *  section.refreshToken — OIDC refresh token (long TTL)
 *  section.tenantId    — tenant claim from the JWT
 *  section.expiresAt   — ms epoch when access token expires
 */

import * as vscode from "vscode";

import type { Credential } from "./gateway.js";

const KEY_API = "section.apiKey";
const KEY_ACCESS = "section.accessToken";
const KEY_REFRESH = "section.refreshToken";
const KEY_TENANT = "section.tenantId";
const KEY_EXPIRES = "section.expiresAt";

export interface DeviceCodeChallenge {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string;
  expires_in: number;
  interval: number;
}

interface DeviceTokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

interface DeviceErrorResponse {
  error:
    | "authorization_pending"
    | "slow_down"
    | "access_denied"
    | "expired_token"
    | string;
  error_description?: string;
}

export class AuthManager {
  constructor(private readonly secrets: vscode.SecretStorage) {}

  async setApiKey(key: string): Promise<void> {
    await this.secrets.store(KEY_API, key);
    // API key wins over OIDC; clear any stale tokens.
    await this.secrets.delete(KEY_ACCESS);
    await this.secrets.delete(KEY_REFRESH);
    await this.secrets.delete(KEY_EXPIRES);
  }

  async setOidcSession(
    accessToken: string,
    refreshToken: string | undefined,
    tenantId: string | undefined,
    expiresInSec: number,
  ): Promise<void> {
    await this.secrets.store(KEY_ACCESS, accessToken);
    if (refreshToken) {
      await this.secrets.store(KEY_REFRESH, refreshToken);
    } else {
      await this.secrets.delete(KEY_REFRESH);
    }
    if (tenantId) {
      await this.secrets.store(KEY_TENANT, tenantId);
    }
    await this.secrets.store(
      KEY_EXPIRES,
      String(Date.now() + expiresInSec * 1000),
    );
    // Clear API key — bearer token wins until explicit sign-out.
    await this.secrets.delete(KEY_API);
  }

  async signOut(): Promise<void> {
    await Promise.all(
      [KEY_API, KEY_ACCESS, KEY_REFRESH, KEY_TENANT, KEY_EXPIRES].map((k) =>
        this.secrets.delete(k),
      ),
    );
  }

  /** Return the current credential blob for the gateway client. */
  async current(fallbackTenant: string | null): Promise<Credential> {
    const [apiKey, bearer, tenant] = await Promise.all([
      this.secrets.get(KEY_API),
      this.secrets.get(KEY_ACCESS),
      this.secrets.get(KEY_TENANT),
    ]);
    return {
      apiKey: apiKey || null,
      bearerToken: !apiKey ? bearer || null : null,
      tenantId: tenant || fallbackTenant || null,
    };
  }

  async hasCredential(): Promise<boolean> {
    const cred = await this.current(null);
    return !!(cred.apiKey || cred.bearerToken);
  }

  /**
   * Run the RFC 8628 device-code flow.
   *
   *  1. POST to the device authorisation endpoint, receive a
   *     verification URL + user code.
   *  2. Open the URL in the user's default browser; show the user
   *     code in a VS Code notification.
   *  3. Poll the token endpoint until the user approves, expiration,
   *     or the user cancels.
   */
  async signInWithDeviceCode(opts: {
    deviceCodeEndpoint: string;
    tokenEndpoint: string;
    clientId: string;
    scopes: string;
    fetchImpl?: typeof fetch;
    openExternal?: (uri: vscode.Uri) => Thenable<boolean>;
    progress?: vscode.Progress<{ message: string }>;
    token?: vscode.CancellationToken;
  }): Promise<boolean> {
    const fetchImpl = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);

    opts.progress?.report({ message: "Requesting device code…" });
    const initBody = new URLSearchParams({
      client_id: opts.clientId,
      scope: opts.scopes,
    });
    const init = await fetchImpl(opts.deviceCodeEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: initBody.toString(),
    });
    if (!init.ok) {
      const t = await init.text().catch(() => "");
      throw new Error(
        `device authorisation failed: HTTP ${init.status} ${t.slice(0, 200)}`,
      );
    }
    const challenge = (await init.json()) as DeviceCodeChallenge;

    // Open browser + show user code.
    const verify =
      challenge.verification_uri_complete ?? challenge.verification_uri;
    const open = opts.openExternal ?? vscode.env.openExternal;
    await open(vscode.Uri.parse(verify));
    void vscode.window.showInformationMessage(
      `Section: enter code ${challenge.user_code} in the browser to finish sign-in.`,
    );

    // Poll for the token.
    const intervalMs = Math.max(1, challenge.interval) * 1000;
    const deadline = Date.now() + challenge.expires_in * 1000;
    let nextInterval = intervalMs;

    while (Date.now() < deadline) {
      if (opts.token?.isCancellationRequested) return false;
      await sleep(nextInterval);
      opts.progress?.report({ message: "Waiting for browser approval…" });

      const pollBody = new URLSearchParams({
        client_id: opts.clientId,
        device_code: challenge.device_code,
        grant_type: "urn:ietf:params:oauth:grant-type:device_code",
      });
      const poll = await fetchImpl(opts.tokenEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: pollBody.toString(),
      });
      const raw = await poll.text();
      let parsed: DeviceTokenResponse | DeviceErrorResponse | null = null;
      try {
        parsed = raw ? (JSON.parse(raw) as any) : null;
      } catch {
        parsed = null;
      }

      if (poll.ok && parsed && "access_token" in parsed) {
        const tok = parsed as DeviceTokenResponse;
        const tenantId = decodeTenantClaim(tok.access_token);
        await this.setOidcSession(
          tok.access_token,
          tok.refresh_token,
          tenantId,
          tok.expires_in,
        );
        return true;
      }

      const err = parsed && "error" in parsed ? (parsed as DeviceErrorResponse).error : "unknown_error";
      if (err === "authorization_pending") {
        continue;
      }
      if (err === "slow_down") {
        nextInterval += 5000;
        continue;
      }
      if (err === "access_denied" || err === "expired_token") {
        throw new Error(`OIDC sign-in failed: ${err}`);
      }
      throw new Error(
        `OIDC sign-in error: ${err} (HTTP ${poll.status})`,
      );
    }
    throw new Error("OIDC sign-in timed out");
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Best-effort JWT tenant extraction. Reads the `tenant`, `tid`, or
 * `section_tenant` claim from an unverified JWT. We do NOT validate
 * the signature here — the gateway does that on every request.
 */
export function decodeTenantClaim(token: string): string | undefined {
  const parts = token.split(".");
  if (parts.length !== 3) return undefined;
  try {
    const payload = parts[1];
    if (!payload) return undefined;
    const json = Buffer.from(
      payload.replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    ).toString("utf-8");
    const claims = JSON.parse(json) as Record<string, unknown>;
    const t =
      claims["section_tenant"] ?? claims["tenant"] ?? claims["tid"];
    return typeof t === "string" ? t : undefined;
  } catch {
    return undefined;
  }
}
