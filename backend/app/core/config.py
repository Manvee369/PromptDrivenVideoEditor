"""Application configuration via environment variables with PDVE_ prefix."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage
    storage_base: str = "storage/jobs"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    # Whisper
    whisper_model: str = "base"

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

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": "PDVE_"}


settings = Settings()
