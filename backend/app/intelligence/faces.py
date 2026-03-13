"""Face detection using MediaPipe Tasks API."""

import os
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "blaze_face_short_range.tflite"


def _ensure_model() -> str:
    """Download the face detection model if not cached."""
    if MODEL_PATH.exists():
        return str(MODEL_PATH)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Downloading face detection model...")
    urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
    log.info("Model saved to %s", MODEL_PATH)
    return str(MODEL_PATH)


def detect_faces(storage: StorageManager, sample_fps: float = 2.0) -> dict:
    """
    Detect faces per frame using MediaPipe on the proxy video.

    Output saved to signals/faces.json:
    {
      "tracks": [
        {
          "source": "clip.mp4",
          "detections": [
            {"time": 1.0, "count": 2, "confidence": 0.95,
             "boxes": [{"x": 0.3, "y": 0.2, "w": 0.15, "h": 0.2}]}
          ],
          "face_regions": [
            {"start": 0.5, "end": 5.0, "avg_count": 1.5, "avg_confidence": 0.88}
          ]
        }
      ]
    }
    """
    model_path = _ensure_model()
    manifest = storage.load_signal("media_manifest")
    tracks = []

    BaseOptions = mp.tasks.BaseOptions
    FaceDetector = mp.tasks.vision.FaceDetector
    FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions

    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        min_detection_confidence=0.5,
    )

    with FaceDetector.create_from_options(options) as detector:
        for file_info in manifest["files"]:
            if file_info.get("width", 0) == 0:
                continue

            proxy_path = file_info.get("proxy_path")
            video_path = proxy_path or file_info["raw_path"]
            log.info("Detecting faces: %s", file_info["filename"])

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                log.error("Cannot open video: %s", video_path)
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_skip = max(1, int(fps / sample_fps))
            detections = []
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_skip == 0:
                    time_sec = frame_idx / fps
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(
                        image_format=mp.ImageFormat.SRGB, data=rgb
                    )
                    results = detector.detect(mp_image)

                    boxes = []
                    max_conf = 0.0
                    for det in results.detections:
                        bb = det.bounding_box
                        conf = det.categories[0].score
                        max_conf = max(max_conf, conf)
                        # Normalize box to relative coords
                        img_h, img_w = frame.shape[:2]
                        boxes.append({
                            "x": round(bb.origin_x / img_w, 3),
                            "y": round(bb.origin_y / img_h, 3),
                            "w": round(bb.width / img_w, 3),
                            "h": round(bb.height / img_h, 3),
                        })

                    detections.append({
                        "time": round(time_sec, 3),
                        "count": len(boxes),
                        "confidence": round(max_conf, 3),
                        "boxes": boxes,
                    })

                frame_idx += 1

            cap.release()

            # Group into face regions (consecutive frames with faces)
            face_regions = _find_face_regions(detections)

            tracks.append({
                "source": file_info["filename"],
                "detections": detections,
                "face_regions": face_regions,
            })

    faces_data = {"tracks": tracks}
    storage.save_signal("faces", faces_data)
    log.info("Face detection complete: %d tracks", len(tracks))
    return faces_data


def _find_face_regions(detections: list[dict], min_gap: float = 1.0) -> list[dict]:
    """Group consecutive face detections into regions."""
    regions = []
    current_start = None
    counts = []
    confs = []

    for det in detections:
        if det["count"] > 0:
            if current_start is None:
                current_start = det["time"]
            counts.append(det["count"])
            confs.append(det["confidence"])
        else:
            if current_start is not None:
                regions.append({
                    "start": round(current_start, 3),
                    "end": round(det["time"], 3),
                    "avg_count": round(sum(counts) / len(counts), 2),
                    "avg_confidence": round(sum(confs) / len(confs), 3),
                })
                current_start = None
                counts = []
                confs = []

    # Close last region
    if current_start is not None and detections:
        regions.append({
            "start": round(current_start, 3),
            "end": round(detections[-1]["time"], 3),
            "avg_count": round(sum(counts) / len(counts), 2),
            "avg_confidence": round(sum(confs) / len(confs), 3),
        })

    return regions
