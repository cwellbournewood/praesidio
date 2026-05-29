import type { DecisionRecord } from '../../lib/types.js';
import type { Translate } from '../../lib/i18n.js';

export function DecisionList(props: {
  decisions: DecisionRecord[];
  t: Translate;
}): JSX.Element {
  const { decisions, t } = props;
  if (decisions.length === 0) {
    return <p className="empty">{t('popup.decisions.empty')}</p>;
  }
  return (
    <div className="decision-list">
      {decisions.map((d, i) => (
        <DecisionRow key={`${d.ts}-${i}`} d={d} t={t} />
      ))}
    </div>
  );
}

function DecisionRow({ d, t }: { d: DecisionRecord; t: Translate }): JSX.Element {
  const label =
    d.action === 'mask'
      ? t('popup.decisions.mask', { count: d.masked ?? 0 })
      : d.action === 'block'
        ? t('popup.decisions.block')
        : t('popup.decisions.allow');
  return (
    <div className="decision">
      <span className="site">{d.site}</span>
      <span className="action" data-action={d.action}>
        {label}
      </span>
      <span className="when" aria-label={new Date(d.ts).toISOString()}>
        {formatRelative(d.ts)}
      </span>
    </div>
  );
}

function formatRelative(ts: number): string {
  const diff = Math.max(0, Date.now() - ts);
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}
