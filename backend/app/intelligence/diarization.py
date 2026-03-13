"""Speaker diarization using MFCC embeddings + agglomerative clustering.

No heavy dependencies — uses librosa (already installed) for features
and scikit-learn for clustering. Works well for 2-4 speaker content
like podcasts and interviews.
"""

import string

import librosa
import numpy as np
from sklearn.cluster import AgglomerativeClustering

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def diarize(storage: StorageManager, max_speakers: int = 6) -> dict:
    """
    Assign speaker labels to each transcript segment using audio clustering.

    Reads signals/transcript.json and the prep/ audio files.
    Output saved to signals/diarization.json:
    {
      "tracks": [{
        "source": "clip.mp4",
        "num_speakers": 2,
        "segments": [
          {"start": 0.0, "end": 2.5, "text": "Hello", "speaker": "A"}
        ],
        "speaker_turns": [
          {"speaker": "A", "start": 0.0, "end": 2.5}
        ]
      }]
    }
    """
    transcript = storage.load_signal("transcript")
    manifest = storage.load_signal("media_manifest")

    # Build audio path lookup
    audio_lookup = {}
    for f in manifest["files"]:
        if f.get("audio_path"):
            audio_lookup[f["filename"]] = f["audio_path"]

    tracks = []

    for t_track in transcript.get("tracks", []):
        source = t_track["source"]
        segments = t_track.get("segments", [])

        if not segments or source not in audio_lookup:
            continue

        audio_path = audio_lookup[source]
        log.info("Diarizing %s (%d segments)", source, len(segments))

        # Extract MFCC embeddings for each segment
        embeddings = _extract_embeddings(audio_path, segments)

        if len(embeddings) < 2:
            # Single segment or failed extraction — assign all to speaker A
            labeled = [
                {**seg, "speaker": "A"} for seg in segments
            ]
            tracks.append({
                "source": source,
                "num_speakers": 1,
                "segments": labeled,
                "speaker_turns": _build_turns(labeled),
            })
            continue

        # Cluster embeddings to find speakers
        n_clusters = min(max_speakers, len(embeddings))
        labels = _cluster_speakers(embeddings, n_clusters)

        # Map cluster IDs to stable letter labels (most frequent = A)
        label_map = _build_label_map(labels)
        num_speakers = len(set(labels))

        labeled = []
        for seg, label in zip(segments, labels):
            labeled.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
                "speaker": label_map[label],
            })

        turns = _build_turns(labeled)

        tracks.append({
            "source": source,
            "num_speakers": num_speakers,
            "segments": labeled,
            "speaker_turns": turns,
        })

        log.info("Diarized %s: %d speakers, %d turns",
                 source, num_speakers, len(turns))

    result = {"tracks": tracks}
    storage.save_signal("diarization", result)
    log.info("Diarization complete: %d tracks", len(tracks))
    return result


def _extract_embeddings(
    audio_path: str, segments: list[dict], sr: int = 16000, n_mfcc: int = 20
) -> np.ndarray:
    """Extract mean MFCC vector per segment as speaker embedding."""
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    total_duration = len(y) / sr

    embeddings = []
    for seg in segments:
        start_sample = int(seg["start"] * sr)
        end_sample = int(min(seg["end"], total_duration) * sr)

        if end_sample <= start_sample:
            embeddings.append(np.zeros(n_mfcc))
            continue

        chunk = y[start_sample:end_sample]
        if len(chunk) < sr * 0.1:  # skip chunks shorter than 100ms
            embeddings.append(np.zeros(n_mfcc))
            continue

        mfcc = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=n_mfcc)
        embeddings.append(np.mean(mfcc, axis=1))

    return np.array(embeddings)


def _cluster_speakers(embeddings: np.ndarray, max_k: int) -> np.ndarray:
    """Cluster speaker embeddings. Auto-selects number of clusters."""
    from sklearn.metrics import silhouette_score

    best_labels = None
    best_score = -1

    # Try k from 2 to max_k, pick best silhouette score
    for k in range(2, min(max_k + 1, len(embeddings))):
        try:
            model = AgglomerativeClustering(n_clusters=k)
            labels = model.fit_predict(embeddings)
            score = silhouette_score(embeddings, labels)
            if score > best_score:
                best_score = score
                best_labels = labels
        except Exception:
            continue

    if best_labels is None:
        # Fallback: everything is one speaker
        return np.zeros(len(embeddings), dtype=int)

    return best_labels


def _build_label_map(labels: np.ndarray) -> dict[int, str]:
    """Map cluster IDs to letters, most frequent speaker = A."""
    unique, counts = np.unique(labels, return_counts=True)
    sorted_by_freq = unique[np.argsort(-counts)]
    return {
        int(cluster_id): string.ascii_uppercase[i]
        for i, cluster_id in enumerate(sorted_by_freq)
    }


def _build_turns(labeled_segments: list[dict]) -> list[dict]:
    """Group consecutive same-speaker segments into turns."""
    if not labeled_segments:
        return []

    turns = []
    current = {
        "speaker": labeled_segments[0]["speaker"],
        "start": labeled_segments[0]["start"],
        "end": labeled_segments[0]["end"],
    }

    for seg in labeled_segments[1:]:
        if seg["speaker"] == current["speaker"]:
            current["end"] = seg["end"]
        else:
            turns.append(current)
            current = {
                "speaker": seg["speaker"],
                "start": seg["start"],
                "end": seg["end"],
            }

    turns.append(current)
    return turns
