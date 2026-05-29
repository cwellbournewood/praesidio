import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function Breadcrumb({ items, className }: { items: BreadcrumbItem[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={cn('flex items-center font-mono text-[11px] text-text-tertiary', className)}>
      <ol className="flex items-center gap-1">
        {items.map((it, i) => (
          <li key={`${it.label}-${i}`} className="flex items-center gap-1">
            {it.href ? (
              <Link href={it.href} className="hover:text-text-primary">
                {it.label}
              </Link>
            ) : (
              <span className="text-text-primary">{it.label}</span>
            )}
            {i < items.length - 1 && (
              <ChevronRight className="h-3.5 w-3.5 text-text-tertiary" aria-hidden />
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
