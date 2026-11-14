"""Contratos do radar ASTRA, sem consultas externas ou downloads."""
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from clipforge.twitch import TwitchClient, TwitchDiscovery, TwitchError


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"TWITCH_DISCOVERY_MODE": "auto", "TWITCH_CATEGORY_IDS": "",
            "TWITCH_BROADCASTER_IDS": "", "TWITCH_GTA6_LAUNCH_AT": "2099-01-01T00:00:00Z",
            "TWITCH_TRENDING_CATEGORIES": "12"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def discovery(self, client=None):
        return TwitchDiscovery(self.root / "test.db", threading.RLock(), self.root, client)

    def test_default_trending_and_manual_launch_override(self):
        radar = self.discovery()
        self.assertEqual(radar.profile()["profile"], "trending")
        with patch.dict(os.environ, {"TWITCH_DISCOVERY_MODE": "gta6_only"}):
            self.assertEqual(radar.profile()["profile"], "gta6_only")
        with patch.dict(os.environ, {"TWITCH_TRENDING_CATEGORIES": "500"}):
            self.assertEqual(radar.profile()["category_limit"], 12)

    def test_configured_categories_deduplicate_and_persist_stream_state(self):
        class Client:
            def get_categories(self, ids):
                return [{"id": x, "name": "Game " + x} for x in ids]
            def get_clips(self, game_id, **kwargs):
                return [{"id": "clip-" + game_id, "url": "https://clips.twitch.tv/test",
                         "broadcaster_id": "42", "duration": 30}]
            def get_streams(self, ids):
                return [{"user_id": "42", "user_name": "Criador", "id": "live1",
                         "game_id": "1", "title": "Live real", "viewer_count": 8}]
        with patch.dict(os.environ, {"TWITCH_CATEGORY_IDS": "1,2,1", "TWITCH_BROADCASTER_IDS": "42,43"}):
            radar = self.discovery(Client())
            radar.refresh()
            radar.refresh()
            self.assertEqual(len(radar.list_candidates()), 2)
            self.assertEqual(radar.status()["live_streams"], 1)
            self.assertEqual(radar.status()["monitored_streamers"], 2)
            streams = {row["broadcaster_id"]: row for row in radar.list_streamers()}
            self.assertEqual(streams["42"]["is_live"], 1)
            self.assertEqual(streams["43"]["is_live"], 0)
            self.assertEqual(list(self.root.glob("*.mp4")), [])

    def test_invalid_configuration_is_explicit(self):
        with patch.dict(os.environ, {"TWITCH_CATEGORY_IDS": "1,invalid"}):
            with self.assertRaises(TwitchError):
                self.discovery(object()).refresh()

    def test_oauth_401_refreshes_once_and_does_not_leak_secret(self):
        client = TwitchClient("id", "secret")
        client._token = "expired"
        client._expires_at = float("inf")
        requests = []
        def send(req):
            requests.append(req)
            if len(requests) == 1:
                raise TwitchError("Twitch API HTTP 401", status_code=401)
            if req.full_url.endswith("/token"):
                return {"access_token": "fresh", "expires_in": 3600}
            return {"data": []}
        with patch.object(client, "_send", side_effect=send):
            self.assertEqual(client.get_top_categories(), [])
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[-1].get_header("Authorization"), "Bearer fresh")

    def test_streams_use_repeated_official_user_id_parameters(self):
        client = TwitchClient("id", "secret")
        with patch.object(client, "_token_value", return_value="token"), patch.object(client, "_send", return_value={"data": []}) as send:
            client.get_streams(["42", "43"])
        self.assertIn("user_id=42&user_id=43", send.call_args.args[0].full_url)

    def test_malformed_sources_are_typed_error(self):
        (self.root / "twitch_sources.json").write_text('[]')
        with self.assertRaises(TwitchError):
            self.discovery().sources()

class HelixTransportTests(unittest.TestCase):
    """Exercita urllib contra servidor HTTP local real sem publicar."""
    def test_http_token_refresh_and_real_json_roundtrip(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                calls.append(("POST", self.path))
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.reply(200, {"access_token": "fresh", "expires_in": 3600})
            def do_GET(self):
                calls.append(("GET", self.path))
                if self.headers.get("Authorization") != "Bearer fresh":
                    self.reply(401, {"message": "invalid token"})
                else:
                    self.reply(200, {"data": [{"id": "1", "name": "Just Chatting"}]})
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            client = TwitchClient("app", "private")
            client._token, client._expires_at = "expired", float("inf")
            with patch("clipforge.twitch.TWITCH_BASE", base), patch("clipforge.twitch.OAUTH_URL", base + "/token"):
                result = client.get_top_categories()
            self.assertEqual(result, [{"id": "1", "name": "Just Chatting"}])
            self.assertEqual([method for method, _ in calls], ["GET", "POST", "GET"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
