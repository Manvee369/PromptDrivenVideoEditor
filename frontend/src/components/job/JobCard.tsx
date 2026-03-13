import React from 'react';
import Link from 'next/link';
import { cn, formatRelativeTime, truncate, shortId } from '@/lib/utils';
import type { JobRecord } from '@/types/job';
import { Badge } from '@/components/ui/Badge';
import { getThumbnailUrl } from '@/lib/api';

interface JobCardProps {
  job: JobRecord;
  compact?: boolean;
  className?: string;
}

export function JobCard({ job, compact, className }: JobCardProps) {
  const thumbSrc = job.status === 'completed' ? getThumbnailUrl(job.job_id) : null;

  return (
    <Link
      href={`/jobs/${job.job_id}`}
      className={cn(
        'flex items-start gap-3 rounded-[var(--radius-lg)]',
        'border border-[var(--border)] bg-[var(--surface-1)]',
        'transition-all duration-[var(--duration-base)] ease-[var(--ease-out)]',
        'hover:bg-[var(--surface-2)] hover:border-[var(--border-strong)] hover:shadow-[var(--shadow-sm)]',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--accent)]',
        compact ? 'p-3' : 'p-4',
        className,
      )}
      aria-label={`Job ${shortId(job.job_id)}: ${job.prompt}`}
    >
      {/* Thumbnail */}
      {!compact && (
        <div className="shrink-0 w-20 h-12 rounded-[var(--radius-md)] overflow-hidden bg-[var(--surface-3)]">
          {thumbSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumbSrc}
              alt={`Thumbnail for job ${shortId(job.job_id)}`}
              className="w-full h-full object-cover"
            />
          ) : (
            <ThumbnailSkeleton active={job.status !== 'completed' && job.status !== 'failed'} />
          )}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="font-mono text-xs text-[var(--text-tertiary)]">
            {shortId(job.job_id)}
          </span>
          <Badge status={job.status} />
        </div>

        <p className="text-sm text-[var(--text-secondary)] line-clamp-2 leading-snug">
          {truncate(job.prompt, compact ? 60 : 120)}
        </p>

        <p className="text-xs text-[var(--text-tertiary)]">
          {formatRelativeTime(job.updated_at)}
        </p>
      </div>
    </Link>
  );
}

function ThumbnailSkeleton({ active }: { active: boolean }) {
  return (
    <div
      className={cn(
        'w-full h-full',
        active
          ? 'animate-shimmer bg-[length:200%_100%] [background-image:linear-gradient(90deg,var(--surface-3)_0%,var(--surface-4)_50%,var(--surface-3)_100%)]'
          : 'bg-[var(--surface-3)]',
      )}
      aria-hidden="true"
    />
  );
}
