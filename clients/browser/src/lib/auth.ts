/**
 * OIDC device-code (RFC 8628) flow for the browser extension.
 *
 * Why device-code: a content-script-hosted browser extension has no
 * stable redirect URI, can't carry a client secret, and shouldn't pop a
 * full authorisation_code dance from a popup. RFC 8628 is the standard
 * for this exact shape — IoT and CLIs use it for the same reason.
 *
 * Flow:
 *   1. POST {issuer}/device_authorization with client_id + scope.
 *      Discover the endpoint via {issuer}/.well-known/openid-configuration
 *      so we work against Keycloak / Auth0 / Okta / Azure AD.
 *   2. Open a new tab to `verification_uri_complete` (so the user lands
 *      directly on the code-confirmation screen).
 *   3. Poll the token endpoint every `interval` seconds. The IdP returns
 *      `authorization_pending` until the user approves; `access_denied`
 *      / `expired_token` end the flow.
 *   4. On success, store {access_token, refresh_token, expires_at}.
 *
 * Cancellation: the caller passes an `AbortSignal`; aborting stops the
 * polling loop. Useful for "I changed my mind" buttons in the popup.
 *
 * Refresh: see `refreshAccessToken()` — exchange refresh_token for a new
 * access_token. The gateway client calls this lazily on 401.
 */

export interface OidcDiscovery {
  issuer: string;
  device_authorization_endpoint: string;
  token_endpoint: string;
  authorization_endpoint?: string;
  revocation_endpoint?: string;
}

export interface DeviceAuthResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string;
  expires_in: number;
  interval: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
  id_token?: string;
  scope?: string;
}

export interface DeviceFlowResult {
  accessToken: string;
  refreshToken: string | null;
  expiresAt: number; // epoch ms
  idToken: string | null;
}

export class OidcError extends Error {
  constructor(message: string, public readonly code?: string) {
    super(message);
    this.name = 'OidcError';
  }
}

export class OidcUserCancelled extends OidcError {
  constructor() {
    super('User cancelled OIDC flow', 'access_denied');
    this.name = 'OidcUserCancelled';
  }
}

export interface OidcOptions {
  fetchImpl?: typeof fetch;
  scope?: string;
  /** Hard upper bound on the flow (s); IdPs usually cap at 600s already. */
  maxWaitSeconds?: number;
  /** Override sleep — primarily for tests. */
  sleep?: (ms: number) => Promise<void>;
}

const DEFAULTS: Required<Omit<OidcOptions, 'fetchImpl'>> & {
  fetchImpl: typeof fetch;
} = {
  fetchImpl: typeof fetch !== 'undefined' ? fetch.bind(globalThis) : (() => {
    throw new Error('fetch is not available');
  }) as unknown as typeof fetch,
  scope: 'openid profile email offline_access',
  maxWaitSeconds: 900,
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
};

export class DeviceFlow {
  private readonly opts: Required<Omit<OidcOptions, 'fetchImpl'>> & {
    fetchImpl: typeof fetch;
  };

  constructor(
    private readonly issuer: string,
    private readonly clientId: string,
    options: OidcOptions = {},
  ) {
    this.opts = { ...DEFAULTS, ...options };
    if (!issuer) throw new OidcError('issuer is required');
    if (!clientId) throw new OidcError('clientId is required');
  }

  async discover(): Promise<OidcDiscovery> {
    const base = this.issuer.replace(/\/$/, '');
    const url = `${base}/.well-known/openid-configuration`;
    const res = await this.opts.fetchImpl(url);
    if (!res.ok) {
      throw new OidcError(`Discovery failed: HTTP ${res.status}`);
    }
    const j = (await res.json()) as Record<string, unknown>;
    const dev = j['device_authorization_endpoint'];
    const tok = j['token_endpoint'];
    if (typeof dev !== 'string' || typeof tok !== 'string') {
      throw new OidcError(
        'IdP does not advertise device_authorization_endpoint or token_endpoint',
      );
    }
    return {
      issuer: this.issuer,
      device_authorization_endpoint: dev,
      token_endpoint: tok,
      authorization_endpoint: typeof j['authorization_endpoint'] === 'string'
        ? (j['authorization_endpoint'] as string)
        : undefined,
      revocation_endpoint: typeof j['revocation_endpoint'] === 'string'
        ? (j['revocation_endpoint'] as string)
        : undefined,
    };
  }

  /**
   * Kick off device authorization and return the response (so the
   * caller can show user_code + verification_uri before we begin
   * polling). The caller should then call `pollForToken()`.
   */
  async startDeviceAuth(discovery: OidcDiscovery): Promise<DeviceAuthResponse> {
    const body = new URLSearchParams({
      client_id: this.clientId,
      scope: this.opts.scope,
    });
    const res = await this.opts.fetchImpl(
      discovery.device_authorization_endpoint,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      },
    );
    if (!res.ok) {
      const txt = await safeText(res);
      throw new OidcError(
        `device_authorization failed: HTTP ${res.status} ${txt ?? ''}`.trim(),
      );
    }
    const j = (await res.json()) as Partial<DeviceAuthResponse>;
    if (!j.device_code || !j.user_code || !j.verification_uri) {
      throw new OidcError('device_authorization missing required fields');
    }
    return {
      device_code: j.device_code,
      user_code: j.user_code,
      verification_uri: j.verification_uri,
      verification_uri_complete: j.verification_uri_complete,
      expires_in: j.expires_in ?? 600,
      interval: j.interval ?? 5,
    };
  }

  /**
   * Poll the token endpoint until success, denial, or timeout. The
   * `interval` may be increased by `slow_down` responses (per RFC 8628
   * §3.5) — we add 5s each time.
   */
  async pollForToken(
    discovery: OidcDiscovery,
    auth: DeviceAuthResponse,
    signal?: AbortSignal,
  ): Promise<DeviceFlowResult> {
    let interval = Math.max(1, auth.interval);
    const start = Date.now();
    const hardDeadline =
      start + Math.min(auth.expires_in, this.opts.maxWaitSeconds) * 1000;

    while (Date.now() < hardDeadline) {
      if (signal?.aborted) throw new OidcUserCancelled();
      await this.opts.sleep(interval * 1000);
      if (signal?.aborted) throw new OidcUserCancelled();

      const body = new URLSearchParams({
        grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
        device_code: auth.device_code,
        client_id: this.clientId,
      });
      const res = await this.opts.fetchImpl(discovery.token_endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      });
      if (res.ok) {
        const tok = (await res.json()) as TokenResponse;
        return {
          accessToken: tok.access_token,
          refreshToken: tok.refresh_token ?? null,
          expiresAt: Date.now() + Math.max(0, tok.expires_in - 30) * 1000,
          idToken: tok.id_token ?? null,
        };
      }
      const errJson = (await res.json().catch(() => null)) as
        | { error?: string; error_description?: string }
        | null;
      const code = errJson?.error ?? `http_${res.status}`;
      if (code === 'authorization_pending') {
        continue;
      }
      if (code === 'slow_down') {
        interval += 5;
        continue;
      }
      if (code === 'access_denied') {
        throw new OidcUserCancelled();
      }
      if (code === 'expired_token') {
        throw new OidcError('device code expired', 'expired_token');
      }
      // Unknown error — surface and stop.
      throw new OidcError(
        errJson?.error_description ?? `token endpoint returned ${code}`,
        code,
      );
    }
    throw new OidcError('device code flow timed out', 'expired_token');
  }

  /**
   * Convenience: discover, start auth, open a tab to the verification
   * URL (best-effort), and poll until done.
   */
  async run(
    openTab: (url: string) => void | Promise<void>,
    signal?: AbortSignal,
  ): Promise<{ flow: DeviceAuthResponse; result: DeviceFlowResult }> {
    const discovery = await this.discover();
    const flow = await this.startDeviceAuth(discovery);
    await Promise.resolve(
      openTab(flow.verification_uri_complete ?? flow.verification_uri),
    );
    const result = await this.pollForToken(discovery, flow, signal);
    return { flow, result };
  }

  /**
   * Trade a refresh token for a new access token.
   */
  async refresh(
    discovery: OidcDiscovery,
    refreshToken: string,
  ): Promise<DeviceFlowResult> {
    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: this.clientId,
    });
    const res = await this.opts.fetchImpl(discovery.token_endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!res.ok) {
      throw new OidcError(
        `refresh failed: HTTP ${res.status}`,
        `http_${res.status}`,
      );
    }
    const tok = (await res.json()) as TokenResponse;
    return {
      accessToken: tok.access_token,
      refreshToken: tok.refresh_token ?? refreshToken,
      expiresAt: Date.now() + Math.max(0, tok.expires_in - 30) * 1000,
      idToken: tok.id_token ?? null,
    };
  }
}

async function safeText(res: Response): Promise<string | null> {
  try {
    return await res.text();
  } catch {
    return null;
  }
}
