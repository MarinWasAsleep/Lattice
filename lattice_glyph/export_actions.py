"""Export controller of the shell: full-resolution export, text export, preset saving.

The window owns one instance and its toolbar calls it. Every render goes through
:mod:`lattice_glyph.rendering`, which calls the same two functions the CLI calls
(``render_rgb8`` and ``write_render``), so the GUI cannot drift from the CLI (G9).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog

from lattice_core.pipeline import PipelineSpec
from lattice_core.types import RGB8, Image
from lattice_core.ui import ExportDialog
from lattice_glyph import presets as preset_tools
from lattice_glyph.document import DocumentError, format_of
from lattice_glyph.rendering import export_to, render_full

if TYPE_CHECKING:
    from lattice_glyph.window import MainWindow

TEXT_FILTER = "Text export (*.txt *.ansi *.html);;All files (*)"
NO_SOURCE = "Load an image before rendering."
DEFAULT_TEXT_NAME = "glyph.txt"


class ExportController:
    """Export and preset-saving actions of one window."""

    def __init__(self, window: MainWindow) -> None:
        """Bind the controller to the window that owns the source, the spec and settings."""
        self.window = window

    def render_full(self, image: Image, spec: PipelineSpec) -> RGB8:
        """Render spec on image through the function the CLI calls (G9)."""
        return render_full(image, spec)

    def dialog(self) -> list[Path]:
        """Open the shared full-resolution export dialog and return the files written."""
        window = self.window
        if window.source is None:
            window.report(NO_SOURCE)
            return []
        source = window.source
        dialog = ExportDialog(source, window.spec, window,
                              render_full=lambda spec: render_full(source, spec),
                              settings=window.settings())
        dialog.exec()
        if dialog.written:
            window.status(f"Exported {dialog.written[0].name}")
        return list(dialog.written)

    def to(self, path: str | Path) -> dict:
        """Write the current render to path in the format the path names."""
        window = self.window
        return export_to(window.source, window.spec, path, window, window.settings())

    def text(self) -> None:
        """Ask for a text-export path and write txt, ansi or html from the layout."""
        window = self.window
        if window.source is None:
            window.report(NO_SOURCE)
            return
        path, _ = QFileDialog.getSaveFileName(
            window, "Export text", str(Path.home() / DEFAULT_TEXT_NAME), TEXT_FILTER
        )
        if not path:
            return
        try:
            result = self.to(Path(path).with_suffix(f".{format_of(path)}"))
        except DocumentError as exc:
            window.report(str(exc))
            return
        for warning in result["warnings"]:
            window.status(warning)
        window.status(f"Exported {Path(result['file']).name}")

    def save_preset(self, path: str | Path) -> Path | None:
        """Write the current spec as a v3 preset and remember it as the applied one."""
        window = self.window
        try:
            target = preset_tools.save_spec(path, window.spec)
        except (OSError, ValueError) as exc:
            window.report(f"Cannot write {path}: {exc}")
            return None
        window.preset_panel.refresh()
        window.preset_panel.select_name(target.name)
        window.indicator.set_preset(target.name)
        window.status(f"Saved {target.name}")
        return target


__all__ = ["ExportController", "NO_SOURCE", "TEXT_FILTER"]
