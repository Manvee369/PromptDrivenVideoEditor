"""Visual scoring using SigLIP ViT-B/16 via open_clip.

Extracts keyframes from shot boundaries, computes:
1. Text-image similarity scores (prompt relevance per keyframe)
2. Zero-shot video type classification from sampled frames

Outputs saved to signals/visual_scores.json.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Lazy-loaded model singletons
_model = None
_preprocess = None
_tokenizer = None

# Zero-shot labels for video type classification
VIDEO_TYPE_LABELS = [
    "a person talking directly to the camera, vlog style",
    "multiple people having a conversation or interview, podcast style",
    "sports action footage with athletes competing",
    "video game screen recording or gaming footage",
    "outdoor travel or adventure footage, vlog",
    "tutorial or educational content with screen or demonstration",
    "live event, concert, or ceremony footage",
    "raw unedited footage, b-roll, or stock clips",
    "cooking or food preparation video",
    "music performance or music video",
]

VIDEO_TYPE_KEYS = [
    "talking_head",
    "podcast",
    "sports",
    "gaming",
    "vlog",
    "tutorial",
    "event",
    "raw_footage",
    "cooking",
    "music_performance",
]


def _load_model():
    """Lazy-load SigLIP model on first use."""
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return

    import open_clip
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("Loading SigLIP model: %s (%s) on %s",
             settings.visual_model, settings.visual_pretrained, device)

    _model, _, _preprocess = open_clip.create_model_and_transforms(
        settings.visual_model,
        pretrained=settings.visual_pretrained,
    )

    # SigLIP uses a HuggingFace tokenizer — requires `transformers` package.
    try:
        _tokenizer = open_clip.get_tokenizer(settings.visual_model)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load tokenizer for '{settings.visual_model}'. "
            "Ensure `transformers` is installed: pip install transformers"
        ) from exc

    if _tokenizer is None:
        raise RuntimeError(
            f"get_tokenizer returned None for '{settings.visual_model}'. "
            "Check open_clip and transformers versions."
        )

    _model = _model.to(device)
    _model.eval()
    log.info("SigLIP model loaded successfully")


def _get_device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def _extract_keyframe(video_path: str, time_sec: float) -> np.ndarray | None:
    """Extract a single frame from video at the given timestamp."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return None

    # Convert BGR to RGB
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _get_keyframe_times(shots_data: dict, filename: str, duration: float) -> list[float]:
    """Get keyframe timestamps: middle of each shot, or uniform sampling."""
    for track in shots_data.get("tracks", []):
        if track["source"] == filename:
            shots = track.get("shots", [])
            if shots:
                # Use midpoint of each shot
                return [round((s["start"] + s["end"]) / 2, 3) for s in shots]

    # No shots — sample uniformly
    interval = 1.0 / settings.visual_sample_fps
    times = []
    t = interval / 2  # start at half-interval to avoid black frames at 0
    while t < duration:
        times.append(round(t, 3))
        t += interval
    return times or [duration / 2]


def compute_visual_scores(
    prompt: str,
    storage: StorageManager,
    shots_data: dict | None = None,
) -> dict:
    """
    Score keyframes against the user prompt and classify video type.

    Returns dict saved to signals/visual_scores.json:
    {
        "tracks": [{
            "source": "clip.mp4",
            "keyframes": [
                {"time": 5.0, "prompt_score": 0.82, "type_scores": {...}}
            ],
            "avg_prompt_score": 0.75,
            "classification": {
                "talking_head": 0.65, "sports": 0.12, ...
            },
            "top_type": "talking_head",
            "top_type_confidence": 0.65
        }]
    }
    """
    import torch
    from PIL import Image

    _load_model()

    manifest = storage.load_signal("media_manifest")
    if shots_data is None and storage.has_json("signals", "shots"):
        shots_data = storage.load_signal("shots")
    shots_data = shots_data or {}

    device = _get_device()
    tracks = []

    # Tokenize prompt once
    prompt_tokens = _tokenizer([prompt]).to(device)
    with torch.no_grad():
        prompt_features = _model.encode_text(prompt_tokens)
        prompt_features = prompt_features / prompt_features.norm(dim=-1, keepdim=True)

    # Tokenize video type labels once
    type_tokens = _tokenizer(VIDEO_TYPE_LABELS).to(device)
    with torch.no_grad():
        type_features = _model.encode_text(type_tokens)
        type_features = type_features / type_features.norm(dim=-1, keepdim=True)

    for file_info in manifest["files"]:
        if file_info.get("width", 0) == 0:
            continue

        filename = file_info["filename"]
        duration = file_info["duration"]
        video_path = file_info.get("proxy_path") or file_info["raw_path"]

        log.info("Visual scoring: %s", filename)

        keyframe_times = _get_keyframe_times(shots_data, filename, duration)
        # Cap at 30 keyframes to keep inference fast
        if len(keyframe_times) > 30:
            step = len(keyframe_times) / 30
            keyframe_times = [keyframe_times[int(i * step)] for i in range(30)]

        keyframes = []
        all_prompt_scores = []
        type_score_accum = np.zeros(len(VIDEO_TYPE_LABELS))
        valid_frames = 0

        for t in keyframe_times:
            frame_rgb = _extract_keyframe(video_path, t)
            if frame_rgb is None:
                continue

            # Preprocess frame for model
            pil_img = Image.fromarray(frame_rgb)
            img_tensor = _preprocess(pil_img).unsqueeze(0).to(device)

            with torch.no_grad():
                img_features = _model.encode_image(img_tensor)
                img_features = img_features / img_features.norm(dim=-1, keepdim=True)

                # Prompt similarity
                prompt_sim = (img_features @ prompt_features.T).squeeze().item()
                # Sigmoid to map to 0-1 (SigLIP uses sigmoid loss)
                prompt_score = float(1 / (1 + np.exp(-prompt_sim)))

                # Video type classification
                type_sims = (img_features @ type_features.T).squeeze().cpu().numpy()
                type_probs = np.exp(type_sims) / np.exp(type_sims).sum()

            type_scores_dict = {
                key: round(float(prob), 4)
                for key, prob in zip(VIDEO_TYPE_KEYS, type_probs)
            }

            keyframes.append({
                "time": t,
                "prompt_score": round(prompt_score, 4),
                "type_scores": type_scores_dict,
            })

            all_prompt_scores.append(prompt_score)
            type_score_accum += type_probs
            valid_frames += 1

        # Aggregate across all keyframes
        if valid_frames > 0:
            avg_prompt = float(np.mean(all_prompt_scores))
            avg_type_scores = type_score_accum / valid_frames
            classification = {
                key: round(float(score), 4)
                for key, score in zip(VIDEO_TYPE_KEYS, avg_type_scores)
            }
            top_idx = int(np.argmax(avg_type_scores))
            top_type = VIDEO_TYPE_KEYS[top_idx]
            top_confidence = float(avg_type_scores[top_idx])
        else:
            avg_prompt = 0.0
            classification = {k: 0.0 for k in VIDEO_TYPE_KEYS}
            top_type = "raw_footage"
            top_confidence = 0.0

        tracks.append({
            "source": filename,
            "keyframes": keyframes,
            "avg_prompt_score": round(avg_prompt, 4),
            "classification": classification,
            "top_type": top_type,
            "top_type_confidence": round(top_confidence, 4),
        })

        log.info("Visual scoring complete for %s: top_type=%s (%.2f), avg_prompt=%.3f",
                 filename, top_type, top_confidence, avg_prompt)

    result = {"tracks": tracks}
    storage.save_signal("visual_scores", result)
    log.info("Visual scoring complete: %d tracks processed", len(tracks))
    return result
