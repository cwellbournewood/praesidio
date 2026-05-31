'use client';

import * as React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface CheckboxProps {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  id?: string;
  disabled?: boolean;
  'aria-label'?: string;
  className?: string;
}

export function Checkbox({ checked, onCheckedChange, id, disabled, className, ...aria }: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      id={id}
      aria-checked={checked}
      aria-label={aria['aria-label']}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        'inline-flex h-4 w-4 items-center justify-center rounded-xs border transition-colors duration-fast',
        checked ? 'bg-accent border-accent text-white' : 'bg-surface border-border-strong',
        disabled && 'opacity-50 cursor-not-allowed',
        className,
      )}
    >
      {checked && <Check className="h-3 w-3" strokeWidth={3} />}
    </button>
  );
}
