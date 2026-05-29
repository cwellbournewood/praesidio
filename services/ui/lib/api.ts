// Thin client around the gateway's /admin/* API.
//
// Mode resolution (each call, freshly evaluated so runtime toggles work):
//   1. If runtime mode is "mock" (operator chose mock from the Topbar, or no
//      gateway URL was baked in)  → serve from lib/mock.ts.
//   2. Otherwise → POST/GET against `NEXT_PUBLIC_GATEWAY_URL`.
//      On network failure, fall back to mock data so the console stays
//      interactive instead of going blank. (A WARN line is logged once per
//      session per endpoint.)
//
// Every outbound request carries `X-Praesidio-Tenant: <id>` (when a tenant is
// selected) so the gateway can scope authorisation. The header is added
// transparently — call-sites should never have to thread it through.

import type {
  AuditEvent,
  DashboardKpis,
  GatewayHealth,
  LineageGraphData,
  ModelCardEntry,
  Policy,
  SimulateRequest,
  SimulateResponse,
  Tenant,
} from './types';
import {
  MOCK_MODE,
  mockEvents,
  mockHealth,
  mockKpis,
  mockLineage,
  mockModels,
  mockPolicies,
} from './mock';
import { currentMode } from './runtime-mode';
import { currentTenant, MOCK_TENANTS } from './tenant';

function gatewayBase(): string {
  if (typeof window === 'undefined') {
    return (
      process.env.PRAESIDIO_GATEWAY_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_GATEWAY_URL ??
      'http://localhost:8080'
    );
  }
  return process.env.NEXT_PUBLIC_GATEWAY_URL ?? 'http://localhost:8080';
}

/** True when the operator (or build env) has selected mock data. */
function shouldUseMock(): boolean {
  if (MOCK_MODE) return true;
  // SSR: trust the build-time env. Browser: honour runtime override.
  if (typeof window === 'undefined') return !process.env.NEXT_PUBLIC_GATEWAY_URL;
  return currentMode() === 'mock';
}

function tenantHeaders(): Record<string, string> {
  const id = currentTenant();
  return id ? { 'X-Praesidio-Tenant': id } : {};
}

const warned = new Set<string>();
function warnFallback(path: string, err: unknown): void {
  if (warned.has(path)) return;
  warned.add(path);
  // eslint-disable-next-line no-console
  console.warn(`[praesidio.api] ${path} unreachable — serving mock data.`, err);
}

async function safeFetch<T>(
  path: string,
  fallback: () => T,
  init?: RequestInit,
): Promise<T> {
  if (shouldUseMock()) return fallback();
  try {
    const res = await fetch(`${gatewayBase()}${path}`, {
      ...init,
      headers: {
        accept: 'application/json',
        ...tenantHeaders(),
        ...(init?.headers ?? {}),
      },
      cache: 'no-store',
    });
    if (!res.ok) throw new Error(`gateway ${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    warnFallback(path, err);
    return fallback();
  }
}

function mockSimulate(req: SimulateRequest): SimulateResponse {
  // A deterministic, illustrative simulator response — good enough for the UI
  // preview when the gateway isn't reachable.
  const prompt = req.prompt ?? '';
  const findings: SimulateResponse['findings'] = [];
  const transforms: SimulateResponse['transforms'] = [];
  let sanitised = prompt;

  const detectors: Array<{
    re: RegExp;
    label: import('./types').DetectorLabel;
    method: import('./types').TransformMethod;
    token: (m: string) => string;
  }> = [
    {
      re: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,
      label: 'pii.email',
      method: 'tokenise',
      token: () =>
        `<EMAIL_${Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0')}>`,
    },
    {
      re: /(?:\+?\d[\d\s().-]{7,}\d)/g,
      label: 'pii.phone',
      method: 'fpe',
      token: (m) => m.replace(/\d/g, (d) => String((Number(d) + 3) % 10)),
    },
    {
      re: /\b(?:\d[ -]*?){13,16}\b/g,
      label: 'financial.credit_card',
      method: 'redact',
      token: () => '[REDACTED_PAN]',
    },
    {
      re: /\bAKIA[0-9A-Z]{16}\b/g,
      label: 'credential.aws_access_key',
      method: 'redact',
      token: () => '[BLOCKED_AWS]',
    },
  ];

  // Walk each detector; emit findings + transforms; produce sanitised copy.
  for (const det of detectors) {
    let m: RegExpExecArray | null;
    det.re.lastIndex = 0;
    while ((m = det.re.exec(prompt))) {
      const start = m.index;
      const end = m.index + m[0].length;
      const replacement = det.token(m[0]);
      findings.push({
        label: det.label,
        span: [start, end],
        score: 0.92,
        detector_version: 'sim-2026.05',
        vault_token: det.method === 'redact' ? null : replacement,
        replacement: det.method === 'redact' ? replacement : null,
      });
      transforms.push({
        label: det.label,
        method: det.method,
        span: [start, end],
        replacement,
      });
      if (det.method === 'redact' && det.label === 'credential.aws_access_key') {
        return {
          decision: 'block',
          rule_id: 'block-secrets',
          rule_index: 0,
          policy_id: req.policy_id ?? 'pii-strict',
          policy_version: 'v2026.05.3 (sim)',
          reason: 'Credential leakage attempt (sim)',
          findings,
          transforms,
          sanitised: 'BLOCKED: credential leakage attempt (credential.aws_access_key)',
          latency_ms: 12,
        };
      }
    }
  }

  // Apply transforms in reverse-position order so spans stay valid.
  const sorted = [...transforms].sort((a, b) => b.span[0] - a.span[0]);
  for (const t of sorted) {
    sanitised = sanitised.slice(0, t.span[0]) + t.replacement + sanitised.slice(t.span[1]);
  }

  const decision = transforms.length > 0 ? 'transform' : 'allow';
  return {
    decision,
    rule_id: decision === 'transform' ? 'transform-pii' : 'default-allow',
    rule_index: decision === 'transform' ? 1 : 2,
    policy_id: req.policy_id ?? 'pii-strict',
    policy_version: 'v2026.05.3 (sim)',
    reason: undefined,
    findings,
    transforms,
    sanitised,
    latency_ms: 8 + transforms.length * 2,
  };
}

export const api = {
  events: (params?: { limit?: number }) =>
    safeFetch<AuditEvent[]>(
      `/admin/events?limit=${params?.limit ?? 200}`,
      () => mockEvents().slice(0, params?.limit ?? 200),
    ),
  policies: () => safeFetch<Policy[]>('/admin/policies', mockPolicies),
  policy: (id: string) =>
    safeFetch<Policy | undefined>(`/admin/policies/${id}`, () =>
      mockPolicies().find((p) => p.id === id),
    ),
  lineage: (requestId: string) =>
    safeFetch<LineageGraphData>(`/admin/lineage/${requestId}`, () => mockLineage(requestId)),
  models: () => safeFetch<ModelCardEntry[]>('/admin/models', mockModels),
  kpis: () => safeFetch<DashboardKpis>('/admin/metrics/summary', mockKpis),
  health: () => safeFetch<GatewayHealth>('/healthz', mockHealth),
  tenants: () => safeFetch<Tenant[]>('/admin/tenants', () => MOCK_TENANTS),
  simulate: (req: SimulateRequest) =>
    safeFetch<SimulateResponse>(
      '/admin/simulate',
      () => mockSimulate(req),
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(req),
      },
    ),
};

// SWR fetcher
export const swrFetcher = async (key: string) => {
  const path = key.startsWith('/') ? key : `/${key}`;
  if (shouldUseMock()) {
    // Crude routing for the mock layer.
    if (path.startsWith('/admin/events')) return api.events();
    if (path === '/admin/policies') return api.policies();
    if (path.startsWith('/admin/policies/')) return api.policy(path.split('/').pop()!);
    if (path.startsWith('/admin/lineage/')) return api.lineage(path.split('/').pop()!);
    if (path === '/admin/models') return api.models();
    if (path === '/admin/metrics/summary') return api.kpis();
    if (path === '/admin/tenants') return api.tenants();
    if (path === '/healthz') return api.health();
  }
  try {
    const res = await fetch(`${gatewayBase()}${path}`, {
      cache: 'no-store',
      headers: { accept: 'application/json', ...tenantHeaders() },
    });
    if (!res.ok) throw new Error(`gateway ${res.status}`);
    return res.json();
  } catch (err) {
    warnFallback(path, err);
    // Graceful degradation — try the mock layer if we know the route.
    if (path.startsWith('/admin/events')) return api.events();
    if (path === '/admin/policies') return api.policies();
    if (path.startsWith('/admin/policies/')) return api.policy(path.split('/').pop()!);
    if (path.startsWith('/admin/lineage/')) return api.lineage(path.split('/').pop()!);
    if (path === '/admin/models') return api.models();
    if (path === '/admin/metrics/summary') return api.kpis();
    if (path === '/admin/tenants') return api.tenants();
    if (path === '/healthz') return api.health();
    throw err;
  }
};
