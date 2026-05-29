'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { useSearchParams } from 'next/navigation';
import { Filter, Search } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { DataTable, type ColumnDef } from '@/components/ui/table';
import { Pagination } from '@/components/ui/pagination';
import { Tag } from '@/components/ui/tag';
import { EmptyState } from '@/components/ui/empty-state';
import { DecisionBadge } from '@/components/praesidio/DecisionBadge';
import { EventDetail } from '@/components/praesidio/EventDetail';
import { swrFetcher } from '@/lib/api';
import type { AuditEvent, Decision } from '@/lib/types';
import { ago, formatMs, shortId } from '@/lib/utils';

function EventsView() {
  const sp = useSearchParams();
  const idFromUrl = sp.get('id');

  const { data } = useSWR<AuditEvent[]>('/admin/events?limit=400', swrFetcher, {
    refreshInterval: 10_000,
  });

  const [q, setQ] = useState('');
  const [tenant, setTenant] = useState<string>('all');
  const [decision, setDecision] = useState<Decision | 'all'>('all');
  const [detector, setDetector] = useState<string>('all');
  const [days, setDays] = useState<string>('7');
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const tenants = useMemo(() => Array.from(new Set((data ?? []).map((e) => e.tenant_id))), [data]);
  const detectors = useMemo(() => {
    const s = new Set<string>();
    (data ?? []).forEach((e) => e.findings.forEach((f) => s.add(f.label)));
    return Array.from(s).sort();
  }, [data]);

  const filtered = useMemo(() => {
    const now = Date.now();
    const ms = Number(days) * 24 * 60 * 60 * 1000;
    return (data ?? []).filter((e) => {
      if (tenant !== 'all' && e.tenant_id !== tenant) return false;
      if (decision !== 'all' && e.decision !== decision) return false;
      if (detector !== 'all' && !e.findings.some((f) => f.label === detector)) return false;
      if (Number.isFinite(ms) && now - new Date(e.occurred_at).getTime() > ms) return false;
      if (q) {
        const hay = `${e.principal.email} ${e.id} ${e.upstream} ${e.route} ${e.tenant_id}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });
  }, [data, tenant, decision, detector, days, q]);

  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => setPage(1), [q, tenant, decision, detector, days]);

  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {
    if (idFromUrl) setOpenId(idFromUrl);
  }, [idFromUrl]);
  const openEvent = (data ?? []).find((e) => e.id === openId) ?? null;

  const columns: ColumnDef<AuditEvent>[] = [
    {
      key: 'decision',
      header: 'Decision',
      width: '140px',
      cell: (e) => <DecisionBadge decision={e.decision} size="xs" />,
    },
    {
      key: 'principal',
      header: 'Principal',
      width: '1.4fr',
      cell: (e) => (
        <div className="min-w-0">
          <div className="truncate font-medium">{e.principal.email}</div>
          <div className="truncate font-mono text-xs text-text-tertiary">
            {e.tenant_id} · {e.principal.country ?? '—'}
          </div>
        </div>
      ),
    },
    {
      key: 'route',
      header: 'Route → upstream',
      width: '1.4fr',
      cell: (e) => (
        <div className="min-w-0">
          <div className="truncate font-mono text-xs">{e.route}</div>
          <div className="truncate font-mono text-xs text-text-tertiary">{e.upstream}</div>
        </div>
      ),
    },
    {
      key: 'findings',
      header: 'Findings',
      width: '1fr',
      cell: (e) =>
        e.findings.length === 0 ? (
          <span className="text-text-tertiary">—</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {e.findings.slice(0, 3).map((f, i) => (
              <Tag key={i}>{f.label.replace(/^.*\./, '')}</Tag>
            ))}
            {e.findings.length > 3 && (
              <span className="text-xs text-text-tertiary">+{e.findings.length - 3}</span>
            )}
          </div>
        ),
    },
    {
      key: 'latency',
      header: 'Latency',
      width: '100px',
      align: 'right',
      cell: (e) => <span className="font-mono tabular-nums">{formatMs(e.latency_ms)}</span>,
    },
    {
      key: 'id',
      header: 'ID',
      width: '120px',
      cell: (e) => <span className="font-mono text-xs text-text-tertiary">{shortId(e.id)}</span>,
    },
    {
      key: 'when',
      header: 'When',
      width: '120px',
      align: 'right',
      cell: (e) => <span className="text-text-secondary">{ago(e.occurred_at)}</span>,
    },
  ];

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              ii.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Events
            </h1>
          </div>
          <div className="hidden md:flex items-baseline gap-3 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <span className="tnum">{filtered.length}</span> matching rows
          </div>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Every decision the gateway made, with a row-level chain-hash linking it
          to its predecessor. The audit log is append-only and Merkle-rooted.
        </p>
      </header>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="relative min-w-[260px] flex-1">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-tertiary"
              aria-hidden
            />
            <Input
              placeholder="Search principal, request id, upstream…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-7"
            />
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
            <Filter className="h-3.5 w-3.5" /> Filters
          </div>
          <div className="w-[140px]">
            <Select value={tenant} onChange={(e) => setTenant(e.target.value)} aria-label="Tenant">
              <option value="all">All tenants</option>
              {tenants.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-[140px]">
            <Select
              value={decision}
              onChange={(e) => setDecision(e.target.value as any)}
              aria-label="Decision"
            >
              <option value="all">All decisions</option>
              <option value="allow">Allowed</option>
              <option value="transform">Transformed</option>
              <option value="block">Blocked</option>
              <option value="simulate">Simulated</option>
              <option value="error">Error</option>
            </Select>
          </div>
          <div className="w-[200px]">
            <Select
              value={detector}
              onChange={(e) => setDetector(e.target.value)}
              aria-label="Detector"
            >
              <option value="all">All detectors</option>
              {detectors.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-[110px]">
            <Select value={days} onChange={(e) => setDays(e.target.value)} aria-label="Range">
              <option value="1">24 hours</option>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="9999">All time</option>
            </Select>
          </div>
        </div>
        <div className="p-3">
          <DataTable
            columns={columns}
            rows={paged}
            rowKey={(r) => r.id}
            onRowClick={(r) => setOpenId(r.id)}
            empty={
              <EmptyState
                title="No events match these filters. Try widening the time range, or clear the principal search."
                docHref="/docs/architecture/06-audit-lineage.md"
                docLabel="Audit & lineage docs"
              />
            }
          />
          <div className="mt-3">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={filtered.length}
              onPageChange={setPage}
            />
          </div>
        </div>
      </Card>

      <EventDetail
        event={openEvent}
        open={Boolean(openEvent)}
        onOpenChange={(o) => !o && setOpenId(null)}
      />
    </div>
  );
}

export default function EventsPage() {
  return (
    <Suspense
      fallback={<div className="h-32 animate-pulse-soft rounded-md bg-surface-sunken" />}
    >
      <EventsView />
    </Suspense>
  );
}
