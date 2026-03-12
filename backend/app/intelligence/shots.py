"""Shot/scene detection using PySceneDetect."""

from pathlib import Path

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def detect_shots(storage: StorageManager, threshold: float = 27.0) -> dict:
    """
    Detect scene/shot boundaries using PySceneDetect ContentDetector.

    Output saved to signals/shots.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "shots": [
            {"start": 0.0, "end": 3.5, "duration": 3.5, "index": 0},
            {"start": 3.5, "end": 8.2, "duration": 4.7, "index": 1}
          ],
          "total_shots": 5
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    tracks = []

    for file_info in manifest["files"]:
        # Skip non-video files
        if file_info.get("width", 0) == 0:
            continue

        proxy_path = file_info.get("proxy_path")
        source_path = proxy_path or file_info["raw_path"]
        log.info("Detecting shots: %s", file_info["filename"])

        video = open_video(source_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        shots = []
        if scene_list:
            for i, (start, end) in enumerate(scene_list):
                start_sec = start.get_seconds()
                end_sec = end.get_seconds()
                shots.append({
                    "start": round(start_sec, 3),
                    "end": round(end_sec, 3),
                    "duration": round(end_sec - start_sec, 3),
                    "index": i,
                })
        else:
            # No cuts detected — treat entire video as one shot
            duration = file_info["duration"]
            shots.append({
                "start": 0.0,
                "end": round(duration, 3),
                "duration": round(duration, 3),
                "index": 0,
            })

        tracks.append({
            "source": file_info["filename"],
            "shots": shots,
            "total_shots": len(shots),
        })

    shots_data = {"tracks": tracks}
    storage.save_signal("shots", shots_data)
    log.info("Shot detection complete: %d tracks", len(tracks))
    return shots_data
