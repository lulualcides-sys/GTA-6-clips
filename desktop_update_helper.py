"""Small standalone Windows updater executable.

Built separately with PyInstaller --onefile, copied outside the install dir
before running, so Windows can safely close/replace the desktop app files.
Keeps a full rollback folder and never touches LocalAppData/data or config.env.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 0x00000102


def wait_for_exit(pid: int, timeout_ms: int = 90000):
    # HANDLE é um ponteiro em Windows x64; ctypes usa int32 sem assinatura.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        code = ctypes.get_last_error()
        if code == 87:  # ERROR_INVALID_PARAMETER: PID já encerrado.
            return
        raise OSError(code, "Não foi possível abrir o processo antigo")
    try:
        outcome = kernel.WaitForSingleObject(handle, timeout_ms)
        if outcome == WAIT_TIMEOUT:
            raise TimeoutError("GTA6Clips is still running; update cancelled")
        if outcome != 0:
            raise OSError("Could not wait for old application to exit")
    finally:
        kernel.CloseHandle(handle)


def validate_paths(home: Path, staged: Path, installed: Path):
    home = home.resolve()
    staged = staged.resolve()
    installed = installed.resolve()
    if staged.parent != (home / "updates").resolve():
        raise ValueError("The staging directory must be inside application updates")
    if not staged.name.startswith("ready-v"):
        raise ValueError("Invalid staged release name")
    if not (staged / "GTA6Clips.exe").is_file():
        raise ValueError("New GTA6Clips.exe missing")
    if not (staged / "GTA6ClipsUpdater.exe").is_file():
        raise ValueError("New updater missing")
    if not (installed / "GTA6Clips.exe").is_file():
        raise ValueError("Current app folder not found")
    if installed == home or home in installed.parents or installed in home.parents:
        raise ValueError("Refusing to update the persistent application data directory")
    if len(installed.parts) < 2:
        raise ValueError("Application installation path is unsafe")
    return home, staged, installed


def install(home: Path, staged: Path, installed: Path, parent_pid: int):
    if sys.platform != "win32":
        raise OSError("Windows updater only")
    home, staged, installed = validate_paths(home, staged, installed)
    if parent_pid <= 0 or parent_pid == os.getpid():
        raise ValueError("Invalid parent process")
    wait_for_exit(parent_pid)
    parent = installed.parent
    nonce = uuid.uuid4().hex[:8]
    prepared = parent / (installed.name + ".next-" + nonce)
    backup = parent / (installed.name + ".backup-" +
                       time.strftime("%Y%m%d-%H%M%S") + "-" + nonce)
    shutil.copytree(staged, prepared)
    if not (prepared / "GTA6Clips.exe").is_file():
        raise ValueError("Prepared update is incomplete")
    renamed = False
    try:
        for attempt in range(12):
            try:
                installed.rename(backup)
                renamed = True
                break
            except (OSError, PermissionError):
                if attempt == 11:
                    raise
                time.sleep(.5)
        prepared.rename(installed)
    except Exception:
        if renamed and not installed.exists() and backup.exists():
            backup.rename(installed)
        raise
    finally:
        if prepared.exists():
            shutil.rmtree(prepared, ignore_errors=True)
    new_app = installed / "GTA6Clips.exe"
    try:
        process = subprocess.Popen([str(new_app)], cwd=str(installed),
                                   close_fds=True)
        # An immediate exit is a strong indicator of a broken launch.
        time.sleep(3)
        if process.poll() is not None:
            raise RuntimeError("New application terminated immediately")
    except Exception:
        if installed.exists():
            failed = parent / (installed.name + ".failed-" + nonce)
            installed.rename(failed)
        if backup.exists():
            backup.rename(installed)
        raise
    # Do not delete previous installation. Backup is intentional for rollback.
    return {"ok": True, "backup": str(backup)}


def self_test():
    """Confere proteção de dados e, no Windows, o HANDLE do processo real."""
    with tempfile.TemporaryDirectory(prefix="gta6-updater-test-") as tmp:
        root = Path(tmp)
        home = root / "profile"
        staged = home / "updates" / "ready-v0.0.0"
        staged.mkdir(parents=True)
        installed = root / "program"
        installed.mkdir()
        for folder in (staged, installed):
            (folder / "GTA6Clips.exe").write_bytes(b"test")
            (folder / "GTA6ClipsUpdater.exe").write_bytes(b"test")
        validate_paths(home, staged, installed)
        (root / "GTA6Clips.exe").write_bytes(b"test")
        try:
            validate_paths(home, staged, root)
        except ValueError:
            pass
        else:
            raise AssertionError("Dados persistentes não estão protegidos")
    if sys.platform == "win32":
        try:
            wait_for_exit(os.getpid(), timeout_ms=0)
        except TimeoutError:
            pass  # Processo atual está vivo: HANDLE real e timeout funcionam.
        else:
            raise AssertionError("Espera Win32 não reconheceu processo ativo")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--staged", type=Path)
    parser.add_argument("--installed", type=Path)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("UPDATER HELPER PASS")
        return 0
    if not args.apply or not all((args.home, args.staged, args.installed, args.parent_pid)):
        return 2
    try:
        install(args.home, args.staged, args.installed, args.parent_pid)
    except Exception as exc:
        # Write a non-sensitive error file outside of the installation directory.
        try:
            folder = args.home / "updates"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "last-update-error.txt").write_text(
                f"{type(exc).__name__}: {str(exc)[:200]}", encoding="utf-8"
            )
        except OSError:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
