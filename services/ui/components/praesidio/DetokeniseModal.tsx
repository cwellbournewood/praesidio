'use client';

/**
 * Break-glass detokenisation modal.
 *
 * UX contract:
 *   - Two-step confirmation: the operator types a justification (≥16 chars)
 *     and a ticket id (required) and ticks "I understand…" → clicks
 *     "Continue" → sees "Are you sure?" → clicks "Reveal value" to commit.
 *     Escape cancels at any point.
 *   - On reveal the plaintext appears inline with a copy button and a
 *     30-second auto-hide countdown, so the value is never left on screen
 *     after the operator walks away.
 *   - HTTP 429 from the gateway (per-tenant detokenise quota) is handled
 *     explicitly: the modal shows a Retry-After countdown rather than a
 *     generic error, and the Retry button is disabled until the cooldown
 *     expires.
 *   - Visual register is intentionally "elevated": indigo accent on the
 *     header sits on a soft amber backdrop so the modal reads as a
 *     privileged action, distinct from any other dialog in the app.
 *   - A polite aria-live region announces success ("Reveal logged to
 *     audit trail."), failure, and hide events for screen-reader users.
 *
 * Wire-level contract: POST /admin/detokenise with the schema
 * documented in `services/gateway/praesidio_gateway/api/admin/detokenise.py`.
 * The plaintext is returned in `hits[0].value` and is NEVER cached or
 * persisted on the client — it lives in component state for at most 30s.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Eye, Loader2, Lock, ShieldAlert } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/components/ui/toast';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';

const MIN_JUSTIFICATION = 16;
const AUTO_HIDE_SECONDS = 30;
const GATEWAY_BASE =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_GATEWAY_URL) ||
  'http://localhost:8080';

type Stage =
  | 'form'
  | 'confirm'
  | 'submitting'
  | 'revealed'
  | 'notfound'
  | 'ratelimited'
  | 'error';

export interface DetokeniseResult {
  placeholder: string;
  value: string;
  value_sha256: string;
}

export function DetokeniseModal({
  open,
  onOpenChange,
  requestId,
  placeholder,
  tenantId,
  onRevealed,
  returnFocusRef,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  requestId: string;
  placeholder: string;
  tenantId?: string;
  onRevealed?: (r: DetokeniseResult) => void;
  /** Element to return focus to when the dialog closes. */
  returnFocusRef?: React.RefObject<HTMLElement>;
}) {
  const t = useT();
  const toast = useToast();
  const [stage, setStage] = useState<Stage>('form');
  const [justification, setJustification] = useState('');
  const [ticketId, setTicketId] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [revealed, setRevealed] = useState<{ value: string; sha256: string } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(AUTO_HIDE_SECONDS);
  const continueBtnRef = useRef<HTMLButtonElement>(null);
  const liveRef = useRef<HTMLDivElement>(null);

  const justificationValid = justification.trim().length >= MIN_JUSTIFICATION;
  const ticketValid = ticketId.trim().length > 0;

  // Reset state every time the modal opens for a new placeholder.
  useEffect(() => {
    if (open) {
      setStage('form');
      setJustification('');
      setTicketId('');
      setConfirmed(false);
      setRevealed(null);
      setErrorMsg(null);
      setRetryAfter(0);
      setSecondsLeft(AUTO_HIDE_SECONDS);
    }
  }, [open, placeholder]);

  // Per-tenant rate-limit countdown — surfaces a live timer in the
  // 'ratelimited' branch so the operator knows when to retry.
  useEffect(() => {
    if (stage !== 'ratelimited' || retryAfter <= 0) return;
    const id = window.setTimeout(() => setRetryAfter((s) => s - 1), 1_000);
    return () => window.clearTimeout(id);
  }, [stage, retryAfter]);

  // Auto-hide countdown for the revealed plaintext.
  useEffect(() => {
    if (stage !== 'revealed') return;
    if (secondsLeft <= 0) {
      setRevealed(null);
      announce(t('detok.hidden', 'Revealed value auto-hidden.'));
      onOpenChange(false);
      return;
    }
    const id = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1_000);
    return () => window.clearTimeout(id);
  }, [stage, secondsLeft]); // eslint-disable-line react-hooks/exhaustive-deps

  // Return focus to the trigger element on close.
  useEffect(() => {
    if (!open && returnFocusRef?.current) {
      // Defer to next tick so Radix has finished closing animations.
      const tid = window.setTimeout(() => returnFocusRef.current?.focus(), 0);
      return () => window.clearTimeout(tid);
    }
  }, [open, returnFocusRef]);

  function announce(msg: string) {
    if (liveRef.current) {
      liveRef.current.textContent = '';
      // Force re-announce by RAF.
      window.requestAnimationFrame(() => {
        if (liveRef.current) liveRef.current.textContent = msg;
      });
    }
  }

  async function submit() {
    setStage('submitting');
    setErrorMsg(null);
    try {
      const body = {
        request_id: requestId,
        placeholders: [placeholder],
        justification: justification.trim(),
        ticket_id: ticketId.trim(),
      };
      const headers: Record<string, string> = {
        'content-type': 'application/json',
        accept: 'application/json',
      };
      if (tenantId) headers['X-Praesidio-Tenant'] = tenantId;
      const res = await fetch(`${GATEWAY_BASE}/admin/detokenise`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        cache: 'no-store',
      });
      if (res.status === 429) {
        // Per-tenant detokenise rate limit. The gateway sets Retry-After
        // (seconds) — surface it so the operator gets a live countdown
        // rather than a generic "try later" message.
        const retryHeader = res.headers.get('retry-after') ?? '';
        const seconds = Math.max(1, parseInt(retryHeader, 10) || 60);
        setRetryAfter(seconds);
        setStage('ratelimited');
        announce(
          t(
            'detok.rateLimited',
            `Tenant detokenise rate limit exceeded. Retry in ${seconds} seconds.`,
            { seconds },
          ),
        );
        return;
      }
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`gateway ${res.status} ${txt.slice(0, 200)}`);
      }
      const json = await res.json();
      const hit = (json.hits ?? []).find((h: any) => h.placeholder === placeholder);
      if (!hit || !hit.found) {
        setStage('notfound');
        announce(t('detok.notFound', 'Placeholder not found in vault.'));
        return;
      }
      setRevealed({ value: hit.value, sha256: hit.value_sha256 });
      setSecondsLeft(AUTO_HIDE_SECONDS);
      setStage('revealed');
      announce(t('detok.success', 'Reveal logged to audit trail.'));
      onRevealed?.({
        placeholder,
        value: hit.value,
        value_sha256: hit.value_sha256,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg);
      setStage('error');
      announce(t('detok.error', 'Detokenise request failed.'));
      toast.push({
        tone: 'danger',
        title: t('detok.error', 'Detokenise failed'),
        description: msg,
      });
    }
  }

  async function copyRevealed() {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed.value);
      toast.push({ tone: 'success', title: t('common.copied', 'Copied') });
      announce(t('common.copied', 'Copied'));
    } catch {
      /* ignore — older browsers */
    }
  }

  const charCount = justification.trim().length;
  const counterTone = useMemo(() => {
    if (charCount === 0) return 'text-text-tertiary';
    if (charCount < MIN_JUSTIFICATION) return 'text-warn';
    return 'text-success';
  }, [charCount]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby="detok-desc"
        className={cn(
          // Soft amber backdrop + indigo accent → "elevated permission" register.
          'border-warn/40 bg-[#FFFBEF]',
        )}
      >
        <div className="flex items-start gap-3">
          <div className="rounded-md border border-accent bg-accent/10 p-2 text-accent">
            <ShieldAlert className="h-5 w-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <DialogTitle className="text-text-primary">
              {t('detok.title', 'Detokenise placeholder')}
            </DialogTitle>
            <DialogDescription id="detok-desc">
              {t(
                'detok.subtitle',
                'Reveals the original value behind a vault token. Audited and notified to SecOps.',
              )}
            </DialogDescription>
          </div>
        </div>

        <div className="sr-skip" role="status" aria-live="polite" ref={liveRef} />

        <div className="mt-4 space-y-3">
          <div className="rounded-md border border-border bg-canvas px-3 py-2">
            <div className="grid grid-cols-[100px_1fr] gap-3 text-sm">
              <dt className="text-xs uppercase tracking-[0.04em] text-text-tertiary">
                {t('detok.placeholder', 'Placeholder')}
              </dt>
              <dd className="min-w-0 break-all font-mono text-text-primary">{placeholder}</dd>
              <dt className="text-xs uppercase tracking-[0.04em] text-text-tertiary">
                request_id
              </dt>
              <dd className="min-w-0 break-all font-mono text-text-secondary">{requestId}</dd>
            </div>
          </div>

          {(stage === 'form' || stage === 'confirm') && (
            <>
              <label className="block text-sm">
                <span className="flex items-baseline justify-between">
                  <span className="font-medium text-text-primary">
                    {t('detok.justification', 'Justification')}
                  </span>
                  <span className={cn('font-mono text-[10.5px] tnum', counterTone)}>
                    {t('detok.charCount', `${charCount} / ${MIN_JUSTIFICATION}`, {
                      count: charCount,
                      min: MIN_JUSTIFICATION,
                    })}
                  </span>
                </span>
                <Textarea
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder="e.g. SOC-2026-118 incident — verifying source email for IR ticket"
                  rows={3}
                  className="mt-1.5"
                  aria-describedby="detok-just-help"
                  aria-invalid={charCount > 0 && !justificationValid}
                  required
                  disabled={stage === 'confirm'}
                />
                <span
                  id="detok-just-help"
                  className="mt-1 block text-xs text-text-tertiary"
                >
                  {t(
                    'detok.justificationHelp',
                    'Why is this reveal necessary? Minimum 16 characters. Recorded verbatim.',
                  )}
                </span>
              </label>

              <label className="block text-sm">
                <span className="font-medium text-text-primary">
                  {t('detok.ticketId', 'Ticket ID')}
                  <span className="ml-1 text-danger" aria-hidden>
                    *
                  </span>
                </span>
                <Input
                  value={ticketId}
                  onChange={(e) => setTicketId(e.target.value)}
                  placeholder="SEC-2024-118"
                  className="mt-1.5 font-mono"
                  aria-describedby="detok-ticket-help"
                  aria-invalid={ticketId.length > 0 && !ticketValid}
                  required
                  disabled={stage === 'confirm'}
                />
                <span id="detok-ticket-help" className="mt-1 block text-xs text-text-tertiary">
                  {t(
                    'detok.ticketHelp',
                    'Required. Links this reveal to an open incident, e.g. JIRA SEC-2024-118.',
                  )}
                </span>
              </label>

              <label className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={confirmed}
                  onCheckedChange={(c) => setConfirmed(Boolean(c))}
                  aria-label={t(
                    'detok.confirmCheckbox',
                    'I understand this action is logged and notifies SecOps.',
                  )}
                  disabled={stage === 'confirm'}
                />
                <span className="text-text-secondary">
                  {t(
                    'detok.confirmCheckbox',
                    'I understand this action is logged and notifies SecOps.',
                  )}
                </span>
              </label>
            </>
          )}

          {stage === 'confirm' && (
            <div className="rounded-md border border-warn/50 bg-warn/5 px-3 py-2 text-sm text-text-primary">
              <span className="font-medium">{t('detok.areYouSure', 'Are you sure?')}</span>{' '}
              <span className="text-text-secondary">
                This will reveal the plaintext to you and write an audit row visible to
                SecOps.
              </span>
            </div>
          )}

          {stage === 'submitting' && (
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              {t('common.loading', 'Loading…')}
            </div>
          )}

          {stage === 'notfound' && (
            <div className="rounded-md border border-warn/50 bg-warn/5 px-3 py-2 text-sm text-text-primary">
              {t(
                'detok.notFound',
                'Placeholder not found in vault. Token may have expired or belongs to another request.',
              )}
            </div>
          )}

          {stage === 'ratelimited' && (
            <div
              role="alert"
              className="rounded-md border border-warn/50 bg-warn/5 px-3 py-2 text-sm text-text-primary"
            >
              <div className="font-medium">
                {t('detok.rateLimitedTitle', 'Tenant rate limit reached')}
              </div>
              <div className="mt-1 text-text-secondary">
                {t(
                  'detok.rateLimitedBody',
                  'Detokenise requests for this tenant are capped to protect operator workflows from misuse. Retry once the cooldown expires.',
                )}
              </div>
              <div
                className="mt-2 font-mono text-[10.5px] tnum text-warn"
                aria-live="polite"
              >
                {retryAfter > 0
                  ? t('detok.retryIn', `Retry in ${retryAfter}s`, { seconds: retryAfter })
                  : t('detok.retryNow', 'You can retry now.')}
              </div>
            </div>
          )}

          {stage === 'error' && (
            <div className="rounded-md border border-danger/50 bg-danger/5 px-3 py-2 text-sm text-danger">
              {t('detok.error', 'Detokenise request failed. Check the audit log.')}
              {errorMsg && <div className="mt-1 font-mono text-xs">{errorMsg}</div>}
            </div>
          )}

          {stage === 'revealed' && revealed && (
            <div className="rounded-md border-2 border-accent bg-accent/5 px-3 py-3 text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-accent">
                  <Eye className="mr-1 inline-block h-3 w-3 align-[-1px]" aria-hidden />
                  {t('detok.revealedLabel', 'Revealed value')}
                </span>
                <span
                  className="font-mono text-[10.5px] tnum text-text-tertiary"
                  aria-live="off"
                >
                  {t('detok.autoHideHint', `Auto-hide in ${secondsLeft}s`, {
                    seconds: secondsLeft,
                  })}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded border border-border bg-canvas px-2 py-1.5 font-mono text-text-primary">
                  {revealed.value}
                </code>
                <Button variant="secondary" size="sm" onClick={copyRevealed}>
                  <Copy className="h-3 w-3" aria-hidden /> {t('common.copy', 'Copy')}
                </Button>
              </div>
              <div className="mt-2 font-mono text-[10.5px] text-text-tertiary break-all">
                sha256: {revealed.sha256}
              </div>
            </div>
          )}
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="md"
            onClick={() => onOpenChange(false)}
            disabled={stage === 'submitting'}
          >
            {stage === 'revealed'
              ? t('common.close', 'Close')
              : t('detok.cancel', 'Cancel')}
          </Button>
          {stage === 'form' && (
            <Button
              ref={continueBtnRef}
              variant="danger"
              size="md"
              disabled={!justificationValid || !ticketValid || !confirmed}
              onClick={() => setStage('confirm')}
            >
              <Lock className="h-3 w-3" aria-hidden /> {t('detok.continue', 'Continue')}
            </Button>
          )}
          {stage === 'confirm' && (
            <Button
              variant="danger"
              size="md"
              autoFocus
              onClick={() => void submit()}
            >
              <Eye className="h-3 w-3" aria-hidden />{' '}
              {t('detok.finalConfirm', 'Reveal value')}
            </Button>
          )}
          {(stage === 'notfound' || stage === 'error' || stage === 'ratelimited') && (
            <Button
              variant="secondary"
              size="md"
              disabled={stage === 'ratelimited' && retryAfter > 0}
              onClick={() => setStage('form')}
            >
              {t('common.retry', 'Retry')}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
