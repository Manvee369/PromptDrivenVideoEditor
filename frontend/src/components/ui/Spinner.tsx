import React from 'react';
import { cn } from '@/lib/utils';

interface SpinnerProps {
  size?: 'sm' | 'md';
  className?: string;
}

const sizeMap = { sm: 16, md: 24 };

export function Spinner({ size = 'md', className }: SpinnerProps) {
  const px = sizeMap[size];
  const stroke = size === 'sm' ? 2.5 : 2;
  const r = (px - stroke * 2) / 2;
  const circumference = 2 * Math.PI * r;

  return (
    <svg
      width={px}
      height={px}
      viewBox={`0 0 ${px} ${px}`}
      fill="none"
      aria-hidden="true"
      className={cn('animate-spin shrink-0', className)}
      style={{ animationDuration: '0.7s' }}
    >
      {/* Track */}
      <circle
        cx={px / 2}
        cy={px / 2}
        r={r}
        stroke="currentColor"
        strokeWidth={stroke}
        strokeOpacity={0.15}
      />
      {/* Arc */}
      <circle
        cx={px / 2}
        cy={px / 2}
        r={r}
        stroke="currentColor"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * 0.75}
        style={{ transformOrigin: 'center', transform: 'rotate(-90deg)' }}
      />
    </svg>
  );
}
