"""Proof that GTA VI editorial readiness depends on actual source context."""
import unittest

from clipforge.gta6_readiness import SCENARIOS, available_scenarios, plan_gta_clip

BEATS = {"setup": 3, "development": 14, "climax": 36,
         "reaction": 44, "end": 50}


class GTAReadinessTests(unittest.TestCase):
    def test_all_scenarios_available_and_distinct(self):
        self.assertEqual(len(SCENARIOS), 7)
        self.assertEqual(len({x["key"] for x in available_scenarios()}), 7)

    def test_gta5_training_maps_to_gta6_editorial_scenarios(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                pre = plan_gta_clip("Grand Theft Auto V", scenario, BEATS)
                post = plan_gta_clip("GTA VI", scenario, BEATS)
                self.assertEqual(pre["scenario"], post["scenario"])
                self.assertEqual(pre["gta_source"], "gta5")
                self.assertEqual(post["gta_source"], "gta6")
                self.assertEqual(pre["event_style"], post["event_style"])
                self.assertEqual(len(pre["phases"]), 4)

    def test_story_structure_is_not_cut_to_only_the_payoff(self):
        for event in ("perseguicao", "assalto", "dupla", "humor", "viral", "exploracao", "dialogo_rp"):
            plan = plan_gta_clip("GTA V", event, BEATS)
            self.assertEqual([p["phase"] for p in plan["phases"]],
                             ["contexto", "desenrolar", "climax", "reacao"])
            self.assertEqual(plan["phases"][0]["source_start"], 3)
            self.assertEqual(plan["phases"][-1]["source_end"], 50)

    def test_gta5_rp_dialogue_keeps_actual_speech(self):
        plan = plan_gta_clip("GTA RP", "dialogo_rp", BEATS)
        self.assertEqual(plan["event_style"], "dialogo")
        self.assertIn("accurate PT-BR captions", plan["scenario_guidance"]["audio"])
        self.assertIsNone(plan["optional_replay"])

    def test_crime_and_characters_grounded_but_not_mechanics(self):
        crime = plan_gta_clip("GTA VI", "assalto", BEATS)
        duo = plan_gta_clip("GTA VI", "dupla", BEATS)
        self.assertIn("rockstargames.com", crime["official_evidence_url"])
        self.assertIn("rockstargames.com", duo["official_evidence_url"])
        self.assertFalse(crime["gta6_mechanics_confirmed"])
        self.assertTrue(crime["scene_selection_manual"])
        self.assertTrue(crime["check_source_rights_before_publication"])

    def test_assumed_mechanics_not_misrepresented_as_confirmed(self):
        for scenario in ("perseguicao", "humor", "dialogo_rp"):
            result = plan_gta_clip("GTA VI", scenario, BEATS)
            self.assertIsNone(result["official_evidence_url"])
            self.assertEqual(result["scenario_guidance"]["source_basis"], "editorial_transfer")

    def test_replay_optional_and_unlabeled(self):
        result = plan_gta_clip("GTA V", "humor", BEATS, replay=(35, 37))
        self.assertIsNone(result["optional_replay"]["on_screen_label"])
        self.assertEqual(result["optional_replay"]["source_end"], 37)

    def test_invalid_source_and_scenario_rejected(self):
        for game in ("Minecraft", "", 99):
            with self.subTest(game=game):
                with self.assertRaises(ValueError):
                    plan_gta_clip(game, "humor", BEATS)
        with self.assertRaises(ValueError):
            plan_gta_clip("GTA VI", "police_ai_confirmed", BEATS)

    def test_invalid_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "chronology"):
            plan_gta_clip("GTA VI", "assalto", {**BEATS, "climax": 2})

    def test_export_includes_evidence_and_editorial_focus(self):
        entries = available_scenarios()
        self.assertTrue(all("gta5_training" in s and "gta6_opportunity" in s
                            and "screen_focus" in s and "source_basis" in s
                            and "evidence_url" in s for s in entries))
        self.assertTrue(all("mechanic" not in s for s in entries))


if __name__ == "__main__":
    unittest.main()
