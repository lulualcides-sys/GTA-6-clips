"""No real Twitch tokens or network calls are needed for this suite."""
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from clipforge.twitch import (
    TwitchClient, TwitchDiscovery, TwitchError, clip_score, twitch_clip_url
)


def clip(clip_id="abc", broadcaster_id="1234", views=1200):
    return {
        "id": clip_id, "broadcaster_id": broadcaster_id,
        "broadcaster_name": "Creator XYZ", "title": "GTA 6 special moment",
        "url": "https://clips.twitch.tv/FunnyClip123",
        "view_count": views, "duration": 34.5,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
    }


class DummyClient:
    def __init__(self, records):
        self.records = records
        self.requested_game = None

    def find_gta6_game(self):
        return "123456"

    def get_clips(self, game_id):
        self.requested_game = game_id
        return self.records


class TwitchDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.db = self.root / "test.sqlite3"
        self.lock = threading.RLock()
        self.env = patch.dict(os.environ, {
            "TWITCH_CLIENT_ID": "", "TWITCH_CLIENT_SECRET": "",
            "TWITCH_GAME_ID": "", "TWITCH_ENABLED": "0"
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_score_favors_views_and_recency(self):
        now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        fresh = clip(views=1000)
        fresh["created_at"] = now.isoformat()
        old = dict(fresh, created_at=(now-timedelta(days=10)).isoformat())
        popular = dict(fresh, view_count=50000)
        self.assertGreater(clip_score(fresh,now),clip_score(old,now))
        self.assertGreaterEqual(clip_score(popular,now),clip_score(fresh,now))

    def test_clip_url_rejects_untrusted_sites(self):
        self.assertTrue(twitch_clip_url("https://clips.twitch.tv/FunnyClip123"))
        self.assertFalse(twitch_clip_url("javascript:alert(1)"))
        self.assertFalse(twitch_clip_url("https://clips.twitch.tv.fake.example/test"))
        self.assertFalse(twitch_clip_url("http://clips.twitch.tv/clip"))

    def test_missing_credentials_is_explicit(self):
        discovery=TwitchDiscovery(self.db,self.lock,self.root)
        self.assertFalse(discovery.status()["configured"])
        with self.assertRaisesRegex(TwitchError,"TWITCH_CLIENT_ID"):
            discovery.refresh()

    def test_readonly_metadata_ranking_and_dedupe(self):
        api=DummyClient([clip("alpha"),clip("beta",views=12000)])
        discovery=TwitchDiscovery(self.db,self.lock,self.root,api)
        result=discovery.refresh()
        self.assertTrue(result["ok"])
        self.assertEqual(result["processed"],2)
        self.assertEqual(api.requested_game,"123456")
        items=discovery.list_candidates()
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]["id"],"beta")
        self.assertEqual(items[0]["consent_flag"],"unverified")
        self.assertEqual(discovery.status()["count"],2)
        discovery.refresh()
        self.assertEqual(discovery.status()["count"],2)
        self.assertEqual(list(self.root.glob("*.mp4")),[])

    def test_permission_label_is_declarative(self):
        manifest = {
            "broadcasters": [{"id":"1234","rights_status":"permission_granted",
                              "evidence":"signed agreement 2026-11-13"}]
        }
        (self.root/"twitch_sources.json").write_text(json.dumps(manifest),encoding="utf-8")
        discovery=TwitchDiscovery(self.db,self.lock,self.root,DummyClient([clip()]))
        discovery.refresh()
        self.assertEqual(discovery.list_candidates()[0]["consent_flag"],"declared_permission")

    def test_permission_without_evidence_does_not_grant_flag(self):
        manifest={"broadcasters":[{"id":"1234","rights_status":"permission_granted",
                                    "evidence":"no"}]}
        (self.root/"twitch_sources.json").write_text(json.dumps(manifest),encoding="utf-8")
        discovery=TwitchDiscovery(self.db,self.lock,self.root,DummyClient([clip()]))
        discovery.refresh()
        self.assertEqual(discovery.list_candidates()[0]["consent_flag"],"unverified")

    def test_non_twitch_video_urls_ignored(self):
        forged=dict(clip(),url="https://attack.example/malware.mp4")
        discovery=TwitchDiscovery(self.db,self.lock,self.root,DummyClient([forged]))
        self.assertEqual(discovery.refresh()["processed"],0)
        self.assertEqual(discovery.list_candidates(),[])

    def test_category_must_be_exact(self):
        client=TwitchClient("id","secret")
        with patch.object(client,"_get",return_value={
            "data":[{"id":"1","name":"Grand Theft Auto V"},
                    {"id":"2","name":"Grand Theft Auto VI"}]
        }):
            self.assertEqual(client.find_gta6_game(),"2")
        with patch.object(client,"_get",return_value={
            "data":[{"id":"1","name":"Grand Theft Auto V"}]
        }):
            with self.assertRaisesRegex(TwitchError,"not yet available"):
                client.find_gta6_game()


if __name__=="__main__":
    unittest.main()
