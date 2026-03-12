"""Transcription intelligence using OpenAI Whisper."""

import whisper

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Lazy-loaded model singleton
_model = None


def _get_model():
    global _model
    if _model is None:
        log.info("Loading Whisper model: %s", settings.whisper_model)
        _model = whisper.load_model(settings.whisper_model)
    return _model


def transcribe_media(storage: StorageManager) -> dict:
    """
    Transcribe each audio file from prep/ using Whisper.

    Output saved to signals/transcript.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "language": "en",
          "segments": [
            {"start": 0.0, "end": 2.5, "text": "Hello world"}
          ],
          "full_text": "Hello world ..."
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    model = _get_model()
    tracks = []

    for file_info in manifest["files"]:
        audio_path = file_info["audio_path"]
        if not audio_path:
            continue

        log.info("Transcribing: %s", file_info["filename"])
        result = model.transcribe(audio_path, fp16=False)

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": round(seg["start"], 3),
                "end": round(seg["end"], 3),
                "text": seg["text"].strip(),
            })

        tracks.append({
            "source": file_info["filename"],
            "language": result.get("language", "en"),
            "segments": segments,
            "full_text": result.get("text", "").strip(),
        })

    transcript = {"tracks": tracks}
    storage.save_signal("transcript", transcript)
    log.info("Transcription complete: %d tracks", len(tracks))
    return transcript
