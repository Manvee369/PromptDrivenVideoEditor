import React from 'react';
import { cn } from '@/lib/utils';

interface ProgressBarProps {
  /** Value from 0 to 1. */
  value: number;
  /** Show the animated shimmer (use while actively processing). */
  active?: boolean;
  className?: string;
  label?: string;
}

export function ProgressBar({ value, active, className, label }: ProgressBarProps) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);

  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? `Progress: ${pct}%`}
      className={cn('relative h-1 w-full rounded-full bg-[var(--surface-3)] overflow-hidden', className)}
    >
      <div
        className={cn(
          'h-full rounded-full',
          'transition-[width] duration-[600ms] ease-[var(--ease-out)]',
          active
            ? [
                'animate-shimmer',
                'bg-[length:200%_100%]',
                '[background-image:linear-gradient(90deg,var(--accent)_0%,var(--accent-hover)_50%,var(--accent)_100%)]',
              ]
            : 'bg-[var(--accent)]',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
