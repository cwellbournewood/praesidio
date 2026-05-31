'use client';

/**
 * Global keyboard shortcuts help modal.
 *
 * Triggered by the `?` key from anywhere in the app (except inside form
 * fields, where `?` is a legal character). Lists the shortcuts the app
 * actually wires up — keep this catalogue in sync with the keydown
 * handlers in CommandPalette.tsx, EventDetail.tsx, LineageGraph.tsx,
 * and any future global handlers.
 *
 * Rendered inside the providers tree so it's available on every route.
 */

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Kbd } from '@/components/ui/kbd';

interface ShortcutGroup {
  heading: string;
  shortcuts: { keys: string[]; label: string }[];
}

const GROUPS: ShortcutGroup[] = [
  {
    heading: 'Global',
    shortcuts: [
      { keys: ['?'], label: 'Open this help dialog' },
      { keys: ['⌘', 'K'], label: 'Open command palette (Ctrl-K on Windows / Linux)' },
      { keys: ['Esc'], label: 'Close dialog / palette / drawer' },
    ],
  },
  {
    heading: 'Navigate',
    shortcuts: [
      { keys: ['G', 'D'], label: 'Dashboard' },
      { keys: ['G', 'E'], label: 'Events' },
      { keys: ['G', 'S'], label: 'Policy simulator' },
      { keys: ['G', 'P'], label: 'Policies' },
      { keys: ['G', 'M'], label: 'Model registry' },
    ],
  },
  {
    heading: 'Within event detail',
    shortcuts: [
      { keys: ['↑'], label: 'Previous finding' },
      { keys: ['↓'], label: 'Next finding' },
      { keys: ['Home'], label: 'First finding' },
      { keys: ['End'], label: 'Last finding' },
      { keys: ['Enter'], label: 'Copy matched snippet to clipboard' },
    ],
  },
  {
    heading: 'Within lineage graph',
    shortcuts: [
      { keys: ['Tab'], label: 'Move focus through nodes' },
      { keys: ['↑', '↓', '←', '→'], label: 'Move between nodes' },
      { keys: ['Enter'], label: 'Select node and copy its id' },
    ],
  },
];

const NAV_PREFIXES = new Set(['G']);

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    el.isContentEditable
  );
}

export function KeyboardShortcuts() {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const navBuf = React.useRef<{ key: string; at: number } | null>(null);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Open help with `?` (Shift-/) unless the operator is typing.
      if (e.key === '?' && !isTypingTarget(e.target)) {
        e.preventDefault();
        setOpen(true);
        return;
      }
      // Two-key navigation chords (G then D/E/S/P/M).
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      const up = e.key.toUpperCase();
      const now = Date.now();
      const prev = navBuf.current;
      if (prev && now - prev.at < 1_200 && NAV_PREFIXES.has(prev.key)) {
        const dest = navTarget(prev.key, up);
        navBuf.current = null;
        if (dest) {
          e.preventDefault();
          router.push(dest);
        }
        return;
      }
      if (NAV_PREFIXES.has(up)) {
        navBuf.current = { key: up, at: now };
      } else {
        navBuf.current = null;
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [router]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent aria-describedby="kbd-help-desc">
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogDescription id="kbd-help-desc">
          Every shortcut wired in the Section console. Press <Kbd>?</Kbd> from
          any page to reopen this dialog.
        </DialogDescription>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          {GROUPS.map((g) => (
            <section key={g.heading}>
              <h4 className="mb-2 text-[10.5px] font-mono uppercase tracking-[0.14em] text-text-tertiary">
                {g.heading}
              </h4>
              <ul className="space-y-1.5">
                {g.shortcuts.map((s, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-text-secondary">{s.label}</span>
                    <span className="flex items-center gap-1 shrink-0">
                      {s.keys.map((k, j) => (
                        <Kbd key={j}>{k}</Kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function navTarget(prefix: string, second: string): string | null {
  if (prefix !== 'G') return null;
  switch (second) {
    case 'D':
      return '/';
    case 'E':
      return '/events';
    case 'S':
      return '/simulator';
    case 'P':
      return '/policies';
    case 'M':
      return '/models';
    default:
      return null;
  }
}

