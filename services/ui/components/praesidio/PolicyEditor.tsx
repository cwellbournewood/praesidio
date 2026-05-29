'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';

// MVP: read-only YAML viewer with lightweight syntax tinting. Write-mode
// (edit + dry-run + open PR) is tracked in TODO and not built here — see
// docs/architecture/03-policy-engine.md §"Why YAML": policy edits ship as
// PRs, never live mutations from the UI.
function tint(line: string, i: number) {
  // Comment
  if (/^\s*#/.test(line)) {
    return <span className="text-text-tertiary">{line}</span>;
  }
  // key: value
  const m = line.match(/^(\s*[-]?\s*)([A-Za-z0-9_\-\.]+)(:\s*)(.*)$/);
  if (m) {
    const [, indent, key, sep, rest] = m;
    return (
      <>
        <span>{indent}</span>
        <span className="text-accent">{key}</span>
        <span className="text-text-tertiary">{sep}</span>
        <span className="text-text-primary">{rest}</span>
      </>
    );
  }
  // list item
  if (/^\s*-\s/.test(line)) {
    return (
      <>
        <span className="text-warn">{line.match(/^\s*-/)?.[0]}</span>
        <span>{line.replace(/^\s*-/, '')}</span>
      </>
    );
  }
  return <span>{line}</span>;
}

export function PolicyEditor({ yaml, className }: { yaml: string; className?: string }) {
  const lines = useMemo(() => yaml.split('\n'), [yaml]);
  return (
    <div className={cn('overflow-hidden border border-border bg-canvas', className)}>
      <div className="flex items-center justify-between border-b border-border bg-canvas px-3 h-9 font-mono text-[10.5px] tracking-[0.14em] uppercase text-text-tertiary">
        <span className="flex items-baseline gap-2">
          <span className="font-serif italic text-[13px] normal-case tracking-normal text-text-tertiary">
            §
          </span>
          policy.yaml
        </span>
        <span className="text-text-tertiary">read-only · edits ship as PR</span>
      </div>
      <pre className="overflow-auto p-3 font-mono text-[12px] leading-[1.6] text-text-primary">
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[36px_1fr]">
            <span className="select-none pr-3 text-right text-text-tertiary tabular-nums">{i + 1}</span>
            <span className="whitespace-pre">{tint(l, i)}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}
