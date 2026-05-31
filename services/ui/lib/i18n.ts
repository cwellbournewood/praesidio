/**
 * Lightweight i18n hook.
 *
 * A full ICU runtime is overkill for the Section admin console — the
 * surface area is mostly nouns and short verbs, and our operators are
 * native English speakers. We ship a zero-dependency dictionary lookup
 * with `{placeholder}` interpolation and a hidden `?lang=` query toggle
 * so the wiring is proven and a second locale (Spanish) is exercised on
 * every build.
 *
 * Add a locale by:
 *   1. Drop `locales/<lang>.json` next to `en.json`.
 *   2. Import it below and add it to `LOCALES`.
 *   3. Optionally surface a control to set the cookie / query param.
 *
 * The hook is safe to call from server components — it falls back to
 * English when no client query is available.
 */
'use client';

import { useSearchParams } from 'next/navigation';
import en from '@/locales/en.json';
import es from '@/locales/es.json';

type Dict = Record<string, string>;

const LOCALES: Record<string, Dict> = {
  en: en as Dict,
  es: es as Dict,
};

export type LocaleKey = keyof typeof LOCALES;
export const SUPPORTED_LOCALES: LocaleKey[] = Object.keys(LOCALES) as LocaleKey[];

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
}

/**
 * Returns a translate function. Falls back to the supplied default text
 * (or the key itself) when a translation is missing, so missing keys
 * never render as empty strings or `[]`.
 */
export function useT() {
  // useSearchParams returns null during SSR for client components; that's
  // fine — we default to English. The Suspense boundary belongs to the
  // route, not to this hook.
  let lang: LocaleKey = 'en';
  try {
    const sp = useSearchParams();
    const q = sp?.get('lang');
    if (q && q in LOCALES) lang = q as LocaleKey;
  } catch {
    // SSR / no Suspense — fine, stick with English.
  }
  const dict = LOCALES[lang] ?? LOCALES.en;

  return function t(
    key: string,
    fallback?: string,
    vars?: Record<string, string | number>,
  ): string {
    const tmpl = dict[key] ?? LOCALES.en[key] ?? fallback ?? key;
    return interpolate(tmpl, vars);
  };
}

/** Server-safe variant for components that can't use the hook. */
export function tStatic(
  key: string,
  fallback?: string,
  lang: LocaleKey = 'en',
  vars?: Record<string, string | number>,
): string {
  const dict = LOCALES[lang] ?? LOCALES.en;
  const tmpl = dict[key] ?? LOCALES.en[key] ?? fallback ?? key;
  return interpolate(tmpl, vars);
}
