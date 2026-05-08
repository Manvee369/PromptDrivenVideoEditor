"""Transcription intelligence using faster-whisper, optionally enhanced with
WhisperX wav2vec2 forced alignment.

Two-stage flow:
    1. faster-whisper transcribes audio → segments with text + word timestamps.
       At compute_type="float32" the numerical output is identical to
       openai-whisper while running ~2-4x faster on CPU.
    2. (optional) WhisperX runs wav2vec2 forced alignment on the segments,
       producing tighter word boundaries (the difference is most visible in
       karaoke-style captions). If WhisperX isn't installed or alignment
       fails, we silently keep faster-whisper's word timestamps.
"""

from __future__ import annotations

from typing import Any

from faster_whisper import WhisperModel

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Lazy-loaded singletons. WhisperX modules are imported on first use so a
# missing/unhappy install never blocks app startup.
_model: WhisperModel | None = None
_align_model: Any = None
_align_metadata: Any = None
_align_lang_code: str | None = None
_whisperx_available: bool | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        log.info(
            "Loading faster-whisper model: %s (cpu, float32)",
            settings.whisper_model,
        )
        _model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="float32",
        )
    return _model


def _try_import_whisperx() -> bool:
    """Probe for WhisperX once. Cached result. Returns True if available."""
    global _whisperx_available
    if _whisperx_available is not None:
        return _whisperx_available
    try:
        import whisperx  # noqa: F401
        _whisperx_available = True
        log.info("WhisperX available — word-level alignment enabled")
    except Exception as e:
        _whisperx_available = False
        log.info("WhisperX not available (%s) — using faster-whisper timestamps", e)
    return _whisperx_available


def _get_align_model(language_code: str):
    """Lazy-load the wav2vec2 alignment model. Re-loads if the language
    changes (each language uses a different aligner)."""
    global _align_model, _align_metadata, _align_lang_code
    if _align_model is not None and _align_lang_code == language_code:
        return _align_model, _align_metadata
    import whisperx
    log.info("Loading WhisperX alignment model for language=%s", language_code)
    _align_model, _align_metadata = whisperx.load_align_model(
        language_code=language_code, device="cpu",
    )
    _align_lang_code = language_code
    return _align_model, _align_metadata


def transcribe_media(storage: StorageManager) -> dict:
    """Transcribe each audio file from prep/, with optional WhisperX alignment.

    Output saved to signals/transcript.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "language": "en",
          "alignment": "whisperx" | "faster_whisper",
          "segments": [
            {
              "start": 0.0, "end": 2.5, "text": "Hello world",
              "words": [
                {"start": 0.0, "end": 0.4, "text": "Hello", "probability": 0.97},
                ...
              ]
            }
          ],
          "full_text": "Hello world ..."
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    model = _get_model()
    use_alignment = settings.use_whisperx_alignment and _try_import_whisperx()
    tracks = []

    for file_info in manifest["files"]:
        audio_path = file_info["audio_path"]
        if not audio_path:
            continue

        log.info("Transcribing: %s", file_info["filename"])
        segments_iter, info = model.transcribe(
            audio_path,
            word_timestamps=True,
        )

        # Materialize segments first — the generator runs inference lazily,
        # and we'll feed them to WhisperX next if alignment is on.
        raw_segments = []
        for seg in segments_iter:
            raw_segments.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "words": [
                    {
                        "start": float(w.start),
                        "end": float(w.end),
                        "word": w.word.strip(),
                        "probability": float(w.probability),
                    }
                    for w in (seg.words or [])
                ],
            })

        language = info.language or "en"
        alignment_used = "faster_whisper"

        if use_alignment and raw_segments:
            try:
                raw_segments = _align_with_whisperx(
                    raw_segments, audio_path, language,
                )
                alignment_used = "whisperx"
            except Exception as e:
                log.warning(
                    "WhisperX alignment failed for %s: %s — keeping faster-whisper timestamps",
                    file_info["filename"], e,
                )

        # Normalize to our schema (text/probability keys)
        segments_out = []
        for seg in raw_segments:
            words_out = []
            for w in seg.get("words", []) or []:
                words_out.append({
                    "start": round(float(w.get("start", 0.0)), 3),
                    "end": round(float(w.get("end", 0.0)), 3),
                    "text": str(w.get("word") or w.get("text") or "").strip(),
                    "probability": round(float(w.get("probability", w.get("score", 0.0))), 3),
                })
            segments_out.append({
                "start": round(float(seg["start"]), 3),
                "end": round(float(seg["end"]), 3),
                "text": str(seg["text"]).strip(),
                "words": words_out,
            })

        full_text = " ".join(s["text"] for s in segments_out).strip()

        tracks.append({
            "source": file_info["filename"],
            "language": language,
            "alignment": alignment_used,
            "segments": segments_out,
            "full_text": full_text,
        })

    transcript = {"tracks": tracks}
    storage.save_signal("transcript", transcript)
    log.info("Transcription complete: %d tracks", len(tracks))
    return transcript


def _align_with_whisperx(
    segments: list[dict], audio_path: str, language: str,
) -> list[dict]:
    """Run WhisperX wav2vec2 forced alignment on faster-whisper segments.

    Returns the aligned segment list (same shape, tighter word timings).
    Raises on any failure so the caller can fall back gracefully.
    """
    import whisperx

    align_model, metadata = _get_align_model(language)
    aligned = whisperx.align(
        segments,
        align_model,
        metadata,
        audio_path,
        device="cpu",
        return_char_alignments=False,
    )
    # WhisperX returns {"segments": [...], "word_segments": [...]}
    return aligned.get("segments", segments)
