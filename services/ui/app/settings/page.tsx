'use client';

import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { swrFetcher } from '@/lib/api';
import type { GatewayHealth } from '@/lib/types';

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[200px_1fr] gap-3 border-b border-border py-2.5 last:border-b-0 text-sm">
      <div className="text-text-tertiary">{k}</div>
      <div className="min-w-0 break-words font-mono text-text-primary">{v}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { data: health } = useSWR<GatewayHealth>('/healthz', swrFetcher);

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              vi.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Settings
            </h1>
          </div>
          <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            read-only · ship via redeploy
          </span>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Read-only view of the current control plane configuration. To change
          values, update the environment, Helm chart, or policy bundle and
          redeploy.
        </p>
      </header>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Runtime</CardTitle>
            <p className="mt-0.5 text-sm text-text-secondary">From the gateway's /healthz probe.</p>
          </div>
          {health ? (
            <Badge tone={health.ok ? 'success' : 'danger'}>{health.ok ? 'healthy' : 'down'}</Badge>
          ) : (
            <Skeleton className="h-5 w-16" />
          )}
        </CardHeader>
        <CardContent>
          {health ? (
            <>
              <KV k="Gateway URL" v={health.gateway_url} />
              <KV k="Environment" v={<Badge tone="info">{health.env}</Badge>} />
              <KV k="Build version" v={health.version} />
              <KV k="Active bundle digest" v={health.bundle_digest} />
              <KV k="Policies loaded" v={String(health.policy_count)} />
              <KV
                k="Default fail mode"
                v={
                  <Badge tone={health.fail_mode === 'closed' ? 'block' : 'warn'}>
                    {health.fail_mode}
                  </Badge>
                }
              />
            </>
          ) : (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>UI</CardTitle>
        </CardHeader>
        <CardContent>
          <KV
            k="NEXT_PUBLIC_GATEWAY_URL"
            v={process.env.NEXT_PUBLIC_GATEWAY_URL ?? '(unset — using mock)'}
          />
          <KV
            k="NEXT_PUBLIC_MOCK"
            v={process.env.NEXT_PUBLIC_MOCK ?? '0'}
          />
          <KV k="UI build" v="section-ui v0.1.0" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Operator notes</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1.5 text-sm text-text-secondary">
            <li>
              Policy edits are made by opening a PR against the policy bundle repository; the
              gateway pulls signed bundles and hot-reloads them.
            </li>
            <li>
              Audit rows form a per-tenant hash chain. To verify integrity, replay the chain from
              the last published checkpoint.
            </li>
            <li>
              All UI traffic is admin-only; principals are resolved by the same identity provider
              the data plane uses.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
