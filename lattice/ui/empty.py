"""Shared empty state: the guidance shown while no image is loaded."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

DEFAULT_TEXT = "Open an image to start."


class EmptyState(QWidget):
    """A centred placeholder telling the user what to do with an empty workspace."""

    def __init__(self, text: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("empty_state")
        self.label = QLabel(text if text is not None else DEFAULT_TEXT, self)
        self.label.setObjectName("empty_state_text")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_message(self, text: str) -> None:
        """Replace the guidance text."""
        self.label.setText(text)

    def message(self) -> str:
        """Return the current guidance text."""
        return self.label.text()


__all__ = ["DEFAULT_TEXT", "EmptyState"]
