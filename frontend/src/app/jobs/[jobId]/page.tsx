'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { cn, formatRelativeTime, shortId, progressPercent } from '@/lib/utils';
import { useJob } from '@/lib/hooks/useJob';
import { getExplanation, getThumbnailUrl, getVideoUrl } from '@/lib/api';
import type { JobExplanation } from '@/types/job';
import { STATUS_LABELS } from '@/types/job';

import { Badge }                  from '@/components/ui/Badge';
import { Card }                   from '@/components/ui/Card';
import { ProgressBar }            from '@/components/ui/ProgressBar';
import { ProgressRing }           from '@/components/ui/ProgressRing';
import { Spinner }                from '@/components/ui/Spinner';
import { Button }                 from '@/components/ui/Button';
import { StageTimeline }          from '@/components/job/StageTimeline';
import { ExplanationAccordion }   from '@/components/job/ExplanationAccordion';
import { VideoPlayer }            from '@/components/job/VideoPlayer';
import { StatGrid }               from '@/components/job/StatGrid';
import { PromptDisplay }          from '@/components/job/PromptDisplay';

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, loading, error } = useJob(jobId);

  const isComplete = job?.status === 'completed';
  const isFailed   = job?.status === 'failed';
  const isActive   = job !== null && !isComplete && !isFailed;

  if (loading && !job) {
    return <PageSkeleton />;
  }

  if (error || !job) {
    return (
      <div className="px-6 py-10 max-w-3xl mx-auto animate-fade-in">
        <ErrorState message={error ?? 'Job not found'} />
      </div>
    );
  }

  return (
    <div className="px-6 py-10 max-w-5xl mx-auto animate-fade-in">
      {/* Page header */}
      <header className="flex items-start justify-between gap-4 mb-8 flex-wrap">
        <div className="flex flex-col gap-2">
          <Link
            href="/history"
            className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <ChevronLeftIcon />
            Back to History
          </Link>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold text-[var(--text-primary)] font-mono">
              {shortId(job.job_id)}
            </h1>
            <Badge status={job.status} />
          </div>
          <p className="text-xs text-[var(--text-tertiary)]">
            {isComplete && 'Completed '}
            {isFailed   && 'Failed '}
            {isActive   && 'Started '}
            {formatRelativeTime(job.updated_at)}
          </p>
        </div>

        {isComplete && (
          <a
            href={getVideoUrl(jobId)}
            download={`edited_${shortId(jobId)}.mp4`}
            className={cn(
              'inline-flex items-center gap-2 px-4 h-9 rounded-[var(--radius-md)]',
              'bg-[var(--accent)] text-white text-sm font-medium',
              'hover:bg-[var(--accent-hover)] active:bg-[var(--accent-active)]',
              'transition-colors duration-[var(--duration-fast)]',
            )}
          >
            <DownloadIcon />
            Download Video
          </a>
        )}
      </header>

      {/* Prompt */}
      <div className="mb-8">
        <PromptDisplay prompt={job.prompt} />
      </div>

      {/* ─── ACTIVE STATE ─── */}
      {isActive && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
          {/* Main: ring + bar */}
          <Card className="flex flex-col items-center gap-6 py-10">
            <ProgressRing
              value={job.progress}
              size={180}
              strokeWidth={10}
              label={STATUS_LABELS[job.status]}
              sublabel="in progress"
            />
            <div className="w-full max-w-sm">
              <ProgressBar
                value={job.progress}
                active
                label={`Pipeline progress: ${progressPercent(job.progress)}`}
              />
              <p className="mt-2 text-center text-xs text-[var(--text-tertiary)] tabular-nums">
                {progressPercent(job.progress)} complete
              </p>
            </div>
            <p className="text-xs text-[var(--text-tertiary)] animate-pulse-dot">
              Analyzing your video — this may take a few minutes...
            </p>
          </Card>

          {/* Sidebar: stage timeline */}
          <Card className="flex flex-col gap-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Pipeline stages</h2>
            <StageTimeline status={job.status} />
          </Card>
        </div>
      )}

      {/* ─── FAILED STATE ─── */}
      {isFailed && (
        <Card className="border-[var(--status-error)] bg-[var(--status-error-bg)]">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-[var(--status-error)]">
              <ErrorCircleIcon />
              <span className="font-semibold text-sm">Pipeline failed</span>
            </div>
            {job.error && (
              <p className="text-sm text-[var(--text-secondary)] font-mono leading-relaxed">
                {job.error}
              </p>
            )}
            <Link href="/">
              <Button variant="secondary" size="sm" className="mt-2">
                Try again with a new job
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {/* ─── COMPLETED STATE ─── */}
      {isComplete && <CompletedView jobId={jobId} />}
    </div>
  );
}

/* ─── Completed view ─────────────────────────────────────────────────────── */

function CompletedView({ jobId }: { jobId: string }) {
  const [explanation, setExplanation] = useState<JobExplanation | null>(null);
  const [expLoading, setExpLoading]   = useState(true);

  useEffect(() => {
    getExplanation(jobId)
      .then(setExplanation)
      .catch(() => setExplanation(null))
      .finally(() => setExpLoading(false));
  }, [jobId]);

  return (
    <div className="flex flex-col gap-6 animate-slide-up">
      {/* Video + stats row */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-6 items-start">
        <VideoPlayer jobId={jobId} />

        <div className="flex flex-col gap-4">
          {/* Thumbnail */}
          <div className="rounded-[var(--radius-lg)] overflow-hidden border border-[var(--border)] bg-[var(--surface-2)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={getThumbnailUrl(jobId)}
              alt="Generated thumbnail"
              className="w-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
          </div>

          {/* Stats */}
          {explanation?.stats && (
            <StatGrid stats={explanation.stats} />
          )}
        </div>
      </div>

      {/* AI explanation */}
      <Card>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              How the AI edited your video
            </h2>
            {explanation?.summary && (
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                {explanation.summary}
              </p>
            )}
          </div>

          {expLoading ? (
            <div className="flex items-center gap-2 py-4 text-[var(--text-tertiary)]">
              <Spinner size="sm" />
              <span className="text-sm">Loading decisions...</span>
            </div>
          ) : explanation?.decisions ? (
            <ExplanationAccordion decisions={explanation.decisions} />
          ) : (
            <p className="text-sm text-[var(--text-tertiary)]">
              Explanation not available for this job.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

/* ─── Page skeleton ──────────────────────────────────────────────────────── */

function PageSkeleton() {
  return (
    <div className="px-6 py-10 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Skeleton className="h-7 w-24 rounded-[var(--radius-md)]" />
        <Skeleton className="h-5 w-20 rounded-[var(--radius-full)]" />
      </div>
      <Skeleton className="h-10 w-full max-w-sm rounded-[var(--radius-md)] mb-8" />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
        <Skeleton className="h-72 rounded-[var(--radius-lg)]" />
        <Skeleton className="h-72 rounded-[var(--radius-lg)]" />
      </div>
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

/* ─── Error state ────────────────────────────────────────────────────────── */

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-4 py-20 text-center">
      <div className="text-[var(--status-error)]">
        <ErrorCircleIcon size={40} />
      </div>
      <p className="text-sm text-[var(--text-secondary)]">{message}</p>
      <Link href="/">
        <Button variant="secondary" size="sm">Go back</Button>
      </Link>
    </div>
  );
}

/* ─── Icons ──────────────────────────────────────────────────────────────── */

function ChevronLeftIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function ErrorCircleIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  );
}
