'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button }   from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';
import { DropZone } from '@/components/ui/DropZone';
import { Card }     from '@/components/ui/Card';
import { createJob } from '@/lib/api';

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
  const [error,   setError]   = useState<string | null>(null);

  const canSubmit = files.length > 0 && prompt.trim().length > 0 && !loading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

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
                onFilesChange={setFiles}
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
                onChange={(e) => setPrompt(e.target.value)}
                maxLength={500}
                disabled={loading}
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
                    onClick={() => setPrompt(ex)}
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

          {/* Submit */}
          <div className="p-6">
            {error && (
              <p role="alert" className="mb-4 text-sm text-[var(--status-error)]">
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              disabled={!canSubmit}
              className="w-full"
              rightIcon={!loading ? <ArrowRightIcon /> : undefined}
            >
              {loading ? 'Starting job…' : 'Start Editing'}
            </Button>
            <p className="mt-3 text-center text-xs text-[var(--text-tertiary)]">
              Processing may take 1–5 minutes depending on video length.
            </p>
          </div>
        </Card>
      </form>
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
