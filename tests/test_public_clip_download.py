import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from clipforge.public_clip_download import download_public_clip
from clipforge.twitch_download import DownloadError

MANIFEST = {"creator": "Streamer", "rights_status": "permission_granted",
            "evidence": "Bio pública: cortes liberados", "broadcaster_id": "111"}


def make_video(path: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=320x180:r=15:d=2", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(path)], check=True, timeout=60)


class PublicClipDownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.incoming = Path(self.tmp.name) / "data" / "incoming"

    def fake_run(self, produce=True, code=0):
        calls = []
        def run(cmd, **kwargs):
            calls.append(cmd)
            out = Path(cmd[cmd.index("-o") + 1]).parent
            if produce:
                make_video(out / "clip.mp4")
            return SimpleNamespace(returncode=code, stderr="ERROR: boom" if code else "")
        return run, calls

    def test_downloads_authorized_clip_with_manifest(self):
        run, calls = self.fake_run()
        target = download_public_clip("GoodClip-1", "111", MANIFEST, self.incoming,
                                      run=run, command=["yt-dlp"])
        self.assertTrue(target.is_file())
        sidecar = json.loads(Path(str(target) + ".rights.json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["download_method"], "public_clip_page_yt_dlp")
        self.assertEqual(sidecar["source_url"], "https://clips.twitch.tv/GoodClip-1")
        self.assertEqual(sidecar["rights_status"], "permission_granted")
        self.assertEqual(calls[0][-1], "https://clips.twitch.tv/GoodClip-1")
        self.assertIn("--no-playlist", calls[0])

    def test_unauthorized_or_mismatched_manifest_never_runs(self):
        run = Mock()
        for manifest in ({}, {**MANIFEST, "broadcaster_id": "999"},
                         {**MANIFEST, "evidence": "x"}, {**MANIFEST, "rights_status": "public"}):
            with self.assertRaises(DownloadError):
                download_public_clip("GoodClip", "111", manifest, self.incoming, run=run, command=["yt-dlp"])
        run.assert_not_called()

    def test_invalid_clip_id_never_runs(self):
        run = Mock()
        for bad in ("../x", "a b", "", "https://evil"):
            with self.assertRaises(DownloadError):
                download_public_clip(bad, "111", MANIFEST, self.incoming, run=run, command=["yt-dlp"])
        run.assert_not_called()

    def test_ytdlp_failure_leaves_nothing(self):
        run, _ = self.fake_run(produce=False, code=1)
        with self.assertRaises(DownloadError):
            download_public_clip("GoodClip", "111", MANIFEST, self.incoming, run=run, command=["yt-dlp"])
        self.assertFalse(any(self.incoming.glob("twitch-*")))

    def test_duplicate_is_blocked(self):
        run, _ = self.fake_run()
        download_public_clip("GoodClip", "111", MANIFEST, self.incoming, run=run, command=["yt-dlp"])
        with self.assertRaises(DownloadError):
            download_public_clip("GoodClip", "111", MANIFEST, self.incoming, run=run, command=["yt-dlp"])

    def test_missing_ytdlp_is_explicit(self):
        with patch("clipforge.public_clip_download.yt_dlp_command", return_value=None):
            with self.assertRaises(DownloadError) as ctx:
                download_public_clip("GoodClip", "111", MANIFEST, self.incoming, run=Mock())
        self.assertIn("yt-dlp", str(ctx.exception))


class AutoIngestPublicFallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "data"
        (root / "incoming").mkdir(parents=True)
        (root / "twitch_sources.json").write_text(json.dumps({"broadcasters": [
            {"id": "111", "creator": "Autorizado", "rights_status": "permission_granted",
             "evidence": "Bio pública: cortes liberados"}]}), encoding="utf-8")
        meta = {"duration": 30, "view_count": 5000, "title": "Fuga insana", "score": 95,
                "language": "pt", "game_name": "Grand Theft Auto VI",
                "created_at": "2099-01-01T00:00:00Z"}
        self.items = [{"id": "AuthClip", "broadcaster_id": "111", **meta},
                      {"id": "OtherClip", "broadcaster_id": "222", **meta}]
        twitch = SimpleNamespace(client_id="cid", secret="s",
                                 list_candidates=lambda limit=100: self.items,
                                 profile=lambda: {"profile": "gta6_only"})
        from clipforge.twitch_auto import TwitchAutoIngest
        self.runtime = SimpleNamespace(store=SimpleNamespace(root=root, incoming=root / "incoming"),
                                       twitch=twitch, autoclip_bridge=SimpleNamespace(available=lambda: True),
                                       scan=Mock(return_value={"added": ["x"], "errors": []}))
        self.intake = TwitchAutoIngest(self.runtime)

    def _run(self, env):
        with patch.dict(os.environ, env, clear=False), \
             patch("clipforge.curation.qualifies", return_value=True), \
             patch("clipforge.twitch_auto.download_clip",
                   side_effect=DownloadError("Clipe ausente ou sem autorização de acesso pelo editor")) as official, \
             patch("clipforge.public_clip_download.download_public_clip") as public:
            self.intake._work()
        return official, public

    def test_public_fallback_only_for_authorized_when_enabled(self):
        official, public = self._run({"TWITCH_PUBLIC_DOWNLOAD": "1", "TWITCH_USER_ACCESS_TOKEN": "",
                                      "TWITCH_EDITOR_ID": ""})
        official.assert_not_called()
        public.assert_called_once()
        self.assertEqual(public.call_args.args[:2], ("AuthClip", "111"))

    def test_official_first_then_public(self):
        with patch("clipforge.twitch_oauth.refreshed_token", return_value="tok"):
            official, public = self._run({"TWITCH_PUBLIC_DOWNLOAD": "1",
                                          "TWITCH_USER_ACCESS_TOKEN": "tok", "TWITCH_EDITOR_ID": "999"})
        official.assert_called_once()
        public.assert_called_once()

    def test_disabled_never_uses_public(self):
        with patch("clipforge.twitch_oauth.refreshed_token", return_value="tok"):
            official, public = self._run({"TWITCH_PUBLIC_DOWNLOAD": "0",
                                          "TWITCH_USER_ACCESS_TOKEN": "tok", "TWITCH_EDITOR_ID": "999"})
        official.assert_called_once()
        public.assert_not_called()
        self.assertIn("editor", self.intake.last_error)


if __name__ == "__main__":
    unittest.main()
