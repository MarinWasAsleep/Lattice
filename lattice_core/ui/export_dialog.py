"""Shared full-resolution export dialog (PNG/SVG/GIF).

The Dither product review blocker was that the advanced export ran on the
1024 px preview proxy. This dialog fixes that contract: it owns the render. It
is handed the source image and the pipeline spec, renders the pipeline at FULL
resolution (no ``max_side``) on export, and only then writes the file, so the
file always matches the pipeline output size. The render callable can be
injected for worker-thread rendering in an application shell.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lattice_core import color
from lattice_core.pipeline import PipelineSpec, render
from lattice_core.types import RGB8, Image
from lattice_core.ui.svg import write_svg

EXPORT_DIR_KEY = "export_dir"
REPORT_SEPARATOR = "\n"
FORMATS: tuple[str, ...] = ("png", "svg", "gif")
FORMAT_LABELS = {"png": "PNG", "svg": "SVG", "gif": "GIF"}
FORMAT_SUFFIX = {"png": ".png", "svg": ".svg", "gif": ".gif"}
FORMAT_FILTER = {
    "png": "PNG images (*.png);;All files (*)",
    "svg": "SVG images (*.svg);;All files (*)",
    "gif": "GIF images (*.gif);;All files (*)",
}
DEFAULT_CELL = 1
MAX_CELL = 64
DEFAULT_PATH_NAME = "export"
RENDER = Callable[[PipelineSpec], RGB8]


class ExportError(Exception):
    """An export that could not be written: no output path, or a render failure."""


class ExportDialog(QDialog):
    """Dialog that renders the pipeline at full resolution and writes it as PNG, SVG or GIF."""

    def __init__(
        self,
        source: Image,
        spec: PipelineSpec,
        parent: QWidget | None = None,
        *,
        render_full: RENDER | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.source = np.ascontiguousarray(source, dtype=np.float32)
        self.spec = spec
        self._render_full = render_full if render_full is not None else self._default_render
        self.written: list[Path] = []
        self._settings = settings or QSettings()
        self._build()
        self._load_defaults()

    def _build(self) -> None:
        """Create the format selector, the option pages, the path row and the buttons."""
        self.format_box = QComboBox(self)
        self.format_box.setObjectName("export_format")
        for key in FORMATS:
            self.format_box.addItem(FORMAT_LABELS[key], key)
        self.stack = QWidget(self)
        self._build_svg_page(self.stack)
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("export_path")
        browse = QPushButton("Browse…", self)
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
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Export")
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        self.buttons.accepted.connect(self._on_export)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.format_box)
        layout.addWidget(self.stack)
        layout.addLayout(row)
        layout.addWidget(self.report)
        layout.addWidget(self.buttons)

    def _build_svg_page(self, page: QWidget) -> None:
        """Create the SVG page: cell size and background colour."""
        self.cell = QSpinBox(page)
        self.cell.setObjectName("export_cell")
        self.cell.setRange(1, MAX_CELL)
        self.cell.setValue(DEFAULT_CELL)
        self.background_edit = QLineEdit(page)
        self.background_edit.setObjectName("export_background")
        self.background_edit.setPlaceholderText("#RRGGBB, empty for transparent")
        form = QFormLayout(page)
        form.addRow("Cell size", self.cell)
        form.addRow("Background", self.background_edit)

    def format(self) -> str:
        """Return the selected format key: png, svg or gif."""
        return str(self.format_box.currentData())

    def export_directory(self) -> Path:
        """Return the remembered export directory, or the home directory."""
        stored = self._settings.value(EXPORT_DIR_KEY)
        return Path(stored) if stored else Path.home()

    def target_path(self) -> Path:
        """Return the output path typed in the dialog, with the format's suffix."""
        text = self.path_edit.text().strip()
        if not text:
            raise ExportError("Choose an output file first.")
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
        self.report.setText("Rendering at full resolution…")
        image = self._render_full(self.spec)
        written = self._write(image, target)
        self.written = written
        self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
        self.report.setText(REPORT_SEPARATOR.join(f"Exported {path.name}" for path in written))
        return written

    def _write(self, image: RGB8, target: Path) -> list[Path]:
        """Write the selected format to target and return every file created."""
        kind = self.format()
        if kind == "svg":
            write_svg(image, target, cell=self.cell.value(), background=self.background())
        else:
            color.to_pil(image).save(target, format="PNG" if kind == "png" else "GIF")
        return [target]

    def _on_export(self) -> None:
        """Export with the current options and report the outcome in the dialog."""
        try:
            self.export_now()
        except (ExportError, OSError, ValueError) as exc:
            self.report.setText(str(exc))

    def _on_browse(self) -> None:
        """Ask for an output path with the selected format's filter."""
        current = self.path_edit.text().strip() or str(self.export_directory())
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", current, FORMAT_FILTER[self.format()]
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
) -> list[Path]:
    """Show the export dialog for source and spec and return every file written."""
    dialog = ExportDialog(source, spec, parent, render_full=render_full)
    dialog.exec()
    return dialog.written


__all__ = ["ExportDialog", "ExportError", "FORMATS", "run_export_dialog"]
