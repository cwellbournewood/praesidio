'use client';

import * as React from 'react';
import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Sheet = RadixDialog.Root;
export const SheetTrigger = RadixDialog.Trigger;
export const SheetClose = RadixDialog.Close;

export function SheetContent({
  className,
  children,
  side = 'right',
  ...props
}: React.ComponentPropsWithoutRef<typeof RadixDialog.Content> & { side?: 'right' | 'left' }) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-50 bg-text-primary/20 animate-fade-in" />
      <RadixDialog.Content
        className={cn(
          'fixed top-0 z-50 h-full w-full max-w-[640px] border-l border-border bg-canvas',
          'flex flex-col',
          'animate-slide-in-right',
          side === 'right' ? 'right-0' : 'left-0 border-l-0 border-r',
          className,
        )}
        {...props}
      >
        {children}
        <RadixDialog.Close
          aria-label="Close"
          className="absolute right-3 top-3 rounded-sm p-1 text-text-tertiary hover:bg-surface-sunken hover:text-text-primary"
        >
          <X className="h-4 w-4" />
        </RadixDialog.Close>
      </RadixDialog.Content>
    </RadixDialog.Portal>
  );
}

export function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('border-b border-border px-5 py-4 flex items-start justify-between gap-4', className)}
      {...props}
    />
  );
}

export function SheetBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex-1 overflow-y-auto px-5 py-4', className)} {...props} />;
}

export function SheetFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('border-t border-border px-5 py-3 flex items-center justify-end gap-2', className)} {...props} />
  );
}

export function SheetTitle({ className, ...props }: React.ComponentPropsWithoutRef<typeof RadixDialog.Title>) {
  return <RadixDialog.Title className={cn('font-serif text-xl tracking-display text-text-primary', className)} {...props} />;
}

export function SheetDescription({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof RadixDialog.Description>) {
  return <RadixDialog.Description className={cn('text-sm text-text-secondary', className)} {...props} />;
}
