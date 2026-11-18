"""Export controller of the Glitch shell: full-resolution export and preset saving.

The window owns one instance and its toolbar calls it. Every render goes through
:func:`lattice_glitch.document.render_rgb8` with the window's render context and seed
controller — the same function, masks and streams the CLI uses for the same preset —
so the GUI cannot drift from the CLI (G9). PNG export goes through the shared
``ExportDialog``, restricted to the one raster format this application writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lattice_core.pipeline import PipelineSpec
from lattice_core.types import RGB8, Image
from lattice_core.ui import ExportDialog, ExportError
from lattice_glitch import presets as preset_tools
from lattice_glitch.document import (
    DocumentError,
    format_of,
    png_bytes,
    render_rgb8,
    target_path,
)

if TYPE_CHECKING:
    from lattice_glitch.window import MainWindow

NO_SOURCE = "Load an image before rendering."


class ExportController:
    """Export and preset-saving actions of one window."""

    def __init__(self, window: MainWindow) -> None:
        """Bind the controller to the window that owns the source, the spec and settings."""
        self.window = window

    def render_full(self, image: Image, spec: PipelineSpec) -> RGB8:
        """Render spec on image through the CLI's function (G9); a DocumentError becomes
        an ExportError so the dialog's Qt slot reports it instead of crashing."""
        window = self.window
        try:
            return render_rgb8(image, spec, context=window.render_context(),
                               controller=window.controller)
        except DocumentError as exc:
            raise ExportError(str(exc)) from exc

    def dialog(self) -> list[Path]:
        """Open the shared full-resolution export dialog, PNG only, and return the files."""
        window = self.window
        if window.source is None:
            window.report(NO_SOURCE)
            return []
        source = window.source
        dialog = ExportDialog(source, window.spec, window,
                              render_full=lambda spec: self.render_full(source, spec),
                              settings=window.settings())
        dialog.format_box.clear()
        dialog.format_box.addItem("PNG", "png")
        dialog.exec()
        if dialog.written:
            window.status(f"Exported {dialog.written[0].name}")
        return list(dialog.written)

    def to(self, path: str | Path) -> dict:
        """Write the current full-resolution render to path as PNG."""
        window = self.window
        if window.source is None:
            raise DocumentError(NO_SOURCE)
        fmt = format_of(path)
        try:
            payload = png_bytes(self.render_full(window.source, window.spec))
        except ExportError as exc:
            raise DocumentError(str(exc)) from None
        target = target_path(path, fmt)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        except OSError as exc:
            raise DocumentError(f"cannot write {target}: {exc}") from None
        return {"file": str(target), "format": fmt, "warnings": []}

    def save_preset(self, path: str | Path) -> Path | None:
        """Write the current document as a v3 preset and remember it as the applied one."""
        window = self.window
        streams = window.render_context().streams
        locked_streams = {i: streams[i] for i in sorted(window.controller.locked())
                          if i < len(streams)}
        try:
            target = preset_tools.save_spec(
                path, window.spec, stack=window.effect_stack,
                masks=window.mask_panel.planes(), locked_streams=locked_streams,
            )
        except (OSError, ValueError) as exc:
            window.report(f"Cannot write {path}: {exc}")
            return None
        window.preset_panel.refresh()
        window.preset_panel.select_name(target.name)
        window.indicator.set_preset(target.name)
        window.status(f"Saved {target.name}")
        return target


__all__ = ["ExportController", "NO_SOURCE"]
