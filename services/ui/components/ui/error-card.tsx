import * as React from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Inline error surface for SWR / fetch failures inside a page body.
 *
 * Differs from <EmptyState/> in tone (danger-coloured) and intent: an
 * empty state describes "no data yet, here's how to get some"; an error
 * card describes "we tried and it failed, here's the detail and the
 * next step". Use it whenever a fetch resolves to an error and the
 * page can still render its chrome.
 */
export interface ErrorCardProps {
  title: string;
  detail?: string;
  action?: React.ReactNode;
  docHref?: string;
  docLabel?: string;
  className?: string;
}

export function ErrorCard({
  title,
  detail,
  action,
  docHref,
  docLabel,
  className,
}: ErrorCardProps) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-start gap-3 rounded-md border border-danger/40 bg-danger/5 px-4 py-4',
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-danger"
          aria-hidden
          strokeWidth={1.75}
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-text-primary">{title}</p>
          {detail && (
            <p className="mt-1 break-words font-mono text-[11.5px] text-text-secondary">
              {detail}
            </p>
          )}
        </div>
      </div>
      {(action || docHref) && (
        <div className="flex items-center gap-3">
          {action}
          {docHref && (
            <Link
              href={docHref}
              className="inline-flex items-center gap-1 text-sm text-accent hover:underline"
            >
              {docLabel ?? 'Read the docs'}
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
