"""Explanation Agent — generates a human-readable summary of editing decisions."""

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def generate_explanation(
    plan: dict, signals: dict, storage: StorageManager
) -> dict:
    """
    Generate an explanation of what the pipeline did and why.

    Output saved to outputs/explanation.json:
    {
      "summary": "Created a 30s high-energy montage from 8 minutes of F1 footage...",
      "decisions": [
        {"stage": "highlights", "detail": "Selected 17 segments from 114 candidates..."},
        ...
      ],
      "stats": {
        "input_duration": 480.0,
        "output_duration": 28.3,
        "compression_ratio": "17x",
        ...
      }
    }
    """
    decisions = []
    stats = {}

    # Input stats
    manifest = signals.get("media_manifest", {})
    total_input = sum(f.get("duration", 0) for f in manifest.get("files", []))
    num_files = len(manifest.get("files", []))
    stats["input_files"] = num_files
    stats["input_duration"] = round(total_input, 1)

    # Plan info
    operations = plan.get("operations", [])
    style = plan.get("style", {})
    target = plan.get("target_duration")
    planner_type = plan.get("planner", "rule_based")

    # Content classification
    classification = signals.get("classification")
    if classification:
        video_type = classification.get("video_type", "unknown")
        type_conf = classification.get("video_type_confidence", 0)
        user_intent = classification.get("user_intent", "unknown")
        intent_conf = classification.get("user_intent_confidence", 0)
        decisions.append({
            "stage": "classification",
            "detail": f"Classified video as '{video_type}' ({type_conf:.0%} confidence) "
                      f"with user intent '{user_intent}' ({intent_conf:.0%} confidence).",
        })

    # Strategy routing
    strategy = signals.get("strategy") or plan.get("strategy")
    if strategy:
        decisions.append({
            "stage": "strategy",
            "detail": f"Applied '{strategy.get('video_type', 'default')}' editing strategy: "
                      f"energy={strategy.get('energy', 'medium')}, "
                      f"story={strategy.get('story_structure', 'medium')}, "
                      f"speaker_tags={'on' if strategy.get('caption_config', {}).get('speaker_tags') else 'off'}.",
        })

    decisions.append({
        "stage": "planning",
        "detail": f"Detected operations: {', '.join(operations)}. "
                  f"Style: {style.get('energy', 'medium')} energy, "
                  f"aspect ratio {style.get('aspect', '16:9')}."
                  + (f" Target duration: {target}s." if target else "")
                  + f" Planner: {planner_type}.",
    })

    # Visual scoring
    visual_scores = signals.get("visual_scores")
    if visual_scores:
        for track in visual_scores.get("tracks", []):
            kf_count = len(track.get("keyframes", []))
            avg_prompt = track.get("avg_prompt_score", 0)
            top_type = track.get("top_type", "unknown")
            top_conf = track.get("top_type_confidence", 0)
            decisions.append({
                "stage": "visual_scoring",
                "detail": f"Scored {kf_count} keyframes with SigLIP: "
                          f"avg prompt relevance {avg_prompt:.2f}, "
                          f"visual type '{top_type}' ({top_conf:.0%}).",
            })

    # Intelligence stats
    transcript = signals.get("transcript", {})
    total_segments = sum(
        len(t.get("segments", []))
        for t in transcript.get("tracks", [])
    )
    if total_segments:
        decisions.append({
            "stage": "transcription",
            "detail": f"Transcribed {total_segments} speech segments using Whisper.",
        })

    silence = signals.get("silence", {})
    for track in silence.get("tracks", []):
        silent_count = len(track.get("silent_regions", []))
        speech_count = len(track.get("speech_regions", []))
        if silent_count:
            decisions.append({
                "stage": "silence_detection",
                "detail": f"Found {silent_count} silent regions and "
                          f"{speech_count} speech regions.",
            })

    shots = signals.get("shots", {})
    for track in shots.get("tracks", []):
        num_shots = track.get("total_shots", 0)
        if num_shots:
            decisions.append({
                "stage": "shot_detection",
                "detail": f"Detected {num_shots} distinct shots/scenes.",
            })

    motion = signals.get("motion", {})
    for track in motion.get("tracks", []):
        high_regions = len(track.get("high_motion_regions", []))
        if high_regions:
            decisions.append({
                "stage": "motion_analysis",
                "detail": f"Found {high_regions} high-motion regions.",
            })

    faces = signals.get("faces", {})
    for track in faces.get("tracks", []):
        face_regions = len(track.get("face_regions", []))
        if face_regions:
            decisions.append({
                "stage": "face_detection",
                "detail": f"Detected faces in {face_regions} regions of the video.",
            })

    diarization = signals.get("diarization")
    if diarization:
        for track in diarization.get("tracks", []):
            n_speakers = track.get("num_speakers", 0)
            n_turns = len(track.get("speaker_turns", []))
            if n_speakers > 1:
                decisions.append({
                    "stage": "diarization",
                    "detail": f"Identified {n_speakers} speakers with {n_turns} speaker turns.",
                })

    # Highlight stats
    highlights = signals.get("highlights")
    if highlights:
        top_score = highlights[0]["score"] if highlights else 0
        decisions.append({
            "stage": "highlights",
            "detail": f"Scored {len(highlights)} candidate segments. "
                      f"Top score: {top_score:.3f}.",
        })

    # Story stats
    story = signals.get("story")
    if story:
        roles = [s["role"] for s in story]
        role_summary = ", ".join(dict.fromkeys(roles))
        story_dur = sum(s["duration"] for s in story)
        decisions.append({
            "stage": "story",
            "detail": f"Arranged {len(story)} segments into narrative: "
                      f"{role_summary}. Total: {story_dur:.1f}s.",
        })

    # Timeline stats
    try:
        dsl = storage.load_dsl()
        num_clips = len(dsl.get("clips", []))
        num_captions = len(dsl.get("captions", []))
        output_dur = sum(
            (c["end"] - c["start"]) / c.get("speed", 1.0)
            for c in dsl.get("clips", [])
        )
        stats["output_clips"] = num_clips
        stats["output_duration"] = round(output_dur, 1)
        stats["captions"] = num_captions
        stats["format"] = dsl.get("format", {}).get("aspect", "16:9")

        if total_input > 0 and output_dur > 0:
            stats["compression_ratio"] = f"{total_input / output_dur:.0f}x"

        decisions.append({
            "stage": "editing",
            "detail": f"Built timeline with {num_clips} clips, "
                      f"{num_captions} captions, {output_dur:.1f}s total output.",
        })
    except Exception:
        pass

    # Build summary
    summary = _build_summary(plan, stats, decisions)

    explanation = {
        "summary": summary,
        "decisions": decisions,
        "stats": stats,
    }

    storage.save_json("outputs", "explanation", explanation)
    log.info("Explanation generated: %d decisions", len(decisions))
    return explanation


def _build_summary(plan: dict, stats: dict, decisions: list) -> str:
    """Generate a one-paragraph summary."""
    goal = plan.get("goal", "video edit")
    style = plan.get("style", {})
    energy = style.get("energy", "medium")
    aspect = style.get("aspect", "16:9")

    input_dur = stats.get("input_duration", 0)
    output_dur = stats.get("output_duration", 0)
    num_clips = stats.get("output_clips", 0)
    ratio = stats.get("compression_ratio", "")

    parts = [f"Created a {energy}-energy {aspect} edit from"]

    if input_dur > 60:
        parts.append(f"{input_dur / 60:.1f} minutes of footage")
    else:
        parts.append(f"{input_dur:.0f}s of footage")

    if output_dur:
        parts.append(f"into a {output_dur:.0f}s video")

    if num_clips:
        parts.append(f"using {num_clips} clips")

    if ratio:
        parts.append(f"({ratio} compression)")

    summary = " ".join(parts) + "."

    if "highlight_select" in plan.get("operations", []):
        summary += " Highlights were selected based on motion intensity, audio peaks, speech content, visual relevance, and shot variety."

    if "add_captions" in plan.get("operations", []):
        captions = stats.get("captions", 0)
        summary += f" {captions} captions were added from the transcript."

    # Mention content classification if available
    strategy = plan.get("strategy")
    if strategy:
        video_type = strategy.get("video_type", "").replace("_", " ")
        user_intent = strategy.get("user_intent", "").replace("_", " ")
        if video_type and user_intent:
            summary += f" Editing strategy was optimized for {video_type} content with {user_intent} intent."

    return summary
