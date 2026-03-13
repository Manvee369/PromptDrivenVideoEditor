'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { cn, formatRelativeTime, shortId, truncate, formatDuration } from '@/lib/utils';
import { useJobs } from '@/lib/hooks/useJobs';
import type { JobRecord, JobStatus } from '@/types/job';
import { STATUS_LABELS } from '@/types/job';
import { Badge }    from '@/components/ui/Badge';
import { Button }   from '@/components/ui/Button';
import { Input }    from '@/components/ui/Input';
import { Spinner }  from '@/components/ui/Spinner';
import { getThumbnailUrl } from '@/lib/api';

type FilterTab = 'all' | JobStatus;

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: 'all',       label: 'All' },
  { key: 'rendering', label: 'Processing' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed',    label: 'Failed' },
];

export default function HistoryPage() {
  const { jobs, loading, error } = useJobs(true);
  const [filter, setFilter]     = useState<FilterTab>('all');
  const [search, setSearch]     = useState('');

  const filtered = useMemo(() => {
    let result = jobs;

    if (filter === 'rendering') {
      result = result.filter((j) =>
        ['preprocessing', 'intelligence', 'planning', 'rendering', 'created'].includes(j.status),
      );
    } else if (filter !== 'all') {
      result = result.filter((j) => j.status === filter);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (j) =>
          j.prompt.toLowerCase().includes(q) ||
          j.job_id.toLowerCase().includes(q),
      );
    }

    return result;
  }, [jobs, filter, search]);

  return (
    <div className="px-6 py-10 max-w-5xl mx-auto animate-fade-in">
      {/* Header */}
      <header className="flex items-center justify-between gap-4 mb-8 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Job History</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            All your editing jobs, sorted newest first.
          </p>
        </div>
        <Link href="/">
          <Button variant="secondary" size="sm" leftIcon={<PlusIcon />}>
            New Edit
          </Button>
        </Link>
      </header>

      {/* Filter bar */}
      <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
        {/* Tab filters */}
        <div
          className="flex items-center gap-1 p-1 rounded-[var(--radius-lg)] bg-[var(--surface-2)] border border-[var(--border)]"
          role="tablist"
          aria-label="Filter jobs by status"
        >
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={filter === tab.key}
              onClick={() => setFilter(tab.key)}
              className={cn(
                'px-3 h-7 text-xs font-medium rounded-[var(--radius-md)]',
                'transition-all duration-[var(--duration-fast)]',
                'focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--accent)]',
                filter === tab.key
                  ? 'bg-[var(--surface-1)] text-[var(--text-primary)] shadow-[var(--shadow-sm)]'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="w-52">
          <Input
            placeholder="Search prompt or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<SearchIcon />}
            aria-label="Search jobs"
          />
        </div>
      </div>

      {/* Table / content */}
      {loading && jobs.length === 0 ? (
        <LoadingSkeleton />
      ) : error ? (
        <ErrorState message={error} />
      ) : filtered.length === 0 ? (
        <EmptyState hasJobs={jobs.length > 0} />
      ) : (
        <JobTable jobs={filtered} />
      )}
    </div>
  );
}

/* ─── Job table ──────────────────────────────────────────────────────────── */

function JobTable({ jobs }: { jobs: JobRecord[] }) {
  return (
    <div
      className="rounded-[var(--radius-lg)] border border-[var(--border)] overflow-hidden"
      role="table"
      aria-label="Jobs list"
    >
      {/* Header */}
      <div
        role="row"
        className="grid grid-cols-[64px_1fr_120px_100px_100px] gap-4 items-center
                   px-4 h-9 border-b border-[var(--border-subtle)]
                   bg-[var(--surface-2)]"
      >
        {['', 'Prompt', 'Status', 'Duration', 'When'].map((col) => (
          <span
            key={col}
            role="columnheader"
            className="text-2xs uppercase tracking-widest font-semibold text-[var(--text-tertiary)]"
          >
            {col}
          </span>
        ))}
      </div>

      {/* Rows */}
      <div role="rowgroup">
        {jobs.map((job, idx) => (
          <JobRow key={job.job_id} job={job} isLast={idx === jobs.length - 1} />
        ))}
      </div>
    </div>
  );
}

function JobRow({ job, isLast }: { job: JobRecord; isLast: boolean }) {
  const thumbSrc = job.status === 'completed' ? getThumbnailUrl(job.job_id) : null;

  return (
    <Link
      href={`/jobs/${job.job_id}`}
      role="row"
      className={cn(
        'grid grid-cols-[64px_1fr_120px_100px_100px] gap-4 items-center',
        'px-4 py-3 bg-[var(--surface-1)]',
        'transition-colors duration-[var(--duration-fast)]',
        'hover:bg-[var(--surface-2)]',
        'focus-visible:outline-none focus-visible:bg-[var(--accent-subtle)]',
        !isLast && 'border-b border-[var(--border-subtle)]',
      )}
      aria-label={`Job ${shortId(job.job_id)}: ${job.prompt}`}
    >
      {/* Thumbnail */}
      <div role="cell" className="w-16 h-9 rounded-[var(--radius-sm)] overflow-hidden bg-[var(--surface-3)] shrink-0">
        {thumbSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbSrc} alt="" className="w-full h-full object-cover" />
        ) : (
          <ThumbnailPlaceholder active={!['completed', 'failed'].includes(job.status)} />
        )}
      </div>

      {/* Prompt */}
      <div role="cell" className="min-w-0 flex flex-col gap-0.5">
        <p className="text-sm text-[var(--text-primary)] line-clamp-1">
          {truncate(job.prompt, 80)}
        </p>
        <p className="text-xs font-mono text-[var(--text-tertiary)]">{shortId(job.job_id)}</p>
      </div>

      {/* Status */}
      <div role="cell">
        <Badge status={job.status} />
      </div>

      {/* Duration */}
      <div role="cell" className="text-sm tabular-nums text-[var(--text-secondary)]">
        —
      </div>

      {/* When */}
      <div role="cell" className="text-xs text-[var(--text-tertiary)] whitespace-nowrap">
        {formatRelativeTime(job.created_at)}
      </div>
    </Link>
  );
}

/* ─── Sub-components ─────────────────────────────────────────────────────── */

function ThumbnailPlaceholder({ active }: { active: boolean }) {
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

function LoadingSkeleton() {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] overflow-hidden">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'grid grid-cols-[64px_1fr_120px_100px_100px] gap-4 items-center px-4 py-3',
            i < 4 && 'border-b border-[var(--border-subtle)]',
          )}
        >
          <Skeleton className="h-9 w-16 rounded-[var(--radius-sm)]" />
          <Skeleton className="h-4 rounded-[var(--radius-sm)]" />
          <Skeleton className="h-5 w-20 rounded-[var(--radius-full)]" />
          <Skeleton className="h-4 w-8 rounded-[var(--radius-sm)]" />
          <Skeleton className="h-4 w-16 rounded-[var(--radius-sm)]" />
        </div>
      ))}
    </div>
  );
}

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-shimmer bg-[length:200%_100%]',
        '[background-image:linear-gradient(90deg,var(--surface-2)_0%,var(--surface-3)_50%,var(--surface-2)_100%)]',
        className,
      )}
      aria-hidden="true"
    />
  );
}

function EmptyState({ hasJobs }: { hasJobs: boolean }) {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <div className="flex items-center justify-center w-12 h-12 rounded-[var(--radius-xl)] bg-[var(--surface-2)] text-[var(--text-tertiary)]">
        <HistoryIcon />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          {hasJobs ? 'No jobs match your filter' : 'No jobs yet'}
        </p>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          {hasJobs
            ? 'Try adjusting your search or filter.'
            : 'Start your first edit to see it here.'}
        </p>
      </div>
      {!hasJobs && (
        <Link href="/">
          <Button variant="primary" size="sm">Start your first edit</Button>
        </Link>
      )}
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="text-sm text-[var(--status-error)]">{message}</p>
    </div>
  );
}

/* ─── Icons ──────────────────────────────────────────────────────────────── */

const si = {
  width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const, 'aria-hidden': true,
};

const PlusIcon    = () => <svg {...si}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
const SearchIcon  = () => <svg {...si}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>;
const HistoryIcon = () => <svg width={24} height={24} viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round"
                                aria-hidden="true"><polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 0 .5-4.5"/><polyline points="3 2 3 7 8 7"/></svg>;
