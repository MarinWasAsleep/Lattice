"""Bridge controller of the Glyph shell: host work on its own thread (§7, E9).

The window never talks to a host on the GUI thread, and a host that is not running is a
normal answer reported through ``absent`` (a status-bar line), never a dialog. The
controller is opt-in: without it, the shell is a complete standalone application.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

from lattice_core.pipeline import PipelineSpec
from lattice_core.types import Image
from lattice_glyph.bridge_actions import DEFAULT_HOST, BridgeWorker

LOGGER = logging.getLogger(__name__)

STOP_MS = 5000
LAYER_NAME = "Lattice Glyph"


class BridgeController(QObject):
    """Owns the bridge thread and re-emits its results in the window's vocabulary."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    absent = Signal(str)
    progress = Signal(str)
    pull_request = Signal(str)
    push_request = Signal(str, object, object, str)

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
        worker.absent.connect(self.absent)
        worker.progress.connect(self.progress)
        thread.start()

    def pull(self) -> None:
        """Ask the worker to read the active document of the host."""
        self.pull_request.emit(self.host)

    def push(self, image: Image, spec: PipelineSpec, name: str = LAYER_NAME) -> None:
        """Ask the worker to render image with spec and place it in the host as a layer."""
        self.push_request.emit(self.host, image, spec, name)

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


__all__ = ["BridgeController", "LAYER_NAME"]
