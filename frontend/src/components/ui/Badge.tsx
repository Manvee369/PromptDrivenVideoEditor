import React from 'react';
import { cn } from '@/lib/utils';
import type { JobStatus } from '@/types/job';
import { STATUS_LABELS } from '@/types/job';

type BadgeVariant = JobStatus | 'default';

interface BadgeProps {
  variant?: BadgeVariant;
  children?: React.ReactNode;
  className?: string;
  /** If true, auto-populates children from STATUS_LABELS for JobStatus variants. */
  status?: JobStatus;
}

const isProcessing = (v: BadgeVariant) =>
  ['preprocessing', 'intelligence', 'planning', 'rendering'].includes(v);

const variantStyles: Record<BadgeVariant, string> = {
  default:       'bg-[var(--surface-3)] text-[var(--text-secondary)]',
  created:       'bg-[var(--status-created-bg)] text-[var(--status-created)]',
  preprocessing: 'bg-[var(--status-processing-bg)] text-[var(--status-processing)]',
  intelligence:  'bg-[var(--status-processing-bg)] text-[var(--status-processing)]',
  planning:      'bg-[var(--status-processing-bg)] text-[var(--status-processing)]',
  rendering:     'bg-[var(--status-processing-bg)] text-[var(--status-processing)]',
  completed:     'bg-[var(--status-success-bg)] text-[var(--status-success)]',
  failed:        'bg-[var(--status-error-bg)] text-[var(--status-error)]',
};

const dotColors: Record<BadgeVariant, string> = {
  default:       'bg-[var(--text-tertiary)]',
  created:       'bg-[var(--status-created)]',
  preprocessing: 'bg-[var(--status-processing)]',
  intelligence:  'bg-[var(--status-processing)]',
  planning:      'bg-[var(--status-processing)]',
  rendering:     'bg-[var(--status-processing)]',
  completed:     'bg-[var(--status-success)]',
  failed:        'bg-[var(--status-error)]',
};

export function Badge({ variant = 'default', status, children, className }: BadgeProps) {
  const resolvedVariant: BadgeVariant = status ?? variant;
  const label = children ?? (status ? STATUS_LABELS[status] : undefined);
  const pulse  = isProcessing(resolvedVariant);

  return (
    <span
      aria-label={status ? `Status: ${STATUS_LABELS[status]}` : undefined}
      className={cn(
        'inline-flex items-center gap-1.5',
        'px-2.5 py-0.5 rounded-[var(--radius-full)]',
        'text-xs font-medium leading-5 select-none',
        variantStyles[resolvedVariant],
        className,
      )}
    >
      <span
        className={cn(
          'inline-block h-1.5 w-1.5 rounded-full shrink-0',
          dotColors[resolvedVariant],
          pulse && 'animate-pulse-dot',
        )}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}
