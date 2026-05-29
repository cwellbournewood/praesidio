import { describe, expect, it, vi } from 'vitest';
import {
  GatewayClient,
  GatewayAuthError,
  GatewayError,
  GatewayConfigError,
} from '../src/lib/gateway.js';
import { DEFAULT_SETTINGS, EMPTY_SECRETS } from '../src/lib/types.js';

function makeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    return handler(url, init ?? {});
  }) as unknown as typeof fetch;
}

describe('GatewayClient.scan', () => {
  it('sends X-API-Key when an API key is configured', async () => {
    const fetchImpl = makeFetch((_url, init) => {
      const headers = init.headers as Record<string, string>;
      expect(headers['X-API-Key']).toBe('test-key');
      expect(headers['Content-Type']).toBe('application/json');
      return new Response(
        JSON.stringify({
          request_id: 'r1',
          action: 'allow',
          sanitised: 'hi',
          transforms: [],
          findings: [],
          decision: {
            action: 'allow',
            mode: 'enforce',
            effective_action: 'allow',
            is_shadow: false,
            policy_id: null,
            policy_version: null,
            rule_index: null,
            reason: null,
            severity: null,
          },
          bundle_digest: 'd',
          reason: null,
          severity: null,
        }),
        { status: 200 },
      );
    });
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { ...EMPTY_SECRETS, apiKey: 'test-key' },
      { fetchImpl, maxRetries: 0 },
    );
    const resp = await client.scan({ text: 'hi', client: 'browser-extension' });
    expect(resp.action).toBe('allow');
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('uses OIDC Bearer when no API key but OIDC token exists', async () => {
    const fetchImpl = makeFetch((_url, init) => {
      const headers = init.headers as Record<string, string>;
      expect(headers['Authorization']).toBe('Bearer access-1');
      return new Response('{"request_id":"r","action":"allow","sanitised":"x","transforms":[],"findings":[],"decision":{"action":"allow","mode":"enforce","effective_action":"allow","is_shadow":false,"policy_id":null,"policy_version":null,"rule_index":null,"reason":null,"severity":null},"bundle_digest":"d","reason":null,"severity":null}');
    });
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { apiKey: null, oidc: { accessToken: 'access-1', refreshToken: null, expiresAt: Date.now() + 600_000 } },
      { fetchImpl, maxRetries: 0 },
    );
    await client.scan({ text: 'hi', client: 'browser-extension' });
  });

  it('throws GatewayAuthError on 401 without retrying', async () => {
    const fetchImpl = makeFetch(() => new Response('unauthorized', { status: 401 }));
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { ...EMPTY_SECRETS, apiKey: 'bad' },
      { fetchImpl, maxRetries: 3 },
    );
    await expect(client.scan({ text: 'hi', client: 'browser-extension' })).rejects.toBeInstanceOf(GatewayAuthError);
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('retries on 5xx and eventually succeeds', async () => {
    let calls = 0;
    const fetchImpl = makeFetch(() => {
      calls += 1;
      if (calls < 2) return new Response('boom', { status: 503 });
      return new Response('{"request_id":"r","action":"allow","sanitised":"x","transforms":[],"findings":[],"decision":{"action":"allow","mode":"enforce","effective_action":"allow","is_shadow":false,"policy_id":null,"policy_version":null,"rule_index":null,"reason":null,"severity":null},"bundle_digest":"d","reason":null,"severity":null}');
    });
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { ...EMPTY_SECRETS, apiKey: 'x' },
      { fetchImpl, maxRetries: 2, backoffMs: 1 },
    );
    const resp = await client.scan({ text: 'hi', client: 'browser-extension' });
    expect(resp.action).toBe('allow');
    expect(calls).toBe(2);
  });

  it('honours Retry-After on 429 and surfaces a GatewayError(429)', async () => {
    const fetchImpl = makeFetch(() => new Response('slow down', { status: 429, headers: { 'Retry-After': '1' } }));
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { ...EMPTY_SECRETS, apiKey: 'x' },
      { fetchImpl, maxRetries: 0, backoffMs: 1 },
    );
    try {
      await client.scan({ text: 'hi', client: 'browser-extension' });
      throw new Error('expected throw');
    } catch (err) {
      expect(err).toBeInstanceOf(GatewayError);
      expect((err as GatewayError).status).toBe(429);
      expect((err as GatewayError).retryAfterMs).toBe(1000);
    }
  });

  it('refuses to call a gateway URL outside the manifest allow-list', async () => {
    const fetchImpl = makeFetch(() => {
      throw new Error('should not be called');
    });
    const client = new GatewayClient(
      { gatewayUrl: 'https://evil.example.com' },
      { ...EMPTY_SECRETS, apiKey: 'x' },
      { fetchImpl, maxRetries: 0 },
    );
    await expect(client.scan({ text: 'hi', client: 'browser-extension' })).rejects.toBeInstanceOf(GatewayConfigError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('isAuthenticated returns false when OIDC token has expired', () => {
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { apiKey: null, oidc: { accessToken: 'x', refreshToken: 'r', expiresAt: Date.now() - 1000 } },
    );
    expect(client.isAuthenticated()).toBe(false);
  });
});

describe('GatewayClient.restore', () => {
  it('round-trips the restore payload', async () => {
    const fetchImpl = makeFetch((url, init) => {
      expect(url.endsWith('/v1/restore')).toBe(true);
      const body = JSON.parse(init.body as string);
      expect(body.request_id).toBe('req-1');
      expect(body.text).toBe('hello <EMAIL_A2B3>');
      return new Response('{"request_id":"req-1","text":"hello bob@x.com","restored":1,"missing":[]}');
    });
    const client = new GatewayClient(
      DEFAULT_SETTINGS,
      { ...EMPTY_SECRETS, apiKey: 'x' },
      { fetchImpl, maxRetries: 0 },
    );
    const resp = await client.restore({ request_id: 'req-1', text: 'hello <EMAIL_A2B3>' });
    expect(resp.restored).toBe(1);
    expect(resp.text).toContain('bob@x.com');
  });
});

describe('GatewayClient.ping', () => {
  it('returns ok=false with a reason on misconfigured URL', async () => {
    const client = new GatewayClient(
      { gatewayUrl: 'not-a-url' },
      EMPTY_SECRETS,
      { maxRetries: 0 },
    );
    const r = await client.ping();
    expect(r.ok).toBe(false);
    expect(r.error).toBeTruthy();
  });
});
