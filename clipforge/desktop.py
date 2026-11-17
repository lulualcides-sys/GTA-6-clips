"""Windows desktop runtime for the existing GTA VI Clips Mission Control.

Uses pywebview/Edge WebView2 as a native shell over the existing loopback-only
backend. No remote hosting, no extra local web server process and no admin
rights required. User data stays outside the executable under LocalAppData.
"""
from __future__ import annotations

import json
import os
import re
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
from .updater import UpdateService, UpdateError
from .version import VERSION
from .web import ThreadingHTTPServer, make_handler, start_publishing, stop_publishing

APP_NAME = "GTA6Clips"
CONFIG_KEYS = frozenset({
    "AUTO_RENDER", "AUTO_SCAN", "AUTO_TRANSCRIBE", "ENABLE_SYNTHETIC_DEMO",
    "SMART_SCENES", "POLL_SECONDS", "TWITCH_ENABLED", "TWITCH_POLL_SECONDS",
    "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_GAME_ID",
    "TWITCH_USER_ACCESS_TOKEN", "TWITCH_REFRESH_TOKEN", "TWITCH_EDITOR_ID",
    "TWITCH_AUTO_DOWNLOAD", "TWITCH_AUTO_BATCH",
    "TWITCH_AUTO_MIN_SCORE", "TWITCH_AUTO_GTA6_ONLY",
    "TWITCH_AUTO_PER_CREATOR", "TWITCH_GTA6_WINDOW_HOURS",
    "TWITCH_GTA6_PAGES_PER_WINDOW",
    "AUTOCLIP_ENABLED", "AUTOCLIP_AUTO_IMPORT", "AUTOCLIP_PROVIDER",
    "AUTOCLIP_OLLAMA_MODEL",
    "TWITCH_GTA6_LAUNCH_AT", "TWITCH_DISCOVERY_MODE", "TWITCH_CATEGORY_IDS",
    "TWITCH_BROADCASTER_IDS", "TWITCH_GTA5_GAME_ID", "TWITCH_TRENDING_CATEGORIES",
    "TWITCH_CLIPS_PER_CATEGORY", "TWITCH_LOOKBACK_HOURS",
    "WHISPER_MODEL", "WHISPER_LANGUAGE", "MAX_SOURCE_SECONDS",
    "PUBLISHING_ENABLED", "PUBLISHING_AUTO_ENABLED", "PUBLISHING_DAILY_LIMIT",
    "PUBLISHING_MAX_POLLS", "YOUTUBE_ACCESS_TOKEN", "TIKTOK_ACCESS_TOKEN",
})
DEFAULT_CONFIG = """# GTA VI Clips - configuracoes locais. Reinicie o app apos editar.
# Credenciais privadas: nao envie este arquivo para o GitHub.
AUTO_SCAN=1
AUTO_RENDER=1
# Motor AutoClip real incluido no pacote Windows; nunca usar FFmpeg como editor.
AUTOCLIP_ENABLED=1
AUTOCLIP_AUTO_IMPORT=1
AUTOCLIP_PROVIDER=ollama
AUTOCLIP_OLLAMA_MODEL=
SMART_SCENES=0
AUTO_TRANSCRIBE=0
ENABLE_SYNTHETIC_DEMO=0
WHISPER_MODEL=base
WHISPER_LANGUAGE=pt

# Crie um app em https://dev.twitch.tv/console/apps para usar descoberta real.
TWITCH_ENABLED=1
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
# Permissoes de download para canal proprio/editor (via OAuth especifico):
TWITCH_AUTO_DOWNLOAD=1
# Ate 12 downloads autorizados por busca; apenas candidatos com nota alta
TWITCH_AUTO_BATCH=5
TWITCH_AUTO_MIN_SCORE=78
TWITCH_AUTO_PER_CREATOR=2
TWITCH_AUTO_GTA6_ONLY=1
TWITCH_GTA6_WINDOW_HOURS=12
TWITCH_GTA6_PAGES_PER_WINDOW=3
TWITCH_EDITOR_ID=
TWITCH_USER_ACCESS_TOKEN=
TWITCH_REFRESH_TOKEN=
TWITCH_POLL_SECONDS=900
# Até o lançamento, categorias populares; depois, apenas GTA VI:
TWITCH_GTA6_LAUNCH_AT=2026-11-19T03:00:00+00:00

# Publicação desativada por padrão. Ative somente com direitos e contas válidas.
# Tokens OAuth são privados; obtenha-os pelos fluxos oficiais das plataformas.
# Estes campos não implementam login nem renovação automática de tokens.
PUBLISHING_ENABLED=0
PUBLISHING_AUTO_ENABLED=0
PUBLISHING_DAILY_LIMIT=5
PUBLISHING_MAX_POLLS=20
YOUTUBE_ACCESS_TOKEN=
TIKTOK_ACCESS_TOKEN=
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
    package = Path(__file__).resolve().parent
    roots = [
        package / "bin",
        Path(getattr(sys, "_MEIPASS", package.parent)) / "clipforge" / "bin",
        Path(sys.executable).resolve().parent / "_internal" / "clipforge" / "bin",
        Path(sys.executable).resolve().parent / "clipforge" / "bin",
    ]
    found = {}
    for name in ("ffmpeg", "ffprobe"):
        binary_name = name + (".exe" if sys.platform == "win32" else "")
        for folder in roots:
            binary = folder / binary_name
            if binary.is_file():
                found[name] = str(binary)
                break
        if name not in found:
            tool = shutil.which(name)
            if tool:
                found[name] = tool
    if len(found) == 2:
        bin_dir = str(Path(found["ffmpeg"]).parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return found


class DesktopBridge:
    """Explicit no-argument UI actions. No arbitrary filesystem paths accepted."""
    def __init__(self, home: Path, runtime: Runtime | None = None):
        self.home = home
        self._runtime = runtime
        self._twitch_oauth = None
        self.updater = UpdateService(home)

    def check_updates(self):
        """Check signed-by-release-digest official builds; no installation."""
        try:
            return {"ok": True, "version": VERSION, **self.updater.check()}
        except UpdateError as exc:
            return {"ok": False, "version": VERSION,
                    "error": str(exc)[:200]}

    def install_update(self):
        """Explicit user action: verify, stage, then restart via helper."""
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return {"ok": False, "error": "Requer o aplicativo Windows compilado"}
        installed = Path(sys.executable).resolve().parent
        helper = installed / "GTA6ClipsUpdater.exe"
        if not helper.is_file():
            return {"ok": False, "error": "Atualizador ausente nesta instalação"}
        try:
            release, staged = self.updater.stage()
            # Helper must run OUTSIDE the old install folder, otherwise
            # Windows keeps it locked while trying to replace the directory.
            helper_copy = self.home / "updates" / (
                "GTA6ClipsUpdater-" + secrets.token_hex(5) + ".exe"
            )
            shutil.copy2(helper, helper_copy)
            subprocess.Popen([
                str(helper_copy), "--apply",
                "--home", str(self.home),
                "--staged", str(staged),
                "--installed", str(installed),
                "--parent-pid", str(os.getpid()),
            ], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True)
            # Give the JS caller a moment to receive the status, then
            # close the UI and let the helper update after this EXE exits.
            def close_window():
                try:
                    import webview
                    if webview.windows:
                        webview.windows[0].destroy()
                except Exception:
                    pass
            threading.Timer(1.2, close_window).start()
            return {"ok": True, "restarting": True,
                    "latest": release["latest"]}
        except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": str(exc)[:220]}

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

    def save_twitch_credentials(self, client_id: str, client_secret: str) -> dict:
        """User-supplied OAuth app credentials saved only in LocalAppData.

        Called from the desktop-only pywebview bridge, never through the HTTP API.
        Reconfigures the running monitor immediately when a Runtime is attached.
        No token or secret is returned to JavaScript.
        """
        if not isinstance(client_id, str) or not isinstance(client_secret, str):
            return {"ok": False, "error": "Client ID e Secret devem ser textos"}
        client_id, client_secret = client_id.strip(), client_secret.strip()
        if not re.fullmatch(r"[A-Za-z0-9]{10,80}", client_id):
            return {"ok": False, "error": "Client ID inválido; confira o Twitch Developer Console"}
        if not re.fullmatch(r"[A-Za-z0-9]{10,160}", client_secret):
            return {"ok": False, "error": "Client Secret inválido; confira o Twitch Developer Console"}
        # Check the official Twitch OAuth application credentials BEFORE saving.
        # Credentials are never returned in the API response or written to logs.
        from .twitch import TwitchClient, TwitchError
        try:
            client = TwitchClient(client_id, client_secret)
            client.get_top_categories(limit=1)
        except TwitchError:
            return {"ok": False, "error": "Não foi possível autenticar na API da Twitch; confira Client ID e Secret"}
        try:
            conf = initialize_settings(self.home)
            current = conf.read_text(encoding="utf-8-sig").splitlines()
            updates = {
                "TWITCH_ENABLED": "1",
                "TWITCH_CLIENT_ID": client_id,
                "TWITCH_CLIENT_SECRET": client_secret,
            }
            output = []
            for line in current:
                key = line.split("=", 1)[0].strip() if "=" in line else ""
                if key in updates:
                    output.append(f"{key}={updates.pop(key)}")
                else:
                    output.append(line)
            output.extend(f"{k}={v}" for k, v in updates.items())
            temp = self.home / ("config-" + secrets.token_hex(7) + ".tmp")
            try:
                with temp.open("x", encoding="utf-8") as f:
                    f.write("\n".join(output) + "\n")
                os.replace(temp, conf)
            finally:
                temp.unlink(missing_ok=True)
            if self._runtime is not None:
                # A live pywebview app previously saved correctly but retained
                # the old TwitchDiscovery snapshot until full process restart.
                # The OAuth credentials were validated above; apply them only
                # after the atomic config file replacement succeeds.
                os.environ.update({
                    "TWITCH_ENABLED": "1",
                    "TWITCH_CLIENT_ID": client_id,
                    "TWITCH_CLIENT_SECRET": client_secret,
                })
                discovery = self._runtime.twitch
                with self._runtime.store.lock:
                    discovery.client_id = client_id
                    discovery.secret = client_secret
                    discovery.client = client
                    discovery.enabled = True
                    # A falha de uma tentativa anterior nao pode mascarar
                    # a nova autenticacao validada enquanto a busca inicia.
                    with discovery._db() as db:
                        db.execute("UPDATE twitch_sync SET last_error=NULL WHERE id=1")
                        db.commit()
                discovery.start_polling()
                return {"ok": True, "restart_required": False,
                        "monitoring": True}
            return {"ok": True, "restart_required": True}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": "Não foi possível salvar configurações locais"}

    def authorize_twitch_download(self):
        """Open the official Twitch user-consent page on a real user click."""
        if self._runtime is None:
            return {"ok": False, "error": "Requer aplicativo Windows ativo."}
        from .twitch_oauth import TwitchDownloadOAuth
        if self._twitch_oauth is None:
            self._twitch_oauth = TwitchDownloadOAuth(self.home, self._runtime)
        return self._twitch_oauth.begin()

    def twitch_download_status(self):
        if self._twitch_oauth is None:
            return {"status": "not_started", "active": False,
                    "grant_present": bool(os.getenv("TWITCH_USER_ACCESS_TOKEN")
                                          and os.getenv("TWITCH_EDITOR_ID"))}
        return self._twitch_oauth.status()

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
    start_publishing(runtime)
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
    stop_publishing(runtime)


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
            "tool_paths": tools, "tool_errors": {},
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
            if check.returncode != 0:
                result["tool_errors"][name] = (
                    f"exit={check.returncode} "
                    + check.stderr.decode("utf-8", "replace")[-180:]
                )
        report({**result, "phase": "native_tools"})
        # CI previously tested the backend only, while pywebview imported
        # pythonnet only when opening the GUI. Exercise the CLR bridge without
        # creating a window so a broken/missing DLL blocks Windows releases.
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            result["pythonnet"] = False
            try:
                import clr  # noqa: F401 - triggers pythonnet DLL initialization
                result["pythonnet"] = True
            except Exception as exc:
                result["pythonnet_error"] = (
                    f"{type(exc).__name__}: {str(exc)[:350]}"
                )
            report({**result, "phase": "pythonnet_checked"})
            # pywebview imports this managed DLL only when opening its window.
            # Loading it explicitly catches .NET CAS / Mark-of-the-Web failures
            # (0x80131515) that the old backend-only self-test missed.
            result["webview2_core"] = False
            try:
                from System.Reflection import Assembly
                internal = Path(getattr(sys, "_MEIPASS"))
                dll = internal / "webview" / "lib" / "Microsoft.Web.WebView2.Core.dll"
                if not dll.is_file():
                    raise FileNotFoundError(f"Missing GUI assembly: {dll.name}")
                loaded = Assembly.LoadFrom(str(dll))
                result["webview2_core"] = (
                    loaded.GetName().Name == "Microsoft.Web.WebView2.Core"
                )
            except Exception as exc:
                result["webview2_core_error"] = (
                    f"{type(exc).__name__}: {str(exc)[:350]}"
                )
            report({**result, "phase": "webview2_checked"})
        token = secrets.token_urlsafe(32)
        server, runtime, thread = start_backend(home / "data", token)
        # Validate the complete AutoClip sidecar inside the actual frozen EXE.
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            sidecar = runtime.autoclip_bridge._bundled_runtime()
            result["autoclip_cli"] = False
            if sidecar:
                try:
                    command = subprocess.run([*sidecar, "styles"], stdin=subprocess.DEVNULL,
                                             capture_output=True, timeout=40, check=False)
                    result["autoclip_cli"] = command.returncode == 0
                    if command.returncode:
                        result["autoclip_error"] = command.stderr.decode(
                            "utf-8", "replace")[-280:]
                except (OSError, subprocess.SubprocessError) as exc:
                    result["autoclip_error"] = str(exc)[:180]
            report({**result, "phase": "autoclip_checked"})
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
        required = ["ffmpeg", "ffprobe", "health", "protected_api"]
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            required.extend(["pythonnet", "webview2_core", "autoclip_cli"])
        result["status"] = "pass" if all(result.get(k) for k in required) else "fail"
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
            background_color="#080d17", js_api=DesktopBridge(home, runtime),
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
