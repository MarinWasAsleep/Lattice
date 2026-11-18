"""Render and export service of the Glyph shell: one path, shared with the CLI (G9).

The window delegates here so that the GUI never builds its own pipeline call: ``render_full``
is :func:`lattice_glyph.document.render_rgb8` and ``export_to`` is
:func:`lattice_glyph.document.write_render`, the two functions the CLI calls. PNG export
goes through the shared ``ExportDialog``, which owns the full-resolution render.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from lattice_core.pipeline import PipelineSpec
from lattice_core.types import RGB8, Image
from lattice_core.ui import ExportDialog
from lattice_glyph.document import DocumentError, format_of, render_rgb8, write_render

PNG = "png"
TEXT_FORMATS = ("txt", "ansi", "html")


def render_full(image: Image, spec: PipelineSpec) -> RGB8:
    """Render spec on the full source through the CLI's own function (G9)."""
    return render_rgb8(image, spec)


def export_png(image: Image, spec: PipelineSpec, path: str | Path, parent: QWidget | None,
               settings: QSettings) -> Path:
    """Write the PNG the shared export dialog produces at full resolution."""
    dialog = ExportDialog(image, spec, parent,
                          render_full=lambda current: render_full(image, current),
                          settings=settings)
    dialog.format_box.setCurrentIndex(dialog.format_box.findData(PNG))
    dialog.path_edit.setText(str(path))
    (written,) = dialog.export_now()
    return written


def export_to(image: Image | None, spec: PipelineSpec, path: str | Path, parent: QWidget | None,
              settings: QSettings) -> dict:
    """Write one render of image to path in the format its suffix names."""
    if image is None:
        raise DocumentError("load an image before rendering")
    target = Path(path)
    fmt = format_of(target)
    if fmt == PNG:
        written = export_png(image, spec, target, parent, settings)
        return {"file": str(written), "format": PNG, "warnings": []}
    if fmt not in TEXT_FORMATS and fmt != "svg":
        raise DocumentError(f"unknown export format {fmt!r}")
    export = write_render(image, spec, target, fmt)
    return {"file": str(export.path), "format": export.fmt,
            "warnings": list(export.warnings)}


__all__ = ["export_png", "export_to", "render_full"]
