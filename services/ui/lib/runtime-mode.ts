'use client';

/**
 * Runtime data-source mode.
 *
 * - "live"  : every API call goes to the configured gateway (NEXT_PUBLIC_GATEWAY_URL).
 * - "mock"  : every API call is served from the synthetic dataset in `lib/mock.ts`.
 *
 * Live is the DEFAULT whenever the build was given a gateway URL. The operator
 * can flip to mock at runtime from the Topbar dropdown (useful when the gateway
 * is down or for offline demos); the choice persists in localStorage.
 *
 * SSR-safe: every reader is wrapped so the first paint matches the server.
 */

import * as React from 'react';

export type RuntimeMode = 'live' | 'mock';

const KEY = 'praesidio.runtime-mode';

export function gatewayUrl(): string | null {
  const url = process.env.NEXT_PUBLIC_GATEWAY_URL;
  return url && url.length > 0 ? url : null;
}

/** Initial default: live if a gateway URL was baked into the build, else mock. */
export function defaultMode(): RuntimeMode {
  if (process.env.NEXT_PUBLIC_MOCK === '1') return 'mock';
  return gatewayUrl() ? 'live' : 'mock';
}

function readPersisted(): RuntimeMode | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'live' || v === 'mock' ? v : null;
  } catch {
    return null;
  }
}

function writePersisted(mode: RuntimeMode): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(KEY, mode);
  } catch {
    /* private mode etc. — silent */
  }
}

interface Ctx {
  mode: RuntimeMode;
  setMode: (m: RuntimeMode) => void;
  toggle: () => void;
  gateway: string | null;
}

const RuntimeModeContext = React.createContext<Ctx | null>(null);

const EVENT = 'praesidio:runtime-mode-changed';

/** Imperative reader for non-React modules (lib/api.ts). */
export function currentMode(): RuntimeMode {
  if (typeof window === 'undefined') return defaultMode();
  return readPersisted() ?? defaultMode();
}

export function setCurrentMode(mode: RuntimeMode): void {
  writePersisted(mode);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<RuntimeMode>(EVENT, { detail: mode }));
  }
}

export function RuntimeModeProvider({ children }: { children: React.ReactNode }) {
  // Always render with the SSR-safe default first; hydrate from localStorage
  // in a useEffect so the markup matches the server.
  const [mode, setModeState] = React.useState<RuntimeMode>(defaultMode());

  React.useEffect(() => {
    const persisted = readPersisted();
    if (persisted) setModeState(persisted);
  }, []);

  // Cross-tab + cross-component sync.
  React.useEffect(() => {
    function onCustom(e: Event) {
      const m = (e as CustomEvent<RuntimeMode>).detail;
      if (m === 'live' || m === 'mock') setModeState(m);
    }
    function onStorage(e: StorageEvent) {
      if (e.key === KEY && (e.newValue === 'live' || e.newValue === 'mock')) {
        setModeState(e.newValue);
      }
    }
    window.addEventListener(EVENT, onCustom);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(EVENT, onCustom);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const setMode = React.useCallback((m: RuntimeMode) => {
    setModeState(m);
    setCurrentMode(m);
  }, []);

  const value = React.useMemo<Ctx>(
    () => ({
      mode,
      setMode,
      toggle: () => setMode(mode === 'live' ? 'mock' : 'live'),
      gateway: gatewayUrl(),
    }),
    [mode, setMode],
  );

  return React.createElement(RuntimeModeContext.Provider, { value }, children);
}

export function useRuntimeMode(): Ctx {
  const ctx = React.useContext(RuntimeModeContext);
  if (!ctx) {
    // Permit non-provider consumers (e.g. tests) — return a benign default.
    return {
      mode: defaultMode(),
      setMode: setCurrentMode,
      toggle: () => setCurrentMode(currentMode() === 'live' ? 'mock' : 'live'),
      gateway: gatewayUrl(),
    };
  }
  return ctx;
}
