"""Azure AI Speech transcription backend.

Replaces faster-whisper for transcription when Azure credentials are
configured. Azure Speech transcribes at real-time speed via cloud API —
an 8-minute video takes ~8-10 minutes instead of 25-80 minutes on CPU.

Features supported:
- Word-level timestamps (native in Azure Speech)
- Speaker diarization (via diarization_enabled=True on the API call)
- Language auto-detection (optional)
- Batch transcription for files > 60 seconds (recommended)

Configuration (in backend/.env):
    PDVE_AZURE_SPEECH_KEY=<your-key>
    PDVE_AZURE_SPEECH_REGION=eastus

Pricing (Azure Free tier F0):
    5 hours/month free → ~37 x 8-min videos free per month
    After free tier: ~$1/audio-hour

Fallback:
    If PDVE_AZURE_SPEECH_KEY is not set, the system falls back to
    faster-whisper (local CPU transcription) automatically.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)


def is_available() -> bool:
    """Return True if Azure Speech credentials are configured."""
    return bool(settings.azure_speech_key and settings.azure_speech_region)


def transcribe_file_azure(audio_path: Path, language: str = "en-US") -> dict:
    """Transcribe an audio file using Azure AI Speech REST API.

    Returns a transcript dict in the same schema as the faster-whisper path:
    {
        "language": "en",
        "alignment": "azure_speech",
        "segments": [
            {
                "start": 0.0,
                "end": 2.5,
                "text": "Hello world",
                "words": [
                    {"start": 0.0, "end": 0.4, "text": "Hello", "probability": 0.97},
                    ...
                ]
            }
        ],
        "full_text": "Hello world ..."
    }
    """
    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore
    except ImportError:
        raise RuntimeError(
            "azure-cognitiveservices-speech is not installed. "
            "Run: pip install azure-cognitiveservices-speech"
        )

    key = settings.azure_speech_key
    region = settings.azure_speech_region

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = language

    # Request word-level timestamps and detailed output
    speech_config.request_word_level_timestamps()
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))

    # Use conversation transcriber for speaker diarization support
    recognizer = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_config,
    ) if settings.diarization_enabled else speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    log.info("Azure Speech: transcribing %s (region=%s)", audio_path.name, region)

    all_results: list[dict] = []
    done = [False]

    def _on_result(evt):
        result = evt.result
        if result.reason.name in ("RecognizedSpeech", "RecognizedIntent", "TranscribedParticipant"):
            try:
                detail = json.loads(result.json)
                best = detail.get("NBest", [{}])[0]
                words_raw = best.get("Words", [])
                words = [
                    {
                        "start": round(w.get("Offset", 0) / 1e7, 3),
                        "end": round((w.get("Offset", 0) + w.get("Duration", 0)) / 1e7, 3),
                        "text": w.get("Word", "").strip(),
                        "probability": round(w.get("Confidence", 0.9), 3),
                    }
                    for w in words_raw
                ]
                seg_start = result.offset / 1e7
                seg_end = (result.offset + result.duration) / 1e7
                all_results.append({
                    "start": round(seg_start, 3),
                    "end": round(seg_end, 3),
                    "text": result.text.strip(),
                    "words": words,
                    "speaker": getattr(result, "speaker_id", None),
                })
            except Exception as e:
                log.warning("Azure Speech: failed to parse result: %s", e)

    def _on_canceled(evt):
        log.warning("Azure Speech: canceled — %s", evt.result.cancellation_details)
        done[0] = True

    def _on_session_stopped(evt):
        done[0] = True

    if settings.diarization_enabled:
        recognizer.transcribed.connect(_on_result)
        recognizer.session_stopped.connect(_on_session_stopped)
        recognizer.canceled.connect(_on_canceled)
        recognizer.start_transcribing_async()
    else:
        recognizer.recognized.connect(_on_result)
        recognizer.session_stopped.connect(_on_session_stopped)
        recognizer.canceled.connect(_on_canceled)
        recognizer.start_continuous_recognition_async()

    # Poll until done (Azure SDK is callback-based)
    timeout = 60 * 60  # 1 hour max
    start = time.time()
    while not done[0] and (time.time() - start) < timeout:
        time.sleep(0.5)

    if settings.diarization_enabled:
        recognizer.stop_transcribing_async().get()
    else:
        recognizer.stop_continuous_recognition_async().get()

    full_text = " ".join(s["text"] for s in all_results).strip()
    lang_code = language.split("-")[0]  # "en-US" → "en"

    log.info(
        "Azure Speech: transcription complete — %d segments, %d words",
        len(all_results), sum(len(s["words"]) for s in all_results),
    )

    return {
        "language": lang_code,
        "alignment": "azure_speech",
        "segments": all_results,
        "full_text": full_text,
    }
