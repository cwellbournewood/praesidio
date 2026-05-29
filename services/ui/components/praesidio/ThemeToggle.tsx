'use client';

import * as React from 'react';
import { useTheme } from 'next-themes';
import { Moon, Sun, Contrast } from 'lucide-react';
import { cn } from '@/lib/utils';

const ORDER = ['light', 'dark', 'high-contrast'] as const;
type Theme = (typeof ORDER)[number];

const LABELS: Record<Theme, string> = {
  light: 'Light',
  dark: 'Dark',
  'high-contrast': 'High contrast',
};

/**
 * Tri-state theme toggle: light → dark → high-contrast → light.
 *
 * Keyboard: Tab focus, Enter|Space cycles to the next theme.
 * Announces the new value via the button's `aria-label`.
 */
export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const active = (theme as Theme) ?? (resolvedTheme as Theme) ?? 'light';
  const idx = ORDER.indexOf(active);
  const next = ORDER[(idx + 1 + ORDER.length) % ORDER.length]!;

  const Icon =
    active === 'dark' ? Sun : active === 'high-contrast' ? Moon : Contrast;

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${LABELS[active]}. Press to switch to ${LABELS[next]}.`}
      title={mounted ? `${LABELS[active]} → ${LABELS[next]}` : 'Theme'}
      className={cn(
        'h-7 w-7 flex items-center justify-center border border-border bg-canvas',
        'hover:bg-surface-sunken transition-colors',
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
    </button>
  );
}
