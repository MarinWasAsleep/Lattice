"""Export dialog: one window for the four export formats (CONTRACT §19 to §21).

The dialog renders nothing: it is handed the finished uint8 RGB image, and for the
animated formats the rendered frame sequence, and writes it with the export functions of
``lattice_dither.export``. The last directory used is remembered in ``QSettings`` under
``export_dir``, the same key the main window uses for its PNG export.

The defaults are the contract defaults: ``cell=1``, ``dpi=300``, ``bleed_mm=0``,
``crop_marks=False``, ``separations=False`` and ``fps=12``.
"""

from __future__ import annotations

from pathlib import Path

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

from lattice_core.types import RGB8
from lattice_dither.export.print import export_print
from lattice_dither.export.svg import export_svg
from lattice_dither.export.video import export_gif, export_video
from lattice_dither.i18n import tr

SETTINGS_NAME = "LatticeDither"
EXPORT_DIR_KEY = "export_dir"
REPORT_SEPARATOR = "\n"
FORMATS: tuple[str, ...] = ("svg", "print", "gif", "video")
FORMAT_LABELS = {"svg": "SVG", "print": "Print PNG", "gif": "Animated GIF", "video": "Video"}
FORMAT_SUFFIX = {"svg": ".svg", "print": ".png", "gif": ".gif", "video": ".mp4"}
FORMAT_FILTER = {
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
MAX_CELL = 64
MAX_DPI = 1200
MAX_BLEED_MM = 50.0
MAX_FPS = 60
MAX_LOOP = 100


class ExportError(Exception):
    """An export that could not be written: no output path, or no ffmpeg."""


class ExportDialog(QDialog):
    """Dialog exporting one render as SVG, print PNG, animated GIF or video."""

    def __init__(
        self,
        image: RGB8,
        parent: QWidget | None = None,
        *,
        frames: list[RGB8] | None = None,
        settings: QSettings | None = None,
    ) -> None:
        """Build the dialog for image, using frames for the animated formats."""
        super().__init__(parent)
        self.setWindowTitle(tr("Export"))
        self.image = image
        self.frames = list(frames) if frames else [image]
        self.written: list[Path] = []
        self._settings = settings or QSettings(SETTINGS_NAME, SETTINGS_NAME)
        self._build()
        self._load_defaults()

    def _build(self) -> None:
        """Create the format selector, the option pages, the path row and the buttons."""
        self.format_box = QComboBox(self)
        self.format_box.setObjectName("export_format")
        for key in FORMATS:
            self.format_box.addItem(tr(FORMAT_LABELS[key]), key)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("export_options")
        self._build_svg_page()
        self._build_print_page()
        self._build_gif_page()
        self._build_video_page()
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("export_path")
        browse = QPushButton(tr("Browse…"), self)
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
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Export"))
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
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
        self.background_edit.setPlaceholderText(tr("#RRGGBB, empty for transparent"))
        form = QFormLayout(page)
        form.addRow(tr("Cell size"), self.cell)
        form.addRow(tr("Background"), self.background_edit)
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
        self.crop_marks = QCheckBox(tr("Crop marks"), page)
        self.crop_marks.setObjectName("export_crop_marks")
        self.separations = QCheckBox(tr("Separations"), page)
        self.separations.setObjectName("export_separations")
        form = QFormLayout(page)
        form.addRow(tr("Resolution"), self.dpi)
        form.addRow(tr("Bleed (mm)"), self.bleed)
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
        self.gif_loop.setSpecialValueText(tr("forever"))
        form = QFormLayout(page)
        form.addRow(tr("Frame rate"), self.gif_fps)
        form.addRow(tr("Loop"), self.gif_loop)
        self.stack.addWidget(page)

    def _build_video_page(self) -> None:
        """Create the video page: frame rate."""
        page = QWidget(self.stack)
        self.video_fps = QSpinBox(page)
        self.video_fps.setObjectName("export_video_fps")
        self.video_fps.setRange(1, MAX_FPS)
        self.video_fps.setValue(DEFAULT_FPS)
        form = QFormLayout(page)
        form.addRow(tr("Frame rate"), self.video_fps)
        self.stack.addWidget(page)

    def format(self) -> str:
        """Return the selected format key: svg, print, gif or video."""
        return str(self.format_box.currentData())

    def export_directory(self) -> Path:
        """Return the remembered export directory, or the home directory."""
        stored = self._settings.value(EXPORT_DIR_KEY)
        return Path(stored) if stored else Path.home()

    def target_path(self) -> Path:
        """Return the output path typed in the dialog, with the format's suffix."""
        text = self.path_edit.text().strip()
        if not text:
            raise ExportError(tr("Choose an output file first."))
        path = Path(text)
        return path if path.suffix else path.with_suffix(FORMAT_SUFFIX[self.format()])

    def background(self) -> str | None:
        """Return the SVG background colour, or None when the field is empty."""
        return self.background_edit.text().strip() or None

    def export_now(self) -> list[Path]:
        """Export the image with the current options and return the files written."""
        target = self.target_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        written = self._write(target)
        self.written = written
        self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
        lines = [tr("Exported {name}", name=path.name) for path in written]
        self.report.setText(REPORT_SEPARATOR.join(lines))
        return written

    def _write(self, target: Path) -> list[Path]:
        """Write the selected format to target and return every file created."""
        kind = self.format()
        if kind == "svg":
            export_svg(self.image, target, cell=self.cell.value(), background=self.background())
            return [target]
        if kind == "print":
            return export_print(
                self.image,
                target,
                dpi=self.dpi.value(),
                bleed_mm=self.bleed.value(),
                crop_marks=self.crop_marks.isChecked(),
                separations=self.separations.isChecked(),
            )
        if kind == "gif":
            export_gif(self.frames, target, fps=self.gif_fps.value(), loop=self.gif_loop.value())
            return [target]
        if not export_video(self.frames, target, fps=self.video_fps.value()):
            reason = tr("No ffmpeg available.")
            raise ExportError(tr("Cannot write {path}: {error}", path=target.name, error=reason))
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
        text = self.path_edit.text().strip() or "export"
        self.path_edit.setText(str(Path(text).with_suffix(FORMAT_SUFFIX[self.format()])))

    def _on_browse(self) -> None:
        """Ask for an output path with the selected format's filter."""
        current = self.path_edit.text().strip() or str(self.export_directory())
        filters = tr(FORMAT_FILTER[self.format()])
        path, _ = QFileDialog.getSaveFileName(self, tr("Export"), current, filters)
        if path:
            self.path_edit.setText(path)

    def _load_defaults(self) -> None:
        """Point the path field at the remembered directory and the format's suffix."""
        suffix = FORMAT_SUFFIX[self.format()]
        self.path_edit.setText(str(self.export_directory() / f"export{suffix}"))


def run_export_dialog(
    image: RGB8, parent: QWidget | None = None, *, frames: list[RGB8] | None = None
) -> list[Path]:
    """Show the export dialog for image and return every file written."""
    dialog = ExportDialog(image, parent, frames=frames)
    dialog.exec()
    return dialog.written
