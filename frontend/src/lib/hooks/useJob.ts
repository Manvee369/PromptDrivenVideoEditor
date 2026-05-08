/**
 * useJob — live job state via Server-Sent Events with polling fallback.
 *
 * Flow:
 *   1. Initial GET /jobs/{id} — gives us prompt, download_token, created_at,
 *      and other static fields the SSE stream doesn't repeat.
 *   2. EventSource on /jobs/{id}/events — applies partial-state deltas to
 *      `job` (status/progress/error) and exposes substage info separately.
 *   3. On SSE 'done' event or terminal status — re-fetch /jobs/{id} once to
 *      pick up final fields like `output_file`.
 *   4. On SSE error — fall back to interval polling so the UI still updates
 *      in environments where SSE is blocked (some corp proxies).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getJob } from '@/lib/api';
import { isJobActive, type JobRecord } from '@/types/job';

const POLL_INTERVAL_MS = 2000;
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** Sub-stage progress emitted on the events stream. */
export interface SubstageInfo {
  substage: string | null;
  substage_progress: number | null;
  frame: number | null;
  fps: number | null;
  speed: string | null;
  message: string | null;
}

interface SSEPayload {
  status: JobRecord['status'];
  progress: number;
  error: string | null;
  substage: string | null;
  substage_progress: number | null;
  frame: number | null;
  fps: number | null;
  speed: string | null;
  message: string | null;
}

interface UseJobResult {
  job: JobRecord | null;
  substage: SubstageInfo | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<JobRecord | null>;
}

export function useJob(jobId: string): UseJobResult {
  const [job, setJob] = useState<JobRecord | null>(null);
  const [substage, setSubstage] = useState<SubstageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refs to keep callback identity stable and to coordinate cleanup.
  const mountedRef = useRef(true);
  const esRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalFetchedRef = useRef(false);

  const refetch = useCallback(async (): Promise<JobRecord | null> => {
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
    finalFetchedRef.current = false;
    setLoading(true);

    const cleanupStreams = () => {
      esRef.current?.close();
      esRef.current = null;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const startPolling = () => {
      const tick = async () => {
        if (!mountedRef.current) return;
        try {
          const data = await getJob(jobId);
          if (!mountedRef.current) return;
          setJob(data);
          setError(null);
          if (isJobActive(data.status)) {
            pollTimerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
          }
        } catch (err) {
          if (!mountedRef.current) return;
          setError(err instanceof Error ? err.message : 'Failed to fetch job');
        }
      };
      pollTimerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    };

    const onTerminal = async () => {
      cleanupStreams();
      if (!mountedRef.current || finalFetchedRef.current) return;
      finalFetchedRef.current = true;
      // Final pull picks up output_file and any fields not in the SSE payload.
      await refetch();
    };

    const attachSSE = (initial: JobRecord) => {
      // Already terminal? Skip the stream entirely.
      if (!isJobActive(initial.status)) return;

      try {
        const es = new EventSource(`${BASE_URL}/jobs/${jobId}/events`);
        esRef.current = es;

        es.onmessage = (ev: MessageEvent) => {
          if (!mountedRef.current) return;
          try {
            const partial = JSON.parse(ev.data) as SSEPayload;
            setJob((prev) =>
              prev
                ? { ...prev, status: partial.status, progress: partial.progress, error: partial.error }
                : prev,
            );
            setSubstage({
              substage: partial.substage,
              substage_progress: partial.substage_progress,
              frame: partial.frame,
              fps: partial.fps,
              speed: partial.speed,
              message: partial.message,
            });
            if (!isJobActive(partial.status)) {
              void onTerminal();
            }
          } catch {
            // Ignore malformed messages; the stream will keep delivering.
          }
        };

        es.addEventListener('done', () => {
          void onTerminal();
        });

        es.onerror = () => {
          // SSE failed — could be proxy buffering, network blip, or 4xx.
          // Close and fall back to polling so the UI still progresses.
          cleanupStreams();
          if (mountedRef.current && isJobActive(initial.status)) {
            startPolling();
          }
        };
      } catch {
        // EventSource not available (very old browsers, SSR) — poll instead.
        startPolling();
      }
    };

    void (async () => {
      const data = await refetch();
      if (!mountedRef.current || !data) return;
      attachSSE(data);
    })();

    return () => {
      mountedRef.current = false;
      cleanupStreams();
    };
  }, [jobId, refetch]);

  return { job, substage, loading, error, refetch };
}
