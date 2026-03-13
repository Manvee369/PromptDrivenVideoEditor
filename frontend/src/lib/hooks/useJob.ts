/**
 * useJob — polls GET /jobs/{id} on an interval while the job is active.
 * Stops polling automatically when the job reaches a terminal state.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getJob } from '@/lib/api';
import { isJobActive, type JobRecord } from '@/types/job';

const POLL_INTERVAL_MS = 1500;

interface UseJobResult {
  job: JobRecord | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<JobRecord | null>;
}

export function useJob(jobId: string): UseJobResult {
  const [job, setJob]       = useState<JobRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const timerRef            = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef          = useRef(true);

  const fetchJob = useCallback(async (): Promise<JobRecord | null> => {
    try {
      const data = await getJob(jobId);
      if (!mountedRef.current) return null;
      setJob(data);
      setError(null);
      return data;
    } catch (err) {
      if (!mountedRef.current) return null;
      setError(err instanceof Error ? err.message : 'Failed to fetch job');
      return null;
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    mountedRef.current = true;
    setLoading(true);

    const poll = async () => {
      const data = await fetchJob();
      if (!mountedRef.current) return;

      // Stop polling once the job reaches a terminal state
      if (data && !isJobActive(data.status)) return;

      timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    };

    void poll();

    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, fetchJob]);

  return { job, loading, error, refetch: fetchJob };
}
