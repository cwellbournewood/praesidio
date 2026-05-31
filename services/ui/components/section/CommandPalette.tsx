'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Activity, Boxes, GitBranch, ListChecks, Settings, ShieldCheck, Wand2 } from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Kbd } from '@/components/ui/kbd';
import type { AuditEvent } from '@/lib/types';
import { swrFetcher } from '@/lib/api';
import useSWR from 'swr';
import { shortId } from '@/lib/utils';

interface PaletteCtx {
  open: () => void;
  close: () => void;
}

const Ctx = React.createContext<PaletteCtx | null>(null);

/**
 * Command palette.
 *
 * Keyboard flow (provided by cmdk + Radix Dialog):
 *   ⌘K / Ctrl-K  → toggle open
 *   Type         → fuzzy filter, debounced result count announced via aria-live
 *   ↑ ↓          → move highlight
 *   Enter        → invoke highlighted command (navigate to route)
 *   Esc          → close + restore focus to previously-active element
 *
 * The result-count announcer (`role="status" aria-live="polite"`) sits inside
 * the dialog so screen readers learn how many matches the current query has,
 * after a short settle window.
 */
export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const [announce, setAnnounce] = React.useState('');
  const router = useRouter();
  const { data: events } = useSWR<AuditEvent[]>(isOpen ? '/admin/events' : null, swrFetcher);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((x) => !x);
      }
      if (e.key === 'Escape' && isOpen) setOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  // Debounce-announce visible items. `data-cmdk-list-sizer` is cmdk's hook
  // we can read from; failing that, we count rendered [cmdk-item] elements.
  const listRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!isOpen) return;
    const t = window.setTimeout(() => {
      const root = listRef.current;
      if (!root) return;
      const visible = root.querySelectorAll('[cmdk-item]:not([data-disabled="true"])').length;
      setAnnounce(`${visible} ${visible === 1 ? 'result' : 'results'}`);
    }, 180);
    return () => window.clearTimeout(t);
  }, [query, events, isOpen]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <Ctx.Provider value={{ open: () => setOpen(true), close: () => setOpen(false) }}>
      {children}
      <CommandDialog open={isOpen} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Type a command, principal, request id…"
          value={query}
          onValueChange={setQuery}
          aria-label="Command palette query"
        />
        {/* Result-count announcer — polite so it doesn't fight the input. */}
        <div role="status" aria-live="polite" className="sr-skip">
          {announce}
        </div>
        <div ref={listRef}>
          <CommandList>
            <CommandEmpty>No matches.</CommandEmpty>
            <CommandGroup heading="Navigate">
              <CommandItem onSelect={() => go('/')}>
                <Activity className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Dashboard</span>
                <Kbd className="ml-auto">G D</Kbd>
              </CommandItem>
              <CommandItem onSelect={() => go('/events')}>
                <ListChecks className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Events</span>
                <Kbd className="ml-auto">G E</Kbd>
              </CommandItem>
              <CommandItem onSelect={() => go('/simulator')}>
                <Wand2 className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Policy simulator</span>
                <Kbd className="ml-auto">G S</Kbd>
              </CommandItem>
              <CommandItem onSelect={() => go('/policies')}>
                <ShieldCheck className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Policies</span>
                <Kbd className="ml-auto">G P</Kbd>
              </CommandItem>
              <CommandItem onSelect={() => go('/models')}>
                <Boxes className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Model registry</span>
                <Kbd className="ml-auto">G M</Kbd>
              </CommandItem>
              <CommandItem onSelect={() => go('/lineage/demo-req-1')}>
                <GitBranch className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Lineage (sample request)</span>
              </CommandItem>
              <CommandItem onSelect={() => go('/settings')}>
                <Settings className="h-4 w-4 text-text-tertiary" aria-hidden />
                <span>Settings</span>
              </CommandItem>
            </CommandGroup>
            {events && events.length > 0 && (
              <CommandGroup heading="Recent events">
                {events.slice(0, 8).map((e) => (
                  <CommandItem
                    key={e.id}
                    value={`${e.id} ${e.principal.email} ${e.upstream}`}
                    onSelect={() => go(`/events?id=${e.id}`)}
                  >
                    <span className="font-mono text-xs text-text-tertiary">{shortId(e.id)}</span>
                    <span className="truncate">{e.principal.email}</span>
                    <span className="ml-auto truncate font-mono text-xs text-text-tertiary">
                      {e.upstream}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </div>
      </CommandDialog>
    </Ctx.Provider>
  );
}

export function useCommandPalette() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error('useCommandPalette must be used within CommandPaletteProvider');
  return ctx;
}
