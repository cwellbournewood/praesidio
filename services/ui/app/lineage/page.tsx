'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { ArrowUpRight, GitBranch } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Breadcrumb } from '@/components/ui/breadcrumb';
import { swrFetcher } from '@/lib/api';
import { ago, shortId } from '@/lib/utils';
import { useT } from '@/lib/i18n';

interface LineageIndexItem {
  request_id: string;
  started_at: string | null;
  node_count: number;
  source: 'lineage' | 'audit';
}
interface LineageIndex {
  items: LineageIndexItem[];
  tenant_id: string;
}

export default function LineageIndexPage() {
  const t = useT();
  const { data, error, isLoading } = useSWR<LineageIndex>('/admin/lineage', swrFetcher, {
    refreshInterval: 15_000,
  });

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <Breadcrumb items={[{ label: t('lineage.title', 'Lineage') }]} />
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              iv.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              {t('lineage.title', 'Lineage')}
            </h1>
          </div>
          <div className="hidden md:flex items-baseline gap-3 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <span className="tnum">{data?.items.length ?? 0}</span>{' '}
            {t('lineage.recent', 'recent requests')}
          </div>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          {t(
            'lineage.subtitle',
            'Every recorded request derivation graph. Pick a request to trace its prompt, retrievals, tool calls and outputs.',
          )}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>{t('lineage.recentHeader', 'Recent lineage')}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && !data && (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          )}
          {error && !data && (
            <EmptyState
              title={t(
                'lineage.errorTitle',
                'Could not load recent lineage from the gateway.',
              )}
              docHref="/docs/architecture/06-audit-lineage.md"
              docLabel={t('lineage.docs', 'Audit & lineage docs')}
            />
          )}
          {data && data.items.length === 0 && (
            <EmptyState
              title={t(
                'lineage.emptyTitle',
                'No requests recorded yet. Send a prompt through the gateway and refresh.',
              )}
              docHref="/docs/architecture/06-audit-lineage.md"
              docLabel={t('lineage.docs', 'Audit & lineage docs')}
            />
          )}
          {data && data.items.length > 0 && (
            <ul className="divide-y divide-border" role="list">
              {data.items.map((item) => (
                <li key={item.request_id}>
                  <Link
                    href={`/lineage/${encodeURIComponent(item.request_id)}`}
                    className="group flex items-center gap-3 px-2 py-3 hover:bg-surface-sunken focus:bg-surface-sunken focus:outline-none focus-visible:ring-1 focus-visible:ring-accent transition-colors"
                  >
                    <GitBranch
                      className="h-3.5 w-3.5 text-text-tertiary shrink-0"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-[12px] text-text-primary">
                        {item.request_id}
                      </span>
                      <span className="block truncate font-mono text-[10.5px] uppercase tracking-[0.14em] text-text-tertiary">
                        {shortId(item.request_id, 12)} ·{' '}
                        {item.source === 'lineage'
                          ? `${item.node_count} ${t('lineage.nodes', 'nodes')}`
                          : t('lineage.noNodes', 'no lineage rows · audit only')}
                      </span>
                    </span>
                    <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-text-tertiary tnum">
                      {item.started_at ? ago(item.started_at) : '—'}
                    </span>
                    <ArrowUpRight
                      className="h-3 w-3 text-text-tertiary group-hover:text-accent shrink-0"
                      aria-hidden
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
