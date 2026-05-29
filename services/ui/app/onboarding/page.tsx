'use client';

/**
 * Onboarding — a sequential, six-step wizard for first-run operators.
 *
 * Design contract (see docs/deployment-coverage.md §§ 5–8):
 *   1. Pick a deployment shape  (local · self-hosted · cloud)
 *   2. Bring up the gateway      (copy/paste one-liner, live healthz)
 *   3. Wire your first client    (env vars + curl + "Run from browser")
 *   4. Watch it work             (live event tape, three demo prompts)
 *   5. Expand coverage           (PEPs 2–5 install cards)
 *   6. You're live               (next steps + dismiss flag)
 *
 * Progress is persisted in localStorage so refreshes do not lose place.
 * The page renders on any screen width and degrades gracefully if the
 * gateway is unreachable (uses mock data via lib/api).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {
  ArrowRight,
  Check,
  Cloud,
  Copy,
  ExternalLink,
  Laptop,
  Play,
  RotateCw,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { swrFetcher } from '@/lib/api';
import type { AuditEvent, GatewayHealth } from '@/lib/types';

// ─── Types ────────────────────────────────────────────────────────────────

type Shape = 'local' | 'self-hosted' | 'cloud';

type StepKey = 'shape' | 'bringup' | 'wire' | 'watch' | 'expand' | 'live';

const STEPS: { key: StepKey; num: string; label: string; sub: string }[] = [
  { key: 'shape', num: '§ 1', label: 'Pick a path', sub: 'How will you run Praesidio?' },
  { key: 'bringup', num: '§ 2', label: 'Bring it up', sub: 'One command, ~90 seconds' },
  { key: 'wire', num: '§ 3', label: 'Wire a client', sub: 'Point an SDK at the gateway' },
  { key: 'watch', num: '§ 4', label: 'Watch it work', sub: 'See decisions land in real time' },
  { key: 'expand', num: '§ 5', label: 'Expand coverage', sub: 'Beyond the API gateway' },
  { key: 'live', num: '§ 6', label: "You're live", sub: 'Next steps' },
];

const STORAGE_KEY = 'praesidio.onboarding.v1';

type Progress = {
  shape: Shape | null;
  completed: Partial<Record<StepKey, boolean>>;
  current: StepKey;
  demoMarker: string | null; // a token we look for in audit rows
  finishedAt: string | null;
};

const DEFAULT_PROGRESS: Progress = {
  shape: null,
  completed: {},
  current: 'shape',
  demoMarker: null,
  finishedAt: null,
};

// ─── Persistence ──────────────────────────────────────────────────────────

function loadProgress(): Progress {
  if (typeof window === 'undefined') return DEFAULT_PROGRESS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PROGRESS;
    return { ...DEFAULT_PROGRESS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PROGRESS;
  }
}

function saveProgress(p: Progress) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [progress, setProgress] = useState<Progress>(DEFAULT_PROGRESS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setProgress(loadProgress());
    setHydrated(true);
  }, []);

  const update = useCallback((patch: Partial<Progress>) => {
    setProgress((prev) => {
      const next = { ...prev, ...patch };
      saveProgress(next);
      return next;
    });
  }, []);

  const complete = useCallback(
    (key: StepKey, advanceTo?: StepKey) => {
      setProgress((prev) => {
        const next: Progress = {
          ...prev,
          completed: { ...prev.completed, [key]: true },
          current: advanceTo ?? prev.current,
        };
        saveProgress(next);
        return next;
      });
    },
    [],
  );

  const reset = useCallback(() => {
    saveProgress(DEFAULT_PROGRESS);
    setProgress(DEFAULT_PROGRESS);
  }, []);

  // Avoid hydration mismatch on the initial paint.
  if (!hydrated) return <Shell progress={DEFAULT_PROGRESS} onJump={() => {}} onReset={() => {}} />;

  return (
    <Shell
      progress={progress}
      onJump={(k) => update({ current: k })}
      onReset={reset}
    >
      {progress.current === 'shape' && (
        <StepShape
          value={progress.shape}
          onPick={(s) => update({ shape: s })}
          onContinue={() => complete('shape', 'bringup')}
        />
      )}
      {progress.current === 'bringup' && (
        <StepBringup
          shape={progress.shape ?? 'local'}
          onDone={() => complete('bringup', 'wire')}
        />
      )}
      {progress.current === 'wire' && (
        <StepWire
          shape={progress.shape ?? 'local'}
          marker={progress.demoMarker}
          setMarker={(m) => update({ demoMarker: m })}
          onDone={() => complete('wire', 'watch')}
        />
      )}
      {progress.current === 'watch' && (
        <StepWatch
          marker={progress.demoMarker}
          setMarker={(m) => update({ demoMarker: m })}
          onDone={() => complete('watch', 'expand')}
        />
      )}
      {progress.current === 'expand' && (
        <StepExpand onDone={() => complete('expand', 'live')} />
      )}
      {progress.current === 'live' && (
        <StepLive
          onFinish={() => {
            const now = new Date().toISOString();
            update({ finishedAt: now });
            // Tell the rest of the app we're past onboarding.
            window.localStorage.setItem('praesidio.onboarded', '1');
          }}
          finishedAt={progress.finishedAt}
        />
      )}
    </Shell>
  );
}

// ─── Shell (masthead + rail + step body) ─────────────────────────────────

function Shell({
  progress,
  onJump,
  onReset,
  children,
}: {
  progress: Progress;
  onJump: (k: StepKey) => void;
  onReset: () => void;
  children?: React.ReactNode;
}) {
  const currentIdx = STEPS.findIndex((s) => s.key === progress.current);
  const completedCount = Object.values(progress.completed).filter(Boolean).length;
  const pct = Math.round((completedCount / STEPS.length) * 100);

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-8">
      {/* Masthead */}
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              o.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Onboarding
            </h1>
          </div>
          <div className="hidden md:flex items-center gap-3 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <span>budget · 5 min to first decision</span>
            <span className="leader h-[1px] w-24" aria-hidden />
            <span className="tnum text-text-primary">{pct}%</span>
          </div>
        </div>
        <div className="mt-3 flex items-baseline justify-between gap-4">
          <p className="marginalia max-w-2xl">
            Six small steps from a fresh clone to a live audit row. Every
            step is independently valuable; you can stop after any one of
            them and still have something useful running.
          </p>
          <button
            onClick={onReset}
            className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
          >
            <RotateCw className="h-3 w-3" /> reset
          </button>
        </div>
      </header>

      {/* Step rail */}
      <nav
        aria-label="Onboarding progress"
        className="grid grid-cols-2 md:grid-cols-6 gap-0 border border-border bg-canvas
                   [&>*]:border-r [&>*]:border-border [&>*:last-child]:border-r-0
                   md:[&>*:nth-child(2n)]:border-r md:[&>*:nth-child(6n)]:border-r-0
                   [&>*]:border-b [&>*]:border-border [&>*:nth-last-child(-n+2)]:border-b-0
                   md:[&>*]:border-b-0"
      >
        {STEPS.map((s, i) => {
          const done = !!progress.completed[s.key];
          const active = progress.current === s.key;
          const reachable = done || i <= currentIdx;
          return (
            <button
              key={s.key}
              onClick={() => reachable && onJump(s.key)}
              disabled={!reachable}
              className={cn(
                'flex flex-col items-start gap-1 p-4 text-left transition-colors',
                active && 'bg-surface-sunken',
                !active && reachable && 'hover:bg-surface-sunken',
                !reachable && 'opacity-40 cursor-not-allowed',
              )}
            >
              <div className="flex items-center gap-2 w-full">
                <span
                  className={cn(
                    'inline-flex items-center justify-center h-4 w-4 border',
                    done
                      ? 'bg-success border-success text-canvas'
                      : active
                        ? 'bg-text-primary border-text-primary text-canvas'
                        : 'border-border text-text-tertiary',
                  )}
                >
                  {done ? (
                    <Check className="h-2.5 w-2.5" strokeWidth={3} />
                  ) : (
                    <span className="font-mono text-[8.5px] tnum">{i + 1}</span>
                  )}
                </span>
                <span className="font-serif italic text-[12px] text-text-tertiary">
                  {s.num}
                </span>
              </div>
              <div className="font-mono text-[11.5px] text-text-primary">
                {s.label}
              </div>
              <div className="font-mono text-[10px] tracking-[0.04em] text-text-tertiary leading-tight">
                {s.sub}
              </div>
            </button>
          );
        })}
      </nav>

      {/* Step body */}
      <section>{children}</section>
    </div>
  );
}

// ─── Step 1 — Pick a path ────────────────────────────────────────────────

function StepShape({
  value,
  onPick,
  onContinue,
}: {
  value: Shape | null;
  onPick: (s: Shape) => void;
  onContinue: () => void;
}) {
  const cards: {
    id: Shape;
    icon: typeof Laptop;
    label: string;
    eta: string;
    body: string;
    target: string;
  }[] = [
    {
      id: 'local',
      icon: Laptop,
      label: 'Local demo',
      eta: '< 5 min',
      body: 'Docker Desktop on your laptop. SQLite audit log, demo API key, no TLS. The fastest way to see Praesidio block a real prompt.',
      target: 'Evaluation · demos · policy authoring',
    },
    {
      id: 'self-hosted',
      icon: Server,
      label: 'Self-hosted',
      eta: '< 30 min',
      body: 'Full compose stack with Postgres, Redis, TLS via Caddy, OIDC. Persistent, small-team production or air-gapped install.',
      target: 'Small-team prod · air-gapped · regulated',
    },
    {
      id: 'cloud',
      icon: Cloud,
      label: 'Kubernetes',
      eta: '< 4 hr',
      body: 'Helm chart with HA gateway, ExternalSecrets vault, NetworkPolicies, HPA, Grafana. Terraform refs for AWS · Azure · GCP.',
      target: 'Real production · multi-tenant',
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHead num="i." title="What are we building?" hint="Pick the smallest shape that matches your goal — you can graduate later." />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 border border-border bg-canvas
                      [&>*]:border-r [&>*]:border-border [&>*:last-child]:border-r-0
                      [&>*]:border-b [&>*]:border-border [&>*:last-child]:border-b-0 lg:[&>*]:border-b-0">
        {cards.map((c) => {
          const Icon = c.icon;
          const selected = value === c.id;
          return (
            <button
              key={c.id}
              onClick={() => onPick(c.id)}
              className={cn(
                'flex flex-col gap-3 p-5 text-left transition-colors min-h-[200px]',
                selected ? 'bg-surface-sunken' : 'hover:bg-surface',
              )}
            >
              <div className="flex items-start justify-between">
                <Icon
                  className={cn(
                    'h-5 w-5',
                    selected ? 'text-accent' : 'text-text-tertiary',
                  )}
                  strokeWidth={1.5}
                />
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                  {c.eta}
                </span>
              </div>
              <div className="font-serif text-[22px] leading-tight text-text-primary">
                {c.label}
              </div>
              <p className="text-[13px] text-text-secondary leading-relaxed">
                {c.body}
              </p>
              <div className="mt-auto font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                {c.target}
              </div>
              {selected && (
                <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.14em] uppercase text-accent">
                  <Check className="h-3 w-3" strokeWidth={2.5} /> selected
                </div>
              )}
            </button>
          );
        })}
      </div>

      <StepFooter
        rightLabel="Continue"
        onRight={onContinue}
        rightDisabled={!value}
        rightHint={value ? `Shape: ${value}` : 'Pick one to continue'}
      />
    </div>
  );
}

// ─── Step 2 — Bring it up ────────────────────────────────────────────────

function StepBringup({ shape, onDone }: { shape: Shape; onDone: () => void }) {
  const { data: health, mutate } = useSWR<GatewayHealth>('/healthz', swrFetcher, {
    refreshInterval: 2_000,
    shouldRetryOnError: true,
  });

  const healthy = !!health?.ok;

  const cmds = useMemo(() => {
    switch (shape) {
      case 'local':
        return [
          {
            label: 'Clone & bring up',
            code: [
              'git clone --depth 1 https://github.com/cwellbournewood/praesidio.git',
              'cd praesidio',
              'cp .env.example .env',
              'docker compose --profile quickstart up -d',
            ].join('\n'),
          },
        ];
      case 'self-hosted':
        return [
          {
            label: 'Clone & bring up (full)',
            code: [
              'git clone --depth 1 https://github.com/cwellbournewood/praesidio.git',
              'cd praesidio',
              'cp .env.example .env',
              '# edit .env: set PRAESIDIO_API_KEYS, OIDC_*, UPSTREAM keys',
              'docker compose up -d --build',
            ].join('\n'),
          },
        ];
      case 'cloud':
        return [
          {
            label: 'Provision cluster (Terraform)',
            code: [
              'cd deploy/terraform/aws  # or azure / gcp',
              'terraform init',
              'terraform apply',
            ].join('\n'),
          },
          {
            label: 'Install Praesidio (Helm)',
            code: [
              'helm repo add praesidio https://charts.praesidio.io',
              'helm upgrade --install praesidio praesidio/praesidio \\',
              '  -n praesidio --create-namespace \\',
              '  -f deploy/helm/values.production.yaml',
            ].join('\n'),
          },
        ];
    }
  }, [shape]);

  return (
    <div className="space-y-6">
      <SectionHead
        num="ii."
        title="Bring up the control plane"
        hint={
          shape === 'local'
            ? 'Pre-built images from the public registry. No local build, no Postgres migration — just up.'
            : shape === 'self-hosted'
              ? 'Full compose stack with persistent volumes. Configure .env first.'
              : 'Terraform creates the cluster + managed Postgres/Redis; Helm installs Praesidio with HA + NetworkPolicies.'
        }
      />

      <div className="space-y-4">
        {cmds.map((c) => (
          <CodeBlock key={c.label} label={c.label} code={c.code} />
        ))}
      </div>

      {/* Health pill */}
      <div className="border border-border bg-canvas">
        <div className="flex items-center justify-between border-b border-border px-4 h-9">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic text-[13px] text-text-tertiary">iii.</span>
            <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              Gateway health
            </span>
          </div>
          <button
            onClick={() => mutate()}
            className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
          >
            <RotateCw className="h-3 w-3" /> retry
          </button>
        </div>
        <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <HealthRow label="Status">
            <span className="inline-flex items-center gap-2">
              <span
                className={cn(
                  'sig',
                  healthy ? 'sig-allow pulse' : 'sig-idle',
                )}
                aria-hidden
              />
              <span className="font-mono text-[11.5px] text-text-primary">
                {healthy ? 'healthy' : health ? 'reachable' : 'waiting…'}
              </span>
            </span>
          </HealthRow>
          <HealthRow label="Gateway URL">
            <span className="font-mono text-[11.5px] text-text-primary break-all">
              {health?.gateway_url ?? '—'}
            </span>
          </HealthRow>
          <HealthRow label="Build">
            <span className="font-mono text-[11.5px] text-text-primary">
              {health?.version ?? '—'}
            </span>
          </HealthRow>
        </div>
      </div>

      <StepFooter
        leftLabel="Back"
        rightLabel={healthy ? 'Continue · gateway is up' : 'Continue anyway'}
        onRight={onDone}
        rightHint={
          healthy
            ? 'Decision: forward · audit chain initialised'
            : 'You can wire a client now and come back when it’s healthy'
        }
      />
    </div>
  );
}

// ─── Step 3 — Wire your first client ─────────────────────────────────────

function StepWire({
  shape,
  marker,
  setMarker,
  onDone,
}: {
  shape: Shape;
  marker: string | null;
  setMarker: (m: string) => void;
  onDone: () => void;
}) {
  const base =
    shape === 'cloud'
      ? 'https://praesidio.example.com/v1'
      : 'http://localhost:8080/v1';

  const ensureMarker = useCallback(() => {
    if (marker) return marker;
    const m = `onb-${Math.random().toString(36).slice(2, 8)}`;
    setMarker(m);
    return m;
  }, [marker, setMarker]);

  const [running, setRunning] = useState(false);
  const [lastStatus, setLastStatus] = useState<number | null>(null);
  const [lastReason, setLastReason] = useState<string | null>(null);

  const runBrowserDemo = async () => {
    setRunning(true);
    setLastStatus(null);
    setLastReason(null);
    const m = ensureMarker();
    try {
      const res = await fetch(`${base}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer praesidio-demo-key',
          'X-Praesidio-Session': m,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [
            {
              role: 'user',
              content: `Email John Smith at john.smith@acme.com about invoice 4471 [${m}]`,
            },
          ],
        }),
      });
      setLastStatus(res.status);
      setLastReason(res.headers.get('X-Praesidio-Reason'));
    } catch (e) {
      setLastStatus(0);
      setLastReason(e instanceof Error ? e.message : 'network error');
    } finally {
      setRunning(false);
    }
  };

  const envBlock = [
    `export OPENAI_BASE_URL=${base}`,
    'export OPENAI_API_KEY=praesidio-demo-key',
  ].join('\n');

  const curlBlock = [
    `curl ${base}/chat/completions \\`,
    '  -H "Authorization: Bearer praesidio-demo-key" \\',
    '  -H "Content-Type: application/json" \\',
    "  -d '{",
    '    "model": "gpt-4o-mini",',
    '    "messages": [{"role":"user","content":"Email john.smith@acme.com about invoice 4471"}]',
    "  }'",
  ].join('\n');

  return (
    <div className="space-y-6">
      <SectionHead
        num="i."
        title="Point a client at the gateway"
        hint="Any OpenAI-compatible SDK works. The gateway speaks the OpenAI API on the front side and forwards to whichever provider the policy selects on the back."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CodeBlock label="Environment" code={envBlock} />
        <CodeBlock label="One-shot curl" code={curlBlock} />
      </div>

      <div className="border border-border bg-canvas">
        <div className="flex items-center justify-between border-b border-border px-4 h-9">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic text-[13px] text-text-tertiary">ii.</span>
            <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              No terminal? Run it from here
            </span>
          </div>
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
            POSTs the same request via the browser
          </span>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-[13px] text-text-secondary leading-relaxed">
            Sends the canonical PII prompt directly from this page. Expect{' '}
            <span className="font-mono text-text-primary">200</span> with a{' '}
            <span className="font-mono text-text-primary">transform</span>{' '}
            decision (email tokenised) — or{' '}
            <span className="font-mono text-text-primary">403</span> with{' '}
            <span className="font-mono text-text-primary">X-Praesidio-Reason</span>{' '}
            if policy says block.
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={runBrowserDemo}
              disabled={running}
              className="inline-flex items-center gap-2 h-8 px-3 font-mono text-[11.5px] bg-text-primary text-canvas border border-text-primary hover:bg-text-secondary disabled:opacity-50"
            >
              <Play className="h-3 w-3" strokeWidth={2} />
              {running ? 'sending…' : 'Send demo prompt'}
            </button>
            {lastStatus !== null && (
              <div className="font-mono text-[11.5px] text-text-secondary flex items-center gap-3">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className={cn(
                      'sig',
                      lastStatus === 200
                        ? 'sig-warn'
                        : lastStatus === 403
                          ? 'sig-block'
                          : 'sig-idle',
                    )}
                    aria-hidden
                  />
                  HTTP <span className="text-text-primary">{lastStatus}</span>
                </span>
                {lastReason && (
                  <span className="text-text-tertiary">
                    reason: <span className="text-text-primary">{lastReason}</span>
                  </span>
                )}
              </div>
            )}
          </div>
          {marker && (
            <p className="font-mono text-[10px] tracking-[0.04em] text-text-tertiary">
              session marker · <span className="text-text-primary">{marker}</span>{' '}
              · the next step filters the event tape to this token
            </p>
          )}
        </div>
      </div>

      <StepFooter
        leftLabel="Back"
        rightLabel="See the result"
        onRight={onDone}
        rightHint="Watch the audit row land in the live tape"
      />
    </div>
  );
}

// ─── Step 4 — Watch it work ──────────────────────────────────────────────

function StepWatch({
  marker,
  setMarker,
  onDone,
}: {
  marker: string | null;
  setMarker: (m: string) => void;
  onDone: () => void;
}) {
  const { data: events } = useSWR<AuditEvent[]>(
    '/admin/events?limit=50',
    swrFetcher,
    { refreshInterval: 2_000 },
  );

  const ensureMarker = useCallback(() => {
    if (marker) return marker;
    const m = `onb-${Math.random().toString(36).slice(2, 8)}`;
    setMarker(m);
    return m;
  }, [marker, setMarker]);

  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { status: number; reason: string | null }>>({});

  const prompts: { id: string; label: string; tone: string; body: string }[] = [
    {
      id: 'pii',
      label: 'PII · person + email',
      tone: 'warn',
      body: 'Email John Smith at john.smith@acme.com about invoice 4471',
    },
    {
      id: 'secret',
      label: 'Secret · AWS access key',
      tone: 'block',
      body: 'Use AWS access key AKIAIOSFODNN7EXAMPLE and secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY to upload',
    },
    {
      id: 'iban',
      label: 'Financial · IBAN',
      tone: 'warn',
      body: 'Send the invoice to my account DE89 3704 0044 0532 0130 00 by Friday',
    },
  ];

  const send = async (id: string, body: string) => {
    setRunning(id);
    const m = ensureMarker();
    try {
      const res = await fetch('/api/gateway/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer praesidio-demo-key',
          'X-Praesidio-Session': m,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: `${body} [${m}/${id}]` }],
        }),
      });
      setResults((prev) => ({
        ...prev,
        [id]: { status: res.status, reason: res.headers.get('X-Praesidio-Reason') },
      }));
    } catch (e) {
      setResults((prev) => ({
        ...prev,
        [id]: { status: 0, reason: e instanceof Error ? e.message : 'network' },
      }));
    } finally {
      setRunning(null);
    }
  };

  const sendAll = async () => {
    for (const p of prompts) {
      await send(p.id, p.body);
    }
  };

  // Filter events to anything tagged with our session marker, falling back to
  // the latest events if no marker has been used yet.
  const filtered = useMemo(() => {
    if (!events) return [];
    if (!marker) return events.slice(0, 8);
    return events
      .filter((e) => JSON.stringify(e).includes(marker))
      .slice(0, 8);
  }, [events, marker]);

  return (
    <div className="space-y-6">
      <SectionHead
        num="i."
        title="Three prompts, three decisions"
        hint="Run the canonical demo. Each prompt is shaped to exercise a different detector family — you should see one transform, one block, one transform."
      />

      <div className="border border-border bg-canvas">
        <div className="flex items-center justify-between border-b border-border px-4 h-9">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic text-[13px] text-text-tertiary">i.</span>
            <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              Scripted demo
            </span>
          </div>
          <button
            onClick={sendAll}
            disabled={!!running}
            className="inline-flex items-center gap-2 h-7 px-2.5 font-mono text-[11px] bg-text-primary text-canvas border border-text-primary hover:bg-text-secondary disabled:opacity-50"
          >
            <Play className="h-3 w-3" strokeWidth={2} />
            run all three
          </button>
        </div>
        <ul>
          {prompts.map((p) => {
            const r = results[p.id];
            return (
              <li
                key={p.id}
                className="grid grid-cols-[28px_auto_1fr_auto_auto] items-center gap-3 px-4 h-11 border-b border-border last:border-b-0"
              >
                <span
                  className={cn(
                    'sig',
                    p.tone === 'warn' && 'sig-warn',
                    p.tone === 'block' && 'sig-block',
                  )}
                  aria-hidden
                />
                <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
                  {p.label}
                </span>
                <span className="font-mono text-[11.5px] text-text-primary truncate">
                  {p.body}
                </span>
                <span className="font-mono text-[11px] text-text-tertiary tnum">
                  {r ? `HTTP ${r.status}` : '—'}
                </span>
                <button
                  onClick={() => send(p.id, p.body)}
                  disabled={!!running}
                  className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent disabled:opacity-50"
                >
                  {running === p.id ? 'sending…' : 'send'}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Live event tape filtered to our marker */}
      <div className="border border-border bg-canvas">
        <div className="flex items-center justify-between border-b border-border px-4 h-9">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic text-[13px] text-text-tertiary">ii.</span>
            <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              Live tape · this session
            </span>
            <span className="sig sig-block pulse ml-1" aria-hidden />
          </div>
          <Link
            href="/events"
            className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
          >
            all events <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
        {filtered.length === 0 ? (
          <div className="p-6 text-center">
            <p className="font-serif italic text-[13px] text-text-tertiary">
              Nothing here yet. Send a prompt above and watch a row land within ~1 second.
            </p>
          </div>
        ) : (
          <ul className="max-h-[280px] overflow-y-auto">
            {filtered.map((e) => (
              <li
                key={e.id}
                className="grid grid-cols-[16px_120px_1fr_80px] items-center gap-3 px-4 h-9 border-b border-border last:border-b-0 hover:bg-surface-sunken"
              >
                <span
                  className={cn(
                    'sig',
                    e.decision === 'allow' && 'sig-allow',
                    e.decision === 'transform' && 'sig-warn',
                    e.decision === 'block' && 'sig-block',
                    !['allow', 'transform', 'block'].includes(e.decision) && 'sig-idle',
                  )}
                  aria-hidden
                />
                <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
                  {e.decision}
                </span>
                <span className="font-mono text-[11px] text-text-secondary truncate">
                  {e.principal?.email ?? e.principal?.user_id ?? '—'} · {e.upstream ?? '—'}
                </span>
                <Link
                  href={`/events?id=${e.id}`}
                  className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center justify-end gap-1"
                >
                  lineage <ArrowRight className="h-3 w-3" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <StepFooter
        leftLabel="Back"
        rightLabel="Expand coverage"
        onRight={onDone}
        rightHint={
          filtered.length > 0
            ? `${filtered.length} decision${filtered.length === 1 ? '' : 's'} recorded · you have first value`
            : 'You can move on even if no rows landed yet'
        }
      />
    </div>
  );
}

// ─── Step 5 — Expand coverage ────────────────────────────────────────────

function StepExpand({ onDone }: { onDone: () => void }) {
  const peps: {
    id: string;
    num: string;
    label: string;
    icon: typeof Server;
    status: 'shipping' | 'alpha' | 'roadmap';
    body: string;
    snippet: string;
    href: string;
  }[] = [
    {
      id: 'forward',
      num: '§ 2',
      label: 'Forward proxy · SWG',
      icon: Server,
      status: 'alpha',
      body: 'TLS-MITM browser → AI web UIs (chat.openai.com, claude.ai, gemini.google.com). MDM-pushed root CA + SWG rule.',
      snippet: 'docker compose --profile fwdproxy up -d',
      href: '/settings?tab=connectors#forward-proxy',
    },
    {
      id: 'ext',
      num: '§ 3',
      label: 'Browser extension',
      icon: ShieldCheck,
      status: 'roadmap',
      body: 'Chrome / Edge / Firefox extension pushed via enterprise policy. Catches unmanaged / BYOD where MITM is not viable.',
      snippet: 'praesidio-ext.crx · pushed via Chrome Enterprise',
      href: '/settings?tab=connectors#browser-ext',
    },
    {
      id: 'ide',
      num: '§ 4',
      label: 'IDE plugin',
      icon: Terminal,
      status: 'roadmap',
      body: 'VSCode + JetBrains. Wraps Copilot, Cursor, Continue, Cody. The highest-value PEP for engineering orgs.',
      snippet: 'ext install praesidio.praesidio-vscode',
      href: '/settings?tab=connectors#ide',
    },
    {
      id: 'mcp',
      num: '§ 5',
      label: 'MCP · agent middleware',
      icon: Sparkles,
      status: 'alpha',
      body: 'Wraps MCP tool calls and the Claude Agent SDK / OpenAI Agents / LangGraph. The cleanest integration for the agentic future.',
      snippet: 'pip install praesidio-agent-sdk',
      href: '/settings?tab=connectors#mcp',
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHead
        num="i."
        title="One control plane, many enforcement points"
        hint="The gateway covers everything code-mediated. These four PEPs close the gaps for browsers, IDEs, and agents — install whichever your population needs."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border border-border bg-canvas
                      [&>*]:border-r [&>*]:border-border md:[&>*:nth-child(2n)]:border-r-0
                      [&>*]:border-b [&>*]:border-border [&>*:nth-last-child(-n+2)]:border-b-0">
        {peps.map((p) => {
          const Icon = p.icon;
          return (
            <div key={p.id} className="flex flex-col gap-3 p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-baseline gap-2">
                  <span className="font-serif italic text-[12px] text-text-tertiary">{p.num}</span>
                  <Icon className="h-4 w-4 text-text-secondary" strokeWidth={1.5} />
                  <span className="font-mono text-[11px] tracking-[0.14em] uppercase text-text-primary">
                    {p.label}
                  </span>
                </div>
                <StatusPill status={p.status} />
              </div>
              <p className="text-[13px] text-text-secondary leading-relaxed">{p.body}</p>
              <CodeBlock label="install" code={p.snippet} compact />
              <Link
                href={p.href}
                className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1 mt-auto"
              >
                connector docs <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          );
        })}
      </div>

      <div className="border border-border bg-surface-sunken p-4">
        <p className="font-serif italic text-[13px] text-text-secondary leading-relaxed">
          You can skip this step and come back any time — every PEP has its
          own page under <Link href="/settings?tab=connectors" className="text-accent hover:underline">Settings · Connectors</Link>.
          The gateway alone already covers 70%+ of leakage surface for most orgs.
        </p>
      </div>

      <StepFooter
        leftLabel="Back"
        rightLabel="Finish onboarding"
        onRight={onDone}
        rightHint="One last screen"
      />
    </div>
  );
}

// ─── Step 6 — You're live ────────────────────────────────────────────────

function StepLive({
  onFinish,
  finishedAt,
}: {
  onFinish: () => void;
  finishedAt: string | null;
}) {
  useEffect(() => {
    if (!finishedAt) onFinish();
  }, [finishedAt, onFinish]);

  const links: { href: string; label: string; sub: string }[] = [
    {
      href: '/policies',
      label: 'Author policy',
      sub: 'YAML + CEL, git-versioned, cosign-signed bundles',
    },
    {
      href: '/settings?tab=identity',
      label: 'Configure identity',
      sub: 'OIDC, API keys, group → policy bindings',
    },
    {
      href: '/events',
      label: 'Browse decisions',
      sub: 'Every prompt, every verdict, every lineage edge',
    },
    {
      href: '/lineage/demo-req-1',
      label: 'Inspect lineage',
      sub: 'Trace a request across detectors, transforms, and the upstream call',
    },
    {
      href: '/settings?tab=docs',
      label: 'Read the architecture',
      sub: '/docs · ADRs · threat model · compliance maps',
    },
    {
      href: '/settings?tab=connectors',
      label: 'Install another PEP',
      sub: 'Forward proxy, browser extension, IDE plugin, MCP',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="border border-border bg-canvas p-8 text-center">
        <div className="inline-flex items-center justify-center h-10 w-10 bg-success text-canvas mx-auto">
          <Check className="h-5 w-5" strokeWidth={2.5} />
        </div>
        <h2 className="mt-4 font-serif text-[36px] leading-tight text-text-primary">
          You&apos;re live.
        </h2>
        <p className="mt-2 marginalia max-w-xl mx-auto">
          A request was inspected, a policy was applied, a decision was signed
          and chained. That is the whole product, in miniature. Everything from
          here is volume, fidelity, and coverage.
        </p>
        {finishedAt && (
          <p className="mt-3 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
            onboarded · {new Date(finishedAt).toISOString().slice(0, 19).replace('T', ' ')} UTC
          </p>
        )}
      </div>

      <SectionHead num="i." title="Where next" hint="Six places to spend your next ten minutes." />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 border border-border bg-canvas
                      [&>*]:border-r [&>*]:border-border md:[&>*:nth-child(2n)]:border-r-0 lg:[&>*:nth-child(2n)]:border-r lg:[&>*:nth-child(3n)]:border-r-0
                      [&>*]:border-b [&>*]:border-border [&>*:nth-last-child(-n+1)]:border-b-0">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="flex flex-col gap-1 p-4 hover:bg-surface-sunken transition-colors"
          >
            <div className="font-mono text-[11.5px] text-text-primary inline-flex items-center gap-1.5">
              {l.label} <ArrowRight className="h-3 w-3" />
            </div>
            <div className="font-serif italic text-[12.5px] text-text-tertiary leading-relaxed">
              {l.sub}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Atoms ───────────────────────────────────────────────────────────────

function SectionHead({
  num,
  title,
  hint,
}: {
  num: string;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border pb-3">
      <div className="flex items-baseline gap-3">
        <span className="font-serif italic text-[16px] text-text-tertiary">{num}</span>
        <h2 className="font-serif text-[24px] tracking-display text-text-primary">{title}</h2>
      </div>
      {hint && <p className="marginalia max-w-lg text-right hidden md:block">{hint}</p>}
    </div>
  );
}

function HealthRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
        {label}
      </span>
      {children}
    </div>
  );
}

function CodeBlock({
  label,
  code,
  compact = false,
}: {
  label?: string;
  code: string;
  compact?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — silently no-op */
    }
  };

  return (
    <div className="border border-border bg-canvas">
      {label && (
        <div className="flex items-center justify-between border-b border-border px-3 h-8">
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
            {label}
          </span>
          <button
            onClick={onCopy}
            className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" /> copied
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" /> copy
              </>
            )}
          </button>
        </div>
      )}
      <pre
        className={cn(
          'font-mono text-[12px] leading-relaxed text-text-primary whitespace-pre-wrap break-all',
          compact ? 'p-2.5' : 'p-4',
        )}
      >
        {code}
      </pre>
    </div>
  );
}

function StatusPill({ status }: { status: 'shipping' | 'alpha' | 'roadmap' }) {
  const tone =
    status === 'shipping'
      ? 'border-success text-success'
      : status === 'alpha'
        ? 'border-warn text-warn'
        : 'border-border text-text-tertiary';
  return (
    <span
      className={cn(
        'font-mono text-[9.5px] tracking-[0.14em] uppercase border px-1.5 h-4 inline-flex items-center bg-canvas',
        tone,
      )}
    >
      {status}
    </span>
  );
}

function StepFooter({
  leftLabel,
  rightLabel,
  onRight,
  rightDisabled = false,
  rightHint,
}: {
  leftLabel?: string;
  rightLabel: string;
  onRight: () => void;
  rightDisabled?: boolean;
  rightHint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-border pt-5">
      <div className="font-serif italic text-[13px] text-text-tertiary">
        {rightHint ?? leftLabel ?? ''}
      </div>
      <button
        onClick={onRight}
        disabled={rightDisabled}
        className="inline-flex items-center gap-2 h-9 px-4 font-mono text-[12px] bg-text-primary text-canvas border border-text-primary hover:bg-text-secondary disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {rightLabel}
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
    </div>
  );
}
