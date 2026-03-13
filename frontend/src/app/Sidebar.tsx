'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useJobs } from '@/lib/hooks/useJobs';
import { JobCard } from '@/components/job/JobCard';

export function Sidebar() {
  const pathname = usePathname();
  const { jobs } = useJobs(true);
  const recentJobs = jobs.slice(0, 5);

  return (
    <nav
      aria-label="Application navigation"
      className={cn(
        'flex flex-col w-60 h-full shrink-0',
        'bg-[var(--surface-1)] border-r border-[var(--border)]',
        'overflow-y-auto overflow-x-hidden',
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-5 h-14 border-b border-[var(--border-subtle)] shrink-0">
        <BrandMark />
        <span className="text-sm font-semibold text-[var(--text-primary)] tracking-tight">
          Prompt Editor
        </span>
      </div>

      {/* Primary CTA */}
      <div className="px-3 pt-4 pb-2 shrink-0">
        <Link
          href="/"
          className={cn(
            'flex items-center gap-2 w-full px-3 h-9 rounded-[var(--radius-md)]',
            'bg-[var(--accent)] text-white text-sm font-medium',
            'transition-colors duration-[var(--duration-fast)]',
            'hover:bg-[var(--accent-hover)] active:bg-[var(--accent-active)]',
            'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--accent-glow)]',
          )}
        >
          <PlusIcon />
          New Edit
        </Link>
      </div>

      {/* Navigation links */}
      <div className="px-3 pb-3 shrink-0">
        <NavItem href="/"        label="Dashboard"   icon={<HomeIcon />}    active={pathname === '/'} />
        <NavItem href="/history" label="Job History" icon={<HistoryIcon />} active={pathname === '/history'} />
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-[var(--border-subtle)] shrink-0" />

      {/* Recent jobs */}
      <div className="flex-1 overflow-y-auto px-3 pt-4">
        <p className="px-2 mb-2 text-2xs uppercase tracking-widest font-semibold text-[var(--text-tertiary)]">
          Recent
        </p>
        <div className="flex flex-col gap-1.5">
          {recentJobs.length === 0 ? (
            <p className="px-2 text-xs text-[var(--text-tertiary)]">No jobs yet.</p>
          ) : (
            recentJobs.map((job) => (
              <JobCard key={job.job_id} job={job} compact />
            ))
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[var(--border-subtle)] shrink-0">
        <p className="text-2xs text-[var(--text-tertiary)]">
          Powered by Groq + FFmpeg
        </p>
      </div>
    </nav>
  );
}

/* ─── Nav Item ───────────────────────────────────────────────────────────── */

function NavItem({
  href,
  label,
  icon,
  active,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        'flex items-center gap-2.5 w-full px-3 h-8 rounded-[var(--radius-md)] text-sm',
        'transition-colors duration-[var(--duration-fast)]',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--accent)]',
        active
          ? 'bg-[var(--accent-subtle)] text-[var(--accent)] font-medium'
          : 'text-[var(--text-secondary)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]',
      )}
      aria-current={active ? 'page' : undefined}
    >
      <span className="shrink-0">{icon}</span>
      {label}
    </Link>
  );
}

/* ─── Icons ──────────────────────────────────────────────────────────────── */

const iconProps = {
  width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const, 'aria-hidden': true,
};

function BrandMark() {
  return (
    <div className="flex items-center justify-center w-7 h-7 rounded-[var(--radius-md)] bg-[var(--accent)]">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
           aria-hidden="true">
        <polygon points="23 7 16 12 23 17 23 7"/>
        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
      </svg>
    </div>
  );
}

const PlusIcon    = () => <svg {...iconProps}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
const HomeIcon    = () => <svg {...iconProps}><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
const HistoryIcon = () => <svg {...iconProps}><polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 0 .5-4.5"/><polyline points="3 2 3 7 8 7"/></svg>;
