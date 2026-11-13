"""Produce a reviewable game-aware edit plan, not a rendered clip.

Example:
python -m tools.editorial_plan --game "Rocket League" \
  --beats '{"setup":0,"development":8,"climax":25,"reaction":33,"end":40}'
"""
from __future__ import annotations

import argparse
import json

from clipforge.editorial_profiles import build_storyboard


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nexus Clips BR storyboard for manual review")
    parser.add_argument("--game", required=True, help="Game/category title")
    parser.add_argument("--event", help="Optional incident type; overrides the game preset")
    parser.add_argument("--beats", required=True,
                        help="JSON timestamps: setup, development, climax, optional reaction, end")
    parser.add_argument("--replay", nargs=2, type=float, metavar=("START", "END"),
                        help="Optional manually selected replay source window")
    args = parser.parse_args(argv)
    try:
        beats = json.loads(args.beats)
        result = build_storyboard(args.game, beats, event=args.event,
                                  replay=tuple(args.replay) if args.replay else None)
    except (json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
