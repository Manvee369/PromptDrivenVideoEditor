'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { cn, capitalize } from '@/lib/utils';
import { Button }   from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';
import { DropZone } from '@/components/ui/DropZone';
import { Card }     from '@/components/ui/Card';
import { createJob, analyzeContent } from '@/lib/api';
import type { AnalysisResult } from '@/lib/api';

const EXAMPLE_PROMPTS = [
  'Make a 30 second TikTok highlight reel with bold captions. High energy, vertical format.',
  'Create a calm podcast recap with speaker labels and lower-thirds captions.',
  'Generate a gaming montage with fast cuts at audio peaks. 9:16 aspect, no music.',
];

export default function NewJobPage() {
  const router = useRouter();

  const [files,   setFiles]   = useState<File[]>([]);
  const [prompt,  setPrompt]  = useState('');
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);

  const canSubmit = files.length > 0 && prompt.trim().length > 0 && !loading && !analyzing;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    // If we already have an analysis (user confirmed warnings), proceed directly
    if (analysis) {
      await startJob();
      return;
    }

    // First, analyze the content for warnings
    setAnalyzing(true);
    setError(null);

    try {
      const result = await analyzeContent(prompt.trim(), files);
      if (result.warnings.length > 0) {
        // Show warnings and let user confirm
        setAnalysis(result);
        setAnalyzing(false);
      } else {
        // No warnings — proceed directly to job creation
        setAnalyzing(false);
        await startJob();
      }
    } catch {
      // Analysis failed (maybe endpoint not available) — proceed anyway
      setAnalyzing(false);
      await startJob();
    }
  };

  const startJob = async () => {
    setLoading(true);
    setError(null);

    try {
      const { job_id } = await createJob(prompt.trim(), files);
      router.push(`/jobs/${job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start job. Please try again.');
      setLoading(false);
    }
  };

  const dismissWarning = () => {
    setAnalysis(null);
  };

  return (
    <div className="px-6 py-10 max-w-3xl mx-auto animate-fade-in">
      {/* Page header */}
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">New Edit</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Upload your clips and describe the edit in plain English.
          The AI will analyze, plan, and render it automatically.
        </p>
      </header>

      <form onSubmit={handleSubmit} noValidate>
        <Card noPadding className="overflow-hidden">
          {/* Section 1: File Upload */}
          <div className="p-6 border-b border-[var(--border-subtle)]">
            <SectionLabel number={1} label="Upload video files" />
            <div className="mt-4">
              <DropZone
                files={files}
                onFilesChange={(f) => { setFiles(f); setAnalysis(null); }}
              />
            </div>
          </div>

          {/* Section 2: Prompt */}
          <div className="p-6 border-b border-[var(--border-subtle)]">
            <SectionLabel number={2} label="Describe your edit" />
            <div className="mt-4">
              <Textarea
                id="prompt"
                placeholder='e.g. "Make a 30 second TikTok highlight reel with captions. High energy, vertical format."'
                value={prompt}
                onChange={(e) => { setPrompt(e.target.value); setAnalysis(null); }}
                maxLength={500}
                disabled={loading || analyzing}
                aria-label="Editing prompt"
              />
            </div>

            {/* Example prompt suggestions */}
            <div className="mt-3 flex flex-col gap-1.5">
              <p className="text-xs text-[var(--text-tertiary)]">Try an example:</p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_PROMPTS.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => { setPrompt(ex); setAnalysis(null); }}
                    className="text-xs px-2.5 py-1 rounded-[var(--radius-full)]
                               bg-[var(--surface-3)] border border-[var(--border)]
                               text-[var(--text-secondary)]
                               hover:border-[var(--accent)] hover:text-[var(--accent)] hover:bg-[var(--accent-subtle)]
                               transition-all duration-[var(--duration-fast)]
                               focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--accent)]"
                  >
                    {ex.length > 48 ? ex.slice(0, 48) + '…' : ex}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Warning banner (if analysis returned warnings) */}
          {analysis && analysis.warnings.length > 0 && (
            <div className="p-6 border-b border-[var(--border-subtle)] animate-slide-up">
              <AnalysisWarning
                analysis={analysis}
                onProceed={startJob}
                onDismiss={dismissWarning}
                loading={loading}
              />
            </div>
          )}

          {/* Submit */}
          <div className="p-6">
            {error && (
              <p role="alert" className="mb-4 text-sm text-[var(--status-error)]">
                {error}
              </p>
            )}
            {!analysis && (
              <>
                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  loading={loading || analyzing}
                  disabled={!canSubmit}
                  className="w-full"
                  rightIcon={!loading && !analyzing ? <ArrowRightIcon /> : undefined}
                >
                  {analyzing ? 'Analyzing content…' : loading ? 'Starting job…' : 'Start Editing'}
                </Button>
                <p className="mt-3 text-center text-xs text-[var(--text-tertiary)]">
                  Processing may take 1–5 minutes depending on video length.
                </p>
              </>
            )}
          </div>
        </Card>
      </form>
    </div>
  );
}

/* ─── Analysis Warning Banner ──────────────────────────────────────────── */

function AnalysisWarning({
  analysis,
  onProceed,
  onDismiss,
  loading,
}: {
  analysis: AnalysisResult;
  onProceed: () => void;
  onDismiss: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      {/* Classification info */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-[#06b6d4]" />
          <span className="text-xs text-[var(--text-secondary)]">
            Detected: <span className="font-medium text-[var(--text-primary)]">{capitalize(analysis.video_type.replace('_', ' '))}</span>
            <span className="text-[var(--text-tertiary)]"> ({Math.round(analysis.video_type_confidence * 100)}%)</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)]" />
          <span className="text-xs text-[var(--text-secondary)]">
            Intent: <span className="font-medium text-[var(--text-primary)]">{capitalize(analysis.user_intent.replace('_', ' '))}</span>
          </span>
        </div>
      </div>

      {/* Warning messages */}
      {analysis.warnings.map((warning, i) => (
        <div
          key={i}
          className={cn(
            'flex gap-3 p-3 rounded-[var(--radius-md)]',
            'bg-[#f59e0b0a] border border-[#f59e0b33]',
          )}
          role="alert"
        >
          <WarningIcon className="text-[#f59e0b] shrink-0 mt-0.5" />
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{warning}</p>
        </div>
      ))}

      {/* Action buttons */}
      <div className="flex gap-3">
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={loading}
          onClick={onProceed}
        >
          Proceed Anyway
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onDismiss}
          disabled={loading}
        >
          Change Prompt
        </Button>
      </div>
    </div>
  );
}

/* ─── Section label with number badge ───────────────────────────────────── */

function SectionLabel({ number, label }: { number: number; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex items-center justify-center w-5 h-5 rounded-full
                       bg-[var(--accent-subtle)] border border-[var(--accent-border)]
                       text-[var(--accent)] text-xs font-bold tabular-nums shrink-0">
        {number}
      </span>
      <span className="text-sm font-semibold text-[var(--text-primary)]">{label}</span>
    </div>
  );
}

function ArrowRightIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <line x1="5" y1="12" x2="19" y2="12"/>
      <polyline points="12 5 19 12 12 19"/>
    </svg>
  );
}

function WarningIcon({ className }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}
