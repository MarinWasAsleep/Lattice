"""Export controller of the Glitch shell: full-resolution PNG, GIF and APNG (L25).

The window owns one instance and its toolbar calls it. Every render goes through
:func:`lattice.modes.glitch.document.render_rgb8` with the window's render context and seed
controller — the same function, masks and streams the CLI uses for the same preset —
so the GUI cannot drift from the CLI (G9). Animated exports ride the shared N-image
loop with that same render function injected, so frame 0 of a loop is the PNG the
user sees. The animation module is loaded lazily: the CLI's import audit stays clean.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox, QFileDialog, QFormLayout, QSpinBox, QWidget

from lattice import axes
from lattice.modes.glitch import presets as preset_tools
from lattice.modes.glitch.document import (
    DocumentError,
    format_of,
    png_bytes,
    render_rgb8,
    target_path,
)
from lattice.pipeline import PipelineSpec
from lattice.types import RGB8, Image
from lattice.ui import ExportDialog, ExportError
from lattice.ui.export_dialog import DEFAULT_PATH_NAME

if TYPE_CHECKING:
    from lattice.modes.glitch.window import MainWindow

NO_SOURCE = "Load an image before rendering."
LOOP_FORMATS = ("png", "gif", "apng")
LOOP_LABELS = {"png": "PNG", "gif": "Animated GIF", "apng": "Animated PNG"}
LOOP_SUFFIX = {"png": ".png", "gif": ".gif", "apng": ".png"}
LOOP_FILTER = {
    "png": "PNG images (*.png);;All files (*)",
    "gif": "Animated GIF (*.gif);;All files (*)",
    "apng": "Animated PNG (*.png *.apng);;All files (*)",
}
LOOP_AXES = axes.AXES  # single source of truth, and it imports without Qt or the renderer
DEFAULT_FRAMES = 8
MAX_FRAMES = 240
LOOP_RENDER = Callable[[int, str, int], list[RGB8]]


class GlitchExportDialog(ExportDialog):
    """The Glitch export dialog: PNG, animated GIF and animated PNG (APNG).

    GIF and APNG share one options page (frame rate, loop, frame count, axis) and
    render their frames at export time through the injected loop callable, on the
    same masked, stream-seeded path as the PNG (G9, L25).
    """

    def __init__(
        self,
        source: Image,
        spec: PipelineSpec,
        parent: QWidget | None = None,
        *,
        render_full: Callable[[PipelineSpec], RGB8] | None = None,
        settings: QSettings | None = None,
        loop_frames: LOOP_RENDER | None = None,
    ) -> None:
        """Build the dialog; loop_frames(count, axis, step) renders the animation."""
        super().__init__(source, spec, parent, render_full=render_full,
                         settings=settings)
        self._loop_frames = loop_frames
        self._rebuild_formats()

    def _rebuild_formats(self) -> None:
        """Offer PNG, GIF and APNG only, keeping the PNG and animation option pages."""
        box = self.format_box
        box.blockSignals(True)
        box.clear()
        for key in LOOP_FORMATS:
            box.addItem(LOOP_LABELS[key], key)
        box.setCurrentIndex(0)
        box.blockSignals(False)
        png_page, gif_page = self.stack.widget(0), self.stack.widget(3)
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            if widget is not png_page and widget is not gif_page:
                widget.deleteLater()
        self.stack.insertWidget(0, png_page)
        self.stack.insertWidget(1, gif_page)
        self._build_loop_options(gif_page)
        self._on_format_changed(0)

    def _build_loop_options(self, page: QWidget) -> None:
        """Add the frame count and the variation axis to the animation options page."""
        self.loop_count = QSpinBox(page)
        self.loop_count.setObjectName("export_loop_frames")
        self.loop_count.setRange(1, MAX_FRAMES)
        self.loop_count.setValue(DEFAULT_FRAMES)
        self.loop_axis = QComboBox(page)
        self.loop_axis.setObjectName("export_loop_axis")
        for axis in LOOP_AXES:
            self.loop_axis.addItem(axis, axis)
        form = cast(QFormLayout, page.layout())
        form.addRow("Frames", self.loop_count)
        form.addRow("Axis", self.loop_axis)

    def target_path(self) -> Path:
        """Return the output path typed in the dialog, with the format's suffix."""
        text = self.path_edit.text().strip()
        if not text:
            raise ExportError("Choose an output file first.")
        path = Path(text)
        return path if path.suffix else path.with_suffix(LOOP_SUFFIX[self.format()])

    def _on_format_changed(self, index: int) -> None:
        """Show the options of the selected format and retarget the path suffix."""
        kind = self.format()
        if kind not in LOOP_SUFFIX:
            return
        self.stack.setCurrentIndex(1 if kind in ("gif", "apng") else 0)
        text = self.path_edit.text().strip() or DEFAULT_PATH_NAME
        self.path_edit.setText(str(Path(text).with_suffix(LOOP_SUFFIX[kind])))

    def _on_browse(self) -> None:
        """Ask for an output path with the selected format's filter."""
        current = self.path_edit.text().strip() or str(self.export_directory())
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", current, LOOP_FILTER[self.format()]
        )
        if path:
            self.path_edit.setText(path)

    def _frames_for_export(self) -> list[RGB8]:
        """Render the loop on the glitch path for GIF/APNG, else one full render."""
        if self.format() in ("gif", "apng"):
            if self._loop_frames is None:
                raise ExportError("No loop renderer available.")
            self.report.setText("Rendering the loop at full resolution…")
            return self._loop_frames(int(self.loop_count.value()),
                                     str(self.loop_axis.currentData()), 1)
        return super()._frames_for_export()

    def _write(self, frames: list[RGB8], target: Path) -> list[Path]:
        """Write GIF and APNG with the core writers the CLI uses; PNG stays shared."""
        kind = self.format()
        if kind in ("gif", "apng"):
            animation = importlib.import_module("lattice.animation")
            writer = animation.export_gif if kind == "gif" else animation.export_apng
            writer(frames, target, fps=self.gif_fps.value(), loop=self.gif_loop.value())
            return [target]
        return super()._write(frames, target)


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

    def loop_frames(self, count: int, axis: str, step: int = 1) -> list[RGB8]:
        """Render count full-resolution frames on the glitch path (masks, streams, locks)."""
        window = self.window
        if window.source is None:
            raise ExportError(NO_SOURCE)
        animation = importlib.import_module("lattice.animation")
        context, controller = window.render_context(), window.controller
        locked = {index: context.streams[index]
                  for index in sorted(controller.locked())
                  if index < len(context.streams)}

        def render_fn(image: Image, spec: PipelineSpec) -> RGB8:
            try:
                return render_rgb8(image, spec, context=context, controller=controller)
            except DocumentError as exc:
                raise ExportError(str(exc)) from exc

        try:
            return animation.render_loop(window.source, window.spec, count=count,
                                         axis=axis, step=step, locked_streams=locked,
                                         render_fn=render_fn)
        except ValueError as exc:
            raise ExportError(str(exc)) from exc

    def build_dialog(self) -> GlitchExportDialog:
        """Build the PNG/GIF/APNG export dialog bound to this window's render path."""
        window = self.window
        if window.source is None:
            raise ExportError(NO_SOURCE)
        return GlitchExportDialog(
            window.source, window.spec, window,
            render_full=lambda spec: self.render_full(window.source, spec),
            settings=window.settings(),
            loop_frames=self.loop_frames,
        )

    def dialog(self) -> list[Path]:
        """Open the full-resolution export dialog (PNG, GIF, APNG) and return the files."""
        window = self.window
        if window.source is None:
            window.report(NO_SOURCE)
            return []
        dialog = self.build_dialog()
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


__all__ = ["ExportController", "GlitchExportDialog", "NO_SOURCE"]
