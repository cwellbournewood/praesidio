// Synthetic data for local development and the "no gateway reachable" fallback.
// All identifiers are obviously test data (4242 cards, example.com domains).

import type {
  AuditEvent,
  DashboardKpis,
  Decision,
  DetectorLabel,
  Finding,
  GatewayHealth,
  LineageGraphData,
  ModelCardEntry,
  Policy,
} from './types';

export const MOCK_MODE =
  typeof process !== 'undefined' && process.env.NEXT_PUBLIC_MOCK === '1';

const TENANTS = ['acme', 'globex', 'initech'];

const PRINCIPALS = [
  { user_id: 'u_8s2', email: 'alice.kim@acme.example', tenant_id: 'acme', groups: ['marketing'], country: 'US' },
  { user_id: 'u_2lk', email: 'john.mathers@acme.example', tenant_id: 'acme', groups: ['support'], country: 'US' },
  { user_id: 'u_91j', email: 'priya.patel@globex.example', tenant_id: 'globex', groups: ['engineering'], country: 'IN' },
  { user_id: 'u_44a', email: 'leo.schmidt@globex.example', tenant_id: 'globex', groups: ['sales', 'marketing'], country: 'DE' },
  { user_id: 'u_07f', email: 'mei.tanaka@initech.example', tenant_id: 'initech', groups: ['finance'], country: 'JP' },
  { user_id: 'u_55z', email: 'samir.rao@initech.example', tenant_id: 'initech', groups: ['legal'], country: 'GB' },
  { user_id: 'svc_etl', email: 'etl@acme.example', tenant_id: 'acme', groups: ['service'], country: 'US' },
];

const UPSTREAMS = [
  'openai/gpt-4o-mini',
  'openai/gpt-4o',
  'anthropic/claude-3-5-sonnet',
  'azure-westeurope/gpt-4o',
  'ollama/llama-3.1-70b',
  'mistral/mixtral-8x22b',
];

const ROUTES = [
  '/v1/chat/completions',
  '/v1/completions',
  '/v1/embeddings',
  '/anthropic/v1/messages',
];

const FINDING_TEMPLATES: Array<{ label: DetectorLabel; replacement?: string; method: Finding['vault_token'] extends string ? string : string }> = [
  { label: 'pii.email', method: 'tokenise' },
  { label: 'pii.phone', method: 'fpe' },
  { label: 'financial.iban', method: 'redact', replacement: '[REDACTED_IBAN]' },
  { label: 'financial.credit_card', method: 'redact', replacement: '[REDACTED_PAN]' },
  { label: 'pii.person', method: 'tokenise' },
  { label: 'pii.location', method: 'tokenise' },
  { label: 'pii.organization', method: 'tokenise' },
  { label: 'credential.aws_access_key', method: 'block' },
  { label: 'credential.gcp_service_account', method: 'block' },
  { label: 'credential.generic_high_entropy', method: 'block' },
  { label: 'code.block', method: 'redact' },
  { label: 'code.proprietary_marker', method: 'block' },
];

// Deterministic pseudo-random so the mock dataset is stable across renders.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(0xc0ffee);

function pick<T>(xs: T[]): T {
  return xs[Math.floor(rand() * xs.length)]!;
}

function uuid(): string {
  // Pseudo UUID — good enough for synthetic data; not for production.
  const hex = '0123456789abcdef';
  let s = '';
  for (let i = 0; i < 32; i++) s += hex[Math.floor(rand() * 16)];
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-7${s.slice(13, 16)}-${s.slice(16, 20)}-${s.slice(20, 32)}`;
}

function vaultToken(label: string): string {
  const family = label.replace(/^.*\./, '').toUpperCase();
  return `<${family}_${Math.floor(rand() * 0xffffff).toString(16).padStart(6, '0')}>`;
}

function buildFindings(decision: Decision): Finding[] {
  if (decision === 'allow') return [];
  const n = decision === 'block' ? 1 + Math.floor(rand() * 2) : 1 + Math.floor(rand() * 4);
  const out: Finding[] = [];
  for (let i = 0; i < n; i++) {
    const tpl = pick(
      decision === 'block'
        ? FINDING_TEMPLATES.filter(
            (t) => t.label.startsWith('credential.') || t.label === 'code.proprietary_marker',
          )
        : FINDING_TEMPLATES.filter(
            (t) => !t.label.startsWith('credential.') && t.label !== 'code.proprietary_marker',
          ),
    );
    const start = Math.floor(rand() * 800);
    out.push({
      label: tpl.label,
      span: [start, start + 6 + Math.floor(rand() * 24)],
      score: 0.7 + rand() * 0.29,
      detector_version: '2026.04.1',
      vault_token: tpl.replacement ? null : vaultToken(tpl.label),
      replacement: tpl.replacement ?? null,
    });
  }
  return out;
}

const SANITISED_SAMPLES: Array<{ original: string; sanitised: string }> = [
  {
    original:
      'Please email the renewal contract to alice.kim@acme.example by Friday; her direct line is +1 415 555 0142.',
    sanitised:
      'Please email the renewal contract to <EMAIL_a1f309> by Friday; her direct line is <PHONE_e92b71>.',
  },
  {
    original:
      'Customer John Mathers paid with card 4242 4242 4242 4242 — please refund €120 to IBAN DE89 3704 0044 0532 0130 00.',
    sanitised:
      'Customer <PERSON_4c1a> paid with card [REDACTED_PAN] — please refund €120 to [REDACTED_IBAN].',
  },
  {
    original:
      'AWS access key AKIAIOSFODNN7EXAMPLE is failing — can you rotate it for the data-eng account?',
    sanitised: 'BLOCKED: credential leakage attempt (credential.aws_access_key)',
  },
  {
    original:
      'Summarise the attached medical record for patient Mei Tanaka, MRN 220194, diagnosed with type-2 diabetes.',
    sanitised:
      'Summarise the attached medical record for patient <PERSON_8e22>, MRN <MRN_a91c>, diagnosed with type-2 diabetes.',
  },
  {
    original:
      'Draft a sales pitch for Globex GmbH — Leo Schmidt is the buyer at leo.schmidt@globex.example.',
    sanitised:
      'Draft a sales pitch for <ORG_71fa> — <PERSON_2811> is the buyer at <EMAIL_3b4c>.',
  },
  {
    original:
      'What does this Python function do?\n```python\ndef secret_sauce(x):\n    return x * 1337\n```',
    sanitised: 'What does this Python function do?\n[CODE_REDACTED 4 lines]',
  },
  {
    original: 'Hi! Can you help me brainstorm marketing taglines for a new espresso machine?',
    sanitised: 'Hi! Can you help me brainstorm marketing taglines for a new espresso machine?',
  },
];

function buildOneEvent(i: number, now: number): AuditEvent {
  // Decision distribution: 62% allow, 28% transform, 7% block, 2% simulate, 1% error
  const roll = rand();
  const decision: Decision =
    roll < 0.62 ? 'allow' : roll < 0.9 ? 'transform' : roll < 0.97 ? 'block' : roll < 0.99 ? 'simulate' : 'error';
  const principal = pick(PRINCIPALS);
  const upstream = pick(UPSTREAMS);
  const route = pick(ROUTES);
  const findings = buildFindings(decision);
  const sample = pick(SANITISED_SAMPLES);
  const occurred = new Date(now - i * 47_000 - Math.floor(rand() * 30_000)).toISOString();
  const baseLatency = upstream.includes('claude') ? 480 : upstream.includes('llama') ? 720 : 310;
  return {
    id: uuid(),
    tenant_id: principal.tenant_id,
    occurred_at: occurred,
    principal: { ...principal, ip: `10.${Math.floor(rand() * 250)}.${Math.floor(rand() * 250)}.${Math.floor(rand() * 250)}` },
    route,
    upstream,
    decision,
    rule_id: decision === 'allow' ? 'default-allow' : decision === 'block' ? 'block-secrets' : 'transform-pii',
    rule_index: decision === 'allow' ? 2 : decision === 'block' ? 0 : 1,
    policy_id: 'pii-strict',
    policy_version: 'v2026.05.3',
    bundle_digest: 'sha256:9c4f…b71e',
    findings,
    transforms:
      decision === 'transform'
        ? findings.map((f) => ({
            label: f.label,
            method: (f.replacement ? 'redact' : 'tokenise') as 'tokenise' | 'redact' | 'fpe',
            count: 1,
            scope: 'session' as const,
            ttl: '1h',
          }))
        : [],
    request_digest: `sha256:${uuid().replace(/-/g, '').slice(0, 16)}…`,
    response_digest: decision === 'block' ? undefined : `sha256:${uuid().replace(/-/g, '').slice(0, 16)}…`,
    latency_ms: Math.floor(baseLatency + rand() * 260 + (findings.length * 18)),
    bytes_in: 240 + Math.floor(rand() * 4_800),
    bytes_out: decision === 'block' ? 96 : 320 + Math.floor(rand() * 8_400),
    degraded: rand() < 0.04,
    reason:
      decision === 'block'
        ? 'Credential leakage attempt'
        : decision === 'error'
          ? 'Upstream timeout — fail-closed'
          : undefined,
    sanitised_preview: sample.sanitised,
    received_preview: sample.original,
  };
}

let _events: AuditEvent[] | null = null;
export function mockEvents(): AuditEvent[] {
  if (_events) return _events;
  const now = Date.now();
  _events = Array.from({ length: 220 }, (_, i) => buildOneEvent(i, now));
  return _events;
}

export function mockKpis(): DashboardKpis {
  const events = mockEvents();
  const today = events.slice(0, 1_840); // pretend day window
  const transformed = today.filter((e) => e.decision === 'transform').length;
  const blocked = today.filter((e) => e.decision === 'block').length;
  const tally = new Map<DetectorLabel, number>();
  for (const e of today) {
    for (const f of e.findings) tally.set(f.label, (tally.get(f.label) ?? 0) + 1);
  }
  const top = [...tally.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const latencies = today.map((e) => e.latency_ms).sort((a, b) => a - b);
  const p99 = latencies[Math.floor(latencies.length * 0.99)] ?? 0;
  // 24 buckets, last 24h — produce a believable diurnal shape.
  const spark = Array.from({ length: 24 }, (_, h) => {
    const base = 40 + 80 * Math.sin(((h - 4) / 24) * Math.PI * 2);
    return Math.max(8, Math.round(base + (h % 5) * 9 + 30));
  });
  return {
    requests_today: 1_843 + Math.floor(today.length / 4),
    transformed_pct: (transformed / today.length) * 100,
    blocked_pct: (blocked / today.length) * 100,
    top_detectors: top,
    p99_latency_ms: p99,
    spark,
  };
}

const PII_STRICT_YAML = `apiVersion: praesidio/v1
kind: Policy
metadata:
  id: pii-strict
  name: "Strict PII anonymisation"
  owner: data-protection@acme.example
  description: |
    Tokenise emails and people names; FPE phone numbers; redact IBANs and
    credit-card-shaped numbers; block AWS / GCP / Azure / generic secrets.
spec:
  match:
    routes: ["/v1/chat/completions", "/v1/completions", "/anthropic/v1/messages"]
    tenants: ["*"]
  detect:
    enable:
      - pii.email
      - pii.phone
      - financial.iban
      - financial.credit_card
      - pii.person
      - pii.location
      - credential.aws_access_key
      - credential.gcp_service_account
      - credential.azure_storage_key
      - credential.generic_high_entropy
    thresholds:
      pii.person: 0.7
      pii.location: 0.8
  decide:
    rules:
      - when: "any(findings, .label in ['credential.aws_access_key','credential.gcp_service_account','credential.azure_storage_key','credential.generic_high_entropy'])"
        action: block
        reason: "Credential leakage attempt"
        severity: critical
      - when: "any(findings, .label in ['pii.email','pii.person','pii.phone','financial.iban','financial.credit_card'])"
        action: transform
        transforms:
          - { label: pii.email,     method: tokenise, scope: session, ttl: 1h }
          - { label: pii.person, method: tokenise, scope: session, ttl: 1h }
          - { label: pii.phone,     method: fpe }
          - { label: financial.iban,      method: redact, replacement: "[REDACTED_IBAN]" }
          - { label: financial.credit_card,        method: redact, replacement: "[REDACTED_PAN]" }
      - when: "true"
        action: allow
  fail_mode: closed
  audit:
    severity_min: info
`;

const CODE_PROTECTION_YAML = `apiVersion: praesidio/v1
kind: Policy
metadata:
  id: code-protection
  name: "Source code & secret protection"
  owner: appsec@acme.example
  description: |
    Strip embedded source code and block any request shipping recognised
    cloud credentials or generic secret patterns to external upstreams.
spec:
  match:
    routes: ["/v1/chat/completions", "/v1/completions"]
    tenants: ["*"]
    principals:
      groups: ["engineering", "data-eng"]
  detect:
    enable:
      - code.block
      - credential.aws_access_key
      - credential.gcp_service_account
      - credential.azure_storage_key
      - credential.generic_high_entropy
  decide:
    rules:
      - when: "any(findings, .label startsWith 'secrets.')"
        action: block
        reason: "Secret pattern detected in prompt"
        severity: critical
      - when: "any(findings, .label == 'code.block')"
        action: transform
        transforms:
          - { label: code.block, method: redact, replacement: "[CODE_REDACTED]" }
      - when: "true"
        action: allow
  fail_mode: closed
`;

const HEALTHCARE_YAML = `apiVersion: praesidio/v1
kind: Policy
metadata:
  id: healthcare-phi
  name: "HIPAA Safe Harbor — PHI handling"
  owner: privacy@acme.example
  description: |
    Tokenise all 18 HIPAA identifiers; constrain routing to BAA-covered
    upstreams; force EU residency when jurisdiction is EU.
spec:
  match:
    routes: ["/v1/chat/completions"]
    tenants: ["acme", "initech"]
  detect:
    enable:
      - pii.person
      - pii.location
      - pii.phone
      - pii.email
      - healthcare.medical_license
  decide:
    rules:
      - when: "any(findings, .label == 'healthcare.medical_license') && ctx.model_request.provider == 'openai'"
        action: block
        reason: "PHI may not be sent to non-BAA upstream"
        severity: high
      - when: "any(findings, .label startsWith 'presidio.')"
        action: transform
        transforms:
          - { label: pii.person,   method: tokenise, scope: tenant, ttl: 24h }
          - { label: pii.location, method: tokenise, scope: tenant, ttl: 24h }
      - when: "true"
        action: allow
  route:
    when_jurisdiction: "EU"
    upstream: "azure-westeurope-gpt4o"
  fail_mode: closed
`;

export function mockPolicies(): Policy[] {
  return [
    {
      id: 'pii-strict',
      name: 'Strict PII anonymisation',
      owner: 'data-protection@acme.example',
      description:
        'Tokenise emails and people names; FPE phone numbers; redact IBANs and credit-card-shaped numbers; block cloud credentials.',
      version: 'v2026.05.3',
      enabled: true,
      fail_mode: 'closed',
      match: {
        routes: ['/v1/chat/completions', '/v1/completions', '/anthropic/v1/messages'],
        tenants: ['*'],
      },
      detectors: [
        'pii.email',
        'pii.phone',
        'financial.iban',
        'financial.credit_card',
        'pii.person',
        'pii.location',
        'credential.aws_access_key',
        'credential.gcp_service_account',
        'credential.azure_storage_key',
        'credential.generic_high_entropy',
      ],
      rules: [
        { when: "any(findings, .label in ['secrets.*'])", action: 'block', reason: 'Credential leakage attempt', severity: 'critical' },
        { when: "any(findings, .label in ['pii.email','pii.person','pii.phone','financial.iban','financial.credit_card'])", action: 'transform' },
        { when: 'true', action: 'allow' },
      ],
      raw_yaml: PII_STRICT_YAML,
      recent_decisions: [
        { decision: 'allow', count: 1112 },
        { decision: 'transform', count: 481 },
        { decision: 'block', count: 39 },
        { decision: 'error', count: 4 },
      ],
      updated_at: '2026-05-21T14:02:00Z',
    },
    {
      id: 'code-protection',
      name: 'Source code & secret protection',
      owner: 'appsec@acme.example',
      description:
        'Strip embedded source code from prompts and block any request shipping recognised cloud credentials to external upstreams.',
      version: 'v2026.04.7',
      enabled: true,
      fail_mode: 'closed',
      match: {
        routes: ['/v1/chat/completions', '/v1/completions'],
        tenants: ['*'],
        principals: { groups: ['engineering', 'data-eng'] },
      },
      detectors: ['code.block', 'credential.aws_access_key', 'credential.gcp_service_account', 'credential.azure_storage_key', 'credential.generic_high_entropy'],
      rules: [
        { when: "any(findings, .label startsWith 'secrets.')", action: 'block', reason: 'Secret pattern detected', severity: 'critical' },
        { when: "any(findings, .label == 'code.block')", action: 'transform' },
        { when: 'true', action: 'allow' },
      ],
      raw_yaml: CODE_PROTECTION_YAML,
      recent_decisions: [
        { decision: 'allow', count: 612 },
        { decision: 'transform', count: 173 },
        { decision: 'block', count: 12 },
      ],
      updated_at: '2026-05-09T08:44:00Z',
    },
    {
      id: 'healthcare-phi',
      name: 'HIPAA Safe Harbor — PHI handling',
      owner: 'privacy@acme.example',
      description:
        'Tokenise the 18 HIPAA identifiers, constrain routing to BAA-covered upstreams, and force EU residency on EU-jurisdiction traffic.',
      version: 'v2026.05.1',
      enabled: true,
      fail_mode: 'closed',
      match: {
        routes: ['/v1/chat/completions'],
        tenants: ['acme', 'initech'],
      },
      detectors: ['pii.person', 'pii.location', 'pii.phone', 'pii.email', 'healthcare.medical_license'],
      rules: [
        { when: "any(findings, .label == 'healthcare.medical_license') && ctx.model_request.provider == 'openai'", action: 'block', reason: 'PHI may not be sent to non-BAA upstream', severity: 'high' },
        { when: "any(findings, .label startsWith 'presidio.')", action: 'transform' },
        { when: 'true', action: 'allow' },
      ],
      raw_yaml: HEALTHCARE_YAML,
      recent_decisions: [
        { decision: 'allow', count: 304 },
        { decision: 'transform', count: 88 },
        { decision: 'block', count: 7 },
      ],
      updated_at: '2026-05-18T11:11:00Z',
    },
  ];
}

export function mockLineage(requestId: string): LineageGraphData {
  const n = (id: string, kind: any, label: string, meta: Record<string, unknown> = {}) => ({
    id,
    kind,
    label,
    meta,
  });
  return {
    request_id: requestId,
    nodes: [
      n('prompt-1', 'prompt', 'User prompt', { tokens: 184, principal: 'alice.kim@acme.example' }),
      n('retr-1', 'retrieval', 'RAG · kb.acme.contracts', { top_k: 5, score: 0.82 }),
      n('emb-1', 'embedding', 'chunk_4d2a', { doc: 'contract-2026-Q1.pdf' }),
      n('emb-2', 'embedding', 'chunk_b91f', { doc: 'renewal-template.md' }),
      n('emb-3', 'embedding', 'chunk_77c0', { doc: 'pricing-tier-3.xlsx' }),
      n('tool-1', 'tool', 'calendar.lookup', { latency_ms: 92 }),
      n('out-1', 'output', 'Model output', {
        upstream: 'anthropic/claude-3-5-sonnet',
        tokens: 612,
      }),
      n('mem-1', 'memory_write', 'session.notes', { ttl: '24h' }),
    ],
    edges: [
      { parent_id: 'prompt-1', child_id: 'retr-1', relation: 'derived_from' },
      { parent_id: 'emb-1', child_id: 'retr-1', relation: 'retrieved_from' },
      { parent_id: 'emb-2', child_id: 'retr-1', relation: 'retrieved_from' },
      { parent_id: 'emb-3', child_id: 'retr-1', relation: 'retrieved_from' },
      { parent_id: 'prompt-1', child_id: 'tool-1', relation: 'tool_output_of' },
      { parent_id: 'retr-1', child_id: 'out-1', relation: 'derived_from' },
      { parent_id: 'tool-1', child_id: 'out-1', relation: 'derived_from' },
      { parent_id: 'out-1', child_id: 'mem-1', relation: 'derived_from' },
    ],
  };
}

export function mockModels(): ModelCardEntry[] {
  return [
    {
      id: 'openai-gpt-4o',
      provider: 'OpenAI',
      model: 'gpt-4o',
      display_name: 'OpenAI · GPT-4o',
      jurisdiction: 'US',
      region: 'us-east',
      certifications: ['SOC 2 Type II', 'ISO 27001', 'CSA STAR'],
      privacy: { training_optout: true, data_retention_days: 30, customer_managed_keys: false },
      risk_tier: 'medium',
      route_mappings: ['/v1/chat/completions', '/v1/completions'],
      notes: 'Default upstream for marketing and support tenants. Not BAA-eligible.',
    },
    {
      id: 'azure-westeurope-gpt4o',
      provider: 'Azure OpenAI',
      model: 'gpt-4o',
      display_name: 'Azure · GPT-4o (westeurope)',
      jurisdiction: 'EU',
      region: 'westeurope',
      certifications: ['SOC 2 Type II', 'ISO 27001', 'C5', 'HDS', 'BAA'],
      privacy: { training_optout: true, data_retention_days: 0, customer_managed_keys: true },
      risk_tier: 'low',
      route_mappings: ['/v1/chat/completions'],
      notes: 'EU residency. Used for healthcare-phi and any DE/FR/NL principal.',
    },
    {
      id: 'anthropic-claude-3-5-sonnet',
      provider: 'Anthropic',
      model: 'claude-3-5-sonnet',
      display_name: 'Anthropic · Claude 3.5 Sonnet',
      jurisdiction: 'US',
      region: 'us-west',
      certifications: ['SOC 2 Type II', 'ISO 42001'],
      privacy: { training_optout: true, data_retention_days: 30, customer_managed_keys: false },
      risk_tier: 'medium',
      route_mappings: ['/anthropic/v1/messages'],
      notes: 'Used for long-context summarisation. Higher latency, higher quality.',
    },
    {
      id: 'ollama-llama-3-1-70b',
      provider: 'Self-hosted',
      model: 'llama-3.1-70b',
      display_name: 'On-prem · Llama 3.1 70B (Ollama)',
      jurisdiction: 'on-prem',
      region: 'dc-fra-1',
      certifications: ['Air-gapped'],
      privacy: { training_optout: true, data_retention_days: 0, customer_managed_keys: true },
      risk_tier: 'low',
      route_mappings: ['/v1/chat/completions', '/v1/embeddings'],
      notes: 'Fallback for fail-closed routes. No egress.',
    },
  ];
}

export function mockHealth(): GatewayHealth {
  return {
    ok: true,
    version: 'gateway 2026.05.3 (commit 9c4fb71e)',
    bundle_digest: 'sha256:9c4f4b2e1a73…b71e',
    policy_count: 3,
    env: 'staging',
    fail_mode: 'closed',
    gateway_url: 'http://localhost:8080',
  };
}
