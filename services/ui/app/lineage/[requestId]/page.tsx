'use client';

import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Breadcrumb } from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { swrFetcher } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { LineageGraphData, LineageNode } from '@/lib/types';

// V5 — lazy-load the graph renderer so the lineage bundle doesn't bloat
// the initial UI shell. The lineage route is rarely the first page a
// new operator visits.
const LineageGraph = lazy(() =>
  import('@/components/section/LineageGraph').then((m) => ({ default: m.LineageGraph })),
);

interface ApiLineage extends LineageGraphData {
  tenant_id?: string;
  audit_event_id?: string | null;
}

export default function LineagePage() {
  const t = useT();
  const params = useParams<{ requestId: string }>();
  const requestId = decodeURIComponent(params.requestId ?? '');
  const { data, error, isLoading, mutate } = useSWR<ApiLineage>(
    requestId ? `/admin/lineage/${encodeURIComponent(requestId)}` : null,
    swrFetcher,
  );
  const [selected, setSelected] = useState<LineageNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Keyboard navigation: arrow keys cycle focus among nodes in DOM
  // order; Enter / Space activates (delegated to the node button).
  const onKey = useCallback((e: KeyboardEvent) => {
    if (!containerRef.current) return;
    const buttons = Array.from(
      containerRef.current.querySelectorAll<HTMLButtonElement>('button[data-lineage-node="true"], foreignObject button'),
    );
    if (buttons.length === 0) return;
    const idx = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1 + buttons.length) % buttons.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + buttons.length) % buttons.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = buttons.length - 1;
    if (next >= 0) {
      e.preventDefault();
      buttons[next]?.focus();
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  }, [onKey]);

  const isEmpty = useMemo(
    () => Boolean(data && data.nodes.length === 0),
    [data],
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    (data?.nodes ?? []).forEach((n) => {
      c[n.kind] = (c[n.kind] ?? 0) + 1;
    });
    return c;
  }, [data]);

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <Breadcrumb
        items={[
          { label: t('lineage.title', 'Lineage'), href: '/lineage' },
          { label: requestId },
        ]}
      />
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
          <div className="flex items-center gap-2 flex-wrap">
            {Object.entries(counts).map(([kind, n]) => (
              <Badge
                key={kind}
                tone={
                  kind === 'prompt'
                    ? 'neutral'
                    : kind === 'retrieval'
                      ? 'info'
                      : kind === 'tool'
                        ? 'warn'
                        : kind === 'output'
                          ? 'success'
                          : 'block'
                }
              >
                {kind} · {n}
              </Badge>
            ))}
          </div>
        </div>
        <div className="mt-3 flex items-baseline justify-between gap-4">
          <p className="marginalia max-w-2xl">
            DAG of derivations for{' '}
            <span className="font-mono not-italic text-text-primary">{requestId}</span>.
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => mutate()}
              aria-label={t('common.retry', 'Retry')}
            >
              <RefreshCw className="h-3 w-3" aria-hidden /> {t('common.retry', 'Retry')}
            </Button>
            <Link
              href="/lineage"
              className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent inline-flex items-center gap-1"
            >
              <ArrowLeft className="h-3 w-3" aria-hidden /> {t('common.back', 'Back')}
            </Link>
          </div>
        </div>
      </header>

      <div
        ref={containerRef}
        className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]"
        tabIndex={-1}
      >
        <div className="min-h-[480px]">
          {isLoading && !data && <Skeleton className="min-h-[480px]" />}
          {error && !data && (
            <EmptyState
              title={t(
                'lineage.detailErrorTitle',
                'Could not load lineage for this request.',
              )}
              docHref="/docs/architecture/06-audit-lineage.md"
              docLabel={t('lineage.docs', 'Audit & lineage docs')}
            />
          )}
          {data && isEmpty && (
            <EmptyState
              title={t(
                'lineage.detailEmptyTitle',
                'No lineage recorded for this request.',
              )}
              docHref="/docs/architecture/06-audit-lineage.md"
              docLabel={t('lineage.docs', 'Audit & lineage docs')}
            />
          )}
          {data && !isEmpty && (
            <Suspense fallback={<Skeleton className="min-h-[480px]" />}>
              <LineageGraph data={data} onSelect={setSelected} className="min-h-[480px]" />
            </Suspense>
          )}
          <p className="mt-3 text-[10.5px] font-mono uppercase tracking-[0.14em] text-text-tertiary">
            {t('lineage.keyboardHint', 'Use ↑ ↓ ← → to move between nodes, Enter to open detail.')}
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{selected ? selected.label : 'Node detail'}</CardTitle>
          </CardHeader>
          <CardContent>
            {selected ? (
              <dl className="space-y-2 text-sm">
                <Row label="Kind">
                  <code className="font-mono text-text-primary">{selected.kind}</code>
                </Row>
                <Row label="ID">
                  <code className="font-mono text-text-tertiary break-all">{selected.id}</code>
                </Row>
                {selected.meta &&
                  Object.entries(selected.meta).map(([k, v]) => (
                    <Row key={k} label={k}>
                      <span className="font-mono text-text-primary">{String(v)}</span>
                    </Row>
                  ))}
                {data?.audit_event_id && (
                  <Row label="Audit">
                    <Link
                      href={`/events?id=${data.audit_event_id}`}
                      className="font-mono text-accent hover:underline inline-flex items-center gap-1"
                    >
                      {t('lineage.openInEvents', 'Open in events')}{' '}
                      <ArrowUpRight className="h-3 w-3" aria-hidden />
                    </Link>
                  </Row>
                )}
              </dl>
            ) : (
              <p className="text-sm text-text-secondary">
                Click any node in the graph to see its metadata and link to the originating audit event.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-3">
      <dt className="text-xs uppercase tracking-[0.04em] text-text-tertiary">{label}</dt>
      <dd className="min-w-0 break-words text-text-primary">{children}</dd>
    </div>
  );
}
