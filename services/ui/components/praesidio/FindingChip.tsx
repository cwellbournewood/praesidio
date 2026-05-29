import { cn, familyClasses, labelFamily } from '@/lib/utils';
import { lookup } from '@/lib/labels';
import type { Finding } from '@/lib/types';

/**
 * Render a single DLP finding as a compact chip.
 *
 * Renders the human-readable display name (e.g. "Organization name")
 * instead of the wire label (e.g. `pii.organization`) — operators were
 * confused by the raw IDs. The tooltip carries the wire label, the
 * category, severity, confidence, and the one-line description so power
 * users can still drill in without losing the technical detail.
 */
export function FindingChip({
  finding,
  showScore = false,
  showWireLabel = false,
  className,
}: {
  finding: Finding;
  showScore?: boolean;
  /** Render the wire ID instead of the human name. Used in policy
   *  authoring contexts where the label IS the thing being edited. */
  showWireLabel?: boolean;
  className?: string;
}) {
  const fam = labelFamily(finding.label);
  const c = familyClasses(fam);
  const display = lookup(finding.label);
  const text = showWireLabel ? finding.label : display.name;
  const scorePct = (finding.score * 100).toFixed(0);
  // Single-line tooltip works in every browser without a popover library.
  const tooltip = [
    display.name,
    `${finding.label} · ${display.category} · ${display.severity}`,
    `confidence ${scorePct}%`,
    display.description,
  ].join('\n');
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 border px-1.5 h-[18px] font-mono text-[10.5px] uppercase tracking-[0.04em] whitespace-nowrap',
        c.chip,
        className,
      )}
      title={tooltip}
    >
      <span className={cn('h-[6px] w-[6px]', c.dot)} aria-hidden />
      <span className="truncate normal-case tracking-normal">{text}</span>
      {showScore && (
        <span className="text-text-tertiary tnum normal-case tracking-normal">
          {scorePct}%
        </span>
      )}
    </span>
  );
}
