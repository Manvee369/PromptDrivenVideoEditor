import React from 'react';
import { cn } from '@/lib/utils';

interface PromptDisplayProps {
  prompt: string;
  className?: string;
}

export function PromptDisplay({ prompt, className }: PromptDisplayProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-1',
        'pl-4 border-l-[3px] border-[var(--accent)]',
        className,
      )}
    >
      <span className="text-2xs uppercase tracking-widest font-semibold text-[var(--text-tertiary)]">
        Prompt
      </span>
      <p className="text-sm italic text-[var(--text-secondary)] leading-relaxed">
        {prompt}
      </p>
    </div>
  );
}
