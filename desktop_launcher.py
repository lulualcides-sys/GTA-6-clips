"""Frozen Windows application entry point (no console by default)."""
from __future__ import annotations

import sys

from clipforge.desktop import main


def startup_error_message(error: Exception) -> str:
    """Troubleshooting without suppressing Windows security warnings."""
    detail = str(error)[:650] or "Unexpected error"
    if "Python.Runtime.Loader.Initialize" in detail or "Python.Runtime.dll" in detail:
        return (
            "Nao foi possivel carregar Python.Runtime.dll. O Windows pode ter "
            "bloqueado esta DLL ao extrair o ZIP baixado da internet.\n\n"
            "Se o pacote veio do GitHub oficial, execute "
            "Corrigir-e-Abrir-GTA6Clips.cmd na mesma pasta do GTA6Clips.exe "
            "e confirme o reparo.\n\n"
            "O reparo nao exige administrador e nao apaga seus videos. "
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
