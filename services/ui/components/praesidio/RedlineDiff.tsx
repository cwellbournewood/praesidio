'use client';

import { cn } from '@/lib/utils';

// Highlight vault tokens like <PERSON_a1b2> and [REDACTED_*] inside the
// sanitised pane; the "received" pane is best-effort and may be blank.
function highlightSanitised(s: string) {
  const parts: React.ReactNode[] = [];
  const re = /(\[REDACTED_[A-Z_]+\]|<[A-Z_]+_[a-z0-9]+>|\[CODE_REDACTED[^\]]*\])/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) parts.push(<span key={key++}>{s.slice(last, m.index)}</span>);
    const token = m[0];
    const isRedaction = token.startsWith('[REDACTED') || token.startsWith('[CODE');
    parts.push(
      isRedaction ? (
        <span key={key++} className="redaction" data-token="REDACTED">
          {token}
        </span>
      ) : (
        <span key={key++} className="tokenized">
          {token}
        </span>
      ),
    );
    last = m.index + token.length;
  }
  if (last < s.length) parts.push(<span key={key++}>{s.slice(last)}</span>);
  return parts;
}

function Pane({
  num,
  title,
  caption,
  children,
}: {
  num: string;
  title: string;
  caption: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border bg-canvas">
      <div className="flex items-baseline justify-between border-b border-border px-3 h-9">
        <div className="flex items-baseline gap-2">
          <span className="font-serif italic text-[13px] text-text-tertiary">{num}</span>
          <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-primary">
            {title}
          </span>
        </div>
        <span className="font-mono text-[10px] text-text-tertiary">{caption}</span>
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-3 font-mono text-[12px] leading-[1.65] text-text-primary">
        {children}
      </pre>
    </div>
  );
}

export function RedlineDiff({
  received,
  sanitised,
  className,
}: {
  received?: string | null;
  sanitised?: string | null;
  className?: string;
}) {
  return (
    <div className={cn('grid grid-cols-1 gap-0 md:grid-cols-2 md:[&>div:first-child]:border-r-0', className)}>
      <Pane num="i." title="Received from caller" caption="local preview only">
        {received ?? <span className="text-text-tertiary">(not retained)</span>}
      </Pane>
      <Pane num="ii." title="Sent to upstream" caption="vault tokens only">
        {sanitised ? highlightSanitised(sanitised) : <span className="text-text-tertiary">—</span>}
      </Pane>
    </div>
  );
}
