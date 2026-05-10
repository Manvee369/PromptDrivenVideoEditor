# Kairo: Prompt-Driven Video Editor

Kairo is an autonomous, multi-agent video editing platform that translates natural language prompts into polished, production-ready video content. 

Instead of treating video editing as a monolithic, black-box AI generation problem, Kairo decomposes the editing process into a deterministic pipeline. It uses specialized AI agents to extract multimodal signals, reason about narrative structure, and compile a declarative "Timeline DSL" that ultimately drives a highly optimized FFmpeg rendering engine.

## The Tech Stack

**Core Infrastructure**
* **Backend:** FastAPI (Python), orchestrated asynchronously.
* **Task Queue:** RQ (Redis Queue) + Redis for background job management.
* **Frontend:** Next.js 14 (App Router), React, Tailwind CSS. Features Server-Sent Events (SSE) for real-time pipeline telemetry.
* **Deployment:** Docker & Docker Compose, fully containerized for CPU/GPU Azure VMs.

**Intelligence & Machine Learning**
* **LLM Reasoning:** Groq API running **Llama 3.3** for ultra-low latency narrative planning and decision-making.
* **Visual Understanding:** **SigLIP** (ViT-B-16) for zero-shot frame scoring and semantic prompt matching.
* **Computer Vision:** **MediaPipe** (Face detection/tracking for smart cropping), **OpenCV** (Dense optical flow for motion intensity scoring).
* **Audio & Speech:** **Azure AI Speech / WhisperX** for highly accurate, word-level timestamped transcription and diarization. **Librosa** for beat tracking, RMS loudness spikes, and silence detection.
* **Video Rendering:** **FFmpeg** (via complex, dynamically generated filtergraphs).

---

## How It Actually Works (The Pipeline)

Kairo doesn't just pass video to a single AI model. It runs a rigorous 6-stage pipeline to ensure the final output is structurally sound and mathematically precise.

### Stage 1: Preprocessing
Raw media comes in all shapes and sizes. Before any AI touches the file, Kairo normalizes it. It extracts a pristine `16kHz WAV` audio track and encodes a lightweight, low-resolution `H.264 proxy video`. This ensures the heavy computer vision models don't blow up the RAM trying to process 4K footage.

### Stage 2: Intelligence Extraction (The "Signals")
We extract raw data from the media and store it as pure, decoupled JSON files in a `signals/` directory. No agent touches the video file directly.
* **Transcript:** Azure AI/Whisper generates word-level timestamps.
* **Faces:** MediaPipe tracks bounding boxes across time.
* **Motion & Shots:** OpenCV calculates motion intensity per frame; PySceneDetect logs hard cuts.
* **Audio:** Librosa finds the rhythmic grid (beats) and detects dead air (silence).
* **Visual Scores:** SigLIP compares frames against the user's prompt to find the most semantically relevant moments.

### Stage 3: Multi-Agent Planning
This is the brain. We use a chain of Llama 3.3 agents via the Groq API:
1. **Content Classifier:** Is this a podcast? Gameplay? A vlog?
2. **Strategy Router:** Maps the content type to an editorial blueprint (e.g., Podcasts get silence removal and face-tracking; Gameplay gets heavy motion weighting and jump cuts).
3. **Planner:** Reads the prompt and the signals, then outputs a high-level narrative plan (e.g., "Hook -> Build -> Climax").
4. **Highlight & Story Agents:** Math meets narrative. These agents scan the signals to find clips that satisfy the Planner's requested structure, scoring segments based on visual relevance, motion, and audio energy.

### Stage 4: The Timeline DSL
The agents don't write video files; they write a **Timeline DSL (Domain-Specific Language)**. This is a strict JSON schema representing the edit: clip start/end times, crop boxes, transition types, audio fades, and subtitle arrays. 
*Why do this?* It completely decouples the unpredictable nature of LLMs from the rigid mathematics of video rendering.

### Stage 5: The Rendering Engine
The `ffmpeg_builder.py` script parses the Timeline DSL and compiles it into a massive, highly optimized FFmpeg command. 
It handles:
* Complex `xfade` visual transitions.
* Frame-accurate audio mixing using `amix` and `adelay` to prevent crossfade deadlocks.
* Dynamic `crop` filter generation based on MediaPipe face-tracking data to punch-in on vertical (9:16) formats.
* `libass` rendering for animated, TikTok-style karaoke captions based on Whisper's word timestamps.
* EBU R128 loudness normalization.

---

## Data Flow Architecture

```text
Upload -> [Raw Media] 
             |
             v
      [Preprocessing] -> Proxy Video & Audio
             |
             v
    [Signal Extraction] -> (Whisper, SigLIP, OpenCV, Librosa)
             |
             v
       [JSON Signals] -> (transcript.json, faces.json, motion.json...)
             |
             v
    [AI Agent Router] -> Groq API (Llama 3.3) analyzes signals + prompt
             |
             v
      [Timeline DSL]  -> Abstract JSON representation of the edit
             |
             v
    [FFmpeg Builder]  -> Compiles filtergraph
             |
             v
      [Final Render]  -> final.mp4
```

## Running Locally

Kairo is built to run via Docker Compose.

1. Clone the repo.
2. Copy `.env.example` to `.env.production` and fill in your keys (Groq API, Azure Speech).
3. Build and spin up the stack:
   ```bash
   docker compose --env-file .env.production up --build -d
   ```
4. Access the UI at `http://localhost:3000` (or port 80 if running behind the Nginx proxy).

## Resilience & Graceful Degradation
Kairo is designed for production environments. If the Groq API fails or rate-limits, the system falls back to a deterministic, rule-based planner that uses math (motion peaks and audio loudness) to edit the video without LLM intervention. If a specific signal extraction fails (e.g., no faces detected), the downstream agents simply ignore that signal and proceed with the next best available data.