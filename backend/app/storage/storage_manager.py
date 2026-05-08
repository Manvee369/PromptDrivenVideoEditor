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

# Sidecar file inside raw/ holding the {filename: role} map. Hidden-style
# leading underscore so it sorts to the top of directory listings and is
# easy to skip when iterating raw media.
ROLES_FILENAME = "_roles.json"


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
        if not raw.exists():
            return []
        # Skip the roles sidecar — it's metadata, not media.
        return sorted(p for p in raw.iterdir() if p.name != ROLES_FILENAME)

    def raw_video_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in VIDEO_EXTENSIONS]

    def raw_audio_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in AUDIO_EXTENSIONS]

    def raw_image_files(self) -> list[Path]:
        return [f for f in self.raw_files() if f.suffix.lower() in IMAGE_EXTENSIONS]

    # --- Role metadata for raw files ---
    # The /jobs/ POST endpoint accepts separate `music_files[]` and
    # `voiceover_files[]` form fields so users can mark intent at upload time.
    # We persist that mapping to raw/_roles.json so downstream agents can pick
    # the right audio for music vs voiceover slots without guessing.

    def _roles_path(self) -> Path:
        return self.stage_dir("raw") / ROLES_FILENAME

    def save_roles(self, roles: dict[str, str]) -> None:
        """Persist a {filename: role} map to raw/_roles.json. Roles are
        free-form strings; recognized values: 'video', 'music', 'voiceover',
        'image'. Unmapped files default to inferred-from-extension."""
        self.stage_dir("raw").mkdir(parents=True, exist_ok=True)
        self._roles_path().write_text(
            json.dumps(roles, indent=2), encoding="utf-8",
        )

    def load_roles(self) -> dict[str, str]:
        """Return persisted role map, or {} if none was saved."""
        path = self._roles_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def role_of(self, filename: str) -> str:
        """Resolve the role for a raw filename. Falls back to extension-inferred
        defaults: video extensions → 'video', audio → 'music', image → 'image'."""
        roles = self.load_roles()
        if filename in roles:
            return roles[filename]
        ext = Path(filename).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            return "video"
        if ext in AUDIO_EXTENSIONS:
            return "music"
        if ext in IMAGE_EXTENSIONS:
            return "image"
        return "unknown"

    def raw_files_by_role(self, role: str) -> list[Path]:
        """All raw files tagged with the given role."""
        return [f for f in self.raw_files() if self.role_of(f.name) == role]

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
