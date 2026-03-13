'use client';

import React, { useCallback, useRef } from 'react';
import { cn } from '@/lib/utils';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  maxLength?: number;
  /** Auto-grow up to this height in pixels (default: 240). */
  maxHeight?: number;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, maxLength, maxHeight = 240, className, id, onChange, ...props }, ref) => {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);
    const charCount = typeof props.value === 'string' ? props.value.length : 0;

    const setRefs = (el: HTMLTextAreaElement | null) => {
      (innerRef as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
      if (typeof ref === 'function') ref(el);
      else if (ref) (ref as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
    };

    const autoGrow = useCallback(() => {
      const el = innerRef.current;
      if (!el) return;
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    }, [maxHeight]);

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      autoGrow();
      onChange?.(e);
    };

    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-[var(--text-secondary)]"
          >
            {label}
          </label>
        )}
        <div className="relative">
          <textarea
            ref={setRefs}
            id={inputId}
            maxLength={maxLength}
            onChange={handleChange}
            className={cn(
              'w-full min-h-[120px] px-3 py-3 rounded-[var(--radius-md)]',
              'bg-[var(--surface-3)] border border-[var(--border)]',
              'text-sm text-[var(--text-primary)] leading-relaxed',
              'placeholder:text-[var(--text-tertiary)]',
              'transition-all duration-[var(--duration-fast)] ease-[var(--ease-out)]',
              'focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_3px_var(--accent-glow)]',
              'resize-none overflow-y-auto',
              error && 'border-[var(--status-error)]',
              className,
            )}
            style={{ maxHeight }}
            {...props}
          />
          {maxLength != null && (
            <span
              aria-live="polite"
              className={cn(
                'absolute bottom-2.5 right-3 text-2xs font-mono tabular-nums',
                charCount >= maxLength
                  ? 'text-[var(--status-error)]'
                  : 'text-[var(--text-tertiary)]',
              )}
            >
              {charCount}/{maxLength}
            </span>
          )}
        </div>
        {error && (
          <p role="alert" className="text-xs text-[var(--status-error)]">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Textarea.displayName = 'Textarea';
