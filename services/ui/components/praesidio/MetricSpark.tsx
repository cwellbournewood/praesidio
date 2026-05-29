import { cn } from '@/lib/utils';

export interface MetricSparkProps {
  data: number[];
  width?: number;
  height?: number;
  stroke?: string; // tailwind class for stroke colour, e.g. 'text-accent'
  fill?: string; // tailwind class for fill, e.g. 'text-accent/10'
  className?: string;
}

// A tiny inline sparkline. No axes, no labels — just shape.
export function MetricSpark({
  data,
  width = 120,
  height = 32,
  stroke = 'text-text-primary',
  fill = 'text-text-primary/10',
  className,
}: MetricSparkProps) {
  if (data.length === 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = data.length === 1 ? width : width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y] as const;
  });
  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${path} L${width},${height} L0,${height} Z`;
  return (
    <svg
      role="img"
      aria-hidden
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn('overflow-visible', className)}
    >
      <path d={area} className={cn('fill-current', fill)} stroke="none" />
      <path d={path} className={cn('fill-none stroke-current', stroke)} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
