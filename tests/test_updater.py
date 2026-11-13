"""No-network regression tests for GitHub Releases update validation."""
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipforge.updater import (
    REPO, ASSET_NAME, UpdateError, UpdateService, _download,
    _extract_verified, check_latest, parse_version, validate_release
)
from desktop_update_helper import validate_paths
from clipforge.version import VERSION


def sample_release(version=None):
    if version is None:
        major,minor,patch = map(int, VERSION.split("."))
        version = f"v{major}.{minor}.{patch+1}"
    size = 5_000_000
    return {
        "tag_name": version, "draft": False, "prerelease": False,
        "assets": [{
            "name": ASSET_NAME, "size": size,
            "digest": "sha256:"+"a"*64,
            "browser_download_url": (
                f"https://github.com/{REPO}/releases/download/{version}/{ASSET_NAME}"
            ),
        }]
    }


def bundle_bytes(entries=None):
    if entries is None:
        entries = {
            "GTA6Clips.exe": b"sample-app",
            "GTA6ClipsUpdater.exe": b"sample-updater",
            "_internal/python312.dll": b"sample-dll",
        }
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as bundle:
        for name, value in entries.items():
            bundle.writestr(name, value)
    return memory.getvalue()


class ReleaseValidationTests(unittest.TestCase):
    def test_semantic_comparison(self):
        self.assertEqual(parse_version("v0.2.1"), (0,2,1))
        self.assertIsNone(parse_version("0.2.1-beta"))
        self.assertIsNone(parse_version("garbage"))
        self.assertTrue(validate_release(sample_release(), current="0.2.0")["available"])
        self.assertFalse(validate_release(sample_release("v0.2.0"), current="0.2.0")["available"])
        self.assertFalse(validate_release(sample_release("v0.1.9"), current="0.2.0")["available"])

    def test_missing_or_unverified_asset_is_rejected(self):
        x = sample_release()
        x["assets"][0]["digest"] = None
        with self.assertRaisesRegex(UpdateError, "SHA-256"):
            validate_release(x)
        x = sample_release()
        x["assets"][0]["browser_download_url"] = "https://evil.example/bad.exe"
        with self.assertRaisesRegex(UpdateError, "repositório"):
            validate_release(x)
        x = sample_release()
        x["assets"][0]["size"] = 100
        with self.assertRaisesRegex(UpdateError, "Tamanho"):
            validate_release(x)
        x = sample_release()
        x["prerelease"] = True
        with self.assertRaisesRegex(UpdateError, "estável"):
            validate_release(x)

    def test_no_release_is_not_reported_as_updated(self):
        from urllib.error import HTTPError
        with patch("clipforge.updater.urllib.request.urlopen",
                   side_effect=HTTPError("https://example",404,"not found",{},None)):
            outcome = check_latest()
        self.assertFalse(outcome["available"])
        self.assertIsNone(outcome["latest"])


class ArchiveAndStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/"GTA6Clips"
        self.home.mkdir()
        (self.home/"data").mkdir()
        (self.home/"data"/"clips.sqlite3").write_bytes(b"existing-user-database")
        (self.home/"config.env").write_text("TWITCH_CLIENT_SECRET=keep-private\n")

    def test_sha256_checked_during_download(self):
        payload = b"fake-zip-with-mismatched-digest"
        release = sample_release()
        release.update(size=len(payload), sha256="b"*64,
                       url="https://example.org/asset.zip")
        output=Path(self.tmp.name)/"incomplete.zip"
        with patch("clipforge.updater.urllib.request.urlopen",return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(UpdateError, "SHA-256"):
                _download(release,output)

    def test_zip_path_traversal_is_refused(self):
        content = bundle_bytes({
            "GTA6Clips.exe": b"file",
            "GTA6ClipsUpdater.exe": b"helper",
            "../secret.txt": b"malicious",
        })
        archive=Path(self.tmp.name)/"archive.zip"
        archive.write_bytes(content)
        with self.assertRaisesRegex(UpdateError, "caminho inseguro"):
            _extract_verified(archive,Path(self.tmp.name)/"test-dir")
        self.assertFalse((Path(self.tmp.name)/"secret.txt").is_file())

    def test_unpacked_bundle_has_real_expected_structure(self):
        archive=Path(self.tmp.name)/"archive.zip"
        archive.write_bytes(bundle_bytes())
        root=_extract_verified(archive,Path(self.tmp.name)/"payload")
        self.assertTrue((root/"GTA6Clips.exe").is_file())
        self.assertTrue((root/"GTA6ClipsUpdater.exe").is_file())

    def test_staging_preserves_database_and_settings(self):
        service=UpdateService(self.home)
        info=sample_release()
        validated=validate_release(info)
        data=bundle_bytes()
        def fake_download(_release, output):
            output.write_bytes(data)
        def fake_run(cmd,env,**kwargs):
            Path(env["GTA6_SELFTEST_PATH"]).write_text(json.dumps({
                "status":"pass","phase":"complete"
            }))
            return SimpleNamespace(returncode=0)
        with patch("clipforge.updater.check_latest",return_value=validated),\
             patch("clipforge.updater._download",side_effect=fake_download),\
             patch("clipforge.updater.subprocess.run",side_effect=fake_run):
            release, staged = service.stage()
        self.assertEqual(release["latest"], info["tag_name"])
        self.assertTrue((staged/"GTA6Clips.exe").exists())
        self.assertEqual((self.home/"data"/"clips.sqlite3").read_bytes(),b"existing-user-database")
        self.assertIn("keep-private",(self.home/"config.env").read_text())

    def test_windows_helper_refuses_persistent_data_folder_as_install(self):
        root=self.home
        updates=root/"updates"
        updates.mkdir()
        staged=updates/"ready-v0.3.0"
        staged.mkdir()
        (staged/"GTA6Clips.exe").write_bytes(b"exe")
        (staged/"GTA6ClipsUpdater.exe").write_bytes(b"helper")
        installed=root/"program"
        installed.mkdir()
        (installed/"GTA6Clips.exe").write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "persistent"):
            validate_paths(root,staged,installed)


if __name__ == "__main__":
    unittest.main()
