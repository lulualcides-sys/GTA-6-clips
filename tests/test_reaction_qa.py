import unittest
from dataclasses import replace
from clipforge.reaction_qa import ReactionReview

BASE=ReactionReview(
    source_url="https://clips.twitch.tv/example",
    creator="streamer",
    duration=30.0,
    facecam_visible=True,
    same_source_facecam=True,
    facecam_region=(0, 30, 350, 250),
    reaction_start=20.0,
    reaction_end=23.0,
    setup_start=0.0,
    payoff_start=18.0,
    end=26.0,
    verified_by_editor=True,
)

class ReactionQATests(unittest.TestCase):
    def test_genuine_in_source_reaction_passes_manual_gate(self):
        result=BASE.validate()
        self.assertTrue(result["eligible_for_editorial_preview"])
        self.assertFalse(result["automatically_verified"])

    def test_no_camera_fails(self):
        r=replace(BASE,facecam_visible=False).validate()
        self.assertFalse(r["eligible_for_editorial_preview"])
        self.assertIn("No visible streamer camera", " ".join(r["reasons"]))

    def test_borrowed_camera_fails(self):
        r=replace(BASE,same_source_facecam=False).validate()
        self.assertFalse(r["eligible_for_editorial_preview"])

    def test_no_verified_reaction_fails(self):
        for change in (
            {"verified_by_editor":False},
            {"reaction_start":None},
            {"reaction_start":31},
            {"reaction_start":13},
            {"reaction_end":20},
            {"end":31},
        ):
            with self.subTest(change=change):
                self.assertFalse(replace(BASE,**change).validate()["eligible_for_editorial_preview"])

    def test_missing_camera_region_fails(self):
        for region in (None,(0,0,0,180),(0,0,-4,100)):
            self.assertFalse(replace(BASE,facecam_region=region).validate()["eligible_for_editorial_preview"])

    def test_social_permission_not_inferred(self):
        self.assertFalse(BASE.validate()["social_republication_authorized"])

if __name__=="__main__":
    unittest.main()
