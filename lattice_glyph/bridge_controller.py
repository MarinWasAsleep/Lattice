"""Bridge controller of the Glyph shell: host work on its own thread (§7, E9).

The window never talks to a host on the GUI thread, and a host that is not running is a
normal answer reported through ``failed``, never an exception. The controller is opt-in:
without it, the shell is a complete standalone application.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

from lattice_core import color
from lattice_core.bridge import ArtCraftClient, BridgeError
from lattice_core.types import RGB8
from lattice_glyph.bridge_actions import DEFAULT_HOST, BridgeWorker

LOGGER = logging.getLogger(__name__)

STOP_MS = 5000
LAYER_NAME = "Lattice Glyph"


class BridgeController(QObject):
    """Owns the bridge thread and re-emits its results in the window's vocabulary."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    progress = Signal(str)
    pull_request = Signal(str)
    push_request = Signal(str, object, str)

    def __init__(self, parent: QObject | None = None, host: str = DEFAULT_HOST) -> None:
        """Create the helper thread and its worker, then start it."""
        super().__init__(parent)
        self.host = host
        self.thread: QThread | None = QThread(None)
        self.worker: BridgeWorker | None = BridgeWorker()
        worker, thread = self.worker, self.thread
        worker.moveToThread(thread)
        thread.finished.connect(worker.deleteLater)
        self.pull_request.connect(worker.pull)
        self.push_request.connect(worker.push)
        worker.pulled.connect(self.pulled)
        worker.pushed.connect(self.pushed)
        worker.failed.connect(self.failed)
        worker.progress.connect(self.progress)
        thread.start()

    def pull(self) -> None:
        """Ask the worker to read the active document of the host."""
        self.pull_request.emit(self.host)

    def push(self, rgb8: RGB8, name: str = LAYER_NAME) -> None:
        """Ask the worker to place rgb8 in the host as a layer called name."""
        self.push_request.emit(self.host, rgb8, name)

    def stop(self) -> None:
        """Stop the helper thread; safe to call more than once.

        The worker is dropped only after its thread has stopped: PySide frees the C++ object
        with the last Python reference, and a worker freed mid-slot is a crash.
        """
        thread = self.thread
        if thread is None:
            return
        thread.quit()
        if not thread.wait(STOP_MS):
            LOGGER.warning("the bridge thread did not stop within %d ms", STOP_MS)
            thread.wait()
        self.thread = self.worker = None


def fetch_image(host: str = DEFAULT_HOST):
    """Synchronously read a host document, returning None when the host is absent."""
    try:
        client = ArtCraftClient.discover(host)  # type: ignore[arg-type]
    except (BridgeError, OSError, ValueError):
        return None
    if client is None:
        return None
    try:
        return color.to_float(client.render_document())
    except (BridgeError, OSError, ValueError):
        return None
    finally:
        client.disconnect()


__all__ = ["BridgeController", "LAYER_NAME", "fetch_image"]
