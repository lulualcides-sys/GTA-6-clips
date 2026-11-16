"""Download oficial: autorização, limites e fluxo HTTP local real."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {"creator": "Criador", "rights_status": "permission_granted",
                         "evidence": "autorização documentada", "broadcaster_id": "42"}

    def test_missing_rights_rejected_before_network(self):
        from clipforge.twitch_download import download_clip, DownloadError
        with self.assertRaises(DownloadError):
            download_clip("clip1", "42", "42", "app", "token", {}, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cdn_and_clip_id_validation(self):
        from clipforge.twitch_download import safe_download_url, download_clip, DownloadError
        self.assertTrue(safe_download_url("https://production.assets.clips.twitchcdn.net/video.mp4?sig=x"))
        for url in ("http://production.assets.clips.twitchcdn.net/a", "https://production.assets.clips.twitchcdn.net.evil/a", "https://127.0.0.1/a", "https://user:pass@production.assets.clips.twitchcdn.net/a"):
            self.assertFalse(safe_download_url(url))
        with self.assertRaises(DownloadError):
            download_clip("../escape", "42", "42", "app", "token", self.manifest, self.root)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
    def test_real_http_media_ingest_and_duplicate_block(self):
        from clipforge.twitch_download import download_clip, DownloadError
        source = self.root / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1", "-c:v", "libx264", "-threads", "1", str(source)], check=True)
        media = source.read_bytes()
        calls = []
        denied = [False]
        redirect = [False]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                calls.append((self.path, self.headers.get("Authorization")))
                if self.path == "/validate":
                    data = {"client_id": "app", "user_id": "42", "expires_in": 3600,
                            "scopes": [] if denied[0] else ["channel:manage:clips"]}
                elif self.path.startswith("/clips/downloads?"):
                    data = {"data": [{"clip_id": "clip1", "landscape_download_url": base + "/media"}]}
                else:
                    if redirect[0]:
                        self.send_response(302)
                        self.send_header("Location", base + "/forbidden")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(media)))
                    self.end_headers()
                    self.wfile.write(media)
                    return
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch("clipforge.twitch_download.VALIDATE_URL", base + "/validate"), patch("clipforge.twitch_download.HELIX_BASE", base), patch("clipforge.twitch_download.safe_download_url", side_effect=lambda url: url == base + "/media"):
                denied[0] = True
                with self.assertRaisesRegex(DownloadError, "scope"):
                    download_clip("clip1", "42", "42", "app", "token", self.manifest, self.root / "incoming")
                denied[0] = False
                with patch("clipforge.twitch_download.MAX_BYTES", 1):
                    with self.assertRaisesRegex(DownloadError, "512 MiB"):
                        download_clip("clip1", "42", "42", "app", "token", self.manifest, self.root / "incoming")
                self.assertEqual(list((self.root / "incoming").iterdir()), [])
                redirect[0] = True
                with self.assertRaisesRegex(DownloadError, "Redirecionamento"):
                    download_clip("clip1", "42", "42", "app", "token", self.manifest, self.root / "incoming")
                self.assertFalse(any(path == "/forbidden" for path, _ in calls))
                redirect[0] = False
                output = download_clip("clip1", "42", "42", "app", "token", self.manifest, self.root / "incoming")
                self.assertEqual(output.read_bytes(), media)
                rights = json.loads(Path(str(output) + ".rights.json").read_text())
                self.assertEqual(rights["source_url"], "https://clips.twitch.tv/clip1")
                self.assertNotIn("token", json.dumps(rights))
                self.assertEqual(calls[-1], ("/media", None))
                with self.assertRaisesRegex(DownloadError, "existe"):
                    download_clip("clip1", "42", "42", "app", "token", self.manifest, self.root / "incoming")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
