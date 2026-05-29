import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 border px-1.5 h-[18px] font-mono text-[10.5px] tracking-[0.04em] uppercase whitespace-nowrap',
  {
    variants: {
      tone: {
        neutral: 'bg-canvas text-text-secondary border-border',
        accent: 'bg-canvas text-accent border-accent',
        success: 'bg-canvas text-success border-success',
        warn: 'bg-canvas text-warn border-warn',
        block: 'bg-accent text-canvas border-accent',
        danger: 'bg-canvas text-danger border-danger',
        info: 'bg-canvas text-info border-info',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
