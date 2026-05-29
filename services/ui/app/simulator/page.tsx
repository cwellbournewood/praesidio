'use client';

/**
 * Policy simulator.
 *
 *   POST {gateway}/admin/simulate  with { prompt, policy_id? }
 *
 * Render the decision, the matched rule, the findings list (with offsets
 * highlighted over the input prompt), and a preview of the transforms that
 * would be applied. The last five prompts are persisted in localStorage so
 * the operator can iterate quickly.
 *
 * Keyboard:
 *   ⌘/Ctrl + Enter  → Run
 *   Tab             → cycles textarea → run → recent → policy select → output
 *   Arrow keys      → move between recent-prompt chips
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { Wand2, Play, Loader2, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/tag';
import { Skeleton } from '@/components/ui/skeleton';
import { DecisionBadge } from '@/components/praesidio/DecisionBadge';
import { FindingChip } from '@/components/praesidio/FindingChip';
import { api, swrFetcher } from '@/lib/api';
import { lookup } from '@/lib/labels';
import type { Policy, SimulateResponse, Finding } from '@/lib/types';
import { cn, decisionClasses, decisionLabel, formatMs } from '@/lib/utils';

const HISTORY_KEY = 'praesidio.simulator.recent';
const MAX_HISTORY = 5;

const SAMPLE_PROMPTS = [
  'Please email the renewal contract to alice.kim@acme.example by Friday; her direct line is +1 415 555 0142.',
  'Customer paid with card 4242 4242 4242 4242 — refund €120 to that account.',
  'AWS access key AKIAIOSFODNN7EXAMPLE is failing — please rotate it.',
  'Summarise this medical record for patient John Mathers, DOB 1984-02-14.',
];

function loadHistory(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string').slice(0, MAX_HISTORY) : [];
  } catch {
    return [];
  }
}

function saveHistory(items: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)));
  } catch {
    /* silent */
  }
}

/**
 * Render the prompt with each finding's span highlighted in-place. Uses a
 * deterministic colour family per detector (PII / secret / financial / etc.).
 */
function HighlightedPrompt({ prompt, findings }: { prompt: string; findings: Finding[] }) {
  // Sort by start; merge overlapping spans defensively.
  const spans = useMemo(() => {
    const sorted = [...findings].sort((a, b) => a.span[0] - b.span[0]);
    const merged: Array<{ start: number; end: number; finding: Finding }> = [];
    for (const f of sorted) {
      const last = merged[merged.length - 1];
      if (last && f.span[0] < last.end) {
        last.end = Math.max(last.end, f.span[1]);
      } else {
        merged.push({ start: f.span[0], end: f.span[1], finding: f });
      }
    }
    return merged;
  }, [findings]);

  if (findings.length === 0) {
    return (
      <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed text-text-secondary">
        {prompt || <span className="text-text-tertiary">— enter a prompt and run —</span>}
      </pre>
    );
  }

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  spans.forEach((s, i) => {
    if (cursor < s.start) {
      parts.push(<span key={`t-${i}`}>{prompt.slice(cursor, s.start)}</span>);
    }
    const display = lookup(s.finding.label);
    parts.push(
      <mark
        key={`m-${i}`}
        className="bg-accent-soft text-text-primary border-b-2 border-accent px-0.5"
        title={`${display.name} · ${s.finding.label} · ${display.category} · ${Math.round(
          s.finding.score * 100,
        )}%`}
      >
        {prompt.slice(s.start, s.end)}
      </mark>,
    );
    cursor = s.end;
  });
  if (cursor < prompt.length) parts.push(<span key="t-end">{prompt.slice(cursor)}</span>);

  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed text-text-primary">
      {parts}
    </pre>
  );
}

export default function SimulatorPage() {
  const { data: policies } = useSWR<Policy[]>('/admin/policies', swrFetcher);

  const [prompt, setPrompt] = useState('');
  const [policyId, setPolicyId] = useState<string>('');
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Hydrate history once on the client to keep SSR markup stable.
  useEffect(() => {
    setRecent(loadHistory());
  }, []);

  // Default to the first available policy.
  useEffect(() => {
    if (!policyId && policies && policies[0]) setPolicyId(policies[0].id);
  }, [policies, policyId]);

  const run = useCallback(async () => {
    if (!prompt.trim() || running) return;
    setRunning(true);
    setError(null);
    try {
      const res = await api.simulate({ prompt, policy_id: policyId || undefined });
      setResult(res);
      setRecent((prev) => {
        const next = [prompt, ...prev.filter((p) => p !== prompt)].slice(0, MAX_HISTORY);
        saveHistory(next);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }, [prompt, policyId, running]);

  // ⌘/Ctrl + Enter to run from inside the textarea.
  function onTextareaKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void run();
    }
  }

  const decisionTone = result ? decisionClasses(result.decision) : null;

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none" aria-hidden>
              §
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Simulator
            </h1>
          </div>
          <div className="hidden md:flex items-center gap-2 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <Wand2 className="h-3 w-3" strokeWidth={1.75} aria-hidden />
            dry-run · no audit row
          </div>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Paste a prompt to preview the gateway's decision. Findings are
          highlighted in place; transforms show what the upstream model would
          actually receive. Nothing is persisted to the audit log.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.05fr_1fr]">
        {/* Left: prompt + controls + recent */}
        <div className="space-y-3">
          <label
            htmlFor="sim-prompt"
            className="block font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary"
          >
            Prompt
          </label>
          <Textarea
            id="sim-prompt"
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={onTextareaKey}
            placeholder="e.g. Email the contract to alice.kim@acme.example…"
            className="min-h-[260px] font-mono text-[12.5px] leading-relaxed"
            aria-describedby="sim-prompt-help"
          />
          <p
            id="sim-prompt-help"
            className="font-mono text-[10.5px] tracking-[0.04em] text-text-tertiary"
          >
            ⌘ / Ctrl + Enter to run.
          </p>

          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[200px]">
              <label
                htmlFor="sim-policy"
                className="mb-1 block font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary"
              >
                Policy
              </label>
              <Select
                id="sim-policy"
                value={policyId}
                onChange={(e) => setPolicyId(e.target.value)}
              >
                <option value="">(default)</option>
                {(policies ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </div>
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={() => void run()}
              disabled={running || !prompt.trim()}
              aria-label="Run simulation"
            >
              {running ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <Play className="h-3.5 w-3.5" aria-hidden />
              )}
              {running ? 'Running…' : 'Run'}
            </Button>
            {error && (
              <span className="text-xs text-danger" role="alert">
                {error}
              </span>
            )}
          </div>

          {/* Sample prompts */}
          <div className="pt-2">
            <div className="mb-2 flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
              Samples
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SAMPLE_PROMPTS.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    setPrompt(s);
                    textareaRef.current?.focus();
                  }}
                  className="chip hover:bg-surface-sunken"
                  aria-label={`Use sample prompt ${i + 1}`}
                  title={s}
                >
                  <span className="max-w-[180px] truncate">{s}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Recent */}
          {recent.length > 0 && (
            <div className="pt-2">
              <div className="mb-2 flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                <History className="h-3 w-3" aria-hidden /> Recent
              </div>
              <ul className="space-y-1" aria-label="Recent prompts">
                {recent.map((p, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => {
                        setPrompt(p);
                        textareaRef.current?.focus();
                      }}
                      className="w-full truncate border border-border bg-canvas px-2 py-1.5 text-left font-mono text-[11px] text-text-secondary hover:bg-surface-sunken"
                      title={p}
                    >
                      {p}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right: result panel */}
        <div className="space-y-3">
          <Card aria-live="polite" aria-atomic="true">
            <CardHeader>
              <div className="min-w-0">
                <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                  Result
                </div>
                <CardTitle className="mt-0.5">
                  {result ? decisionLabel(result.decision) : 'No run yet'}
                </CardTitle>
                {result && (
                  <div className="mt-1 font-mono text-[10.5px] text-text-tertiary">
                    {result.policy_id ?? '—'} · {result.policy_version ?? '—'}
                    {result.latency_ms != null && ` · ${formatMs(result.latency_ms)}`}
                  </div>
                )}
              </div>
              {result && (
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 border px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.08em]',
                    decisionTone?.bg,
                    decisionTone?.fg,
                    decisionTone?.border,
                  )}
                  aria-label={`Decision: ${decisionLabel(result.decision)}`}
                >
                  <DecisionBadge decision={result.decision} size="xs" />
                </span>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {!result && !running && (
                <p className="text-sm text-text-secondary">
                  Run a prompt to see the decision, findings and transforms.
                </p>
              )}
              {running && (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-20 w-full" />
                </div>
              )}
              {result && (
                <>
                  {/* Highlighted prompt */}
                  <section>
                    <div className="mb-1.5 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                      Findings · {result.findings.length}
                    </div>
                    <div className="rounded-md border border-border bg-surface px-3 py-2">
                      <HighlightedPrompt prompt={prompt} findings={result.findings} />
                    </div>
                    {result.findings.length > 0 && (
                      <ul className="mt-2 flex flex-wrap gap-1.5">
                        {result.findings.map((f, i) => (
                          <li key={i}>
                            <FindingChip finding={f} showScore />
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {/* Matched rule */}
                  <section>
                    <div className="mb-1.5 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                      Matched rule
                    </div>
                    <div className="rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs">
                      <span className="text-text-tertiary">rule_id</span>{' '}
                      <span className="text-text-primary">{result.rule_id ?? '—'}</span>
                      {result.rule_index != null && (
                        <span className="ml-3 text-text-tertiary">
                          index {result.rule_index}
                        </span>
                      )}
                      {result.reason && (
                        <div className="mt-1 text-text-secondary">{result.reason}</div>
                      )}
                    </div>
                  </section>

                  {/* Transforms preview */}
                  <section>
                    <div className="mb-1.5 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                      Transforms · {result.transforms.length}
                    </div>
                    {result.transforms.length === 0 ? (
                      <p className="text-sm text-text-secondary">
                        No transforms — prompt passes through unmodified.
                      </p>
                    ) : (
                      <div className="overflow-hidden rounded-md border border-border">
                        <div className="grid grid-cols-[1fr_100px_1fr] gap-2 border-b border-border bg-surface-sunken px-3 py-1.5 text-xs uppercase tracking-[0.04em] text-text-tertiary">
                          <div>Label</div>
                          <div>Method</div>
                          <div>Replacement</div>
                        </div>
                        {result.transforms.map((t, i) => (
                          <div
                            key={i}
                            className="grid grid-cols-[1fr_100px_1fr] gap-2 border-b border-border bg-surface px-3 py-2 text-sm last:border-b-0"
                          >
                            <div className="font-mono text-text-primary truncate">{t.label}</div>
                            <div>
                              <Badge tone={t.method === 'redact' ? 'warn' : 'accent'}>
                                {t.method}
                              </Badge>
                            </div>
                            <div className="font-mono text-xs text-text-secondary truncate">
                              {t.replacement}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* Sanitised */}
                  <section>
                    <div className="mb-1.5 flex items-center justify-between font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                      <span>Sent to upstream</span>
                      <Tag>preview</Tag>
                    </div>
                    <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface px-3 py-2 font-mono text-[12.5px] leading-relaxed text-text-primary">
                      {result.sanitised}
                    </pre>
                  </section>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
