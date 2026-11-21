"""Shared full-resolution export dialog: PNG, SVG, print and GIF/video sequence.

The Dither product review blocker was that the advanced export ran on the
1024 px preview proxy. This dialog fixes that contract: it owns the render. It
is handed the source image and the pipeline spec, renders the pipeline at FULL
resolution (no ``max_side``) on export, and only then writes the file. The
render callable, the frame sequence, the video writer (ffmpeg lives outside
core) and ``tr`` are injectable, so every application reuses this one dialog
and core never imports an application.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lattice import color
from lattice.pipeline import PipelineSpec, render
from lattice.types import RGB8, Image
from lattice.ui.export_writers import write_gif, write_print
from lattice.ui.svg import write_svg

EXPORT_DIR_KEY = "export_dir"
REPORT_SEPARATOR = "\n"
FORMATS: tuple[str, ...] = ("png", "svg", "print", "gif", "video")
ANIMATED_FORMATS: tuple[str, ...] = ("gif", "video")
FORMAT_LABELS = {
    "png": "PNG",
    "svg": "SVG",
    "print": "Print PNG",
    "gif": "Animated GIF",
    "video": "Video",
}
FORMAT_SUFFIX = {"png": ".png", "svg": ".svg", "print": ".png", "gif": ".gif", "video": ".mp4"}
FORMAT_FILTER = {
    "png": "PNG images (*.png);;All files (*)",
    "svg": "SVG images (*.svg);;All files (*)",
    "print": "PNG images (*.png);;All files (*)",
    "gif": "Animated GIF (*.gif);;All files (*)",
    "video": "Video (*.mp4 *.mkv *.webm);;All files (*)",
}
DEFAULT_CELL = 1
DEFAULT_DPI = 300
DEFAULT_BLEED_MM = 0.0
DEFAULT_FPS = 12
DEFAULT_LOOP = 0
DEFAULT_PATH_NAME = "export"
MAX_CELL = 64
MAX_DPI = 1200
MAX_BLEED_MM = 50.0
MAX_FPS = 60
MAX_LOOP = 100
RENDER = Callable[[PipelineSpec], RGB8]


class VideoWriter(Protocol):
    """Writes a frame sequence through an external encoder, like the app's export_video."""

    def __call__(self, frames: list[RGB8], path: Path, *, fps: int = 12) -> bool:
        """Write frames to path at fps; return False, never raise, when unavailable."""
        ...


class Translate(Protocol):
    """Translates one UI key and formats it with kwargs, like an application's tr."""

    def __call__(self, key: str, **kwargs: object) -> str:
        """Return the translated, formatted text of key."""
        ...


def _default_tr(key: str, **kwargs: object) -> str:
    """Return key formatted with kwargs: the app-agnostic fallback translation."""
    return key.format(**kwargs)


class ExportError(Exception):
    """An export that could not be written: no output path, or a render failure."""


class ExportDialog(QDialog):
    """Dialog rendering the pipeline at full resolution as PNG, SVG, print, GIF or video."""

    def __init__(
        self,
        source: Image,
        spec: PipelineSpec,
        parent: QWidget | None = None,
        *,
        render_full: RENDER | None = None,
        settings: QSettings | None = None,
        frames: list[RGB8] | None = None,
        video_writer: VideoWriter | None = None,
        tr: Translate | None = None,
    ) -> None:
        """Build the dialog; frames, the video writer and tr are injected by the app."""
        super().__init__(parent)
        self._tr = tr if tr is not None else _default_tr
        self.setWindowTitle(self._tr("Export"))
        self.source = np.ascontiguousarray(source, dtype=np.float32)
        self.spec = spec
        self.frames = list(frames) if frames else []
        self._render_full = render_full if render_full is not None else self._default_render
        self._video_writer = video_writer
        self.written: list[Path] = []
        self._settings = settings or QSettings()
        self._build()
        self._load_defaults()

    def _build(self) -> None:
        """Create the format selector, the option pages, the path row and the buttons."""
        self.format_box = QComboBox(self)
        self.format_box.setObjectName("export_format")
        for key in FORMATS:
            self.format_box.addItem(self._tr(FORMAT_LABELS[key]), key)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("export_options")
        self.stack.addWidget(QWidget(self.stack))  # the PNG page carries no option
        self._build_svg_page()
        self._build_print_page()
        self._build_gif_page()
        self._build_video_page()
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("export_path")
        browse = QPushButton(self._tr("Browse…"), self)
        browse.setObjectName("export_browse")
        browse.clicked.connect(self._on_browse)
        row = QHBoxLayout()
        row.addWidget(self.path_edit)
        row.addWidget(browse)
        self.report = QLabel(self)
        self.report.setObjectName("export_report")
        self.report.setWordWrap(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close, self
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(self._tr("Export"))
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(self._tr("Close"))
        self.buttons.accepted.connect(self._on_export)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.format_box)
        layout.addWidget(self.stack)
        layout.addLayout(row)
        layout.addWidget(self.report)
        layout.addWidget(self.buttons)
        self.format_box.currentIndexChanged.connect(self._on_format_changed)

    def _build_svg_page(self) -> None:
        """Create the SVG page: cell size and background colour."""
        page = QWidget(self.stack)
        self.cell = QSpinBox(page)
        self.cell.setObjectName("export_cell")
        self.cell.setRange(1, MAX_CELL)
        self.cell.setValue(DEFAULT_CELL)
        self.background_edit = QLineEdit(page)
        self.background_edit.setObjectName("export_background")
        self.background_edit.setPlaceholderText(self._tr("#RRGGBB, empty for transparent"))
        form = QFormLayout(page)
        form.addRow(self._tr("Cell size"), self.cell)
        form.addRow(self._tr("Background"), self.background_edit)
        self.stack.addWidget(page)

    def _build_print_page(self) -> None:
        """Create the print page: resolution, bleed, crop marks and separations."""
        page = QWidget(self.stack)
        self.dpi = QSpinBox(page)
        self.dpi.setObjectName("export_dpi")
        self.dpi.setRange(1, MAX_DPI)
        self.dpi.setValue(DEFAULT_DPI)
        self.bleed = QDoubleSpinBox(page)
        self.bleed.setObjectName("export_bleed")
        self.bleed.setRange(0.0, MAX_BLEED_MM)
        self.bleed.setDecimals(1)
        self.bleed.setValue(DEFAULT_BLEED_MM)
        self.crop_marks = QCheckBox(self._tr("Crop marks"), page)
        self.crop_marks.setObjectName("export_crop_marks")
        self.separations = QCheckBox(self._tr("Separations"), page)
        self.separations.setObjectName("export_separations")
        form = QFormLayout(page)
        form.addRow(self._tr("Resolution"), self.dpi)
        form.addRow(self._tr("Bleed (mm)"), self.bleed)
        form.addRow(self.crop_marks)
        form.addRow(self.separations)
        self.stack.addWidget(page)

    def _build_gif_page(self) -> None:
        """Create the GIF page: frame rate and loop count."""
        page = QWidget(self.stack)
        self.gif_fps = QSpinBox(page)
        self.gif_fps.setObjectName("export_gif_fps")
        self.gif_fps.setRange(1, MAX_FPS)
        self.gif_fps.setValue(DEFAULT_FPS)
        self.gif_loop = QSpinBox(page)
        self.gif_loop.setObjectName("export_gif_loop")
        self.gif_loop.setRange(0, MAX_LOOP)
        self.gif_loop.setValue(DEFAULT_LOOP)
        self.gif_loop.setSpecialValueText(self._tr("forever"))
        form = QFormLayout(page)
        form.addRow(self._tr("Frame rate"), self.gif_fps)
        form.addRow(self._tr("Loop"), self.gif_loop)
        self.stack.addWidget(page)

    def _build_video_page(self) -> None:
        """Create the video page: frame rate."""
        page = QWidget(self.stack)
        self.video_fps = QSpinBox(page)
        self.video_fps.setObjectName("export_video_fps")
        self.video_fps.setRange(1, MAX_FPS)
        self.video_fps.setValue(DEFAULT_FPS)
        form = QFormLayout(page)
        form.addRow(self._tr("Frame rate"), self.video_fps)
        self.stack.addWidget(page)

    def format(self) -> str:
        """Return the selected format key: png, svg, print, gif or video."""
        return str(self.format_box.currentData())

    def export_directory(self) -> Path:
        """Return the remembered export directory, or the home directory."""
        stored = self._settings.value(EXPORT_DIR_KEY)
        return Path(stored) if stored else Path.home()

    def target_path(self) -> Path:
        """Return the output path typed in the dialog, with the format's suffix."""
        text = self.path_edit.text().strip()
        if not text:
            raise ExportError(self._tr("Choose an output file first."))
        path = Path(text)
        return path if path.suffix else path.with_suffix(FORMAT_SUFFIX[self.format()])

    def background(self) -> str | None:
        """Return the SVG background colour, or None when the field is empty."""
        return self.background_edit.text().strip() or None

    def _default_render(self, spec: PipelineSpec) -> RGB8:
        """Render spec at full resolution; the preview proxy is never used here."""
        return render(self.source, spec)

    def export_now(self) -> list[Path]:
        """Render at full resolution, write the file and return the paths written."""
        target = self.target_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        frames = self._frames_for_export()
        written = self._write(frames, target)
        self.written = written
        self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
        lines = [self._tr("Exported {name}", name=path.name) for path in written]
        self.report.setText(REPORT_SEPARATOR.join(lines))
        return written

    def _frames_for_export(self) -> list[RGB8]:
        """Return the injected sequence for animated formats, else one full render."""
        if self.frames and self.format() in ANIMATED_FORMATS:
            return self.frames
        self.report.setText(self._tr("Rendering at full resolution…"))
        return [self._render_full(self.spec)]

    def _write(self, frames: list[RGB8], target: Path) -> list[Path]:
        """Write the selected format to target and return every file created."""
        kind = self.format()
        image = frames[0]
        if kind == "svg":
            write_svg(image, target, cell=self.cell.value(), background=self.background())
        elif kind == "print":
            return write_print(
                image,
                target,
                dpi=self.dpi.value(),
                bleed_mm=self.bleed.value(),
                crop_marks=self.crop_marks.isChecked(),
                separations=self.separations.isChecked(),
            )
        elif kind == "gif":
            write_gif(frames, target, fps=self.gif_fps.value(), loop=self.gif_loop.value())
        elif kind == "video":
            return self._write_video(frames, target)
        else:
            color.to_pil(image).save(target, format="PNG")
        return [target]

    def _write_video(self, frames: list[RGB8], target: Path) -> list[Path]:
        """Write through the injected video writer; a missing encoder is an error."""
        if self._video_writer is None:
            raise ExportError(self._tr("No video writer available."))
        if not self._video_writer(frames, target, fps=self.video_fps.value()):
            reason = self._tr("No ffmpeg available.")
            raise ExportError(
                self._tr("Cannot write {path}: {error}", path=target.name, error=reason)
            )
        return [target]

    def _on_export(self) -> None:
        """Export with the current options and report the outcome in the dialog."""
        try:
            self.export_now()
        except (ExportError, OSError, ValueError) as exc:
            self.report.setText(str(exc))

    def _on_format_changed(self, index: int) -> None:
        """Show the options of the selected format and retarget the path suffix."""
        self.stack.setCurrentIndex(index)
        text = self.path_edit.text().strip() or DEFAULT_PATH_NAME
        self.path_edit.setText(str(Path(text).with_suffix(FORMAT_SUFFIX[self.format()])))

    def _on_browse(self) -> None:
        """Ask for an output path with the selected format's filter."""
        current = self.path_edit.text().strip() or str(self.export_directory())
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("Export"), current, self._tr(FORMAT_FILTER[self.format()])
        )
        if path:
            self.path_edit.setText(path)

    def _load_defaults(self) -> None:
        """Point the path field at the remembered directory and the format's suffix."""
        suffix = FORMAT_SUFFIX[self.format()]
        self.path_edit.setText(str(self.export_directory() / f"{DEFAULT_PATH_NAME}{suffix}"))


def run_export_dialog(
    source: Image,
    spec: PipelineSpec,
    parent: QWidget | None = None,
    *,
    render_full: RENDER | None = None,
    settings: QSettings | None = None,
    frames: list[RGB8] | None = None,
    video_writer: VideoWriter | None = None,
    tr: Translate | None = None,
) -> list[Path]:
    """Show the export dialog for source and spec and return every file written."""
    dialog = ExportDialog(
        source,
        spec,
        parent,
        render_full=render_full,
        settings=settings,
        frames=frames,
        video_writer=video_writer,
        tr=tr,
    )
    dialog.exec()
    return dialog.written


__all__ = ["ExportDialog", "ExportError", "FORMATS", "run_export_dialog"]
