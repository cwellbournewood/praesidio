'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  Boxes,
  GitBranch,
  ListChecks,
  Rocket,
  Settings,
  ShieldCheck,
  FileSignature,
  Database,
  Webhook,
  Users,
  KeyRound,
  Library,
  ChevronDown,
  Wand2,
  Lightbulb,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type NavItem = {
  href: string;
  label: string;
  icon: typeof Activity;
  exact?: boolean;
  tag?: string;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const SECTIONS: NavSection[] = [
  {
    label: '§ 0 · Begin',
    items: [{ href: '/onboarding', label: 'Onboarding', icon: Rocket, tag: '5 MIN' }],
  },
  {
    label: '§ I · Operate',
    items: [
      { href: '/', label: 'Overview', icon: Activity, exact: true },
      { href: '/events', label: 'Events', icon: ListChecks, tag: 'LIVE' },
      { href: '/simulator', label: 'Simulator', icon: Wand2 },
      { href: '/lineage/demo-req-1', label: 'Lineage', icon: GitBranch },
    ],
  },
  {
    label: '§ II · Govern',
    items: [
      { href: '/policies', label: 'Policies', icon: ShieldCheck },
      { href: '/policies?tab=bundles', label: 'Bundles', icon: FileSignature },
      { href: '/recommendations', label: 'Recommendations', icon: Lightbulb, tag: 'NEW' },
      { href: '/models', label: 'Models', icon: Boxes },
    ],
  },
  {
    label: '§ III · Configure',
    items: [
      { href: '/settings', label: 'Settings', icon: Settings },
      { href: '/settings?tab=vault', label: 'Vault', icon: Database },
      { href: '/settings?tab=connectors', label: 'Connectors', icon: Webhook },
      { href: '/settings?tab=identity', label: 'Identity', icon: Users },
      { href: '/settings?tab=keys', label: 'API Keys', icon: KeyRound },
      { href: '/settings?tab=docs', label: 'Documentation', icon: Library },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (item: NavItem) => {
    const href = item.href.split('?')[0];
    if (item.exact) return pathname === href;
    if (href === '/') return pathname === '/';
    return pathname === href || pathname.startsWith(href + '/');
  };

  return (
    <aside className="hidden md:flex sticky top-0 h-screen w-[228px] shrink-0 flex-col border-r border-border bg-canvas">
      {/* Brand block */}
      <div className="px-4 pt-4 pb-3 border-b border-border">
        <div className="flex items-baseline justify-between">
          <span className="font-serif italic text-[26px] leading-none tracking-tight text-text-primary">
            Section
          </span>
          <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            v0.1
          </span>
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            Control Plane
          </span>
          <span className="leader flex-1 h-[1px]" aria-hidden />
          <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            EU-WEST-1
          </span>
        </div>
      </div>

      {/* Tenant / env switcher */}
      <button
        type="button"
        className="mx-3 mt-3 flex items-center justify-between border border-border bg-surface px-3 h-9 text-left hover:bg-surface-sunken transition-colors"
      >
        <div className="min-w-0">
          <div className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary leading-none">
            Tenant
          </div>
          <div className="font-mono text-[11.5px] text-text-primary leading-tight mt-0.5 truncate">
            acme-corp · staging
          </div>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-text-tertiary shrink-0" strokeWidth={1.75} />
      </button>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto mt-2" aria-label="Primary">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="nav-section">{section.label}</div>
            <ul>
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(item);
                return (
                  <li key={item.href + item.label}>
                    <Link
                      href={item.href}
                      className={cn('nav-item', active && 'active')}
                    >
                      <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                      <span className="flex-1">{item.label}</span>
                      {item.tag && (
                        <span className="font-mono text-[8.5px] tracking-[0.14em] text-accent">
                          {item.tag}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Status footer */}
      <div className="border-t border-border p-3 space-y-1.5">
        <div className="flex items-center justify-between font-mono text-[10px] text-text-tertiary">
          <span className="flex items-center gap-1.5">
            <span className="sig sig-allow pulse" aria-hidden />
            GATEWAY OK
          </span>
          <span className="tnum">42ms</span>
        </div>
        <div className="flex items-center justify-between font-mono text-[10px] text-text-tertiary">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="h-2.5 w-2.5" strokeWidth={2} />
            BUNDLE
          </span>
          <span className="tnum">9c4f…b71e</span>
        </div>
        <div className="flex items-center justify-between font-mono text-[10px] text-text-tertiary">
          <span>BUILD</span>
          <span className="tnum">v0.1.0 · staging</span>
        </div>
      </div>
    </aside>
  );
}
