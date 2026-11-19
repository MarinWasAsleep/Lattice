"""Shared render worker: progressive previews, full-resolution renders and bridge calls.

Previews are rendered from cached proxies, coarse first (``PREVIEW_STAGES``), so
a large source never reaches the pipeline at full resolution. The full render
happens only on export or send. Sources above ``MAX_SOURCE_SIDE`` are refused
instead of exhausting memory. With ``bridge=True`` the worker also talks to
PhotoCraft (send/get/version) and probes the connection on a timer; the default
worker renders only, so an application that does not use the bridge is
unaffected. The worker never touches a widget and never imports an application.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from lattice import color
from lattice.bridge import DEFAULT_LAYER_NAME
from lattice.bridge.photocraft import (
    BridgeError,
    PhotoCraftClient,
    installed_photocraft_version,
    version_status,
)
from lattice.palettes.extract import extract_palette
from lattice.palettes.io import hex_list
from lattice.pipeline import PipelineSpec, render
from lattice.types import RGB8, Image
from lattice.ui.bridge import ConnectionProbe

LOGGER = logging.getLogger(__name__)

DEBOUNCE_MS = 120
PREVIEW_STAGES: tuple[int, ...] = (256, 1024)
PREVIEW_MAX_SIDE = PREVIEW_STAGES[-1]
MAX_SOURCE_SIDE = 8000
PROXY_STRIP_ROWS = 256
CONNECTION_INTERVAL_MS = 3000
LAYER_NAME = DEFAULT_LAYER_NAME
UNTESTED = "untested"
UNKNOWN = "unknown"
NO_CLIENT_MESSAGE = "PhotoCraft is not reachable. Start it from the {shortcut} shortcut."
SHORTCUT_NAME = "PhotoCraft"


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
    """Return the refusal message for a source of this (height, width), or None.

    Wording is app-agnostic by design (L-UI2): the shared worker names no app.
    """
    if len(shape) < 2:
        return None
    height, width = int(shape[0]), int(shape[1])
    if max(height, width) <= MAX_SOURCE_SIDE:
        return None
    return (
        f"Image is {width}×{height} px, above the {MAX_SOURCE_SIDE} px limit; "
        "downscale it before opening it."
    )


class PaletteExtraction(QObject):
    """Runs one palette extraction on a helper thread and reports it by signal."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, image: Image, k: int, method: str) -> None:
        super().__init__()
        self._args = (image, k, method)
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self.finished.connect(self._thread.quit)
        self.failed.connect(self._thread.quit)
        self._thread.finished.connect(self.deleteLater)
        _ACTIVE_EXTRACTIONS.add(self)
        self._thread.finished.connect(lambda: _ACTIVE_EXTRACTIONS.discard(self))

    def start(self) -> None:
        """Start the helper thread; this object stays alive until it finishes."""
        self._thread.start()

    @Slot()
    def run(self) -> None:
        """Emit the extracted colours, or the error message."""
        try:
            self.finished.emit(hex_list(extract_palette(*self._args)))
        except ValueError as exc:
            self.failed.emit(str(exc))


_ACTIVE_EXTRACTIONS: set[PaletteExtraction] = set()


class RenderWorker(QObject):
    """Renders previews and full-resolution images; with bridge=True talks to PhotoCraft."""

    preview_ready = Signal(object)
    export_ready = Signal(object)
    image_ready = Signal(object)
    send_finished = Signal(int)
    failed = Signal(str)
    progress = Signal(str)
    connection_state = Signal(str)
    version_status_ready = Signal(str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        bridge: bool = False,
        layer_name: str = LAYER_NAME,
        shortcut_name: str = SHORTCUT_NAME,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._layer_name = layer_name
        self._no_client_message = NO_CLIENT_MESSAGE.format(shortcut=shortcut_name)
        self.probe: ConnectionProbe | None = ConnectionProbe(parent=self) if bridge else None
        if self.probe is not None:
            self.probe.state_changed.connect(self.connection_state)
        self._source: Image | None = None
        self._proxies: dict[int, tuple[Image, RGB8]] = {}
        self._spec: PipelineSpec | None = None
        self._job = 0
        self._pending_job = 0
        self._debounce: QTimer | None = None
        self._connection: QTimer | None = None

    @Slot()
    def start(self) -> None:
        """Create the timers inside the worker thread; with bridge=True run startup checks."""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._render_preview)
        if self._bridge:
            self._connection = QTimer(self)
            self._connection.setInterval(CONNECTION_INTERVAL_MS)
            self._connection.timeout.connect(self.check_connection)
            self._connection.start()
            self.check_connection()
            self.check_version()

    def stop_probing(self) -> None:
        """Stop the connection probe; called from the GUI thread before shutdown."""
        if self.probe is not None:
            self.probe.stop()

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

    @Slot(object)
    def request_send(self, spec: PipelineSpec) -> None:
        """Render spec at full resolution and place it as a new PhotoCraft layer."""
        self.progress.emit("Rendering for PhotoCraft…")
        result = self._render_full(spec)
        if result is None:
            return
        client = self._client()
        if client is None:
            return
        self.progress.emit("Sending the render to PhotoCraft…")
        try:
            layer = client.place_as_layer(color.to_pil(result.image), self._layer_name)
        except BridgeError as exc:
            self.failed.emit(f"Cannot send the render to PhotoCraft: {exc}")
            return
        self.send_finished.emit(int(layer))

    @Slot()
    def request_get(self) -> None:
        """Fetch the visible PhotoCraft document and emit it as a float32 image."""
        client = self._client()
        if client is None:
            return
        self.progress.emit("Fetching the image from PhotoCraft…")
        try:
            image = client.render_document()
        except BridgeError as exc:
            self.failed.emit(f"Cannot get the image from PhotoCraft: {exc}")
            return
        self.image_ready.emit(color.to_float(image))

    @Slot()
    def check_connection(self) -> None:
        """Refresh the PhotoCraft connection state with one discover() call."""
        if self.probe is not None:
            self.probe.check()

    @Slot()
    def check_version(self) -> None:
        """Emit the §8.6 version status, with the installed version when untested."""
        try:
            status = version_status()
        except Exception:  # noqa: BLE001 - a version probe must never break the worker
            LOGGER.exception("version_status failed")
            status = UNKNOWN
        installed = None
        if status == UNTESTED:
            installed = installed_photocraft_version()
        self.version_status_ready.emit(status, installed)

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

    def _client(self) -> PhotoCraftClient | None:
        """Return a connected PhotoCraft client, or emit a failure and return None."""
        client = PhotoCraftClient.discover()
        if client is None:
            self.failed.emit(self._no_client_message)
        return client
