"""Twitch metadata discovery tests: no tokens, network, or video downloads."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from clipforge.twitch import TwitchClient, TwitchDiscovery, TwitchError, clip_score, twitch_clip_url


def clip(clip_id="abc", broadcaster_id="1234", views=1200, language="en"):
    return {
        "id": clip_id, "broadcaster_id": broadcaster_id,
        "broadcaster_name": "Creator XYZ", "title": "A funny game moment",
        "url": "https://clips.twitch.tv/FunnyClip123",
        "view_count": views, "duration": 34.5, "language": language,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class DummyClient:
    def __init__(self, records):
        self.records = records
        self.requested_game = None
        self.categories_requested = None
        self.requested_lookback = None

    def get_top_categories(self, limit=30):
        self.categories_requested = limit
        return [{"id": "123456", "name": "Grand Theft Auto V"}]

    def get_clips(self, game_id, lookback_hours=72, first=15):
        self.requested_game = game_id
        self.requested_lookback = lookback_hours
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
            "TWITCH_GAME_ID": "", "TWITCH_ENABLED": "0",
            "TWITCH_TRENDING_CATEGORIES": "30",
            "TWITCH_CLIPS_PER_CATEGORY": "15",
            "TWITCH_LOOKBACK_HOURS": "72",
            # Official launch is midnight Nov 19 in São Paulo.
            "TWITCH_GTA6_LAUNCH_AT": "2026-11-19T03:00:00+00:00",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_score_favors_views_and_recency(self):
        now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        fresh = clip(views=1000)
        fresh["created_at"] = now.isoformat()
        old = dict(fresh, created_at=(now-timedelta(days=10)).isoformat())
        popular = dict(fresh, view_count=50000)
        self.assertGreater(clip_score(fresh, now), clip_score(old, now))
        self.assertGreaterEqual(clip_score(popular, now), clip_score(fresh, now))

    def test_portuguese_priority_is_not_exclusion(self):
        now = datetime.now(timezone.utc)
        en = clip(views=1000, language="en")
        pt = dict(en, language="pt-BR")
        self.assertGreater(clip_score(pt, now), clip_score(en, now))
        self.assertGreater(clip_score(en, now), 0)

    def test_clip_url_rejects_untrusted_sites(self):
        self.assertTrue(twitch_clip_url("https://clips.twitch.tv/FunnyClip123"))
        self.assertFalse(twitch_clip_url("javascript:alert(1)"))
        self.assertFalse(twitch_clip_url("https://clips.twitch.tv.fake.example/test"))
        self.assertFalse(twitch_clip_url("http://clips.twitch.tv/clip"))

    def test_missing_credentials_is_explicit(self):
        discovery = TwitchDiscovery(self.db, self.lock, self.root)
        self.assertFalse(discovery.status()["configured"])
        with self.assertRaisesRegex(TwitchError, "TWITCH_CLIENT_ID"):
            discovery.refresh()

    def test_readonly_metadata_ranking_and_dedupe(self):
        api = DummyClient([clip("alpha"),clip("beta",views=12000)])
        discovery = TwitchDiscovery(self.db,self.lock,self.root,api)
        result = discovery.refresh()
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"],"global_trending")
        self.assertEqual(result["processed"],2)
        self.assertEqual(api.requested_game,"123456")
        self.assertEqual(api.categories_requested,30)
        self.assertEqual(api.requested_lookback,72)
        items = discovery.list_candidates()
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]["id"],"beta")
        self.assertEqual(items[0]["consent_flag"],"unverified")
        self.assertEqual(discovery.status()["count"],2)
        discovery.refresh()
        self.assertEqual(discovery.status()["count"],2)
        self.assertEqual(list(self.root.glob("*.mp4")),[])

    def test_permission_label_is_declarative(self):
        manifest = {"broadcasters":[{"id":"1234","rights_status":"permission_granted",
            "evidence":"signed agreement 2026-11-13"}]}
        (self.root/"twitch_sources.json").write_text(json.dumps(manifest),encoding="utf-8")
        discovery = TwitchDiscovery(self.db,self.lock,self.root,DummyClient([clip()]))
        discovery.refresh()
        self.assertEqual(discovery.list_candidates()[0]["consent_flag"],"declared_permission")

    def test_permission_without_evidence_is_unverified(self):
        manifest = {"broadcasters":[{"id":"1234","rights_status":"permission_granted",
            "evidence":"no"}]}
        (self.root/"twitch_sources.json").write_text(json.dumps(manifest),encoding="utf-8")
        discovery = TwitchDiscovery(self.db,self.lock,self.root,DummyClient([clip()]))
        discovery.refresh()
        self.assertEqual(discovery.list_candidates()[0]["consent_flag"],"unverified")

    def test_non_twitch_video_urls_ignored(self):
        forged = dict(clip(),url="https://attack.example/malware.mp4")
        discovery = TwitchDiscovery(self.db,self.lock,self.root,DummyClient([forged]))
        self.assertEqual(discovery.refresh()["processed"],0)
        self.assertEqual(discovery.list_candidates(),[])

    def test_upgrade_preserves_legacy_database_and_all_categories(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("""CREATE TABLE twitch_candidates (
                id TEXT PRIMARY KEY, broadcaster_id TEXT NOT NULL,
                creator_name TEXT, title TEXT, url TEXT,
                view_count INTEGER NOT NULL, duration REAL NOT NULL,
                created_at TEXT, score INTEGER NOT NULL,
                consent_flag TEXT NOT NULL, seen_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE twitch_sync (
                id INTEGER PRIMARY KEY CHECK(id=1), last_at TEXT,
                last_error TEXT, game_id TEXT
            )""")
            seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute("""INSERT INTO twitch_candidates VALUES
                (?,?,?,?,?,?,?,?,?,?,?)""", ("legacy","123","Streamer","Old clip",
                 "https://clips.twitch.tv/FunnyClip123",1,30,
                 seen_at,20,"unverified",seen_at))
            db.commit()
        discovery = TwitchDiscovery(self.db,self.lock,self.root,DummyClient([]))
        with closing(sqlite3.connect(self.db)) as db:
            cols = {col[1] for col in db.execute("PRAGMA table_info(twitch_candidates)")}
            self.assertTrue({"game_id","game_name","language"}.issubset(cols))
            self.assertEqual(db.execute("SELECT count(*) FROM twitch_candidates").fetchone()[0],1)
        self.assertEqual(discovery.status()["count"],1)
        self.assertEqual(discovery.list_candidates()[0]["id"],"legacy")

    def test_global_until_midnight_sao_paulo_then_gta6_only(self):
        discovery = TwitchDiscovery(self.db,self.lock,self.root)
        before = datetime(2026,11,19,2,59,59,tzinfo=timezone.utc)
        start = datetime(2026,11,19,3,tzinfo=timezone.utc)
        for when in (datetime(2026,11,13,tzinfo=timezone.utc), before):
            self.assertEqual(discovery.profile(when)["profile"],"global_trending")
            self.assertIsNone(discovery.profile(when)["focus_game"])
        for when in (start, datetime(2027,1,1,tzinfo=timezone.utc)):
            self.assertEqual(discovery.profile(when)["profile"],"gta6_only")
            self.assertEqual(discovery.profile(when)["focus_game"],"Grand Theft Auto VI")

    def test_invalid_launch_override_still_switches_on_official_day(self):
        with patch.dict(os.environ, {"TWITCH_GTA6_LAUNCH_AT":"not-a-date"}):
            discovery = TwitchDiscovery(self.db,self.lock,self.root)
            self.assertEqual(discovery.profile(
                datetime(2026,11,19,3,tzinfo=timezone.utc))["profile"],"gta6_only")
        with patch.dict(os.environ, {"TWITCH_GTA6_LAUNCH_AT":"2027-01-01T03:00:00+00:00"}):
            discovery = TwitchDiscovery(self.db,self.lock,self.root)
            self.assertEqual(discovery.profile(
                datetime(2026,11,19,3,tzinfo=timezone.utc))["profile"],"global_trending")

    def test_multiple_categories_and_streamers_are_not_filtered(self):
        class MixedClient(DummyClient):
            def get_top_categories(self,limit=30):
                return [
                    {"id":"11","name":"Just Chatting"},
                    {"id":"22","name":"Minecraft"},
                    {"id":"33","name":"Grand Theft Auto V"},
                    {"id":"44","name":"IRL"},
                ]
            def get_clips(self, game_id, lookback_hours=72, first=15):
                return [clip("mixed-"+game_id, broadcaster_id=game_id,
                             views=1000+int(game_id),language="pt" if game_id=="44" else "en")]
        discovery = TwitchDiscovery(self.db,self.lock,self.root,MixedClient([]))
        result = discovery.refresh()
        self.assertEqual(result["profile"],"global_trending")
        self.assertEqual(result["received"],4)
        self.assertIsNone(result["game_id"])
        self.assertEqual(set(result["categories"]),{"Just Chatting","Minecraft","Grand Theft Auto V","IRL"})
        self.assertEqual({x["game_name"] for x in discovery.list_candidates()},set(result["categories"]))
        self.assertEqual(discovery.status()["count"],4)
        self.assertIn("language",discovery.list_candidates()[0])

    def test_switch_hides_old_games_and_queries_only_gta6(self):
        class MixedClient(DummyClient):
            def find_gta6_game(self):
                return "777"
            def get_top_categories(self,limit=30):
                return [{"id":"11","name":"Just Chatting"},
                        {"id":"22","name":"League of Legends"}]
            def get_clips(self,game_id,lookback_hours=72,first=15):
                self.requested_game = game_id
                return [clip("clip-"+game_id, broadcaster_id=game_id)]
        fake = MixedClient([])
        discovery = TwitchDiscovery(self.db,self.lock,self.root,fake)
        discovery.refresh()
        self.assertEqual(discovery.status()["count"],2)
        self.assertEqual(len(discovery.list_candidates()),2)
        with patch.dict(os.environ,{"TWITCH_GTA6_LAUNCH_AT":"2026-01-01T00:00:00+00:00"}):
            self.assertEqual(discovery.status()["count"],0)
            self.assertEqual(discovery.list_candidates(),[])
            result = discovery.refresh()
            self.assertEqual(result["profile"],"gta6_only")
            self.assertEqual(result["game_id"],"777")
            self.assertEqual(result["categories"],["Grand Theft Auto VI"])
            self.assertEqual(fake.requested_game,"777")
            self.assertEqual(discovery.status()["count"],1)
            self.assertEqual({x["game_name"] for x in discovery.list_candidates()},
                             {"Grand Theft Auto VI"})

    def test_lookup_gta6_category_exact_only(self):
        client = TwitchClient("id","secret")
        with patch.object(client,"_get",return_value={"data":[
            {"id":"11","name":"Grand Theft Auto V"},
            {"id":"12","name":"Grand Theft Auto VI"}]}):
            self.assertEqual(client.find_gta6_game(),"12")
        with patch.object(client,"_get",return_value={"data":[
            {"id":"11","name":"Grand Theft Auto V"}]}):
            with self.assertRaisesRegex(TwitchError,"not yet available"):
                client.find_gta6_game()

    def test_top_categories_are_bounded_not_whitelisted(self):
        client = TwitchClient("id","secret")
        with patch.object(client,"_get",return_value={"data":[
            {"id":"1","name":"Just Chatting"},
            {"id":"2","name":"Minecraft"},
            {"id":"not_number","name":"Invalid"},
        ]}) as request:
            result = client.get_top_categories()
        self.assertEqual([x["name"] for x in result],["Just Chatting","Minecraft"])
        request.assert_called_once_with("games/top",{"first":30})

    def test_configurable_limits_capped_for_twitch_quotas(self):
        with patch.dict(os.environ,{
            "TWITCH_TRENDING_CATEGORIES":"500",
            "TWITCH_CLIPS_PER_CATEGORY":"999",
            "TWITCH_LOOKBACK_HOURS":"999"
        }):
            settings = TwitchDiscovery(self.db,self.lock,self.root).profile()
            self.assertEqual(settings["category_limit"],100)
            self.assertEqual(settings["clips_per_category"],30)
            self.assertEqual(settings["lookback_hours"],168)
        with patch.dict(os.environ,{"TWITCH_TRENDING_CATEGORIES":"bad"}):
            self.assertEqual(TwitchDiscovery(self.db,self.lock,self.root).profile()["category_limit"],30)


if __name__=="__main__":
    unittest.main()
