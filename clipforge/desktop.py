"""Windows desktop runtime for the existing GTA VI Clips Mission Control.

Uses pywebview/Edge WebView2 as a native shell over the existing loopback-only
backend. No remote hosting, no extra local web server process and no admin
rights required. User data stays outside the executable under LocalAppData.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from .core import Runtime
from .web import ThreadingHTTPServer, make_handler

APP_NAME = "GTA6Clips"
CONFIG_KEYS = frozenset({
    "AUTO_RENDER", "AUTO_SCAN", "AUTO_TRANSCRIBE", "ENABLE_SYNTHETIC_DEMO",
    "SMART_SCENES", "POLL_SECONDS", "TWITCH_ENABLED", "TWITCH_POLL_SECONDS",
    "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_GAME_ID",
    "WHISPER_MODEL", "WHISPER_LANGUAGE", "MAX_SOURCE_SECONDS",
})
DEFAULT_CONFIG = """# GTA VI Clips - configuracoes locais. Reinicie o app apos editar.
# Credenciais privadas: nao envie este arquivo para o GitHub.
AUTO_SCAN=1
AUTO_RENDER=1
SMART_SCENES=0
AUTO_TRANSCRIBE=0
ENABLE_SYNTHETIC_DEMO=0
WHISPER_MODEL=base
WHISPER_LANGUAGE=pt

# Crie um app em https://dev.twitch.tv/console/apps para usar descoberta real.
TWITCH_ENABLED=0
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
TWITCH_POLL_SECONDS=900
"""


def app_home() -> Path:
    """Persistent data folder, independent of installation/zip/unzip location."""
    override = os.environ.get("GTA6_CLIPS_HOME")
    if override:
        root = Path(override).expanduser()
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or
                    (Path.home() / "AppData" / "Local"))
        root = base / APP_NAME
    return root.resolve()


def initialize_settings(home: Path) -> Path:
    """Create an easy-to-edit local config once; never overwrite personal data."""
    home.mkdir(parents=True, exist_ok=True)
    conf = home / "config.env"
    if not conf.exists():
        # Exclusive creation protects user changes during two startup attempts.
        try:
            with conf.open("x", encoding="utf-8") as stream:
                stream.write(DEFAULT_CONFIG)
        except FileExistsError:
            pass
    if conf.is_symlink() or conf.stat().st_size > 65536:
        raise ValueError("Config is a link or exceeds 64 KiB")
    for line in conf.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in CONFIG_KEYS and "\x00" not in value:
            os.environ[key] = value.strip('"').strip("'")
    return conf


def find_ffmpeg_tools() -> dict[str, str]:
    """Prefer shipped portable binaries, fall back to a user-installed FFmpeg."""
    native = Path(__file__).resolve().parent / "bin"
    found = {}
    for name in ("ffmpeg", "ffprobe"):
        binary = native / (name + (".exe" if sys.platform == "win32" else ""))
        if binary.is_file():
            found[name] = str(binary)
        else:
            tool = shutil.which(name)
            if tool:
                found[name] = tool
    if len(found) == 2:
        bin_dir = str(Path(found["ffmpeg"]).parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return found


class DesktopBridge:
    """Explicit no-argument UI actions. No arbitrary filesystem paths accepted."""
    def __init__(self, home: Path):
        self.home = home

    def _open(self, path: Path):
        if sys.platform != "win32":
            return {"ok": False, "error": "Windows only"}
        if path != path.resolve() or not path.exists():
            return {"ok": False, "error": "Path unavailable"}
        os.startfile(str(path))  # noqa: S606 - only fixed user-owned locations
        return {"ok": True}

    def open_incoming(self):
        return self._open(self.home / "data" / "incoming")

    def open_rendered(self):
        return self._open(self.home / "data" / "rendered")

    def open_settings(self):
        return self._open(self.home / "config.env")


def start_backend(data_dir: Path, token: str):
    """Bind only 127.0.0.1 on an OS-assigned port; no remote exposure."""
    os.environ["HOST"] = "127.0.0.1"
    os.environ["DASHBOARD_TOKEN"] = token
    os.environ["CLIPS_DATA_DIR"] = str(data_dir)
    runtime = Runtime(data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runtime))
    runtime.start_polling()
    runtime.twitch.start_polling()
    thread = threading.Thread(
        target=server.serve_forever, name="gta6-local-http", daemon=True
    )
    thread.start()
    return server, runtime, thread


def shutdown_backend(server, runtime, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=8)
    runtime.executor.shutdown(wait=False)
    runtime.captions.stop()


def self_test(destination: Path | None = None) -> dict:
    """Safe headless validation of the frozen EXE, local HTTP API and FFmpeg."""
    def report(state: dict) -> None:
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(state, indent=2), encoding="utf-8")

    report({"phase": "entry", "status": "running"})
    with tempfile.TemporaryDirectory(prefix="gta6-desktop-qa-") as root:
        home = Path(root)
        tools = find_ffmpeg_tools()
        result = {
            "status": "fail", "ffmpeg": False, "ffprobe": False,
            "health": False, "protected_api": False,
        }
        for name in ("ffmpeg", "ffprobe"):
            path = tools.get(name)
            if not path:
                continue
            check = subprocess.run(
                [path, "-version"], capture_output=True, timeout=15,
                check=False
            )
            result[name] = check.returncode == 0
        report({**result, "phase": "native_tools"})
        token = secrets.token_urlsafe(32)
        server, runtime, thread = start_backend(home / "data", token)
        errors = []
        server.handle_error = lambda request, address: errors.append(traceback.format_exc())
        report({**result, "phase": "server_started"})
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/api/health", timeout=10) as resp:
                result["health"] = resp.status == 200
            report({**result, "phase": "health_checked"})
            request = urllib.request.Request(
                base + "/api/agents",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                data = json.load(resp)
                result["protected_api"] = (
                    resp.status == 200 and len(data.get("stages", [])) == 9
                )
            report({**result, "phase": "agents_checked"})
            try:
                urllib.request.urlopen(base + "/api/agents", timeout=10)
                result["protected_api"] = False
            except urllib.error.HTTPError as exc:
                result["protected_api"] &= exc.code == 401
            report({**result, "phase": "unauthorized_checked"})
        except Exception as exc:
            report({**result, "phase": "http_failure",
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "handler_error": errors[-1][-2800:] if errors else ""})
            raise
        finally:
            report({**result, "phase": "stopping_server",
                    "handler_error": errors[-1][-2800:] if errors else ""})
            shutdown_backend(server, runtime, thread)
            report({**result, "phase": "server_stopped"})
        result["status"] = ("pass" if
                            all(result.get(k) for k in (
                                "ffmpeg", "ffprobe", "health", "protected_api"
                            )) else "fail")
        report({**result, "phase": "complete"})
        return result


def run_desktop() -> None:
    if sys.platform != "win32":
        raise SystemExit("The packaged desktop app targets Windows 10/11")
    home = app_home()
    initialize_settings(home)
    find_ffmpeg_tools()
    import webview  # optional dependency; installed in Windows build only

    token = secrets.token_urlsafe(32)
    server, runtime, thread = start_backend(home / "data", token)
    url = (f"http://127.0.0.1:{server.server_port}/"
           f"#desktop-token={quote(token, safe='')}")
    try:
        window = webview.create_window(
            "GTA VI CLIPS | Mission Control", url=url,
            width=1480, height=910, min_size=(950, 630),
            background_color="#080d17", js_api=DesktopBridge(home),
        )
        # The native window uses Edge WebView2, available on most current
        # Windows 10/11 machines. Do not install anything without consent.
        webview.start(gui="edgechromium", debug=False)
    finally:
        shutdown_backend(server, runtime, thread)


def main() -> int:
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        destination = (Path(os.environ["GTA6_SELFTEST_PATH"])
                       if os.environ.get("GTA6_SELFTEST_PATH")
                       else Path(sys.argv[index + 1]) if len(sys.argv) > index + 1
                       else None)
        try:
            result = self_test(destination)
            return 0 if result["status"] == "pass" else 2
        except Exception as exc:
            if destination:
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous = {}
                if destination.is_file():
                    try:
                        previous = json.loads(destination.read_text(encoding="utf-8"))
                    except ValueError:
                        pass
                destination.write_text(
                    json.dumps({"phase": "exception", "status": "fail",
                                "last_phase": previous.get("phase"),
                                "server_trace": previous.get("handler_error", ""),
                                "type": type(exc).__name__,
                                "message": str(exc)[:700]}, indent=2),
                    encoding="utf-8",
                )
            return 3
    run_desktop()
    return 0
