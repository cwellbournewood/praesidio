import { ago, cn, decisionLabel, decisionSigClass, formatMs, shortId } from '@/lib/utils';
import type { AuditEvent } from '@/lib/types';

export function EventRow({
  event,
  onClick,
  selected,
  className,
}: {
  event: AuditEvent;
  onClick?: () => void;
  selected?: boolean;
  className?: string;
}) {
  const sig = decisionSigClass(event.decision);
  return (
    <button
      onClick={onClick}
      className={cn(
        'row group grid w-full items-center gap-3 border-b border-border px-3 h-9 text-left transition-colors duration-fast hover:bg-surface-sunken font-mono text-[11.5px]',
        // [sig | time | id | principal | route | upstream | latency | findings]
        'grid-cols-[12px_64px_82px_minmax(120px,1.4fr)_minmax(160px,1.6fr)_minmax(120px,1fr)_56px_56px]',
        selected && 'selected',
        className,
      )}
    >
      <span className={cn('sig', sig)} aria-hidden title={decisionLabel(event.decision)} />
      <span className="text-text-tertiary tnum truncate">{ago(event.occurred_at)}</span>
      <span className="text-text-secondary tnum truncate">{shortId(event.id)}</span>
      <span className="text-text-primary truncate">{event.principal.email}</span>
      <span className="text-text-tertiary truncate whitespace-nowrap">{event.route}</span>
      <span className="text-text-secondary truncate">{event.upstream}</span>
      <span className="text-text-secondary tnum text-right">{formatMs(event.latency_ms)}</span>
      <span className="text-text-tertiary tnum text-right">
        {event.findings.length > 0 ? event.findings.length : '—'}
      </span>
    </button>
  );
}
