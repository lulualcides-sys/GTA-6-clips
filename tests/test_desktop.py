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

    def test_initialize_settings_cannot_overwrite_existing_user_data(self):
        settings = initialize_settings(self.home)
        settings.write_text("AUTO_SCAN=0\n", encoding="utf-8")
        initialize_settings(self.home)
        self.assertEqual(settings.read_text(), "AUTO_SCAN=0\n")


if __name__ == "__main__":
    unittest.main()
