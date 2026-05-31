'use client';

// Observation-led recommendations.
//
// The premise of this page is that Section should never make the operator
// declare an industry up front. Instead, the gateway emits events for the
// universal default policy, and *this page* surfaces optional overlays once
// enough evidence has accumulated to justify them.
//
// Each recommendation card carries:
//   - the family of evidence that triggered it,
//   - a one-line "why" with named detector counts (display names from the
//     catalogue, not opaque IDs like `financial.credit_card`),
//   - what adopting the overlay would change,
//   - a deep link to the audit rows that triggered it ("Show examples"),
//   - Adopt / Dismiss controls (Adopt → opens a PR against the policy repo
//     in production; here it shows a toast so the demo stays honest).
//
// Dismissed state persists per-user in localStorage; a dismissed
// recommendation only resurfaces if evidence increases by ≥ 50%.

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  HeartPulse,
  Lightbulb,
  Database,
  KeyRound,
  Code2,
  X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tag } from '@/components/ui/tag';
import { EmptyState } from '@/components/ui/empty-state';
import { useToast } from '@/components/ui/toast';
import { cn, formatInt } from '@/lib/utils';
import { LABELS, lookup } from '@/lib/labels';

/* Healthcare-overlay-only detectors that aren't in the core taxonomy
   yet. Once they ship as canonical labels, drop this map. */
const OVERLAY_DETECTOR_DISPLAY: Record<string, string> = {
  'regex.medical_record_number': 'Medical record number',
  'regex.mrn': 'Medical record number',
  'regex.icd10': 'ICD-10 diagnosis code',
  'regex.cpt': 'CPT procedure code',
  'regex.npi': 'US National Provider Identifier',
  'regex.health_plan_beneficiary': 'Health-plan beneficiary number',
  'regex.us_account_number': 'US bank account number',
};

function display(label: string): string {
  return OVERLAY_DETECTOR_DISPLAY[label] ?? lookup(label).name;
}

/* ─── recommendation shape + sample evidence ─── */

type Evidence = { label: string; count: number };

type Recommendation = {
  id: string;
  family: 'health_data' | 'payment_data' | 'credentials' | 'source_code';
  overlay_path: string;
  headline: string;
  body: string;
  adds: string[];
  evidence: Evidence[];
  window: string;
  trigger_query: string; // shown in "Why this surfaced"
};

// In production these come from the gateway's `/admin/recommendations`
// endpoint — derived from the last N hours of audit findings, deduped
// against dismissed state. For now the page ships with a representative
// set so the design and the user flow are demonstrable.
const RECOMMENDATIONS: Recommendation[] = [
  {
    id: 'rec.healthcare',
    family: 'health_data',
    overlay_path: 'policies/0100-healthcare.yaml',
    headline: 'Adopt the healthcare overlay',
    body: 'We saw clinical identifiers in the last 24 hours. The healthcare overlay tightens retention and routes those prompts to a BAA-covered model only.',
    adds: [
      'Retention extended to 2,555 days for PHI findings',
      'Route forced to azure/gpt-4o-eu (BAA-covered)',
      'Deterministic tokens for MRN / NPI so chart joins still work',
    ],
    evidence: [
      { label: 'regex.medical_record_number', count: 47 },
      { label: 'regex.icd10', count: 12 },
      { label: 'regex.npi', count: 6 },
      { label: 'healthcare.medical_license', count: 3 },
    ],
    window: 'Last 24 h',
    trigger_query: "any(findings, .family == 'health_data')",
  },
  {
    id: 'rec.finance',
    family: 'payment_data',
    overlay_path: 'policies/0200-finance.yaml',
    headline: 'Adopt the finance overlay',
    body: 'IBAN and US-account numbers are appearing alongside person names. The finance overlay logs a SOX-aligned audit trail and irreversibly redacts PANs.',
    adds: [
      'PAN redaction switched from reversible to irreversible',
      'IBAN tokens scoped to tenant + 30d TTL (was 1h)',
      'SOX retention tag applied for the audit export',
    ],
    evidence: [
      { label: 'financial.iban', count: 31 },
      { label: 'financial.credit_card', count: 14 },
      { label: 'regex.us_account_number', count: 9 },
    ],
    window: 'Last 24 h',
    trigger_query: "any(findings, .family == 'payment_data')",
  },
  {
    id: 'rec.secrets',
    family: 'credentials',
    overlay_path: 'policies/0300-secrets-hardening.yaml',
    headline: 'Harden secret-leak handling',
    body: 'Five distinct secret issuers fired in the last 7 days. The hardening overlay raises severity to "critical", pages on-call via PagerDuty, and rotates the upstream key on confirmed exfiltration.',
    adds: [
      'Severity for secrets.* findings raised to critical',
      'PagerDuty incident on first occurrence per principal',
      'Upstream provider key auto-rotated via Vault on confirmed leak',
    ],
    evidence: [
      { label: 'credential.aws_access_key', count: 4 },
      { label: 'credential.github_pat', count: 2 },
      { label: 'credential.openai_api_key', count: 2 },
      { label: 'credential.private_key', count: 1 },
    ],
    window: 'Last 7 d',
    trigger_query: "count(findings, .family == 'credentials') >= 5",
  },
  {
    id: 'rec.code',
    family: 'source_code',
    overlay_path: 'policies/0400-code-egress.yaml',
    headline: 'Restrict source-code egress',
    body: 'Large code blocks with proprietary markers are being sent to consumer model endpoints. The code-egress overlay forces these through self-hosted models only.',
    adds: [
      'Code-bearing requests routed to local-llm/qwen-coder-2.5',
      'Proprietary-marker findings escalate from transform → block',
      'Repo-name lineage edge attached so the source repo is auditable',
    ],
    evidence: [
      { label: 'code.block', count: 218 },
      { label: 'code.proprietary_marker', count: 8 },
    ],
    window: 'Last 7 d',
    trigger_query: "count(findings, .label == 'code.proprietary_marker') >= 3",
  },
];

/* ─── per-family iconography ─── */
const FAMILY_META: Record<
  Recommendation['family'],
  { Icon: typeof HeartPulse; label: string }
> = {
  health_data: { Icon: HeartPulse, label: 'Health data' },
  payment_data: { Icon: Database, label: 'Payment data' },
  credentials: { Icon: KeyRound, label: 'Credentials & secrets' },
  source_code: { Icon: Code2, label: 'Source code' },
};

/* ─── persistence of dismissed state ─── */
const DISMISSED_KEY = 'section.recommendations.dismissed.v1';

function loadDismissed(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.localStorage.getItem(DISMISSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as string[];
    return new Set(parsed);
  } catch {
    return new Set();
  }
}

function saveDismissed(s: Set<string>): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(DISMISSED_KEY, JSON.stringify([...s]));
}

export default function RecommendationsPage() {
  const { push } = useToast();
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const [adopted, setAdopted] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setDismissed(loadDismissed());
  }, []);

  const visible = useMemo(
    () => RECOMMENDATIONS.filter((r) => !dismissed.has(r.id) && !adopted.has(r.id)),
    [dismissed, adopted],
  );

  const dismiss = (id: string) => {
    const next = new Set(dismissed);
    next.add(id);
    setDismissed(next);
    saveDismissed(next);
    push({
      title: 'Recommendation dismissed',
      description: "We won't show it again until the evidence increases materially.",
    });
  };

  const adopt = (rec: Recommendation) => {
    const next = new Set(adopted);
    next.add(rec.id);
    setAdopted(next);
    push({
      title: 'Adoption queued',
      description: `A pull request adding ${rec.overlay_path} to the bundle would be opened against your policy repo.`,
    });
  };

  const restoreAll = () => {
    setDismissed(new Set());
    saveDismissed(new Set());
    setAdopted(new Set());
  };

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              iv.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Recommendations
            </h1>
          </div>
          <Link
            href="/docs/deployment-coverage.md#75-detector-catalogue--recommendations"
            className="inline-flex items-center gap-1 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent"
          >
            how this works <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Section never asks for your industry. The universal default policy
          catches everything; this page surfaces optional overlays once real
          traffic has produced enough evidence to make them worth the extra
          friction. Adopt only what your audit log earns.
        </p>
      </header>

      {/* Summary strip */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryStat label="Pending" value={visible.length} accent />
        <SummaryStat label="Adopted (session)" value={adopted.size} />
        <SummaryStat label="Dismissed" value={dismissed.size} />
        <SummaryStat
          label="Catalogue size"
          value={
            Object.keys(LABELS).length + Object.keys(OVERLAY_DETECTOR_DISPLAY).length
          }
          hint="detectors with display names"
        />
      </section>

      {visible.length === 0 && (
        <EmptyState
          icon={<Lightbulb className="h-6 w-6" />}
          title="No active recommendations. We'll surface one when audit findings warrant it — universal detection is already running."
          docHref="/docs/deployment-coverage.md#75-detector-catalogue--recommendations"
          docLabel="Read the philosophy"
          action={
            (dismissed.size > 0 || adopted.size > 0) ? (
              <Button variant="ghost" size="sm" onClick={restoreAll}>
                Restore dismissed & adopted
              </Button>
            ) : undefined
          }
        />
      )}

      <div className="space-y-4">
        {visible.map((rec) => {
          const { Icon, label } = FAMILY_META[rec.family];
          const totalEvidence = rec.evidence.reduce((s, e) => s + e.count, 0);
          const isExpanded = expanded === rec.id;
          return (
            <Card key={rec.id} className="overflow-hidden">
              <CardHeader>
                <div className="flex items-start gap-3 min-w-0">
                  <div className="mt-0.5 grid h-7 w-7 place-items-center border border-border bg-surface-sunken shrink-0">
                    <Icon className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <CardTitle>{label}</CardTitle>
                      <Badge tone="neutral">{rec.window}</Badge>
                    </div>
                    <div className="mt-0.5 text-[15px] text-text-primary leading-snug">
                      {rec.headline}
                    </div>
                    <div className="mt-0.5 font-mono text-[10.5px] tracking-[0.06em] text-text-tertiary truncate">
                      {rec.overlay_path}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
                    Evidence
                  </span>
                  <span className="font-mono tabular-nums text-[18px] text-text-primary leading-none">
                    {formatInt(totalEvidence)}
                  </span>
                  <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
                    findings
                  </span>
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                <p className="text-sm text-text-secondary max-w-2xl">{rec.body}</p>

                {/* Evidence chips */}
                <div>
                  <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary mb-1.5">
                    Detected
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {rec.evidence.map((e) => (
                      <Tag key={e.label}>
                        <span>{display(e.label)}</span>
                        <span className="ml-1 font-mono tabular-nums text-text-primary">
                          {formatInt(e.count)}
                        </span>
                      </Tag>
                    ))}
                  </div>
                </div>

                {/* What it adds */}
                <div>
                  <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary mb-1.5">
                    What this overlay adds
                  </div>
                  <ul className="space-y-1">
                    {rec.adds.map((a) => (
                      <li key={a} className="flex items-start gap-2 text-sm text-text-secondary">
                        <Check className="mt-0.5 h-3.5 w-3.5 text-accent shrink-0" strokeWidth={2} />
                        <span>{a}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Expand: why this surfaced */}
                <button
                  type="button"
                  onClick={() => setExpanded(isExpanded ? null : rec.id)}
                  className={cn(
                    'flex items-center gap-1 font-mono text-[10.5px] tracking-[0.14em] uppercase',
                    'text-text-tertiary hover:text-text-primary transition-colors',
                  )}
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
                  ) : (
                    <ChevronRight className="h-3 w-3" strokeWidth={1.75} />
                  )}
                  Why this surfaced
                </button>
                {isExpanded && (
                  <div className="border-l-2 border-border pl-3 space-y-2">
                    <div className="text-sm text-text-secondary">
                      The recommendations engine ran the following predicate
                      against your audit findings:
                    </div>
                    <pre className="font-mono text-[11.5px] text-text-primary bg-surface-sunken border border-border p-2 overflow-x-auto">
                      <code>{rec.trigger_query}</code>
                    </pre>
                    <div className="text-sm text-text-secondary">
                      The {formatInt(totalEvidence)} matching findings are
                      visible in the audit log filtered to this overlay's
                      detector set.
                    </div>
                    <Link
                      href={`/events?family=${rec.family}`}
                      className="inline-flex items-center gap-1 font-mono text-[10.5px] tracking-[0.14em] uppercase text-accent hover:underline underline-offset-2"
                    >
                      Show evidence in Events <ArrowUpRight className="h-3 w-3" />
                    </Link>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
                  <Button variant="primary" size="sm" onClick={() => adopt(rec)}>
                    Adopt overlay
                  </Button>
                  <Button variant="secondary" size="sm" asChild>
                    <Link href={`/events?family=${rec.family}`}>Show examples</Link>
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => dismiss(rec.id)}>
                    <X className="h-3.5 w-3.5" strokeWidth={1.75} />
                    Dismiss
                  </Button>
                  <span className="ml-auto font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
                    Adopt = opens a PR against your policy repo
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {visible.length > 0 && (dismissed.size > 0 || adopted.size > 0) && (
        <div className="border-t border-border pt-4">
          <Button variant="ghost" size="sm" onClick={restoreAll}>
            Restore dismissed & adopted
          </Button>
        </div>
      )}
    </div>
  );
}

function SummaryStat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: number;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="border border-border bg-canvas px-4 py-3">
      <div className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
        {label}
      </div>
      <div
        className={cn(
          'mt-1 font-mono tabular-nums text-[22px] leading-none',
          accent ? 'text-accent' : 'text-text-primary',
        )}
      >
        {formatInt(value)}
      </div>
      {hint && (
        <div className="mt-1 font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
          {hint}
        </div>
      )}
    </div>
  );
}
