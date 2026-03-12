# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Prompt-driven video editor: a FastAPI backend that accepts natural language prompts and video uploads, then uses AI agents to analyze, plan, and render edited video. Currently in early development — core API works with simple keyword-based editing; most modules are scaffolded but empty.

## Commands

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run the FastAPI server
cd backend && uvicorn app.main:app --reload

# FFmpeg must be installed and available on PATH (used for silence removal and rendering)
```

No test suite exists yet.

## Architecture

### Request Flow

```
HTTP Request (prompt + video files)
  → POST /jobs/ (routes_jobs.py) — creates UUID job dir, stores files in storage/jobs/{job_id}/raw/
  → POST /generate (main.py) — keyword matching on prompt → moviepy transforms → output to processed/
  → POST /remove-silence (main.py) → video_processing.py → FFmpeg silenceremove filter
```

### Module Layout (backend/app/)

| Module | Purpose | Status |
|--------|---------|--------|
| `main.py` | FastAPI app, /generate and /remove-silence endpoints | Implemented (basic) |
| `video_processing.py` | FFmpeg-based silence removal | Implemented |
| `api/routes_jobs.py` | Job creation with file uploads, UUID-based job dirs | Implemented |
| `agents/` | 8 AI agents (planner, editing, captions, highlight, music, story, thumbnail, explanation) | Empty placeholders |
| `intelligence/` | Video analysis (transcribe, audio_features, faces, motion, shots) | Empty placeholders |
| `dsl/schema.py` | Video editing instruction schema | Empty |
| `jobs/pipeline.py` | Job execution pipeline orchestration | Empty |
| `render/` | FFmpeg command building and render execution | Empty |
| `storage/storage_manager.py` | File/artifact management | Empty |
| `worker/worker.py` | Background job worker | Empty |
| `core/config.py`, `core/logger.py` | Config and logging | Empty |
| `db/jobs_db.py` | Job persistence | Empty |

### Key Patterns

- **Job isolation**: Each job gets a UUID directory under `storage/jobs/{job_id}/` with a `raw/` subfolder for uploads.
- **Current video processing**: Uses moviepy for transforms (trim, B&W, slow-mo) triggered by keyword matching in the prompt string. This is a placeholder for future LLM-driven editing.
- **Planned multi-agent pipeline**: Agents in `agents/` are intended to handle different aspects of editing (planning, captioning, music, etc.), coordinated by `jobs/pipeline.py`.

### External Dependencies

- **FastAPI/Uvicorn**: HTTP server
- **moviepy**: High-level video editing (note: not listed in requirements.txt)
- **ffmpeg-python**: FFmpeg wrapper for audio/video processing
- **librosa/scipy/scikit-learn**: Audio feature extraction
- **opencv-python**: Computer vision (imported but unused currently)
- **FFmpeg binary**: Required on system PATH

### File Storage Layout

```
uploads/          — raw uploaded files (used by /generate)
processed/        — output from /generate
storage/jobs/     — job-based storage (used by /jobs/ endpoint)
  {uuid}/raw/     — uploaded files per job
```

---

## System Design Specification

This section defines the target architecture and design rules for the autonomous prompt-driven video editing system. All implementation work must follow these principles.

### Core Objective

Convert raw media (video clips, audio, images, music) + a natural language prompt into a fully edited video with subtitles, transitions, background music, thumbnail, and an explanation of editing decisions. The system acts as a **Creative Director AI**.

### Fundamental Design Rules

1. **Deterministic Rendering** — All rendering is handled by FFmpeg pipelines. LLMs NEVER directly manipulate video. LLMs only produce structured plans and metadata.

2. **Signal-Based Intelligence** — All media analysis produces structured timestamped JSON signals. Agents operate ONLY on signals, NEVER on raw video.

3. **Multi-Agent Architecture** — Specialized agents instead of a single model. Each agent has clear inputs, deterministic outputs, and JSON schemas.

4. **Timeline DSL** — All editing occurs via an intermediate JSON representation (the single source of truth for rendering):

```json
{
  "format": { "aspect": "9:16", "fps": 30 },
  "clips": [
    { "source": "clip1.mp4", "start": 12.3, "end": 14.0, "transition": "flash" }
  ],
  "captions": [
    { "time": 13.0, "text": "NO WAY", "style": "tiktok_bold" }
  ],
  "music": { "track": "track1.mp3", "sync_beats": true }
}
```

### Target Repository Structure

```
backend/
  app/
    api/            jobs.py, upload.py
    core/           config.py, logging.py
    db/             models.py
    jobs/           pipeline.py, orchestrator.py
    intelligence/   transcribe.py, diarize.py, audio_features.py, shots.py, motion.py, faces.py
    agents/         planner.py, highlight.py, story.py, editing.py, captions.py, music.py, thumbnail.py, explanation.py
    dsl/            schema.py, validators.py
    render/         ffmpeg_builder.py, run.py
    storage/        local_store.py, s3_store.py
    worker/         worker.py
frontend/           React / Next.js / Tailwind CSS
```

### Job Storage Structure

Each job must use stage-based artifact directories for resumability:

```
storage/jobs/<job_id>/
  raw/       — uploaded files
  prep/      — standardized media (extracted audio, proxy video)
  signals/   — JSON signals from intelligence modules
  plans/     — agent outputs (structured JSON)
  dsl/       — Timeline DSL files
  render/    — intermediate render artifacts
  outputs/   — final deliverables
```

### Media Preprocessing

All media must be standardized before analysis:
- Extract audio: `ffmpeg -i clip.mp4 -ac 1 -ar 16000 -vn clip_audio.wav`
- Create proxy video: `ffmpeg -i clip.mp4 -vf scale=854:-2 -c:v libx264 -preset veryfast -crf 28 clip_proxy.mp4`
- Output directory: `prep/`

### Intelligence Modules (signals/)

All modules produce JSON signals saved to `signals/`:

| Module | Tool | Output |
|--------|------|--------|
| Transcription | Whisper / WhisperX | transcript.json (word timestamps) |
| Speaker Diarization | pyannote | speakers.json |
| Silence Detection | FFmpeg / librosa RMS | silence.json, audio_curve.json, peaks.json |
| Shot Detection | PySceneDetect | shots.json |
| Motion Detection | OpenCV frame differencing / optical flow | motion.json |
| Face Detection | MediaPipe | faces.json |

### Agent Specifications

**Planner Agent** — Reads user prompt + signal summaries. Outputs structured plan:
```json
{
  "goal": "30s gaming montage",
  "duration": 30,
  "style": { "energy": "high", "aspect": "9:16" },
  "constraints": { "max_clips": 8 },
  "priorities": { "motion": 0.5, "audio_peak": 0.3, "keywords": 0.2 }
}
```

**Highlight Selection Agent** — Ranks candidate segments from shots/audio peaks/transcript windows using:
`score = motion_weight * motion_score + audio_weight * peak_score + keyword_weight * sentiment_score + face_weight * face_presence`

**Story Composer Agent** — Constructs narrative structure (Hook → Build → Peak → Ending), ensures pacing matches style energy. Outputs ordered highlight segments.

**Editing Agent** — Converts story sequence into Timeline DSL. Adds trims, transitions, zoom effects, crop rules, clip durations. Validates DSL with schema.

**Caption Agent** — Generates subtitles: 2-6 word groups, emphasized hype words, TikTok-style captions. Outputs `captions.ass`.

**Music Agent** — Chooses music track, runs beat detection (librosa), aligns clip cuts with beats. Outputs `music.json`.

**Thumbnail Agent** — Selects best frame (high motion, clear face, excitement peak), overlays text. Outputs `thumbnail.png`.

**Explanation Agent** — Generates human-readable explanation of editing decisions. Outputs `explanation.json`.

### Worker Pipeline Order

Workers execute in strict order, each stage writing artifacts to disk:
1. `preprocess_media(job_id)`
2. `run_intelligence(job_id)`
3. `run_agents(job_id)`
4. `render(job_id)`
5. `finalize(job_id)`

### Technology Stack

- **Backend**: Python, FastAPI, FFmpeg, OpenCV, PyTorch, Whisper/WhisperX, pyannote, librosa, MediaPipe
- **Queue**: Redis + Celery
- **Frontend**: React, Next.js, Tailwind CSS

### Implementation Priority (MVP)

**Phase 1**: Preprocessing, transcription, silence removal, DSL schema, FFmpeg render, basic subtitles

**Phase 2**: Highlight detection, shot detection, WhisperX, animated captions, beat sync

**Phase 3**: Face tracking, improved highlight scoring, thumbnail generation, explanation agent

### Code Rules

- Produce full working files with docstrings
- Maintain modular design — no monolithic scripts
- Keep components isolated
- Follow Python best practices
- Always reason about architecture before implementation
