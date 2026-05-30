'use client';

import useSWR from 'swr';
import { notFound, useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/tag';
import { Breadcrumb } from '@/components/ui/breadcrumb';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { PolicyEditor } from '@/components/section/PolicyEditor';
import { swrFetcher } from '@/lib/api';
import type { Policy } from '@/lib/types';
import { ago, decisionClasses, decisionLabel, formatInt } from '@/lib/utils';

export default function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: policy, isLoading } = useSWR<Policy | undefined>(
    `/admin/policies/${id}`,
    swrFetcher,
  );

  if (!isLoading && !policy) notFound();

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <Breadcrumb
        items={[
          { label: 'Policies', href: '/policies' },
          { label: policy?.name ?? id },
        ]}
      />

      <header className="border-b border-border pb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
              {policy?.id ?? id} · {policy?.owner ?? '—'}
            </div>
            <h1 className="mt-1 font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary truncate">
              {policy?.name ?? <Skeleton className="h-12 w-72" />}
            </h1>
            {policy && (
              <p className="mt-2 font-mono text-[11px] text-text-tertiary">
                updated {ago(policy.updated_at)} · {policy.version}
              </p>
            )}
          </div>
          {policy && (
            <div className="flex items-center gap-2 shrink-0">
              <Badge tone={policy.enabled ? 'success' : 'neutral'}>
                {policy.enabled ? 'enabled' : 'disabled'}
              </Badge>
              <Badge tone={policy.fail_mode === 'closed' ? 'block' : 'warn'}>
                fail {policy.fail_mode}
              </Badge>
            </div>
          )}
        </div>
      </header>

      {policy && (
        <>
          <Card>
            <CardContent>
              <p className="text-sm text-text-secondary">{policy.description}</p>
            </CardContent>
          </Card>

          <Tabs defaultValue="yaml">
            <TabsList>
              <TabsTrigger value="yaml">YAML</TabsTrigger>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="decisions">Recent decisions</TabsTrigger>
            </TabsList>

            <TabsContent value="yaml">
              <PolicyEditor yaml={policy.raw_yaml} />
              <p className="mt-2 text-xs text-text-tertiary">
                TODO · edit mode + dry-run preview is out of MVP scope. The intended flow generates
                a pull request against the policy bundle repo.
              </p>
            </TabsContent>

            <TabsContent value="overview">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Match</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <Row label="Routes">
                      <div className="flex flex-wrap gap-1">
                        {policy.match.routes.map((r) => (
                          <Tag key={r}>{r}</Tag>
                        ))}
                      </div>
                    </Row>
                    <Row label="Tenants">
                      <div className="flex flex-wrap gap-1">
                        {policy.match.tenants.map((t) => (
                          <Tag key={t}>{t}</Tag>
                        ))}
                      </div>
                    </Row>
                    {policy.match.principals?.groups && (
                      <Row label="Groups">
                        <div className="flex flex-wrap gap-1">
                          {policy.match.principals.groups.map((g) => (
                            <Tag key={g}>{g}</Tag>
                          ))}
                        </div>
                      </Row>
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Detectors enabled</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1.5">
                      {policy.detectors.map((d) => (
                        <Tag key={d}>{d}</Tag>
                      ))}
                    </div>
                  </CardContent>
                </Card>
                <Card className="md:col-span-2">
                  <CardHeader>
                    <CardTitle>Rules (top-down, first match wins)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ol className="space-y-2">
                      {policy.rules.map((r, i) => (
                        <li
                          key={i}
                          className="grid grid-cols-[28px_1fr_120px] items-start gap-3 rounded-md border border-border bg-surface px-3 py-2"
                        >
                          <span className="font-mono text-xs text-text-tertiary">{i}</span>
                          <div className="min-w-0">
                            <code className="block whitespace-pre-wrap break-words font-mono text-xs text-text-primary">
                              {r.when}
                            </code>
                            {r.reason && (
                              <div className="mt-1 text-xs text-text-secondary">{r.reason}</div>
                            )}
                          </div>
                          <Badge
                            tone={
                              r.action === 'block' ? 'block' : r.action === 'transform' ? 'warn' : 'success'
                            }
                          >
                            {r.action}
                          </Badge>
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="decisions">
              <Card>
                <CardContent>
                  <ul className="divide-y divide-border">
                    {policy.recent_decisions.map((d) => {
                      const c = decisionClasses(d.decision);
                      return (
                        <li
                          key={d.decision}
                          className="flex items-center justify-between py-2.5 text-sm"
                        >
                          <span className="inline-flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-pill ${c.fg.replace('text-', 'bg-')}`} />
                            {decisionLabel(d.decision)}
                          </span>
                          <span className="font-mono tabular-nums text-text-primary">
                            {formatInt(d.count)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3">
      <div className="text-xs uppercase tracking-[0.04em] text-text-tertiary">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
