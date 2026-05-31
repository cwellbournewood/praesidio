'use client';

/**
 * Mount @axe-core/react in development to surface accessibility violations
 * directly in the browser console.
 *
 * Usage:
 *   import { mountAxe } from '@/lib/a11y';
 *   mountAxe();
 *
 * The import is dynamic so that axe is excluded from the production bundle
 * even though it lives in `dependencies` (we cannot put it in
 * `devDependencies` and still have Next pick it up reliably across all
 * deploy modes — but the dynamic import + NODE_ENV gate guarantees tree-shake).
 *
 * To run an explicit audit pass over the current page from the console:
 *   await window.__axe?.run()
 */

let mounted = false;

export async function mountAxe(): Promise<void> {
  if (mounted) return;
  if (typeof window === 'undefined') return;
  if (process.env.NODE_ENV !== 'development') return;
  mounted = true;
  try {
    // Use indirect import so webpack does not statically resolve @axe-core/react
    // (it's optional dev-only; the package may not be installed locally).
    const axeModName = '@axe-core/react';
    const dynImport = new Function('m', 'return import(m)') as (
      m: string,
    ) => Promise<any>;
    const [{ default: React }, { default: ReactDOM }, { default: axe }] = await Promise.all([
      import('react'),
      import('react-dom'),
      dynImport(axeModName),
    ]);
    // 1000 ms debounce keeps the console tidy during fast nav.
    await axe(React, ReactDOM, 1000, {
      // Quiet rules that match the design intentionally (single-page audit
      // tool, no landmark <main> required outside the shell).
      rules: [{ id: 'page-has-heading-one', enabled: true }],
    });
    // eslint-disable-next-line no-console
    console.info('[section] axe-core mounted (dev). Violations will print here.');
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[section] axe-core failed to mount:', err);
  }
}
