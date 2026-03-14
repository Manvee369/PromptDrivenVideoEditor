# Prompt-Driven Video Editor — Complete Project Guide

> **All-in-one reference** for understanding the architecture, data flow, tech stack, and every component of the system. Read this to go from zero to full understanding.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Tech Stack](#2-tech-stack)
3. [Repository Structure](#3-repository-structure)
4. [System Architecture Overview](#4-system-architecture-overview)
5. [End-to-End Flow: What Happens When a User Uploads a Video](#5-end-to-end-flow)
6. [Backend Deep Dive](#6-backend-deep-dive)
   - 6.1 [API Layer](#61-api-layer)
   - 6.2 [Job Management](#62-job-management)
   - 6.3 [Storage Manager](#63-storage-manager)
   - 6.4 [Pipeline Orchestration](#64-pipeline-orchestration)
   - 6.5 [Preprocessing](#65-preprocessing)
   - 6.6 [Intelligence Modules](#66-intelligence-modules)
   - 6.7 [Content Classification & Strategy](#67-content-classification--strategy)
   - 6.8 [Agent Modules](#68-agent-modules)
   - 6.9 [DSL & Rendering](#69-dsl--rendering)
7. [Frontend Deep Dive](#7-frontend-deep-dive)
   - 7.1 [Pages & Routing](#71-pages--routing)
   - 7.2 [Component Library](#72-component-library)
   - 7.3 [API Client & Hooks](#73-api-client--hooks)
   - 7.4 [Design System](#74-design-system)
8. [AI Models & Libraries](#8-ai-models--libraries)
9. [Configuration Reference](#9-configuration-reference)
10. [How Components Connect](#10-how-components-connect)

---

## 1. What This Project Does

A user uploads one or more video files and types a natural language prompt like:

> *"Make a 30 second TikTok highlight reel with bold captions. High energy, vertical format."*

The system then:
1. Analyzes the video (speech, faces, motion, shots, visual content)
2. Classifies what kind of video it is (podcast, sports, gaming, etc.)
3. Plans the edit using an LLM or rule-based planner
4. Selects the best moments, arranges them into a narrative
5. Builds a timeline with transitions, captions, and music sync
6. Renders the final video via FFmpeg
7. Generates a thumbnail and a human-readable explanation

No human intervention. Fully autonomous. The user gets back a finished video.

---

## 2. Tech Stack

### Backend
```
 Language        Python 3.11+
 Framework       FastAPI + Uvicorn
 Video Engine    FFmpeg (binary on PATH)
 Speech-to-Text  OpenAI Whisper (small model)
 Vision          SigLIP ViT-B/16 (via open_clip + transformers)
 Face Detection  MediaPipe Blaze Face
 Scene Detection PySceneDetect (ContentDetector)
 Audio Analysis  librosa (RMS, beat detection, peaks)
 Motion          OpenCV (frame differencing)
 Clustering      scikit-learn (AgglomerativeClustering for diarization)
 LLM Planner     Groq API (openai/gpt-oss-120b)
 Image           Pillow (thumbnails)
 Data Models     Pydantic v2
```

### Frontend
```
 Framework       Next.js 14.2 (App Router)
 UI Library      React 18.3
 Language        TypeScript 5
 Styling         Tailwind CSS 3.4 + CSS custom properties
 Class Merging   clsx + tailwind-merge
 HTTP Client     Native fetch (typed wrappers)
```

### External Services
```
 Groq API        LLM planning (with API key)
 HuggingFace Hub SigLIP model/tokenizer download (auto on first use)
```

---

## 3. Repository Structure

```
PromptDrivenVideoEditor/
├── CLAUDE.md                          # AI coding instructions
├── guide.md                           # This file
├── .gitignore
│
├── backend/
│   ├── requirements.txt               # Python dependencies
│   ├── .env                           # PDVE_LLM_API_KEY, PDVE_LLM_MODEL
│   ├── models/                        # Downloaded ML models (gitignored)
│   │   └── blaze_face_short_range.tflite
│   ├── storage/                       # Job artifacts (gitignored)
│   │   └── jobs/{job_id}/             # Per-job directories
│   │
│   └── app/
│       ├── main.py                    # FastAPI app entry point
│       ├── video_processing.py        # Legacy silence removal
│       │
│       ├── api/
│       │   └── routes_jobs.py         # All REST endpoints
│       │
│       ├── core/
│       │   ├── config.py              # Settings (env vars, PDVE_ prefix)
│       │   └── logger.py              # Logging setup
│       │
│       ├── db/
│       │   └── jobs_db.py             # In-memory job store
│       │
│       ├── storage/
│       │   └── storage_manager.py     # File/artifact abstraction
│       │
│       ├── jobs/
│       │   ├── pipeline.py            # Pipeline orchestrator (THE core)
│       │   └── preprocess.py          # Media standardization
│       │
│       ├── intelligence/              # Signal extraction modules
│       │   ├── transcribe.py          # Whisper speech-to-text
│       │   ├── audio_features.py      # Silence detection + energy/peaks
│       │   ├── diarization.py         # Speaker identification
│       │   ├── shots.py               # Scene/shot boundary detection
│       │   ├── motion.py              # Motion intensity analysis
│       │   ├── faces.py               # Face detection
│       │   └── visual_scoring.py      # SigLIP visual classification
│       │
│       ├── agents/                    # Decision-making modules
│       │   ├── content_classifier.py  # Video type + intent detection
│       │   ├── strategy_router.py     # Strategy selection
│       │   ├── planner.py             # Rule-based planner + LLM dispatch
│       │   ├── llm_planner.py         # Groq LLM planner
│       │   ├── highlight.py           # Segment scoring + ranking
│       │   ├── story.py               # Narrative structure composer
│       │   ├── editing.py             # Timeline DSL builder
│       │   ├── captions.py            # Subtitle generation + ASS output
│       │   ├── music.py               # Beat detection + cut alignment
│       │   ├── thumbnail.py           # Best frame selection + overlay
│       │   └── explanation.py         # Human-readable decision summary
│       │
│       ├── dsl/
│       │   ├── schema.py              # Timeline data models (Pydantic)
│       │   └── validators.py          # Timeline validation rules
│       │
│       ├── render/
│       │   ├── ffmpeg_builder.py      # FFmpeg command construction
│       │   └── run_render.py          # Render execution
│       │
│       └── utils/
│           └── ffmpeg_utils.py        # FFmpeg/FFprobe helpers
│
└── frontend/
    ├── package.json
    ├── next.config.mjs                # Image remotes, API rewrites
    ├── tailwind.config.ts             # Design token extensions
    ├── tsconfig.json
    ├── .env.local                     # NEXT_PUBLIC_API_URL
    │
    └── src/
        ├── app/
        │   ├── layout.tsx             # Root layout (sidebar + main)
        │   ├── page.tsx               # Home: new job form
        │   ├── Sidebar.tsx            # Navigation sidebar
        │   ├── history/page.tsx       # Job history table
        │   └── jobs/[jobId]/page.tsx  # Job detail + video player
        │
        ├── components/
        │   ├── ui/                    # Reusable primitives
        │   │   ├── Button.tsx         # 4 variants, loading state
        │   │   ├── Card.tsx           # Surface container
        │   │   ├── Badge.tsx          # Status indicator
        │   │   ├── Spinner.tsx        # SVG spinner
        │   │   ├── Input.tsx          # Text input
        │   │   ├── Textarea.tsx       # Auto-grow, char counter
        │   │   ├── DropZone.tsx       # Drag-drop file upload
        │   │   ├── ProgressBar.tsx    # Linear progress + shimmer
        │   │   └── ProgressRing.tsx   # Circular SVG progress
        │   │
        │   └── job/                   # Job-specific composites
        │       ├── VideoPlayer.tsx     # Custom HTML5 player
        │       ├── StageTimeline.tsx   # Pipeline stage viz
        │       ├── StatGrid.tsx       # 2-col stats
        │       ├── ExplanationAccordion.tsx
        │       ├── PromptDisplay.tsx
        │       └── JobCard.tsx        # Job preview card
        │
        ├── lib/
        │   ├── api.ts                 # Typed backend API client
        │   ├── utils.ts              # Formatting helpers
        │   └── hooks/
        │       ├── useJob.ts          # Single job poller
        │       └── useJobs.ts         # Job list fetcher
        │
        ├── types/
        │   └── job.ts                 # TypeScript interfaces
        │
        └── styles/
            └── globals.css            # Design tokens + reset
```

---

## 4. System Architecture Overview

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Next.js)                         │
│                                                                      │
│  ┌─────────┐   ┌──────────┐   ┌─────────────┐   ┌──────────────┐   │
│  │ New Edit │   │ History  │   │ Job Detail  │   │   Sidebar    │   │
│  │  Page    │   │  Page    │   │    Page     │   │              │   │
│  │         │   │          │   │             │   │ Recent Jobs  │   │
│  │ DropZone │   │ JobCards  │   │ ProgressRing│   │ Navigation   │   │
│  │ Textarea │   │ Filters  │   │ VideoPlayer │   │              │   │
│  │ Analysis │   │ Search   │   │ Explanation │   │              │   │
│  └────┬─────┘   └────┬─────┘   └──────┬──────┘   └──────────────┘   │
│       │              │                │                              │
│       └──────────────┴────────────────┘                              │
│                       │                                              │
│              ┌────────┴────────┐                                     │
│              │   API Client    │  (typed fetch wrappers)             │
│              │   lib/api.ts    │                                     │
│              └────────┬────────┘                                     │
└───────────────────────┼──────────────────────────────────────────────┘
                        │ HTTP (localhost:8000)
                        │
┌───────────────────────┼──────────────────────────────────────────────┐
│                       │         BACKEND (FastAPI)                    │
│              ┌────────┴────────┐                                     │
│              │   API Routes    │  POST /jobs/, GET /jobs/{id}, etc.  │
│              │ routes_jobs.py  │                                     │
│              └────────┬────────┘                                     │
│                       │                                              │
│              ┌────────┴────────┐         ┌────────────────┐          │
│              │   Jobs DB       │         │ Storage Manager │          │
│              │ (in-memory)     │         │ (file system)   │          │
│              └────────┬────────┘         └───────┬────────┘          │
│                       │                          │                   │
│              ┌────────┴──────────────────────────┴──────┐            │
│              │          PIPELINE ORCHESTRATOR            │            │
│              │            pipeline.py                    │            │
│              └────────┬─────────────────────────────────┘            │
│                       │                                              │
│    ┌──────────────────┼──────────────────────────────────┐           │
│    │                  │                                   │           │
│    ▼                  ▼                                   ▼           │
│ ┌──────────┐  ┌───────────────┐  ┌─────────────────────────────┐    │
│ │  PREPROC │  │ INTELLIGENCE  │  │         AGENTS              │    │
│ │          │  │               │  │                             │    │
│ │ Extract  │  │ Transcribe    │  │ Classifier → Strategy      │    │
│ │ audio    │  │ Silence       │  │ Planner (LLM / Rules)      │    │
│ │ Create   │  │ Energy/Peaks  │  │ Highlights → Story         │    │
│ │ proxy    │  │ Shots         │  │ Editing → Captions         │    │
│ │          │  │ Motion        │  │ Music → Thumbnail          │    │
│ │          │  │ Faces         │  │ Explanation                 │    │
│ │          │  │ Diarization   │  │                             │    │
│ │          │  │ Visual (SigLIP)│ │                             │    │
│ └──────────┘  └───────────────┘  └──────────────┬──────────────┘    │
│                                                  │                   │
│                                         ┌────────┴────────┐         │
│                                         │  DSL (Timeline)  │         │
│                                         │  schema.py       │         │
│                                         └────────┬────────┘         │
│                                                  │                   │
│                                         ┌────────┴────────┐         │
│                                         │    RENDERER      │         │
│                                         │ ffmpeg_builder   │         │
│                                         │ → FFmpeg binary  │         │
│                                         └────────┬────────┘         │
│                                                  │                   │
│                                            final.mp4                 │
│                                            thumbnail.png             │
│                                            explanation.json          │
└──────────────────────────────────────────────────────────────────────┘
```

### Core Design Principles

| Principle | What It Means |
|-----------|---------------|
| **Deterministic Rendering** | FFmpeg renders everything. LLMs never touch video bytes. They only produce JSON plans. |
| **Signal-Based Intelligence** | All media analysis outputs timestamped JSON. Agents read signals, never raw video. |
| **Multi-Agent Architecture** | 11 specialized agents, each with clear inputs and outputs. No monolithic processing. |
| **Timeline DSL** | A single JSON document is the source of truth for rendering. Everything builds toward it. |
| **Stage-Based Storage** | Each job gets isolated directories per pipeline stage, enabling resumability. |
| **Graceful Degradation** | Non-critical modules (diarization, thumbnail, visual scoring) fail without killing the pipeline. |

---

## 5. End-to-End Flow

### What happens when a user uploads a video and types a prompt

This is the complete journey, from button click to finished video.

```
USER ACTION                           SYSTEM RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. User drags video files       →  DropZone component stores File[]
    into the upload zone             in React state

 2. User types editing prompt    →  Textarea stores string in state
    "Make a 30s TikTok reel          (max 500 chars)
     with bold captions"

 3. User clicks "Start Editing"  →  Frontend calls POST /jobs/analyze
                                     (pre-flight content analysis)

 4. Backend analyzes content     →  Quick preprocess + classify only
    - Extract audio, detect          Returns: video_type, user_intent,
      speech, count speakers         warnings[], strategy_summary
    - Classify: "talking_head"
      intent: "highlight_reel"

 5. If warnings exist           →  Frontend shows warning banner:
    (e.g., "highlight reel on        "Proceed Anyway" / "Change Prompt"
     talking head may not work")

 6. User confirms / no warnings  →  Frontend calls POST /jobs/
                                     with FormData (prompt + files)

 7. Backend creates job          →  Generate UUID job_id
                                     Create storage/jobs/{id}/ dirs
                                     Save files to raw/
                                     Register in JobsDB (status: created)
                                     Launch pipeline in background thread
                                     Return { job_id, status: "created" }

 8. Frontend navigates to        →  /jobs/{job_id} page
    job detail page                  useJob() hook starts polling
                                     every 1.5 seconds

 9. Pipeline runs (see below)    →  Progress updates: 0% → 100%
                                     Status transitions through stages
                                     Frontend shows ProgressRing + stages

10. Pipeline completes           →  Status: "completed"
                                     Frontend stops polling
                                     Shows VideoPlayer, stats, explanation

11. User watches/downloads       →  GET /jobs/{id}/download → final.mp4
                                     GET /jobs/{id}/thumbnail → thumbnail.png
```

### Pipeline Execution (Stage by Stage)

```
                          ┌─────────────────────┐
                          │   run_pipeline()     │
                          │   pipeline.py        │
                          └──────────┬──────────┘
                                     │
    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 1: PREPROCESSING          │                          Progress: 5%
    Status: "preprocessing"          │
    ─────────────────────────────────┤
                                     ▼
                          ┌─────────────────────┐
                          │  preprocess_media()  │
                          │  preprocess.py       │
                          └──────────┬──────────┘
                                     │
                    For each video file in raw/:
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌──────────┐   ┌──────────┐   ┌──────────────┐
              │ ffprobe  │   │ Extract  │   │ Create proxy │
              │ metadata │   │ audio    │   │ video        │
              │          │   │ 16kHz    │   │ 854px CRF28  │
              │ duration │   │ mono WAV │   │ libx264      │
              │ width    │   │          │   │              │
              │ height   │   │ → prep/  │   │ → prep/      │
              └──────────┘   └──────────┘   └──────────────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
                          signals/media_manifest.json
                          {
                            "files": [{
                              "filename": "video.mp4",
                              "duration": 480.0,
                              "width": 1920, "height": 1080,
                              "audio_path": "prep/video_audio.wav",
                              "proxy_path": "prep/video_proxy.mp4",
                              "raw_path": "raw/video.mp4"
                            }]
                          }

    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 2: INTELLIGENCE            │                     Progress: 15→48%
    Status: "intelligence"           │
    ─────────────────────────────────┤
                                     │
         9 intelligence modules run sequentially:
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                │                                │
    │  ┌─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  1. TRANSCRIPTION (15→20%)  │                                │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  transcribe_media()  │   │                                │
    │  │  │                      │   │                                │
    │  │  │  Whisper "small"     │   │                                │
    │  │  │  model loads on      │   │                                │
    │  │  │  first use (~461MB)  │   │                                │
    │  │  │                      │   │                                │
    │  │  │  Input: prep/*.wav   │   │                                │
    │  │  │  Output: transcript  │   │                                │
    │  │  │  with word times     │   │                                │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/transcript.json    │                                │
    │  │  { "tracks": [{             │                                │
    │  │      "source": "video.mp4", │                                │
    │  │      "segments": [{         │                                │
    │  │        "start": 0.0,        │                                │
    │  │        "end": 2.5,          │                                │
    │  │        "text": "Hello"      │                                │
    │  │      }],                    │                                │
    │  │      "full_text": "..."     │                                │
    │  │  }]}                        │                                │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  2. DIARIZATION (20→25%)    │   (non-fatal if fails)        │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  diarize()           │   │                                │
    │  │  │                      │   │                                │
    │  │  │  MFCC embeddings     │   │                                │
    │  │  │  + Agglomerative     │   │                                │
    │  │  │    Clustering        │   │                                │
    │  │  │                      │   │                                │
    │  │  │  Groups transcript   │   │                                │
    │  │  │  segments by speaker │   │                                │
    │  │  │  (A, B, C...)        │   │                                │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/diarization.json   │                                │
    │  │  { "tracks": [{             │                                │
    │  │      "num_speakers": 2,     │                                │
    │  │      "segments": [{         │                                │
    │  │        "start":0, "end":2.5,│                                │
    │  │        "speaker": "A"       │                                │
    │  │      }],                    │                                │
    │  │      "speaker_turns": [...]│                                │
    │  │  }]}                        │                                │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  3. SILENCE DETECTION       │                                │
    │  │  4. AUDIO ENERGY     (25→35%)                                │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  detect_silence()    │   │  FFmpeg silencedetect filter   │
    │  │  │  compute_audio_      │   │  librosa RMS + peak detection  │
    │  │  │    energy()          │   │                                │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/silence.json       │  silent_regions, speech_regions│
    │  │  signals/audio_energy.json  │  rms_curve, peaks              │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  5. SHOT DETECTION (35→40%) │                                │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  detect_shots()      │   │  PySceneDetect ContentDetector│
    │  │  │  threshold=27.0      │   │  Finds scene boundaries       │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/shots.json         │  shots[{start, end, duration}] │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  6. MOTION DETECTION (40→45%)                                │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  detect_motion()     │   │  OpenCV frame differencing     │
    │  │  │  sample_fps=5.0      │   │  at 5 FPS                     │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/motion.json        │  scores[{time, intensity}]     │
    │  │                             │  high_motion_regions[]         │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  7. FACE DETECTION (45→48%) │                                │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  detect_faces()      │   │  MediaPipe Blaze Face          │
    │  │  │  sample_fps=2.0      │   │  Downloads model on first use │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/faces.json         │  detections[{time,count,boxes}]│
    │  │                             │  face_regions[]                │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  8. MUSIC ANALYSIS          │  (only if audio files present) │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  analyze_music()     │   │  librosa beat tracking         │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/music_analysis.json│  tempo, beats[], downbeats[]   │
    │  │                             │                                │
    │  ├─────────────────────────────┤                                │
    │  │                             │                                │
    │  │  9. VISUAL SCORING (48%)    │  (non-fatal, if enabled)      │
    │  │  ┌──────────────────────┐   │                                │
    │  │  │  compute_visual_     │   │  SigLIP ViT-B/16             │
    │  │  │    scores()          │   │  ~400MB model download        │
    │  │  │                      │   │                                │
    │  │  │  Extracts keyframes  │   │  1 per shot midpoint          │
    │  │  │  Scores vs prompt    │   │  text-image similarity        │
    │  │  │  Classifies type     │   │  zero-shot classification     │
    │  │  └──────────┬───────────┘   │                                │
    │  │             ▼               │                                │
    │  │  signals/visual_scores.json │  keyframes[{time,prompt_score}]│
    │  │                             │  top_type, classification{}    │
    │  │                             │                                │
    └──┴─────────────────────────────┴────────────────────────────────┘

    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 3: CLASSIFICATION + PLANNING │                   Progress: 50%
    Status: "planning"               │
    ─────────────────────────────────┤
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                │                                │
    │  Step A: CLASSIFY CONTENT      │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  classify_content()      │  │                                │
    │  │  content_classifier.py   │  │                                │
    │  │                          │  │                                │
    │  │  Inputs:                 │  │                                │
    │  │  - All signals           │  │                                │
    │  │  - User prompt           │  │                                │
    │  │                          │  │                                │
    │  │  Heuristic features:     │  │                                │
    │  │  - Speaker count (diar.) │  │                                │
    │  │  - Speech ratio          │  │                                │
    │  │  - Motion intensity      │  │                                │
    │  │  - Face presence         │  │                                │
    │  │  - Shot count/variety    │  │                                │
    │  │                          │  │                                │
    │  │  Blends with SigLIP:     │  │                                │
    │  │  40% heuristic +         │  │                                │
    │  │  60% visual scores       │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │ video_type: "podcast"    │  │                                │
    │  │ confidence: 0.82         │  │                                │
    │  │ user_intent: "highlight" │  │                                │
    │  │ warnings: [...]          │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             │                  │                                │
    │  Step B: GET STRATEGY          │                                │
    │  ┌──────────┴───────────────┐  │                                │
    │  │  get_strategy()          │  │                                │
    │  │  strategy_router.py      │  │                                │
    │  │                          │  │                                │
    │  │  Maps (type, intent)     │  │                                │
    │  │  → editing config:       │  │                                │
    │  │                          │  │                                │
    │  │  operations: [...]       │  │                                │
    │  │  highlight_weights: {}   │  │                                │
    │  │  caption_config: {}      │  │                                │
    │  │  story_structure: "..."  │  │                                │
    │  │  transition_config: {}   │  │                                │
    │  │  energy: "high"          │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             │                  │                                │
    │  Step C: PLAN EDIT             │                                │
    │  ┌──────────┴───────────────┐  │                                │
    │  │  plan_edit()             │  │                                │
    │  │  planner.py              │  │                                │
    │  │                          │  │                                │
    │  │  Try 1: LLM Planner     │  │  Groq API call                │
    │  │    llm_plan_edit()       │  │  System prompt + media summary │
    │  │    → JSON plan           │  │  + transcript excerpt          │
    │  │                          │  │                                │
    │  │  Try 2: Rule-Based      │  │  Keyword matching, regex       │
    │  │    _rule_based_plan()    │  │  for duration, aspect, etc.   │
    │  │                          │  │                                │
    │  │  Merges strategy ops    │  │                                │
    │  │  into final plan        │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │  plans/plan.json               │                                │
    │  {                             │                                │
    │    "goal": "30s highlight reel"│                                │
    │    "target_duration": 30,      │                                │
    │    "style": {                  │                                │
    │      "aspect": "9:16",         │                                │
    │      "energy": "high"          │                                │
    │    },                          │                                │
    │    "operations": [             │                                │
    │      "highlight_select",       │                                │
    │      "story_compose",          │                                │
    │      "add_captions",           │                                │
    │      "add_transitions"         │                                │
    │    ],                          │                                │
    │    "priorities": {             │                                │
    │      "motion": 0.25,           │                                │
    │      "audio_peak": 0.20,       │                                │
    │      "visual_relevance": 0.20  │                                │
    │    },                          │                                │
    │    "strategy": { ... }         │                                │
    │  }                             │                                │
    │                                │                                │
    └────────────────────────────────┴────────────────────────────────┘

    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 4: AGENTS                  │                     Progress: 55→70%
    Status: "planning" → "rendering" │
    ─────────────────────────────────┤
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                │                                │
    │  4a. HIGHLIGHT SELECTION       │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  select_highlights()     │  │                                │
    │  │                          │  │                                │
    │  │  For each shot/window:   │  │                                │
    │  │                          │  │                                │
    │  │  score = Σ weight * dim  │  │                                │
    │  │                          │  │                                │
    │  │  Dimensions:             │  │                                │
    │  │  ├─ motion       (0.25) │  │  avg intensity in window      │
    │  │  ├─ audio_peak   (0.20) │  │  peak density                 │
    │  │  ├─ visual_rel   (0.20) │  │  SigLIP prompt similarity     │
    │  │  ├─ speech       (0.15) │  │  speech overlap ratio         │
    │  │  ├─ shot_variety (0.10) │  │  shorter = more dynamic       │
    │  │  └─ face         (0.10) │  │  face detection confidence    │
    │  │                          │  │                                │
    │  │  Ranks all candidates    │  │                                │
    │  │  by total score desc.    │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │  plans/highlights.json         │  [{source, start, end, score}] │
    │                                │                                │
    │  4b. STORY COMPOSITION         │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  compose_story()         │  │                                │
    │  │                          │  │                                │
    │  │  Narrative structures:   │  │                                │
    │  │                          │  │                                │
    │  │  HIGH ENERGY:            │  │                                │
    │  │  Hook(12%)→Build(20%)    │  │                                │
    │  │  →Climax(25%)→Finale(18%)│  │                                │
    │  │                          │  │                                │
    │  │  MEDIUM:                 │  │                                │
    │  │  Intro→Dev→Peak→Resolve  │  │                                │
    │  │                          │  │                                │
    │  │  LOW:                    │  │                                │
    │  │  Intro→Body→Conclusion   │  │                                │
    │  │                          │  │                                │
    │  │  CHRONOLOGICAL:          │  │                                │
    │  │  Best moments, time order│  │                                │
    │  │                          │  │                                │
    │  │  Assigns roles, budgets, │  │                                │
    │  │  preserves source order  │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │  plans/story.json              │  [{source,start,end,role}]     │
    │                                │                                │
    │  4c. TIMELINE BUILDING         │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  build_timeline()        │  │                                │
    │  │  editing.py              │  │                                │
    │  │                          │  │                                │
    │  │  Converts segments →     │  │                                │
    │  │  Timeline DSL clips      │  │                                │
    │  │                          │  │                                │
    │  │  Applies:                │  │                                │
    │  │  - Speed changes         │  │                                │
    │  │  - Video filters         │  │                                │
    │  │  - Transitions (xfade)   │  │                                │
    │  │  - Beat sync (±0.25s)    │  │                                │
    │  │  - Duration trimming     │  │                                │
    │  │  - Music track selection │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │                                │                                │
    │  4d. CAPTION GENERATION        │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  generate_captions()     │  │                                │
    │  │  captions.py             │  │                                │
    │  │                          │  │                                │
    │  │  Maps transcript to      │  │                                │
    │  │  output timeline         │  │                                │
    │  │                          │  │                                │
    │  │  Speaker tags:           │  │                                │
    │  │  [Speaker A] only for    │  │                                │
    │  │  podcast/interview       │  │                                │
    │  │                          │  │                                │
    │  │  generate_ass_file()     │  │  ASS subtitle format          │
    │  │  - Static or animated    │  │                                │
    │  │  - Word-by-word reveal   │  │                                │
    │  │  - Hype word highlights  │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             ▼                  │                                │
    │  render/captions.ass           │                                │
    │  dsl/timeline.json             │  ← THE SINGLE SOURCE OF TRUTH │
    │                                │                                │
    └────────────────────────────────┴────────────────────────────────┘

    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 5: RENDERING               │                     Progress: 70%
    Status: "rendering"              │
    ─────────────────────────────────┤
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                │                                │
    │  ┌──────────────────────────┐  │                                │
    │  │  render_timeline()       │  │                                │
    │  │  run_render.py           │  │                                │
    │  │                          │  │                                │
    │  │  1. Load dsl/timeline    │  │                                │
    │  │  2. Validate sources     │  │                                │
    │  │  3. FFmpegCommandBuilder │  │                                │
    │  │     builds the command   │  │                                │
    │  └──────────┬───────────────┘  │                                │
    │             │                  │                                │
    │             ▼                  │                                │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │                   FFmpeg Command                          │   │
    │  │                                                          │   │
    │  │  ffmpeg                                                  │   │
    │  │    -i raw/clip1.mp4                                      │   │
    │  │    -i raw/music.mp3          (if music)                  │   │
    │  │    -filter_complex "                                     │   │
    │  │      [0:v]trim=3:8,setpts,...,scale=1080:1920[v0];       │   │
    │  │      [0:v]trim=15:21,setpts,...,scale=1080:1920[v1];     │   │
    │  │      [v0][v1]xfade=transition=fade:duration=0.3[outv];   │   │
    │  │      [0:a]atrim=3:8,...[a0];                              │   │
    │  │      [0:a]atrim=15:21,...[a1];                            │   │
    │  │      [a0][a1]acrossfade=d=0.3[outa];                     │   │
    │  │      [outa][1:a]amix=inputs=2[finala]                    │   │
    │  │    "                                                     │   │
    │  │    -map [outv] -map [finala]                              │   │
    │  │    -vf "ass=render/captions.ass"    (if captions)         │   │
    │  │    -c:v libx264 -preset medium -crf 22                   │   │
    │  │    -c:a aac -b:a 128k                                    │   │
    │  │    -movflags +faststart                                  │   │
    │  │    outputs/final.mp4                                     │   │
    │  └──────────────────────────────────────────────────────────┘   │
    │             │                                                    │
    │             ▼                                                    │
    │       outputs/final.mp4                                         │
    │                                                                  │
    └──────────────────────────────────────────────────────────────────┘

    ══════════════════════════════════╪═══════════════════════════════════
    STAGE 6: POST-PROCESSING         │                     Progress: 90→100%
    Status: "completed"              │
    ─────────────────────────────────┤
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                │                                │
    │  THUMBNAIL (non-fatal)         │  EXPLANATION (non-fatal)      │
    │  ┌──────────────────────┐      │  ┌──────────────────────┐     │
    │  │ generate_thumbnail() │      │  │ generate_explanation()│     │
    │  │                      │      │  │                      │     │
    │  │ Score = 0.35*motion  │      │  │ Collects stats from  │     │
    │  │       + 0.40*face    │      │  │ all pipeline stages  │     │
    │  │       + 0.25*peak    │      │  │                      │     │
    │  │                      │      │  │ Builds summary +     │     │
    │  │ Extract best frame   │      │  │ decisions list +     │     │
    │  │ Resize to aspect     │      │  │ stats object         │     │
    │  │ Add text overlay     │      │  │                      │     │
    │  └──────────┬───────────┘      │  └──────────┬───────────┘     │
    │             ▼                  │             ▼                  │
    │  outputs/thumbnail.png         │  outputs/explanation.json     │
    │                                │                                │
    └────────────────────────────────┴────────────────────────────────┘

    ══════════════════════════════════════════════════════════════════════
    DONE — Job status set to "completed", progress = 1.0
    Frontend stops polling, shows video player + results
    ══════════════════════════════════════════════════════════════════════
```

---

## 6. Backend Deep Dive

### 6.1 API Layer

**File**: `app/api/routes_jobs.py` — All REST endpoints

| Method | Path | Purpose | Returns |
|--------|------|---------|---------|
| `POST` | `/jobs/` | Create job + upload files | `{job_id, status}` |
| `GET` | `/jobs/` | List all jobs | `JobRecord[]` |
| `GET` | `/jobs/{id}` | Get job status + progress | `JobRecord` |
| `GET` | `/jobs/{id}/timeline` | Get Timeline DSL JSON | `TimelineDSL` |
| `GET` | `/jobs/{id}/download` | Download final video | `FileResponse` |
| `GET` | `/jobs/{id}/explanation` | Get editing explanation | `JobExplanation` |
| `GET` | `/jobs/{id}/thumbnail` | Download thumbnail | `FileResponse` |
| `POST` | `/jobs/analyze` | Pre-flight content analysis | `AnalysisResult` |

**How `POST /jobs/` works**:
```
Request (multipart form):
  prompt: "Make a 30s TikTok..."
  files: [video1.mp4, video2.mp4]

→ Generate UUID
→ StorageManager(job_id).ensure_dirs()
→ Save each file to storage/jobs/{id}/raw/
→ jobs_db.create(job_id, prompt)
→ BackgroundTask: run_pipeline(job_id, prompt)
→ Response: {"job_id": "abc-123", "status": "created"}
```

**How `POST /jobs/analyze` works**:
```
Request (multipart form):
  prompt: "Make a highlight reel"
  files: [video.mp4]

→ Temporary analysis_id (not a real job)
→ Quick preprocess (audio extract only)
→ Fast intelligence (transcribe, silence, faces, diarization)
→ classify_content() → video_type, user_intent, warnings
→ get_strategy() → strategy summary
→ Cleanup temp files
→ Response: {video_type, confidence, warnings, strategy_summary}
```

### 6.2 Job Management

**File**: `app/db/jobs_db.py`

```
Job Lifecycle:

  created → preprocessing → intelligence → planning → rendering → completed
                                                                  ↘ failed
```

**JobRecord fields**:
- `job_id` — UUID string
- `prompt` — User's editing instruction
- `status` — One of: created, preprocessing, intelligence, planning, rendering, completed, failed
- `progress` — Float 0.0 to 1.0
- `created_at`, `updated_at` — ISO timestamps
- `error` — Error message if failed
- `output_file` — Path to final.mp4 if completed

Thread-safe in-memory store (no database, resets on restart).

### 6.3 Storage Manager

**File**: `app/storage/storage_manager.py`

Each job gets an isolated directory tree:

```
storage/jobs/{job_id}/
│
├── raw/              Uploaded files (video, audio, images)
│   ├── video1.mp4
│   └── music.mp3
│
├── prep/             Standardized media
│   ├── video1_audio.wav     (16kHz mono)
│   └── video1_proxy.mp4     (854px, CRF 28)
│
├── signals/          Intelligence outputs (JSON)
│   ├── media_manifest.json
│   ├── transcript.json
│   ├── diarization.json
│   ├── silence.json
│   ├── audio_energy.json
│   ├── shots.json
│   ├── motion.json
│   ├── faces.json
│   ├── visual_scores.json
│   ├── music_analysis.json
│   └── classification.json
│
├── plans/            Agent decision outputs (JSON)
│   ├── plan.json
│   ├── highlights.json
│   └── story.json
│
├── dsl/              Timeline source of truth
│   └── timeline.json
│
├── render/           Intermediate render artifacts
│   └── captions.ass
│
└── outputs/          Final deliverables
    ├── final.mp4
    ├── thumbnail.png
    └── explanation.json
```

### 6.4 Pipeline Orchestration

**File**: `app/jobs/pipeline.py`

The pipeline is the heart of the system. It orchestrates all stages sequentially, updating job status and progress as it goes.

**Progress Map**:
```
 0%   Job started
 5%   Preprocessing complete
15%   Starting intelligence
20%   Transcription done
25%   Diarization done
35%   Silence + energy done
40%   Shots done
45%   Motion done
48%   Faces + visual scoring done
50%   Classification + strategy done
55%   Plan created
60%   Highlights selected
65%   Story composed
70%   Timeline built, captions generated
85%   Render complete
90%   Thumbnail generated
95%   Explanation generated
100%  Done
```

**Error handling**: Pipeline wraps everything in try/except. Non-fatal stages (diarization, visual scoring, thumbnail, explanation) log warnings but don't kill the pipeline. Fatal failures set job status to "failed" with error message.

### 6.5 Preprocessing

**File**: `app/jobs/preprocess.py`

For each video file:
1. **Probe** — `ffprobe` extracts duration, resolution
2. **Audio** — `ffmpeg -i clip.mp4 -ac 1 -ar 16000 -vn clip_audio.wav`
3. **Proxy** — `ffmpeg -i clip.mp4 -vf scale=854:-2 -c:v libx264 -preset veryfast -crf 28 clip_proxy.mp4`

Why proxy? Intelligence modules analyze the proxy (smaller, faster) instead of the full-resolution original. The final render uses the original.

### 6.6 Intelligence Modules

All modules live in `app/intelligence/` and write JSON to `signals/`.

```
                    prep/*.wav                      prep/*_proxy.mp4
                        │                                │
           ┌────────────┼────────────┐      ┌────────────┼────────────┐
           │            │            │      │            │            │
           ▼            ▼            ▼      ▼            ▼            ▼
     ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
     │Transcribe│ │ Silence  │ │ Energy │ │ Shots  │ │ Motion │ │ Faces  │
     │ Whisper  │ │ FFmpeg   │ │librosa │ │PyScene │ │OpenCV  │ │MediaPipe
     │ "small"  │ │silencedet│ │  RMS   │ │Detect  │ │frame   │ │BlazeFace
     └────┬─────┘ └────┬─────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
          │            │           │           │          │          │
          ▼            ▼           ▼           ▼          ▼          ▼
     transcript   silence.json  audio_     shots.json  motion.   faces.json
     .json        silent_rgns   energy     shot bounds  json      detections
     segments     speech_rgns   .json      start/end   scores    boxes
     words                      rms_curve              intensity  regions
                                peaks
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │Visual Scoring│
                                    │   SigLIP     │
                                    │  ViT-B/16    │
                                    └──────┬───────┘
                                           ▼
                                    visual_scores
                                    .json
                                    prompt_score
                                    type_classify

                   ┌───────────────────────────┐
                   │      Diarization          │
                   │  MFCC + Clustering        │
                   │  (uses transcript.json)   │
                   └───────────┬───────────────┘
                               ▼
                        diarization.json
                        speaker labels (A,B,C)
                        speaker turns
```

#### Module Details

| Module | Tool/Library | Input | Output Key Fields | First-Use Download |
|--------|-------------|-------|-------------------|--------------------|
| **Transcription** | Whisper "small" | prep/*.wav | segments[{start,end,text}], full_text | ~461MB model |
| **Silence** | FFmpeg silencedetect | prep/*.wav | silent_regions[], speech_regions[] | None |
| **Audio Energy** | librosa RMS | prep/*.wav | rms_curve[{time,value}], peaks[{time,strength}] | None |
| **Shots** | PySceneDetect | proxy/*.mp4 | shots[{start,end,duration}], total_shots | None |
| **Motion** | OpenCV | proxy/*.mp4 | scores[{time,intensity}], high_motion_regions[] | None |
| **Faces** | MediaPipe Blaze | proxy/*.mp4 | detections[{time,count,confidence,boxes}], face_regions[] | ~1MB model |
| **Diarization** | MFCC + sklearn | transcript + wav | num_speakers, segments[{...,speaker}], speaker_turns[] | None |
| **Visual Scoring** | SigLIP ViT-B/16 | proxy/*.mp4 + prompt | keyframes[{time,prompt_score,type_scores}], top_type | ~400MB model |
| **Music** | librosa beat_track | raw/*.mp3 | tempo, beats[], downbeats[], beat_interval | None |

### 6.7 Content Classification & Strategy

This is the intelligence layer that makes the system context-aware.

#### Classification (`content_classifier.py`)

Two-axis classification system:

```
VIDEO TYPE (what kind of content)          USER INTENT (what to do with it)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━           ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
talking_head   1 speaker, high face        clean_up        remove silence/filler
podcast        2+ speakers, high speech    highlight_reel  best moments montage
sports         high motion, many shots     recap           condensed summary
gaming         moderate motion, speech     reformat        change aspect ratio
vlog           1 speaker, varied           full_edit       complete edit
tutorial       1 speaker, low motion
event          many shots, moderate motion
raw_footage    low speech, few faces
cooking        moderate speech, low motion
music_performance  low speech, high motion
```

**How it classifies**:
1. Extract heuristic features from signals (speaker count, speech ratio, motion, faces, shots)
2. Score each video type with hand-tuned rules
3. If SigLIP visual scores exist, blend: 40% heuristic + 60% visual
4. Parse user intent from prompt keywords ("highlight", "clean up", "recap", etc.)
5. Check for mismatches and generate warnings

#### Strategy Router (`strategy_router.py`)

Maps `(video_type, user_intent)` → complete editing configuration:

```
Example: podcast + highlight_reel

  operations:       [highlight_select, story_compose, add_captions, add_transitions]
  highlight_weights: {speech: 0.35, face: 0.25, audio_peak: 0.15, ...}
  caption_config:   {speaker_tags: true, style: "default", animated: false}
  story_structure:  "high"
  transition_config: {style: "dynamic", crossfade_duration: 0.25}
  energy:           "high"
```

```
Example: talking_head + clean_up

  operations:       [remove_silence, add_captions]
  highlight_weights: {speech: 0.40, face: 0.30, ...}
  caption_config:   {speaker_tags: false, style: "default", animated: false}
  story_structure:  "chronological"
  transition_config: {style: "minimal", crossfade_duration: 0.4}
  energy:           "low"
```

### 6.8 Agent Modules

```
              plan.json + signals
                     │
        ┌────────────┼────────────────┐
        │            │                │
        ▼            │                │
  ┌───────────┐      │                │
  │ Highlight │      │                │
  │ Selection │      │                │
  │           │      │                │
  │ Scores    │      │                │
  │ every     │      │                │
  │ segment   │      │                │
  │ on 6 dims │      │                │
  └─────┬─────┘      │                │
        │            │                │
        ▼            │                │
  ┌───────────┐      │                │
  │   Story   │      │                │
  │ Composer  │      │                │
  │           │      │                │
  │ Arranges  │      │                │
  │ into      │      │                │
  │ narrative │      │                │
  └─────┬─────┘      │                │
        │            │                │
        └────────────┤                │
                     ▼                │
               ┌───────────┐          │
               │  Editing   │          │
               │  Agent     │          │
               │            │          │
               │ Builds     │          │
               │ Timeline   │          │
               │ DSL        │          │
               └─────┬─────┘          │
                     │                │
                     ▼                ▼
               ┌───────────┐   ┌───────────┐
               │ Captions  │   │   Music   │
               │ Agent     │   │   Agent   │
               │           │   │           │
               │ Maps text │   │ Beat      │
               │ to clips  │   │ detection │
               │ ASS file  │   │ Cut align │
               └─────┬─────┘   └─────┬─────┘
                     │               │
                     ▼               ▼
               dsl/timeline.json
               render/captions.ass
```

#### Highlight Scoring Formula

```
score = (motion_w    × motion_score)        # avg intensity in window
      + (audio_w     × peak_score)          # peak density in window
      + (visual_w    × visual_relevance)    # SigLIP prompt similarity
      + (speech_w    × speech_score)        # speech overlap ratio
      + (variety_w   × variety_score)       # shorter shots = higher
      + (face_w      × face_score)          # face detection confidence

Default weights: motion=0.25, audio=0.20, visual=0.20, speech=0.15, variety=0.10, face=0.10
(Weights are overridden by strategy for each video type)
```

#### Story Structures

```
HIGH ENERGY (sports/gaming/events):
┌──────┬─────────┬──────────┬─────────┬────────┐
│ Hook │  Build  │ Climax   │  Build  │ Finale │
│ 12%  │  20%    │  25%     │  25%    │  18%   │
│early │  mid    │  late    │  mid    │ latest │
└──────┴─────────┴──────────┴─────────┴────────┘

MEDIUM (vlogs):
┌──────────┬──────────────┬──────────┬────────────┐
│  Intro   │ Development  │   Peak   │ Resolution │
│  20%     │    30%       │   30%    │    20%     │
│  early   │    mid       │   late   │   latest   │
└──────────┴──────────────┴──────────┴────────────┘

LOW (podcasts/tutorials):
┌──────────┬──────────────────────────┬────────────┐
│  Intro   │          Body           │ Conclusion │
│  25%     │          50%            │    25%     │
│  early   │          mid            │   latest   │
└──────────┴──────────────────────────┴────────────┘

CHRONOLOGICAL (talking heads):
┌──────────────────────────────────────────────────┐
│                Content (100%)                     │
│           Best moments in time order              │
└──────────────────────────────────────────────────┘
```

### 6.9 DSL & Rendering

#### Timeline DSL Schema (`dsl/schema.py`)

The Timeline DSL is the **single source of truth** for rendering. Every agent builds toward it.

```json
{
  "version": "1.0",
  "format": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "aspect": "9:16"
  },
  "clips": [
    {
      "source": "video1.mp4",
      "start": 3.0,
      "end": 8.0,
      "speed": 1.0,
      "volume": 1.0,
      "transition_in": "crossfade",
      "transition_duration": 0.3,
      "zoom": 1.0,
      "filters": []
    },
    {
      "source": "video1.mp4",
      "start": 15.2,
      "end": 21.0,
      "speed": 1.0,
      "volume": 1.0,
      "transition_in": "fade",
      "transition_duration": 0.3,
      "zoom": 1.0,
      "filters": []
    }
  ],
  "captions": [
    {
      "start": 0.5,
      "end": 3.2,
      "text": "[Speaker A] And that's the thing about creativity...",
      "style": "default",
      "position": "bottom_center"
    }
  ],
  "music": {
    "source": "track.mp3",
    "volume": 0.3,
    "fade_in": 0.0,
    "fade_out": 2.0,
    "sync_beats": true
  }
}
```

#### FFmpeg Command Builder (`render/ffmpeg_builder.py`)

Transforms the Timeline DSL into an FFmpeg command. Handles:

- **Per-clip video chain**: trim → setpts → speed → zoom → filters → scale → pad
- **Per-clip audio chain**: atrim → asetpts → volume → tempo
- **Transitions**: xfade (crossfade, fade, flash) between consecutive clips
- **Subtitles**: ASS filter overlay from render/captions.ass
- **Music mixing**: amix for background music with volume/fade control
- **Output encoding**: libx264 CRF 22, AAC 128kbps, movflags +faststart

---

## 7. Frontend Deep Dive

### 7.1 Pages & Routing

```
/                    →  NewJobPage      (upload + prompt form)
/history             →  HistoryPage     (job list with filters)
/jobs/[jobId]        →  JobPage         (detail, progress, video player)
```

#### Page: New Edit (`/`)

```
┌──────────────────────────────────────────┐
│  New Edit                                │
│  Upload your clips and describe the edit │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  (1) Upload video files            │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │        DROPZONE              │  │  │
│  │  │   Drag & drop or click      │  │  │
│  │  │   [video1.mp4] [video2.mp4] │  │  │
│  │  └──────────────────────────────┘  │  │
│  │                                    │  │
│  │  (2) Describe your edit            │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │ Make a 30s TikTok highlight  │  │  │
│  │  │ reel with bold captions...   │  │  │
│  │  └──────────────────────────────┘  │  │
│  │  Try: [example 1] [example 2]      │  │
│  │                                    │  │
│  │  ┌──── Warning (if any) ────────┐  │  │
│  │  │ ⚠ Highlight reel may not     │  │  │
│  │  │   work well with podcast...  │  │  │
│  │  │ [Proceed Anyway] [Change]    │  │  │
│  │  └──────────────────────────────┘  │  │
│  │                                    │  │
│  │  [ ━━━━ Start Editing ━━━━━━ → ]   │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

**Flow**: Upload → Type prompt → Click submit → Analyze → (Show warnings?) → Create job → Navigate to detail page

#### Page: Job Detail (`/jobs/[jobId]`)

**While processing**:
```
┌──────────────────────────────────────────┐
│                                          │
│           ┌──────────┐                   │
│           │   42%    │  ProgressRing     │
│           │Analyzing │                   │
│           └──────────┘                   │
│                                          │
│  ━━━━━━━━━━━━━━━░░░░░░░░░░  42%         │
│                                          │
│  ● Preprocessing     ✓                   │
│  │                                       │
│  ● Intelligence      ◌ (spinning)        │
│  │                                       │
│  ○ Planning                              │
│  │                                       │
│  ○ Rendering                             │
│  │                                       │
│  ○ Done                                  │
└──────────────────────────────────────────┘
```

**When complete**:
```
┌──────────────────────────────────────────┐
│                                          │
│  ┌─────────────────────┐  ┌──────────┐  │
│  │                     │  │Thumbnail │  │
│  │   VIDEO PLAYER      │  │          │  │
│  │   ▶ 0:12 / 0:30    │  │          │  │
│  │   ━━━━━━━━░░░░░░░░ │  └──────────┘  │
│  └─────────────────────┘                 │
│                                          │
│  "Make a 30s TikTok highlight reel..."   │
│                                          │
│  ┌─────────────────────────────────────┐ │
│  │ Output     │ Input      │ Clips    │ │
│  │ 30.0s      │ 8m 0.0s   │ 12       │ │
│  │────────────┼────────────┼──────────│ │
│  │ Captions   │ Format     │ Compress │ │
│  │ 25         │ 9:16       │ 16x      │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  AI Explanation                          │
│  ┌─────────────────────────────────────┐ │
│  │ ● Classification                ▾  │ │
│  │   Classified as 'podcast' (82%)... │ │
│  │─────────────────────────────────── │ │
│  │ ● Strategy                      ▸  │ │
│  │ ● Planning                      ▸  │ │
│  │ ● Visual Scoring                ▸  │ │
│  │ ● Highlights                    ▸  │ │
│  │ ● Story                         ▸  │ │
│  │ ● Editing                       ▸  │ │
│  └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

#### Page: History (`/history`)

```
┌──────────────────────────────────────────┐
│  Job History                             │
│                                          │
│  [All] [Processing] [Completed] [Failed] │
│  ┌──────────────────────────────────────┐│
│  │ 🔍 Search by prompt or job ID...    ││
│  └──────────────────────────────────────┘│
│                                          │
│  ┌──────┬───────────────┬────────┬─────┐│
│  │Thumb │ Prompt        │ Status │ When││
│  ├──────┼───────────────┼────────┼─────┤│
│  │ ▓▓▓▓ │ Make a 30s... │✓ Done  │ 2m  ││
│  │ ▓▓▓▓ │ Clean up my...│◌ Proc  │ 5m  ││
│  │ ▓▓▓▓ │ Gaming mont...│✗ Fail  │ 1h  ││
│  └──────┴───────────────┴────────┴─────┘│
└──────────────────────────────────────────┘
```

#### Sidebar

```
┌───────────────────┐
│  ◆ Prompt Editor  │
│                   │
│ [+ New Edit     ] │
│                   │
│  Dashboard        │
│  Job History      │
│                   │
│  ── Recent ────── │
│  ┌───────────────┐│
│  │ abc-123       ││
│  │ Make a 30s... ││
│  │ ✓ Completed   ││
│  └───────────────┘│
│  ┌───────────────┐│
│  │ def-456       ││
│  │ Clean up...   ││
│  │ ◌ Processing  ││
│  └───────────────┘│
│                   │
│  Powered by       │
│  Groq + FFmpeg    │
└───────────────────┘
```

### 7.2 Component Library

#### UI Primitives (`components/ui/`)

| Component | Props | Purpose |
|-----------|-------|---------|
| `Button` | variant (primary/secondary/ghost/destructive), size (sm/md/lg), loading, leftIcon, rightIcon | Action buttons with loading spinner |
| `Card` | hoverable, noPadding | Surface container with border + shadow |
| `Badge` | variant, status | Status indicator with colored dot (pulses when processing) |
| `Spinner` | size (sm/md) | SVG circular spinner |
| `Input` | label, error, leftIcon | Text input with validation |
| `Textarea` | label, error, maxLength, maxHeight | Auto-growing textarea with char counter |
| `DropZone` | files, onFilesChange, accept, multiple | Drag-drop file upload with file chips |
| `ProgressBar` | value (0-1), active, label | Linear progress with shimmer animation |
| `ProgressRing` | value, size, strokeWidth, label, sublabel | Circular SVG progress with center text |

#### Job Components (`components/job/`)

| Component | Props | Purpose |
|-----------|-------|---------|
| `VideoPlayer` | jobId, captionsUrl | Full custom HTML5 player with keyboard shortcuts |
| `StageTimeline` | status | Visual pipeline stage indicator (dots + connectors) |
| `StatGrid` | stats | 2-column grid showing output stats |
| `ExplanationAccordion` | decisions, defaultOpenIndex | Collapsible list of AI editing decisions |
| `PromptDisplay` | prompt | Styled quote block for the user prompt |
| `JobCard` | job, compact | Preview card for job list/sidebar |

### 7.3 API Client & Hooks

#### API Client (`lib/api.ts`)

Typed fetch wrappers with automatic error handling:

```typescript
// Base URL from environment or localhost:8000
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// All functions throw Error with backend detail message on failure
listJobs()                    → GET  /jobs/
getJob(jobId)                 → GET  /jobs/{id}
createJob(prompt, files)      → POST /jobs/          (FormData)
getTimeline(jobId)            → GET  /jobs/{id}/timeline
getExplanation(jobId)         → GET  /jobs/{id}/explanation
analyzeContent(prompt, files) → POST /jobs/analyze    (FormData)
getVideoUrl(jobId)            → string (direct URL)
getThumbnailUrl(jobId)        → string (direct URL)
```

#### Hooks

**`useJob(jobId)`** — Polls a single job every 1.5 seconds until it reaches a terminal state (completed/failed). Returns `{ job, loading, error, refetch }`.

**`useJobs(autoRefresh?)`** — Fetches all jobs, sorted newest first. Optional 5-second auto-refresh. Returns `{ jobs, loading, error, refetch }`.

### 7.4 Design System

**Color scheme**: Dark-mode first with electric indigo accent (`#7c6aff`)

```
Background layers:
  --background:   #0a0a0f    (darkest)
  --surface-1:    #141419    (cards)
  --surface-2:    #1c1c23    (elevated)
  --surface-3:    #24242c    (inputs)
  --surface-4:    #2c2c35    (hover)

Text hierarchy:
  --text-primary:   #f0f0f5  (headings, important)
  --text-secondary: #a0a0b0  (body text)
  --text-tertiary:  #606070  (labels, hints)

Accent:
  --accent:         #7c6aff  (electric indigo)
  --accent-hover:   #8f7fff
  --accent-glow:    rgba(124,106,255,0.25)

Status:
  --status-created:    #7c6aff  (indigo)
  --status-processing: #f59e0b  (amber)
  --status-success:    #10b981  (emerald)
  --status-error:      #ef4444  (red)
```

**Typography**: Inter (sans), JetBrains Mono (code)

**Motion**: 120ms fast, 200ms base, 350ms slow. Custom easing curves.

**Animations**: pulse-dot, shimmer, fade-in, slide-up, slide-in-left, spin

---

## 8. AI Models & Libraries

### Models Used

| Model | Purpose | Size | Source | Auto-Download |
|-------|---------|------|--------|---------------|
| **Whisper "small"** | Speech-to-text transcription | ~461 MB | OpenAI (torch hub) | Yes, on first transcription |
| **SigLIP ViT-B/16** | Visual classification + prompt relevance | ~400 MB | HuggingFace (via open_clip) | Yes, on first visual scoring |
| **Blaze Face** | Face detection | ~1 MB | Google (MediaPipe) | Yes, on first face detection |

### Library → Purpose Map

| Library | Used By | Purpose |
|---------|---------|---------|
| `openai-whisper` | transcribe.py | Speech recognition with word timestamps |
| `open-clip-torch` | visual_scoring.py | SigLIP model loading and inference |
| `transformers` | visual_scoring.py | SigLIP tokenizer (HFTokenizer) |
| `torch` + `torchvision` | whisper, open_clip | PyTorch runtime for model inference |
| `opencv-python` | motion.py, faces.py, thumbnail.py | Frame extraction, differencing, image processing |
| `mediapipe` | faces.py | Blaze Face detection |
| `librosa` | audio_features.py, music.py | RMS energy, peak detection, beat tracking |
| `scipy` | audio_features.py | Signal processing |
| `scikit-learn` | diarization.py | AgglomerativeClustering for speaker grouping |
| `scenedetect` | shots.py | ContentDetector for scene boundaries |
| `Pillow` | thumbnail.py, visual_scoring.py | Image manipulation, text overlay |
| `ffmpeg-python` | (legacy) | FFmpeg wrapper (being replaced by direct subprocess) |
| `pydantic` | schema.py, config.py, jobs_db.py | Data validation and serialization |
| `requests` | llm_planner.py | HTTP calls to Groq API |

---

## 9. Configuration Reference

All backend settings use the `PDVE_` environment variable prefix (via pydantic-settings).

### Backend Settings (`core/config.py`)

| Setting | Env Var | Default | Purpose |
|---------|---------|---------|---------|
| `storage_base` | `PDVE_STORAGE_BASE` | `storage/jobs` | Root directory for job artifacts |
| `ffmpeg_path` | `PDVE_FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |
| `ffprobe_path` | `PDVE_FFPROBE_PATH` | `ffprobe` | Path to FFprobe binary |
| `whisper_model` | `PDVE_WHISPER_MODEL` | `small` | Whisper model size (tiny/base/small/medium/large) |
| `proxy_resolution` | `PDVE_PROXY_RESOLUTION` | `854` | Proxy video width in pixels |
| `proxy_crf` | `PDVE_PROXY_CRF` | `28` | Proxy video quality (lower = better) |
| `audio_sample_rate` | `PDVE_AUDIO_SAMPLE_RATE` | `16000` | Audio extraction sample rate |
| `default_fps` | `PDVE_DEFAULT_FPS` | `30` | Output video frame rate |
| `default_width` | `PDVE_DEFAULT_WIDTH` | `1920` | Default output width |
| `default_height` | `PDVE_DEFAULT_HEIGHT` | `1080` | Default output height |
| `default_aspect` | `PDVE_DEFAULT_ASPECT` | `16:9` | Default aspect ratio |
| `silence_threshold_db` | `PDVE_SILENCE_THRESHOLD_DB` | `-40.0` | Silence detection threshold |
| `silence_min_duration` | `PDVE_SILENCE_MIN_DURATION` | `0.3` | Minimum silence duration (seconds) |
| `diarization_enabled` | `PDVE_DIARIZATION_ENABLED` | `True` | Enable speaker diarization |
| `diarization_max_speakers` | `PDVE_DIARIZATION_MAX_SPEAKERS` | `6` | Maximum speakers to detect |
| `llm_api_key` | `PDVE_LLM_API_KEY` | `""` | Groq API key |
| `llm_model` | `PDVE_LLM_MODEL` | `openai/gpt-oss-120b` | LLM model identifier |
| `llm_planner_enabled` | `PDVE_LLM_PLANNER_ENABLED` | `True` | Use LLM for planning |
| `visual_model` | `PDVE_VISUAL_MODEL` | `ViT-B-16-SigLIP` | SigLIP model name |
| `visual_pretrained` | `PDVE_VISUAL_PRETRAINED` | `webli` | SigLIP pretrained weights |
| `visual_sample_fps` | `PDVE_VISUAL_SAMPLE_FPS` | `1.0` | Keyframes per second for scoring |
| `visual_scoring_enabled` | `PDVE_VISUAL_SCORING_ENABLED` | `True` | Enable visual scoring |
| `log_level` | `PDVE_LOG_LEVEL` | `INFO` | Logging level |

### Frontend Settings

| Setting | File | Default | Purpose |
|---------|------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `.env.local` | `http://localhost:8000` | Backend API base URL |

---

## 10. How Components Connect

### Signal Dependencies Between Modules

```
media_manifest ──────────────────────┐
       │                             │
       ├──→ transcribe ──→ transcript │
       │         │                   │
       │         ├──→ diarize ──→ diarization
       │         │                   │
       │         └───────────────────┤
       │                             │
       ├──→ detect_silence ──→ silence
       │                             │
       ├──→ compute_energy ──→ audio_energy
       │                             │
       ├──→ detect_shots ──→ shots ──┤
       │                        │    │
       │                        │    │
       ├──→ detect_motion ──→ motion │
       │                             │
       ├──→ detect_faces ──→ faces   │
       │                             │
       ├──→ analyze_music ──→ music_analysis (if audio files)
       │                             │
       └──→ compute_visual_scores ──→ visual_scores
              (uses shots + prompt)  │
                                     │
                ALL SIGNALS          │
                     │               │
                     ▼               │
              classify_content ──→ classification
                     │               │
                     ▼               │
              get_strategy ──→ strategy (in-memory)
                     │               │
                     ▼               │
              plan_edit ──→ plan.json │
                     │               │
                     ▼               │
              select_highlights ──→ highlights.json
              (uses: plan, motion,   │
               energy, silence,      │
               faces, visual_scores) │
                     │               │
                     ▼               │
              compose_story ──→ story.json
              (uses: plan, highlights)
                     │               │
                     ▼               │
              build_timeline ──→ Timeline DSL
              (uses: plan, story/highlights/silence,
               music_analysis for beat sync)
                     │               │
                     ▼               │
              generate_captions ──→ captions in Timeline
              (uses: timeline, transcript, diarization)
                     │
                     ▼
              generate_ass_file ──→ render/captions.ass
                     │
                     ▼
              save_dsl ──→ dsl/timeline.json
                     │
                     ▼
              render_timeline ──→ outputs/final.mp4
              (FFmpegCommandBuilder reads timeline.json)
                     │
                     ▼
              generate_thumbnail ──→ outputs/thumbnail.png
              (uses: motion, faces, energy)
                     │
                     ▼
              generate_explanation ──→ outputs/explanation.json
              (reads all signals, plans, and timeline)
```

### Frontend ↔ Backend Communication

```
Frontend                              Backend
━━━━━━━━                              ━━━━━━━

page.tsx                              routes_jobs.py
  │                                     │
  ├─ analyzeContent() ──POST /analyze──→ classify + strategy
  │   ← AnalysisResult ────────────────┤
  │                                     │
  ├─ createJob() ──────POST /jobs/ ───→ save files, start pipeline
  │   ← {job_id} ─────────────────────┤
  │                                     │
  │  navigate to /jobs/[id]             │
  │                                     │
  ▼                                     │
jobs/[id]/page.tsx                      │
  │                                     │
  ├─ useJob() ─────── GET /jobs/{id} ──→ JobRecord (status, progress)
  │   polls every 1.5s until done       │
  │                                     │
  │  When completed:                    │
  ├─ getExplanation() GET /explain ────→ explanation.json
  ├─ getVideoUrl() ── GET /download ───→ final.mp4 (FileResponse)
  └─ getThumbnailUrl() GET /thumbnail ─→ thumbnail.png (FileResponse)
                                        │
history/page.tsx                        │
  │                                     │
  └─ useJobs() ─────── GET /jobs/ ────→ JobRecord[] (all jobs)
       auto-refresh every 5s            │
                                        │
Sidebar.tsx                             │
  │                                     │
  └─ useJobs() ─────── GET /jobs/ ────→ 5 most recent jobs
       auto-refresh                     │
```

---

## Quick Reference: Running the Project

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
# Set environment variables in .env:
#   PDVE_LLM_API_KEY=gsk_your_groq_key
#   PDVE_LLM_MODEL=openai/gpt-oss-120b
uvicorn app.main:app --reload

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev

# 3. Prerequisites
# - FFmpeg must be on PATH
# - Python 3.11+
# - Node.js 18+
# - GPU optional (CUDA for faster Whisper/SigLIP, CPU works fine)

# 4. First run
# Models download automatically on first job:
#   Whisper "small" (~461 MB)
#   SigLIP ViT-B/16 (~400 MB)
#   MediaPipe Blaze Face (~1 MB)
```

---

*This guide was generated from the complete source code of the PromptDrivenVideoEditor project.*
