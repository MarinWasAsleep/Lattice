"""GUI bootstrap of Lattice: one application object, one window, three modes.

The three shells used to carry three near-identical ``app.py`` files, each building a
``QApplication``, applying a dark palette and showing its own window. What actually differs
between them is nothing: the theme and the bootstrap were copy-pasted. They now live here, once,
and the window they open is the tabbed one from ``lattice.window``.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QColor, QPalette

LOGGER = logging.getLogger(__name__)

BASE_COLOR = QColor(35, 35, 38)
WINDOW_COLOR = QColor(53, 53, 56)
TEXT_COLOR = QColor(220, 220, 220)
DISABLED_COLOR = QColor(120, 120, 120)
HIGHLIGHT_COLOR = QColor(64, 132, 214)


def dark_palette() -> QPalette:
    """Return the dark palette applied on top of the Fusion style."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, WINDOW_COLOR)
    palette.setColor(QPalette.ColorRole.WindowText, TEXT_COLOR)
    palette.setColor(QPalette.ColorRole.Base, BASE_COLOR)
    palette.setColor(QPalette.ColorRole.AlternateBase, WINDOW_COLOR)
    palette.setColor(QPalette.ColorRole.ToolTipBase, BASE_COLOR)
    palette.setColor(QPalette.ColorRole.ToolTipText, TEXT_COLOR)
    palette.setColor(QPalette.ColorRole.Text, TEXT_COLOR)
    palette.setColor(QPalette.ColorRole.Button, WINDOW_COLOR)
    palette.setColor(QPalette.ColorRole.ButtonText, TEXT_COLOR)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 90, 90))
    palette.setColor(QPalette.ColorRole.Link, HIGHLIGHT_COLOR)
    palette.setColor(QPalette.ColorRole.Highlight, HIGHLIGHT_COLOR)
    palette.setColor(QPalette.ColorRole.HighlightedText, BASE_COLOR)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, DISABLED_COLOR)
    return palette


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


__all__ = ["create_application", "dark_palette", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
