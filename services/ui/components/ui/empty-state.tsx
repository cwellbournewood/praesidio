import * as React from 'react';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  action?: React.ReactNode;
  docHref?: string;
  docLabel?: string;
  className?: string;
}

export function EmptyState({ icon, title, action, docHref, docLabel, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-surface px-6 py-12 text-center',
        className,
      )}
    >
      {icon && <div className="text-text-tertiary">{icon}</div>}
      <p className="max-w-md text-sm text-text-secondary">{title}</p>
      <div className="flex items-center gap-3">
        {action}
        {docHref && (
          <Link
            href={docHref}
            className="inline-flex items-center gap-1 text-sm text-accent hover:underline"
          >
            {docLabel ?? 'Read the docs'}
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
    </div>
  );
}
