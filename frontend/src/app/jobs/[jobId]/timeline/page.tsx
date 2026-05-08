'use client';

/**
 * Timeline editor — read the AI's DSL, tweak it, save, and re-render.
 *
 * The Timeline DSL is the contract between the agent layer and the FFmpeg
 * renderer. Editing it here is the user's escape hatch for cases where the
 * AI's choices need a small manual fix (cut a beat earlier, change a
 * transition, drop a clip) without re-running the entire pipeline.
 */

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import { cn, shortId } from '@/lib/utils';
import { getTimeline, updateTimeline, rerenderJob } from '@/lib/api';
import type { TimelineDSL, TimelineClip } from '@/types/job';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';

/* ─── Page ───────────────────────────────────────────────────────────────── */

export default function TimelineEditorPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();

  const [dsl, setDsl] = useState<TimelineDSL | null>(null);
  const [savedDsl, setSavedDsl] = useState<TimelineDSL | null>(null);  // last persisted snapshot
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rerendering, setRerendering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* Load on mount */
  useEffect(() => {
    let alive = true;
    getTimeline(jobId)
      .then((t) => {
        if (!alive) return;
        setDsl(t);
        setSavedDsl(t);
        if (t.clips.length > 0) setSelectedIdx(0);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Failed to load timeline'))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [jobId]);

  const dirty = useMemo(
    () => dsl !== null && savedDsl !== null && JSON.stringify(dsl) !== JSON.stringify(savedDsl),
    [dsl, savedDsl],
  );

  /* Mutators — clone-and-replace so React picks up the change */

  function patchClip(idx: number, patch: Partial<TimelineClip>) {
    if (!dsl) return;
    const next = { ...dsl, clips: dsl.clips.map((c, i) => (i === idx ? { ...c, ...patch } : c)) };
    setDsl(next);
  }

  function deleteClip(idx: number) {
    if (!dsl) return;
    const next = { ...dsl, clips: dsl.clips.filter((_, i) => i !== idx) };
    setDsl(next);
    if (selectedIdx !== null) {
      if (selectedIdx === idx) setSelectedIdx(next.clips.length > 0 ? Math.max(0, idx - 1) : null);
      else if (selectedIdx > idx) setSelectedIdx(selectedIdx - 1);
    }
  }

  function moveClip(idx: number, direction: 'up' | 'down') {
    if (!dsl) return;
    const target = direction === 'up' ? idx - 1 : idx + 1;
    if (target < 0 || target >= dsl.clips.length) return;
    const clips = [...dsl.clips];
    [clips[idx], clips[target]] = [clips[target], clips[idx]];
    setDsl({ ...dsl, clips });
    setSelectedIdx(target);
  }

  /* Async actions */

  async function handleSave() {
    if (!dsl) return;
    setSaving(true);
    setError(null);
    try {
      const persisted = await updateTimeline(jobId, dsl);
      setSavedDsl(persisted);
      setDsl(persisted);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function handleRerender() {
    if (!dsl) return;
    if (dirty) {
      // Save first; bail if save fails so we don't render a stale DSL.
      try {
        await handleSaveSync();
      } catch {
        return;
      }
    }
    setRerendering(true);
    setError(null);
    try {
      await rerenderJob(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Re-render failed');
      setRerendering(false);
    }
  }

  async function handleSaveSync() {
    if (!dsl) return;
    setSaving(true);
    try {
      const persisted = await updateTimeline(jobId, dsl);
      setSavedDsl(persisted);
      setDsl(persisted);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
      throw e;
    } finally {
      setSaving(false);
    }
  }

  /* Render */

  if (loading) {
    return <CenteredSpinner label="Loading timeline…" />;
  }
  if (error && !dsl) {
    return <CenteredError message={error} jobId={jobId} />;
  }
  if (!dsl) return null;

  const selected = selectedIdx !== null ? dsl.clips[selectedIdx] : null;
  const totalDur = totalDuration(dsl);

  return (
    <div className="px-6 py-10 max-w-6xl mx-auto animate-fade-in">
      <header className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <Link
            href={`/jobs/${jobId}`}
            className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <ChevronLeftIcon /> Back to job
          </Link>
          <h1 className="text-xl font-bold text-[var(--text-primary)] mt-2 font-mono">
            Edit timeline · {shortId(jobId)}
          </h1>
          <p className="text-xs text-[var(--text-tertiary)] mt-1">
            {dsl.clips.length} clips · {totalDur.toFixed(1)}s · {dsl.format.width}×{dsl.format.height} · {dsl.format.fps}fps
          </p>
        </div>

        <div className="flex items-center gap-2">
          {dirty && (
            <span className="text-xs text-[var(--accent)] tabular-nums">Unsaved changes</span>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleSave}
            disabled={!dirty || saving || rerendering}
            loading={saving}
          >
            Save
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleRerender}
            disabled={rerendering || dsl.clips.length === 0}
            loading={rerendering}
          >
            Save &amp; Re-render
          </Button>
        </div>
      </header>

      {error && (
        <div className="mb-4 p-3 rounded-[var(--radius-md)] bg-[#ef44440a] border border-[#ef444433]">
          <p className="text-sm text-[var(--status-error)]">{error}</p>
        </div>
      )}

      <Card className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Track</h2>
        <TimelineTrack
          dsl={dsl}
          selectedIdx={selectedIdx}
          onSelect={setSelectedIdx}
        />
      </Card>

      {selected !== null && selectedIdx !== null && (
        <Card>
          <ClipPropertyPanel
            clip={selected}
            index={selectedIdx}
            total={dsl.clips.length}
            onChange={(patch) => patchClip(selectedIdx, patch)}
            onDelete={() => deleteClip(selectedIdx)}
            onMoveUp={() => moveClip(selectedIdx, 'up')}
            onMoveDown={() => moveClip(selectedIdx, 'down')}
          />
        </Card>
      )}
    </div>
  );
}

/* ─── TimelineTrack ──────────────────────────────────────────────────────── */

function TimelineTrack({
  dsl,
  selectedIdx,
  onSelect,
}: {
  dsl: TimelineDSL;
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  const total = totalDuration(dsl) || 1;  // avoid div-by-zero

  if (dsl.clips.length === 0) {
    return (
      <p className="text-sm text-[var(--text-tertiary)] py-6 text-center">
        No clips. Add clips by re-running the pipeline.
      </p>
    );
  }

  return (
    <div className="flex gap-1 h-20 overflow-x-auto items-stretch py-1">
      {dsl.clips.map((clip, idx) => {
        const widthPct = (effectiveDuration(clip) / total) * 100;
        return (
          <ClipBlock
            key={idx}
            clip={clip}
            index={idx}
            widthPct={widthPct}
            selected={selectedIdx === idx}
            onSelect={() => onSelect(idx)}
          />
        );
      })}
    </div>
  );
}

/* ─── ClipBlock ──────────────────────────────────────────────────────────── */

function ClipBlock({
  clip,
  index,
  widthPct,
  selected,
  onSelect,
}: {
  clip: TimelineClip;
  index: number;
  widthPct: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const dur = effectiveDuration(clip);
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{ flexBasis: `${Math.max(widthPct, 4)}%`, minWidth: 36 }}
      className={cn(
        'flex flex-col justify-between rounded-[var(--radius-sm)] px-2 py-1.5 text-left',
        'border transition-all duration-[var(--duration-fast)]',
        'shrink-0 overflow-hidden',
        selected
          ? 'border-[var(--accent)] bg-[var(--accent-subtle)] shadow-[0_0_0_1px_var(--accent)]'
          : 'border-[var(--border)] bg-[var(--surface-3)] hover:border-[var(--border-strong)]',
      )}
      title={`Clip ${index + 1}: ${clip.source} (${clip.start.toFixed(2)}–${clip.end.toFixed(2)}s)`}
    >
      <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums">
        #{index + 1}
      </span>
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-xs text-[var(--text-primary)] truncate font-mono">
          {clip.source}
        </span>
        <span className="text-[10px] text-[var(--text-secondary)] tabular-nums">
          {dur.toFixed(1)}s
          {clip.transition_in && (
            <span className="ml-1 text-[var(--accent)]">·{clip.transition_in[0]}</span>
          )}
        </span>
      </div>
    </button>
  );
}

/* ─── ClipPropertyPanel ──────────────────────────────────────────────────── */

const TRANSITIONS = [null, 'crossfade', 'fade', 'flash'] as const;

function ClipPropertyPanel({
  clip,
  index,
  total,
  onChange,
  onDelete,
  onMoveUp,
  onMoveDown,
}: {
  clip: TimelineClip;
  index: number;
  total: number;
  onChange: (patch: Partial<TimelineClip>) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          Clip #{index + 1}
          <span className="ml-2 text-[var(--text-tertiary)] font-normal font-mono">
            {clip.source}
          </span>
        </h2>
        <div className="flex items-center gap-1.5">
          <Button variant="secondary" size="sm" onClick={onMoveUp} disabled={index === 0}>
            ↑ Move up
          </Button>
          <Button variant="secondary" size="sm" onClick={onMoveDown} disabled={index === total - 1}>
            ↓ Move down
          </Button>
          <Button variant="secondary" size="sm" onClick={onDelete}>
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <NumField label="Start (s)" value={clip.start} step={0.1} min={0}
                  onChange={(v) => onChange({ start: v })} />
        <NumField label="End (s)" value={clip.end} step={0.1} min={0}
                  onChange={(v) => onChange({ end: v })} />
        <NumField label="Speed" value={clip.speed} step={0.1} min={0.1}
                  onChange={(v) => onChange({ speed: v })} />
        <NumField label="Volume" value={clip.volume} step={0.1} min={0} max={2}
                  onChange={(v) => onChange({ volume: v })} />
        <NumField label="Zoom" value={clip.zoom} step={0.05} min={1.0} max={3.0}
                  onChange={(v) => onChange({ zoom: v })} />
        <SelectField
          label="Transition in"
          value={clip.transition_in ?? ''}
          options={TRANSITIONS.map((t) => ({ value: t ?? '', label: t ?? 'none' }))}
          onChange={(v) => onChange({ transition_in: v === '' ? null : v })}
        />
        <NumField label="Transition (s)" value={clip.transition_duration} step={0.05} min={0}
                  onChange={(v) => onChange({ transition_duration: v })} />
      </div>

      {clip.end <= clip.start && (
        <p className="text-xs text-[var(--status-error)]">
          End time must be greater than start time.
        </p>
      )}
    </div>
  );
}

/* ─── Form primitives ────────────────────────────────────────────────────── */

function NumField({
  label, value, step, min, max, onChange,
}: {
  label: string;
  value: number;
  step?: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
        className={cn(
          'h-9 px-2 rounded-[var(--radius-sm)] tabular-nums',
          'bg-[var(--surface-2)] border border-[var(--border)] text-[var(--text-primary)]',
          'focus-visible:outline-none focus-visible:border-[var(--accent)]',
        )}
      />
    </label>
  );
}

function SelectField({
  label, value, options, onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-9 px-2 rounded-[var(--radius-sm)]',
          'bg-[var(--surface-2)] border border-[var(--border)] text-[var(--text-primary)]',
          'focus-visible:outline-none focus-visible:border-[var(--accent)]',
        )}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

/* ─── Helpers ────────────────────────────────────────────────────────────── */

function effectiveDuration(clip: TimelineClip): number {
  const raw = clip.end - clip.start;
  return clip.speed > 0 ? raw / clip.speed : raw;
}

function totalDuration(dsl: TimelineDSL): number {
  let t = 0;
  for (let i = 0; i < dsl.clips.length; i++) {
    const c = dsl.clips[i];
    t += effectiveDuration(c);
    if (i > 0 && c.transition_in === 'crossfade') {
      t -= c.transition_duration;
    }
  }
  return t;
}

/* ─── Loading / error placeholders ───────────────────────────────────────── */

function CenteredSpinner({ label }: { label: string }) {
  return (
    <div className="px-6 py-20 max-w-3xl mx-auto flex flex-col items-center gap-3">
      <Spinner size="md" />
      <p className="text-sm text-[var(--text-tertiary)]">{label}</p>
    </div>
  );
}

function CenteredError({ message, jobId }: { message: string; jobId: string }) {
  return (
    <div className="px-6 py-20 max-w-3xl mx-auto flex flex-col items-center gap-3 text-center">
      <p className="text-sm text-[var(--status-error)]">{message}</p>
      <Link href={`/jobs/${jobId}`}>
        <Button variant="secondary" size="sm">Back to job</Button>
      </Link>
    </div>
  );
}

function ChevronLeftIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  );
}
