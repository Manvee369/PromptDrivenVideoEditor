"""LLM-based planner — uses Groq API for smarter prompt understanding.

Falls back to rule-based planner if API call fails.
Uses raw HTTP requests to avoid SDK dependencies.
"""

import json

import requests

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You are a professional video editor's AI assistant. Given a user's editing prompt and media analysis summary, produce a structured JSON editing plan.

Available operations (include all that apply):
- "remove_silence": Remove silent portions
- "add_captions": Add subtitles/captions from speech
- "highlight_select": Pick the best moments from the footage
- "story_compose": Arrange highlights into a narrative arc
- "beat_sync": Sync clip cuts to music beats
- "slow_motion": Apply slow-motion effect
- "black_and_white": Apply B&W filter
- "trim": Cut to a specific duration
- "add_transitions": Add crossfade/fade/flash transitions between clips

Aspect ratio options: "16:9" (landscape), "9:16" (vertical/TikTok/Reels), "1:1" (square)
Energy levels: "high" (fast cuts, intense), "medium" (balanced), "low" (calm, slow)
Transition styles: "auto" (based on energy), "none" (hard cuts only)

Respond with ONLY valid JSON matching this schema:
{
  "goal": "<user's intent in one sentence>",
  "target_duration": <seconds as number or null>,
  "style": {
    "aspect": "<aspect ratio>",
    "energy": "<energy level>",
    "transitions": "<transition style>"
  },
  "operations": ["<operation1>", "<operation2>"],
  "priorities": {
    "motion": <0.0-1.0>,
    "audio_peak": <0.0-1.0>,
    "speech": <0.0-1.0>,
    "shot_variety": <0.0-1.0>,
    "face": <0.0-1.0>
  }
}

Priority weights should sum to 1.0. They control how highlights are scored.
Infer operations even if not explicitly mentioned (e.g., "podcast clip for Twitter" implies vertical + captions + trim).
"""

VALID_OPERATIONS = {
    "remove_silence", "add_captions", "highlight_select", "story_compose",
    "beat_sync", "slow_motion", "black_and_white", "trim", "add_transitions",
}

VALID_ASPECTS = {"16:9", "9:16", "1:1"}
VALID_ENERGIES = {"high", "medium", "low"}

ASPECT_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


def llm_plan_edit(prompt: str, signals: dict) -> dict | None:
    """
    Call Groq API to produce a structured editing plan.

    Returns the plan dict or None if the call fails.
    """
    if not settings.llm_api_key:
        return None

    summary = _build_media_summary(signals)
    user_message = f"User prompt: {prompt}\n\nMedia analysis:\n{summary}"

    try:
        response = _call_groq(user_message)
        if not response:
            return None

        plan = _parse_and_validate(response, prompt)
        if plan:
            log.info("LLM planner produced plan: operations=%s", plan.get("operations"))
        return plan

    except Exception as e:
        log.warning("LLM planner error: %s", e)
        return None


def _build_media_summary(signals: dict) -> str:
    """Condense signals into a text summary for the LLM."""
    lines = []

    manifest = signals.get("media_manifest", {})
    files = manifest.get("files", [])
    total_dur = sum(f.get("duration", 0) for f in files)
    lines.append(f"Files: {len(files)}, total duration: {total_dur:.1f}s ({total_dur/60:.1f} min)")

    for f in files:
        lines.append(f"  - {f.get('filename')}: {f.get('duration', 0):.1f}s, "
                     f"{f.get('width', 0)}x{f.get('height', 0)}")

    transcript = signals.get("transcript", {})
    seg_count = sum(len(t.get("segments", [])) for t in transcript.get("tracks", []))
    if seg_count:
        lines.append(f"Speech: {seg_count} transcript segments detected")

    shots = signals.get("shots", {})
    for t in shots.get("tracks", []):
        lines.append(f"Shots: {t.get('total_shots', 0)} scene changes")

    motion = signals.get("motion", {})
    for t in motion.get("tracks", []):
        high = len(t.get("high_motion_regions", []))
        lines.append(f"Motion: {high} high-motion regions")

    faces = signals.get("faces", {})
    for t in faces.get("tracks", []):
        regions = len(t.get("face_regions", []))
        lines.append(f"Faces: detected in {regions} regions")

    diarization = signals.get("diarization")
    if diarization:
        for t in diarization.get("tracks", []):
            lines.append(f"Speakers: {t.get('num_speakers', 1)} detected")

    return "\n".join(lines)


def _call_groq(user_message: str) -> str | None:
    """Call Groq API (OpenAI-compatible endpoint)."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            "max_completion_tokens": 800,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        log.warning("Groq API returned %d: %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_and_validate(response: str, prompt: str) -> dict | None:
    """Parse LLM response and validate the plan structure."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM response is not valid JSON")
        return None

    if not isinstance(plan.get("operations"), list):
        return None

    plan["operations"] = [op for op in plan["operations"] if op in VALID_OPERATIONS]
    if not plan["operations"]:
        return None

    style = plan.get("style", {})
    aspect = style.get("aspect", "16:9")
    if aspect not in VALID_ASPECTS:
        aspect = "16:9"
    style["aspect"] = aspect

    width, height = ASPECT_DIMENSIONS[aspect]
    style["width"] = width
    style["height"] = height

    energy = style.get("energy", "medium")
    if energy not in VALID_ENERGIES:
        energy = "medium"
    style["energy"] = energy

    plan["style"] = style

    priorities = plan.get("priorities", {})
    expected_keys = {"motion", "audio_peak", "speech", "shot_variety", "face"}
    if not all(k in priorities for k in expected_keys):
        priorities = {"motion": 0.30, "audio_peak": 0.25, "speech": 0.15,
                      "shot_variety": 0.15, "face": 0.15}
    plan["priorities"] = priorities

    plan["goal"] = plan.get("goal", prompt)

    td = plan.get("target_duration")
    if td is not None:
        try:
            plan["target_duration"] = float(td)
        except (TypeError, ValueError):
            plan["target_duration"] = None

    plan["constraints"] = plan.get("constraints", {})
    plan["planner"] = "llm"

    return plan
