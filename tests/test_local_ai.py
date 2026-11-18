import io
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from clipforge.local_ai import LocalAI, OLLAMA_INSTALLER_URL


class FakeResponse(io.BytesIO):
    def __init__(self, data=b"", headers=None, lines=None, url="https://ollama.com/x"):
        super().__init__(data)
        self.headers = headers or {}
        self._lines = lines
        self._url = url

    def __iter__(self):
        return iter(self._lines if self._lines is not None else [])

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOllama:
    """Simula a API local do Ollama e o download do instalador."""

    def __init__(self, running=False, models=None, installer=b"MZ" + b"0" * 2_000_000,
                 pull_lines=None):
        self.running = running
        self.models = list(models or [])
        self.installer = installer
        self.pull_lines = pull_lines
        self.requests = []

    def __call__(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        self.requests.append(url)
        if url == OLLAMA_INSTALLER_URL:
            return FakeResponse(self.installer, {"Content-Length": str(len(self.installer))})
        if not self.running:
            raise OSError("connection refused")
        if url.endswith("/api/tags"):
            body = {"models": [{"name": m} for m in self.models]}
            return FakeResponse(json.dumps(body).encode())
        if url.endswith("/api/pull"):
            model = json.loads(request.data)["model"]
            lines = self.pull_lines
            if lines is None:
                lines = [b'{"status":"pulling manifest"}',
                         b'{"status":"downloading","total":100,"completed":50}',
                         b'{"status":"success"}']
                self.models.append(model)
            return FakeResponse(lines=lines)
        raise AssertionError(url)


def wait(ai, seconds=5):
    deadline = time.time() + seconds
    while ai.busy() and time.time() < deadline:
        time.sleep(0.01)
    return ai.status()["job"]


class LocalAITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.free = SimpleNamespace(free=100 * 1024 ** 3)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, fake, platform="win32", run=None, popen=None, disk=None):
        return LocalAI(self.home, opener=fake, platform=platform,
                       run=run or mock.Mock(), popen=popen or mock.Mock(),
                       sleep=lambda _s: None,
                       disk_usage=lambda _p: disk or self.free)

    def test_status_reports_missing_ollama(self):
        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            status = self.make(FakeOllama()).status()
        self.assertFalse(status["ollama_installed"])
        self.assertFalse(status["model_ready"])
        self.assertTrue(status["can_install"])
        self.assertIn("llama3.1:8b", [m["name"] for m in status["catalog"]])

    def test_rejects_model_outside_catalog(self):
        ai = self.make(FakeOllama(running=True))
        with self.assertRaises(ValueError):
            ai.prepare("evil/model; rm -rf")

    def test_pull_model_when_ollama_running(self):
        fake = FakeOllama(running=True)
        ai = self.make(fake)
        ai.prepare("llama3.1:8b")
        job = wait(ai)
        self.assertEqual(job["state"], "done", job)
        self.assertTrue(ai.status()["model_ready"])

    def test_skip_pull_when_model_present(self):
        fake = FakeOllama(running=True, models=["llama3.1:8b"])
        ai = self.make(fake)
        ai.prepare("llama3.1:8b")
        self.assertEqual(wait(ai)["state"], "done")
        self.assertFalse(any(u.endswith("/api/pull") for u in fake.requests))

    def test_pull_error_is_reported(self):
        fake = FakeOllama(running=True, pull_lines=[b'{"error":"disk full"}'])
        ai = self.make(fake)
        ai.prepare("llama3.1:8b")
        job = wait(ai)
        self.assertEqual(job["state"], "failed")
        self.assertIn("disk full", job["error"])

    def test_pull_without_success_fails(self):
        fake = FakeOllama(running=True, pull_lines=[b'{"status":"downloading"}'])
        ai = self.make(fake)
        ai.prepare("llama3.2:3b")
        self.assertEqual(wait(ai)["state"], "failed")

    def test_insufficient_disk_blocks_pull(self):
        fake = FakeOllama(running=True)
        ai = self.make(fake, disk=SimpleNamespace(free=1 * 1024 ** 3))
        ai.prepare("llama3.1:8b")
        job = wait(ai)
        self.assertEqual(job["state"], "failed")
        self.assertIn("Espaço insuficiente", job["error"])

    def test_full_install_on_windows_verifies_signature_then_installs(self):
        fake = FakeOllama()
        exe = self.home / "Programs" / "Ollama" / "ollama.exe"
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "powershell":
                self.assertTrue(Path(kwargs["env"]["NEXUS_VERIFY_PATH"]).is_file())
                return SimpleNamespace(returncode=0, stdout="Valid\nCN=Ollama Inc., O=Ollama Inc., C=US\n")
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_bytes(b"exe")
            return SimpleNamespace(returncode=0, stdout="")

        def popen(cmd, **kwargs):
            self.assertEqual(cmd, [str(exe), "serve"])
            self.assertEqual(kwargs["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
            fake.running = True

        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            ai = self.make(fake, run=run, popen=popen)
            ai.prepare("llama3.1:8b")
            job = wait(ai)
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(calls[0][0], "powershell")
        self.assertIn("/SILENT", calls[1])
        self.assertFalse((self.home / "extensions" / "local-ai" / "OllamaSetup.exe").exists())

    def test_invalid_signature_blocks_installer(self):
        fake = FakeOllama()
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="NotSigned\n\n")

        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            ai = self.make(fake, run=run)
            ai.prepare("llama3.1:8b")
            job = wait(ai)
        self.assertEqual(job["state"], "failed")
        self.assertIn("Assinatura", job["error"])
        self.assertEqual(len(calls), 1, "instalador não pode executar sem assinatura válida")
        self.assertFalse(any((self.home / "extensions" / "local-ai").glob("*.exe")))

    def test_wrong_publisher_blocks_installer(self):
        fake = FakeOllama()
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="Valid\nCN=Someone Else, O=Ollama-ish\n"))
        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            ai = self.make(fake, run=run)
            ai.prepare("llama3.1:8b")
            self.assertEqual(wait(ai)["state"], "failed")
        self.assertEqual(run.call_count, 1)

    def test_truncated_installer_is_rejected(self):
        fake = FakeOllama(installer=b"tiny")
        run = mock.Mock()
        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            ai = self.make(fake, run=run)
            ai.prepare("llama3.1:8b")
            self.assertEqual(wait(ai)["state"], "failed")
        run.assert_not_called()

    def test_non_windows_without_ollama_explains(self):
        with mock.patch("clipforge.local_ai.shutil.which", return_value=None):
            ai = self.make(FakeOllama(), platform="linux")
            with self.assertRaises(ValueError):
                ai.prepare("llama3.1:8b")

    def test_ensure_running_starts_installed_ollama(self):
        fake = FakeOllama()
        popen = mock.Mock(side_effect=lambda *a, **k: setattr(fake, "running", True))
        with mock.patch("clipforge.local_ai.shutil.which", return_value="/usr/bin/ollama"):
            ai = self.make(fake, platform="linux", popen=popen)
            self.assertTrue(ai.ensure_running())
        popen.assert_called_once()

    def test_ensure_running_never_installs(self):
        run = mock.Mock()
        with mock.patch("clipforge.local_ai.shutil.which", return_value=None), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.home)}):
            ai = self.make(FakeOllama(), run=run)
            self.assertFalse(ai.ensure_running())
        run.assert_not_called()

    def test_single_job_at_a_time(self):
        fake = FakeOllama(running=True)
        ai = self.make(fake)
        with ai.lock:
            ai.job = {"state": "running"}
        with self.assertRaises(ValueError):
            ai.prepare("llama3.1:8b")


class LocalAIWebTest(unittest.TestCase):
    def test_prepare_requires_owner_token(self):
        import os
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from clipforge.core import Runtime
        from clipforge.web import make_handler
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"DASHBOARD_TOKEN": "secret-token", "AUTO_SCAN": "0"}):
            runtime = Runtime(Path(tmp))
            runtime.local_ai.prepare = mock.Mock(return_value={"state": "running"})
            runtime.local_ai.status = mock.Mock(return_value={"model_ready": False})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runtime))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                def call(path, method="GET", token=None, body=None):
                    data = json.dumps(body).encode() if body is not None else None
                    req = urllib.request.Request(base + path, data=data, method=method)
                    if data is not None:
                        req.add_header("Content-Type", "application/json")
                    if token:
                        req.add_header("Authorization", "Bearer " + token)
                    try:
                        with urllib.request.urlopen(req, timeout=5) as r:
                            return r.status, json.loads(r.read())
                    except urllib.error.HTTPError as e:
                        return e.code, json.loads(e.read())

                self.assertEqual(call("/api/local-ai")[0], 401)
                self.assertEqual(call("/api/local-ai", token="secret-token")[0], 200)
                self.assertEqual(call("/api/local-ai/prepare", "POST", body={"model": "llama3.1:8b"})[0], 401)
                status, body = call("/api/local-ai/prepare", "POST", "secret-token", {"model": "llama3.1:8b"})
                self.assertEqual(status, 202)
                runtime.local_ai.prepare.assert_called_once_with("llama3.1:8b")
                self.assertIs(runtime.autoclip_bridge.local_ai, runtime.local_ai)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
