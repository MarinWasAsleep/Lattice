"""Tests for the progressive render worker and the canvas display buffer (T29)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tracemalloc  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lattice.dither  # noqa: E402,F401  (registers every algorithm)
import lattice.effects  # noqa: E402,F401  (registers every effect)
from lattice import color  # noqa: E402
from lattice.pipeline import PipelineSpec, render  # noqa: E402
from lattice.ui import worker as worker_module  # noqa: E402
from lattice.ui.canvas import PreviewCanvas  # noqa: E402
from lattice.ui.worker import (  # noqa: E402
    MAX_SOURCE_SIDE,
    PREVIEW_MAX_SIDE,
    PREVIEW_STAGES,
    PreviewResult,
    RenderWorker,
    oversize_message,
    preview_proxy,
    proxy_factor,
)

LARGE = (4000, 6000)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def worker(qapp: QApplication) -> RenderWorker:
    """Return a worker whose debounce timer is never started, so renders are explicit."""
    return RenderWorker()


@pytest.fixture
def canvas(qapp: QApplication) -> PreviewCanvas:
    """Return a shown canvas of a fixed size."""
    view = PreviewCanvas()
    view.resize(200, 200)
    view.show()
    QApplication.processEvents()
    yield view
    view.close()


def _ramp(height: int, width: int) -> np.ndarray:
    """Return a deterministic float32 grey ramp of the given shape."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:, :, :] = ramp[None, :, None]
    return image


def _solid(height: int, width: int, rgb: tuple[int, int, int]) -> np.ndarray:
    """Return a uint8 RGB image filled with one colour."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = rgb
    return image


def _preview(worker: RenderWorker, source: np.ndarray, spec: PipelineSpec) -> list[PreviewResult]:
    """Run one preview job synchronously and return the stages it emitted."""
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    worker.set_source(source)
    worker.request_preview(spec)
    worker._render_preview()
    return results


def test_preview_emits_the_256_proxy_before_the_1024_proxy(worker: RenderWorker) -> None:
    """The coarse proxy is emitted first, then the §9 preview proxy."""
    source = _ramp(600, 1100)
    spec = PipelineSpec()
    results = _preview(worker, source, spec)
    assert [result.max_side for result in results] == list(PREVIEW_STAGES)
    assert [max(result.image.shape[:2]) for result in results] == [220, 550]
    assert all(result.original.shape == result.image.shape for result in results)
    assert results[0].job == results[1].job
    assert np.array_equal(results[0].image, render(source, spec, max_side=PREVIEW_STAGES[0]))
    assert np.array_equal(results[-1].image, render(source, spec, max_side=PREVIEW_MAX_SIDE))


def test_a_source_below_the_first_stage_emits_one_preview(worker: RenderWorker) -> None:
    """A source smaller than the coarse proxy renders once, not twice."""
    results = _preview(worker, _ramp(48, 64), PipelineSpec())
    assert [result.max_side for result in results] == [PREVIEW_STAGES[0]]
    assert results[0].image.shape == (48, 64, 3)


def test_ten_rapid_spec_changes_render_only_the_last_one(worker: RenderWorker) -> None:
    """Ten requests inside one debounce window render the last spec once."""
    source = _ramp(600, 1100)
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    worker.set_source(source)
    for size in range(2, 12):
        worker.request_preview(PipelineSpec(pixel_size=size))
    worker._render_preview()
    assert len({result.job for result in results}) == 1
    assert len(results) == len(PREVIEW_STAGES)
    last = render(source, PipelineSpec(pixel_size=11), max_side=PREVIEW_MAX_SIDE)
    first = render(source, PipelineSpec(pixel_size=2), max_side=PREVIEW_MAX_SIDE)
    assert np.array_equal(results[-1].image, last)
    assert not np.array_equal(results[-1].image, first)


def test_large_image_preview_stays_within_the_memory_budget(worker: RenderWorker) -> None:
    """A 6000x4000 source previews without allocating memory proportional to the source."""
    spec = PipelineSpec()
    render(np.full((64, 64, 3), 0.5, dtype=np.float32), spec)  # warm numba and lazy imports
    source = _ramp(*LARGE)
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    tracemalloc.start()
    try:
        worker.set_source(source)
        worker.request_preview(spec)
        worker._render_preview()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert [result.max_side for result in results] == list(PREVIEW_STAGES)
    proxy = results[-1].image
    working = proxy.shape[0] * proxy.shape[1] * 3 * np.dtype(np.float32).itemsize
    assert peak < 12 * working
    assert peak < source.nbytes / 4


def test_an_oversized_image_is_refused_with_a_message(worker: RenderWorker) -> None:
    """A 9000 px source is refused with a message and never reaches the pipeline."""
    messages: list[str] = []
    results: list[PreviewResult] = []
    worker.failed.connect(messages.append)
    worker.preview_ready.connect(results.append)
    worker.set_source(_ramp(9000, 40))
    assert len(messages) == 1
    assert "9000" in messages[0]
    assert str(MAX_SOURCE_SIDE) in messages[0]
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert results == []


def test_a_refused_image_keeps_the_previous_source(worker: RenderWorker) -> None:
    """Refusing an oversized image leaves the loaded source and its preview intact."""
    worker.set_source(_ramp(48, 64))
    messages: list[str] = []
    worker.failed.connect(messages.append)
    worker.set_source(_ramp(40, 9000))
    assert len(messages) == 1
    results: list[PreviewResult] = []
    worker.preview_ready.connect(results.append)
    worker.request_preview(PipelineSpec())
    worker._render_preview()
    assert [result.max_side for result in results] == [PREVIEW_STAGES[0]]


def test_oversize_message_boundary() -> None:
    """Exactly MAX_SOURCE_SIDE is accepted on either side; one pixel more is refused."""
    assert oversize_message((MAX_SOURCE_SIDE, 10)) is None
    assert oversize_message((10, MAX_SOURCE_SIDE)) is None
    message = oversize_message((MAX_SOURCE_SIDE + 1, 10))
    assert message is not None
    assert str(MAX_SOURCE_SIDE) in message


def test_previews_never_render_at_full_resolution(
    worker: RenderWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preview stages render proxies; only export renders the full source."""
    shapes: list[tuple[int, ...]] = []
    real = worker_module.render

    def spy(src: np.ndarray, spec: PipelineSpec, *, max_side: int | None = None) -> np.ndarray:
        shapes.append(src.shape)
        return real(src, spec, max_side=max_side)

    monkeypatch.setattr(worker_module, "render", spy)
    source = _ramp(600, 1100)
    _preview(worker, source, PipelineSpec())
    assert len(shapes) == len(PREVIEW_STAGES)
    assert all(max(shape[:2]) <= PREVIEW_MAX_SIDE for shape in shapes)
    shapes.clear()
    exported: list[object] = []
    worker.export_ready.connect(exported.append)
    worker.request_export(PipelineSpec())
    assert shapes == [source.shape]
    assert exported[0].image.shape == source.shape


@pytest.mark.parametrize("shape", [(5, 7), (37, 23), (601, 1101), (1000, 999)])
def test_preview_proxy_matches_the_core_downscale(shape: tuple[int, int]) -> None:
    """The strip-wise proxy is bit-identical to color.downscale on the whole image."""
    image = np.random.default_rng(0).random((*shape, 3), dtype=np.float32)
    for max_side in PREVIEW_STAGES:
        factor = proxy_factor(image, max_side)
        expected = color.to_rgb8(color.downscale(image, factor))
        assert np.array_equal(preview_proxy(image, max_side), expected)


def test_canvas_reuses_its_buffer_when_the_shape_is_unchanged(canvas: PreviewCanvas) -> None:
    """Setting an image of the same shape keeps the same QImage object."""
    canvas.set_image(_solid(40, 60, RED))
    first = canvas.qimage()
    assert isinstance(first, QImage)
    canvas.set_image(_solid(40, 60, BLUE))
    assert canvas.qimage() is first
    assert first.pixelColor(0, 0).getRgb()[:3] == BLUE


def test_canvas_allocates_a_new_buffer_when_the_shape_changes(canvas: PreviewCanvas) -> None:
    """A different shape replaces the buffer."""
    canvas.set_image(_solid(40, 60, RED))
    first = canvas.qimage()
    canvas.set_image(_solid(30, 60, RED))
    assert canvas.qimage() is not first
    assert canvas.qimage().size() == QSize(60, 30)


def test_canvas_refits_when_the_preview_shape_changes(canvas: PreviewCanvas) -> None:
    """A progressive stage of a different shape is fitted again, unless the user zoomed."""
    canvas.set_image(_solid(120, 220, RED))
    fitted = canvas.zoom()
    canvas.set_image(_solid(300, 550, RED))
    assert canvas.zoom() < fitted
    canvas.set_zoom(1.0)
    canvas.set_image(_solid(120, 220, RED))
    assert canvas.zoom() == pytest.approx(1.0)


def test_canvas_modes_write_into_the_reused_buffer(canvas: PreviewCanvas) -> None:
    """Before and split modes compose into the same buffer without reallocating it."""
    canvas.set_original(_solid(20, 40, BLUE))
    canvas.set_image(_solid(20, 40, RED))
    buffer = canvas.qimage()
    canvas.set_mode("split")
    assert canvas.qimage() is buffer
    assert buffer.pixelColor(0, 0).getRgb()[:3] == BLUE
    assert buffer.pixelColor(39, 0).getRgb()[:3] == RED
    canvas.set_mode("before")
    assert canvas.qimage() is buffer
    assert buffer.pixelColor(39, 0).getRgb()[:3] == BLUE
    canvas.set_mode("after")
    assert canvas.qimage() is buffer
    assert buffer.pixelColor(0, 0).getRgb()[:3] == RED
