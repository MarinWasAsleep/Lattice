"""Integration tests for the wired main window and the render worker (T14)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtCore import QSize, Qt, QThread  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem  # noqa: E402

from lattice import presets  # noqa: E402
from lattice.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice.modes.dither.i18n import set_language, tr  # noqa: E402
from lattice.modes.dither.preprocess import detect_grid, snap_to_grid  # noqa: E402
from lattice.modes.dither.ui import main_window as mw  # noqa: E402
from lattice.modes.dither.ui.algorithm_panel import AlgorithmPanel  # noqa: E402
from lattice.modes.dither.ui.effects_panel import EffectsPanel  # noqa: E402

# aliased: pytest would collect a bare test_image as a test function
from lattice.modes.dither.ui.gallery import test_image as synthetic_image  # noqa: E402
from lattice.modes.dither.ui.palette_panel import PalettePanel  # noqa: E402
from lattice.palettes.library import library_names  # noqa: E402
from lattice.pipeline import COLOR_METRICS, PaletteSpec, PipelineSpec, render  # noqa: E402
from lattice.registry import list_algorithms, list_effects  # noqa: E402
from lattice.ui import worker as worker_module  # noqa: E402
from lattice.ui.worker import PREVIEW_MAX_SIDE, PreviewResult  # noqa: E402

PREVIEW_TIMEOUT = 2.0
RENDER_TIMEOUT = 5.0


class FakeSettings:
    """In-memory stand-in for QSettings so tests never touch the registry."""

    store: dict[str, object] = {}

    def __init__(self, organisation: str, application: str) -> None:
        self._prefix = f"{organisation}/{application}/"

    def value(self, key: str, default: object = None) -> object:
        """Return the stored value of key, or default."""
        return FakeSettings.store.get(self._prefix + key, default)

    def setValue(self, key: str, value: object) -> None:
        """Store value under key."""
        FakeSettings.store[self._prefix + key] = value


class FakeDialogs:
    """Stand-in for QFileDialog that returns scripted paths and records its calls."""

    open_path = ""
    save_path = ""
    calls: list[tuple[str, str, str]] = []

    @classmethod
    def getOpenFileName(cls, parent: object, title: str, directory: str, filters: str) -> tuple:
        """Return the scripted open path."""
        cls.calls.append((title, directory, filters))
        return (cls.open_path, "")

    @classmethod
    def getSaveFileName(cls, parent: object, title: str, directory: str, filters: str) -> tuple:
        """Return the scripted save path."""
        cls.calls.append((title, directory, filters))
        return (cls.save_path, "")


class FakeClient:
    """Stand-in for PhotoCraftClient that records the layers it receives."""

    def __init__(self) -> None:
        self.placed: list[tuple[PILImage.Image, str]] = []

    def place_as_layer(self, img: PILImage.Image, layer_name: str = "Lattice Dither") -> int:
        """Record the image and return a fixed layer id."""
        self.placed.append((img, layer_name))
        return 7

    def render_document(self) -> PILImage.Image:
        """Return a small solid image as the visible document."""
        return PILImage.new("RGB", (32, 24), (10, 20, 30))


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
    monkeypatch.setattr(mw, "QSettings", FakeSettings)
    return FakeSettings


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch) -> type[FakeDialogs]:
    """Replace QFileDialog with a scripted stand-in."""
    FakeDialogs.open_path = ""
    FakeDialogs.save_path = ""
    FakeDialogs.calls = []
    monkeypatch.setattr(mw, "QFileDialog", FakeDialogs)
    return FakeDialogs


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test away from the real PhotoCraft app."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_module, "version_status", lambda: "tested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: None)


@pytest.fixture
def window(qapp: QApplication, settings: type[FakeSettings], bridge: None) -> mw.MainWindow:
    """Return a shown main window with a running worker thread."""
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


def _wait_until(predicate: Callable[[], bool], timeout: float = PREVIEW_TIMEOUT) -> bool:
    """Spin the event loop until predicate is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        QApplication.processEvents()
        time.sleep(0.005)
    return bool(predicate())


def _source(height: int = 48, width: int = 64) -> np.ndarray:
    """Return a deterministic float32 grey ramp image."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
    img = np.repeat(ramp[None, :, None], height, axis=0)
    return np.ascontiguousarray(np.repeat(img, 3, axis=2))


def _write_png(path: Path, image: np.ndarray) -> str:
    """Write a float32 image as a PNG and return its path as text."""
    rgb8 = np.clip(image * 255.0, 0, 255).astype(np.uint8)
    PILImage.fromarray(rgb8, "RGB").save(path)
    return str(path)


def _canvas_array(window: mw.MainWindow) -> np.ndarray:
    """Return the pixels currently shown by the preview canvas."""
    items = [i for i in window.canvas.scene().items() if isinstance(i, QGraphicsPixmapItem)]
    assert len(items) == 1
    image = items[0].pixmap().toImage().convertToFormat(QImage.Format.Format_RGB888)
    buffer = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
    rows = buffer.reshape(image.height(), image.bytesPerLine())
    return rows[:, : image.width() * 3].reshape(image.height(), image.width(), 3).copy()


def _open(window: mw.MainWindow, dialogs: type[FakeDialogs], path: str) -> None:
    """Load path through the Open image action."""
    dialogs.open_path = path
    window.actions["open_image"].trigger()


def test_panels_replace_the_placeholders(window: mw.MainWindow) -> None:
    """The three placeholder tabs are replaced by the real panels."""
    tabs = window.tabs
    assert [tabs.tabText(index) for index in range(tabs.count())] == list(mw.PANEL_TABS)
    assert isinstance(tabs.widget(window.tab_index("Algorithm")), AlgorithmPanel)
    assert isinstance(tabs.widget(window.tab_index("Palette")), PalettePanel)
    assert isinstance(tabs.widget(window.tab_index("Effects")), EffectsPanel)
    assert window.placeholder_tabs == {}


def test_registries_are_populated(window: mw.MainWindow) -> None:
    """Importing the window registers every algorithm and effect."""
    assert list_algorithms()
    assert list_effects()
    assert window.algorithm_panel.algorithm_combo.count() >= len(list_algorithms())


def test_load_image_then_change_algorithm_updates_preview(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """Loading an image renders a preview and an algorithm change refreshes it fast."""
    results: list[PreviewResult] = []
    window.worker.preview_ready.connect(results.append)
    _open(window, dialogs, _write_png(tmp_path / "in.png", _source()))
    assert window.source is not None
    assert _wait_until(lambda: results)
    first = results[-1]
    combo = window.algorithm_panel.algorithm_combo
    index = combo.findData("bayer_4")
    assert index >= 0
    started = time.monotonic()
    combo.setCurrentIndex(index)
    assert _wait_until(lambda: len(results) > 1)
    elapsed = time.monotonic() - started
    assert elapsed < PREVIEW_TIMEOUT
    assert results[-1].job > first.job
    assert not np.array_equal(results[-1].image, first.image)
    assert window.render_time_label.text().startswith("Render: ")


def test_rapid_changes_render_only_the_last_spec(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """Ten rapid edits inside the debounce window produce one render of the last spec."""
    results: list[PreviewResult] = []
    window.worker.preview_ready.connect(results.append)
    _open(window, dialogs, _write_png(tmp_path / "in.png", _source()))
    assert _wait_until(lambda: results)
    results.clear()
    spin = window.algorithm_panel.pixel_size_spin
    for size in range(2, 12):
        spin.setValue(size)
    assert _wait_until(lambda: results)
    time.sleep(0.25)
    qapp.processEvents()
    assert len(results) == 1
    assert window.spec.pixel_size == 11
    expected = render(window.source, window.spec, max_side=PREVIEW_MAX_SIDE)
    assert np.array_equal(results[0].image, expected)
    results.clear()
    window.worker._pending_job = window.worker._job - 1
    window.worker._render_preview()
    qapp.processEvents()
    assert results == []


def test_preview_uses_the_1024_proxy(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """A large source is previewed through the max_side proxy, with a matching original."""
    results: list[PreviewResult] = []
    window.worker.preview_ready.connect(results.append)
    _open(window, dialogs, _write_png(tmp_path / "big.png", _source(600, 1100)))
    assert _wait_until(lambda: results, timeout=RENDER_TIMEOUT)
    result = results[-1]
    assert max(result.image.shape[:2]) <= PREVIEW_MAX_SIDE
    assert result.original.shape == result.image.shape


def test_preview_updates_the_canvas_and_drops_stale_results(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """The canvas shows the render, and an older PreviewResult is not applied."""
    _open(window, dialogs, _write_png(tmp_path / "in.png", _source()))
    assert _wait_until(lambda: window.canvas.scene().sceneRect().width() > 0)
    expected = render(window.source, window.spec, max_side=PREVIEW_MAX_SIDE)
    assert window.canvas.scene().sceneRect().size().toSize() == QSize(*expected.shape[1::-1])
    assert np.array_equal(_canvas_array(window), expected)
    stale = PreviewResult(job=window._applied_job - 1, image=np.zeros_like(expected),
                          original=np.zeros_like(expected), seconds=0.0)
    window._on_preview_ready(stale)
    assert np.array_equal(_canvas_array(window), expected)


def test_send_places_one_png_with_a_fake_bridge(
    window: mw.MainWindow,
    qapp: QApplication,
    dialogs: type[FakeDialogs],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Send renders at full resolution and places exactly one PNG as a layer."""
    client = FakeClient()
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: client)
    _open(window, dialogs, _write_png(tmp_path / "in.png", _source()))
    assert _wait_until(lambda: window.source is not None)
    window.actions["send_to_photocraft"].trigger()
    assert _wait_until(lambda: client.placed, timeout=RENDER_TIMEOUT)
    assert len(client.placed) == 1
    image, name = client.placed[0]
    assert name == "Lattice Dither"
    assert image.size == (64, 48)
    assert np.array_equal(np.asarray(image), render(window.source, window.spec))
    assert _wait_until(lambda: "layer 7" in window.statusBar().currentMessage())


def test_get_from_photocraft_loads_the_document(
    window: mw.MainWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Get from PhotoCraft adopts the document returned by the bridge."""
    client = FakeClient()
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: client)
    window.actions["get_from_photocraft"].trigger()
    assert _wait_until(lambda: window.source is not None)
    assert window.source.shape == (24, 32, 3)


def test_connection_indicator_follows_the_worker(
    window: mw.MainWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status bar shows the state reported by discover() in the worker."""
    assert _wait_until(lambda: window.connection_label.text() == "PhotoCraft: disconnected")
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: object())
    window.worker.check_connection()
    assert _wait_until(lambda: window.connection_label.text() == "PhotoCraft: connected")


def test_untested_version_warns_once_and_keeps_the_warning(
    qapp: QApplication, settings: type[FakeSettings], bridge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The startup check warns once, in a permanent label that later messages do not wipe."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "untested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: "0.23.0")
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    try:
        assert _wait_until(lambda: "0.23.0" in win.version_label.text())
        assert "not tested" in win.version_label.text() and "0.22.0" in win.version_label.text()
        win.statusBar().showMessage("Exported out.png", 5000)
        qapp.processEvents()
        assert "not tested" in win.version_label.text()
        win.version_label.clear()
        time.sleep(0.2)
        qapp.processEvents()
        assert win.version_label.text() == ""
    finally:
        win.close()


def test_shutdown_waits_for_a_running_thread(
    window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timed-out shutdown keeps waiting instead of leaving a running QThread behind."""
    thread, real_wait, calls = window.thread, QThread.wait, []

    def fake_wait(self: QThread, *args: object) -> bool:
        calls.append(args)
        return False if len(calls) == 1 else real_wait(self, *args)

    monkeypatch.setattr(QThread, "wait", fake_wait)
    window.shutdown()
    assert calls[0] == (mw.WORKER_STOP_MS,)
    assert window.thread is None and thread.isRunning() is False


def test_unknown_version_shows_nothing(
    window: mw.MainWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown PhotoCraft version produces no warning."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "unknown")
    window.worker.check_version()
    qapp.processEvents()
    assert window.version_label.text() == ""


def test_preset_round_trip_uses_the_user_presets_folder(
    window: mw.MainWindow,
    qapp: QApplication,
    dialogs: type[FakeDialogs],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save defaults to the user presets folder and Load restores the spec."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    user_dir = presets.user_preset_dir()
    dialogs.save_path = str(tmp_path / "preset.json")
    window.actions["save_preset"].trigger()
    assert Path(dialogs.calls[-1][1]).parent == user_dir
    assert Path(dialogs.save_path).exists()
    combo = window.algorithm_panel.algorithm_combo
    combo.setCurrentIndex(combo.findData("bayer_8"))
    assert window.algorithm_panel.algorithm_combo.currentData() == "bayer_8"
    dialogs.open_path = dialogs.save_path
    window.actions["load_preset"].trigger()
    assert window.spec.algorithm_id == "floyd_steinberg"
    assert window.algorithm_panel.algorithm_combo.currentData() == "floyd_steinberg"


def test_export_png_writes_the_full_resolution_render(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """Export PNG writes the full-resolution render, not the preview proxy."""
    _open(window, dialogs, _write_png(tmp_path / "in.png", _source()))
    assert _wait_until(lambda: window.source is not None)
    target = tmp_path / "out.png"
    dialogs.save_path = str(target)
    window.actions["export_png"].trigger()
    assert _wait_until(target.exists, timeout=RENDER_TIMEOUT)
    with PILImage.open(target) as handle:
        assert handle.size == (64, 48)


def test_geometry_is_remembered(window: mw.MainWindow, settings: type[FakeSettings]) -> None:
    """Closing the window stores its geometry through QSettings."""
    window.close()
    assert any(key.endswith("geometry") for key in settings.store)


def test_worker_module_never_touches_widgets() -> None:
    """The worker module imports no widget class, so it cannot touch a widget."""
    source = Path(worker_module.__file__).read_text(encoding="utf-8")
    assert "QtWidgets" not in source
    assert "QMessageBox" not in source


# --------------------------------------------------------------------------- T32
# Integration and acceptance: every 1.1 control is reachable from the window, the
# gallery is wired, the §23 pre-pass is gated on its own confidence, and the whole
# pipeline runs from a preset on disk to a PNG on disk inside the budget.

CHECKLIST = Path(__file__).resolve().parent / "manual" / "CHECKLIST.md"
# The H9 recipe must name each of these, in any wording that contains the term.
CHECKLIST_TERMS: tuple[str, ...] = (
    "photo",
    "pixel art",
    "scan",
    "svg",
    "print",
    "gif",
    "video",
    "cli",
    "french",
    "undo",
    "redo",
    "photocraft",
)
GRID_CONFIDENCE = 0.5
PIPELINE_BUDGET_S = 5.0


def _colour_source(height: int = 48, width: int = 64) -> np.ndarray:
    """Return a low-contrast coloured image: saturated enough for every control to bite."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    u, v = xs / (width - 1), ys / (height - 1)
    img = np.empty((height, width, 3), dtype=np.float32)
    img[:, :, 0] = 0.2 + 0.6 * u
    img[:, :, 1] = 0.2 + 0.6 * v
    img[:, :, 2] = 0.2 + 0.6 * (1.0 - u) * (1.0 - v)
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0))


def _pixel_art(factor: int = 4, size: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Return (upscaled, original) pixel art: a nearest-neighbour upscale of a lattice."""
    rng = np.random.default_rng(7)
    small = rng.integers(0, 2, size=(size, size, 3)).astype(np.float32)
    big = np.repeat(np.repeat(small, factor, axis=0), factor, axis=1)
    return np.ascontiguousarray(big), np.ascontiguousarray(small)


def _smooth_photo(height: int = 64, width: int = 64) -> np.ndarray:
    """Return a smooth gradient photo, the case the pre-pass must never touch."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    img = np.stack([xs / (width - 1), ys / (height - 1), (xs + ys) / (width + height - 2)], axis=2)
    return np.ascontiguousarray(img.astype(np.float32))


def test_the_algorithm_panel_exposes_the_conditioning_strip(window: mw.MainWindow) -> None:
    """Saturation, pre-blur and auto levels sit next to the tone controls, at their defaults."""
    panel = window.algorithm_panel
    assert panel.saturation.value() == pytest.approx(0.0)
    assert panel.pre_blur.value() == pytest.approx(0.0)
    assert panel.auto_levels.isChecked() is False
    assert (panel.saturation.spin.minimum(), panel.saturation.spin.maximum()) == (-1.0, 1.0)
    assert (panel.pre_blur.spin.minimum(), panel.pre_blur.spin.maximum()) == (0.0, 20.0)


def test_the_algorithm_panel_exposes_every_colour_metric(window: mw.MainWindow) -> None:
    """The metric combo offers exactly the four metrics of §12, srgb first."""
    combo = window.algorithm_panel.metric_combo
    offered = [combo.itemData(index) for index in range(combo.count())]
    assert offered == list(COLOR_METRICS)
    assert combo.currentData() == "srgb"


def test_strength_and_the_halftone_parameters_reach_the_user(window: mw.MainWindow) -> None:
    """Every algorithm parameter, strength and the halftone set included, has a widget."""
    panel = window.algorithm_panel
    for info in list_algorithms():
        panel.load_from(PipelineSpec(algorithm_id=info.id))
        for spec in info.params:
            assert panel.param_form.widget(spec.id) is not None, (info.id, spec.id)
    panel.load_from(PipelineSpec(algorithm_id="halftone_dots"))
    for key in ("cell_size", "angle", "dot_shape", "oversample", "per_channel", "strength"):
        assert panel.param_form.widget(key) is not None, key


def test_each_conditioning_control_changes_the_render(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """Each new control is wired to the pipeline: moving it changes the rendered pixels."""
    _open(window, dialogs, _write_png(tmp_path / "in.png", _colour_source()))
    assert _wait_until(lambda: window.source is not None)
    panel = window.algorithm_panel
    base = render(window.source, window.spec)
    for widget, field, value in (
        (panel.saturation.spin, "saturation", 1.0),
        (panel.pre_blur.spin, "pre_blur", 6.0),
    ):
        widget.setValue(value)
        window._rebuild_spec()
        assert getattr(window.spec, field) == pytest.approx(value)
        assert not np.array_equal(render(window.source, window.spec), base), field
        widget.setValue(0.0)
    panel.auto_levels.setChecked(True)
    window._rebuild_spec()
    assert window.spec.auto_levels is True
    assert not np.array_equal(render(window.source, window.spec), base)


def test_the_colour_metric_reaches_the_kernel(window: mw.MainWindow) -> None:
    """Choosing oklab in the combo changes the indices, so the metric is really applied."""
    panel = window.algorithm_panel
    spec = PipelineSpec(
        algorithm_id="floyd_steinberg", palette=PaletteSpec(source="builtin", name="pico8")
    )
    panel.load_from(spec)
    srgb = render(synthetic_image(), spec)
    panel.metric_combo.setCurrentIndex(panel.metric_combo.findData("oklab"))
    panel.apply_to(spec)
    assert spec.color_metric == "oklab"
    oklab = render(synthetic_image(), spec)
    assert float((srgb != oklab).any(axis=2).mean()) > 0.05


def test_every_new_parameter_round_trips_through_a_preset(
    window: mw.MainWindow,
    qapp: QApplication,
    dialogs: type[FakeDialogs],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set every 1.1 control, save a preset, reload it, and get the same values back."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    panel = window.algorithm_panel
    panel.saturation.spin.setValue(-0.75)
    panel.pre_blur.spin.setValue(4.5)
    panel.auto_levels.setChecked(True)
    panel.metric_combo.setCurrentIndex(panel.metric_combo.findData("lab2000"))
    window._rebuild_spec()
    expected = copy.deepcopy(window.spec)
    dialogs.save_path = str(tmp_path / "preset.json")
    window.actions["save_preset"].trigger()
    assert Path(dialogs.save_path).is_file()
    panel.load_from(PipelineSpec())
    assert panel.saturation.value() == pytest.approx(0.0)
    dialogs.open_path = dialogs.save_path
    window.actions["load_preset"].trigger()
    assert window.spec.saturation == pytest.approx(expected.saturation)
    assert window.spec.pre_blur == pytest.approx(expected.pre_blur)
    assert window.spec.auto_levels is expected.auto_levels
    assert window.spec.color_metric == expected.color_metric
    assert panel.saturation.value() == pytest.approx(-0.75)
    assert panel.pre_blur.value() == pytest.approx(4.5)
    assert panel.auto_levels.isChecked() is True
    assert panel.metric_combo.currentData() == "lab2000"


def test_the_palette_panel_exposes_the_library_lock_and_order(window: mw.MainWindow) -> None:
    """The library combo lists every shipped palette, and lock and order reach the spec."""
    panel = window.palette_panel
    offered = [panel.library_combo.itemData(index) for index in range(panel.library_combo.count())]
    assert set(library_names()) <= set(offered)
    panel.library_combo.setCurrentIndex(panel.library_combo.findData(library_names()[0]))
    panel._on_library_chosen(panel.library_combo.currentIndex())
    assert panel.colors()
    panel._on_swatch_lock_toggled(0)
    panel._on_swatch_dropped(0, 1)
    window._rebuild_spec()
    assert window.spec.palette.locked == [panel.colors()[0]]
    assert window.spec.palette.order == [1, 0, *range(2, len(panel.colors()))]


def test_the_effects_panel_lists_the_cmyk_halftone(window: mw.MainWindow) -> None:
    """halftone_cmyk is a post-effect and appears in the Add menu."""
    panel = window.effects_panel
    panel._rebuild_add_menu()
    offered = [action.data() for action in panel.add_menu.actions()]
    assert "halftone_cmyk" in offered
    assert "halftone_cmyk" in {info.id for info in list_effects()}


def test_the_gallery_is_wired_into_the_window(window: mw.MainWindow) -> None:
    """The gallery lives in its own dock and holds one cell per registered algorithm."""
    # AlgorithmGallery is a factory in the app module (the widget lives in the core),
    # so the check is duck-typed on the API the window relies on.
    assert hasattr(window.gallery, "cells") and hasattr(window.gallery, "set_search")
    assert window.dockWidgetArea(window.gallery_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.gallery_dock.widget() is window.gallery
    assert len(window.gallery.cells()) == len(list_algorithms())


def test_choosing_a_gallery_cell_selects_the_algorithm(
    window: mw.MainWindow, qapp: QApplication
) -> None:
    """A gallery choice drives the algorithm combo, exactly as picking it there would."""
    combo = window.algorithm_panel.algorithm_combo
    assert combo.currentData() != "bayer_4"
    window.gallery.algorithm_chosen.emit("bayer_4")
    qapp.processEvents()
    assert combo.currentData() == "bayer_4"
    assert window.spec.algorithm_id == "bayer_4"


def test_an_unknown_gallery_choice_is_ignored(window: mw.MainWindow) -> None:
    """A gallery id the registry does not know leaves the selection alone."""
    combo = window.algorithm_panel.algorithm_combo
    before = combo.currentData()
    window.gallery.algorithm_chosen.emit("no_such_algorithm")
    assert combo.currentData() == before


def test_prepare_source_is_off_by_default(window: mw.MainWindow) -> None:
    """Both pre-pass toggles start unchecked and are reachable from the toolbar."""
    assert window.actions["prepare_source"].isCheckable()
    assert window.actions["prepare_source"].isChecked() is False
    assert window.actions["descreen"].isCheckable()
    assert window.actions["descreen"].isChecked() is False
    in_toolbar = {action.objectName() for action in window.toolbar.actions()}
    assert {"prepare_source", "descreen"} <= in_toolbar


def test_prepare_source_reports_the_grid_before_applying_it(
    window: mw.MainWindow, qapp: QApplication
) -> None:
    """The detected grid and confidence are shown, and the snap then recovers the original."""
    big, small = _pixel_art()
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(big)
    assert confidence >= GRID_CONFIDENCE
    window.actions["prepare_source"].setChecked(True)
    window._set_source(big)
    qapp.processEvents()
    assert window.grid_label.text() == tr(
        mw.GRID_FOUND, cell_w=cell_w, cell_h=cell_h, confidence=confidence
    )
    snapped = snap_to_grid(big, (cell_w, cell_h, offset_x, offset_y))
    assert np.array_equal(window.prepared_source, snapped)
    assert np.array_equal(window.prepared_source, small)


def test_prepare_source_leaves_a_photo_untouched_below_the_confidence(
    window: mw.MainWindow, qapp: QApplication
) -> None:
    """A smooth photo scores below 0.5, so the pre-pass must not touch a single pixel."""
    photo = _smooth_photo()
    assert detect_grid(photo)[4] < GRID_CONFIDENCE
    window.actions["prepare_source"].setChecked(True)
    window.actions["descreen"].setChecked(True)
    window._set_source(photo)
    qapp.processEvents()
    assert np.array_equal(window.prepared_source, photo)
    assert window.grid_label.text() == tr(mw.GRID_MISSING, confidence=detect_grid(photo)[4])


def test_the_pre_pass_is_the_identity_when_both_toggles_are_off(
    window: mw.MainWindow, qapp: QApplication
) -> None:
    """With the toggles off the source reaches the worker unchanged and no grid is reported."""
    big, _small = _pixel_art()
    window._set_source(big)
    qapp.processEvents()
    assert np.array_equal(window.prepared_source, big)
    assert window.grid_label.text() == ""


def test_the_prepared_source_is_what_the_worker_renders(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """The preview is rendered from the prepared source, not from the raw one."""
    big, small = _pixel_art()
    window.actions["prepare_source"].setChecked(True)
    _open(window, dialogs, _write_png(tmp_path / "art.png", big))
    assert _wait_until(lambda: window._last_image is not None)
    expected = render(small, window.spec, max_side=PREVIEW_MAX_SIDE)
    assert np.array_equal(window._last_image, expected)


def test_the_full_pipeline_runs_from_a_preset_on_disk_to_a_png_on_disk(
    window: mw.MainWindow,
    qapp: QApplication,
    dialogs: type[FakeDialogs],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 1024x1024 render, preset from disk to PNG on disk, offscreen, inside five seconds.

    The preset carries every control this card added, including the ``lab2000`` metric,
    so the budget covers the slowest kernel the window can ask for.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    source = _write_png(tmp_path / "big.png", _colour_source(1024, 1024))
    preset_path = tmp_path / "preset.json"
    presets.save_preset(
        preset_path,
        PipelineSpec(
            algorithm_id="floyd_steinberg",
            palette=PaletteSpec(source="builtin", name="pico8"),
            saturation=0.3,
            pre_blur=1.0,
            auto_levels=True,
            color_metric="lab2000",
        ),
    )
    target = tmp_path / "out.png"
    started = time.monotonic()
    _open(window, dialogs, source)
    dialogs.open_path = str(preset_path)
    window.actions["load_preset"].trigger()
    dialogs.save_path = str(target)
    window.actions["export_png"].trigger()
    assert _wait_until(target.exists, timeout=PIPELINE_BUDGET_S)
    elapsed = time.monotonic() - started
    assert elapsed < PIPELINE_BUDGET_S, f"{elapsed:.2f}s"
    with PILImage.open(target) as handle:
        assert handle.size == (1024, 1024)
    assert window.spec.auto_levels is True and window.spec.pre_blur == 1.0
    assert window.spec.color_metric == "lab2000"


def test_the_window_follows_a_language_change(
    qapp: QApplication, settings: type[FakeSettings]
) -> None:
    """Built in French, every label of the window comes from the French catalogue."""
    set_language("fr")
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    try:
        assert win.windowTitle() == tr("Lattice Dither")
        assert win.tabs.tabText(win.tab_index("Algorithm")) == tr("Algorithm")
        assert win.tabs.tabText(win.tab_index("Algorithm")) != "Algorithm"
        assert win.actions["prepare_source"].text() == tr("Prepare source")
        assert win.gallery_dock.windowTitle() == tr("Gallery")
        combo = win.algorithm_panel.metric_combo
        assert combo.itemText(combo.findData("linear")) == tr("Linear")
        assert win.algorithm_panel.reset_button.text() == tr("Reset")
    finally:
        win.close()
        qapp.processEvents()
        set_language("en")


def test_the_checklist_covers_the_h9_recipe() -> None:
    """tests/manual/CHECKLIST.md names every source type, export path and round trip."""
    assert CHECKLIST.is_file(), CHECKLIST
    text = CHECKLIST.read_text(encoding="utf-8").lower()
    missing = [term for term in CHECKLIST_TERMS if term not in text]
    assert missing == [], missing
