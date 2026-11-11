"""QApplication bootstrap with the Fusion dark theme."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from dithercraft.ui.main_window import MainWindow

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
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link, HIGHLIGHT_COLOR)
    palette.setColor(QPalette.ColorRole.Highlight, HIGHLIGHT_COLOR)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, DISABLED_COLOR)
    return palette


def create_application(argv: list[str] | None = None) -> QApplication:
    """Return the QApplication, creating it with the Fusion dark theme if needed."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        app = existing
    else:
        app = QApplication(list(argv) if argv is not None else list(sys.argv))
    app.setApplicationName("DitherCraft")
    app.setApplicationDisplayName("DitherCraft")
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    return app


def main(argv: list[str] | None = None) -> int:
    """Start the DitherCraft GUI and return the Qt exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_application(argv)
    window = MainWindow()
    window.show()
    LOGGER.info("DitherCraft window shown")
    return app.exec()
