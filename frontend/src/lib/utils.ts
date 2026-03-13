/**
 * Shared utility functions — formatting, class merging, and helpers.
 */

import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind class names safely, resolving conflicts. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a duration in seconds to a human-readable string.
 * Examples: 8.9 → "8.9s", 90 → "1m 30s", 509 → "8m 29s"
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds * 10) / 10}s`;
  }
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/**
 * Format a relative timestamp.
 * Examples: "just now", "2 minutes ago", "1 hour ago"
 */
export function formatRelativeTime(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 10)  return 'just now';
  if (diffSec < 60)  return `${diffSec} seconds ago`;

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60)  return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;

  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24)   return `${diffHr} hour${diffHr !== 1 ? 's' : ''} ago`;

  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;
}

/** Truncate a string to a maximum length, appending an ellipsis. */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 1) + '…';
}

/** Format a file size in bytes to a human-readable string. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 ** 2)   return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3)   return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

/** Capitalize the first letter of a string. */
export function capitalize(str: string): string {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Shorten a UUID to its first 8 characters for display. */
export function shortId(jobId: string): string {
  return jobId.slice(0, 8);
}

/**
 * Map a pipeline progress value (0–1) to a percentage string.
 * Clamps to [0, 100].
 */
export function progressPercent(progress: number): string {
  return `${Math.round(Math.min(Math.max(progress, 0), 1) * 100)}%`;
}
