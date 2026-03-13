import React from 'react';
import { cn } from '@/lib/utils';
import { PIPELINE_STAGES } from '@/types/job';
import type { JobStatus } from '@/types/job';
import { Spinner } from '@/components/ui/Spinner';

interface StageTimelineProps {
  status: JobStatus;
  className?: string;
}

type StageState = 'completed' | 'active' | 'pending' | 'error';

/** Map the running job status to which pipeline index is active. */
const STATUS_TO_STAGE_INDEX: Partial<Record<JobStatus, number>> = {
  created:       -1,
  preprocessing:  0,
  intelligence:   1,
  planning:       2,
  rendering:      3,
  completed:      4,
  failed:        -2, // special error state
};

function getStageState(stageIdx: number, activeIdx: number, isError: boolean): StageState {
  if (isError) return stageIdx <= activeIdx ? 'error' : 'pending';
  if (stageIdx < activeIdx)  return 'completed';
  if (stageIdx === activeIdx) return 'active';
  return 'pending';
}

export function StageTimeline({ status, className }: StageTimelineProps) {
  const isError   = status === 'failed';
  const activeIdx = STATUS_TO_STAGE_INDEX[status] ?? -1;

  return (
    <ol
      aria-label="Pipeline stages"
      className={cn('flex flex-col gap-0', className)}
    >
      {PIPELINE_STAGES.map((stage, idx) => {
        const state = getStageState(idx, activeIdx, isError);
        const isLast = idx === PIPELINE_STAGES.length - 1;

        return (
          <li key={stage.key} className="flex gap-3">
            {/* Left: icon + connector line */}
            <div className="flex flex-col items-center">
              <StageIcon state={state} />
              {!isLast && (
                <div
                  className={cn(
                    'w-px flex-1 mt-1 mb-1 min-h-[20px]',
                    state === 'completed'
                      ? 'bg-[var(--accent)]'
                      : 'bg-[var(--border)]',
                  )}
                />
              )}
            </div>

            {/* Right: text */}
            <div className={cn('pb-5', isLast && 'pb-0')}>
              <p
                className={cn(
                  'text-sm font-medium leading-tight',
                  state === 'active'    && 'text-[var(--accent)]',
                  state === 'completed' && 'text-[var(--text-primary)]',
                  state === 'pending'   && 'text-[var(--text-tertiary)]',
                  state === 'error'     && 'text-[var(--status-error)]',
                )}
              >
                {stage.label}
              </p>
              {state === 'active' && (
                <p className="mt-0.5 text-xs text-[var(--text-secondary)] animate-fade-in">
                  {stage.sublabel}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StageIcon({ state }: { state: StageState }) {
  const base = 'flex items-center justify-center w-5 h-5 rounded-full shrink-0 mt-0.5';

  if (state === 'active') {
    return (
      <div className={cn(base, 'bg-[var(--accent-subtle)] border border-[var(--accent)]')}>
        <Spinner size="sm" className="text-[var(--accent)] w-3 h-3" />
      </div>
    );
  }

  if (state === 'completed') {
    return (
      <div className={cn(base, 'bg-[var(--accent)] border border-[var(--accent)]')}>
        <CheckIcon />
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className={cn(base, 'bg-[var(--status-error-bg)] border border-[var(--status-error)]')}>
        <ErrorIcon />
      </div>
    );
  }

  // pending
  return (
    <div className={cn(base, 'bg-[var(--surface-3)] border border-[var(--border)]')}>
      <span className="w-1.5 h-1.5 rounded-full bg-[var(--border-strong)]" />
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
         stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
         stroke="var(--status-error)" strokeWidth="3" strokeLinecap="round"
         aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
