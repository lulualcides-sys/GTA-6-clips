"""Desktop runtime quality gates; no pywebview dependency on Linux test jobs."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from clipforge.desktop import (
    DesktopBridge, app_home, initialize_settings, start_backend, shutdown_backend
)


class LocalDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "appdata"
        self.env = patch.dict(os.environ, {
            "GTA6_CLIPS_HOME": str(self.home),
            "AUTO_SCAN": "0", "AUTO_RENDER": "0", "AUTO_TRANSCRIBE": "0",
            "TWITCH_ENABLED": "0", "TWITCH_CLIENT_ID": "",
            "TWITCH_CLIENT_SECRET": "", "ENABLE_SYNTHETIC_DEMO": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_gui_loader_error_describes_both_pythonnet_and_webview2(self):
        from desktop_launcher import startup_error_message
        for error_text in (
            "Failed to resolve Python.Runtime.Loader.Initialize",
            "Microsoft.Web.WebView2.Core.dll HRESULT: 0x80131515",
        ):
            with self.subTest(error=error_text):
                message = startup_error_message(RuntimeError(error_text))
                self.assertIn("Corrigir-e-Abrir-GTA6Clips.cmd", message)
                self.assertIn("_internal", message)
        self.assertIn("LEIA-ME", startup_error_message(RuntimeError("other")))

    def test_stores_files_in_user_profile_not_install_directory(self):
        self.assertEqual(app_home(), self.home.resolve())
        path = initialize_settings(self.home)
        self.assertEqual(path, self.home / "config.env")
        self.assertTrue(path.is_file())
        self.assertIn("TWITCH_ENABLED=1", path.read_text())

    def test_config_is_not_overwritten_and_only_allowlisted_values_loaded(self):
        settings = initialize_settings(self.home)
        settings.write_text(
            "TWITCH_ENABLED=1\nUNTRUSTED_VARIABLE=HACK\nWHISPER_MODEL=small\n",
            encoding="utf-8",
        )
        os.environ.pop("UNTRUSTED_VARIABLE", None)
        initialize_settings(self.home)
        self.assertEqual(os.environ.get("TWITCH_ENABLED"), "1")
        self.assertEqual(os.environ.get("WHISPER_MODEL"), "small")
        self.assertNotIn("UNTRUSTED_VARIABLE", os.environ)
        self.assertEqual(settings.read_text().count("TWITCH_ENABLED=1"), 1)

    def test_config_loads_twitch_monitoring_controls(self):
        settings = initialize_settings(self.home)
        values = {"TWITCH_DISCOVERY_MODE": "trending", "TWITCH_CATEGORY_IDS": "1,2",
                  "TWITCH_BROADCASTER_IDS": "3,4", "TWITCH_TRENDING_CATEGORIES": "12",
                  "TWITCH_CLIPS_PER_CATEGORY": "10", "TWITCH_LOOKBACK_HOURS": "24"}
        settings.write_text("\n".join(f"{k}={v}" for k, v in values.items()))
        with patch.dict(os.environ, {}, clear=True):
            initialize_settings(self.home)
            for key, value in values.items():
                self.assertEqual(os.environ.get(key), value)

    def test_private_publication_settings_load_without_allowing_arbitrary_environment(self):
        settings = initialize_settings(self.home)
        values = {"PUBLISHING_ENABLED": "1", "PUBLISHING_AUTO_ENABLED": "0",
                  "PUBLISHING_DAILY_LIMIT": "3", "PUBLISHING_MAX_POLLS": "12",
                  "YOUTUBE_ACCESS_TOKEN": "synthetic-youtube-test-token",
                  "TIKTOK_ACCESS_TOKEN": "synthetic-tiktok-test-token"}
        original = "\n".join(f"{k}={v}" for k, v in values.items()) + "\nPYTHONPATH=untrusted\n"
        settings.write_text(original, encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            result = initialize_settings(self.home)
            for key, value in values.items():
                self.assertEqual(os.environ.get(key), value)
            self.assertNotIn("PYTHONPATH", os.environ)
            self.assertEqual(result, self.home / "config.env")
        self.assertEqual(settings.read_text(encoding="utf-8"), original)

    def test_new_desktop_publication_settings_are_disabled_and_have_no_tokens(self):
        with patch.dict(os.environ, {}, clear=True):
            initialize_settings(self.home)
            self.assertEqual(os.environ.get("PUBLISHING_ENABLED"), "0")
            self.assertEqual(os.environ.get("PUBLISHING_AUTO_ENABLED"), "0")
            self.assertEqual(os.environ.get("YOUTUBE_ACCESS_TOKEN"), "")
            self.assertEqual(os.environ.get("TIKTOK_ACCESS_TOKEN"), "")

    def test_config_rejects_symlink(self):
        initialize_settings(self.home)
        settings = self.home / "config.env"
        settings.unlink()
        settings.symlink_to(self.home / "other.env")
        with self.assertRaisesRegex(ValueError, "link"):
            initialize_settings(self.home)

    def test_bridge_does_not_open_arbitrary_user_supplied_path(self):
        bridge = DesktopBridge(self.home)
        self.assertFalse(hasattr(bridge, "open_path"))
        self.assertEqual(bridge.open_settings()["ok"], False)

    def test_backend_binds_loopback_and_requires_random_token(self):
        os.environ["HOST"] = "0.0.0.0"
        token = "test-token-random-0123456789"
        server, runtime, thread = start_backend(self.home / "data", token)
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/api/health", timeout=3) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/api/clips", timeout=3)
            self.assertEqual(ctx.exception.code, 401)
            request = urllib.request.Request(
                base + "/api/agents",
                headers={"Authorization": "Bearer " + token}
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                agents = json.load(response)
            self.assertEqual(len(agents["stages"]), 9)
            self.assertFalse(agents["publishing_connected"])
            self.assertEqual(agents["counts"]["total"], 0)
        finally:
            shutdown_backend(server, runtime, thread)

    def test_publication_worker_starts_without_dashboard_request_and_stops(self):
        with patch.dict(os.environ, {'PUBLISHING_ENABLED': '1',
                                     'YOUTUBE_ACCESS_TOKEN': '', 'TIKTOK_ACCESS_TOKEN': ''}):
            server, runtime, thread = start_backend(self.home / 'data', 'test-private-token')
            try:
                self.assertTrue(hasattr(runtime, 'publishing'))
                self.assertTrue(runtime.publishing._thread.is_alive())
            finally:
                shutdown_backend(server, runtime, thread)
            runtime.publishing._thread.join(timeout=3)
            self.assertFalse(runtime.publishing._thread.is_alive())

    def test_gui_http_server_works_without_any_stderr_console(self):
        # PyInstaller --windowed normally sets sys.stderr=None on Windows.
        # The standard BaseHTTPRequestHandler logger must not crash requests.
        token = "desktop-no-console-security-token-012345"
        server, runtime, thread = start_backend(self.home / "data", token)
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/health"
            with patch("sys.stderr", None):
                with urllib.request.urlopen(url, timeout=4) as response:
                    self.assertEqual(response.status, 200)
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/agents",
                    headers={"Authorization": "Bearer " + token},
                )
                with urllib.request.urlopen(request, timeout=4) as response:
                    self.assertEqual(response.status, 200)
        finally:
            shutdown_backend(server, runtime, thread)

    def test_private_twitch_onboarding_checks_oauth_before_local_save(self):
        from clipforge.desktop import DesktopBridge
        bridge = DesktopBridge(self.home)
        client_id, secret = "a"*30, "b"*30
        with patch("clipforge.twitch.TwitchClient.get_top_categories",
                   return_value=[{"id":"1","name":"Just Chatting"}]) as query:
            response = bridge.save_twitch_credentials(client_id, secret)
        self.assertTrue(response["ok"])
        self.assertTrue(response["restart_required"])
        query.assert_called_once_with(limit=1)
        config = (self.home/"config.env").read_text(encoding="utf-8")
        self.assertIn("TWITCH_ENABLED=1",config)
        self.assertIn("TWITCH_CLIENT_ID="+client_id,config)
        self.assertIn("TWITCH_CLIENT_SECRET="+secret,config)
        self.assertIn("TWITCH_GTA6_LAUNCH_AT=2026-11-19",config)
        self.assertNotIn(secret,str(response))

    def test_twitch_credentials_take_effect_in_running_monitor(self):
        from clipforge.core import Runtime
        from clipforge.desktop import DesktopBridge
        runtime = Runtime(self.home / "data")
        self.addCleanup(runtime.executor.shutdown, wait=True)
        self.assertFalse(runtime.twitch.status()["configured"])
        bridge = DesktopBridge(self.home, runtime)
        client_id, client_secret = "c"*30, "d"*30
        with patch("clipforge.twitch.TwitchClient.get_top_categories",
                   return_value=[{"id":"1","name":"Just Chatting"}]), \
             patch.object(runtime.twitch, "start_polling") as polling:
            reply = bridge.save_twitch_credentials(client_id, client_secret)
            self.assertTrue(reply["ok"])
            self.assertFalse(reply["restart_required"])
            polling.assert_called_once()
        current = runtime.twitch.status()
        self.assertTrue(current["configured"])
        self.assertTrue(current["auto_monitoring"])
        self.assertEqual(runtime.twitch.client_id, client_id)
        self.assertEqual(runtime.twitch.secret, client_secret)
        self.assertNotIn(client_secret, str(reply))
        self.assertIn("TWITCH_ENABLED=1", (self.home/"config.env").read_text())
        self.assertEqual(os.environ["TWITCH_ENABLED"], "1")

    def test_invalid_or_unreachable_twitch_credentials_are_not_saved(self):
        from clipforge.desktop import DesktopBridge
        from clipforge.twitch import TwitchError
        bridge = DesktopBridge(self.home)
        self.assertFalse(bridge.save_twitch_credentials("x\\nTWITCH_ENABLED=1","bad")["ok"])
        with patch("clipforge.twitch.TwitchClient.get_top_categories",
                   side_effect=TwitchError("OAuth 401")):
            outcome = bridge.save_twitch_credentials("a"*30, "b"*30)
        self.assertFalse(outcome["ok"])
        self.assertFalse((self.home/"config.env").exists())

    def test_initialize_settings_cannot_overwrite_existing_user_data(self):
        settings = initialize_settings(self.home)
        settings.write_text("AUTO_SCAN=0\n", encoding="utf-8")
        initialize_settings(self.home)
        self.assertEqual(settings.read_text(), "AUTO_SCAN=0\n")


class SelfTestIsolationTests(unittest.TestCase):
    """O atualizador repassa o ambiente do app aberto; o teste não pode usá-lo."""

    USER_ENV = {"TWITCH_CLIENT_ID": "real", "TWITCH_CLIENT_SECRET": "real-secret",
                "TWITCH_ENABLED": "1", "TWITCH_AUTO_DOWNLOAD": "1",
                "TWITCH_PUBLIC_DOWNLOAD": "1", "YOUTUBE_API_KEY": "real-key",
                "YOUTUBE_PUBLIC_DOWNLOAD": "1", "AUTO_SCAN": "1", "AUTO_RENDER": "1",
                "PUBLISHING_ENABLED": "1", "POSTIZ_API_KEY": "k", "NEXUS_LOCAL_PORT": "8855",
                "GTA6_SELFTEST_PATH": "/keep/me"}

    def test_isolation_removes_user_settings_and_disables_automation(self):
        from clipforge.desktop import isolate_selftest_environment
        with patch.dict(os.environ, self.USER_ENV):
            isolate_selftest_environment()
            for key in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_PUBLIC_DOWNLOAD",
                        "YOUTUBE_API_KEY", "YOUTUBE_PUBLIC_DOWNLOAD", "POSTIZ_API_KEY"):
                self.assertNotIn(key, os.environ)
            self.assertEqual(os.environ["TWITCH_ENABLED"], "0")
            self.assertEqual(os.environ["AUTO_SCAN"], "0")
            self.assertEqual(os.environ["PUBLISHING_ENABLED"], "0")
            self.assertEqual(os.environ["GTA6_SELFTEST_PATH"], "/keep/me")

    def test_selftest_passes_with_real_user_environment(self):
        from clipforge.desktop import self_test
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, self.USER_ENV):
            report = Path(tmp) / "report.json"
            result = self_test(report)
            saved = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(saved["phase"], "complete")


class AutoClipQuickCheckTests(unittest.TestCase):
    """Atualização no PC confere a estrutura; o CI roda o motor completo."""

    def _runtime(self, root: Path, skip: str = "") -> Path:
        files = ["python.exe", "nexus_autoclip_runner.py", "AUTOCLIP-LICENSE.txt",
                 "Lib/site-packages/autoclip/cli.py"]
        for rel in files:
            if rel == skip:
                continue
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x")
        for pkg in ("faster_whisper", "mediapipe", "scenedetect"):
            if pkg != skip:
                (root / "Lib" / "site-packages" / pkg).mkdir(parents=True, exist_ok=True)
        return root

    def test_complete_runtime_passes(self):
        from clipforge.desktop import autoclip_runtime_complete
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(autoclip_runtime_complete(self._runtime(Path(tmp))))

    def test_missing_pieces_fail(self):
        from clipforge.desktop import autoclip_runtime_complete
        for missing in ("python.exe", "Lib/site-packages/autoclip/cli.py", "mediapipe"):
            with tempfile.TemporaryDirectory() as tmp:
                self.assertFalse(autoclip_runtime_complete(self._runtime(Path(tmp), missing)), missing)

    def test_full_mode_only_when_ci_flag_set(self):
        from clipforge.desktop import full_selftest
        with patch.dict(os.environ, {"GTA6_SELFTEST_FULL": "1"}):
            self.assertTrue(full_selftest())
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(full_selftest())


if __name__ == "__main__":
    unittest.main()
