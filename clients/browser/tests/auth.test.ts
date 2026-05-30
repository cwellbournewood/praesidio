import { describe, expect, it, vi } from 'vitest';
import {
  DeviceFlow,
  OidcError,
  OidcUserCancelled,
} from '../src/lib/auth.js';

const ISSUER = 'https://idp.example.com';
const CLIENT_ID = 'section-edge';

function makeFetch(responses: Array<{ url: string; status: number; body: unknown }>) {
  let i = 0;
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    const r = responses[i];
    if (!r) throw new Error(`unexpected fetch ${url}`);
    i += 1;
    if (!url.includes(r.url.replace(ISSUER, ''))) {
      throw new Error(`expected url match ${r.url} got ${url}`);
    }
    return new Response(JSON.stringify(r.body), { status: r.status });
  }) as unknown as typeof fetch;
}

describe('DeviceFlow.discover', () => {
  it('reads device_authorization_endpoint + token_endpoint from .well-known', async () => {
    const fetchImpl = makeFetch([
      {
        url: '/.well-known/openid-configuration',
        status: 200,
        body: {
          device_authorization_endpoint: `${ISSUER}/dev`,
          token_endpoint: `${ISSUER}/token`,
        },
      },
    ]);
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, { fetchImpl });
    const d = await flow.discover();
    expect(d.device_authorization_endpoint).toBe(`${ISSUER}/dev`);
    expect(d.token_endpoint).toBe(`${ISSUER}/token`);
  });

  it('throws OidcError if the IdP does not advertise device endpoint', async () => {
    const fetchImpl = makeFetch([
      {
        url: '/.well-known/openid-configuration',
        status: 200,
        body: { token_endpoint: 'x' },
      },
    ]);
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, { fetchImpl });
    await expect(flow.discover()).rejects.toBeInstanceOf(OidcError);
  });
});

describe('DeviceFlow.pollForToken', () => {
  it('polls past authorization_pending and resolves on token success', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      // First call: pending. Second: success.
      if (!(fetchImpl as unknown as { _calls?: number })._calls) {
        (fetchImpl as unknown as { _calls?: number })._calls = 1;
        return new Response(JSON.stringify({ error: 'authorization_pending' }), { status: 400 });
      }
      expect(url).toContain('/token');
      return new Response(JSON.stringify({ access_token: 'AT', refresh_token: 'RT', expires_in: 600, token_type: 'Bearer' }));
    }) as unknown as typeof fetch;
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, { fetchImpl, sleep: () => Promise.resolve() });
    const r = await flow.pollForToken(
      { issuer: ISSUER, device_authorization_endpoint: 'd', token_endpoint: `${ISSUER}/token` },
      { device_code: 'DC', user_code: 'AB-CD', verification_uri: 'u', expires_in: 60, interval: 1 },
    );
    expect(r.accessToken).toBe('AT');
    expect(r.refreshToken).toBe('RT');
    expect(r.expiresAt).toBeGreaterThan(Date.now());
  });

  it('throws OidcUserCancelled on access_denied', async () => {
    const fetchImpl = makeFetch([
      { url: '/token', status: 400, body: { error: 'access_denied' } },
    ]);
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, { fetchImpl, sleep: () => Promise.resolve() });
    await expect(
      flow.pollForToken(
        { issuer: ISSUER, device_authorization_endpoint: 'd', token_endpoint: `${ISSUER}/token` },
        { device_code: 'DC', user_code: 'AB-CD', verification_uri: 'u', expires_in: 60, interval: 1 },
      ),
    ).rejects.toBeInstanceOf(OidcUserCancelled);
  });

  it('bumps interval on slow_down', async () => {
    let calls = 0;
    const intervals: number[] = [];
    const fetchImpl = vi.fn(async () => {
      calls += 1;
      if (calls === 1) return new Response(JSON.stringify({ error: 'slow_down' }), { status: 400 });
      return new Response(JSON.stringify({ access_token: 'AT', expires_in: 600, token_type: 'Bearer' }));
    }) as unknown as typeof fetch;
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, {
      fetchImpl,
      sleep: (ms) => {
        intervals.push(ms);
        return Promise.resolve();
      },
    });
    await flow.pollForToken(
      { issuer: ISSUER, device_authorization_endpoint: 'd', token_endpoint: `${ISSUER}/token` },
      { device_code: 'DC', user_code: 'AB-CD', verification_uri: 'u', expires_in: 60, interval: 1 },
    );
    // First sleep at 1s, second at >=6s after slow_down (+5).
    expect(intervals[0]).toBe(1000);
    expect(intervals[1]).toBeGreaterThanOrEqual(6000);
  });

  it('honours AbortSignal', async () => {
    const fetchImpl = makeFetch([
      { url: '/token', status: 400, body: { error: 'authorization_pending' } },
    ]);
    const ctrl = new AbortController();
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, {
      fetchImpl,
      sleep: async () => {
        ctrl.abort();
      },
    });
    await expect(
      flow.pollForToken(
        { issuer: ISSUER, device_authorization_endpoint: 'd', token_endpoint: `${ISSUER}/token` },
        { device_code: 'DC', user_code: 'AB-CD', verification_uri: 'u', expires_in: 60, interval: 1 },
        ctrl.signal,
      ),
    ).rejects.toBeInstanceOf(OidcUserCancelled);
  });
});

describe('DeviceFlow.refresh', () => {
  it('exchanges refresh_token for a new access_token', async () => {
    const fetchImpl = makeFetch([
      { url: '/token', status: 200, body: { access_token: 'NEW', refresh_token: 'NEW-R', expires_in: 600, token_type: 'Bearer' } },
    ]);
    const flow = new DeviceFlow(ISSUER, CLIENT_ID, { fetchImpl });
    const r = await flow.refresh(
      { issuer: ISSUER, device_authorization_endpoint: 'd', token_endpoint: `${ISSUER}/token` },
      'old-refresh',
    );
    expect(r.accessToken).toBe('NEW');
    expect(r.refreshToken).toBe('NEW-R');
  });
});
