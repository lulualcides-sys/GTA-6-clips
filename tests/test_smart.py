import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipforge.smart import scene_aware_start, choose_smart_highlight, find_cuts


class SmartSelectionTests(unittest.TestCase):
    def test_scene_cut_never_exceeds_video_bounds(self):
        start = scene_aware_start(94, total=110, length=30, cuts=[20, 79, 103])
        self.assertLessEqual(start, 80)
        self.assertGreaterEqual(start, 0)

    def test_no_cuts_uses_audio_only(self):
        self.assertEqual(scene_aware_start(28.5, 120, 30, []), 28.5)

    def test_scene_offset_conservative(self):
        start = scene_aware_start(27, 120, 30, [25, 28, 36])
        self.assertLessEqual(abs(start-27), 10)

    def test_default_flag_does_not_load_scene_detector(self):
        with patch.dict(os.environ, {"SMART_SCENES":"0"}), \
             patch("clipforge.core.choose_highlight", return_value=20), \
             patch("clipforge.smart.find_cuts") as finder:
            start, details = choose_smart_highlight(Path("unused.mp4"), 120, 35)
        self.assertEqual(start, 20)
        self.assertEqual(details["method"], "audio")
        finder.assert_not_called()

    def test_scene_mode_uses_bounded_cut_scan(self):
        with patch.dict(os.environ, {"SMART_SCENES":"1"}), \
             patch("clipforge.core.choose_highlight", return_value=20), \
             patch("clipforge.smart.find_cuts", return_value=[18, 35]) as finder:
            start, details = choose_smart_highlight(Path("unused.mp4"), 120, 35)
        self.assertTrue(0 <= start <= 85)
        self.assertEqual(details["method"],"audio+scene-boundaries")
        self.assertEqual(details["cuts"],2)
        self.assertEqual(finder.call_args.kwargs["limit_seconds"],120)

    def test_missing_package_or_decode_does_not_crash(self):
        with patch("builtins.__import__", side_effect=ImportError):
            self.assertEqual(find_cuts(Path("nonexistent.mp4")), [])


if __name__=="__main__":
    unittest.main()
