'use client';

import { useCallback, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import type { LineageGraphData, LineageNode } from '@/lib/types';

/**
 * SVG DAG renderer for request lineage.
 *
 * Layout: longest-path layering left → right, vertically stacked within each
 * layer. No external graph library — for this scale (≤ ~30 nodes) the
 * straight-forward layered algorithm is faster and looks better than dagre.
 *
 * Interactions:
 *   - Hover a node     → highlight its incident edges, raise to the accent stroke.
 *   - Click a node     → invoke `onSelect`, copy the node id to the clipboard,
 *                        and announce "Copied node <id>" via the aria-live region.
 *   - Keyboard (Tab)   → focuses each node in DOM order; Enter copies & selects.
 *
 * The renderer is colour-coded by `kind`, with both light and dark themes
 * verified for AA contrast on the chip labels.
 */

const KIND_STYLE: Record<
  LineageNode['kind'],
  { bg: string; fg: string; glyph: string }
> = {
  prompt: { bg: 'bg-text-primary', fg: 'text-canvas', glyph: 'P' },
  retrieval: { bg: 'bg-canvas border border-text-primary', fg: 'text-text-primary', glyph: 'R' },
  tool: { bg: 'bg-canvas border border-warn', fg: 'text-warn', glyph: 'T' },
  output: { bg: 'bg-canvas border border-success', fg: 'text-success', glyph: 'O' },
  embedding: {
    bg: 'bg-surface-sunken',
    fg: 'text-text-secondary',
    glyph: 'E',
  },
  memory_write: { bg: 'bg-accent', fg: 'text-canvas', glyph: 'M' },
};

// Simple layered layout: assign each node a layer by longest path from any root.
function layoutGraph(g: LineageGraphData) {
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  g.nodes.forEach((n) => {
    incoming.set(n.id, []);
    outgoing.set(n.id, []);
  });
  g.edges.forEach((e) => {
    incoming.get(e.child_id)!.push(e.parent_id);
    outgoing.get(e.parent_id)!.push(e.child_id);
  });
  const layer = new Map<string, number>();
  function depth(id: string, seen = new Set<string>()): number {
    if (layer.has(id)) return layer.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const ins = incoming.get(id) ?? [];
    const d = ins.length === 0 ? 0 : 1 + Math.max(...ins.map((p) => depth(p, seen)));
    layer.set(id, d);
    return d;
  }
  g.nodes.forEach((n) => depth(n.id));
  const byLayer = new Map<number, string[]>();
  for (const [id, d] of layer.entries()) {
    if (!byLayer.has(d)) byLayer.set(d, []);
    byLayer.get(d)!.push(id);
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const colW = 220;
  const rowH = 90;
  const positions = new Map<string, { x: number; y: number }>();
  layers.forEach((d) => {
    const ids = byLayer.get(d)!;
    ids.forEach((id, i) => {
      positions.set(id, { x: 40 + d * colW, y: 40 + i * rowH });
    });
  });
  const width = 40 + (Math.max(...layers) + 1) * colW + 80;
  const maxCol = Math.max(...layers.map((d) => byLayer.get(d)!.length));
  const height = 40 + maxCol * rowH + 60;
  return { positions, width, height };
}

export function LineageGraph({
  data,
  onSelect,
  className,
}: {
  data: LineageGraphData;
  onSelect?: (n: LineageNode) => void;
  className?: string;
}) {
  const { positions, width, height } = useMemo(() => layoutGraph(data), [data]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [announce, setAnnounce] = useState('');

  const handleNode = useCallback(
    (n: LineageNode) => {
      onSelect?.(n);
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        void navigator.clipboard.writeText(n.id).then(() => {
          setAnnounce(`Copied node ${n.id}`);
          window.setTimeout(() => setAnnounce(''), 2500);
        });
      }
    },
    [onSelect],
  );

  return (
    <div className={cn('overflow-auto border border-border bg-canvas', className)}>
      <div role="status" aria-live="polite" className="sr-skip">
        {announce}
      </div>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Request lineage graph · ${data.nodes.length} nodes · ${data.edges.length} edges`}
        className="block"
      >
        {/* Edges */}
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" className="fill-current text-text-tertiary" />
          </marker>
        </defs>
        <g>
          {data.edges.map((e, i) => {
            const a = positions.get(e.parent_id);
            const b = positions.get(e.child_id);
            if (!a || !b) return null;
            const x1 = a.x + 168;
            const y1 = a.y + 28;
            const x2 = b.x;
            const y2 = b.y + 28;
            const cx = (x1 + x2) / 2;
            const path = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
            const active = hovered && (e.parent_id === hovered || e.child_id === hovered);
            const labelY = (y1 + y2) / 2 - 4;
            const label = e.relation;
            const labelW = label.length * 5.6 + 8;
            return (
              <g key={i}>
                <path
                  d={path}
                  className={cn(
                    'fill-none stroke-current',
                    active ? 'text-accent' : 'text-border-strong',
                  )}
                  strokeWidth={active ? 1.5 : 1}
                  strokeDasharray={active ? '0' : '3 3'}
                  markerEnd="url(#arrow)"
                />
                {/* Label bg to keep edges legible on dark theme too */}
                <rect
                  x={cx - labelW / 2}
                  y={labelY - 9}
                  width={labelW}
                  height={12}
                  className="fill-current text-canvas"
                />
                <text
                  x={cx}
                  y={labelY}
                  textAnchor="middle"
                  className={cn(
                    'fill-current text-[9.5px] font-mono',
                    active ? 'text-accent' : 'text-text-tertiary',
                  )}
                >
                  {label}
                </text>
              </g>
            );
          })}
        </g>
        {/* Nodes */}
        <g>
          {data.nodes.map((n) => {
            const p = positions.get(n.id)!;
            const s = KIND_STYLE[n.kind];
            return (
              <g
                key={n.id}
                transform={`translate(${p.x}, ${p.y})`}
                onMouseEnter={() => setHovered(n.id)}
                onMouseLeave={() => setHovered(null)}
                className="cursor-pointer"
              >
                <foreignObject width={168} height={56}>
                  <button
                    type="button"
                    data-lineage-node="true"
                    onClick={() => handleNode(n)}
                    onFocus={() => setHovered(n.id)}
                    onBlur={() => setHovered(null)}
                    aria-label={`${n.kind} · ${n.label}. Click to copy node id ${n.id}.`}
                    title={`${n.id} — click to copy`}
                    className={cn(
                      'flex h-full w-full items-center gap-2 border bg-canvas px-2.5 py-2 text-left transition-colors duration-fast',
                      hovered === n.id ? 'border-accent' : 'border-border',
                      'hover:bg-surface-sunken',
                    )}
                  >
                    <span
                      className={cn(
                        'flex h-7 w-7 shrink-0 items-center justify-center font-mono text-xs font-semibold',
                        s.bg,
                        s.fg,
                      )}
                      aria-hidden
                    >
                      {s.glyph}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[11.5px] font-mono text-text-primary">
                        {n.label}
                      </span>
                      <span className="block truncate text-[9.5px] font-mono uppercase tracking-[0.14em] text-text-tertiary">
                        {n.kind}
                      </span>
                    </span>
                  </button>
                </foreignObject>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
