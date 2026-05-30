'use client';

import * as React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Check, ChevronDown, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTenant } from '@/lib/tenant';

/**
 * Topbar tenant switcher.
 *
 * Keyboard flow:
 *   Tab          → focus the trigger button
 *   Enter|Space  → open the popover (focus trapped by Radix)
 *   ↑ ↓          → move between tenants (managed via `roving tabindex`)
 *   Enter        → select current tenant + close
 *   Esc          → close, restore focus to trigger
 *
 * The selection is written to the `section_tenant` cookie and propagated to
 * every gateway call as `X-Section-Tenant`.
 */
export function TenantSwitcher() {
  const { tenantId, tenants, setTenant, currentTenant } = useTenant();
  const [open, setOpen] = React.useState(false);
  const listRef = React.useRef<HTMLUListElement>(null);
  const current = currentTenant();

  // Move focus to the currently-selected item when the popover opens.
  React.useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      const list = listRef.current;
      if (!list) return;
      const items = Array.from(list.querySelectorAll<HTMLButtonElement>('[data-tenant-item]'));
      const idx = items.findIndex((b) => b.dataset.id === tenantId);
      (items[Math.max(idx, 0)] ?? items[0])?.focus();
    }, 20);
    return () => window.clearTimeout(t);
  }, [open, tenantId]);

  function handleKey(e: React.KeyboardEvent<HTMLUListElement>) {
    const items = Array.from(
      e.currentTarget.querySelectorAll<HTMLButtonElement>('[data-tenant-item]'),
    );
    const idx = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      items[(idx + 1) % items.length]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      items[(idx - 1 + items.length) % items.length]?.focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      items[items.length - 1]?.focus();
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`Tenant: ${current?.name ?? tenantId ?? 'none selected'}. Open switcher.`}
          className="chip chip-active inline-flex items-center gap-1.5 h-7 px-2"
        >
          <Building2 className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          <span className="truncate max-w-[120px]">
            {current?.name ?? tenantId ?? 'select tenant'}
          </span>
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
            Switch tenant
          </div>
          <ul
            ref={listRef}
            role="listbox"
            aria-label="Tenants"
            onKeyDown={handleKey}
            className="max-h-72 overflow-y-auto py-1"
          >
            {tenants.length === 0 && (
              <li className="px-3 py-2 text-xs text-text-tertiary">No tenants available.</li>
            )}
            {tenants.map((t) => {
              const active = t.id === tenantId;
              return (
                <li key={t.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    data-tenant-item
                    data-id={t.id}
                    onClick={() => {
                      setTenant(t.id);
                      setOpen(false);
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] font-mono',
                      'hover:bg-surface-sunken focus:bg-surface-sunken focus:outline-none',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-flex h-4 w-4 items-center justify-center border',
                        active
                          ? 'bg-text-primary text-canvas border-text-primary'
                          : 'border-border text-transparent',
                      )}
                      aria-hidden
                    >
                      <Check className="h-3 w-3" strokeWidth={2.5} />
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="block text-text-primary truncate">{t.name}</span>
                      <span className="block text-[10px] text-text-tertiary truncate">
                        {t.id}
                        {t.env ? ` · ${t.env}` : ''}
                        {t.region ? ` · ${t.region}` : ''}
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
