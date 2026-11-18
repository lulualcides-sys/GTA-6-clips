"""Regressão: botão Atualizar falhava com o app antigo aberto.

O autoteste do EXE novo usava a porta fixa 8855. No Windows, o SO_REUSEADDR
do ThreadingHTTPServer deixa abrir uma porta já ocupada, e o autoteste falava
com o app ANTIGO (outro token) -> protected_api falso -> "A nova versão falhou
na validação; instalação preservada". Funciona no CI porque lá nada usa a 8855.
"""
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from clipforge import desktop


class _OldApp(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        self.send_response(401)
        self.end_headers()

    def log_message(self, *args):
        pass


class SelfTestPortTests(unittest.TestCase):
    def test_self_test_never_uses_preferred_port_of_running_app(self):
        old = HTTPServer(("127.0.0.1", 0), _OldApp)
        port = old.server_port
        thread = threading.Thread(target=old.serve_forever, daemon=True)
        thread.start()
        _OldApp.hits = 0
        try:
            with tempfile.TemporaryDirectory() as tmp, \
                    patch.dict(os.environ, {"NEXUS_LOCAL_PORT": str(port)}):
                report = Path(tmp) / "r.json"
                result = desktop.self_test(report)
                saved = json.loads(report.read_text(encoding="utf-8"))
        finally:
            old.shutdown()
            old.server_close()
        self.assertEqual(_OldApp.hits, 0, "autoteste falou com o app já aberto")
        self.assertTrue(result["protected_api"])
        self.assertEqual(saved["status"], "pass")
        self.assertEqual(saved["phase"], "complete")

    def test_self_test_requests_ephemeral_port(self):
        calls = []
        real = desktop.start_backend

        def spy(data_dir, token, port=None):
            calls.append(port)
            return real(data_dir, token, port=port)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(desktop, "start_backend", spy):
            desktop.self_test(Path(tmp) / "r.json")
        self.assertEqual(calls, [0])

    def test_explicit_port_zero_is_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, runtime, thread = desktop.start_backend(Path(tmp) / "d", "t" * 32, port=0)
            try:
                self.assertNotEqual(server.server_port, 8855)
            finally:
                desktop.shutdown_backend(server, runtime, thread)

    def test_local_server_does_not_share_ports_on_windows(self):
        self.assertFalse(desktop.LocalHTTPServer.allow_reuse_address and
                         desktop.sys.platform == "win32")
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.assertTrue(desktop.LocalHTTPServer.exclusive_on_windows)


if __name__ == "__main__":
    unittest.main()
