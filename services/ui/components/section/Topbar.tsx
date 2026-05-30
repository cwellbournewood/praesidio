'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Search, ChevronRight } from 'lucide-react';
import { useCommandPalette } from './CommandPalette';
import { TenantSwitcher } from './TenantSwitcher';
import { ThemeToggle } from './ThemeToggle';
import { ModeToggle } from './ModeToggle';
import { UserMenu } from './UserMenu';

const PATH_LABELS: Record<string, string> = {
  '': 'Overview',
  events: 'Events',
  policies: 'Policies',
  simulator: 'Simulator',
  lineage: 'Lineage',
  models: 'Models',
  settings: 'Settings',
};

function useNowUtc() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const i = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(i);
  }, []);
  return now;
}

function fmtUtc(d: Date | null) {
  if (!d) return '—';
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}Z`;
}

export function Topbar() {
  const palette = useCommandPalette();
  const pathname = usePathname();
  const now = useNowUtc();

  const segments = pathname.split('/').filter(Boolean);
  const crumbs =
    segments.length === 0
      ? [{ label: 'Overview', href: '/' }]
      : segments.map((seg, i) => ({
          label: PATH_LABELS[seg] ?? seg,
          href: '/' + segments.slice(0, i + 1).join('/'),
        }));

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-canvas">
      <div className="flex h-11 items-center gap-3 px-5">
        {/* Breadcrumb */}
        <nav
          className="flex items-center gap-1.5 font-mono text-[11px] text-text-secondary"
          aria-label="Breadcrumb"
        >
          <span className="text-text-tertiary tracking-[0.14em] uppercase text-[9.5px]" aria-hidden>
            §
          </span>
          {crumbs.map((c, i) => (
            <span key={c.href} className="flex items-center gap-1.5">
              {i > 0 && (
                <ChevronRight
                  className="h-3 w-3 text-text-tertiary"
                  strokeWidth={1.5}
                  aria-hidden
                />
              )}
              <span
                className={
                  i === crumbs.length - 1 ? 'text-text-primary' : 'text-text-tertiary'
                }
                aria-current={i === crumbs.length - 1 ? 'page' : undefined}
              >
                {c.label}
              </span>
            </span>
          ))}
        </nav>

        {/* Search */}
        <button
          onClick={() => palette.open()}
          className="ml-3 flex h-7 w-72 items-center gap-2 border border-border bg-surface px-2.5 text-[12px] text-text-tertiary font-mono hover:border-border-strong transition-colors"
          aria-label="Open command palette"
        >
          <Search className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          <span className="flex-1 text-left truncate">
            search events · ids · policies…
          </span>
          <span className="kbd" aria-hidden>⌘K</span>
        </button>

        {/* Right cluster */}
        <div className="ml-auto flex items-center gap-2">
          {/* Range chip */}
          <span className="chip" aria-label="Time range: last 24 hours">
            <span className="text-text-tertiary" aria-hidden>RANGE</span>
            <span className="text-text-primary">last 24h</span>
          </span>

          {/* Data-source toggle (live / mock) */}
          <ModeToggle />

          {/* Tenant switcher */}
          <TenantSwitcher />

          {/* Clock */}
          <span className="chip tnum" title="UTC clock" aria-label="UTC clock">
            <span className="text-text-tertiary" aria-hidden>UTC</span>
            <span suppressHydrationWarning>{fmtUtc(now)}</span>
          </span>

          {/* Theme toggle (light/dark/high-contrast) */}
          <ThemeToggle />

          {/* User — dropdown with Keycloak account / admin links + sign out */}
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
