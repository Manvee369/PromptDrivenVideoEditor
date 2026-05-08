"""Application configuration via environment variables with PDVE_ prefix."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage
    storage_base: str = "storage/jobs"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    # Whisper
    # Default upgraded from "small" → "medium" for noticeably better
    # transcription on accented/noisy speech. ~3x slower on CPU but
    # caption text quality is the most user-visible AI output. Override
    # via PDVE_WHISPER_MODEL=small to revert.
    whisper_model: str = "medium"
    # When True, run WhisperX wav2vec2 forced alignment on top of
    # faster-whisper's output for tighter word-level timing. Falls back to
    # faster-whisper's word_timestamps if WhisperX import or alignment fails.
    use_whisperx_alignment: bool = True

    # Preprocessing
    proxy_resolution: int = 854
    proxy_crf: int = 28
    audio_sample_rate: int = 16000

    # Rendering defaults
    default_fps: int = 30
    default_width: int = 1920
    default_height: int = 1080
    default_aspect: str = "16:9"

    # Silence detection
    silence_threshold_db: float = -40.0
    silence_min_duration: float = 0.3

    # Diarization
    diarization_enabled: bool = True
    diarization_max_speakers: int = 6

    # LLM Planner (Groq)
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    llm_planner_enabled: bool = True

    # Visual scoring (SigLIP)
    visual_model: str = "ViT-B-16-SigLIP"
    visual_pretrained: str = "webli"
    visual_sample_fps: float = 1.0  # keyframes per second for scoring
    visual_scoring_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    # --- Ingress hardening (Phase 2) ---

    # Comma-separated CORS origin allowlist. "*" disables the allowlist
    # (development only — never use in production).
    allowed_origins_csv: str = "http://localhost:3000"

    # Per-file upload size cap. Default 2 GB. Files larger than this are
    # rejected mid-stream so we never buffer a giant upload in memory.
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024

    # Per-request file count cap.
    max_files_per_job: int = 20

    # Streaming-read chunk size when saving uploads.
    upload_chunk_size: int = 1024 * 1024  # 1 MB

    # If True, /jobs/{id}/download and /jobs/{id}/thumbnail require a
    # ?token=... query param matching the job's download_token. The token
    # is returned at job creation. Set False for local dev convenience.
    download_token_required: bool = True

    # --- Audio output ---
    # EBU R128 loudness normalization on final render. -14 LUFS is the
    # de-facto target for streaming/social platforms. Set to 0 to disable.
    loudnorm_target_lufs: float = -14.0
    loudnorm_target_lra: float = 11.0          # loudness range
    loudnorm_target_tp: float = -1.5           # true peak ceiling

    # Tiny audio crossfade applied at every clip boundary so cuts don't click.
    # 50ms is inaudible as a fade but smooths waveform discontinuities.
    audio_cut_smooth_seconds: float = 0.05

    # --- Job queue (RQ + Redis) ---
    # When queue_enabled and Redis is reachable, /jobs/ enqueues to RQ and a
    # separate worker process runs the pipeline. Otherwise we fall back to
    # FastAPI BackgroundTasks (in-process, single-job-at-a-time).
    queue_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "pipeline"
    # Per-job worker timeout (10 min default). Long renders may need a higher value.
    queue_job_timeout: int = 600

    # --- Azure AI Speech (transcription) ---
    # When set, the transcription stage uses Azure AI Speech instead of
    # faster-whisper. Real-time speed, no GPU needed. Free tier: 5 hrs/month.
    # Get a key at: https://portal.azure.com → Azure AI Services → Speech
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"

    # --- Azure Blob Storage ---
    # When PDVE_STORAGE_BACKEND=azure, job artifacts are stored in Azure Blob
    # Storage instead of the local filesystem. Required for multi-instance
    # deployments and Container Apps (ephemeral local disks).
    # Get a connection string at: Azure Portal → Storage Accounts → Access keys
    storage_backend: str = "local"          # "local" | "azure"
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "pdve-jobs"

    # --- Disk janitor ---
    # Periodically remove intermediate artifacts (prep/, render/, signals/)
    # for completed jobs aged past the threshold. Safe — does not delete the
    # raw uploads, the DSL, or the final outputs. Re-running the pipeline
    # regenerates everything cleanly.
    janitor_enabled: bool = True
    janitor_max_age_hours: int = 24       # clean jobs older than this when COMPLETED
    janitor_interval_minutes: int = 60    # sweep cadence

    @property
    def allowed_origins(self) -> list[str]:
        """Parse CSV into a list. Empty entries dropped."""
        return [o.strip() for o in self.allowed_origins_csv.split(",") if o.strip()]

    model_config = {"env_prefix": "PDVE_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
