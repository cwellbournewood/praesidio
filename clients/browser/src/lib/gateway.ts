/**
 * Gateway client: typed wrappers around `POST /v1/scan` and
 * `POST /v1/restore`.
 *
 * - Includes auth (API key OR OIDC Bearer) and retries with exponential
 *   backoff for transient (5xx, network) failures.
 * - On 401 with OIDC, the caller is responsible for refreshing the
 *   access token (see `auth.ts`) and retrying once.
 * - Honours `Retry-After` on 429.
 * - Uses `AbortController` with a per-call timeout; the default 6s is
 *   long enough for a cold gateway boot and short enough that a typing
 *   user doesn't sit on a frozen send button.
 */
import { canonicaliseGatewayUrl, checkGatewayUrl } from './csp.js';
import type {
  PingResponse,
  RestoreRequest,
  RestoreResponse,
  ScanRequest,
  ScanResponse,
  Secrets,
  Settings,
} from './types.js';

export interface GatewayClientOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  /** Max retries on 5xx / network errors. Default 2 (so 3 attempts total). */
  maxRetries?: number;
  /** Base backoff in ms. Default 200; doubles each retry. */
  backoffMs?: number;
}

export class GatewayError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly retryAfterMs: number | null = null,
    public readonly body: string | null = null,
  ) {
    super(message);
    this.name = 'GatewayError';
  }
}

export class GatewayAuthError extends GatewayError {
  constructor(message: string, body: string | null = null) {
    super(message, 401, null, body);
    this.name = 'GatewayAuthError';
  }
}

export class GatewayConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GatewayConfigError';
  }
}

const DEFAULTS: Required<GatewayClientOptions> = {
  fetchImpl: typeof fetch !== 'undefined' ? fetch.bind(globalThis) : (() => {
    throw new Error('fetch is not available');
  }) as unknown as typeof fetch,
  timeoutMs: 6000,
  maxRetries: 2,
  backoffMs: 200,
};

export class GatewayClient {
  private readonly opts: Required<GatewayClientOptions>;

  constructor(
    private readonly settings: Pick<Settings, 'gatewayUrl'>,
    private readonly secrets: Pick<Secrets, 'apiKey' | 'oidc'>,
    options: GatewayClientOptions = {},
  ) {
    this.opts = { ...DEFAULTS, ...options };
  }

  /**
   * GET /healthz. Cheap reachability check the popup uses on open.
   */
  async ping(): Promise<PingResponse> {
    const t0 = Date.now();
    const check = checkGatewayUrl(this.settings.gatewayUrl);
    if (!check.ok) {
      return {
        ok: false,
        gatewayUrl: this.settings.gatewayUrl,
        authenticated: this.isAuthenticated(),
        error: check.reason,
      };
    }
    const url = canonicaliseGatewayUrl(this.settings.gatewayUrl) + '/healthz';
    try {
      const res = await this.fetchWithTimeout(url, { method: 'GET' });
      return {
        ok: res.ok,
        gatewayUrl: this.settings.gatewayUrl,
        authenticated: this.isAuthenticated(),
        latencyMs: Date.now() - t0,
        error: res.ok ? undefined : `HTTP ${res.status}`,
      };
    } catch (err) {
      return {
        ok: false,
        gatewayUrl: this.settings.gatewayUrl,
        authenticated: this.isAuthenticated(),
        latencyMs: Date.now() - t0,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  isAuthenticated(): boolean {
    if (this.secrets.apiKey) return true;
    const oidc = this.secrets.oidc;
    if (!oidc?.accessToken) return false;
    if (oidc.expiresAt && oidc.expiresAt < Date.now()) return false;
    return true;
  }

  async scan(req: ScanRequest): Promise<ScanResponse> {
    return this.post<ScanResponse>('/v1/scan', req);
  }

  async restore(req: RestoreRequest): Promise<RestoreResponse> {
    return this.post<RestoreResponse>('/v1/restore', req);
  }

  /**
   * Issue a POST with auth, retries, timeout, Retry-After handling.
   * Exposed for tests; prefer the typed methods.
   */
  async post<T>(path: string, body: unknown): Promise<T> {
    const check = checkGatewayUrl(this.settings.gatewayUrl);
    if (!check.ok) {
      throw new GatewayConfigError(check.reason ?? 'invalid gateway URL');
    }
    const url = canonicaliseGatewayUrl(this.settings.gatewayUrl) + path;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    };
    if (this.secrets.apiKey) {
      headers['X-API-Key'] = this.secrets.apiKey;
    } else if (this.secrets.oidc?.accessToken) {
      headers['Authorization'] = `Bearer ${this.secrets.oidc.accessToken}`;
    }
    let lastErr: unknown;
    for (let attempt = 0; attempt <= this.opts.maxRetries; attempt += 1) {
      try {
        const res = await this.fetchWithTimeout(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });
        if (res.status === 401) {
          const txt = await safeText(res);
          throw new GatewayAuthError('Gateway rejected credentials', txt);
        }
        if (res.status === 429) {
          const ra = parseRetryAfter(res.headers.get('Retry-After'));
          throw new GatewayError(
            'Rate limited',
            429,
            ra,
            await safeText(res),
          );
        }
        if (res.status >= 500) {
          throw new GatewayError(
            `Gateway 5xx: ${res.status}`,
            res.status,
            null,
            await safeText(res),
          );
        }
        if (!res.ok) {
          throw new GatewayError(
            `Gateway error: HTTP ${res.status}`,
            res.status,
            null,
            await safeText(res),
          );
        }
        const data = (await res.json()) as T;
        return data;
      } catch (err) {
        lastErr = err;
        // Don't retry auth or 4xx; do retry 5xx + network.
        if (err instanceof GatewayAuthError) throw err;
        if (
          err instanceof GatewayError &&
          err.status !== 429 &&
          err.status < 500
        ) {
          throw err;
        }
        if (attempt >= this.opts.maxRetries) break;
        const wait =
          (err instanceof GatewayError && err.retryAfterMs) ||
          this.opts.backoffMs * Math.pow(2, attempt);
        await sleep(wait);
      }
    }
    throw lastErr instanceof Error
      ? lastErr
      : new GatewayError(String(lastErr), 0);
  }

  private async fetchWithTimeout(
    url: string,
    init: RequestInit,
  ): Promise<Response> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.opts.timeoutMs);
    try {
      return await this.opts.fetchImpl(url, { ...init, signal: ctrl.signal });
    } finally {
      clearTimeout(t);
    }
  }
}

function parseRetryAfter(raw: string | null): number | null {
  if (!raw) return null;
  // Seconds.
  const n = Number(raw);
  if (!Number.isNaN(n) && Number.isFinite(n)) return Math.max(0, n * 1000);
  // HTTP-date.
  const t = Date.parse(raw);
  if (!Number.isNaN(t)) return Math.max(0, t - Date.now());
  return null;
}

async function safeText(res: Response): Promise<string | null> {
  try {
    return await res.text();
  } catch {
    return null;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
