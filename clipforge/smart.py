"""Optional, bounded scene-aware selection. Not semantic event recognition.

PySceneDetect identifies scene boundaries, not jokes or gameplay highlights.
Combine boundaries with the existing audio-activity heuristic conservatively.
No dependency is loaded unless SMART_SCENES=1.
"""
from __future__ import annotations

import os
from pathlib import Path

MAX_SCAN_SECONDS = 300.0


def find_cuts(path: Path, *, limit_seconds: float = MAX_SCAN_SECONDS) -> list[float]:
    """Get visual cuts from PySceneDetect if installed; fail open to audio baseline."""
    try:
        from scenedetect import open_video, SceneManager, ContentDetector
    except ImportError:
        return []
    try:
        video = open_video(str(path))
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=27.0))
        manager.detect_scenes(
            video=video, end_time=float(max(1.0, min(limit_seconds, MAX_SCAN_SECONDS))),
            show_progress=False
        )
        # Direct cut list, not list of scenes (which can omit the opening scene).
        cuts = [round(float(t.get_seconds()), 3) for t in manager.get_cut_list()]
        return [t for t in cuts if 0 < t < limit_seconds][:500]
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Scene detection unavailable: {type(exc).__name__}", flush=True)
        return []


def scene_aware_start(audio_start: float, total: float, length: float,
                      cuts: list[float]) -> float:
    """Favor audio high-energy windows, align starts near reasonable scene cuts."""
    upper = max(0.0, total - length)
    baseline = min(upper, max(0.0, audio_start))
    if not cuts or length <= 0 or upper <= 0:
        return baseline
    candidates = [baseline]
    for cut in cuts:
        if 0 <= cut <= upper and abs(cut - baseline) <= min(10.0, length / 3):
            candidates.append(cut)
    # Preserve audio focus; visual cut only nudges beginning, doesn't replace the event.
    def value(start: float) -> float:
        drift = abs(start - baseline) / max(1.0, length)
        visual = min(4, sum(start < cut < start + length for cut in cuts)) / 4
        return -drift + 0.15 * visual
    return min(upper, max(0.0, max(candidates, key=value)))


def choose_smart_highlight(path: Path, total: float, length: float) -> tuple[float, dict]:
    """Return proposed start with enough metadata to distinguish heuristics."""
    from .core import choose_highlight
    baseline = choose_highlight(path, total, length)
    enabled = os.getenv("SMART_SCENES", "0") == "1"
    if not enabled:
        return baseline, {"method": "audio", "visual_analysis": False, "cuts": 0}
    cuts = find_cuts(path, limit_seconds=min(total, MAX_SCAN_SECONDS))
    start = scene_aware_start(baseline, total, length, cuts)
    return start, {
        "method": "audio+scene-boundaries" if cuts else "audio-fallback",
        "visual_analysis": bool(cuts), "cuts": len(cuts),
    }
