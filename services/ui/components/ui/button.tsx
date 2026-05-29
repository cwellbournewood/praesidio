'use client';

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap font-mono tracking-ui transition-colors duration-fast ease-standard disabled:pointer-events-none disabled:opacity-50 border',
  {
    variants: {
      variant: {
        primary:
          'bg-text-primary text-canvas border-text-primary hover:bg-text-secondary hover:border-text-secondary',
        secondary:
          'bg-canvas text-text-primary border-border hover:bg-surface-sunken',
        ghost:
          'bg-transparent text-text-secondary border-transparent hover:bg-surface-sunken hover:text-text-primary',
        danger:
          'bg-accent text-canvas border-accent hover:bg-accent-hover hover:border-accent-hover',
        link:
          'bg-transparent text-accent border-transparent hover:underline underline-offset-2 px-0',
      },
      size: {
        xs: 'h-6 px-2 text-[10.5px]',
        sm: 'h-7 px-2.5 text-[11px]',
        md: 'h-8 px-3 text-[12px]',
        lg: 'h-9 px-4 text-[12.5px]',
        icon: 'h-7 w-7',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
    );
  },
);
Button.displayName = 'Button';
