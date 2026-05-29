'use client';

import { useSession, signOut } from 'next-auth/react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { ExternalLink, LogOut, UserCog, Shield } from 'lucide-react';

const KEYCLOAK_ADMIN_URL =
  process.env.NEXT_PUBLIC_KEYCLOAK_ADMIN_URL ?? 'http://localhost:8081/admin/';
const KEYCLOAK_ACCOUNT_URL =
  process.env.NEXT_PUBLIC_KEYCLOAK_ACCOUNT_URL ??
  'http://localhost:8081/realms/praesidio/account/';

/**
 * Signed-in user block with dropdown — replaces the hardcoded "c.tanner"
 * chip. Wires to the NextAuth session for username + groups; surfaces the
 * Keycloak Admin Console and My Account screens for ops, and a Sign out
 * affordance that destroys the local session cookie.
 */
export function UserMenu() {
  const { data, status } = useSession();

  // Initials for the avatar tile.
  const name =
    (data?.user?.name as string | undefined) ??
    (data?.user?.email as string | undefined) ??
    'guest';
  const initials = name
    .replace(/[^a-zA-Z0-9._-]/g, '')
    .split(/[._\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('') || 'U';
  const primaryGroup = data?.groups?.[0] ?? null;
  const groupLabel = primaryGroup
    ? primaryGroup.replace(/^praesidio-/, '').replace(/s$/, '')
    : 'guest';
  const tenant = data?.tenantId ?? null;
  const isAdmin = data?.groups?.includes('praesidio-admins') ?? false;

  // Unauthenticated → render a tiny "sign in" pointer instead.
  if (status !== 'authenticated' || !data) {
    return (
      <a
        href="/login"
        className="flex items-center gap-2 border-l border-border pl-3 ml-1 font-mono text-[10.5px] tracking-[0.12em] uppercase text-text-tertiary hover:text-text-primary"
      >
        <span
          className="h-6 w-6 bg-surface border border-border text-text-tertiary text-[10px] flex items-center justify-center"
          aria-hidden
        >
          —
        </span>
        Sign in
      </a>
    );
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className="flex items-center gap-2 border-l border-border pl-3 ml-1 hover:bg-surface focus-visible:outline-2 focus-visible:outline-vermillion focus-visible:outline-offset-2 transition-colors"
          aria-label={`Account menu for ${name}`}
        >
          <div
            className="h-6 w-6 bg-text-primary text-canvas font-mono text-[10px] flex items-center justify-center"
            aria-hidden
          >
            {initials}
          </div>
          <div className="hidden lg:flex flex-col leading-tight text-left">
            <span className="font-mono text-[10.5px] text-text-primary">
              {name}
            </span>
            <span className="font-mono text-[9px] tracking-[0.12em] uppercase text-text-tertiary">
              {groupLabel}
            </span>
          </div>
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="z-50 w-[280px] bg-canvas border border-border shadow-none p-0 font-mono text-[11px] tracking-[0.04em] text-text-primary"
        >
          {/* identity card */}
          <div className="px-3.5 py-3 border-b border-border bg-surface">
            <div className="flex items-baseline gap-2">
              <span
                className="font-serif italic text-vermillion text-[15px]"
                aria-hidden
              >
                §
              </span>
              <span className="font-serif italic text-[15px] text-text-primary">
                {name}
              </span>
            </div>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-1 text-[10.5px]">
              <dt className="text-text-tertiary uppercase tracking-[0.14em]">
                Group
              </dt>
              <dd className="m-0 text-text-primary">
                {primaryGroup ?? 'none'}
              </dd>
              {tenant && (
                <>
                  <dt className="text-text-tertiary uppercase tracking-[0.14em]">
                    Tenant
                  </dt>
                  <dd className="m-0 text-text-primary">{tenant}</dd>
                </>
              )}
            </dl>
          </div>

          {/* keycloak links */}
          <div className="py-1">
            <DropdownMenu.Item asChild>
              <a
                href={KEYCLOAK_ACCOUNT_URL}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2.5 px-3.5 py-2 hover:bg-surface focus:bg-surface outline-none text-[11px] uppercase tracking-[0.06em] cursor-pointer"
              >
                <UserCog
                  className="h-3.5 w-3.5 text-text-tertiary"
                  strokeWidth={1.75}
                />
                <span className="flex-1">My Account</span>
                <ExternalLink
                  className="h-3 w-3 text-text-tertiary"
                  strokeWidth={1.75}
                  aria-hidden
                />
              </a>
            </DropdownMenu.Item>

            {isAdmin && (
              <DropdownMenu.Item asChild>
                <a
                  href={KEYCLOAK_ADMIN_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2.5 px-3.5 py-2 hover:bg-surface focus:bg-surface outline-none text-[11px] uppercase tracking-[0.06em] cursor-pointer"
                >
                  <Shield
                    className="h-3.5 w-3.5 text-text-tertiary"
                    strokeWidth={1.75}
                  />
                  <span className="flex-1">Admin Console</span>
                  <ExternalLink
                    className="h-3 w-3 text-text-tertiary"
                    strokeWidth={1.75}
                    aria-hidden
                  />
                </a>
              </DropdownMenu.Item>
            )}
          </div>

          {/* sign out */}
          <DropdownMenu.Separator className="h-px bg-border" />
          <div className="py-1">
            <DropdownMenu.Item asChild>
              <button
                type="button"
                onClick={() => signOut({ callbackUrl: '/login' })}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 hover:bg-surface focus:bg-surface outline-none text-[11px] uppercase tracking-[0.06em] cursor-pointer text-left text-vermillion"
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span>Sign out</span>
              </button>
            </DropdownMenu.Item>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
