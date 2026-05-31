/**
 * Vitest setup — happy-dom-backed globals + a minimal `chrome` shim
 * that just throws if anything touches it. Tests that need a chrome
 * surface install their own fakes.
 */
import { vi } from 'vitest';

// Provide an empty `chrome` so type-checked imports don't blow up.
// Individual tests can replace this with a richer mock.
(globalThis as Record<string, unknown>).chrome = {
  runtime: {
    sendMessage: () => Promise.reject(new Error('not implemented in test')),
    onMessage: { addListener: () => undefined, removeListener: () => undefined },
    getURL: (p: string) => `chrome-extension://test/${p}`,
    lastError: undefined,
  },
  storage: {},
  alarms: {
    create: () => undefined,
    onAlarm: { addListener: () => undefined },
  },
  i18n: { getUILanguage: () => 'en-US' },
  tabs: { create: () => Promise.resolve() },
  action: {},
};

// happy-dom doesn't define `crypto.subtle`/`getRandomValues` by default in
// every release — patch a tiny shim if missing.
if (!('crypto' in globalThis) || !globalThis.crypto.getRandomValues) {
  Object.defineProperty(globalThis, 'crypto', {
    value: {
      getRandomValues<T extends ArrayBufferView | null>(arr: T): T {
        if (!arr) return arr;
        const view = new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength);
        for (let i = 0; i < view.length; i += 1) view[i] = Math.floor(Math.random() * 256);
        return arr;
      },
    },
    configurable: true,
    writable: true,
  });
}

// Silence noisy console in tests unless DEBUG=1.
if (!process.env.DEBUG) {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
}
