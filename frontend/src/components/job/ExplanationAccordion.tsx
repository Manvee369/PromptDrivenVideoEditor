'use client';

import React, { useId, useState } from 'react';
import { cn, capitalize } from '@/lib/utils';
import type { ExplanationDecision } from '@/types/job';

interface ExplanationAccordionProps {
  decisions: ExplanationDecision[];
  defaultOpenIndex?: number;
  className?: string;
}

export function ExplanationAccordion({
  decisions,
  defaultOpenIndex = 0,
  className,
}: ExplanationAccordionProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(defaultOpenIndex);
  const baseId = useId();

  return (
    <div
      className={cn('flex flex-col divide-y divide-[var(--border-subtle)]', className)}
      role="list"
    >
      {decisions.map((decision, idx) => {
        const isOpen   = openIndex === idx;
        const headerId = `${baseId}-h-${idx}`;
        const panelId  = `${baseId}-p-${idx}`;

        return (
          <div key={idx} role="listitem">
            {/* Header button */}
            <button
              id={headerId}
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => setOpenIndex(isOpen ? null : idx)}
              className={cn(
                'flex w-full items-center justify-between gap-3',
                'py-3.5 text-left',
                'transition-colors duration-[var(--duration-fast)]',
                'hover:text-[var(--text-primary)] focus-visible:outline-none',
                isOpen ? 'text-[var(--text-primary)]' : 'text-[var(--text-secondary)]',
              )}
            >
              <div className="flex items-center gap-2.5">
                <StageIcon stage={decision.stage} />
                <span className="text-sm font-medium">
                  {capitalize(decision.stage)}
                </span>
              </div>
              <ChevronIcon
                className={cn(
                  'shrink-0 text-[var(--text-tertiary)]',
                  'transition-transform duration-[var(--duration-base)] ease-[var(--ease-out)]',
                  isOpen && 'rotate-180',
                )}
              />
            </button>

            {/* Collapsible panel — uses CSS grid trick for smooth height animation */}
            <div
              id={panelId}
              role="region"
              aria-labelledby={headerId}
              aria-hidden={!isOpen}
              className={cn(
                'grid transition-all duration-[220ms] ease-[var(--ease-in-out)]',
                isOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
              )}
            >
              <div className="overflow-hidden">
                <p className="pb-4 text-sm leading-relaxed text-[var(--text-secondary)]">
                  {decision.detail}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Maps a stage name to a small colored stage indicator dot. */
function StageIcon({ stage }: { stage: string }) {
  const colors: Record<string, string> = {
    planning:          'bg-[var(--accent)]',
    transcription:     'bg-[#06b6d4]',   // cyan
    silence_detection: 'bg-[#8b5cf6]',   // purple
    shot_detection:    'bg-[#f59e0b]',   // amber
    motion_analysis:   'bg-[#10b981]',   // emerald
    face_detection:    'bg-[#ec4899]',   // pink
    highlights:        'bg-[#f97316]',   // orange
    story:             'bg-[#6366f1]',   // indigo
    editing:           'bg-[var(--accent)]',
  };

  const color = colors[stage] ?? 'bg-[var(--text-tertiary)]';

  return (
    <span
      className={cn('inline-block w-2 h-2 rounded-full shrink-0', color)}
      aria-hidden="true"
    />
  );
}

function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
