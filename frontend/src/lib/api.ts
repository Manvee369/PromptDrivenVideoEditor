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
  return apiFetch<JobRecord[]>('/api/jobs/');
}

/** Get a single job by ID. */
export async function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch<JobRecord>(`/api/jobs/${jobId}`);
}

/** Optional extras for createJob. Each field is independently optional. */
export interface CreateJobExtras {
  musicFiles?: File[];
  voiceoverFiles?: File[];
  /** Caption style preset name; null/undefined → let the AI pick. */
  captionStyle?: string | null;
  /** Color grade preset; null/undefined → no grade applied. */
  colorGrade?: string | null;
  /**
   * analysis_id returned by analyzeContent(). When provided, the backend
   * copies the cached signals (transcript, diarization, visual scores, etc.)
   * from the analyze job into the real job, so Whisper/SigLIP never run twice.
   */
  analysisId?: string | null;
}

/**
 * Create a new job.
 * @param prompt   The natural language editing instruction.
 * @param files    Source video files (required).
 * @param extras   Optional music, voiceover, caption-style preset, analysis cache.
 */
export async function createJob(
  prompt: string,
  files: File[],
  extras: CreateJobExtras = {},
): Promise<CreateJobResponse> {
  const form = new FormData();
  form.append('prompt', prompt);
  for (const file of files) form.append('files', file);
  for (const file of extras.musicFiles ?? []) form.append('music_files', file);
  for (const file of extras.voiceoverFiles ?? []) form.append('voiceover_files', file);
  if (extras.captionStyle) form.append('caption_style', extras.captionStyle);
  if (extras.colorGrade && extras.colorGrade !== 'none') {
    form.append('color_grade', extras.colorGrade);
  }
  // Pass the analysis_id so the backend can reuse cached ML signals.
  if (extras.analysisId) form.append('analysis_id', extras.analysisId);

  return apiFetch<CreateJobResponse>('/api/jobs/', {
    method: 'POST',
    body: form,
    // Do NOT set Content-Type — browser sets multipart boundary automatically.
    headers: {},
  });
}

/* ─── Job Artifacts ─────────────────────────────────────────────────────── */

/** Get the Timeline DSL for a completed job. */
export async function getTimeline(jobId: string): Promise<TimelineDSL> {
  return apiFetch<TimelineDSL>(`/api/jobs/${jobId}/timeline`);
}

/** Replace the Timeline DSL on disk (does NOT trigger a re-render). */
export async function updateTimeline(
  jobId: string,
  timeline: TimelineDSL,
): Promise<TimelineDSL> {
  return apiFetch<TimelineDSL>(`/api/jobs/${jobId}/timeline`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(timeline),
  });
}

/** Get the AI explanation of editing decisions. */
export async function getExplanation(jobId: string): Promise<JobExplanation> {
  return apiFetch<JobExplanation>(`/api/jobs/${jobId}/explanation`);
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

  return apiFetch<AnalysisResult>('/api/jobs/analyze', {
    method: 'POST',
    body: form,
    headers: {},
  });
}

/**
 * Returns a direct URL to download the final rendered video.
 * Use this as an `<a href>` or `<video src>`.
 *
 * @param token  per-job download_token from JobRecord — required when the
 *               backend has token enforcement enabled (default: true).
 */
export function getVideoUrl(jobId: string, token?: string): string {
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${BASE_URL}/api/jobs/${jobId}/download${qs}`;
}

/** Returns a direct URL to the job thumbnail image. */
export function getThumbnailUrl(jobId: string, token?: string): string {
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${BASE_URL}/api/jobs/${jobId}/thumbnail${qs}`;
}

/* ─── Pipeline control (Phase 1) ───────────────────────────────────────── */

/** Re-run an existing job, reusing cached per-stage artifacts. */
export async function rerunJob(jobId: string, force = false): Promise<{ job_id: string }> {
  const qs = force ? '?force=true' : '';
  return apiFetch<{ job_id: string }>(`/api/jobs/${jobId}/rerun${qs}`, { method: 'POST' });
}

/** Re-render only — assumes the timeline DSL is on disk. */
export async function rerenderJob(jobId: string): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>(`/api/jobs/${jobId}/rerender`, { method: 'POST' });
}

/** Caption style presets supported by the backend. */
export async function getCaptionStylePresets(): Promise<string[]> {
  const data = await apiFetch<{ presets: string[] }>('/api/jobs/caption-styles');
  return data.presets;
}

/** Fallback list — kept in sync with backend STYLE_PRESETS. */
export const FALLBACK_CAPTION_PRESETS = [
  'default', 'tiktok_bold', 'karaoke',
  'minimal', 'news_lower_third', 'dramatic',
] as const;

/** Color grade presets supported by the backend. */
export async function getColorGradePresets(): Promise<string[]> {
  const data = await apiFetch<{ presets: string[] }>('/api/jobs/color-grades');
  return data.presets;
}

/** Fallback list — kept in sync with backend COLOR_GRADE_PRESET_NAMES. */
export const FALLBACK_COLOR_GRADES = [
  'none', 'cinematic', 'warm', 'cool', 'teal_orange',
  'bw', 'vintage', 'dramatic',
] as const;
