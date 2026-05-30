'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

/**
 * Ambient instrument elements for the login page.
 *
 * - <DecisionTicker/>  : a thin marquee of synthetic decision marks
 *                       (allow/transform/block sig-squares + a label)
 *                       so the page feels like a live system, not a
 *                       static form.
 * - <ScanLine/>         : a vermillion 1px line that sweeps the card
 *                       every 6s, evoking an instrument's scan cycle.
 * - <SignalSpark/>      : a tiny inline area-spark drawn with monospace
 *                       blocks (no SVG) showing simulated throughput.
 *
 * All elements are presentational only — no real data, no fetches.
 * They establish the "alive" mood; the actual liveness arrives once
 * the operator signs in.
 */

const DECISION_LABELS: Array<{ kind: 'allow' | 'warn' | 'block'; label: string }> = [
  { kind: 'allow', label: 'PII · transform' },
  { kind: 'allow', label: 'IBAN · transform' },
  { kind: 'block', label: 'AWS_KEY · block' },
  { kind: 'allow', label: 'EMAIL · allow' },
  { kind: 'warn', label: 'PROMPT_INJ · review' },
  { kind: 'allow', label: 'JWT · transform' },
  { kind: 'allow', label: 'PERSON · transform' },
  { kind: 'block', label: 'SECRET · block' },
  { kind: 'allow', label: 'PHONE · transform' },
  { kind: 'allow', label: 'ADDRESS · transform' },
  { kind: 'warn', label: 'TOOL_CALL · review' },
  { kind: 'allow', label: 'GPT-4o · ok' },
];

const KIND_CLASS: Record<'allow' | 'warn' | 'block', string> = {
  allow: 'bg-moss',
  warn: 'bg-sienna',
  block: 'bg-vermillion',
};

export function DecisionTicker() {
  // We duplicate so the marquee loops seamlessly.
  const items = useMemo(() => [...DECISION_LABELS, ...DECISION_LABELS], []);
  return (
    <div
      className="overflow-hidden border-y border-border bg-canvas/60 backdrop-blur-[1px]"
      role="presentation"
      aria-hidden
    >
      <div className="ticker-track flex items-center gap-8 py-2 whitespace-nowrap will-change-transform">
        {items.map((d, i) => (
          <span
            key={i}
            className="flex items-center gap-2 font-mono text-[10.5px] tracking-[0.06em] uppercase text-text-tertiary"
          >
            <span
              className={`inline-block h-[7px] w-[7px] ${KIND_CLASS[d.kind]}`}
            />
            <span>{d.label}</span>
            <span className="text-border">/</span>
          </span>
        ))}
      </div>
      <style jsx>{`
        .ticker-track {
          animation: ticker 60s linear infinite;
        }
        @keyframes ticker {
          from {
            transform: translateX(0);
          }
          to {
            transform: translateX(-50%);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .ticker-track {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

export function ScanLine() {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden
    >
      <div className="scan-line absolute left-0 top-0 h-px w-full bg-vermillion/70" />
      <style jsx>{`
        .scan-line {
          animation: scan 7s ease-in-out infinite;
          opacity: 0;
        }
        @keyframes scan {
          0% {
            transform: translateY(0);
            opacity: 0;
          }
          10% {
            opacity: 0.55;
          }
          90% {
            opacity: 0.55;
          }
          100% {
            transform: translateY(100%);
            opacity: 0;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .scan-line {
            display: none;
          }
        }
      `}</style>
    </div>
  );
}

/**
 * A 24-cell pseudo-random spark drawn with monospace blocks.
 * The block heights pulse subtly over time so it reads "alive."
 */
export function SignalSpark({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 1200);
    return () => window.clearInterval(id);
  }, []);

  // Deterministic base shape (so SSR matches CSR) with a small drift
  // driven by `tick`.
  const cells = useMemo(() => {
    const base = [3, 5, 4, 6, 7, 5, 4, 3, 5, 6, 8, 7, 5, 4, 6, 7, 6, 4, 3, 5, 6, 7, 5, 4];
    return base.map((b, i) => {
      const drift = ((tick + i) % 5) - 2; // -2..+2
      const h = Math.max(2, Math.min(9, b + drift));
      return h;
    });
  }, [tick]);

  return (
    <div
      ref={ref}
      className={`inline-flex items-end gap-[2px] h-[24px] ${className}`}
      role="img"
      aria-label="Synthetic throughput indicator"
    >
      {cells.map((h, i) => (
        <span
          key={i}
          className="w-[3px] bg-text-primary/85"
          style={{ height: `${h * 2}px` }}
        />
      ))}
    </div>
  );
}

/**
 * Live-looking UTC clock with seconds, so the page doesn't feel static.
 * Hydrates with a placeholder so SSR matches.
 */
export function LiveClock({ className = '' }: { className?: string }) {
  const [now, setNow] = useState<string>('—');
  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString('en-GB', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          timeZone: 'UTC',
        }) + 'Z',
      );
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <span className={className} suppressHydrationWarning>
      {now}
    </span>
  );
}
