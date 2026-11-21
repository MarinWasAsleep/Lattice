"""Tests for the shared widgets of lattice/ui (card L-UI).

Covers every accept item of the card: no application import in lattice/ui
(E8), full-resolution export matching the pipeline output size, honest preset
indicator, and each widget (canvas + worker + split, Looks grid, bridge status
dot, empty state) with an offscreen smoke test.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lattice.dither  # noqa: E402,F401  (registers every algorithm)
import lattice.effects  # noqa: E402,F401  (registers every effect)
from lattice import color  # noqa: E402
from lattice.pipeline import PipelineSpec, render  # noqa: E402
from lattice.types import RGB8, Image  # noqa: E402
from lattice.ui import (  # noqa: E402
    MAX_SOURCE_SIDE,
    PREVIEW_MAX_SIDE,
    PREVIEW_STAGES,
    BridgeStatusDot,
    EmptyState,
    ExportDialog,
    ExportError,
    Look,
    LookGallery,
    PresetIndicator,
    PreviewCanvas,
    PreviewResult,
    RenderWorker,
    oversize_message,
    preview_proxy,
    proxy_factor,
)
from lattice.ui import export_dialog as export_module  # noqa: E402
from lattice.ui import looks as looks_module  # noqa: E402
from lattice.ui import worker as worker_module  # noqa: E402

UI_PACKAGE = Path(lattice.ui.__file__).resolve().parent
REPO_ROOT = UI_PACKAGE.parents[1]
RED = (255, 0, 0)
BLUE = (0, 0, 255)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def _ramp(height: int, width: int) -> Image:
    """Return a deterministic float32 grey ramp of the given shape."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:, :, :] = ramp[None, :, None]
    return image


def _solid(height: int, width: int, rgb: tuple[int, int, int]) -> RGB8:
    """Return a uint8 RGB image filled with one colour."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = rgb
    return image


def _pump(cond, timeout_ms: int = 8000) -> None:
    """Process Qt events until cond() is true or the deadline passes."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while not cond() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert cond(), "the asynchronous widget never reached the expected state"


@pytest.fixture
def looks() -> list[Look]:
    """Two named pipeline variants for the gallery tests."""
    return [
        Look("bw", "Black & white", PipelineSpec(algorithm_id="floyd_steinberg", pixel_size=6)),
        Look("pixel", "Pixel", PipelineSpec(algorithm_id="bayer_4", pixel_size=8)),
    ]


@pytest.fixture
def gallery(qapp: QApplication) -> LookGallery:
    """Return a gallery whose helper thread is stopped even when a test fails."""
    view = LookGallery()
    view.show()
    QApplication.processEvents()
    yield view
    view.shutdown()
    view.close()
    QApplication.processEvents()


# --- accept: lattice/ui imports no application module (E8) --------------------


def test_ui_package_imports_no_application_module() -> None:
    """No module of lattice/ui may reference an application in an import."""
    files = [path for path in UI_PACKAGE.rglob("*.py") if "__pycache__" not in str(path)]
    for path in sorted(files):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert root not in ("lattice.modes.dither", "lattice.modes.glyph",
                                    "lattice.modes.glitch"), (
                    f"{path.name} imports {name!r} from an application package"
                )


def test_base_core_import_never_pulls_ui_or_pyside6() -> None:
    """A fresh interpreter importing lattice must not import the ui package."""
    code = (
        "import lattice, sys\n"
        "assert 'lattice.ui' not in sys.modules, 'lattice.ui was imported'\n"
        "assert 'PySide6' not in sys.modules, 'PySide6 was imported'\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# --- accept: canvas + worker + split -----------------------------------------------


def test_preview_emits_the_coarse_proxy_before_the_fine_proxy(qapp: QApplication) -> None:
    """The 256 proxy is emitted first, then the 1024 proxy."""
    worker = RenderWorker()
    source = _ramp(600, 1100)
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    worker.set_source(source)
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert [result.max_side for result in results] == list(PREVIEW_STAGES)
    assert [max(result.image.shape[:2]) for result in results] == [220, 550]
    assert all(result.original.shape == result.image.shape for result in results)
    assert np.array_equal(results[0].image, render(source, PipelineSpec(), max_side=256))
    assert np.array_equal(results[-1].image, render(source, PipelineSpec(), max_side=1024))


def test_source_below_the_first_stage_emits_one_preview(qapp: QApplication) -> None:
    """A source smaller than the coarse proxy renders once, not twice."""
    worker = RenderWorker()
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    worker.set_source(_ramp(48, 64))
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert [result.max_side for result in results] == [PREVIEW_STAGES[0]]
    assert results[0].image.shape == (48, 64, 3)


def test_previews_render_proxies_and_only_export_renders_full(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preview stages render proxies; the export path renders the full source."""
    shapes: list[tuple[int, ...]] = []
    real = worker_module.render

    def spy(src, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
        shapes.append(src.shape)
        return real(src, spec, max_side=max_side)

    monkeypatch.setattr(worker_module, "render", spy)
    worker = RenderWorker()
    source = _ramp(600, 1100)
    worker.set_source(source)
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert len(shapes) == len(PREVIEW_STAGES)
    assert all(max(shape[:2]) <= PREVIEW_MAX_SIDE for shape in shapes)
    shapes.clear()
    exported: list[object] = []
    worker.export_ready.connect(exported.append)
    worker.request_export(PipelineSpec())
    assert shapes == [source.shape]
    assert exported[0].image.shape == source.shape


def test_oversized_source_is_refused(qapp: QApplication) -> None:
    """A source above MAX_SOURCE_SIDE is refused and never reaches the pipeline."""
    worker = RenderWorker()
    messages: list[str] = []
    results: list[PreviewResult] = []
    worker.failed.connect(messages.append)
    worker.preview_ready.connect(results.append)
    worker.set_source(_ramp(9000, 40))
    assert len(messages) == 1
    assert "9000" in messages[0] and str(MAX_SOURCE_SIDE) in messages[0]
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert results == []
    assert oversize_message((MAX_SOURCE_SIDE, 10)) is None
    assert oversize_message((MAX_SOURCE_SIDE + 1, 10)) is not None


@pytest.mark.parametrize("shape", [(5, 7), (601, 1101), (1000, 999)])
def test_preview_proxy_matches_the_core_downscale(shape: tuple[int, int]) -> None:
    """The strip-wise proxy is bit-identical to color.downscale on the whole image."""
    image = np.random.default_rng(0).random((*shape, 3), dtype=np.float32)
    for max_side in PREVIEW_STAGES:
        factor = proxy_factor(image, max_side)
        expected = color.to_rgb8(color.downscale(image, factor))
        assert np.array_equal(preview_proxy(image, max_side), expected)


def test_canvas_buffer_reuse_and_modes(qapp: QApplication) -> None:
    """Split and before modes compose into the reused display buffer."""
    canvas = PreviewCanvas()
    canvas.set_original(_solid(20, 40, BLUE))
    canvas.set_image(_solid(20, 40, RED))
    buffer = canvas.qimage()
    assert isinstance(buffer, QImage)
    canvas.set_image(_solid(20, 40, RED))
    assert canvas.qimage() is buffer
    canvas.set_mode("split")
    assert buffer.pixelColor(0, 0).getRgb()[:3] == BLUE
    assert buffer.pixelColor(39, 0).getRgb()[:3] == RED
    canvas.set_mode("before")
    assert buffer.pixelColor(39, 0).getRgb()[:3] == BLUE
    canvas.set_mode("after")
    assert buffer.pixelColor(0, 0).getRgb()[:3] == RED
    assert canvas.mode() == "after"


def test_canvas_zoom_is_clamped_and_fit(qapp: QApplication) -> None:
    """Zoom is clamped to the supported range and zoom_fit stays within it."""
    canvas = PreviewCanvas()
    canvas.set_zoom(1.0)
    assert canvas.zoom() == pytest.approx(1.0)
    canvas.set_zoom(1e6)
    assert canvas.zoom() == pytest.approx(32.0)
    canvas.set_zoom(-1.0)
    assert canvas.zoom() == pytest.approx(0.01)
    canvas.set_image(_solid(100, 200, RED))
    canvas.set_zoom(1.0)
    canvas.zoom_fit()
    assert 0.01 <= canvas.zoom() <= 32.0
    with pytest.raises(ValueError):
        canvas.set_mode("diagonal")


# --- accept: Looks grid (thumbnails on the current image) --------------------------


def test_look_gallery_cells_and_names(gallery: LookGallery, looks: list[Look]) -> None:
    """set_looks creates one cell per look, in order."""
    gallery.set_looks(looks)
    assert [cell.look_id for cell in gallery.cells()] == ["bw", "pixel"]
    assert [cell.name_label.text() for cell in gallery.cells()] == ["Black & white", "Pixel"]


def test_look_gallery_renders_thumbnails_on_the_current_image(
    gallery: LookGallery, looks: list[Look], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thumbnails render on the image that is loaded, never a fixed test image."""
    seen: list[tuple[int, ...]] = []
    real = looks_module.render

    def spy(src, spec: PipelineSpec, **kwargs) -> RGB8:
        seen.append(src.shape)
        return real(src, spec, **kwargs)

    monkeypatch.setattr(looks_module, "render", spy)
    gallery.set_looks(looks)
    first = _ramp(400, 900)
    gallery.set_source(first)
    _pump(lambda: all(cell.has_thumbnail() for cell in gallery.cells()))
    assert len(seen) == 2
    assert all(max(shape[:2]) <= 512 for shape in seen)
    expected = preview_proxy(first, 512).shape
    assert all(shape == expected for shape in seen)
    second = _ramp(300, 600)
    gallery.set_source(second)
    _pump(lambda: all(cell.has_thumbnail() for cell in gallery.cells()))
    assert len(seen) == 4
    expected = preview_proxy(second, 512).shape
    assert all(shape == expected for shape in seen[2:])


def test_look_gallery_without_source_keeps_placeholders(
    gallery: LookGallery, looks: list[Look], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an image no thumbnail is rendered and every cell shows a placeholder."""
    calls: list[object] = []
    monkeypatch.setattr(looks_module, "render", lambda *a, **k: calls.append(a))
    gallery.set_looks(looks)
    gallery.set_source(None)
    QApplication.processEvents()
    assert calls == []
    assert not any(cell.has_thumbnail() for cell in gallery.cells())


def test_look_cell_click_emits_its_id(gallery: LookGallery, looks: list[Look]) -> None:
    """Clicking a cell reports the look id through the gallery signal."""
    gallery.set_looks(looks)
    chosen: list[str] = []
    gallery.look_chosen.connect(chosen.append)
    QTest.mouseClick(gallery.cells()[1], Qt.MouseButton.LeftButton)
    assert chosen == ["pixel"]


# --- accept: bridge status dot ------------------------------------------------------


def _stub_discover(result):
    """Return a Discover callable answering with result for any host."""

    def discover(host, port=None):
        return result

    return discover


def test_bridge_dot_starts_unknown_and_validates_states(qapp: QApplication) -> None:
    """The dot starts unknown; a state must be one of the three known states."""
    dot = BridgeStatusDot()
    assert dot.state() == "unknown"
    dot.set_state("connected")
    assert dot.state() == "connected"
    dot.set_state("disconnected")
    assert dot.state() == "disconnected"
    with pytest.raises(ValueError):
        dot.set_state("half-open")
    dot.stop()


def test_bridge_dot_reports_connected_and_disconnected(qapp: QApplication) -> None:
    """A live probe turns the dot green; a refused host turns it red."""
    dot = BridgeStatusDot(discover=_stub_discover(object()))
    dot.check()
    _pump(lambda: dot.state() != "unknown")
    assert dot.state() == "connected"
    dot.stop()
    dot = BridgeStatusDot(discover=_stub_discover(None))
    dot.check()
    _pump(lambda: dot.state() != "unknown")
    assert dot.state() == "disconnected"
    dot.stop()


def test_bridge_dot_probe_error_is_a_normal_disconnect(qapp: QApplication) -> None:
    """A discovery exception must never crash; the dot just reports disconnected."""

    def broken(host, port=None):
        raise OSError("connection refused")

    dot = BridgeStatusDot(discover=broken)
    dot.check()
    _pump(lambda: dot.state() != "unknown")
    assert dot.state() == "disconnected"
    dot.stop()
    with pytest.raises(ValueError):
        BridgeStatusDot(host="hologram")


# --- accept: empty state -------------------------------------------------------------


def test_empty_state_message_and_visibility(qapp: QApplication) -> None:
    """The empty state carries guidance text and shows it as a widget."""
    state = EmptyState()
    assert state.message() == "Open an image to start."
    state.set_message("Drop an image here.")
    assert state.message() == "Drop an image here."
    state.show()
    QApplication.processEvents()
    assert state.isVisible()
    state.close()


# --- accept: preset indicator honest, live, image-gated ------------------------------


def test_preset_indicator_is_hidden_without_an_image(qapp: QApplication) -> None:
    """Without an image the indicator is not shown, whatever the preset state."""
    indicator = PresetIndicator()
    assert indicator.isHidden()
    indicator.show()
    QApplication.processEvents()
    assert indicator.isVisible()
    indicator.set_image_loaded(False)
    QApplication.processEvents()
    assert not indicator.isVisible()
    indicator.set_image_loaded(True)
    QApplication.processEvents()
    assert indicator.isVisible()


def test_preset_indicator_shows_the_applied_preset_and_tracks_changes(
    qapp: QApplication,
) -> None:
    """The indicator names the applied preset and marks every pipeline drift."""
    indicator = PresetIndicator()
    assert indicator.indicator_text() == "Custom"
    indicator.set_preset("01_gameboy.json")
    assert indicator.preset_name() == "01_gameboy.json"
    assert indicator.indicator_text() == "01_gameboy.json"
    assert not indicator.is_modified()
    indicator.pipeline_changed()
    assert indicator.is_modified()
    assert indicator.indicator_text() == "01_gameboy.json (modified)"
    indicator.pipeline_changed()
    assert indicator.indicator_text() == "01_gameboy.json (modified)"
    indicator.set_preset("02_neon.json")
    assert not indicator.is_modified()
    assert indicator.indicator_text() == "02_neon.json"
    indicator.set_preset(None)
    assert indicator.indicator_text() == "Custom"
    assert indicator.preset_name() is None


# --- accept: one full-resolution export dialog ---------------------------------------


def _export_settings(tmp_path: Path) -> QSettings:
    """Return an isolated QSettings so the dialog never touches user settings."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_export_dialog_renders_at_full_resolution(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dialog renders the full source with no max_side, never the preview proxy."""
    source = _ramp(700, 1400)
    spec = PipelineSpec()
    full = render(source, spec)
    proxy = render(source, spec, max_side=PREVIEW_MAX_SIDE)
    assert full.shape != proxy.shape
    calls: list[tuple[tuple[int, ...], PipelineSpec, object]] = []

    def spy(src, s: PipelineSpec, *, max_side: int | None = None):
        calls.append((src.shape, s, max_side))
        return render(src, s, max_side=max_side)

    monkeypatch.setattr(export_module, "render", spy)
    target = tmp_path / "out.png"
    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
    dialog.path_edit.setText(str(target))
    written = dialog.export_now()
    assert written == [target]
    shape, _, max_side = calls[-1]
    assert max_side is None
    assert shape == source.shape
    from PIL import Image as PILImage

    with PILImage.open(target) as image:
        assert image.size == (full.shape[1], full.shape[0])
    assert (proxy.shape[1], proxy.shape[0]) != (full.shape[1], full.shape[0])


@pytest.mark.parametrize("format_key", ["png", "svg", "gif"])
def test_export_file_matches_the_pipeline_output_size(
    qapp: QApplication, tmp_path: Path, format_key: str
) -> None:
    """Every format writes a file of exactly the full-resolution pipeline size."""
    source = _ramp(90, 130)
    spec = PipelineSpec(pixel_size=3)
    expected = render(source, spec)
    target = tmp_path / f"out.{format_key}"
    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
    dialog.format_box.setCurrentIndex(dialog.format_box.findData(format_key))
    if format_key == "svg":
        dialog.cell.setValue(2)
    dialog.path_edit.setText(str(target))
    (written,) = dialog.export_now()
    assert written == target
    if format_key == "svg":
        text = target.read_text(encoding="utf-8")
        assert f'width="{expected.shape[1] * 2}"' in text
        assert f'height="{expected.shape[0] * 2}"' in text
    else:
        from PIL import Image as PILImage

        with PILImage.open(target) as image:
            assert image.size == (expected.shape[1], expected.shape[0])


def test_export_dialog_requires_a_path_and_reports_render_failures(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Export without a path raises; a failing render is reported, never raised."""
    source = _ramp(48, 64)
    dialog = ExportDialog(source, PipelineSpec(), settings=_export_settings(tmp_path))
    dialog.path_edit.clear()
    with pytest.raises(ExportError):
        dialog.export_now()

    def broken(spec):
        raise ValueError("render exploded")

    dialog = ExportDialog(
        source, PipelineSpec(), render_full=broken, settings=_export_settings(tmp_path)
    )
    target = tmp_path / "out.png"
    dialog.path_edit.setText(str(target))
    dialog._on_export()
    assert not target.exists()
    assert "render exploded" in dialog.report.text()


# --- accept: each widget consumed by a smoke test -------------------------------------


def test_shared_widgets_smoke(qapp: QApplication, tmp_path: Path) -> None:
    """Every shared widget instantiates, shows and shuts down cleanly offscreen."""
    source = _ramp(120, 160)
    spec = PipelineSpec(pixel_size=4)
    canvas = PreviewCanvas()
    canvas.set_original(color.to_rgb8(source))
    canvas.set_image(render(source, spec, max_side=256))
    canvas.set_mode("split")
    worker = RenderWorker()
    worker.set_source(source)
    gallery = LookGallery()
    gallery.set_looks([Look("bw", "B&W", spec)])
    gallery.set_source(source)
    dialog = ExportDialog(source, spec, settings=_export_settings(tmp_path))
    dot = BridgeStatusDot()
    empty = EmptyState()
    indicator = PresetIndicator()
    indicator.set_preset("smoke.json")
    indicator.set_image_loaded(True)
    for widget in (canvas, gallery, dialog, dot, empty, indicator):
        widget.show()
    QApplication.processEvents()
    _pump(lambda: gallery.cells()[0].has_thumbnail())
    gallery.shutdown()
    dot.stop()
    for widget in (canvas, gallery, dialog, dot, empty, indicator):
        widget.close()
    QApplication.processEvents()
