"""Windows launcher for Lattice Dither: starts the GUI without a console window.

Double-clicked, or started by the shortcuts created by ``scripts/install_shortcuts.ps1``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Put the project root on sys.path, then run the Lattice Dither GUI."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from lattice_dither.ui.app import main as run_gui

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
