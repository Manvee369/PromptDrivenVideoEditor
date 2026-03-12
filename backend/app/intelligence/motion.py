"""Motion intensity detection using OpenCV frame differencing."""

import cv2
import numpy as np

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def detect_motion(storage: StorageManager, sample_fps: float = 5.0) -> dict:
    """
    Compute motion intensity per frame using frame differencing on proxy video.
    Samples at `sample_fps` to keep it fast.

    Output saved to signals/motion.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "sample_fps": 5.0,
          "scores": [
            {"time": 0.0, "intensity": 0.02},
            {"time": 0.2, "intensity": 0.15}
          ],
          "high_motion_regions": [
            {"start": 3.0, "end": 5.4, "avg_intensity": 0.72}
          ]
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    tracks = []

    for file_info in manifest["files"]:
        if file_info.get("width", 0) == 0:
            continue

        proxy_path = file_info.get("proxy_path")
        video_path = proxy_path or file_info["raw_path"]
        log.info("Detecting motion: %s", file_info["filename"])

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            log.error("Cannot open video: %s", video_path)
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_skip = max(1, int(fps / sample_fps))
        scores = []
        prev_gray = None
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if prev_gray is not None:
                    diff = cv2.absdiff(prev_gray, gray)
                    intensity = float(np.mean(diff)) / 255.0
                    time_sec = frame_idx / fps
                    scores.append({
                        "time": round(time_sec, 3),
                        "intensity": round(intensity, 4),
                    })

                prev_gray = gray

            frame_idx += 1

        cap.release()

        # Find high-motion regions (above 70th percentile, grouped)
        high_motion_regions = _find_high_motion_regions(scores)

        tracks.append({
            "source": file_info["filename"],
            "sample_fps": sample_fps,
            "scores": scores,
            "high_motion_regions": high_motion_regions,
        })

    motion_data = {"tracks": tracks}
    storage.save_signal("motion", motion_data)
    log.info("Motion detection complete: %d tracks", len(tracks))
    return motion_data


def _find_high_motion_regions(
    scores: list[dict], percentile: float = 70, min_gap: float = 0.5
) -> list[dict]:
    """Group consecutive high-motion frames into regions."""
    if not scores:
        return []

    intensities = [s["intensity"] for s in scores]
    threshold = float(np.percentile(intensities, percentile))

    regions = []
    current_start = None
    current_intensities = []

    for s in scores:
        if s["intensity"] >= threshold:
            if current_start is None:
                current_start = s["time"]
            current_intensities.append(s["intensity"])
        else:
            if current_start is not None:
                regions.append({
                    "start": round(current_start, 3),
                    "end": round(s["time"], 3),
                    "avg_intensity": round(float(np.mean(current_intensities)), 4),
                })
                current_start = None
                current_intensities = []

    # Close last region
    if current_start is not None and scores:
        regions.append({
            "start": round(current_start, 3),
            "end": round(scores[-1]["time"], 3),
            "avg_intensity": round(float(np.mean(current_intensities)), 4),
        })

    return regions
