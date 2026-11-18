import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError

from clipforge import connection_check as cc
from clipforge.twitch import TwitchError


class ConnectionCheckTest(unittest.TestCase):
    def test_unconfigured_everything(self):
        runtime = SimpleNamespace(twitch=SimpleNamespace(client=None, client_id="", secret=""))
        with mock.patch.dict(os.environ, {}, clear=True):
            result = cc.check_all(runtime)
        self.assertEqual(set(result), {"twitch", "youtube", "tiktok", "postiz"})
        self.assertTrue(all(not r["configured"] and not r["ok"] for r in result.values()))

    def test_twitch_valid_and_gta6_lookup(self):
        client = mock.Mock()
        client.find_gta6_game.return_value = "123"
        runtime = SimpleNamespace(twitch=SimpleNamespace(client=client, client_id="a", secret="b"))
        with mock.patch.dict(os.environ, {}, clear=True):
            result = cc.check_twitch(runtime)
        self.assertTrue(result["ok"])
        self.assertEqual(result["gta6_category_id"], "123")

    def test_twitch_valid_but_no_gta6_category_yet(self):
        client = mock.Mock()
        client.find_gta6_game.side_effect = TwitchError("missing")
        runtime = SimpleNamespace(twitch=SimpleNamespace(client=client, client_id="a", secret="b"))
        with mock.patch.dict(os.environ, {}, clear=True):
            result = cc.check_twitch(runtime)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["gta6_category_id"])

    def test_twitch_bad_secret(self):
        client = mock.Mock()
        client._token_value.side_effect = TwitchError("Twitch API HTTP 400", 400)
        runtime = SimpleNamespace(twitch=SimpleNamespace(client=client, client_id="a", secret="b"))
        result = cc.check_twitch(runtime)
        self.assertFalse(result["ok"])
        self.assertTrue(result["configured"])

    def test_youtube_rejected_token_never_leaks(self):
        err = HTTPError("u", 401, "no", {}, BytesIO(b""))
        with mock.patch.dict(os.environ, {"YOUTUBE_ACCESS_TOKEN": "tok-SECRET"}), \
                mock.patch.object(cc, "request_json", side_effect=err):
            result = cc.check_youtube()
        self.assertFalse(result["ok"])
        self.assertNotIn("tok-SECRET", str(result))
        self.assertIn("401", result["detail"])

    def test_youtube_ok(self):
        with mock.patch.dict(os.environ, {"YOUTUBE_ACCESS_TOKEN": "t"}), \
                mock.patch.object(cc, "request_json",
                                  return_value=({"items": [{"snippet": {"title": "Nexus"}}]}, {})):
            result = cc.check_youtube()
        self.assertTrue(result["ok"])
        self.assertIn("Nexus", result["detail"])

    def test_tiktok_error_code(self):
        with mock.patch.dict(os.environ, {"TIKTOK_ACCESS_TOKEN": "t"}), \
                mock.patch.object(cc, "request_json",
                                  return_value=({"error": {"code": "access_token_invalid"}}, {})):
            self.assertFalse(cc.check_tiktok()["ok"])

    def test_postiz_missing_channel(self):
        env = {"POSTIZ_API_KEY": "k", "POSTIZ_YOUTUBE_INTEGRATION_ID": "yt1"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("clipforge.postiz_connector.api_json", return_value=[{"id": "other"}]):
            result = cc.check_postiz()
        self.assertFalse(result["ok"])
        self.assertIn("YouTube", result["detail"])

    def test_postiz_ok(self):
        env = {"POSTIZ_API_KEY": "k", "POSTIZ_YOUTUBE_INTEGRATION_ID": "yt1"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("clipforge.postiz_connector.api_json", return_value=[{"id": "yt1"}]):
            self.assertTrue(cc.check_postiz()["ok"])


if __name__ == "__main__":
    unittest.main()
