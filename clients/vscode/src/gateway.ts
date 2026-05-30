/**
 * HTTP client for the Section gateway.
 *
 * Targets `POST /v1/scan` and `POST /v1/restore` defined in
 * `services/gateway/section_gateway/api/v1/scan.py`. Uses the global
 * `fetch` polyfilled by Node 18+/undici (VS Code 1.85 ships Node 20).
 *
 * Auth: caller supplies a credential blob — either an API key (sent as
 * `X-API-Key`) or a bearer JWT (sent as `Authorization: Bearer …`).
 * Empty credentials are allowed; the gateway has a "default" tenant
 * for dev/anonymous use.
 */

import type {
  RestoreRequest,
  RestoreResponse,
  ScanRequest,
  ScanResponse,
} from "./lib/types.js";

export interface Credential {
  /** Optional API key — takes precedence over `bearerToken`. */
  apiKey?: string | null;
  /** Optional OIDC bearer token. */
  bearerToken?: string | null;
  /** Optional tenant id; overridden by JWT claim if a bearer is set. */
  tenantId?: string | null;
}

export interface GatewayOptions {
  /** Base URL (e.g. http://localhost:8080). Trailing slash optional. */
  baseUrl: string;
  /** Per-request timeout (ms). Default 8000. */
  timeoutMs?: number;
  /** Override `fetch` for tests. */
  fetchImpl?: typeof fetch;
}

/** Thrown when the gateway returns a non-2xx response. */
export class GatewayHttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: string,
  ) {
    super(message);
    this.name = "GatewayHttpError";
  }
}

/** Thrown on network failure / timeout. */
export class GatewayNetworkError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = "GatewayNetworkError";
  }
}

export class GatewayClient {
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  public readonly baseUrl: string;

  constructor(opts: GatewayOptions) {
    if (!opts.baseUrl) {
      throw new Error("GatewayClient: baseUrl is required");
    }
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = opts.timeoutMs ?? 8000;
    this.fetchImpl = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  /** Health probe — used by the status bar tooltip. Returns true if /healthz returns 2xx. */
  async health(): Promise<boolean> {
    try {
      const r = await this.request("GET", "/healthz", null, {});
      return r.ok;
    } catch {
      return false;
    }
  }

  async scan(
    payload: ScanRequest,
    cred: Credential,
  ): Promise<ScanResponse> {
    const resp = await this.request("POST", "/v1/scan", payload, cred);
    const raw = await readText(resp);
    if (!resp.ok) {
      throw new GatewayHttpError(
        `scan failed: HTTP ${resp.status}`,
        resp.status,
        raw,
      );
    }
    return safeJson<ScanResponse>(raw, "/v1/scan");
  }

  async restore(
    payload: RestoreRequest,
    cred: Credential,
  ): Promise<RestoreResponse> {
    const resp = await this.request("POST", "/v1/restore", payload, cred);
    const raw = await readText(resp);
    if (!resp.ok) {
      throw new GatewayHttpError(
        `restore failed: HTTP ${resp.status}`,
        resp.status,
        raw,
      );
    }
    return safeJson<RestoreResponse>(raw, "/v1/restore");
  }

  private async request(
    method: "GET" | "POST",
    path: string,
    body: unknown,
    cred: Credential,
  ): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "User-Agent": "section-vscode/1.1",
    };
    if (body !== null && body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (cred.apiKey) {
      headers["X-API-Key"] = cred.apiKey;
    } else if (cred.bearerToken) {
      headers["Authorization"] = `Bearer ${cred.bearerToken}`;
    }
    if (cred.tenantId) {
      headers["X-Section-Tenant"] = cred.tenantId;
    }

    const url = `${this.baseUrl}${path}`;
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), this.timeoutMs);
    try {
      return await this.fetchImpl(url, {
        method,
        headers,
        body: body !== null && body !== undefined ? JSON.stringify(body) : undefined,
        signal: ac.signal,
      });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        throw new GatewayNetworkError(
          `request to ${url} timed out after ${this.timeoutMs}ms`,
          err,
        );
      }
      throw new GatewayNetworkError(
        `request to ${url} failed: ${(err as Error).message}`,
        err,
      );
    } finally {
      clearTimeout(timer);
    }
  }
}

async function readText(r: Response): Promise<string> {
  try {
    return await r.text();
  } catch {
    return "";
  }
}

function safeJson<T>(raw: string, where: string): T {
  if (!raw) {
    throw new GatewayHttpError(`${where}: empty body`, 502, raw);
  }
  try {
    return JSON.parse(raw) as T;
  } catch (e) {
    throw new GatewayHttpError(
      `${where}: invalid JSON: ${(e as Error).message}`,
      502,
      raw,
    );
  }
}
