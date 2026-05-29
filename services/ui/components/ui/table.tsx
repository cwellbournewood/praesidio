'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

export interface ColumnDef<R> {
  key: string;
  header: React.ReactNode;
  width?: string; // CSS width, e.g. '120px' or '1fr'
  cell: (row: R) => React.ReactNode;
  align?: 'left' | 'right' | 'center';
  className?: string;
}

export interface DataTableProps<R> {
  columns: ColumnDef<R>[];
  rows: R[];
  rowKey: (r: R) => string;
  onRowClick?: (r: R) => void;
  empty?: React.ReactNode;
  className?: string;
}

export function DataTable<R>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty,
  className,
}: DataTableProps<R>) {
  const template = columns.map((c) => c.width ?? '1fr').join(' ');
  return (
    <div
      role="table"
      className={cn(
        'w-full overflow-hidden border border-border bg-canvas font-mono text-[11.5px]',
        className,
      )}
    >
      <div
        role="row"
        className="grid border-b border-border bg-canvas px-3 h-8 items-center font-mono text-[9.5px] tracking-[0.14em] uppercase text-text-tertiary"
        style={{ gridTemplateColumns: template }}
      >
        {columns.map((c) => (
          <div
            key={c.key}
            role="columnheader"
            className={cn(
              'truncate',
              c.align === 'right' && 'text-right',
              c.align === 'center' && 'text-center',
            )}
          >
            {c.header}
          </div>
        ))}
      </div>
      <div role="rowgroup" className="divide-y divide-border">
        {rows.length === 0 && empty && (
          <div className="px-3 py-10 text-center text-sm text-text-secondary">{empty}</div>
        )}
        {rows.map((r) => (
          <div
            key={rowKey(r)}
            role="row"
            tabIndex={onRowClick ? 0 : -1}
            onClick={onRowClick ? () => onRowClick(r) : undefined}
            onKeyDown={
              onRowClick
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onRowClick(r);
                    }
                  }
                : undefined
            }
            className={cn(
              'grid items-center px-3 h-9 transition-colors duration-fast',
              onRowClick && 'cursor-pointer hover:bg-surface-sunken focus-visible:bg-surface-sunken',
            )}
            style={{ gridTemplateColumns: template }}
          >
            {columns.map((c) => (
              <div
                key={c.key}
                role="cell"
                className={cn(
                  'min-w-0 truncate',
                  c.align === 'right' && 'text-right justify-self-end',
                  c.align === 'center' && 'text-center justify-self-center',
                  c.className,
                )}
              >
                {c.cell(r)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
