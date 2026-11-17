"""Frozen Windows application entry point (no console by default)."""
from __future__ import annotations

import sys

from clipforge.desktop import main


def startup_error_message(error: Exception) -> str:
    """Troubleshooting without suppressing Windows security warnings."""
    detail = str(error)[:650] or "Unexpected error"
    markers = (
        "Python.Runtime.Loader.Initialize", "Python.Runtime.dll",
        "Microsoft.Web.WebView2.Core.dll", "0x80131515",
    )
    if any(marker.lower() in detail.lower() for marker in markers):
        return (
            "Falha ao carregar bibliotecas .NET do Nexus (Python.NET ou "
            "Microsoft WebView2). Os arquivos extraidos do ZIP podem ter "
            "sido bloqueados como downloads da Internet.\n\n"
            "Se o ZIP veio do GitHub oficial, execute "
            "Corrigir-e-Abrir-GTA6Clips.cmd na pasta do programa "
            "e confirme com S. O reparo se limita a DLL/PYD dentro de "
            "_internal e nao apaga videos.\n\n"
            "Consulte LEIA-ME-PRIMEIRO.md."
        )
    return detail + "\n\nConsulte LEIA-ME-PRIMEIRO.md."


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if "--self-test" in sys.argv:
            raise
        # No invisible crash: communicate missing runtimes without admin changes.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0, startup_error_message(error),
                    "GTA VI Clips - Falha ao iniciar", 0x10
                )
            except Exception:
                pass
        raise SystemExit(1)
