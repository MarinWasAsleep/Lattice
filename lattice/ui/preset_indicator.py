"""Shared preset indicator: shows the preset that is actually applied.

The Dither product review found the old indicator dishonest: it kept showing
"Preset 1/12: …" while no image was loaded and after the user changed the
algorithm or the palette. This widget fixes that contract: the owner tells it
which preset is applied, marks it modified on every pipeline change, and hides
it entirely while no image is loaded.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

CUSTOM_TEXT = "Custom"
MODIFIED_SUFFIX = " (modified)"
NO_IMAGE_HIDDEN = True


class PresetIndicator(QLabel):
    """Status label for the applied preset: honest, live-updating, image-gated."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("preset_indicator")
        self._preset: str | None = None
        self._modified = False
        self._image_loaded = False
        self._refresh()

    def preset_name(self) -> str | None:
        """Return the name of the applied preset, or None for a custom pipeline."""
        return self._preset

    def is_modified(self) -> bool:
        """Return True once the pipeline drifted from the applied preset."""
        return self._modified

    def is_visible_without_image(self) -> bool:
        """Return whether the label stays visible while no image is loaded."""
        return not NO_IMAGE_HIDDEN

    def set_preset(self, name: str | None) -> None:
        """Record the applied preset (None = custom) and clear the modified flag."""
        self._preset = None if name is None or not str(name) else str(name)
        self._modified = False
        self._refresh()

    def set_modified(self, modified: bool) -> None:
        """Mark the pipeline as drifted from the applied preset."""
        self._modified = bool(modified)
        self._refresh()

    def pipeline_changed(self) -> None:
        """Record one pipeline change: the applied preset is now modified."""
        self.set_modified(True)

    def set_image_loaded(self, loaded: bool) -> None:
        """Show the label only when an image is loaded."""
        self._image_loaded = bool(loaded)
        self._refresh()

    def indicator_text(self) -> str:
        """Return the text the label shows: the applied preset, honestly qualified."""
        base = self._preset if self._preset is not None else CUSTOM_TEXT
        return base + (MODIFIED_SUFFIX if self._modified else "")

    def _refresh(self) -> None:
        """Update the text and the visibility from the current state."""
        self.setText(self.indicator_text())
        self.setVisible(self._image_loaded)


__all__ = ["CUSTOM_TEXT", "MODIFIED_SUFFIX", "PresetIndicator"]
