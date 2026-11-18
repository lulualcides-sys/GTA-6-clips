import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipforge import youtube_download as ytd
from clipforge import youtube_radar as yr
from clipforge.autoclip_bridge import AutoClipBridge
from clipforge.twitch_download import DownloadError
from clipforge.youtube_auto import YouTubeAutoIngest

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
CH_A = "UC" + "a" * 22
CH_B = "UC" + "b" * 22
CH_SMALL = "UC" + "c" * 22
MANIFEST = {"channel_id": CH_A, "creator": "Canal A", "rights_status": "permission_granted",
            "evidence": "Descrição do canal: cortes liberados"}


def video(vid, channel, *, views=500_000, hours=5, title="GTA 6 zerado ao vivo", duration="PT25M",
          live="none", lang="pt-BR", description=""):
    return {"id": vid, "snippet": {"channelId": channel, "channelTitle": "Canal " + channel[-1],
                                   "title": title, "publishedAt": (NOW - timedelta(hours=hours)).isoformat(),
                                   "liveBroadcastContent": live, "defaultAudioLanguage": lang,
                                   "description": description, "tags": []},
            "statistics": {"viewCount": str(views), "likeCount": str(views // 20), "commentCount": "900"},
            "contentDetails": {"duration": duration}}


def channel(ident, subs, description=""):
    return {"id": ident, "snippet": {"title": "Canal " + ident[-1], "description": description,
                                     "customUrl": "@canal" + ident[-1], "country": "BR"},
            "statistics": {"subscriberCount": str(subs)},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + ident[2:]}}}


class FakeClient:
    def __init__(self, popular, channels, uploads=None, searched=None):
        self.popular, self._channels = popular, {c["id"]: c for c in channels}
        self.uploads, self.searched = uploads or {}, searched or []
        self.calls = []

    def most_popular_gaming(self, region="BR", limit=50):
        self.calls.append("popular")
        return list(self.popular)

    def search_ids(self, query, published_after, region="BR", limit=25):
        self.calls.append(("search", query))
        return [v["id"] for v in self.searched]

    def videos(self, ids):
        pool = {v["id"]: v for v in self.popular + self.searched + sum(self.uploads.values(), [])}
        return [pool[i] for i in ids if i in pool]

    def channels(self, ids):
        return [self._channels[i] for i in ids if i in self._channels]

    def recent_upload_ids(self, uploads, limit=10):
        return [v["id"] for v in self.uploads.get(uploads, [])][:limit]


class MetadataTest(unittest.TestCase):
    def test_iso_duration(self):
        self.assertEqual(yr.iso_duration("PT1H2M3S"), 3723)
        self.assertEqual(yr.iso_duration("PT45S"), 45)
        self.assertEqual(yr.iso_duration("P1DT1S"), 86401)
        self.assertEqual(yr.iso_duration("garbage"), 0)

    def test_video_row_scores_and_flags(self):
        fast = yr.video_row(video("AAAAAAAAAAA", CH_A, views=900_000, hours=3), NOW)
        slow = yr.video_row(video("BBBBBBBBBBB", CH_A, views=9_000, hours=72, title="Minecraft", lang="en"), NOW)
        self.assertTrue(fast["gta6"] and fast["portuguese"])
        self.assertFalse(slow["gta6"] or slow["portuguese"])
        self.assertGreater(fast["score"], slow["score"])
        self.assertEqual(fast["duration"], 1500)
        self.assertIsNone(yr.video_row(video("bad", CH_A), NOW))

    def test_autoclip_filter_blocks_live_short_long_and_other_games(self):
        ok = yr.video_row(video("AAAAAAAAAAA", CH_A), NOW)
        self.assertTrue(yr.eligible_for_autoclip(ok, gta6_only=True))
        for bad in (video("BBBBBBBBBBB", CH_A, live="live"), video("CCCCCCCCCCC", CH_A, duration="PT50S"),
                    video("DDDDDDDDDDD", CH_A, duration="PT3H")):
            self.assertFalse(yr.eligible_for_autoclip(yr.video_row(bad, NOW), gta6_only=False))
        other = yr.video_row(video("EEEEEEEEEEE", CH_A, title="Fortnite insano"), NOW)
        self.assertFalse(yr.eligible_for_autoclip(other, gta6_only=True))
        self.assertTrue(yr.eligible_for_autoclip(other, gta6_only=False))


class SourcesAndRadarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"YOUTUBE_API_KEY": "k" * 39, "YOUTUBE_MIN_SUBSCRIBERS": "100000",
                                      "YOUTUBE_SEARCH_QUERY": ""})
        env.start()
        self.addCleanup(env.stop)

    def runtime(self, profile="gta6_only"):
        twitch = SimpleNamespace(profile=lambda now=None: {"profile": profile, "focus_game": "GTA VI"})
        return SimpleNamespace(twitch=twitch, store=SimpleNamespace(root=self.root))

    def test_authorization_requires_valid_channel_and_evidence(self):
        with self.assertRaises(ValueError):
            yr.add_source(self.root, "not-a-channel", "X", "permission_granted", "cortes liberados")
        with self.assertRaises(ValueError):
            yr.add_source(self.root, CH_A, "Canal A", "permission_granted", "ok")
        yr.add_source(self.root, CH_A, "Canal A", "permission_granted", "Descrição: cortes liberados")
        self.assertEqual(set(yr.authorized_sources(self.root)), {CH_A})
        self.assertTrue(yr.remove_source(self.root, CH_A))
        self.assertEqual(yr.authorized_sources(self.root), {})

    def test_radar_famous_channels_policy_and_cache(self):
        client = FakeClient(
            popular=[video("AAAAAAAAAAA", CH_A), video("BBBBBBBBBBB", CH_B, description="Proibido cortes, dou strike"),
                     video("CCCCCCCCCCC", CH_SMALL)],
            channels=[channel(CH_A, 2_000_000, "Cortes liberados! Marquem o canal."),
                      channel(CH_B, 900_000, "Cortes liberados"), channel(CH_SMALL, 5_000)],
            searched=[video("DDDDDDDDDDD", CH_A, title="GTA VI final secreto")])
        yr.add_source(self.root, CH_A, "Canal A", "permission_granted", "Descrição: cortes liberados")
        os.environ["YOUTUBE_SEARCH_QUERY"] = "GTA 6|GTA VI"
        result = yr.radar(self.runtime(), now=NOW, client=client)
        ids = {c["channel_id"]: c for c in result["channels"]}
        self.assertEqual(set(ids), {CH_A, CH_B}, "canal pequeno fica fora dos 'famosos'")
        self.assertEqual(ids[CH_A]["policy"]["status"], "allowed")
        self.assertEqual(ids[CH_B]["policy"]["status"], "restricted", "restrição em vídeo vence liberação")
        self.assertTrue(ids[CH_A]["authorized"])
        self.assertEqual({v["id"] for v in result["videos"]}, {"AAAAAAAAAAA", "BBBBBBBBBBB", "DDDDDDDDDDD"})
        self.assertTrue(all("description" not in v for v in result["videos"]))
        self.assertIn(("search", "GTA 6|GTA VI"), client.calls)
        # Segunda leitura usa o cache (cota limitada).
        again = FakeClient([], [])
        cached = yr.radar(self.runtime(), now=NOW + timedelta(minutes=5), client=again)
        self.assertEqual(again.calls, [])
        self.assertEqual(len(cached["videos"]), 3)

    def test_radar_without_key_is_honest(self):
        os.environ["YOUTUBE_API_KEY"] = ""
        result = yr.radar(self.runtime(), now=NOW)
        self.assertFalse(result["configured"])
        self.assertIn("Conecte o YouTube", result["error"])
        self.assertEqual(result["videos"], [])

    def test_api_key_never_leaks_in_errors(self):
        from urllib.error import HTTPError
        import io
        key = "SECRETKEY" + "x" * 30

        def opener(request, timeout=20):
            raise HTTPError(request.full_url, 403, "Forbidden", {},
                            io.BytesIO(b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}'))
        client = yr.YouTubeAPI(key, opener=opener)
        with self.assertRaises(yr.YouTubeError) as ctx:
            client.most_popular_gaming()
        self.assertNotIn(key, str(ctx.exception))
        self.assertIn("Cota", str(ctx.exception))


def make_video(path: Path, seconds=12):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s=320x180:r=15:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(path)], check=True, timeout=60)


class YouTubeDownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.incoming = Path(self.tmp.name) / "data" / "incoming"

    def fake_run(self, *, channel_id=CH_A, code=0, stderr="", produce=True):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            out = Path(cmd[cmd.index("-o") + 1]).parent
            if produce and code == 0:
                make_video(out / "video.mp4")
                (out / "video.info.json").write_text(json.dumps(
                    {"id": cmd[-1].rsplit("=", 1)[-1], "channel_id": channel_id, "title": "GTA 6"}),
                    encoding="utf-8")
            return SimpleNamespace(returncode=code, stderr=stderr)
        return run, calls

    def test_downloads_authorized_video_with_manifest(self):
        run, calls = self.fake_run()
        with patch.object(ytd, "deno_path", return_value="/opt/deno"), \
             patch.dict(os.environ, {"YOUTUBE_COOKIES_BROWSER": "firefox"}):
            target = ytd.download_youtube_video("AAAAAAAAAAA", CH_A, MANIFEST, self.incoming,
                                                run=run, command=["yt-dlp"])
        self.assertEqual(target.name, "youtube-AAAAAAAAAAA.mp4")
        meta = json.loads(Path(str(target) + ".rights.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["download_method"], "youtube_public_yt_dlp")
        self.assertEqual(meta["youtube_channel_id"], CH_A)
        self.assertEqual(meta["source_url"], "https://www.youtube.com/watch?v=AAAAAAAAAAA")
        self.assertGreater(meta["source_duration_sec"], 10)
        cmd = calls[0]
        self.assertIn("--no-playlist", cmd)
        self.assertEqual(cmd[cmd.index("--js-runtimes") + 1], "deno:/opt/deno")
        self.assertEqual(cmd[cmd.index("--cookies-from-browser") + 1], "firefox")
        self.assertIn("!is_live", cmd[cmd.index("--match-filter") + 1])
        self.assertEqual(cmd[-1], "https://www.youtube.com/watch?v=AAAAAAAAAAA")

    def test_unauthorized_or_mismatched_manifest_never_runs(self):
        run, calls = self.fake_run()
        for manifest in ({**MANIFEST, "channel_id": CH_B}, {**MANIFEST, "evidence": "x"},
                         {**MANIFEST, "rights_status": "unknown"}, None):
            with self.assertRaises(DownloadError):
                ytd.download_youtube_video("AAAAAAAAAAA", CH_A, manifest, self.incoming, run=run, command=["y"])
        with self.assertRaises(DownloadError):
            ytd.download_youtube_video("bad id", CH_A, MANIFEST, self.incoming, run=run, command=["y"])
        self.assertEqual(calls, [])

    def test_video_from_other_channel_is_discarded(self):
        run, _ = self.fake_run(channel_id=CH_B)
        with self.assertRaises(DownloadError) as ctx:
            ytd.download_youtube_video("AAAAAAAAAAA", CH_A, MANIFEST, self.incoming, run=run, command=["y"])
        self.assertIn("canal autorizado", str(ctx.exception))
        self.assertEqual(list(self.incoming.glob("youtube-*")), [])

    def test_bot_check_error_is_explained_and_leaves_nothing(self):
        run, _ = self.fake_run(code=1, stderr="ERROR: Sign in to confirm you're not a bot")
        with self.assertRaises(DownloadError) as ctx:
            ytd.download_youtube_video("AAAAAAAAAAA", CH_A, MANIFEST, self.incoming, run=run, command=["y"])
        self.assertIn("Cookies do navegador", str(ctx.exception))
        self.assertEqual(list(self.incoming.glob("youtube-*")), [])

    def test_duplicate_blocked(self):
        run, _ = self.fake_run()
        ytd.download_youtube_video("AAAAAAAAAAA", CH_A, MANIFEST, self.incoming, run=run, command=["y"])
        with self.assertRaises(DownloadError):
            ytd.download_youtube_video("AAAAAAAAAAA", CH_A, MANIFEST, self.incoming, run=run, command=["y"])


class YouTubeAutoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "incoming").mkdir()
        env = patch.dict(os.environ, {"YOUTUBE_API_KEY": "k" * 39, "YOUTUBE_PUBLIC_DOWNLOAD": "1",
                                      "YOUTUBE_AUTO_BATCH": "2", "YOUTUBE_AUTO_GTA6_ONLY": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.downloads = []
        self.scans = 0

    def runtime(self):
        def scan():
            self.scans += 1
            return {"added": ["x"], "errors": []}
        bridge = SimpleNamespace(available=lambda: True, model_ready=lambda: True)
        twitch = SimpleNamespace(profile=lambda: {"profile": "gta6_only"})
        return SimpleNamespace(store=SimpleNamespace(root=self.root, incoming=self.root / "incoming"),
                               autoclip_bridge=bridge, twitch=twitch, scan=scan)

    def downloader(self, vid, channel_id, manifest, incoming, title=""):
        self.downloads.append((vid, channel_id, manifest["channel_id"]))

    def test_only_authorized_eligible_videos_in_batch(self):
        yr.add_source(self.root, CH_A, "Canal A", "permission_granted", "Descrição: cortes liberados")
        uploads = {"UU" + CH_A[2:]: [video("AAAAAAAAAAA", CH_A, views=800_000),
                                     video("BBBBBBBBBBB", CH_A, views=900_000, live="live"),
                                     video("CCCCCCCCCCC", CH_A, title="Fortnite"),
                                     video("DDDDDDDDDDD", CH_A, hours=24 * 10)],
                   "UU" + CH_B[2:]: [video("EEEEEEEEEEE", CH_B, views=9_000_000)]}
        client = FakeClient([], [channel(CH_A, 1_000_000), channel(CH_B, 5_000_000)], uploads=uploads)
        intake = YouTubeAutoIngest(self.runtime(), client_factory=lambda key: client,
                                   downloader=self.downloader)
        with patch.object(ytd, "yt_dlp_command", return_value=["yt-dlp"]):
            intake.running = True
            intake._work(now=NOW)
        self.assertEqual(self.downloads, [("AAAAAAAAAAA", CH_A, CH_A)])
        self.assertEqual(self.scans, 1)
        self.assertEqual(intake.processed, 1)
        self.assertFalse(intake.running)

    def test_kick_refuses_when_disabled_or_unauthorized(self):
        intake = YouTubeAutoIngest(self.runtime(), downloader=self.downloader)
        with patch.object(ytd, "yt_dlp_command", return_value=["yt-dlp"]):
            self.assertFalse(intake.kick())
            self.assertIn("autorizado", intake.last_error)
            os.environ["YOUTUBE_PUBLIC_DOWNLOAD"] = "0"
            self.assertFalse(intake.kick())
            self.assertIn("desligado", intake.last_error)
        self.assertEqual(self.downloads, [])


class BridgeTimeoutTest(unittest.TestCase):
    def test_long_youtube_sources_get_more_time(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "youtube-AAAAAAAAAAA.mp4"
            source.write_bytes(b"x")
            self.assertEqual(AutoClipBridge._timeout_for(source), 1800)
            Path(str(source) + ".rights.json").write_text(json.dumps({"source_duration_sec": 3000}))
            self.assertEqual(AutoClipBridge._timeout_for(source), 6000)
            Path(str(source) + ".rights.json").write_text(json.dumps({"source_duration_sec": 99999}))
            self.assertEqual(AutoClipBridge._timeout_for(source), 10800)
            with patch.dict(os.environ, {"AUTOCLIP_TIMEOUT_SECONDS": "900"}):
                self.assertEqual(AutoClipBridge._timeout_for(source), 900)


class ScanFingerprintTest(unittest.TestCase):
    def test_unchanged_files_are_not_reprobed(self):
        from clipforge import core
        with tempfile.TemporaryDirectory() as d:
            store = core.ClipStore(Path(d))
            media = store.incoming / "own.mp4"
            make_video(media, seconds=12)
            (store.incoming / "own.mp4.rights.json").write_text(json.dumps(
                {"creator": "Eu", "rights_status": "owned"}), encoding="utf-8")
            with patch.object(core, "probe", wraps=core.probe) as spy:
                self.assertEqual(len(store.scan()["added"]), 1)
                first = spy.call_count
                self.assertEqual(store.scan()["added"], [])
                self.assertEqual(spy.call_count, first, "arquivo inalterado não é relido")


class YouTubeWebTest(unittest.TestCase):
    def setUp(self):
        from clipforge.core import Runtime
        from clipforge.web import make_handler
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DASHBOARD_TOKEN": "example-secret", "AUTO_SCAN": "0", "AUTO_RENDER": "0",
                                      "TWITCH_ENABLED": "0", "TWITCH_CLIENT_ID": "", "TWITCH_CLIENT_SECRET": "",
                                      "YOUTUBE_API_KEY": "", "YOUTUBE_PUBLIC_DOWNLOAD": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = Runtime(Path(self.temp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=2)
            self.runtime.executor.shutdown(wait=True)
        self.addCleanup(stop)

    def request(self, method, path, token=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Authorization": "Bearer " + token} if token else {}
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def test_routes_private_honest_and_gated(self):
        self.assertEqual(self.request("GET", "/api/youtube/radar")[0], 401)
        status, body = self.request("GET", "/api/youtube/radar", "example-secret")
        self.assertEqual(status, 200)
        self.assertFalse(body["configured"])
        self.assertEqual(body["videos"], [])
        status, body = self.request("GET", "/api/youtube/status", "example-secret")
        self.assertFalse(body["ready"])
        status, body = self.request("POST", "/api/youtube/run", "example-secret")
        self.assertEqual(status, 409)
        self.assertIn("desligado", body["error"])
        status, body = self.request("POST", "/api/youtube/sources", "example-secret",
                                    {"channel_id": CH_A, "creator": "Canal A",
                                     "rights_status": "permission_granted", "evidence": "curto"})
        self.assertEqual(status, 400)
        status, body = self.request("POST", "/api/youtube/sources", "example-secret",
                                    {"channel_id": CH_A, "creator": "Canal A",
                                     "rights_status": "permission_granted",
                                     "evidence": "Descrição do canal: cortes liberados"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/youtube/radar", "example-secret")[1]["authorized_count"], 1)


if __name__ == "__main__":
    unittest.main()
