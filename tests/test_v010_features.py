"""Histórico de downloads, monitor de lives, configurações do AutoClip, exportação e notificações."""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from clipforge import autoclip_settings as acs
from clipforge.ingest_log import IngestLog, record
from clipforge.twitch_download import DownloadError


def make_video(path: Path, seconds: int = 4, size: str = "360x640"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s={size}:r=15:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True, timeout=60)


class IngestLogTest(unittest.TestCase):
    def test_lifecycle_counts_and_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = IngestLog(Path(tmp) / "db.sqlite3", threading.RLock())
            log.start("twitch", "clip", "1", "abc", source_name="X", title="T", trigger="manual")
            log.finish("twitch", "abc", "failed", "boom")
            log.start("twitch", "clip", "1", "abc")  # nova tentativa reabre a mesma linha
            log.finish("twitch", "abc", "done")
            log.start("youtube", "video", "UC1", "vid1")
            log.finish("youtube", "vid1", "failed", "sem cookies")
            rows = {r["item_id"]: r for r in log.list()}
            self.assertEqual(rows["abc"]["status"], "done")
            self.assertEqual(rows["abc"]["attempts"], 2)
            self.assertEqual(log.counts(), {"done": 1, "failed": 1})
            self.assertEqual([r["item_id"] for r in log.failures_since(1)], ["vid1"])
            with self.assertRaises(ValueError):
                log.start("tiktok", "clip", "1", "x")

    def test_record_is_noop_without_log(self):
        record(SimpleNamespace(), "start", "twitch", "clip", "1", "x")  # não levanta


class LiveMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "incoming").mkdir()
        self.client = Mock()
        self.sources = [{"broadcaster_id": "111", "creator": "Autorizado",
                         "rights_status": "permission_granted", "evidence": "Bio: cortes liberados"}]
        self.runtime = SimpleNamespace(
            store=SimpleNamespace(database=root / "db.sqlite3", incoming=root / "incoming", root=root),
            twitch=SimpleNamespace(client=self.client, client_id="c", secret="s"),
            twitch_auto=SimpleNamespace(_allowed_sources=lambda: self.sources),
            scan=Mock(return_value={"added": ["x"]}))
        self.runtime.ingest_log = IngestLog(self.runtime.store.database, threading.RLock())
        from clipforge.live_monitor import TwitchLiveMonitor
        self.downloader = Mock()
        self.monitor = TwitchLiveMonitor(self.runtime, downloader=self.downloader)

    def test_only_authorized_streams_and_vod_on_end(self):
        self.client.get_streams.return_value = [
            {"id": "s1", "user_id": "111", "user_name": "Autorizado", "title": "GTA VI ao vivo", "game_name": "GTA VI"},
            {"id": "s2", "user_id": "999", "user_name": "Outro"}]
        self.monitor.check()
        self.client.get_streams.assert_called_once_with(["111"])
        status = self.monitor.status()
        self.assertEqual([s["stream_id"] for s in status["sessions"]], ["s1"])
        self.assertEqual(status["live_now"][0]["name"], "Autorizado")
        # Live termina: sem download ligado, só registra a VOD encontrada.
        self.client.get_streams.return_value = []
        self.client.get_latest_vod.return_value = {"id": "555", "stream_id": "s1"}
        with patch.dict(os.environ, {"TWITCH_LIVE_VOD_DOWNLOAD": "0"}):
            self.monitor.check()
        self.assertEqual(self.monitor.status()["sessions"][0]["status"], "vod_found")
        self.downloader.assert_not_called()

    def test_vod_downloaded_when_enabled_and_logged(self):
        self.client.get_streams.side_effect = [[{"id": "s1", "user_id": "111"}], []]
        self.client.get_latest_vod.return_value = {"id": "555", "stream_id": "s1"}
        with patch.dict(os.environ, {"TWITCH_LIVE_VOD_DOWNLOAD": "1", "TWITCH_PUBLIC_DOWNLOAD": "1"}):
            self.monitor.check()
            self.monitor.check(trigger="manual")
        self.downloader.assert_called_once()
        self.assertEqual(self.downloader.call_args.args[:2], ("555", "111"))
        self.assertEqual(self.monitor.status()["sessions"][0]["status"], "vod_downloaded")
        row = self.runtime.ingest_log.list()[0]
        self.assertEqual((row["kind"], row["status"], row["trigger"]), ("vod", "done", "manual"))

    def test_vod_failure_is_recorded(self):
        self.client.get_streams.side_effect = [[{"id": "s1", "user_id": "111"}], []]
        self.client.get_latest_vod.return_value = {"id": "555", "stream_id": "s1"}
        self.downloader.side_effect = DownloadError("yt-dlp falhou: VOD só para inscritos")
        with patch.dict(os.environ, {"TWITCH_LIVE_VOD_DOWNLOAD": "1", "TWITCH_PUBLIC_DOWNLOAD": "1"}):
            self.monitor.check(); self.monitor.check()
        self.assertEqual(self.monitor.status()["sessions"][0]["status"], "vod_failed")
        self.assertEqual(self.runtime.ingest_log.failures_since(1)[0]["item_id"], "555")

    def test_no_sources_or_client(self):
        self.sources.clear()
        self.monitor.check()
        self.assertIn("autorizado", self.monitor.last_error)


class PublicVodTest(unittest.TestCase):
    def test_vod_download_validates_and_limits_duration(self):
        from clipforge.public_clip_download import download_public_vod
        manifest = {"creator": "A", "rights_status": "owned", "broadcaster_id": "111"}
        with tempfile.TemporaryDirectory() as tmp:
            incoming = Path(tmp) / "data" / "incoming"
            calls = []

            def run(cmd, **kw):
                calls.append(cmd)
                make_video(Path(cmd[cmd.index("-o") + 1]).parent / "clip.mp4")
                return SimpleNamespace(returncode=0, stderr="")
            target = download_public_vod("123456", "111", manifest, incoming, max_minutes=90,
                                         run=run, command=["yt-dlp"])
            meta = json.loads(Path(str(target) + ".rights.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["download_method"], "public_vod_yt_dlp")
            self.assertEqual(meta["twitch_vod_id"], "123456")
            self.assertGreater(meta["source_duration_sec"], 0)
            self.assertIn("duration <= 5400 & !is_live", calls[0])
            self.assertEqual(calls[0][-1], "https://www.twitch.tv/videos/123456")
            with self.assertRaises(DownloadError):
                download_public_vod("abc", "111", manifest, incoming, run=run, command=["yt-dlp"])


class AutoClipSettingsTest(unittest.TestCase):
    def test_defaults_save_load_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(acs.load(tmp), acs.DEFAULTS)
            saved = acs.save(tmp, {"max_clips": 5, "caption_preset": "custom", "font": "Inter",
                                   "primary": "#00FF00", "accent": "", "position_percent": 30})
            self.assertEqual(acs.load(tmp), saved)
            for bad in ({"max_clips": 0}, {"framing": "x"}, {"primary": "red"}, {"size_percent": 20},
                        {"font": "Comic"}, {"hack": 1}):
                with self.assertRaises(ValueError, msg=bad):
                    acs.save(tmp, bad)

    def test_cli_args_custom_and_fallback(self):
        settings = acs.validate({"max_clips": 4, "framing": "center", "caption_preset": "custom",
                                 "boxed": True})
        args, env = acs.cli_args(settings, custom_supported=True)
        self.assertEqual(args, ["--max-clips", "4", "--ratio", "9:16", "--style", "nexus_custom", "--centre-crop"])
        spec = json.loads(env["NEXUS_CAPTION_STYLE"])
        self.assertEqual(spec["margin_v_ratio"], 0.24)
        self.assertTrue(spec["boxed"])
        args, env = acs.cli_args(settings, custom_supported=False)
        self.assertEqual(env, {})
        self.assertIn("boxed", args)
        args, _ = acs.cli_args(acs.validate({"caption_preset": "karaoke_fill"}), True)
        self.assertEqual(args[-1], "karaoke_fill")
        self.assertNotIn("--centre-crop", args)

    def test_runner_source_registers_preset(self):
        self.assertIn("NEXUS_CAPTION_STYLE", acs.RUNNER_SOURCE)
        self.assertIn('PRESETS["nexus_custom"]', acs.RUNNER_SOURCE)
        compile(acs.RUNNER_SOURCE, "runner", "exec")


class ExporterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.src = root / "rendered" / "c1.mp4"
        self.src.parent.mkdir()
        make_video(self.src, seconds=4)
        self.clip = {"id": "c1", "status": "approved", "output_path": str(self.src), "filename": "c1.mp4",
                     "creator": "Streamer X", "source_url": "https://clips.twitch.tv/abc",
                     "rights_status": "permission_granted"}
        from clipforge.exporter import Exporter
        self.exporter = Exporter(SimpleNamespace(root=root, get=lambda cid: self.clip if cid == "c1" else None))

    def _tags(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
                             capture_output=True, text=True, check=True).stdout
        return {k.lower(): v for k, v in json.loads(out)["format"].get("tags", {}).items()}

    def test_lossless_copy_keeps_source_and_writes_provenance(self):
        before = self.src.read_bytes()
        rec = self.exporter.export("c1", {"title": "Fuga insana"})
        self.assertTrue(rec["lossless"])
        self.assertEqual(self.src.read_bytes(), before, "original do AutoClip não pode mudar")
        tags = self._tags(self.exporter.path(rec["file"]))
        self.assertEqual(tags["title"], "Fuga insana")
        self.assertEqual(tags["artist"], "Streamer X")
        self.assertIn("https://clips.twitch.tv/abc", tags["comment"])
        self.assertEqual(self.exporter.list("c1")[0]["file"], rec["file"])

    def test_reencode_trim_resolution_and_webm(self):
        rec = self.exporter.export("c1", {"format": "webm", "resolution": "540x960", "quality": "leve",
                                          "start": 1, "end": 3})
        self.assertFalse(rec["lossless"])
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
                                          "-of", "json", str(self.exporter.path(rec["file"]))],
                                         capture_output=True, text=True, check=True).stdout)
        video = [s for s in info["streams"] if s.get("width")][0]
        self.assertEqual((video["width"], video["height"]), (540, 960))
        self.assertAlmostEqual(float(info["format"]["duration"]), 2, delta=0.3)

    def test_rejects_bad_requests(self):
        for opts in ({"format": "avi"}, {"start": 3.9}, {"strip_origin": True}):
            with self.assertRaises(ValueError, msg=opts):
                self.exporter.export("c1", opts)
        self.clip["status"] = "rejected"
        with self.assertRaises(ValueError):
            self.exporter.export("c1", {})
        for name in ("../x.mp4", "x.json", ""):
            with self.assertRaises(ValueError):
                self.exporter.path(name)


class NotificationsTest(unittest.TestCase):
    def test_collects_real_failures_with_mode(self):
        from clipforge.notifications import collect
        with tempfile.TemporaryDirectory() as tmp:
            log = IngestLog(Path(tmp) / "db.sqlite3", threading.RLock())
            log.start("twitch", "clip", "1", "abc", title="Clipe A")
            log.finish("twitch", "abc", "failed", "403")
            runtime = SimpleNamespace(
                ingest_log=log,
                autoclip_bridge=SimpleNamespace(status=lambda: {"jobs": {"c9": {"status": "failed", "error": "Ollama off"}}}),
                twitch_auto=SimpleNamespace(last_error=None), youtube_auto=SimpleNamespace(last_error="sem chave"),
                live_monitor=SimpleNamespace(last_error=None))
            import time as _t
            pub = SimpleNamespace(all=lambda: [{"status": "failed", "updated_at": _t.time(), "automatic": 1,
                                               "platform": "youtube", "title": "Corte", "error": "quota"}])
            data = collect(runtime, pub)
        areas = {(i["area"], i["automatic"]) for i in data["items"]}
        self.assertIn(("download", True), areas)
        self.assertIn(("autoclip", True), areas)
        self.assertIn(("publicacao", True), areas)
        self.assertIn(("automacao", True), areas)
        self.assertEqual(data["count"], 4)


class WebRoutesTest(unittest.TestCase):
    def test_new_routes_auth_and_behaviour(self):
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        from clipforge.core import Runtime
        from clipforge.web import make_handler
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"DASHBOARD_TOKEN": "tok-123456", "AUTO_SCAN": "0",
                                        "TWITCH_ENABLED": "0"}):
            runtime = Runtime(Path(tmp) / "data")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runtime))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}"

            def call(path, method="GET", body=None, token="tok-123456"):
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + path, data=data, method=method)
                if data is not None:
                    req.add_header("Content-Type", "application/json")
                if token:
                    req.add_header("Authorization", "Bearer " + token)
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())
            try:
                for path in ("/api/ingest/history", "/api/live", "/api/notifications",
                             "/api/autoclip/settings", "/api/exports"):
                    self.assertEqual(call(path, token=None)[0], 401, path)
                    self.assertEqual(call(path)[0], 200, path)
                status, body = call("/api/autoclip/settings", "POST", {"max_clips": 6})
                self.assertEqual((status, body["settings"]["max_clips"]), (200, 6))
                self.assertEqual(call("/api/autoclip/settings", "POST", {"max_clips": 99})[0], 400)
                self.assertEqual(call("/api/ingest/run", "POST", {})[0], 202)
                self.assertEqual(call("/api/live/settings", "POST", {"vod_download": "sim"})[0], 400)
                self.assertEqual(call("/api/clips/nope/export", "POST", {})[0], 400)
                self.assertEqual(call("/api/exports/../../etc", )[0], 404)
            finally:
                server.shutdown(); server.server_close()


if __name__ == "__main__":
    unittest.main()


class LiveRecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "incoming").mkdir()

    def _recorder(self, finished=True):
        from clipforge.live_recorder import LiveRecorder
        procs = []

        def popen(cmd, **kw):
            out = Path(cmd[cmd.index("-o") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=15:d=3",
                            "-f", "lavfi", "-i", "sine=d=3", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", "-f", "mpegts", str(out)], check=True, timeout=60)
            proc = Mock()
            proc.poll.return_value = 0 if finished else None
            procs.append((cmd, proc))
            return proc
        return LiveRecorder(self.root, self.root / "incoming", popen=popen, command=["yt-dlp"]), procs

    def test_record_finalize_with_manifest(self):
        rec, procs = self._recorder()
        manifest = {"creator": "A", "rights_status": "permission_granted", "evidence": "bio libera",
                    "broadcaster_id": "111"}
        rec.start("12345", "Streamer_A", manifest)
        self.assertEqual(procs[0][0][-1], "https://www.twitch.tv/streamer_a")
        self.assertEqual(rec.poll("12345", still_live=False), "finished")
        target = rec.finalize("12345", "GTA VI ao vivo")
        meta = json.loads(Path(str(target) + ".rights.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["download_method"], "live_recording_yt_dlp")
        self.assertGreater(meta["source_duration_sec"], 2)
        self.assertFalse(list((self.root / "recordings").glob("*.ts")))

    def test_still_live_keeps_recording_and_blocks_unauthorized(self):
        rec, _ = self._recorder(finished=False)
        with self.assertRaises(DownloadError):
            rec.start("1", "x_y", {"rights_status": "public", "broadcaster_id": "1"})
        with self.assertRaises(DownloadError):
            rec.start("1", "../evil", {"rights_status": "owned", "broadcaster_id": "1"})
        rec.start("1", "abc", {"rights_status": "owned", "broadcaster_id": "1", "creator": "a"})
        self.assertEqual(rec.poll("1", still_live=True), "recording")
        self.assertEqual(rec.poll("1", still_live=False), "finished")

    def test_monitor_records_and_skips_vod(self):
        from clipforge.live_monitor import TwitchLiveMonitor
        rec, _ = self._recorder()
        client = Mock()
        client.get_streams.side_effect = [[{"id": "77", "user_id": "111", "user_login": "aut", "title": "T"}], []]
        sources = [{"broadcaster_id": "111", "creator": "Aut", "rights_status": "owned", "evidence": ""}]
        runtime = SimpleNamespace(
            store=SimpleNamespace(database=self.root / "db.sqlite3", incoming=self.root / "incoming", root=self.root),
            twitch=SimpleNamespace(client=client, client_id="c", secret="s"),
            twitch_auto=SimpleNamespace(_allowed_sources=lambda: sources),
            scan=Mock(return_value={"added": ["x"]}))
        runtime.ingest_log = IngestLog(runtime.store.database, threading.RLock())
        vod = Mock()
        monitor = TwitchLiveMonitor(runtime, downloader=vod, recorder=rec)
        with patch.dict(os.environ, {"TWITCH_LIVE_RECORD": "1", "TWITCH_PUBLIC_DOWNLOAD": "1",
                                     "TWITCH_LIVE_VOD_DOWNLOAD": "1"}):
            monitor.check()
            monitor.check()
        self.assertEqual(monitor.status()["sessions"][0]["status"], "recorded")
        vod.assert_not_called()
        client.get_latest_vod.assert_not_called()
        self.assertEqual(runtime.ingest_log.list()[0]["kind"], "live")
        self.assertTrue((self.root / "incoming" / "twitch-live-77.mp4").is_file())


class FriendlyErrorsTest(unittest.TestCase):
    def test_known_errors_are_translated(self):
        from clipforge.public_clip_download import humanize_ytdlp_error as h
        self.assertIn("inscritos", h("ERROR: [twitch:vod] 123: This video is only available to subscribers"))
        self.assertIn("removido", h("ERROR: Video 123 does not exist"))
        self.assertIn("limite", h("[download] VOD does not pass filter (duration <= 600), skipping"))
        self.assertIn("403", h("ERROR: HTTP Error 403: Forbidden"))
        self.assertTrue(h("ERROR: algo novo").startswith("Download falhou: ERROR: algo novo"))


class WindowsNotifierTest(unittest.TestCase):
    def test_only_new_failures_and_text_via_env(self):
        from clipforge.desktop_notify import WindowsNotifier
        items = [{"area": "download", "platform": "twitch", "title": "Clipe", "message": "403", "at": "1", "automatic": True}]
        run = Mock(return_value=SimpleNamespace(returncode=0))
        n = WindowsNotifier(SimpleNamespace(), run=run, collect=lambda rt, pub: {"items": list(items)},
                            platform="win32")
        self.assertEqual(n.tick(), 0, "primeira leitura só marca o que já existia")
        items.append({"area": "publicacao", "platform": "youtube", "title": "Corte'; rm -rf", "message": "quota",
                      "at": "2", "automatic": False})
        self.assertEqual(n.tick(), 1)
        cmd, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertNotIn("rm -rf", " ".join(cmd), "texto nunca entra no comando")
        self.assertIn("rm -rf", kwargs["env"]["NEXUS_TOAST_BODY"])
        self.assertIn("(manual)", kwargs["env"]["NEXUS_TOAST_TITLE"])
        self.assertEqual(n.tick(), 0)

    def test_disabled_off_windows_or_by_env(self):
        from clipforge.desktop_notify import WindowsNotifier
        self.assertFalse(WindowsNotifier(SimpleNamespace(), collect=lambda *a: {"items": []}, platform="linux").enabled())
        with patch.dict(os.environ, {"NEXUS_WINDOWS_NOTIFY": "0"}):
            self.assertFalse(WindowsNotifier(SimpleNamespace(), collect=lambda *a: {"items": []}, platform="win32").enabled())


class SuggestionEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from clipforge.autoclip_bridge import AutoClipBridge
        root = Path(self.tmp.name)
        self.bridge = AutoClipBridge(SimpleNamespace(root=root, incoming=root / "incoming"))
        out = self.bridge.exports / "job1"
        out.mkdir(parents=True)
        make_video(out / "clip1.mp4", seconds=30, size="360x640")
        self.bridge.jobs["c1"] = {"status": "complete", "suggestions": ["job1/clip1.mp4"], "imports": []}

    def test_trim_creates_new_file_and_keeps_original(self):
        original = (self.bridge.exports / "job1" / "clip1.mp4").read_bytes()
        target = self.bridge.trim_suggestion("c1", 0, 5, 20)
        from clipforge.core import duration_of, probe
        self.assertAlmostEqual(duration_of(probe(target)), 15, delta=0.5)
        self.assertEqual((self.bridge.exports / "job1" / "clip1.mp4").read_bytes(), original)
        for start, end in ((0, 5), (25, 90), (-1, 15)):
            with self.assertRaises(ValueError):
                self.bridge.trim_suggestion("c1", 0, start, end)

    def test_redo_requeues_and_blocks_running(self):
        self.bridge.queue = Mock(return_value={"status": "queued"})
        self.assertEqual(self.bridge.redo("c1"), {"status": "queued"})
        self.assertNotIn("c1", self.bridge.jobs)
        self.bridge.jobs["c1"] = {"status": "running"}
        with self.assertRaises(ValueError):
            self.bridge.redo("c1")
