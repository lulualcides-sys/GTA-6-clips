"""Review gate for genuine streamer facecam + on-source reaction.

Never infer reactions from an audio spike or invent a facecam. The editor
must inspect the original media and supply observed source timestamps.
This gate does not automatically recognize faces.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReactionReview:
    source_url: str
    creator: str
    duration: float
    facecam_visible: bool
    same_source_facecam: bool
    facecam_region: tuple[int, int, int, int] | None
    reaction_start: float | None
    reaction_end: float | None
    setup_start: float
    payoff_start: float
    end: float
    verified_by_editor: bool

    def validate(self) -> dict:
        errors = []
        duration = self.duration
        if not math.isfinite(duration) or duration <= 0:
            errors.append("Source duration must be positive")
        if not self.verified_by_editor:
            errors.append("Facecam and reaction require visual editorial inspection")
        if not self.facecam_visible:
            errors.append("No visible streamer camera: reject")
        if not self.same_source_facecam:
            errors.append("Do not reuse a facecam or reaction from another recording")
        if not self.facecam_region or len(self.facecam_region) != 4 or any(
            not isinstance(v, int) or isinstance(v, bool) for v in self.facecam_region
        ) or any(v < 0 for v in (self.facecam_region or ())) or (
            self.facecam_region and (self.facecam_region[2] == 0 or self.facecam_region[3] == 0)
        ):
            errors.append("Facecam position requires a real rectangle in original pixels")
        times = (self.setup_start, self.payoff_start, self.end,
                 self.reaction_start, self.reaction_end)
        if any(v is None or isinstance(v, bool) or not isinstance(v, (float, int))
               or not math.isfinite(v) for v in times):
            errors.append("All story and reaction timestamps are required and finite")
        elif not (0 <= self.setup_start < self.payoff_start <= self.reaction_start
                  < self.reaction_end <= self.end <= duration + 0.10):
            errors.append("Preserve setup, payoff, source reaction and ending in order")
        if not self.creator.strip() or not self.source_url.startswith("https://clips.twitch.tv/"):
            errors.append("Require creator and source Twitch URL")
        return {
            "eligible_for_editorial_preview": not errors,
            "reasons": errors,
            "evidence": asdict(self),
            "automatically_verified": False,
            "social_republication_authorized": False,
        }
