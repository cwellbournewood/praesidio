'use client';

import * as React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { ChevronDown, Database, FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRuntimeMode, type RuntimeMode } from '@/lib/runtime-mode';

/**
 * Topbar dropdown to flip the UI between live gateway data and the bundled
 * mock dataset, without redeploy. Selection persists in localStorage.
 *
 * Keyboard:
 *   Tab          → focus trigger
 *   Enter|Space  → open
 *   ↑ ↓          → move between options
 *   Enter        → choose + close
 *   Esc          → close
 */
export function ModeToggle() {
  const { mode, setMode, gateway } = useRuntimeMode();
  const [open, setOpen] = React.useState(false);
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const options: Array<{ id: RuntimeMode; title: string; detail: string }> = [
    {
      id: 'live',
      title: 'Live gateway',
      detail: gateway ?? 'NEXT_PUBLIC_GATEWAY_URL is unset',
    },
    {
      id: 'mock',
      title: 'Mock data',
      detail: 'Synthetic demo dataset — no network',
    },
  ];

  // Stable SSR rendering — choose the build-default label until hydration.
  const label = mounted ? (mode === 'live' ? 'LIVE' : 'MOCK') : 'LIVE';

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`Data source: ${label.toLowerCase()}. Open switcher.`}
          className="chip inline-flex items-center gap-1.5 h-7 px-2"
        >
          {mounted && mode === 'mock' ? (
            <FlaskConical className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          ) : (
            <Database className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          )}
          <span suppressHydrationWarning>{label}</span>
          <ChevronDown className="h-3 w-3 opacity-70" strokeWidth={1.75} aria-hidden />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="z-50 w-72 border border-border bg-canvas animate-slide-in-up"
        >
          <div className="border-b border-border px-3 py-2 font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            Data source
          </div>
          <ul role="listbox" aria-label="Data source" className="py-1">
            {options.map((opt) => {
              const active = mounted && opt.id === mode;
              const disabled = opt.id === 'live' && !gateway;
              return (
                <li key={opt.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    aria-disabled={disabled || undefined}
                    onClick={() => {
                      if (disabled) return;
                      setMode(opt.id);
                      setOpen(false);
                    }}
                    className={cn(
                      'flex w-full items-start gap-2 px-3 py-2 text-left text-[12px] font-mono',
                      'hover:bg-surface-sunken focus:bg-surface-sunken focus:outline-none',
                      disabled && 'opacity-50 cursor-not-allowed',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 inline-block h-2 w-2',
                        active ? 'bg-accent' : 'bg-border',
                      )}
                      aria-hidden
                    />
                    <span className="flex-1 min-w-0">
                      <span className="block text-text-primary">{opt.title}</span>
                      <span className="block text-[10px] text-text-tertiary truncate">
                        {opt.detail}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
