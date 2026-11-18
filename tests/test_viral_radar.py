import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from clipforge import viral_radar as vr

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def clip(ident, broadcaster, views, *, lang="pt", title="Fuga insana da polícia", hours=1,
         duration=30, score=90, game="Grand Theft Auto VI", name=None):
    return {"id": ident, "broadcaster_id": broadcaster, "creator_name": name or f"Streamer{broadcaster}",
            "title": title, "url": f"https://clips.twitch.tv/{ident}", "view_count": views,
            "duration": duration, "score": score, "language": lang, "game_name": game,
            "created_at": (NOW - timedelta(hours=hours)).isoformat()}


class FakeTwitch:
    def __init__(self, items, profile="gta6_only"):
        self.items, self._profile = items, profile

    def profile(self, now=None):
        return {"profile": self._profile, "focus_game": "Grand Theft Auto VI"}

    def list_candidates(self, limit=100):
        return list(self.items)[:limit]


class ViralRadarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def runtime(self, items, profile="gta6_only"):
        return SimpleNamespace(twitch=FakeTwitch(items, profile), store=SimpleNamespace(root=self.root))

    def test_filters_viral_pt_and_marks_authorized(self):
        items = [clip("a", "1", 5000), clip("b", "2", 4000),
                 clip("c", "3", 9000, lang="en"),
                 clip("d", "1", 10, title="clip"),           # genérico e poucas views
                 clip("e", "4", 3000, game="Grand Theft Auto V")]
        vr.add_source(self.root, "1", "Streamer1", "permission_granted", "Editor na Twitch em 19/11")
        result = vr.radar(self.runtime(items), now=NOW)
        ids = [c["id"] for c in result["clips"]]
        self.assertEqual(ids, ["a", "b"])
        self.assertTrue(result["clips"][0]["authorized"])
        self.assertFalse(result["clips"][1]["authorized"])
        self.assertEqual(result["streamers"][0]["broadcaster_id"], "1")
        self.assertEqual(result["authorized_count"], 1)

    def test_all_languages_when_requested(self):
        items = [clip("a", "1", 5000), clip("c", "3", 9000, lang="en")]
        result = vr.radar(self.runtime(items), pt_only=False, now=NOW)
        self.assertEqual({c["id"] for c in result["clips"]}, {"a", "c"})

    def test_streamer_ranking_by_viral_clips(self):
        items = [clip("a", "1", 500), clip("b", "2", 800), clip("c", "2", 700, title="Explodiu tudo")]
        ranking = vr.radar(self.runtime(items), now=NOW)["streamers"]
        self.assertEqual(ranking[0]["broadcaster_id"], "2")
        self.assertEqual(ranking[0]["viral_clips"], 2)

    def test_add_source_validation(self):
        with self.assertRaises(ValueError):
            vr.add_source(self.root, "abc", "X", "permission_granted", "evidencia longa")
        with self.assertRaises(ValueError):
            vr.add_source(self.root, "1", "X", "permission_granted", "curta")
        with self.assertRaises(ValueError):
            vr.add_source(self.root, "1", "X", "public_clip", "evidencia longa")
        with self.assertRaises(ValueError):
            vr.add_source(self.root, "1", "", "owned", "")
        self.assertEqual(vr.authorized_ids(self.root), set())

    def test_add_update_remove_source_is_compatible_with_auto_ingest(self):
        vr.add_source(self.root, "77", "Alpha", "permission_granted", "DM no X em 19/11/2026")
        vr.add_source(self.root, "77", "Alpha2", "permission_granted", "Editor Twitch em 19/11/2026")
        data = json.loads((self.root / "twitch_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["broadcasters"]), 1)
        self.assertEqual(data["broadcasters"][0]["creator"], "Alpha2")
        from clipforge.twitch_auto import TwitchAutoIngest
        auto = TwitchAutoIngest(SimpleNamespace(store=SimpleNamespace(root=self.root)))
        self.assertEqual([s["broadcaster_id"] for s in auto._allowed_sources()], ["77"])
        self.assertTrue(vr.remove_source(self.root, "77"))
        self.assertFalse(vr.remove_source(self.root, "77"))
        self.assertEqual(auto._allowed_sources(), [])

    def test_auto_ingest_accepts_legacy_name_field(self):
        (self.root / "twitch_sources.json").write_text(json.dumps({"broadcasters": [
            {"id": "9", "name": "Legacy", "rights_status": "permission_granted",
             "evidence": "acordo assinado 2026"}]}), encoding="utf-8")
        from clipforge.twitch_auto import TwitchAutoIngest
        auto = TwitchAutoIngest(SimpleNamespace(store=SimpleNamespace(root=self.root)))
        self.assertEqual(auto._allowed_sources()[0]["creator"], "Legacy")


if __name__ == "__main__":
    unittest.main()
