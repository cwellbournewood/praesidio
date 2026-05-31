'use client';

import useSWR from 'swr';
import { Boxes } from 'lucide-react';
import { ModelCard } from '@/components/section/ModelCard';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { swrFetcher } from '@/lib/api';
import type { ModelCardEntry } from '@/lib/types';

export default function ModelsPage() {
  const { data: models } = useSWR<ModelCardEntry[]>('/admin/models', swrFetcher);
  const grouped = (models ?? []).reduce<Record<string, ModelCardEntry[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div className="px-5 md:px-10 py-6 md:py-8 space-y-6">
      <header className="border-b border-border pb-5">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-serif italic text-[20px] text-text-tertiary leading-none">
              v.
            </span>
            <h1 className="font-serif text-[44px] md:text-[56px] leading-[1] tracking-display text-text-primary">
              Models
            </h1>
          </div>
          <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
            registry · {models?.length ?? 0} entries
          </span>
        </div>
        <p className="mt-3 marginalia max-w-2xl">
          Upstream models the gateway is allowed to route to, with
          jurisdictional and certification metadata pinned for policy decisions.
        </p>
      </header>

      {!models && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      )}

      {models && models.length === 0 && (
        <EmptyState
          icon={<Boxes className="h-6 w-6" />}
          title="No models registered. Add a provider in models.yaml and push the bundle."
          docHref="/docs/architecture/08-model-routing.md"
          docLabel="Model routing docs"
        />
      )}

      {Object.entries(grouped).map(([provider, entries]) => (
        <section key={provider} className="space-y-3">
          <div className="flex items-baseline gap-3 border-b border-border pb-2">
            <span className="font-serif italic text-[15px] text-text-tertiary">§</span>
            <h2 className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
              {provider}
            </h2>
            <span className="leader flex-1 h-[1px]" aria-hidden />
            <span className="font-mono text-[10px] text-text-tertiary tnum">
              {entries.length} {entries.length === 1 ? 'model' : 'models'}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {entries.map((m) => (
              <ModelCard key={m.id} model={m} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
