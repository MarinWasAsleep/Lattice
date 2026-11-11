"""Render worker: debounced previews, full-resolution renders and bridge calls."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from dithercraft.bridge.photocraft import (
    BridgeError,
    PhotoCraftClient,
    installed_photocraft_version,
    version_status,
)
from dithercraft.core import color
from dithercraft.core.pipeline import PipelineSpec, render
from dithercraft.core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

DEBOUNCE_MS = 120
PREVIEW_MAX_SIDE = 1024
CONNECTION_INTERVAL_MS = 3000
PROBE_JOIN_MS = 250
LAYER_NAME = "DitherCraft"
CONNECTED = "connected"
DISCONNECTED = "disconnected"
UNTESTED = "untested"
UNKNOWN = "unknown"
NO_CLIENT_MESSAGE = (
    "PhotoCraft is not reachable. Start it from the PhotoCraft (DitherCraft) shortcut."
)


@dataclass(frozen=True)
class RenderResult:
    """One finished full-resolution render: its job, the image and its duration."""

    job: int
    image: RGB8
    seconds: float


@dataclass(frozen=True)
class PreviewResult:
    """One finished preview render, with the proxy of the source for the split view."""

    job: int
    image: RGB8
    original: RGB8
    seconds: float


def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
    """Return the uint8 proxy of image, shaped like the preview render."""
    longest = max(image.shape[:2])
    factor = max(1, -(-longest // max_side))
    return color.to_rgb8(color.downscale(image, factor))


class ConnectionProbe(QObject):
    """Runs discover() on a helper thread so a slow probe never delays a render."""

    state_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def check(self) -> None:
        """Start one discover() probe unless the previous one is still running."""
        with self._lock:
            if self._stopped or (self._thread is not None and self._thread.is_alive()):
                return
            self._thread = threading.Thread(
                target=self._run, name="photocraft-probe", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop emitting probe results and wait briefly for the running probe."""
        with self._lock:
            self._stopped = True
            thread = self._thread
        if thread is not None:
            thread.join(PROBE_JOIN_MS / 1000.0)

    def _run(self) -> None:
        """Probe PhotoCraft and emit the resulting connection state."""
        try:
            client = PhotoCraftClient.discover()
        except Exception:  # noqa: BLE001 - a probe must never raise
            LOGGER.exception("PhotoCraft discovery failed")
            client = None
        if not self._stopped:
            self.state_changed.emit(CONNECTED if client is not None else DISCONNECTED)


class RenderWorker(QObject):
    """Renders previews and full-resolution images and talks to PhotoCraft."""

    preview_ready = Signal(object)
    export_ready = Signal(object)
    image_ready = Signal(object)
    send_finished = Signal(int)
    failed = Signal(str)
    progress = Signal(str)
    connection_state = Signal(str)
    version_status_ready = Signal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.probe = ConnectionProbe(self)
        self.probe.state_changed.connect(self.connection_state)
        self._source: Image | None = None
        self._proxy: RGB8 | None = None
        self._spec: PipelineSpec | None = None
        self._job = 0
        self._debounce: QTimer | None = None
        self._connection: QTimer | None = None

    @Slot()
    def start(self) -> None:
        """Create the timers inside the worker thread and run the startup checks."""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._render_preview)
        self._connection = QTimer(self)
        self._connection.setInterval(CONNECTION_INTERVAL_MS)
        self._connection.timeout.connect(self.check_connection)
        self._connection.start()
        self.check_connection()
        self.check_version()

    def stop_probing(self) -> None:
        """Stop the connection probe; called from the GUI thread before shutdown."""
        self.probe.stop()

    @Slot(object)
    def set_source(self, image: Image | None) -> None:
        """Store the pipeline source and cache the proxy used by the split view."""
        if image is None:
            self._source = None
            self._proxy = None
            return
        self._source = np.ascontiguousarray(image, dtype=np.float32)
        self._proxy = preview_proxy(self._source)

    @Slot(object)
    def request_preview(self, spec: PipelineSpec) -> None:
        """Store spec and restart the debounce timer; only the last spec is rendered."""
        self._spec = spec
        self._job += 1
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
            layer = client.place_as_layer(color.to_pil(result.image), LAYER_NAME)
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

    def _render_preview(self) -> None:
        """Render the latest requested spec as a preview and drop stale results."""
        spec, source = self._spec, self._source
        if spec is None or source is None:
            return
        job = self._job
        started = time.perf_counter()
        try:
            rgb8 = render(source, spec, max_side=PREVIEW_MAX_SIDE)
        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
            self.failed.emit(f"Render failed: {exc}")
            return
        if job != self._job:
            LOGGER.debug("dropping stale preview job %d", job)
            return
        original = self._proxy if self._proxy is not None else rgb8
        self.preview_ready.emit(PreviewResult(job, rgb8, original, time.perf_counter() - started))

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
            self.failed.emit(NO_CLIENT_MESSAGE)
        return client
