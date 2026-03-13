'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from './Spinner';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive';
type ButtonSize    = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: [
    'bg-[var(--accent)] text-white',
    'hover:bg-[var(--accent-hover)]',
    'active:bg-[var(--accent-active)]',
    'focus-visible:shadow-[0_0_0_3px_var(--accent-glow)]',
    'disabled:opacity-40 disabled:pointer-events-none',
  ].join(' '),

  secondary: [
    'bg-transparent text-[var(--text-primary)]',
    'border border-[var(--border)]',
    'hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)]',
    'active:bg-[var(--surface-3)]',
    'disabled:opacity-40 disabled:pointer-events-none',
  ].join(' '),

  ghost: [
    'bg-transparent text-[var(--text-secondary)]',
    'hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]',
    'active:bg-[var(--surface-4)]',
    'disabled:opacity-40 disabled:pointer-events-none',
  ].join(' '),

  destructive: [
    'bg-transparent text-[var(--status-error)]',
    'border border-[var(--border)]',
    'hover:bg-[var(--status-error-bg)] hover:border-[var(--status-error)]',
    'active:opacity-80',
    'disabled:opacity-40 disabled:pointer-events-none',
  ].join(' '),
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-7 px-3 text-xs gap-1.5 rounded-[var(--radius-md)]',
  md: 'h-9 px-4 text-sm gap-2   rounded-[var(--radius-md)]',
  lg: 'h-11 px-5 text-base gap-2.5 rounded-[var(--radius-lg)]',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'secondary',
      size = 'md',
      loading = false,
      leftIcon,
      rightIcon,
      children,
      className,
      disabled,
      ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        aria-disabled={isDisabled}
        aria-busy={loading}
        className={cn(
          'inline-flex items-center justify-center font-medium',
          'transition-all duration-[var(--duration-fast)] ease-[var(--ease-out)]',
          'select-none whitespace-nowrap',
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...props}
      >
        {loading ? (
          <Spinner size="sm" className="mr-1.5" />
        ) : leftIcon ? (
          <span className="shrink-0">{leftIcon}</span>
        ) : null}
        {children}
        {!loading && rightIcon ? (
          <span className="shrink-0">{rightIcon}</span>
        ) : null}
      </button>
    );
  },
);

Button.displayName = 'Button';
