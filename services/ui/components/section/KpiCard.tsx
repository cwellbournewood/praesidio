import * as React from 'react';
import { cn } from '@/lib/utils';
import { MetricSpark } from './MetricSpark';

export interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  delta?: { value: string; tone: 'pos' | 'neg' | 'neutral' };
  spark?: number[];
  sparkTone?: 'accent' | 'success' | 'warn' | 'block' | 'danger' | 'info';
  hint?: string;
  unit?: string;
  num?: string; // small editorial section numeral, e.g. "i."
  className?: string;
}

const SPARK_CLASSES: Record<string, { stroke: string; fill: string }> = {
  accent: { stroke: 'text-accent', fill: 'text-accent/10' },
  success: { stroke: 'text-success', fill: 'text-success/10' },
  warn: { stroke: 'text-warn', fill: 'text-warn/10' },
  block: { stroke: 'text-accent', fill: 'text-accent/10' },
  danger: { stroke: 'text-danger', fill: 'text-danger/10' },
  info: { stroke: 'text-info', fill: 'text-info/10' },
};

export function KpiCard({
  label,
  value,
  delta,
  spark,
  sparkTone = 'accent',
  hint,
  unit,
  num,
  className,
}: KpiCardProps) {
  const sc = SPARK_CLASSES[sparkTone];
  return (
    <div
      className={cn(
        'border border-border bg-canvas px-4 pt-3 pb-3 flex flex-col gap-2 min-w-0',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2 min-w-0">
          {num && (
            <span className="font-serif italic text-[13px] leading-none text-text-tertiary">
              {num}
            </span>
          )}
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary truncate">
            {label}
          </span>
        </div>
        {delta && (
          <span
            className={cn(
              'font-mono text-[10px] tnum',
              delta.tone === 'pos' && 'text-success',
              delta.tone === 'neg' && 'text-accent',
              delta.tone === 'neutral' && 'text-text-tertiary',
            )}
          >
            {delta.value}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between gap-3 min-w-0">
        <div className="min-w-0 flex items-baseline gap-1.5">
          <div className="font-serif text-[44px] leading-[1] tracking-display text-text-primary tnum">
            {value}
          </div>
          {unit && (
            <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-text-tertiary pb-1">
              {unit}
            </span>
          )}
        </div>
        {spark && (
          <MetricSpark
            data={spark}
            stroke={sc?.stroke}
            fill={sc?.fill}
            width={96}
            height={28}
          />
        )}
      </div>

      {hint && (
        <div className="font-mono text-[10.5px] text-text-tertiary border-t border-border pt-2 mt-1">
          {hint}
        </div>
      )}
    </div>
  );
}
