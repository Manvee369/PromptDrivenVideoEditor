"""Manages the stage-based directory layout for a job."""

import json
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

STAGES = ["raw", "prep", "signals", "plans", "dsl", "render", "outputs"]


class StorageManager:
    """File I/O abstraction for a single job's stage-based directory tree."""

    def __init__(self, job_id: str, base_path: str | None = None):
        self.job_id = job_id
        self._base = Path(base_path or settings.storage_base)

    # --- Directory helpers ---

    def job_dir(self) -> Path:
        return self._base / self.job_id

    def stage_dir(self, stage: str) -> Path:
        if stage not in STAGES:
            raise ValueError(f"Unknown stage: {stage}")
        return self.job_dir() / stage

    def ensure_dirs(self) -> None:
        """Create all stage directories."""
        for stage in STAGES:
            self.stage_dir(stage).mkdir(parents=True, exist_ok=True)
        log.info("Created job directories for %s", self.job_id)

    # --- File listing ---

    def raw_files(self) -> list[Path]:
        raw = self.stage_dir("raw")
        return sorted(raw.iterdir()) if raw.exists() else []

    def raw_video_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in VIDEO_EXTENSIONS]

    def raw_audio_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in AUDIO_EXTENSIONS]

    def raw_image_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in IMAGE_EXTENSIONS]

    # --- JSON I/O ---

    def _json_path(self, stage: str, name: str) -> Path:
        return self.stage_dir(stage) / f"{name}.json"

    def save_json(self, stage: str, name: str, data: dict | list) -> Path:
        path = self._json_path(stage, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        log.debug("Saved %s/%s.json", stage, name)
        return path

    def load_json(self, stage: str, name: str) -> dict | list:
        path = self._json_path(stage, name)
        return json.loads(path.read_text(encoding="utf-8"))

    def has_json(self, stage: str, name: str) -> bool:
        return self._json_path(stage, name).exists()

    # --- Convenience shortcuts ---

    def save_signal(self, name: str, data: dict | list) -> Path:
        return self.save_json("signals", name, data)

    def load_signal(self, name: str) -> dict | list:
        return self.load_json("signals", name)

    def save_plan(self, name: str, data: dict) -> Path:
        return self.save_json("plans", name, data)

    def load_plan(self, name: str) -> dict:
        return self.load_json("plans", name)

    def save_dsl(self, data: dict) -> Path:
        return self.save_json("dsl", "timeline", data)

    def load_dsl(self) -> dict:
        return self.load_json("dsl", "timeline")

    def output_path(self, filename: str) -> Path:
        return self.stage_dir("outputs") / filename

    def prep_path(self, filename: str) -> Path:
        return self.stage_dir("prep") / filename

    def render_path(self, filename: str) -> Path:
        return self.stage_dir("render") / filename
