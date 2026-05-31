/**
 * Tiny i18n shim for the popup. Mirrors the JSON shape we ship in
 * `src/locales/{en,es}.json`. No flow-control libraries — we just look
 * up a key and substitute `{{var}}` placeholders.
 *
 * For Chrome's `_locales/<lang>/messages.json` (manifest-level strings
 * like the action title and extension name), the platform handles
 * lookup for us — we ship that file separately and don't touch it from
 * code.
 */
import en from '../locales/en.json' assert { type: 'json' };
import es from '../locales/es.json' assert { type: 'json' };

type Catalog = Record<string, string>;

const CATALOGS: Record<string, Catalog> = {
  en: en as Catalog,
  es: es as Catalog,
};

export function pickLocale(override: 'en' | 'es' | null): 'en' | 'es' {
  if (override) return override;
  if (typeof chrome !== 'undefined' && chrome.i18n) {
    const ui = chrome.i18n.getUILanguage().toLowerCase();
    if (ui.startsWith('es')) return 'es';
  }
  return 'en';
}

export function t(
  locale: 'en' | 'es',
  key: string,
  vars: Record<string, string | number> = {},
): string {
  const cat = CATALOGS[locale] ?? CATALOGS.en!;
  let s = cat[key] ?? CATALOGS.en![key] ?? key;
  for (const [k, v] of Object.entries(vars)) {
    s = s.replaceAll(`{{${k}}}`, String(v));
  }
  return s;
}

export type Translate = (
  key: string,
  vars?: Record<string, string | number>,
) => string;

export function makeT(locale: 'en' | 'es'): Translate {
  return (key, vars = {}) => t(locale, key, vars);
}
