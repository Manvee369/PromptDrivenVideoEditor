"""Thumbnail Agent — selects the best frame and generates a thumbnail."""

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def generate_thumbnail(
    plan: dict, signals: dict, storage: StorageManager
) -> Path:
    """
    Select the best frame for a thumbnail based on:
    - High motion intensity
    - Face presence + high confidence
    - Audio peak (excitement moment)

    Then extract that frame and overlay text.
    Output saved to outputs/thumbnail.png.
    """
    manifest = signals.get("media_manifest", {})
    motion_data = signals.get("motion", {})
    faces_data = signals.get("faces", {})
    energy_data = signals.get("audio_energy", {})

    best_time = 0.0
    best_score = -1.0
    best_source = None

    for file_info in manifest.get("files", []):
        if file_info.get("width", 0) == 0:
            continue

        filename = file_info["filename"]

        # Score candidate times
        candidates = _score_candidates(
            filename, motion_data, faces_data, energy_data
        )

        for cand in candidates:
            if cand["score"] > best_score:
                best_score = cand["score"]
                best_time = cand["time"]
                best_source = filename

    if best_source is None:
        log.warning("No suitable thumbnail frame found")
        return None

    log.info("Best thumbnail frame: %s at %.1fs (score: %.3f)",
             best_source, best_time, best_score)

    # Extract the frame
    raw_path = storage.stage_dir("raw") / best_source
    frame = _extract_frame(str(raw_path), best_time)
    if frame is None:
        log.error("Failed to extract frame at %.1fs", best_time)
        return None

    # Convert to PIL and add text overlay
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)

    # Resize to thumbnail dimensions
    style = plan.get("style", {})
    aspect = style.get("aspect", "16:9")
    if aspect == "9:16":
        thumb_size = (1080, 1920)
    elif aspect == "1:1":
        thumb_size = (1080, 1080)
    else:
        thumb_size = (1920, 1080)

    img = _fit_to_size(img, thumb_size)

    # Add text overlay from prompt goal
    goal = plan.get("goal", "")
    if goal:
        img = _add_text_overlay(img, _make_title(goal))

    # Save
    output_path = storage.output_path("thumbnail.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    log.info("Thumbnail saved: %s", output_path)
    return output_path


def _score_candidates(
    filename: str,
    motion_data: dict,
    faces_data: dict,
    energy_data: dict,
) -> list[dict]:
    """Score time points for thumbnail quality."""
    # Collect all scored time points from motion
    motion_scores = {}
    for track in motion_data.get("tracks", []):
        if track["source"] == filename:
            for s in track.get("scores", []):
                motion_scores[round(s["time"], 1)] = s["intensity"]

    # Face presence by time
    face_scores = {}
    for track in faces_data.get("tracks", []):
        if track["source"] == filename:
            for d in track.get("detections", []):
                if d["count"] > 0:
                    face_scores[round(d["time"], 1)] = d["confidence"]

    # Audio peaks
    peak_times = set()
    for track in energy_data.get("tracks", []):
        if track["source"] == filename:
            for p in track.get("peaks", []):
                peak_times.add(round(p["time"], 1))

    # Combine all time points
    all_times = set(motion_scores.keys()) | set(face_scores.keys())

    candidates = []
    for t in all_times:
        motion = motion_scores.get(t, 0)
        face = face_scores.get(t, 0)
        peak = 1.0 if t in peak_times else 0.0

        score = 0.35 * motion + 0.40 * face + 0.25 * peak
        candidates.append({"time": t, "score": score})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:20]


def _extract_frame(video_path: str, time_sec: float):
    """Extract a single frame from a video at the given time."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def _fit_to_size(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize and center-crop image to fit target size."""
    target_w, target_h = size
    target_ratio = target_w / target_h
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        # Wider than target — fit height, crop width
        new_h = target_h
        new_w = int(img_ratio * target_h)
    else:
        # Taller than target — fit width, crop height
        new_w = target_w
        new_h = int(target_w / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def _make_title(goal: str) -> str:
    """Extract a short title from the prompt goal."""
    # Remove common instruction words, keep the subject
    skip = {"make", "create", "generate", "a", "an", "the", "with", "and",
            "second", "seconds", "minute", "minutes", "montage", "video",
            "edit", "vertical", "horizontal", "tiktok", "reels", "shorts"}
    words = [w for w in goal.split() if w.lower() not in skip]
    title = " ".join(words[:5]).strip()
    return title.upper() if title else ""


def _add_text_overlay(img: Image.Image, text: str) -> Image.Image:
    """Add bold text overlay with shadow to bottom of image."""
    if not text:
        return img

    draw = ImageDraw.Draw(img)

    # Try to use a bold font, fall back to default
    font_size = img.height // 15
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    # Calculate text position (bottom center)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (img.width - text_w) // 2
    y = img.height - text_h - img.height // 10

    # Shadow
    shadow_offset = max(2, font_size // 20)
    draw.text((x + shadow_offset, y + shadow_offset), text, fill=(0, 0, 0), font=font)
    draw.text((x - 1, y - 1), text, fill=(0, 0, 0), font=font)
    # Main text
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return img
