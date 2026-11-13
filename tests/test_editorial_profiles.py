"""Event type controls the edit; a game's identity alone does not."""
import unittest

from clipforge.editorial_profiles import build_storyboard, style_for

BEATS = {"setup": 0.0, "development": 8.0, "climax": 24.0,
         "reaction": 34.0, "end": 39.0}


class EditorialProfileTests(unittest.TestCase):
    def test_game_defaults_are_different(self):
        cases = {
            "GTA V": "humor_visual", "GTA VI": "humor_visual",
            "GTA RP": "dialogo", "Minecraft": "sobrevivencia",
            "Counter-Strike 2": "clutch", "Fortnite": "clutch",
            "League of Legends": "teamfight",
            "Rocket League": "competicao",
        }
        for game, expected in cases.items():
            with self.subTest(game=game):
                self.assertEqual(style_for(game).key, expected)

    def test_event_override_is_more_important_than_game(self):
        self.assertEqual(style_for("GTA VI", "dialogo").key, "dialogo")
        self.assertEqual(style_for("Minecraft", "humor").key, "humor_visual")
        self.assertEqual(style_for("League of Legends", "clutch").key, "clutch")

    def test_unknown_game_falls_back_safely(self):
        self.assertEqual(style_for("New Game 9000").key, "narrativo")

    def test_unknown_event_rejected_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "Unknown event"):
            style_for("GTA V", "not-real")

    def test_four_beats_remain_ordered(self):
        plan = build_storyboard("CS2", BEATS)
        self.assertEqual(plan["event_style"], "clutch")
        self.assertEqual([x["phase"] for x in plan["phases"]],
                         ["contexto", "desenrolar", "climax", "reacao"])
        self.assertEqual(plan["phases"][-1]["source_end"], 39)
        self.assertTrue(plan["human_approval_required"])

    def test_timing_is_not_hardcoded_to_seven_seconds(self):
        long = {"setup": 10, "development": 22, "climax": 70,
                "reaction": 88, "end": 102}
        plan = build_storyboard("Rocket League", long)
        self.assertEqual(plan["phases"][-1]["source_end"], 102)
        self.assertEqual(plan["event_style"], "competicao")

    def test_final_can_be_the_payoff_with_no_reaction(self):
        short = {"setup": 0, "development": 3, "climax": 14, "end": 22}
        plan = build_storyboard("Minecraft", short)
        self.assertEqual([b["phase"] for b in plan["phases"]][-1], "climax")
        self.assertIn("No reaction timestamp", " ".join(plan["warnings"]))

    def test_replay_is_explicit_and_has_no_label(self):
        plan = build_storyboard("GTA V", BEATS, replay=(23.5, 25))
        self.assertIsNone(plan["optional_replay"]["on_screen_label"])
        self.assertEqual(plan["optional_replay"]["source_start"], 23.5)
        self.assertIsNone(build_storyboard("GTA V", BEATS)["optional_replay"])

    def test_replay_outside_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "within the edited source"):
            build_storyboard("GTA V", BEATS, replay=(24, 40))

    def test_out_of_order_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "chronology"):
            build_storyboard("Fortnite", {**BEATS, "development": 27})

    def test_missing_markers_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing"):
            build_storyboard("Fortnite", {"setup": 0, "end": 25})

    def test_nan_infinity_bool_and_negative_rejected(self):
        for value in (float("nan"), float("inf"), -1, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_storyboard("GTA V", {**BEATS, "climax": value})

    def test_short_structure_is_flagged_not_silently_approved(self):
        plan = build_storyboard("LoL", {"setup": 0, "development": 1,
                                          "climax": 4, "end": 7})
        self.assertEqual(len(plan["warnings"]), 3)

    def test_dialogue_is_not_fabricated(self):
        plan = build_storyboard("GTA RP", BEATS)
        self.assertIn("never fabricate speech", plan["rules"]["titles"])
        self.assertTrue(plan["manual_event_identification_required"])


if __name__ == "__main__":
    unittest.main()
