"""Tests for the preview canvas and the main window shell."""

from __future__ import annotations

import os
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPalette, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsPixmapItem,
    QLabel,
    QMessageBox,
    QTabWidget,
)

from lattice_core.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice_core.ui import worker as worker_module  # noqa: E402
from lattice_core.ui.canvas import PreviewCanvas  # noqa: E402
from lattice_dither.ui import main_window as mw  # noqa: E402
from lattice_dither.ui.algorithm_panel import AlgorithmPanel  # noqa: E402
from lattice_dither.ui.app import create_application, dark_palette, main  # noqa: E402
from lattice_dither.ui.effects_panel import EffectsPanel  # noqa: E402
from lattice_dither.ui.main_window import PANEL_TABS, MainWindow  # noqa: E402
from lattice_dither.ui.palette_panel import PalettePanel  # noqa: E402

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
REGISTRY_KEY = r"Software\LatticeDither\LatticeDither"


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


def _persisted_geometry() -> object:
    """Return the persisted geometry value, or None when nothing is stored.

    Cross-platform: HKCU\\Software\\LatticeDither\\LatticeDither on Windows,
    ~/.config/LatticeDither/LatticeDither.conf on Linux — QSettings resolves it.
    """

    return QSettings("LatticeDither", "LatticeDither").value("geometry")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> type[FakeSettings]:
    """Replace QSettings with an in-memory store."""
    FakeSettings.store.clear()
    monkeypatch.setattr(mw, "QSettings", FakeSettings)
    return FakeSettings


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every MainWindow away from the real PhotoCraft app and its CLI."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_module, "version_status", lambda: "tested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: None)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def canvas(qapp: QApplication) -> PreviewCanvas:
    """Return a shown canvas of a fixed size."""
    view = PreviewCanvas()
    view.resize(200, 200)
    view.show()
    QApplication.processEvents()
    yield view
    view.close()


def _solid(height: int, width: int, color: tuple[int, int, int]) -> np.ndarray:
    """Return a uint8 RGB image filled with one colour."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = color
    return image


def _pixmap_item(canvas: PreviewCanvas) -> QGraphicsPixmapItem:
    """Return the single pixmap item of the canvas scene."""
    items = [item for item in canvas.scene().items() if isinstance(item, QGraphicsPixmapItem)]
    assert len(items) == 1
    return items[0]


def _render_scene(canvas: PreviewCanvas, size: int, source: QRectF) -> QImage:
    """Render a scene rectangle into a square QImage of the given size."""
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    canvas.scene().render(painter, QRectF(0, 0, size, size), source)
    painter.end()
    return image


def _mouse(kind: QEvent.Type, x: float, y: float, button: Qt.MouseButton) -> QMouseEvent:
    """Build a mouse event at a viewport position."""
    point = QPointF(x, y)
    return QMouseEvent(kind, point, point, button, button, Qt.KeyboardModifier.NoModifier)


def test_main_window_builds_offscreen(
    qapp: QApplication, settings: type[FakeSettings], bridge: None
) -> None:
    """The shell builds with canvas, dock tabs, toolbar actions and status bar."""
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    assert window.windowTitle() == "Lattice Dither"
    assert isinstance(window.centralWidget(), PreviewCanvas)
    assert window.dock.isVisible()
    assert window.dockWidgetArea(window.dock) == Qt.DockWidgetArea.RightDockWidgetArea
    tabs = window.tabs
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == list(PANEL_TABS)
    assert isinstance(tabs.widget(window.tab_index("Algorithm")), AlgorithmPanel)
    assert isinstance(tabs.widget(window.tab_index("Palette")), PalettePanel)
    assert isinstance(tabs.widget(window.tab_index("Effects")), EffectsPanel)
    expected = {
        "open_image",
        "get_from_photocraft",
        "send_to_photocraft",
        "export_png",
        "load_preset",
        "save_preset",
        "mode_before",
        "mode_after",
        "mode_split",
        "zoom_fit",
        "zoom_100",
        "zoom_200",
        "zoom_400",
    }
    assert expected <= set(window.actions)
    assert window.statusBar() is not None
    assert window.connection_label.text() in {
        "PhotoCraft: unknown",
        "PhotoCraft: connected",
        "PhotoCraft: disconnected",
    }
    assert window.render_time_label.text() == "Render: -"
    window.close()


def test_actions_are_wired_to_real_slots(
    qapp: QApplication, settings: type[FakeSettings], bridge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file and bridge actions report errors instead of logging a placeholder."""
    window = MainWindow()
    errors: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[2]))
    for key in ("send_to_photocraft", "export_png"):
        window.actions[key].trigger()
    assert len(errors) == 2
    assert all("Load an image" in message for message in errors)
    window.close()


def test_mode_and_zoom_actions_drive_canvas(
    qapp: QApplication, settings: type[FakeSettings], bridge: None
) -> None:
    """Mode and zoom actions act on the preview canvas."""
    window = MainWindow()
    window.canvas.set_image(_solid(8, 8, WHITE))
    window.actions["mode_split"].trigger()
    assert window.canvas.mode() == "split"
    window.actions["mode_before"].trigger()
    assert window.canvas.mode() == "before"
    window.actions["zoom_400"].trigger()
    assert window.canvas.zoom() == pytest.approx(4.0)
    window.actions["zoom_100"].trigger()
    assert window.canvas.zoom() == pytest.approx(1.0)
    window.close()


def test_replace_tab_swaps_placeholder(
    qapp: QApplication, settings: type[FakeSettings], bridge: None
) -> None:
    """A placeholder tab can be replaced by a real panel widget."""
    window = MainWindow()
    panel = QLabel("real panel")
    window.replace_tab("Palette", panel)
    assert window.tabs.widget(window.tab_index("Palette")) is panel
    assert "Palette" not in window.placeholder_tabs
    with pytest.raises(KeyError):
        window.replace_tab("Nope", panel)
    window.close()


def test_set_image_accepts_tiny_and_large(canvas: PreviewCanvas) -> None:
    """A 1x1 and a 4000x3000 image are both accepted."""
    canvas.set_image(_solid(1, 1, WHITE))
    assert canvas.scene().sceneRect().size().toSize().width() == 1
    assert _pixmap_item(canvas).pixmap().size().width() == 1
    canvas.set_image(_solid(3000, 4000, RED))
    rect = canvas.scene().sceneRect()
    assert (rect.width(), rect.height()) == (4000, 3000)
    assert _pixmap_item(canvas).pixmap().size().width() == 4000


def test_set_image_rejects_bad_shape(canvas: PreviewCanvas) -> None:
    """A non RGB array is rejected."""
    with pytest.raises(ValueError):
        canvas.set_image(np.zeros((4, 4), dtype=np.uint8))
    with pytest.raises(ValueError):
        canvas.set_image(np.zeros((4, 4, 3), dtype=np.float32))


def test_nearest_neighbour_at_400_percent(canvas: PreviewCanvas) -> None:
    """Zooming keeps hard pixel edges because the display is not smoothed."""
    checker = np.zeros((2, 2, 3), dtype=np.uint8)
    checker[0, 0] = BLACK
    checker[0, 1] = WHITE
    checker[1, 0] = WHITE
    checker[1, 1] = BLACK
    canvas.set_image(checker)
    canvas.set_zoom(4.0)
    item = _pixmap_item(canvas)
    assert item.transformationMode() == Qt.TransformationMode.FastTransformation
    image = _render_scene(canvas, 8, QRectF(0, 0, 2, 2))
    assert image.pixelColor(0, 0) == QColor(*BLACK)
    assert image.pixelColor(3, 3) == QColor(*BLACK)
    assert image.pixelColor(4, 0) == QColor(*WHITE)
    assert image.pixelColor(0, 4) == QColor(*WHITE)
    assert image.pixelColor(7, 7) == QColor(*BLACK)


def test_split_mode_shows_both_halves(canvas: PreviewCanvas) -> None:
    """Split mode shows the original on the left and the render on the right."""
    canvas.set_original(_solid(2, 4, BLUE))
    canvas.set_image(_solid(2, 4, RED))
    canvas.set_mode("split")
    image = _pixmap_item(canvas).pixmap().toImage()
    assert image.pixelColor(0, 0) == QColor(*BLUE)
    assert image.pixelColor(1, 1) == QColor(*BLUE)
    assert image.pixelColor(2, 0) == QColor(*RED)
    assert image.pixelColor(3, 1) == QColor(*RED)


def test_before_mode_uses_original(canvas: PreviewCanvas) -> None:
    """Before mode shows the original image, after mode the render."""
    canvas.set_original(_solid(2, 2, BLUE))
    canvas.set_image(_solid(2, 2, RED))
    canvas.set_mode("before")
    assert _pixmap_item(canvas).pixmap().toImage().pixelColor(0, 0) == QColor(*BLUE)
    canvas.set_mode("after")
    assert _pixmap_item(canvas).pixmap().toImage().pixelColor(0, 0) == QColor(*RED)
    canvas.set_original(None)
    canvas.set_mode("before")
    assert _pixmap_item(canvas).pixmap().toImage().pixelColor(0, 0) == QColor(*RED)


def test_set_mode_rejects_unknown(canvas: PreviewCanvas) -> None:
    """An unknown mode raises ValueError."""
    with pytest.raises(ValueError):
        canvas.set_mode("sideways")


def test_zoom_fit_and_set_zoom(canvas: PreviewCanvas) -> None:
    """zoom_fit fits the image and set_zoom applies the factor."""
    canvas.set_image(_solid(400, 800, WHITE))
    canvas.zoom_fit()
    assert canvas.zoom() <= 1.0
    assert canvas.transform().m11() == pytest.approx(canvas.zoom())
    canvas.set_zoom(2.0)
    assert canvas.transform().m11() == pytest.approx(2.0)
    canvas.set_zoom(1000.0)
    assert canvas.zoom() <= 32.0


def test_wheel_zooms_around_cursor(canvas: PreviewCanvas) -> None:
    """A wheel notch zooms in and keeps the scene point under the cursor fixed."""
    canvas.set_image(_solid(400, 400, WHITE))
    canvas.set_zoom(1.0)
    QApplication.processEvents()
    cursor = QPointF(150.0, 40.0)
    before = canvas.mapToScene(cursor.toPoint())
    event = QWheelEvent(
        cursor,
        cursor,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas.viewport(), event)
    QApplication.processEvents()
    assert canvas.zoom() > 1.0
    after = canvas.mapToScene(cursor.toPoint())
    assert after.x() == pytest.approx(before.x(), abs=1.0)
    assert after.y() == pytest.approx(before.y(), abs=1.0)


def test_left_drag_pans(canvas: PreviewCanvas) -> None:
    """Dragging with the left button scrolls the view."""
    canvas.set_image(_solid(100, 100, WHITE))
    canvas.set_zoom(4.0)
    QApplication.processEvents()
    horizontal = canvas.horizontalScrollBar()
    horizontal.setValue(horizontal.maximum() // 2)
    before = horizontal.value()
    viewport = canvas.viewport()
    left = Qt.MouseButton.LeftButton
    QApplication.sendEvent(viewport, _mouse(QEvent.Type.MouseButtonPress, 100, 100, left))
    QApplication.sendEvent(viewport, _mouse(QEvent.Type.MouseMove, 60, 100, left))
    QApplication.sendEvent(viewport, _mouse(QEvent.Type.MouseButtonRelease, 60, 100, left))
    assert horizontal.value() == before + 40


def test_middle_drag_pans(canvas: PreviewCanvas) -> None:
    """Dragging with the middle button scrolls the view too."""
    canvas.set_image(_solid(100, 100, WHITE))
    canvas.set_zoom(4.0)
    QApplication.processEvents()
    vertical = canvas.verticalScrollBar()
    vertical.setValue(vertical.maximum() // 2)
    before = vertical.value()
    viewport = canvas.viewport()
    QApplication.sendEvent(
        viewport, _mouse(QEvent.Type.MouseButtonPress, 100, 100, Qt.MouseButton.MiddleButton)
    )
    QApplication.sendEvent(
        viewport, _mouse(QEvent.Type.MouseMove, 100, 70, Qt.MouseButton.MiddleButton)
    )
    QApplication.sendEvent(
        viewport, _mouse(QEvent.Type.MouseButtonRelease, 100, 70, Qt.MouseButton.MiddleButton)
    )
    assert vertical.value() == before + 30


def test_create_application_uses_fusion_and_dark_palette(qapp: QApplication) -> None:
    """The bootstrap applies the Fusion style and a dark palette."""
    app = create_application([])
    assert app is qapp
    assert app.style().objectName().lower() == "fusion"
    window_color = app.palette().color(QPalette.ColorRole.Window)
    assert window_color.lightness() < 128
    assert dark_palette().color(QPalette.ColorRole.Window).lightness() < 128


def test_main_runs_the_event_loop(
    qapp: QApplication, settings: type[FakeSettings], bridge: None
) -> None:
    """main() builds the window, enters the event loop and returns its exit code."""
    QTimer.singleShot(0, qapp.quit)
    assert main([]) == 0


def test_window_never_spawns_a_process_or_writes_the_registry(
    qapp: QApplication,
    settings: type[FakeSettings],
    bridge: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building and closing a window spawns no process and leaves persisted settings untouched."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test must never spawn a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    before = _persisted_geometry()
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    window.close()
    QApplication.processEvents()
    assert _persisted_geometry() == before
