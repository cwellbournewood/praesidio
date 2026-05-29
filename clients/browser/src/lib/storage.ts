/**
 * Thin wrappers around `chrome.storage.sync` / `.local`.
 *
 * - Settings (non-secret) live in `.sync` so they roam across browsers.
 * - Secrets (API key, OIDC tokens) live in `.local`. NEVER `.sync` them.
 * - Decisions (audit log of last N) live in `.local` so they don't
 *   leak to the user's other devices.
 */
import {
  DEFAULT_SETTINGS,
  EMPTY_SECRETS,
  type DecisionRecord,
  type Secrets,
  type Settings,
} from './types.js';

const SETTINGS_KEY = 'praesidio.settings';
const SECRETS_KEY = 'praesidio.secrets';
const DECISIONS_KEY = 'praesidio.decisions';

const MAX_DECISIONS = 10;

/**
 * A minimal contract for `chrome.storage.StorageArea` we use, so unit
 * tests can inject a plain `Map`-backed fake without depending on the
 * full chrome API surface.
 */
export interface StorageArea {
  get(keys: string | string[] | null): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string | string[]): Promise<void>;
}

/**
 * Resolve `chrome.storage.sync` (preferred for settings). Falls back to
 * `.local` if `.sync` is unavailable (e.g. Manifest V3 without sign-in).
 */
export function getSyncArea(): StorageArea {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.sync) {
    return chrome.storage.sync as unknown as StorageArea;
  }
  return getLocalArea();
}

export function getLocalArea(): StorageArea {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    return chrome.storage.local as unknown as StorageArea;
  }
  // Pure in-memory fallback for tests and SSR.
  return makeMemoryArea();
}

export function makeMemoryArea(): StorageArea {
  const data = new Map<string, unknown>();
  return {
    async get(keys) {
      const out: Record<string, unknown> = {};
      if (keys === null) {
        for (const [k, v] of data) out[k] = v;
        return out;
      }
      const arr = Array.isArray(keys) ? keys : [keys];
      for (const k of arr) {
        if (data.has(k)) out[k] = data.get(k);
      }
      return out;
    },
    async set(items) {
      for (const [k, v] of Object.entries(items)) data.set(k, v);
    },
    async remove(keys) {
      const arr = Array.isArray(keys) ? keys : [keys];
      for (const k of arr) data.delete(k);
    },
  };
}

export async function loadSettings(area: StorageArea = getSyncArea()): Promise<Settings> {
  const stored = await area.get(SETTINGS_KEY);
  const raw = stored[SETTINGS_KEY] as Partial<Settings> | undefined;
  if (!raw) return { ...DEFAULT_SETTINGS, sites: { ...DEFAULT_SETTINGS.sites } };
  return {
    ...DEFAULT_SETTINGS,
    ...raw,
    sites: { ...DEFAULT_SETTINGS.sites, ...(raw.sites ?? {}) },
  };
}

/**
 * Persist a partial settings update — caller-supplied `sites` may be a
 * partial map (e.g. `{claude:false}`), the rest is preserved.
 */
export async function saveSettings(
  partial: Partial<Omit<Settings, 'sites'>> & { sites?: Partial<Settings['sites']> },
  area: StorageArea = getSyncArea(),
): Promise<Settings> {
  const current = await loadSettings(area);
  const next: Settings = {
    ...current,
    ...partial,
    sites: { ...current.sites, ...(partial.sites ?? {}) },
  };
  await area.set({ [SETTINGS_KEY]: next });
  return next;
}

export async function loadSecrets(area: StorageArea = getLocalArea()): Promise<Secrets> {
  const stored = await area.get(SECRETS_KEY);
  const raw = stored[SECRETS_KEY] as Partial<Secrets> | undefined;
  if (!raw) return { ...EMPTY_SECRETS };
  return {
    ...EMPTY_SECRETS,
    ...raw,
    oidc: raw.oidc
      ? {
          accessToken: raw.oidc.accessToken ?? null,
          refreshToken: raw.oidc.refreshToken ?? null,
          expiresAt: raw.oidc.expiresAt ?? null,
        }
      : null,
  };
}

export async function saveSecrets(
  partial: Partial<Secrets>,
  area: StorageArea = getLocalArea(),
): Promise<Secrets> {
  const current = await loadSecrets(area);
  const next: Secrets = {
    ...current,
    ...partial,
    oidc: partial.oidc === undefined ? current.oidc : partial.oidc,
  };
  await area.set({ [SECRETS_KEY]: next });
  return next;
}

export async function clearSecrets(area: StorageArea = getLocalArea()): Promise<void> {
  await area.remove(SECRETS_KEY);
}

export async function loadDecisions(area: StorageArea = getLocalArea()): Promise<DecisionRecord[]> {
  const stored = await area.get(DECISIONS_KEY);
  const raw = stored[DECISIONS_KEY];
  if (!Array.isArray(raw)) return [];
  return raw as DecisionRecord[];
}

export async function recordDecision(
  d: DecisionRecord,
  area: StorageArea = getLocalArea(),
): Promise<DecisionRecord[]> {
  const list = await loadDecisions(area);
  // Newest first; cap at MAX_DECISIONS.
  list.unshift(d);
  const trimmed = list.slice(0, MAX_DECISIONS);
  await area.set({ [DECISIONS_KEY]: trimmed });
  return trimmed;
}

export async function clearDecisions(area: StorageArea = getLocalArea()): Promise<void> {
  await area.remove(DECISIONS_KEY);
}

export const _internal = {
  SETTINGS_KEY,
  SECRETS_KEY,
  DECISIONS_KEY,
  MAX_DECISIONS,
};
