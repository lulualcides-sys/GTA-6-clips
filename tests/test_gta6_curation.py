"""GTA VI wide discovery and conservative pre-download candidate screening."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from clipforge.curation import normalized_title, qualifies, ranked_shortlist
from clipforge.twitch import TwitchClient


class PagedDiscoveryTests(unittest.TestCase):
    def test_official_cursor_pages_time_windows_and_dedupe(self):
        client = TwitchClient("id", "secret")
        requests = []
        def request(endpoint, params):
            self.assertEqual(endpoint, "clips")
            self.assertEqual(params["first"], 100)
            self.assertEqual(params["game_id"], "987")
            requests.append(dict(params))
            if "after" in params:
                return {"data": [{"id": "duplicate", "view_count": 200}],
                        "pagination": {}}
            return {"data": [
                {"id": params["started_at"] + "-first", "view_count": 1000},
                {"id": "duplicate", "view_count": 200},
            ], "pagination": {"cursor": "next"}}
        with patch.object(client, "_get", side_effect=request):
            clips = client.get_game_clips_paged(
                "987", lookback_hours=24, window_hours=12, pages_per_window=3)
        self.assertEqual(len(requests), 4)
        self.assertEqual(len(clips), 3)
        self.assertEqual(len({c["id"] for c in clips}), 3)

    def test_page_budget_and_repeated_cursor_are_bounded(self):
        client = TwitchClient("id", "secret")
        seen = []
        def page(endpoint, params):
            seen.append(dict(params))
            return {"data": [{"id": str(len(seen))}],
                    "pagination": {"cursor": "same-cursor"}}
        with patch.object(client, "_get", side_effect=page):
            clips = client.get_game_clips_paged(
                "123", lookback_hours=48, window_hours=1,
                pages_per_window=8, request_budget=5)
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(clips), 5)

    def test_invalid_game_id_rejected(self):
        from clipforge.twitch import TwitchError
        with self.assertRaises(TwitchError):
            TwitchClient("id", "secret").get_game_clips_paged("../invalid")


class EditorialCurationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.common = {
            "id": "one", "broadcaster_id": "10",
            "game_name": "Grand Theft Auto VI",
            "title": "Ele caiu da moto e o streamer perdeu tudo",
            "view_count": 5000, "duration": 35, "score": 94,
            "created_at": (self.now - timedelta(hours=1)).isoformat(),
        }

    def test_good_clip_passes_and_irrelevant_game_does_not(self):
        self.assertTrue(qualifies(self.common, now=self.now))
        self.assertFalse(qualifies({**self.common, "game_name": "GTA V"}, now=self.now))

    def test_low_effort_title_and_low_engagement_rejected(self):
        self.assertFalse(qualifies({**self.common, "title": "CLIP"}, now=self.now))
        self.assertFalse(qualifies({**self.common, "view_count": 1}, now=self.now))
        self.assertFalse(qualifies({**self.common, "score": 55}, now=self.now))
        self.assertFalse(qualifies({**self.common, "duration": 4}, now=self.now))
        self.assertFalse(qualifies({**self.common, "duration": 120}, now=self.now))

    def test_creator_diversity_and_repeated_title(self):
        clips = [
            dict(self.common),
            {**self.common, "id": "two", "score": 90,
             "title": "Ele caiu da moto e o streamer perdeu tudo"},
            {**self.common, "id": "three", "score": 88,
             "title": "Capotou e saiu voando"},
            {**self.common, "id": "four", "score": 82,
             "title": "Explosão inacreditável"},
            {**self.common, "id": "five", "broadcaster_id": "20", "score": 81,
             "title": "Capotou e saiu voando"},
        ]
        shortlist = ranked_shortlist(clips, min_score=78,
                                     per_creator=2, now=self.now)
        self.assertEqual([c["id"] for c in shortlist], ["one", "three", "five"])

    def test_new_clips_get_appropriate_view_threshold(self):
        fresh = {**self.common, "view_count": 40}
        older = {**fresh,
                 "created_at": (self.now - timedelta(days=2)).isoformat()}
        self.assertTrue(qualifies(fresh, now=self.now))
        self.assertFalse(qualifies(older, now=self.now))

    def test_titles_normalize_accents_without_changing_text(self):
        self.assertEqual(normalized_title("  CLÍPE!!!  "), "clipe")


if __name__ == "__main__":
    unittest.main()
