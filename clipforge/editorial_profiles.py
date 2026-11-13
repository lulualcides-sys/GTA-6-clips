"""Narrative editing decisions shared by games, independent of the renderer.

This module does not identify events, transcribe speech or edit video.
An editor supplies the actual scene boundaries after inspecting source footage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
import re
import unicodedata


@dataclass(frozen=True)
class EditorialStyle:
    key: str
    story_goal: str
    framing: str
    sound: str
    titles: str
    replay: str


STYLES = {
    "humor_visual": EditorialStyle(
        "humor_visual", "Prepare the joke, show the unexpected event, preserve the reaction",
        "Keep the cause and consequence on screen; show facecam only when useful",
        "Preserve timing of the original laughter/reaction; no artificial laughter",
        "Short natural PT-BR hook; no redundant subtitles",
        "Only replay a visual payoff if it makes the joke funnier",
    ),
    "dialogo": EditorialStyle(
        "dialogo", "Preserve who speaks, the setup, the answer and the punchline",
        "Prioritize speakers, facecams and readable dialogue over random action zooms",
        "Original speech stays intelligible; lower music below voices",
        "Accurate synchronized PT-BR subtitles when needed; never fabricate speech",
        "Normally none; avoid replay that breaks conversational timing",
    ),
    "clutch": EditorialStyle(
        "clutch", "Show the disadvantage, the approach, decisive duel and aftermath",
        "Protect scoreboard, target, reticle and critical HUD; facecam near top when useful",
        "Build tension from game audio and reactions, not generic impact sounds",
        "Explain the stakes briefly; remove text during the decisive play",
        "Optional very short replay after the resolution, never before",
    ),
    "teamfight": EditorialStyle(
        "teamfight", "Show team positioning, initiation, combo, outcome and reaction",
        "Keep teams, health bars and important abilities readable",
        "Preserve ability and caster sounds at the climax",
        "A brief PT-BR contextual title; no invented callouts",
        "Replay the decisive ability only if necessary to understand",
    ),
    "sobrevivencia": EditorialStyle(
        "sobrevivencia", "Show the objective, threat, failed attempt or success and consequence",
        "Keep the danger and player action visible; no oversized blurred bands",
        "Preserve ambient danger, original reactions and suspense",
        "Name the challenge, not a result that has not happened yet",
        "Optional after the surprise, not a substitute for setup",
    ),
    "competicao": EditorialStyle(
        "competicao", "Establish score and time, follow the attempt and its result",
        "Protect clock, score and the ball/vehicle/action area",
        "Emphasize naturally rising crowd or game audio",
        "Briefly state what is at stake; never hide score",
        "Optional for the decisive moment after it has happened",
    ),
    "narrativo": EditorialStyle(
        "narrativo", "Keep a complete understandable setup, escalation, payoff and reaction",
        "Prioritize the action and a readable facecam when relevant",
        "Original audio first; effects only if they clarify the event",
        "One natural PT-BR hook, not repeated captions",
        "Only when the selected event benefits",
    ),
}

# These are *starting suggestions* only. The actual incident determines the edit.
GAME_DEFAULTS = {
    "grand theft auto vi": "humor_visual", "grand theft auto 6": "humor_visual",
    "grand theft auto v": "humor_visual", "gta vi": "humor_visual",
    "gta 6": "humor_visual", "gta v": "humor_visual",
    "gta rp": "dialogo", "minecraft": "sobrevivencia",
    "fortnite": "clutch", "call of duty warzone": "clutch",
    "warzone": "clutch", "counter strike 2": "clutch",
    "counter strike": "clutch", "cs2": "clutch",
    "league of legends": "teamfight", "lol": "teamfight",
    "rocket league": "competicao", "ea sports fc 26": "competicao",
}

EVENT_ALIASES = {
    "humor": "humor_visual", "humor visual": "humor_visual",
    "zoeira": "humor_visual", "dialogue": "dialogo",
    "conversa": "dialogo", "fala": "dialogo",
    "acao": "clutch", "ação": "clutch", "combat": "clutch",
    "luta": "teamfight", "team fight": "teamfight",
    "survival": "sobrevivencia", "desafio": "sobrevivencia",
    "corrida": "competicao", "esporte": "competicao",
}


def _normalize(label: str) -> str:
    if not isinstance(label, str):
        raise ValueError("Game/event must be text")
    label = unicodedata.normalize("NFKD", label)
    label = "".join(ch for ch in label if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", label.lower())).strip()


def style_for(game: str, event: str | None = None) -> EditorialStyle:
    """A stated event overrides the game. Unknown games are never rejected."""
    if event is not None and event.strip():
        event_key = _normalize(event)
        style = EVENT_ALIASES.get(event_key, event_key.replace(" ", "_"))
        if style not in STYLES:
            raise ValueError("Unknown event style: " + event[:60])
        return STYLES[style]
    return STYLES[GAME_DEFAULTS.get(_normalize(game), "narrativo")]


def _second(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(key + " must be a number of seconds")
    result = float(value)
    if not isfinite(result) or result < 0:
        raise ValueError(key + " must be finite and nonnegative")
    return result


def build_storyboard(
    game: str,
    beats: dict,
    *,
    event: str | None = None,
    replay: tuple[float, float] | None = None,
) -> dict:
    """Produce an editor-reviewed EDL suggestion; does not infer the beats.

    Beats are source times: setup < development < climax < [reaction] < end.
    A reaction is optional; the ending may be the payoff, with a hard cut.
    Replay source ranges can repeat past material after the story's climax.
    """
    if not isinstance(beats, dict):
        raise ValueError("Beats must be a mapping supplied by the editor")
    required = ("setup", "development", "climax", "end")
    if any(key not in beats for key in required):
        raise ValueError("Missing setup, development, climax or end timestamp")
    times = {k: _second(beats[k], k) for k in required}
    if "reaction" in beats and beats["reaction"] is not None:
        times["reaction"] = _second(beats["reaction"], "reaction")
        order = ("setup", "development", "climax", "reaction", "end")
    else:
        order = required
    if any(times[a] >= times[b] for a, b in zip(order, order[1:])):
        raise ValueError("Beats must follow source chronology")
    if times["end"] - times["setup"] > 600:
        raise ValueError("Review sequences over ten minutes in smaller sections")

    style = style_for(game, event)
    phase_names = {"setup": "contexto", "development": "desenrolar",
                   "climax": "climax", "reaction": "reacao"}
    phases = [
        {"phase": phase_names[a], "source_start": times[a], "source_end": times[b]}
        for a, b in zip(order, order[1:])
    ]
    warnings = []
    if times["development"] - times["setup"] < 3:
        warnings.append("Setup under 3s: verify the viewer understands the situation")
    if times["climax"] - times["setup"] < 10:
        warnings.append("Climax comes before 10s: verify the progression is intact")
    if "reaction" not in times:
        warnings.append("No reaction timestamp: review whether ending at payoff is best")

    chosen_replay = None
    if replay is not None:
        if not isinstance(replay, (tuple, list)) or len(replay) != 2:
            raise ValueError("Replay requires a source (start, end) pair")
        rs, re = (_second(replay[0], "replay_start"),
                  _second(replay[1], "replay_end"))
        if rs < times["setup"] or re > times["end"] or rs >= re:
            raise ValueError("Replay must be within the edited source")
        if re - rs > 5:
            warnings.append("Replay over 5s: shorten unless needed for comprehension")
        chosen_replay = {"source_start": rs, "source_end": re,
                         "when": "after climax, before final reaction",
                         "on_screen_label": None}
    return {
        "game": game.strip() or "Jogo não informado",
        "event_style": style.key,
        "rules": asdict(style),
        "phases": phases,
        "optional_replay": chosen_replay,
        "delivery": "9:16 H.264/AAC, contextual title in PT-BR, small source credit, hard cut",
        "manual_event_identification_required": True,
        "human_approval_required": True,
        "warnings": warnings,
    }
