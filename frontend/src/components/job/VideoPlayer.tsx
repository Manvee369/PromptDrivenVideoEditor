'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { getVideoUrl } from '@/lib/api';

interface VideoPlayerProps {
  jobId: string;
  className?: string;
  /** Subtitles track URL (e.g. a .vtt file). Optional. */
  captionsUrl?: string;
}

export function VideoPlayer({ jobId, className, captionsUrl }: VideoPlayerProps) {
  const videoRef   = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying]   = useState(false);
  const [muted,   setMuted]     = useState(false);
  const [progress, setProgress] = useState(0);   // 0–1
  const [duration, setDuration] = useState(0);
  const [current,  setCurrent]  = useState(0);
  const [captions, setCaptions] = useState(false);

  const videoSrc = getVideoUrl(jobId);

  /* ─── Sync state from native video ───────────────────────────────────── */
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTimeUpdate = () => {
      setCurrent(v.currentTime);
      setProgress(v.duration ? v.currentTime / v.duration : 0);
    };
    const onDurationChange = () => setDuration(v.duration);
    const onPlay  = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => { setPlaying(false); setProgress(1); };

    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('durationchange', onDurationChange);
    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('ended', onEnded);

    return () => {
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('durationchange', onDurationChange);
      v.removeEventListener('play', onPlay);
      v.removeEventListener('pause', onPause);
      v.removeEventListener('ended', onEnded);
    };
  }, []);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (playing) { v.pause(); } else { v.play().catch(() => {}); }
  }, [playing]);

  const toggleMute = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  }, []);

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    const t = parseFloat(e.target.value);
    v.currentTime = t;
    setCurrent(t);
    setProgress(t / duration);
  };

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const v = videoRef.current;
    if (!v) return;
    switch (e.key) {
      case ' ':
      case 'k':
        e.preventDefault();
        togglePlay();
        break;
      case 'f':
        e.preventDefault();
        if (document.fullscreenElement) document.exitFullscreen();
        else v.requestFullscreen();
        break;
      case 'm':
        e.preventDefault();
        v.muted = !v.muted;
        setMuted(v.muted);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        v.currentTime = Math.max(0, v.currentTime - 5);
        break;
      case 'ArrowRight':
        e.preventDefault();
        v.currentTime = Math.min(v.duration || 0, v.currentTime + 5);
        break;
    }
  }, [togglePlay]);

  const toggleFullscreen = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      v.requestFullscreen();
    }
  }, []);

  const toggleCaptions = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    const track = v.textTracks[0];
    if (track) {
      track.mode = track.mode === 'showing' ? 'disabled' : 'showing';
      setCaptions(track.mode === 'showing');
    }
  }, []);

  const fmt = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div
      className={cn(
        'flex flex-col rounded-[var(--radius-lg)] overflow-hidden',
        'bg-black border border-[var(--border)]',
        className,
      )}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="region"
      aria-label="Video player — Space to play/pause, Arrow keys to seek, M to mute, F for fullscreen"
    >
      {/* Video element */}
      <div className="relative bg-black aspect-video">
        <video
          ref={videoRef}
          src={videoSrc}
          className="w-full h-full object-contain"
          preload="metadata"
          onClick={togglePlay}
          aria-label="Edited video output"
        >
          {captionsUrl && (
            <track
              kind="subtitles"
              src={captionsUrl}
              srcLang="en"
              label="English"
              default
            />
          )}
        </video>

        {/* Play/Pause overlay on click (fade out quickly) */}
      </div>

      {/* Controls bar */}
      <div className="flex flex-col gap-2 px-4 py-3 bg-[var(--surface-1)] border-t border-[var(--border)]">
        {/* Scrubber */}
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.05}
          value={current}
          onChange={handleScrub}
          aria-label="Video timeline scrubber"
          className="video-scrubber w-full cursor-pointer"
          style={{ '--progress': `${progress * 100}%` } as React.CSSProperties}
        />

        {/* Button row */}
        <div className="flex items-center gap-2">
          {/* Play/Pause */}
          <ControlButton onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
            {playing ? <PauseIcon /> : <PlayIcon />}
          </ControlButton>

          {/* Time display */}
          <span className="text-xs font-mono tabular-nums text-[var(--text-secondary)] select-none ml-1">
            {fmt(current)} / {fmt(duration)}
          </span>

          <div className="flex-1" />

          {/* Captions toggle (only if track provided) */}
          {captionsUrl && (
            <ControlButton
              onClick={toggleCaptions}
              aria-label={captions ? 'Disable captions' : 'Enable captions'}
              active={captions}
            >
              <CaptionIcon />
            </ControlButton>
          )}

          {/* Mute */}
          <ControlButton onClick={toggleMute} aria-label={muted ? 'Unmute' : 'Mute'}>
            {muted ? <MuteIcon /> : <VolumeIcon />}
          </ControlButton>

          {/* Download */}
          <a
            href={videoSrc}
            download={`edited_${jobId.slice(0, 8)}.mp4`}
            aria-label="Download video"
            className={cn(
              'flex items-center justify-center w-7 h-7 rounded-[var(--radius-sm)]',
              'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]',
              'hover:bg-[var(--surface-3)]',
              'transition-colors duration-[var(--duration-fast)]',
            )}
          >
            <DownloadIcon />
          </a>

          {/* Fullscreen */}
          <ControlButton onClick={toggleFullscreen} aria-label="Toggle fullscreen">
            <FullscreenIcon />
          </ControlButton>
        </div>
      </div>
    </div>
  );
}

/* ─── Control Button ─────────────────────────────────────────────────────── */

function ControlButton({
  children,
  active,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        'flex items-center justify-center w-7 h-7 rounded-[var(--radius-sm)]',
        'transition-colors duration-[var(--duration-fast)]',
        active
          ? 'text-[var(--accent)] bg-[var(--accent-subtle)]'
          : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-3)]',
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/* ─── Icons ──────────────────────────────────────────────────────────────── */

const iconProps = {
  width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const, 'aria-hidden': true,
};

const PlayIcon     = () => <svg {...iconProps}><polygon points="5 3 19 12 5 21 5 3"/></svg>;
const PauseIcon    = () => <svg {...iconProps}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>;
const VolumeIcon   = () => <svg {...iconProps}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>;
const MuteIcon     = () => <svg {...iconProps}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>;
const DownloadIcon = () => <svg {...iconProps}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>;
const FullscreenIcon = () => <svg {...iconProps}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>;
const CaptionIcon  = () => <svg {...iconProps}><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M7 12h4"/><path d="M13 12h4"/><path d="M7 16h2"/><path d="M13 16h4"/></svg>;
