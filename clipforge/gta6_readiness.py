"""GTA V training cuts for GTA VI editorial launch readiness.

Rockstar has confirmed the setting, characters, and overall criminal story.
These templates are EDITORIAL HYPOTHESES, not claims of GTA VI mechanics.

This module only plans story beats supplied by a human editor. It does not
scan footage, infer events, render a video, connect Twitch or publish clips.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import unicodedata
from typing import Mapping

from clipforge.editorial_profiles import build_storyboard


@dataclass(frozen=True)
class GTAEditingScenario:
    key: str
    source_basis: str
    gta5_training: str
    gta6_opportunity: str
    storyboard_style: str
    screen_focus: str
    audio: str
    title_rule: str
    replay_rule: str


# source_basis means an OFFICIAL narrative, setting or depiction supports the
# topic's relevance. It does not assert that a particular mechanic exists.
# A planned edit must be judged from a real clip, not from the expected topic.
SCENARIOS: dict[str, GTAEditingScenario] = {
    "perseguicao": GTAEditingScenario(
        "perseguicao", "editorial_transfer",
        "GTA V police or player chase with a clear beginning and a real escape/crash",
        "Road pursuit and escape moments if actually present in GTA VI gameplay",
        "narrativo", "Follow moving vehicle, road hazards and minimap when essential",
        "Preserve engine, collision, sirens and natural streamer reaction",
        "Identify the risk without revealing the outcome in advance",
        "Short only if crash/escape benefits from a second view",
    ),
    "assalto": GTAEditingScenario(
        "assalto", "official_crime_story",
        "GTA V heist with planning, execution, setback and outcome",
        "Criminal schemes and a job going wrong in Jason/Lucia's official story",
        "narrativo", "Show objective, accomplices, threat and escape path",
        "Balance real dialogue and in-game action; no generic fake alarm",
        "State the objective or stakes, not invented mission names",
        "Only after action if decisive failure/success is visually clear",
    ),
    "dupla": GTAEditingScenario(
        "dupla", "official_jason_lucia",
        "GTA V two-player teamwork, betrayal or misunderstanding with visible context",
        "Jason and Lucia's official partnership and interaction scenes",
        "dialogo", "Keep both relevant characters and reaction visible",
        "Preserve each speaker; translate only verified speech faithfully",
        "Setup a conflict without fabricating dialogue or character actions",
        "Usually none; preserve conversational rhythm",
    ),
    "humor": GTAEditingScenario(
        "humor", "editorial_transfer",
        "GTA V physics, unexpected NPC interaction or a stunt with clear setup",
        "Unexpected GTA VI situations only if supported by actual footage",
        "humor_visual", "Show cause, unexpected result and visible reaction",
        "Keep authentic laughter, timing and impact sounds",
        "One natural short Brazilian hook; avoid explanatory text wall",
        "Optional brief repeat after payoff, no on-screen REPLAY label",
    ),
    "viral": GTAEditingScenario(
        "viral", "official_social_media_setting",
        "GTA V roleplay or a strange street scene understandable without inside jokes",
        "Social-media-flavored moments if they occur in real GTA VI footage",
        "humor_visual", "Focus on the incident and whoever reacts; preserve visual context",
        "Original dialogue/streamer reaction, never imitate a fake live",
        "Describe the actual moment; do not fabricate a viral post or UI",
        "Optional if second viewing improves the joke",
    ),
    "exploracao": GTAEditingScenario(
        "exploracao", "official_leonida_setting",
        "GTA V discovering an unusual place, character, animal or hidden scene",
        "Vice City and Leonida locations/encounters showcased by Rockstar",
        "sobrevivencia", "Prioritize setting, detail being discovered, scale and reaction",
        "Preserve ambience and genuine surprise rather than generic suspense",
        "Name a real location only when independently verified",
        "Normally none; let the reveal unfold",
    ),
    "dialogo_rp": GTAEditingScenario(
        "dialogo_rp", "editorial_transfer",
        "GTA V RP conversation with a premise, response and punchline",
        "GTA VI dialogue/reaction cuts if suitable real material exists",
        "dialogo", "Readable facecam(s) and speaker identification without giant banners",
        "Protect intelligibility; accurate PT-BR captions only if necessary",
        "Do not replace the conversation with clickbait text",
        "Avoid unless essential to the joke",
    ),
}

# Avoid claiming that future game footage, RP multiplayer, in-game social
# posting, police systems or new physics mechanics are confirmed.
_OFFICIAL_EVIDENCE = {
    "official_crime_story": (
        "https://www.rockstargames.com/br/newswire/article/517572321a549a/"
        "watch-the-grand-theft-auto-vi-launch-trailer"
    ),
    "official_jason_lucia": "https://www.rockstargames.com/VI",
    "official_social_media_setting": (
        "https://www.rockstargames.com/VI/only-in-leonida/vice-city"
    ),
    "official_leonida_setting": "https://www.rockstargames.com/VI",
}


def available_scenarios() -> list[dict]:
    """Export a bounded, stable catalogue for UI or editorial documentation."""
    return [asdict(s) | {"evidence_url": _OFFICIAL_EVIDENCE.get(s.source_basis)}
            for s in SCENARIOS.values()]


def _game_key(game: str) -> str:
    if not isinstance(game, str):
        raise ValueError("game must be a string")
    normalized = unicodedata.normalize("NFKD", game)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.lower().split())
    if normalized in ("gta 5", "gta v", "grand theft auto v", "grand theft auto 5", "gta rp"):
        return "gta5"
    if normalized in ("gta 6", "gta vi", "grand theft auto vi", "grand theft auto 6"):
        return "gta6"
    raise ValueError("Use a GTA V or GTA VI source, not an unrelated game")


def plan_gta_clip(game: str, scenario: str, beats: Mapping,
                  *, replay: tuple[float, float] | None = None) -> dict:
    """Build an edit recommendation with actual timestamps supplied by the editor."""
    game_key = _game_key(game)
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError("Unknown GTA scenario: select an existing editorial scenario")
    spec = SCENARIOS[scenario]
    plan = build_storyboard(
        game, dict(beats), event=spec.storyboard_style, replay=replay
    )
    plan.update({
        "gta_source": game_key,
        "scenario": scenario,
        "scenario_guidance": asdict(spec),
        "official_evidence_url": _OFFICIAL_EVIDENCE.get(spec.source_basis),
        "gta6_mechanics_confirmed": False,
        "scene_selection_manual": True,
        "check_source_rights_before_publication": True,
        "approved_v8_quality_reference_only": True,
        "must_preserve": [
            "contexto", "desenrolar", "climax", "reacao quando existir",
            "Nexus Clips BR pequena marca", "creditos discretos",
            "audio real", "corte seco", "player web sem download",
        ],
    })
    return plan
