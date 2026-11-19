"""GUI bootstrap of Lattice: one application object, one window, three modes.

The three shells used to carry three near-identical ``app.py`` files, each building a
``QApplication``, applying a dark palette and showing its own window. What actually differs
between them is nothing: the theme and the bootstrap were copy-pasted. They now live here, once,
and the window they open is the tabbed one from ``lattice.window``.

The theme is a stylesheet (``lattice/resources/lattice.qss``) on top of Fusion, not a hand-built
palette: a stylesheet can say things a palette cannot — which tab is active, how a slider reads,
what a disabled button looks like — and it keeps every colour in one file a designer can edit.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QDir
from PySide6.QtGui import QColor, QFont, QPalette

LOGGER = logging.getLogger(__name__)

BASE_COLOR = QColor(35, 35, 38)
WINDOW_COLOR = QColor(53, 53, 56)
TEXT_COLOR = QColor(220, 220, 220)
DISABLED_COLOR = QColor(120, 120, 120)
HIGHLIGHT_COLOR = QColor(64, 132, 214)

RESOURCES = Path(__file__).resolve().parent / "resources"
STYLESHEET = RESOURCES / "lattice.qss"

# The stylesheet reaches its arrows and check marks through this prefix; Qt resolves
# ``url(lattice:ui/chevron-down.svg)`` against the path registered here.
RESOURCE_PREFIX = "lattice"

# Used for the numeric readouts, where digits must not jitter as the value changes. No font is
# shipped: the first family the system actually has is used, and the stylesheet asks for the
# alias, which Qt resolves through this substitution table.
MONO_ALIAS = "Lattice Mono"
MONO_FAMILIES = (
    "JetBrains Mono", "Cascadia Mono", "SF Mono", "Menlo",
    "DejaVu Sans Mono", "Liberation Mono", "Consolas", "monospace",
)


def dark_palette() -> QPalette:
    """Return the dark palette used where the stylesheet stays silent.

    The stylesheet owns the widgets it names; this palette covers the rest (menus, dialogs and
    anything a platform adds), so no window ever flashes light grey.
    """
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#232323"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#EDEDED"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1C1C1C"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#232323"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#121212"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#EDEDED"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#EDEDED"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2C2C2C"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#EDEDED"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FF5A4D"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#FFB000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#FFB000"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#121212"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6B6B6B"))
    return palette


def _register_resources() -> None:
    """Let the stylesheet resolve ``url(lattice:…)`` to the bundled SVG files."""
    QDir.addSearchPath(RESOURCE_PREFIX, str(RESOURCES))


def _register_mono_font() -> None:
    """Point the ``Lattice Mono`` alias at the first monospace family installed."""
    QFont.insertSubstitutions(MONO_ALIAS, list(MONO_FAMILIES))


def stylesheet() -> str:
    """Return the bundled stylesheet, or an empty string when it is missing.

    A missing stylesheet must not take the window down: the palette still gives a usable dark
    theme, and a broken install should degrade rather than refuse to start.
    """
    try:
        return STYLESHEET.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("stylesheet unavailable (%s): falling back to the palette", exc)
        return ""


def create_application(argv: list[str] | None = None):
    """Return the single QApplication of the process, styled for the dark theme.

    Qt refuses a second application object in one process, so an existing instance is reused
    instead of being created again — that is what makes the suite's fixtures and a real launch
    agree.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(list(sys.argv[1:] if argv is None else argv))
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    _register_resources()
    _register_mono_font()
    sheet = stylesheet()
    if sheet:
        app.setStyleSheet(sheet)
    return app


def main(argv: list[str] | None = None) -> int:
    """Start the Lattice window and return the Qt exit code."""
    from lattice.window import MainWindow

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_application(argv)
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    LOGGER.info("Lattice window shown")
    return app.exec()


__all__ = ["MONO_ALIAS", "RESOURCES", "STYLESHEET", "create_application", "dark_palette",
           "main", "stylesheet"]


if __name__ == "__main__":
    raise SystemExit(main())
