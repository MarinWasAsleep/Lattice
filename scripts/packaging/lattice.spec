# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec of Lattice: one binary holding the whole studio.

Lattice 1.0 ships a single program. There used to be six specs and six binaries (a GUI and a
CLI for each of Dither, Glyph and Glitch); the three modes now live in one package and one
window, so one spec covers them.

``LATTICE_BUILD_MODE`` still chooses the entry point:

* ``gui``  — no arguments: the window opens, with the three modes as tabs (the normal case);
* ``cli``  — console binary for the command line, ``lattice <mode> <verb>``.

Both are frozen from the same source tree and the same version, which is what the release
check verifies.
"""
import os

from PyInstaller.utils.hooks import collect_submodules

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(os.path.dirname(HERE))
MODE = os.environ.get("LATTICE_BUILD_MODE", "gui")
NAME = "Lattice" if MODE == "gui" else "lattice"

ANALYSIS_KW = {
    "pathex": [ROOT],
    "binaries": [],
    "hookspath": [],
    "hooksconfig": {},
    "runtime_hooks": [],
    "excludes": [
        "numba.tests", "llvmlite.tests", "tkinter", "pytest",
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
    ],
    "noarchive": False,
    "optimize": 0,
}

# `lattice/cli.py` reaches each mode through importlib, and `lattice/window.py` imports the mode
# windows the same way: static analysis cannot follow either, so the submodules are listed by
# hand or the frozen binary dies with ModuleNotFoundError on its first launch.
HIDDEN = (collect_submodules("numba") + collect_submodules("llvmlite")
          + collect_submodules("lattice"))
HIDDEN = [item for item in HIDDEN if ".tests" not in item]

DATA = [
    (os.path.join(ROOT, "data"), "data"),
    (os.path.join(ROOT, "presets"), "presets"),
    (os.path.join(ROOT, "assets"), "assets"),
    # The stylesheet and the mode icons: `lattice.app` reads them by path at startup, so
    # PyInstaller cannot see them. Without this the frozen window comes up unstyled.
    (os.path.join(ROOT, "lattice", "resources"), os.path.join("lattice", "resources")),
    (os.path.join(ROOT, "lattice", "data"), os.path.join("lattice", "data")),
    (os.path.join(ROOT, "lattice", "palettes", "data"),
     os.path.join("lattice", "palettes", "data")),
]
# Only Glyph and Glitch keep a per-mode preset directory; Dither reads the shipped presets from
# the top-level `presets/` folder, so that one is already covered above.
for mode in ("glyph", "glitch"):
    directory = os.path.join(ROOT, "lattice", "modes", mode, "presets")
    if os.path.isdir(directory):
        DATA.append((directory, os.path.join("lattice", "modes", mode, "presets")))

# Translation catalogues are read at runtime by path, so PyInstaller cannot see them: without
# this the frozen window dies on its first label, while the CLI keeps working (it never looks
# at a catalogue). Every directory holding locale JSON has to be listed.
for mode in ("dither", "glyph", "glitch"):
    directory = os.path.join(ROOT, "lattice", "modes", mode, "i18n")
    if os.path.isdir(directory):
        DATA.append((directory, os.path.join("lattice", "modes", mode, "i18n")))

# One entry script for both modes: `lattice/__main__.py` picks the CLI when it is given
# arguments and the window otherwise, so the frozen binary behaves like `python -m lattice`.
SCRIPT = os.path.join(ROOT, "lattice", "__main__.py")

a = Analysis([SCRIPT], datas=DATA, hiddenimports=HIDDEN, **ANALYSIS_KW)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name=NAME, console=(MODE == "cli"), onefile=True,
    debug=False, strip=False, upx=False, upx_exclude=[],
    runtime_tmpdir=None, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None,
)
