import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { formatDistanceToNowStrict } from 'date-fns';
import type { Decision, DetectorLabel, LabelFamily } from './types';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatMs(ms: number): string {
  if (ms < 1) return '<1 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatPct(n: number, fractionDigits = 1): string {
  return `${n.toFixed(fractionDigits)}%`;
}

export function formatInt(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

export function ago(iso: string): string {
  try {
    return `${formatDistanceToNowStrict(new Date(iso))} ago`;
  } catch {
    return iso;
  }
}

export function shortId(id: string, len = 8): string {
  return id.replace(/-/g, '').slice(0, len);
}

// Map a wire label to its category. Categories are the first
// dot-segment of the canonical label (`pii.organization` → `pii`).
// Unknown labels fall through to `other` so legacy or one-off labels
// render with a neutral palette rather than crashing the chip.
export function labelFamily(label: DetectorLabel): LabelFamily {
  const dot = label.indexOf('.');
  const category = dot === -1 ? label : label.slice(0, dot);
  switch (category) {
    case 'pii':
    case 'financial':
    case 'healthcare':
    case 'credential':
    case 'network':
    case 'code':
    case 'infra':
    case 'behavior':
      return category;
    default:
      return 'other';
  }
}

export function familyClasses(family: LabelFamily): { dot: string; chip: string } {
  switch (family) {
    case 'pii':
      return { dot: 'bg-info', chip: 'bg-canvas text-info border-info' };
    case 'credential':
      return { dot: 'bg-danger', chip: 'bg-canvas text-danger border-danger' };
    case 'financial':
      return { dot: 'bg-warn', chip: 'bg-canvas text-warn border-warn' };
    case 'healthcare':
      // Healthcare gets the warn palette — regulated PHI, treat as
      // visually warm without going as hot as credential leakage.
      return { dot: 'bg-warn', chip: 'bg-canvas text-warn border-warn' };
    case 'behavior':
      // Behavioural signals (prompt injection, classifier) → accent
      // palette: this is the "model is being manipulated" signal.
      return { dot: 'bg-accent', chip: 'bg-canvas text-accent border-accent' };
    case 'code':
      return {
        dot: 'bg-text-secondary',
        chip: 'bg-canvas text-text-secondary border-border',
      };
    case 'network':
    case 'infra':
      return {
        dot: 'bg-text-tertiary',
        chip: 'bg-canvas text-text-tertiary border-border',
      };
    default:
      return {
        dot: 'bg-text-tertiary',
        chip: 'bg-canvas text-text-tertiary border-border',
      };
  }
}

export function decisionGlyph(d: Decision): string {
  // Single 7px square mapped to status; the renderer uses .sig-* classes
  switch (d) {
    case 'allow':
      return '■';
    case 'transform':
      return '■';
    case 'block':
      return '■';
    case 'error':
      return '▲';
    case 'simulate':
      return '◇';
  }
}

export function decisionSigClass(d: Decision): string {
  switch (d) {
    case 'allow':
      return 'sig-allow';
    case 'transform':
      return 'sig-warn';
    case 'block':
      return 'sig-block';
    case 'error':
      return 'sig-block';
    case 'simulate':
      return 'sig-idle';
  }
}

export function decisionLabel(d: Decision): string {
  switch (d) {
    case 'allow':
      return 'Allowed';
    case 'transform':
      return 'Transformed';
    case 'block':
      return 'Blocked';
    case 'error':
      return 'Error';
    case 'simulate':
      return 'Simulated';
  }
}

export function decisionClasses(d: Decision): { fg: string; bg: string; border: string } {
  switch (d) {
    case 'allow':
      return { fg: 'text-success', bg: 'bg-canvas', border: 'border-success' };
    case 'transform':
      return { fg: 'text-warn', bg: 'bg-canvas', border: 'border-warn' };
    case 'block':
      return { fg: 'text-canvas', bg: 'bg-accent', border: 'border-accent' };
    case 'error':
      return { fg: 'text-canvas', bg: 'bg-danger', border: 'border-danger' };
    case 'simulate':
      return { fg: 'text-text-secondary', bg: 'bg-canvas', border: 'border-border' };
  }
}

export function uniq<T>(xs: T[]): T[] {
  return Array.from(new Set(xs));
}

export function pick<T, K extends keyof T>(obj: T, keys: K[]): Pick<T, K> {
  const out = {} as Pick<T, K>;
  for (const k of keys) out[k] = obj[k];
  return out;
}
