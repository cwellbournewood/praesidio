'use client';

import useSWR from 'swr';
import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { KpiCard } from '@/components/praesidio/KpiCard';
import { EventRow } from '@/components/praesidio/EventRow';
import { MetricSpark } from '@/components/praesidio/MetricSpark';
import { Skeleton } from '@/components/ui/skeleton';
import { swrFetcher } from '@/lib/api';
import type { AuditEvent, DashboardKpis } from '@/lib/types';
import { formatInt, formatMs, formatPct } from '@/lib/utils';

export default function DashboardPage() {
  const { data: kpis } = useSWR<DashboardKpis>('/admin/metrics/summary', swrFetcher);
  const { data: events } = useSWR<AuditEvent[]>('/admin/events?limit=50', swrFetcher, {
    refreshInterval: 5_000,
  });

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-8">
      {/* Masthead */}
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              i.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Overview
            </h1>
          </div>
          <div className="hidden md:flex items-center gap-2 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <span className="sig sig-allow pulse" aria-hidden />
            gateway healthy · live
          </div>
        </div>
        <div className="mt-3 flex items-baseline justify-between gap-4">
          <p className="marginalia max-w-2xl">
            A reading of all decisions across every tenant, every model, every
            minute — printed afresh as data arrives. Quiet by default; loud only
            when policy speaks.
          </p>
          <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            t-zero · last 24h
          </span>
        </div>
      </header>

      {/* KPI grid — five wide */}
      <section>
        <div className="grid grid-cols-1 gap-0 md:grid-cols-2 xl:grid-cols-5 border border-border bg-canvas
                        [&>*]:border-r [&>*]:border-border [&>*:last-child]:border-r-0
                        md:[&>*:nth-child(2n)]:border-r-0 xl:[&>*:nth-child(2n)]:border-r xl:[&>*:nth-child(5n)]:border-r-0
                        [&>*]:border-b [&>*]:border-border [&>*:last-child]:border-b-0 xl:[&>*]:border-b-0">
          {kpis ? (
            <>
              <KpiCard
                num="§ 1"
                label="Requests · today"
                value={formatInt(kpis.requests_today)}
                spark={kpis.spark}
                sparkTone="accent"
                delta={{ value: '+8.4% Δ', tone: 'pos' }}
              />
              <KpiCard
                num="§ 2"
                label="Transformed"
                value={formatPct(kpis.transformed_pct)}
                spark={kpis.spark.map((x) => x * 0.4)}
                sparkTone="warn"
                hint="Mostly PII tokenisation"
              />
              <KpiCard
                num="§ 3"
                label="Blocked"
                value={formatPct(kpis.blocked_pct)}
                spark={kpis.spark.map((x) => x * 0.08 + 4)}
                sparkTone="block"
                delta={{ value: '−0.2 pp w/w', tone: 'pos' }}
              />
              <KpiCard
                num="§ 4"
                label="p99 latency"
                value={formatMs(kpis.p99_latency_ms)}
                spark={kpis.spark.map((x) => 300 + x * 1.2)}
                sparkTone="info"
                hint="Gateway only · excl. upstream"
              />
              <KpiCard
                num="§ 5"
                label="Top detector"
                value={kpis.top_detectors[0]?.label.split('.').slice(-1)[0] ?? '—'}
                hint={`${formatInt(kpis.top_detectors[0]?.count ?? 0)} hits today`}
                sparkTone="accent"
              />
            </>
          ) : (
            Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[128px]" />)
          )}
        </div>
      </section>

      {/* Throughput band */}
      <section className="border border-border bg-canvas">
        <div className="flex items-baseline justify-between border-b border-border px-4 h-9">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic text-[13px] text-text-tertiary">ii.</span>
            <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              Throughput · requests per hour
            </span>
          </div>
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
            {kpis?.spark?.length ?? 24} buckets · diurnal · EMEA peak
          </span>
        </div>
        <div className="px-4 py-4">
          {kpis ? (
            <MetricSpark
              data={kpis.spark}
              width={1100}
              height={84}
              stroke="text-text-primary"
              fill="text-text-primary/10"
              className="w-full"
            />
          ) : (
            <Skeleton className="h-20 w-full" />
          )}
        </div>
      </section>

      {/* Detectors + ticker */}
      <section className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-0 border border-border bg-canvas">
        {/* Detectors */}
        <div className="border-b lg:border-b-0 lg:border-r border-border">
          <div className="flex items-baseline justify-between border-b border-border px-4 h-9">
            <div className="flex items-baseline gap-2">
              <span className="font-serif italic text-[13px] text-text-tertiary">iii.</span>
              <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
                Top detectors
              </span>
            </div>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
              by hits · 24h
            </span>
          </div>
          <div className="px-4 py-3">
            {kpis ? (
              <ul className="space-y-2">
                {kpis.top_detectors.map((d, i) => {
                  const max = kpis.top_detectors[0]?.count ?? 1;
                  const pct = (d.count / max) * 100;
                  return (
                    <li key={d.label} className="flex items-center gap-3 font-mono text-[11.5px]">
                      <span className="text-text-tertiary tnum w-5 text-right">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="text-text-primary flex-1 truncate">{d.label}</span>
                      <span className="bar-track">
                        <i style={{ width: `${pct}%` }} />
                      </span>
                      <span className="text-text-secondary tnum w-12 text-right">
                        {formatInt(d.count)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Skeleton className="h-40 w-full" />
            )}
          </div>
        </div>

        {/* Live events */}
        <div>
          <div className="flex items-baseline justify-between border-b border-border px-4 h-9">
            <div className="flex items-baseline gap-2">
              <span className="font-serif italic text-[13px] text-text-tertiary">iv.</span>
              <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
                Live tape
              </span>
              <span className="sig sig-block pulse ml-1" aria-hidden />
            </div>
            <Link
              href="/events"
              className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
            >
              all events <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
          {events ? (
            <div className="max-h-[440px] overflow-y-auto">
              {events.slice(0, 50).map((e) => (
                <EventRow
                  key={e.id}
                  event={e}
                  onClick={() => (window.location.href = `/events?id=${e.id}`)}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-1 p-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Colophon hint */}
      <footer className="border-t border-border pt-4 flex items-baseline justify-between text-text-tertiary">
        <p className="marginalia max-w-xl">
          Press <span className="kbd">⌘K</span> to jump to a principal, paste a
          request id, or open a policy. The console is keyboard-first.
        </p>
        <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase">
          colophon · praesidio cp · v0.1
        </span>
      </footer>
    </div>
  );
}
