'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Copy, ShieldAlert } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetBody, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/tag';
import { Separator } from '@/components/ui/separator';
import { DecisionBadge } from './DecisionBadge';
import { DetokeniseModal } from './DetokeniseModal';
import { FindingChip } from './FindingChip';
import { RedlineDiff } from './RedlineDiff';
import { ago, cn, formatBytes, formatMs, shortId } from '@/lib/utils';
import type { AuditEvent } from '@/lib/types';

// Vault placeholder grammar: <LABEL_XXXX> where XXXX is base32 (A-Z, 2-7).
// Mirrors the regex used by the gateway's restore stream.
const PLACEHOLDER_RE = /<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4,8})>/g;

function extractPlaceholders(text?: string | null): string[] {
  if (!text) return [];
  const out: string[] = [];
  for (const m of text.matchAll(PLACEHOLDER_RE)) out.push(m[0]);
  return Array.from(new Set(out));
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 py-1.5 text-sm">
      <div className="text-text-tertiary">{k}</div>
      <div className="min-w-0 break-words text-text-primary">{v}</div>
    </div>
  );
}

/**
 * Drawer surfaced when an event row is clicked.
 *
 * Keyboard flow:
 *   Esc                         → close (handled by Radix Dialog).
 *   Tab / Shift-Tab             → cycle through interactive elements; focus is
 *                                 trapped inside the drawer by Radix.
 *   Within "Findings" list:
 *     ArrowDown / ArrowUp       → move focus to next / previous finding.
 *     Home / End                → first / last finding.
 *     Enter | Space             → copy the finding's vault token (or matched
 *                                 detector label, if no token) to the clipboard.
 *     C                         → copy without selecting (shortcut).
 *
 * Copy actions are announced through a polite live region ("Copied …") so that
 * screen-reader users hear the same affordance that sighted users see toast.
 */
export function EventDetail({
  event,
  open,
  onOpenChange,
}: {
  event: AuditEvent | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [rawOpen, setRawOpen] = useState(false);
  const [copied, setCopied] = useState<string>('');
  const findingsRef = useRef<HTMLUListElement>(null);
  const [detokOpen, setDetokOpen] = useState(false);
  const [activePlaceholder, setActivePlaceholder] = useState<string>('');
  const detokTriggerRef = useRef<HTMLButtonElement>(null);
  const [revealedSet, setRevealedSet] = useState<Set<string>>(new Set());

  // Reset state when event changes
  useEffect(() => {
    setRawOpen(false);
    setCopied('');
    setDetokOpen(false);
    setActivePlaceholder('');
    setRevealedSet(new Set());
  }, [event?.id]);

  // Collect every placeholder mentioned in either preview or finding tokens.
  const placeholders = useMemo(() => {
    if (!event) return [];
    const set = new Set<string>();
    extractPlaceholders(event.sanitised_preview).forEach((p) => set.add(p));
    for (const f of event.findings) {
      if (f.vault_token && PLACEHOLDER_RE.test(f.vault_token)) set.add(f.vault_token);
      // Reset lastIndex because PLACEHOLDER_RE is /g and matchAll/test share it.
      PLACEHOLDER_RE.lastIndex = 0;
    }
    return Array.from(set);
  }, [event]);

  function openDetokenise(ph: string, trigger: HTMLButtonElement | null) {
    setActivePlaceholder(ph);
    if (trigger) (detokTriggerRef as any).current = trigger;
    setDetokOpen(true);
  }

  function copyText(text: string, descriptor: string) {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return;
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(`Copied ${descriptor}`);
      // Clear after 2.5s so the same message fires again on the next copy.
      window.setTimeout(() => setCopied(''), 2500);
    });
  }

  function focusFinding(index: number) {
    const root = findingsRef.current;
    if (!root) return;
    const items = root.querySelectorAll<HTMLButtonElement>('[data-finding]');
    if (items.length === 0) return;
    const wrapped = (index + items.length) % items.length;
    items[wrapped]?.focus();
  }

  function handleFindingsKey(e: React.KeyboardEvent<HTMLUListElement>) {
    const items = Array.from(
      e.currentTarget.querySelectorAll<HTMLButtonElement>('[data-finding]'),
    );
    const idx = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusFinding(idx + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusFinding(idx - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusFinding(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      focusFinding(items.length - 1);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent aria-describedby={event ? `event-${event.id}-desc` : undefined}>
        <SheetHeader>
          <div className="min-w-0">
            <SheetTitle className="truncate">
              Event <span className="font-mono text-text-secondary">{event ? shortId(event.id, 12) : ''}</span>
            </SheetTitle>
            <SheetDescription id={event ? `event-${event.id}-desc` : undefined}>
              {event ? `${event.route} · ${ago(event.occurred_at)}` : ''}
            </SheetDescription>
          </div>
          {event && <DecisionBadge decision={event.decision} size="md" />}
        </SheetHeader>

        {/* Polite live region for copy confirmations. */}
        <div role="status" aria-live="polite" className="sr-skip">
          {copied}
        </div>

        {event && (
          <SheetBody>
            <section aria-labelledby="evd-principal">
              <h4
                id="evd-principal"
                className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
              >
                Principal
              </h4>
              <div className="rounded-md border border-border bg-surface px-3 py-2">
                <KV k="User" v={<span className="font-mono">{event.principal.email}</span>} />
                <KV k="Tenant" v={<Tag>{event.tenant_id}</Tag>} />
                <KV
                  k="Groups"
                  v={
                    <div className="flex flex-wrap gap-1">
                      {event.principal.groups.map((g) => (
                        <Tag key={g}>{g}</Tag>
                      ))}
                    </div>
                  }
                />
                <KV k="Country" v={event.principal.country ?? '—'} />
                <KV k="Source IP" v={<span className="font-mono">{event.principal.ip ?? '—'}</span>} />
              </div>
            </section>

            <Separator className="my-4" />

            <section aria-labelledby="evd-policy">
              <h4
                id="evd-policy"
                className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
              >
                Policy hit
              </h4>
              <div className="rounded-md border border-border bg-surface px-3 py-2">
                <KV k="Policy" v={<Tag>{event.policy_id ?? '—'}</Tag>} />
                <KV k="Version" v={<span className="font-mono">{event.policy_version ?? '—'}</span>} />
                <KV
                  k="Rule"
                  v={
                    <span>
                      <span className="font-mono text-text-primary">{event.rule_id}</span>
                      <span className="ml-2 text-text-tertiary">index {event.rule_index ?? '?'}</span>
                    </span>
                  }
                />
                {event.reason && (
                  <KV k="Reason" v={<span className="text-block">{event.reason}</span>} />
                )}
              </div>
            </section>

            <Separator className="my-4" />

            <section aria-labelledby="evd-findings">
              <h4
                id="evd-findings"
                className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
              >
                Findings ({event.findings.length})
              </h4>
              {event.findings.length === 0 ? (
                <p className="text-sm text-text-secondary">No findings — request was clean.</p>
              ) : (
                <>
                  <p className="mb-2 text-xs text-text-tertiary">
                    Use <kbd className="kbd">↑</kbd> <kbd className="kbd">↓</kbd> to move,
                    <kbd className="kbd ml-1">Enter</kbd> to copy the matched snippet.
                  </p>
                  <ul
                    ref={findingsRef}
                    role="list"
                    aria-label="Findings — keyboard navigable"
                    onKeyDown={handleFindingsKey}
                    className="flex flex-wrap gap-1.5"
                  >
                    {event.findings.map((f, i) => {
                      const snippet = f.vault_token ?? f.replacement ?? f.label;
                      const descriptor = f.vault_token
                        ? 'vault token'
                        : f.replacement
                          ? 'replacement marker'
                          : 'detector label';
                      return (
                        <li key={i}>
                          <button
                            type="button"
                            data-finding
                            onClick={() => copyText(snippet, descriptor)}
                            title={`Copy ${descriptor} — span ${f.span[0]}–${f.span[1]}`}
                            aria-label={`Finding ${i + 1} of ${event.findings.length}: ${f.label}. Press Enter to copy ${descriptor}.`}
                            className={cn(
                              'group inline-flex items-center gap-1',
                              'focus:outline-none',
                            )}
                          >
                            <FindingChip finding={f} showScore />
                            <Copy
                              className="h-3 w-3 text-text-tertiary opacity-0 group-hover:opacity-100 group-focus:opacity-100"
                              aria-hidden
                            />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </section>

            {placeholders.length > 0 && (
              <>
                <Separator className="my-4" />
                <section aria-labelledby="evd-tokens">
                  <h4
                    id="evd-tokens"
                    className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
                  >
                    Vault tokens ({placeholders.length})
                    <ShieldAlert className="h-3 w-3 text-accent" aria-hidden />
                  </h4>
                  <p className="mb-2 text-xs text-text-tertiary">
                    Click a token to detokenise. Every reveal is audited and notifies
                    SecOps.
                  </p>
                  <ul className="flex flex-wrap gap-1.5" role="list">
                    {placeholders.map((ph) => {
                      const revealed = revealedSet.has(ph);
                      return (
                        <li key={ph}>
                          <button
                            type="button"
                            onClick={(e) => openDetokenise(ph, e.currentTarget)}
                            title="Click to detokenise — audited"
                            aria-label={`Detokenise ${ph} — opens a break-glass dialog`}
                            className={cn(
                              'inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[11px] transition-colors duration-fast',
                              revealed
                                ? 'border-success/40 bg-success/5 text-success'
                                : 'border-accent/40 bg-accent/5 text-accent hover:bg-accent/10',
                            )}
                          >
                            <span aria-hidden>{revealed ? '◉' : '◈'}</span>
                            {ph}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              </>
            )}

            {event.transforms.length > 0 && (
              <>
                <Separator className="my-4" />
                <section aria-labelledby="evd-transforms">
                  <h4
                    id="evd-transforms"
                    className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
                  >
                    Applied transforms
                  </h4>
                  <div className="overflow-hidden rounded-md border border-border">
                    <div className="grid grid-cols-[1fr_120px_80px_120px] gap-2 border-b border-border bg-surface-sunken px-3 py-1.5 text-xs uppercase tracking-[0.04em] text-text-tertiary">
                      <div>Label</div>
                      <div>Method</div>
                      <div className="text-right">Count</div>
                      <div>Scope / TTL</div>
                    </div>
                    {event.transforms.map((t, i) => (
                      <div
                        key={i}
                        className="grid grid-cols-[1fr_120px_80px_120px] gap-2 border-b border-border bg-surface px-3 py-2 text-sm last:border-b-0"
                      >
                        <div className="font-mono text-text-primary">{t.label}</div>
                        <div>
                          <Badge tone={t.method === 'tokenise' ? 'accent' : t.method === 'redact' ? 'warn' : 'info'}>
                            {t.method}
                          </Badge>
                        </div>
                        <div className="text-right tabular-nums">{t.count}</div>
                        <div className="text-text-secondary">
                          {t.scope ?? '—'}
                          {t.ttl ? ` · ${t.ttl}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </>
            )}

            <Separator className="my-4" />

            <section aria-labelledby="evd-redline">
              <h4
                id="evd-redline"
                className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
              >
                Redline diff
              </h4>
              <RedlineDiff received={event.received_preview} sanitised={event.sanitised_preview} />
            </section>

            <Separator className="my-4" />

            <section aria-labelledby="evd-routing">
              <h4
                id="evd-routing"
                className="mb-2 text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary"
              >
                Routing & performance
              </h4>
              <div className="rounded-md border border-border bg-surface px-3 py-2">
                <KV k="Upstream" v={<span className="font-mono">{event.upstream}</span>} />
                <KV k="Latency" v={`${formatMs(event.latency_ms)}`} />
                <KV
                  k="Bytes in / out"
                  v={`${formatBytes(event.bytes_in)} / ${formatBytes(event.bytes_out)}`}
                />
                <KV k="Bundle digest" v={<span className="font-mono">{event.bundle_digest}</span>} />
                <KV k="Request digest" v={<span className="font-mono">{event.request_digest}</span>} />
                {event.response_digest && (
                  <KV k="Response digest" v={<span className="font-mono">{event.response_digest}</span>} />
                )}
              </div>
            </section>

            <Separator className="my-4" />

            <section>
              <button
                type="button"
                onClick={() => setRawOpen((x) => !x)}
                aria-expanded={rawOpen}
                className="flex w-full items-center justify-between rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium tracking-ui text-text-primary hover:bg-surface-sunken"
              >
                <span>Raw audit row (JSON)</span>
                {rawOpen ? (
                  <ChevronDown className="h-4 w-4" aria-hidden />
                ) : (
                  <ChevronRight className="h-4 w-4" aria-hidden />
                )}
              </button>
              {rawOpen && (
                <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border bg-surface-sunken p-3 font-mono text-[11px] leading-relaxed text-text-secondary">
                  {JSON.stringify(event, null, 2)}
                </pre>
              )}
            </section>
          </SheetBody>
        )}
      </SheetContent>
      {event && activePlaceholder && (
        <DetokeniseModal
          open={detokOpen}
          onOpenChange={setDetokOpen}
          requestId={event.request_id ?? event.id}
          placeholder={activePlaceholder}
          tenantId={event.tenant_id}
          returnFocusRef={detokTriggerRef}
          onRevealed={(r) =>
            setRevealedSet((prev) => new Set(prev).add(r.placeholder))
          }
        />
      )}
    </Sheet>
  );
}
