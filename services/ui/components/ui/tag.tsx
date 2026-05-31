import * as React from 'react';
import { cn } from '@/lib/utils';

export interface TagProps extends React.HTMLAttributes<HTMLSpanElement> {
  icon?: React.ReactNode;
}

// A flatter, more inline cousin of Badge — used inside dense tables.
export function Tag({ className, icon, children, ...props }: TagProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-xs border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-text-secondary',
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </span>
  );
}
