import React from 'react';
import { cn } from '@/lib/utils';
import type { ExplanationStats } from '@/types/job';
import { formatDuration } from '@/lib/utils';

interface StatGridProps {
  stats: ExplanationStats;
  className?: string;
}

export function StatGrid({ stats, className }: StatGridProps) {
  const items = [
    { label: 'Output Duration', value: formatDuration(stats.output_duration) },
    { label: 'Input Duration',  value: formatDuration(stats.input_duration) },
    { label: 'Clips',           value: String(stats.output_clips) },
    { label: 'Captions',        value: String(stats.captions) },
    { label: 'Format',          value: stats.format },
    { label: 'Compression',     value: stats.compression_ratio },
  ];

  return (
    <div
      className={cn('grid grid-cols-2 gap-px bg-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden', className)}
      aria-label="Job statistics"
    >
      {items.map(({ label, value }) => (
        <div
          key={label}
          className="flex flex-col gap-1 p-4 bg-[var(--surface-1)]"
        >
          <span className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide font-medium">
            {label}
          </span>
          <span className="text-lg font-bold tabular-nums text-[var(--text-primary)]">
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}
