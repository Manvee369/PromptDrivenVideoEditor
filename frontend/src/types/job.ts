/**
 * TypeScript types mirroring the backend JobRecord and all API response shapes.
 * Keep in sync with backend/app/db/jobs_db.py and backend/app/api/routes_jobs.py.
 */

/** All possible pipeline stages, in execution order. */
export type JobStatus =
  | 'created'
  | 'preprocessing'
  | 'intelligence'
  | 'planning'
  | 'rendering'
  | 'completed'
  | 'failed';

/** The core job record returned by GET /jobs and GET /jobs/{id}. */
export interface JobRecord {
  job_id: string;
  prompt: string;
  status: JobStatus;
  created_at: string;   // ISO 8601 timestamp
  updated_at: string;   // ISO 8601 timestamp
  error: string | null;
  progress: number;     // 0.0 – 1.0
  output_file: string | null;
}

/** Response from POST /jobs/ */
export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
}

/** Timeline DSL format returned by GET /jobs/{id}/timeline */
export interface TimelineFormat {
  aspect: string;   // e.g. "16:9" or "9:16"
  fps: number;
  width?: number;
  height?: number;
}

export interface TimelineClip {
  source: string;
  start: number;
  end: number;
  transition?: string;
}

export interface TimelineCaption {
  time: number;
  text: string;
  style?: string;
}

export interface TimelineMusic {
  track: string;
  sync_beats?: boolean;
}

export interface TimelineDSL {
  format: TimelineFormat;
  clips: TimelineClip[];
  captions?: TimelineCaption[];
  music?: TimelineMusic;
}

/** Explanation decision entry */
export interface ExplanationDecision {
  stage: string;
  detail: string;
}

/** Explanation stats block */
export interface ExplanationStats {
  input_files: number;
  input_duration: number;
  output_clips: number;
  output_duration: number;
  captions: number;
  format: string;
  compression_ratio: string;
}

/** Full explanation payload returned by GET /jobs/{id}/explanation */
export interface JobExplanation {
  summary?: string;
  decisions?: ExplanationDecision[];
  stats?: ExplanationStats;
}

/**
 * Ordered pipeline stages for rendering progress UI.
 * Maps status → a zero-based step index.
 */
export const PIPELINE_STAGES: { key: JobStatus | 'done'; label: string; sublabel: string }[] = [
  { key: 'preprocessing', label: 'Preprocessing',  sublabel: 'Extracting audio and creating proxies' },
  { key: 'intelligence',  label: 'Intelligence',   sublabel: 'Transcribing, detecting shots and motion' },
  { key: 'planning',      label: 'Planning',        sublabel: 'Selecting highlights and composing story' },
  { key: 'rendering',     label: 'Rendering',       sublabel: 'Building final video with captions' },
  { key: 'done',          label: 'Done',            sublabel: 'Your edit is ready' },
];

/** Returns the index of the active stage (0-based) given a job status. */
export function getStageIndex(status: JobStatus): number {
  const order: JobStatus[] = [
    'created',
    'preprocessing',
    'intelligence',
    'planning',
    'rendering',
    'completed',
  ];
  const idx = order.indexOf(status);
  return idx < 0 ? 0 : idx;
}

/** Whether the job is still actively running. */
export function isJobActive(status: JobStatus): boolean {
  return !['completed', 'failed'].includes(status);
}

/** Maps a JobStatus to its display label. */
export const STATUS_LABELS: Record<JobStatus, string> = {
  created:       'Queued',
  preprocessing: 'Processing',
  intelligence:  'Analyzing',
  planning:      'Planning',
  rendering:     'Rendering',
  completed:     'Completed',
  failed:        'Failed',
};
