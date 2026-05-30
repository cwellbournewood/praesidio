import { cn, decisionLabel, decisionSigClass } from '@/lib/utils';
import type { Decision } from '@/lib/types';

export function DecisionBadge({
  decision,
  size = 'sm',
  className,
}: {
  decision: Decision;
  size?: 'xs' | 'sm' | 'md';
  className?: string;
}) {
  const sigCls = decisionSigClass(decision);
  return (
    <span
      role="status"
      aria-label={decisionLabel(decision)}
      className={cn(
        'inline-flex items-center gap-1.5 font-mono uppercase tracking-[0.08em] text-text-primary',
        size === 'xs' && 'text-[10px]',
        size === 'sm' && 'text-[10.5px]',
        size === 'md' && 'text-[11.5px]',
        className,
      )}
    >
      <span aria-hidden className={cn('sig', sigCls)} />
      {decisionLabel(decision)}
    </span>
  );
}
