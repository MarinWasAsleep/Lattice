"""Tests for the shared export dialog (T33 / CONTRACT §19 to §21, card L-UI2).

The dialog lives in lattice/ui and covers the four export families: PNG,
SVG, print and the GIF/video sequence. The video writer and tr are injected by
the application; these tests inject the Dither ones to prove the pattern, and
pin that the default export renders beyond the preview cap (REVUE bloquant 1).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lattice.modes.dither.export import video as video_module  # noqa: E402
from lattice.pipeline import PipelineSpec  # noqa: E402
from lattice.ui import export_dialog as ed  # noqa: E402
from lattice.ui.export_dialog import ExportDialog, ExportError  # noqa: E402
from lattice.ui.worker import PREVIEW_MAX_SIDE  # noqa: E402

SETTINGS_NAME = "LatticeDither"

needs_ffmpeg = pytest.mark.skipif(
    video_module._resolve_ffmpeg() is None, reason="no ffmpeg binary is available"
)


class FakeSettings:
    """In-memory stand-in for QSettings so tests never touch the registry."""

    store: dict[str, object] = {}

    def __init__(
        self, organisation: str = SETTINGS_NAME, application: str = SETTINGS_NAME
    ) -> None:
        self._prefix = f"{organisation}/{application}/"

    def value(self, key: str, default: object = None) -> object:
        """Return the stored value of key, or default."""
        return FakeSettings.store.get(self._prefix + key, default)

    def setValue(self, key: str, value: object) -> None:
        """Store value under key."""
        FakeSettings.store[self._prefix + key] = value


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> type[FakeSettings]:
    """Replace QSettings with an in-memory store."""
    FakeSettings.store.clear()
    monkeypatch.setattr(ed, "QSettings", FakeSettings)
    return FakeSettings


def _image(size: int = 16) -> np.ndarray:
    """Return a size x size two-colour checkerboard as uint8 RGB."""
    parity = np.add.outer(np.arange(size), np.arange(size)) % 2
    return np.repeat(np.where(parity[:, :, None] == 0, 0, 255), 3, axis=2).astype(np.uint8)


def _source(size: int = 16) -> np.ndarray:
    """Return the checkerboard as a float32 pipeline source in [0, 1]."""
    return _image(size).astype(np.float32) / 255.0


def _frames(count: int = 3, size: int = 16) -> list[np.ndarray]:
    """Return count same-size frames with a moving white band."""
    frames = []
    for index in range(count):
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        frame[:, index * 4 : index * 4 + 4] = 255
        frames.append(frame)
    return frames


def _dialog(kind: str, target: Path, **kwargs) -> ExportDialog:
    """Return a dialog set to kind and pointing at target."""
    dialog = ExportDialog(_source(), PipelineSpec(), **kwargs)
    dialog.format_box.setCurrentIndex(ed.FORMATS.index(kind))
    dialog.path_edit.setText(str(target))
    return dialog


def test_the_defaults_match_the_contract(qapp, settings) -> None:
    """Every option starts at the contract default."""
    dialog = ExportDialog(_source(), PipelineSpec())
    assert dialog.cell.value() == 1
    assert dialog.dpi.value() == 300
    assert dialog.bleed.value() == 0.0
    assert dialog.crop_marks.isChecked() is False
    assert dialog.separations.isChecked() is False
    assert dialog.gif_fps.value() == 12
    assert dialog.video_fps.value() == 12
    assert dialog.gif_loop.value() == 0
    assert dialog.background() is None
    dialog.deleteLater()


def test_all_formats_are_offered(qapp, settings) -> None:
    """The selector lists the four families: PNG, SVG, print, GIF and video."""
    dialog = ExportDialog(_source(), PipelineSpec())
    offered = [dialog.format_box.itemData(index) for index in range(dialog.format_box.count())]
    assert offered == list(ed.FORMATS)
    assert dialog.stack.count() == len(ed.FORMATS)
    dialog.deleteLater()


@pytest.mark.parametrize(
    "kind",
    ["png", "svg", "print", "gif", pytest.param("video", marks=needs_ffmpeg)],
)
def test_each_format_writes_the_expected_files(kind, qapp, settings, tmp_path) -> None:
    """Every format is reachable from the dialog and writes its file."""
    target = tmp_path / f"out{ed.FORMAT_SUFFIX[kind]}"
    kwargs = {"video_writer": video_module.export_video} if kind == "video" else {}
    dialog = _dialog(kind, target, **kwargs)
    written = dialog.export_now()
    assert written == [target]
    assert dialog.written == [target]
    assert target.is_file()
    assert target.stat().st_size > 0
    dialog.deleteLater()


def test_print_separations_writes_five_files(qapp, settings, tmp_path) -> None:
    """Separations add the four ink plates to the print export."""
    dialog = _dialog("print", tmp_path / "plate.png")
    dialog.separations.setChecked(True)
    written = dialog.export_now()
    assert [path.name for path in written] == [
        "plate.png",
        "plate_C.png",
        "plate_M.png",
        "plate_Y.png",
        "plate_K.png",
    ]
    assert all(path.is_file() for path in written)
    dialog.deleteLater()


def test_the_dialog_reports_the_files_written(qapp, settings, tmp_path) -> None:
    """The report label names every file written."""
    dialog = _dialog("print", tmp_path / "plate.png")
    dialog.separations.setChecked(True)
    dialog.export_now()
    assert "plate_K.png" in dialog.report.text()
    dialog.deleteLater()


def test_the_svg_options_reach_the_file(qapp, settings, tmp_path) -> None:
    """Cell size and background are written into the SVG."""
    dialog = _dialog("svg", tmp_path / "out.svg")
    dialog.cell.setValue(3)
    dialog.background_edit.setText("#102030")
    dialog.export_now()
    text = (tmp_path / "out.svg").read_text(encoding="utf-8")
    assert 'width="48"' in text
    assert 'fill="#102030"' in text
    dialog.deleteLater()


def test_the_print_options_reach_the_file(qapp, settings, tmp_path) -> None:
    """Bleed and crop marks enlarge the canvas of the print export."""
    plain = _dialog("print", tmp_path / "plain.png")
    plain.export_now()
    marked = _dialog("print", tmp_path / "marked.png")
    marked.bleed.setValue(2.0)
    marked.crop_marks.setChecked(True)
    marked.export_now()
    with PILImage.open(tmp_path / "plain.png") as handle:
        plain_size = handle.size
    with PILImage.open(tmp_path / "marked.png") as handle:
        marked_size = handle.size
    assert marked_size[0] > plain_size[0]
    assert marked_size[1] > plain_size[1]
    plain.deleteLater()
    marked.deleteLater()


def test_the_animated_formats_use_the_frame_sequence(qapp, settings, tmp_path) -> None:
    """A frame sequence given to the dialog becomes a multi-frame GIF."""
    frames = _frames()
    dialog = _dialog("gif", tmp_path / "anim.gif", frames=frames)
    dialog.export_now()
    with PILImage.open(tmp_path / "anim.gif") as handle:
        assert handle.n_frames == 3
    dialog.deleteLater()


def test_the_video_writer_receives_the_frame_sequence(qapp, settings, tmp_path) -> None:
    """The injected video writer receives the frames, the path and the chosen fps."""
    seen: list[tuple[list[np.ndarray], Path, int]] = []

    def writer(frames: list[np.ndarray], path: Path, *, fps: int = 12) -> bool:
        seen.append((list(frames), path, fps))
        path.write_bytes(b"encoded")
        return True

    frames = _frames()
    target = tmp_path / "out.mp4"
    dialog = _dialog("video", target, frames=frames, video_writer=writer)
    dialog.video_fps.setValue(24)
    assert dialog.export_now() == [target]
    assert len(seen) == 1
    got_frames, path, fps = seen[0]
    assert path == target
    assert fps == 24
    assert len(got_frames) == 3
    assert np.array_equal(got_frames[0], frames[0])
    dialog.deleteLater()


def test_an_animated_export_without_frames_uses_the_full_render(qapp, settings, tmp_path) -> None:
    """Without an injected sequence the GIF holds the single full-resolution render."""
    dialog = _dialog("gif", tmp_path / "still.gif")
    dialog.export_now()
    with PILImage.open(tmp_path / "still.gif") as handle:
        assert handle.n_frames == 1
        assert handle.size == (16, 16)
    dialog.deleteLater()


def test_the_default_export_renders_beyond_the_preview_cap(qapp, settings, tmp_path) -> None:
    """The default render is full resolution: the file exceeds the preview proxy."""
    size = PREVIEW_MAX_SIDE + 100
    dialog = ExportDialog(_source(size), PipelineSpec())
    target = tmp_path / "full.png"
    dialog.path_edit.setText(str(target))
    dialog.export_now()
    with PILImage.open(target) as handle:
        assert handle.size == (size, size)
    dialog.deleteLater()


def test_the_last_directory_survives_a_restart(qapp, settings, tmp_path) -> None:
    """A second dialog starts in the directory the first one exported to."""
    first = _dialog("svg", tmp_path / "out.svg")
    first.export_now()
    first.deleteLater()
    second = ExportDialog(_source(), PipelineSpec())
    assert second.export_directory() == tmp_path
    assert Path(second.path_edit.text()).parent == tmp_path
    assert Path(second.path_edit.text()).name == f"export{ed.FORMAT_SUFFIX[second.format()]}"
    second.deleteLater()


def test_the_remembered_directory_is_stored_in_settings(qapp, settings, tmp_path) -> None:
    """The export directory is written under the export_dir key."""
    dialog = _dialog("svg", tmp_path / "out.svg")
    dialog.export_now()
    key = f"{SETTINGS_NAME}/{SETTINGS_NAME}/{ed.EXPORT_DIR_KEY}"
    assert FakeSettings.store[key] == str(tmp_path)
    dialog.deleteLater()


def test_switching_format_retargets_the_suffix(qapp, settings, tmp_path) -> None:
    """Changing the format updates the path suffix and the visible option page."""
    dialog = _dialog("svg", tmp_path / "out.svg")
    dialog.format_box.setCurrentIndex(ed.FORMATS.index("gif"))
    assert dialog.path_edit.text() == str(tmp_path / "out.gif")
    assert dialog.stack.currentIndex() == ed.FORMATS.index("gif")
    dialog.deleteLater()


def test_an_empty_path_is_reported(qapp, settings) -> None:
    """Exporting without a path raises ExportError instead of writing anywhere."""
    dialog = ExportDialog(_source(), PipelineSpec())
    dialog.path_edit.setText("")
    with pytest.raises(ExportError):
        dialog.export_now()
    dialog.deleteLater()


def test_a_missing_ffmpeg_is_reported_in_the_dialog(qapp, settings, tmp_path) -> None:
    """The video branch reports a missing ffmpeg in the dialog, without a modal box."""
    dialog = _dialog(
        "video", tmp_path / "out.mp4", video_writer=lambda frames, path, *, fps=12: False
    )
    dialog._on_export()
    assert "out.mp4" in dialog.report.text()
    assert dialog.written == []
    assert not (tmp_path / "out.mp4").exists()
    dialog.deleteLater()


def test_a_missing_video_writer_is_reported(qapp, settings, tmp_path) -> None:
    """Without an injected writer the video branch reports it, without a modal box."""
    dialog = _dialog("video", tmp_path / "out.mp4")
    dialog._on_export()
    assert "video" in dialog.report.text().lower()
    assert dialog.written == []
    assert not (tmp_path / "out.mp4").exists()
    dialog.deleteLater()


def test_the_translation_callable_is_injected(qapp, settings, tmp_path) -> None:
    """Every label goes through the injected tr, here a bracketing stand-in."""
    dialog = ExportDialog(_source(), PipelineSpec(), tr=lambda key, **kwargs: f"[{key}]")
    assert dialog.windowTitle() == "[Export]"
    dialog.format_box.setCurrentIndex(ed.FORMATS.index("print"))
    dialog.path_edit.setText(str(tmp_path / "out.png"))
    dialog.export_now()
    assert dialog.report.text() == "[Exported {name}]"
    dialog.deleteLater()


def test_run_export_dialog_returns_the_files_written(qapp, settings, tmp_path, monkeypatch) -> None:
    """The convenience wrapper returns what the dialog wrote."""
    target = tmp_path / "out.svg"

    def fake_exec(self: ExportDialog) -> int:
        self.path_edit.setText(str(target))
        self.export_now()
        return 0

    monkeypatch.setattr(ExportDialog, "exec", fake_exec)
    assert ed.run_export_dialog(_source(), PipelineSpec()) == [target]
