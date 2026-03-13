/**
 * useJobs — fetches the full job list, with an optional refresh interval.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { listJobs } from '@/lib/api';
import type { JobRecord } from '@/types/job';

const REFRESH_INTERVAL_MS = 5000;

interface UseJobsResult {
  jobs: JobRecord[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useJobs(autoRefresh = false): UseJobsResult {
  const [jobs, setJobs]       = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const timerRef              = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef            = useRef(true);

  const fetch_ = useCallback(async () => {
    try {
      const data = await listJobs();
      if (!mountedRef.current) return;
      // Sort newest first by created_at
      data.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      setJobs(data);
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to fetch jobs');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void fetch_();

    if (autoRefresh) {
      const schedule = () => {
        timerRef.current = setTimeout(async () => {
          await fetch_();
          if (mountedRef.current) schedule();
        }, REFRESH_INTERVAL_MS);
      };
      schedule();
    }

    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [fetch_, autoRefresh]);

  return { jobs, loading, error, refetch: fetch_ };
}
