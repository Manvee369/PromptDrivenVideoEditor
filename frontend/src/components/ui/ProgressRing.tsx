import React from 'react';
import { cn } from '@/lib/utils';

interface ProgressRingProps {
  /** Value from 0 to 1. */
  value: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  sublabel?: string;
  className?: string;
}

export function ProgressRing({
  value,
  size = 160,
  strokeWidth = 8,
  label,
  sublabel,
  className,
}: ProgressRingProps) {
  const pct        = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  const radius     = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset     = circumference - (pct / 100) * circumference;

  return (
    <div
      className={cn('relative inline-flex items-center justify-center', className)}
      style={{ width: size, height: size }}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ? `${label}: ${pct}%` : `Progress: ${pct}%`}
    >
      <svg
        width={size}
        height={size}
        style={{ transform: 'rotate(-90deg)' }}
        aria-hidden="true"
      >
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth={strokeWidth}
        />
        {/* Fill */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 600ms cubic-bezier(0.0, 0.0, 0.2, 1)',
          }}
        />
      </svg>

      {/* Center text */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-[var(--text-primary)] font-bold tabular-nums"
              style={{ fontSize: size * 0.18 }}>
          {pct}%
        </span>
        {label && (
          <span
            className="text-[var(--text-secondary)] text-center leading-tight mt-1"
            style={{ fontSize: size * 0.09 }}
          >
            {label}
          </span>
        )}
        {sublabel && (
          <span
            className="text-[var(--text-tertiary)] text-center leading-tight"
            style={{ fontSize: size * 0.08 }}
          >
            {sublabel}
          </span>
        )}
      </div>
    </div>
  );
}
