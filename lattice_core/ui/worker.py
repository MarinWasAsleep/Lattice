"""Shared render worker: progressive previews and full-resolution renders.

Previews are rendered from cached proxies, coarse first (``PREVIEW_STAGES``), so
a large source never reaches the pipeline at full resolution. The full render
happens only on export. Sources above ``MAX_SOURCE_SIDE`` are refused instead of
exhausting memory. The worker is app-agnostic: it renders pipeline specs and
emits signals; it never talks to a host.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from lattice_core import color
from lattice_core.pipeline import PipelineSpec, render
from lattice_core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

DEBOUNCE_MS = 120
PREVIEW_STAGES: tuple[int, ...] = (256, 1024)
PREVIEW_MAX_SIDE = PREVIEW_STAGES[-1]
MAX_SOURCE_SIDE = 8000
PROXY_STRIP_ROWS = 256


@dataclass(frozen=True)
class RenderResult:
    """One finished full-resolution render: its job, the image and its duration."""

    job: int
    image: RGB8
    seconds: float


@dataclass(frozen=True)
class PreviewResult:
    """One finished preview stage: its job, the render, the source proxy and its duration."""

    job: int
    image: RGB8
    original: RGB8
    seconds: float
    max_side: int = PREVIEW_MAX_SIDE


def proxy_factor(image: Image, max_side: int) -> int:
    """Return the integer area-downscale factor that brings image under max_side."""
    longest = max(image.shape[:2])
    return max(1, -(-longest // max(1, int(max_side))))


def _downscale_strips(image: Image, factor: int) -> Image:
    """Area-downscale image by factor in row strips, so peak memory stays near the output."""
    if factor <= 1:
        return np.ascontiguousarray(image, dtype=np.float32)
    rows = max(factor, (PROXY_STRIP_ROWS // factor) * factor)
    parts = [
        color.downscale(image[start : start + rows], factor)
        for start in range(0, image.shape[0], rows)
    ]
    return np.ascontiguousarray(np.concatenate(parts, axis=0))


def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
    """Return the uint8 proxy of image, shaped like the preview render at max_side."""
    return color.to_rgb8(_downscale_strips(image, proxy_factor(image, max_side)))


def oversize_message(shape: tuple[int, ...]) -> str | None:
    """Return the refusal message for a source of this (height, width), or None."""
    if len(shape) < 2:
        return None
    height, width = int(shape[0]), int(shape[1])
    if max(height, width) <= MAX_SOURCE_SIDE:
        return None
    return (
        f"Image is {width}×{height} px, above the {MAX_SOURCE_SIDE} px limit; "
        "downscale it before opening it."
    )


class RenderWorker(QObject):
    """Renders debounced, staged previews and full-resolution exports of one source."""

    preview_ready = Signal(object)
    export_ready = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source: Image | None = None
        self._proxies: dict[int, tuple[Image, RGB8]] = {}
        self._spec: PipelineSpec | None = None
        self._job = 0
        self._pending_job = 0
        self._debounce: QTimer | None = None

    @Slot()
    def start(self) -> None:
        """Create the debounce timer inside whatever thread owns this worker."""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._render_preview)

    @Slot(object)
    def set_source(self, image: Image | None) -> None:
        """Adopt image as the pipeline source, refusing sources above MAX_SOURCE_SIDE."""
        if image is not None:
            message = oversize_message(np.shape(image))
            if message is not None:
                self.failed.emit(message)
                return
        self._proxies.clear()
        self._source = None if image is None else np.ascontiguousarray(image, dtype=np.float32)

    def source(self) -> Image | None:
        """Return the adopted source image, or None when none is loaded."""
        return self._source

    @Slot(object)
    def request_preview(self, spec: PipelineSpec) -> None:
        """Store spec and restart the debounce timer; only the last spec is rendered."""
        self._spec = spec
        self._job += 1
        self._pending_job = self._job
        if self._debounce is not None:
            self._debounce.start()

    @Slot(object)
    def request_export(self, spec: PipelineSpec) -> None:
        """Render spec at full resolution and emit the result for saving."""
        result = self._render_full(spec)
        if result is not None:
            self.export_ready.emit(result)

    def _proxy_for(self, max_side: int) -> tuple[Image, RGB8]:
        """Return the cached (float32 proxy, uint8 proxy) of the source at max_side."""
        cached = self._proxies.get(max_side)
        if cached is None:
            source = self._source
            if source is None:
                raise ValueError("no source image")
            proxy = _downscale_strips(source, proxy_factor(source, max_side))
            cached = (proxy, color.to_rgb8(proxy))
            self._proxies[max_side] = cached
        return cached

    def _render_preview(self) -> None:
        """Render the latest spec through the preview stages, dropping superseded jobs."""
        spec, source = self._spec, self._source
        if spec is None or source is None:
            return
        job = self._pending_job
        if job != self._job:
            LOGGER.debug("dropping superseded preview job %d", job)
            return
        previous: tuple[int, int] | None = None
        for max_side in PREVIEW_STAGES:
            if job != self._job:
                LOGGER.debug("dropping superseded preview job %d", job)
                return
            started = time.perf_counter()
            try:
                proxy, original = self._proxy_for(max_side)
                rgb8 = render(proxy, spec)
            except Exception as exc:  # noqa: BLE001 - report any render failure to the user
                self.failed.emit(f"Render failed: {exc}")
                return
            if rgb8.shape == previous:
                continue
            previous = rgb8.shape
            seconds = time.perf_counter() - started
            self.preview_ready.emit(PreviewResult(job, rgb8, original, seconds, max_side))

    def _render_full(self, spec: PipelineSpec) -> RenderResult | None:
        """Render spec at full resolution, emitting failed and returning None on error."""
        source = self._source
        if source is None:
            self.failed.emit("Load an image before rendering.")
            return None
        started = time.perf_counter()
        try:
            rgb8 = render(source, spec)
        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
            self.failed.emit(f"Render failed: {exc}")
            return None
        return RenderResult(self._job, rgb8, time.perf_counter() - started)
