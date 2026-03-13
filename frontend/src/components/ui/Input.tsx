import React from 'react';
import { cn } from '@/lib/utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  leftIcon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, leftIcon, className, id, ...props }, ref) => {
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
          {leftIcon && (
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] pointer-events-none">
              {leftIcon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              'w-full h-9 px-3 rounded-[var(--radius-md)]',
              'bg-[var(--surface-3)] border border-[var(--border)]',
              'text-sm text-[var(--text-primary)]',
              'placeholder:text-[var(--text-tertiary)]',
              'transition-all duration-[var(--duration-fast)] ease-[var(--ease-out)]',
              'focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_3px_var(--accent-glow)]',
              error && 'border-[var(--status-error)] focus:shadow-[0_0_0_3px_var(--status-error-bg)]',
              leftIcon && 'pl-9',
              className,
            )}
            {...props}
          />
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

Input.displayName = 'Input';
