"""Frozen Windows application entry point (no console by default)."""
from __future__ import annotations

import sys

from clipforge.desktop import main


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
                    0, (str(error)[:650] or "Unexpected error") +
                    "\n\nConsulte docs/DESKTOP_WINDOWS.md no repositório.",
                    "GTA VI Clips - Falha ao iniciar", 0x10
                )
            except Exception:
                pass
        raise SystemExit(1)
