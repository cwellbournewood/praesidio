'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { ArrowUpRight, FileLock2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/tag';
import { EmptyState } from '@/components/ui/empty-state';
import { swrFetcher } from '@/lib/api';
import type { Policy } from '@/lib/types';
import { ago, decisionClasses, decisionLabel, formatInt } from '@/lib/utils';

export default function PoliciesPage() {
  const { data: policies } = useSWR<Policy[]>('/admin/policies', swrFetcher);

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              iii.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Policies
            </h1>
          </div>
          <a
            href="https://github.com/your-org/section-policies"
            className="inline-flex items-center gap-1 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary hover:text-accent"
          >
            open in git <ArrowUpRight className="h-3 w-3" />
          </a>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Active YAML bundle, signed with cosign before reload. Edits ship as
          pull requests against the policies repo — never live mutations from
          this console.
        </p>
      </header>

      {policies && policies.length === 0 && (
        <EmptyState
          icon={<FileLock2 className="h-6 w-6" />}
          title="No policies loaded. The gateway is running in fail-mode default."
          docHref="/docs/architecture/03-policy-engine.md"
          docLabel="Policy engine docs"
        />
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {policies?.map((p) => (
          <Link key={p.id} href={`/policies/${p.id}`} className="group">
            <Card className="transition-colors duration-fast group-hover:border-border-strong">
              <CardHeader>
                <div className="min-w-0">
                  <div className="text-xs font-medium uppercase tracking-[0.04em] text-text-tertiary">
                    {p.id}
                  </div>
                  <CardTitle className="mt-0.5 truncate">{p.name}</CardTitle>
                  <div className="mt-0.5 text-xs text-text-secondary">
                    {p.owner} · updated {ago(p.updated_at)}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <Badge tone={p.enabled ? 'success' : 'neutral'}>
                    {p.enabled ? 'enabled' : 'disabled'}
                  </Badge>
                  <Badge tone={p.fail_mode === 'closed' ? 'block' : 'warn'}>
                    fail {p.fail_mode}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-text-secondary line-clamp-2">{p.description}</p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {p.detectors.slice(0, 6).map((d) => (
                    <Tag key={d}>{d}</Tag>
                  ))}
                  {p.detectors.length > 6 && (
                    <span className="text-xs text-text-tertiary">+{p.detectors.length - 6}</span>
                  )}
                </div>
                <div className="mt-3 flex items-center gap-3 border-t border-border pt-3">
                  {p.recent_decisions.map((d) => {
                    const c = decisionClasses(d.decision);
                    return (
                      <div key={d.decision} className="flex items-center gap-1.5 text-xs">
                        <span className={`h-2 w-2 rounded-pill ${c.fg.replace('text-', 'bg-')}`} />
                        <span className="text-text-secondary">{decisionLabel(d.decision)}</span>
                        <span className="font-mono tabular-nums text-text-primary">
                          {formatInt(d.count)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
