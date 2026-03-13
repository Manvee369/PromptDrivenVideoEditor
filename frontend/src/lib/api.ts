/**
 * API client — typed fetch wrappers for all backend endpoints.
 * Base URL is read from the NEXT_PUBLIC_API_URL environment variable,
 * defaulting to localhost:8000 for local development.
 */

import type {
  CreateJobResponse,
  JobExplanation,
  JobRecord,
  TimelineDSL,
} from '@/types/job';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** Generic fetch helper with JSON parsing and typed error messages. */
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Accept': 'application/json', ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message = body?.detail ?? `HTTP ${res.status}`;
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

/* ─── Jobs ──────────────────────────────────────────────────────────────── */

/** List all jobs. */
export async function listJobs(): Promise<JobRecord[]> {
  return apiFetch<JobRecord[]>('/jobs/');
}

/** Get a single job by ID. */
export async function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch<JobRecord>(`/jobs/${jobId}`);
}

/**
 * Create a new job.
 * @param prompt  The natural language editing instruction.
 * @param files   One or more video files to upload.
 */
export async function createJob(
  prompt: string,
  files: File[],
): Promise<CreateJobResponse> {
  const form = new FormData();
  form.append('prompt', prompt);
  for (const file of files) {
    form.append('files', file);
  }

  return apiFetch<CreateJobResponse>('/jobs/', {
    method: 'POST',
    body: form,
    // Do NOT set Content-Type — browser sets multipart boundary automatically.
    headers: {},
  });
}

/* ─── Job Artifacts ─────────────────────────────────────────────────────── */

/** Get the Timeline DSL for a completed job. */
export async function getTimeline(jobId: string): Promise<TimelineDSL> {
  return apiFetch<TimelineDSL>(`/jobs/${jobId}/timeline`);
}

/** Get the AI explanation of editing decisions. */
export async function getExplanation(jobId: string): Promise<JobExplanation> {
  return apiFetch<JobExplanation>(`/jobs/${jobId}/explanation`);
}

/* ─── Content Analysis ─────────────────────────────────────────────────── */

/** Response from POST /jobs/analyze */
export interface AnalysisResult {
  analysis_id: string;
  video_type: string;
  video_type_confidence: number;
  video_type_scores: Record<string, number>;
  user_intent: string;
  user_intent_confidence: number;
  warnings: string[];
  strategy_summary: {
    operations: string[];
    energy: string;
    caption_style: string;
    speaker_tags: boolean;
    story_structure: string;
  };
}

/**
 * Quick content analysis before starting the full pipeline.
 * Returns classification, intent, and any mismatch warnings.
 */
export async function analyzeContent(
  prompt: string,
  files: File[],
): Promise<AnalysisResult> {
  const form = new FormData();
  form.append('prompt', prompt);
  for (const file of files) {
    form.append('files', file);
  }

  return apiFetch<AnalysisResult>('/jobs/analyze', {
    method: 'POST',
    body: form,
    headers: {},
  });
}

/**
 * Returns a direct URL to download the final rendered video.
 * Use this as an `<a href>` or `<video src>`.
 */
export function getVideoUrl(jobId: string): string {
  return `${BASE_URL}/jobs/${jobId}/download`;
}

/**
 * Returns a direct URL to the job thumbnail image.
 * Use this as an `<img src>`.
 */
export function getThumbnailUrl(jobId: string): string {
  return `${BASE_URL}/jobs/${jobId}/thumbnail`;
}
