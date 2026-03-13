import React from 'react';
import { cn } from '@/lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Adds an interactive hover effect. */
  hoverable?: boolean;
  /** Remove internal padding (useful for tight layouts or custom padding). */
  noPadding?: boolean;
}

export function Card({ hoverable, noPadding, className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'bg-[var(--surface-1)] border border-[var(--border)]',
        'rounded-[var(--radius-lg)] shadow-[var(--shadow-sm)]',
        !noPadding && 'p-5',
        hoverable && [
          'cursor-pointer',
          'transition-all duration-[var(--duration-base)] ease-[var(--ease-out)]',
          'hover:shadow-[var(--shadow-md)] hover:border-[var(--border-strong)]',
          'hover:bg-[var(--surface-2)]',
        ],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/** Lightweight divider for use inside cards. */
export function CardDivider({ className }: { className?: string }) {
  return (
    <hr
      className={cn(
        'border-0 border-t border-[var(--border-subtle)] my-4',
        className,
      )}
    />
  );
}
