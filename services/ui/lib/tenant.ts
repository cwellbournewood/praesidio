'use client';

/**
 * Tenant selection.
 *
 * The currently-selected tenant id is stored in the `praesidio_tenant` cookie
 * so that server components can read it on subsequent navigations (the gateway
 * also accepts it as an `X-Praesidio-Tenant` request header — see lib/api.ts).
 *
 * The list of tenants is fetched from the gateway via `api.tenants()` (which
 * falls back to a deterministic mock list when in mock mode).
 */

import * as React from 'react';
import type { Tenant } from './types';

const COOKIE = 'praesidio_tenant';
const EVENT = 'praesidio:tenant-changed';

export const MOCK_TENANTS: Tenant[] = [
  { id: 'acme', name: 'Acme Corp', env: 'staging', region: 'eu-west-1' },
  { id: 'globex', name: 'Globex GmbH', env: 'prod', region: 'eu-central-1' },
  { id: 'initech', name: 'Initech Ltd', env: 'prod', region: 'us-east-1' },
];

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]!) : null;
}

function writeCookie(name: string, value: string, days = 365) {
  if (typeof document === 'undefined') return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

/** Synchronous reader for non-React modules (lib/api.ts). */
export function currentTenant(): string | null {
  if (typeof window === 'undefined') return null;
  return readCookie(COOKIE);
}

export function setCurrentTenant(id: string): void {
  writeCookie(COOKIE, id);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: id }));
  }
}

interface Ctx {
  tenantId: string | null;
  tenants: Tenant[];
  setTenant: (id: string) => void;
  currentTenant: () => Tenant | undefined;
}

const TenantContext = React.createContext<Ctx | null>(null);

export function TenantProvider({
  children,
  initialTenants = MOCK_TENANTS,
}: {
  children: React.ReactNode;
  initialTenants?: Tenant[];
}) {
  const [tenants, setTenants] = React.useState<Tenant[]>(initialTenants);
  const [tenantId, setTenantId] = React.useState<string | null>(null);

  // Hydrate from cookie once on the client to avoid SSR mismatch.
  React.useEffect(() => {
    const fromCookie = readCookie(COOKIE);
    if (fromCookie) {
      setTenantId(fromCookie);
    } else if (initialTenants[0]) {
      setTenantId(initialTenants[0].id);
      writeCookie(COOKIE, initialTenants[0].id);
    }
  }, [initialTenants]);

  // Fetch the live list (degrades to mock automatically).
  React.useEffect(() => {
    let cancelled = false;
    import('./api').then(({ api }) => {
      api.tenants().then((list) => {
        if (cancelled || !list || list.length === 0) return;
        setTenants(list);
        // If our cookie is stale (refers to a tenant that no longer exists),
        // reset to the first valid one.
        const have = list.some((t) => t.id === readCookie(COOKIE));
        if (!have) {
          setTenantId(list[0]!.id);
          writeCookie(COOKIE, list[0]!.id);
        }
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    function onCustom(e: Event) {
      const id = (e as CustomEvent<string>).detail;
      if (typeof id === 'string') setTenantId(id);
    }
    window.addEventListener(EVENT, onCustom);
    return () => window.removeEventListener(EVENT, onCustom);
  }, []);

  const setTenant = React.useCallback((id: string) => {
    setTenantId(id);
    setCurrentTenant(id);
  }, []);

  const value = React.useMemo<Ctx>(
    () => ({
      tenantId,
      tenants,
      setTenant,
      currentTenant: () => tenants.find((t) => t.id === tenantId),
    }),
    [tenantId, tenants, setTenant],
  );

  return React.createElement(TenantContext.Provider, { value }, children);
}

export function useTenant(): Ctx {
  const ctx = React.useContext(TenantContext);
  if (!ctx) {
    return {
      tenantId: null,
      tenants: MOCK_TENANTS,
      setTenant: setCurrentTenant,
      currentTenant: () => undefined,
    };
  }
  return ctx;
}
