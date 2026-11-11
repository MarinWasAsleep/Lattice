"""Integration tests for the wired main window and the render worker (T14)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time  # noqa: E402
from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dithercraft.bridge.photocraft import PhotoCraftClient  # noqa: E402
from dithercraft.core.pipeline import render  # noqa: E402
from dithercraft.core.registry import list_algorithms, list_effects  # noqa: E402
from dithercraft.ui import main_window as mw  # noqa: E402
from dithercraft.ui import worker as worker_module  # noqa: E402
from dithercraft.ui.algorithm_panel import AlgorithmPanel  # noqa: E402
from dithercraft.ui.effects_panel import EffectsPanel  # noqa: E402
from dithercraft.ui.palette_panel import PalettePanel  # noqa: E402
from dithercraft.ui.worker import PREVIEW_MAX_SIDE, PreviewResult  # noqa: E402

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

    def place_as_layer(self, img: PILImage.Image, layer_name: str = "DitherCraft") -> int:
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
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    QApplication.processEvents()
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
    assert name == "DitherCraft"
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


def test_untested_version_warns_once(
    window: mw.MainWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An untested PhotoCraft version produces exactly one status-bar warning."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "untested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: "0.23.0")
    window.worker.check_version()
    qapp.processEvents()
    message = window.statusBar().currentMessage()
    assert "0.23.0" in message
    assert "not tested" in message
    assert "0.22.0" in message
    window.statusBar().clearMessage()
    window.worker.check_version()
    qapp.processEvents()
    assert window.statusBar().currentMessage() == ""


def test_unknown_version_shows_nothing(
    window: mw.MainWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown PhotoCraft version produces no warning."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "unknown")
    window.worker.check_version()
    qapp.processEvents()
    assert "not tested" not in window.statusBar().currentMessage()


def test_preset_round_trip_uses_the_presets_folder(
    window: mw.MainWindow, qapp: QApplication, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """Save writes to the default presets folder and Load restores the spec."""
    dialogs.save_path = str(tmp_path / "preset.json")
    window.actions["save_preset"].trigger()
    assert dialogs.calls[-1][1] == str(mw.PRESET_DIR / "preset.json")
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
