import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/tag';
import type { ModelCardEntry } from '@/lib/types';

const TIER_TONE: Record<ModelCardEntry['risk_tier'], 'success' | 'warn' | 'danger'> = {
  low: 'success',
  medium: 'warn',
  high: 'danger',
};

const TIER_SIG: Record<ModelCardEntry['risk_tier'], string> = {
  low: 'sig-allow',
  medium: 'sig-warn',
  high: 'sig-block',
};

export function ModelCard({ model }: { model: ModelCardEntry }) {
  return (
    <article className="border border-border bg-canvas flex flex-col">
      {/* Header */}
      <header className="border-b border-border px-4 pt-3 pb-3">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            {model.provider}
          </span>
          <span className="flex items-center gap-1.5 font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
            <span className={`sig ${TIER_SIG[model.risk_tier]}`} aria-hidden />
            {model.risk_tier} risk
          </span>
        </div>
        <h3 className="mt-1 font-serif text-[24px] leading-tight tracking-display text-text-primary truncate">
          {model.display_name}
        </h3>
        <div className="mt-1 font-mono text-[11px] text-text-secondary truncate">
          {model.model}
        </div>
      </header>

      <div className="px-4 py-3 flex flex-col gap-2.5">
        <Row label="Jurisdiction">
          <span className="font-mono text-[11.5px]">{model.jurisdiction}</span>
          <span className="font-mono text-[11.5px] text-text-tertiary"> · {model.region}</span>
        </Row>
        <Row label="Certifications">
          <div className="flex flex-wrap gap-1">
            {model.certifications.map((c) => (
              <Tag key={c}>{c}</Tag>
            ))}
          </div>
        </Row>
        <Row label="Privacy">
          <div className="flex flex-wrap gap-1">
            <Badge tone={model.privacy.training_optout ? 'success' : 'danger'}>
              {model.privacy.training_optout ? 'training opt-out' : 'no opt-out'}
            </Badge>
            <Badge tone="neutral">retention {model.privacy.data_retention_days}d</Badge>
            {model.privacy.customer_managed_keys && <Badge tone="success">CMK</Badge>}
          </div>
        </Row>
        <Row label="Routes">
          <div className="flex flex-wrap gap-1">
            {model.route_mappings.map((r) => (
              <Tag key={r}>{r}</Tag>
            ))}
          </div>
        </Row>
      </div>

      {model.notes && (
        <p className="border-t border-border px-4 py-3 marginalia">{model.notes}</p>
      )}
    </article>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-3 items-baseline">
      <dt className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary">
        {label}
      </dt>
      <dd className="min-w-0 text-text-primary">{children}</dd>
    </div>
  );
}
