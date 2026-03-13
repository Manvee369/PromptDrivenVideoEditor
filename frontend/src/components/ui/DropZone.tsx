'use client';

import React, { useCallback, useId, useRef, useState } from 'react';
import { cn, formatFileSize } from '@/lib/utils';

interface DropZoneProps {
  onFilesChange: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  files?: File[];
  error?: string;
}

export function DropZone({
  onFilesChange,
  accept = 'video/*,.mp4,.mov,.avi,.mkv,.webm',
  multiple = true,
  files = [],
  error,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (newFiles: FileList | null) => {
      if (!newFiles) return;
      const arr = Array.from(newFiles);
      onFilesChange(multiple ? [...files, ...arr] : arr);
    },
    [files, multiple, onFilesChange],
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const removeFile = (index: number) => {
    const next = files.filter((_, i) => i !== index);
    onFilesChange(next);
  };

  return (
    <div className="flex flex-col gap-3 w-full">
      {/* Drop area */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop video files here or click to browse"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={cn(
          'relative flex flex-col items-center justify-center gap-3',
          'border-2 border-dashed rounded-[var(--radius-xl)]',
          'p-10 cursor-pointer select-none',
          'transition-all duration-[var(--duration-base)] ease-[var(--ease-out)]',
          dragging
            ? 'border-[var(--accent)] bg-[var(--accent-subtle)] scale-[1.005]'
            : error
            ? 'border-[var(--status-error)] bg-[var(--status-error-bg)]'
            : 'border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)]',
        )}
      >
        {/* Upload icon */}
        <div
          className={cn(
            'flex items-center justify-center w-12 h-12 rounded-[var(--radius-lg)]',
            'transition-transform duration-150',
            dragging && 'scale-110',
            dragging ? 'bg-[var(--accent-subtle)]' : 'bg-[var(--surface-3)]',
          )}
        >
          <UploadIcon
            className={dragging ? 'text-[var(--accent)]' : 'text-[var(--text-tertiary)]'}
          />
        </div>

        <div className="text-center">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {dragging ? 'Drop to add files' : 'Drop video files here, or click to browse'}
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            MP4, MOV, AVI, MKV, WebM — up to 2 GB per file
          </p>
        </div>

        {/* Hidden real file input — always accessible */}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={accept}
          multiple={multiple}
          className="sr-only"
          aria-label="File upload input"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* File chips */}
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Selected files">
          {files.map((file, i) => (
            <li
              key={`${file.name}-${i}`}
              className="animate-slide-left flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-full)]
                         bg-[var(--surface-3)] border border-[var(--border)] text-xs text-[var(--text-secondary)]"
            >
              <VideoFileIcon className="text-[var(--accent)] shrink-0" />
              <span className="max-w-[180px] truncate font-medium text-[var(--text-primary)]">
                {file.name}
              </span>
              <span className="text-[var(--text-tertiary)]">{formatFileSize(file.size)}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                aria-label={`Remove ${file.name}`}
                className="ml-0.5 text-[var(--text-tertiary)] hover:text-[var(--text-primary)]
                           transition-colors duration-[var(--duration-fast)] rounded-sm"
              >
                <CloseIcon />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p role="alert" className="text-xs text-[var(--status-error)]">{error}</p>
      )}
    </div>
  );
}

/* ─── Inline SVG icons ───────────────────────────────────────────────────── */

function UploadIcon({ className }: { className?: string }) {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function VideoFileIcon({ className }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true">
      <polygon points="23 7 16 12 23 17 23 7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
         aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
