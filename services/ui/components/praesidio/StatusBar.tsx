'use client';

import { useEffect, useState } from 'react';
import { useRuntimeMode } from '@/lib/runtime-mode';

const STREAM = [
  { sig: 'allow' as const, text: 'req_8f3c · gpt-4o · 142 tokens' },
  { sig: 'warn' as const, text: 'req_8f3d · claude-3.5 · PII flagged' },
  { sig: 'allow' as const, text: 'req_8f3e · llama-3.1 · 88 tokens' },
  { sig: 'allow' as const, text: 'req_8f3f · gpt-4o · 312 tokens' },
  { sig: 'block' as const, text: 'req_8f40 · gpt-4o · SSN literal' },
  { sig: 'allow' as const, text: 'req_8f41 · gemini-1.5 · 41 tokens' },
];

/**
 * Footer status strip. Renders:
 *  - A live tail of the most recent decisions (synthetic ticker).
 *  - The current data-source badge: "LIVE · <url>" or "MOCK · demo data".
 *  - Keyboard hints + build marker.
 *
 * Keyboard: nothing focusable here — purely informational. The mode chip is
 * announced via `aria-label`.
 */
export function StatusBar() {
  const { mode, gateway } = useRuntimeMode();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setTick((t) => (t + 1) % STREAM.length), 2400);
    return () => clearInterval(i);
  }, []);
  const current = STREAM[tick];

  // Render a stable string on the server (no mode info), then enrich after
  // hydration. Prevents text-content mismatch when the operator has chosen a
  // different mode than the build default.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const modeLabel = mode === 'live' ? 'LIVE' : 'MOCK';
  const modeDetail =
    mode === 'live' ? gateway ?? 'gateway' : 'demo data';

  return (
    <footer className="border-t border-border bg-canvas h-7 px-4 flex items-center gap-4 font-mono text-[10.5px] text-text-tertiary">
      {/* Live tail */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <span
          className="font-mono text-[9px] tracking-[0.14em] uppercase text-text-tertiary"
          aria-hidden
        >
          TAIL
        </span>
        <span className="flex items-center gap-1.5 min-w-0">
          <span className={`sig sig-${current.sig}`} aria-hidden />
          <span className="text-text-primary truncate">{current.text}</span>
        </span>
        <span className="cursor-blink" aria-hidden />
      </div>

      {/* Mode badge (live / mock) */}
      <div
        className="shrink-0"
        suppressHydrationWarning
        aria-label={
          mounted
            ? `Data source: ${modeLabel.toLowerCase()} (${modeDetail})`
            : 'Data source'
        }
      >
        <span
          className={
            mode === 'live'
              ? 'chip chip-active inline-flex items-center gap-1.5'
              : 'chip inline-flex items-center gap-1.5 border-warn text-warn'
          }
        >
          <span
            className={mode === 'live' ? 'sig sig-allow pulse' : 'sig sig-warn'}
            aria-hidden
          />
          <span className="tracking-[0.12em]">{mounted ? modeLabel : 'LIVE'}</span>
          <span
            className={mode === 'live' ? 'text-canvas/80' : 'text-text-tertiary'}
            title={modeDetail}
          >
            · {mounted ? modeDetail : '—'}
          </span>
        </span>
      </div>

      {/* Kbd hints */}
      <div className="hidden md:flex items-center gap-3 shrink-0">
        <span className="flex items-center gap-1.5">
          <span className="kbd">⌘K</span>
          <span>command</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="kbd">G</span>
          <span className="kbd">E</span>
          <span>events</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="kbd">G</span>
          <span className="kbd">P</span>
          <span>policies</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="kbd">?</span>
          <span>help</span>
        </span>
      </div>

      {/* Build / region marker */}
      <div className="flex items-center gap-3 shrink-0 border-l border-border pl-4">
        <span className="tnum">eu-west-1</span>
        <span>·</span>
        <span className="tnum">build 9c4f…b71e</span>
      </div>
    </footer>
  );
}
