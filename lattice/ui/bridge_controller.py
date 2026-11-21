"""Bridge controller shared by the Lattice shells: host work on its own thread (§7, E9).

The window never talks to a host on the GUI thread, and a host that is not running is a
normal answer reported through ``absent`` (a status-bar line), never a dialog. The
controller is opt-in: without it, the shell is a complete standalone application.

Glitch and Glyph carried near-identical copies of this file. The only real difference was
the push signature: Glitch forwards a render context (its masks and per-slot streams ride
along), Glyph has none. One class carries an optional context instead, so the two shells
share the thread handling, the shutdown order and the signal vocabulary — and a fix to the
worker/thread lifetime cannot reach one app and miss the other.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from lattice.pipeline import PipelineSpec
from lattice.types import Image

LOGGER = logging.getLogger(__name__)

STOP_MS = 5000


class BridgeController(QObject):
    """Owns the bridge thread and re-emits its results in the window's vocabulary."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    absent = Signal(str)
    progress = Signal(str)
    pull_request = Signal(str)
    # (host, image, spec, name, context). `context` is the render context where the shell has
    # one — masks, per-slot streams — and None elsewhere, so one signal serves both shells.
    push_request = Signal(str, object, object, str, object)

    def __init__(self, parent: QObject | None = None, host: str = "", layer_name: str = "",
                 worker: Any = None) -> None:
        """Create the helper thread and its worker, then start it.

        `worker` is the shell's BridgeWorker class: each app resolves hosts against its own
        document type, so the worker stays with the app while the threading lives here.
        """
        super().__init__(parent)
        self.host = host
        self.layer_name = layer_name
        self.thread: QThread | None = QThread(None)
        self.worker: Any = worker() if worker is not None else None
        helper, thread = self.worker, self.thread
        if helper is None:
            return
        helper.moveToThread(thread)
        thread.finished.connect(helper.deleteLater)
        self.pull_request.connect(helper.pull)
        self.push_request.connect(helper.push)
        helper.pulled.connect(self.pulled)
        helper.pushed.connect(self.pushed)
        helper.failed.connect(self.failed)
        helper.absent.connect(self.absent)
        helper.progress.connect(self.progress)
        thread.start()

    def pull(self) -> None:
        """Ask the worker to read the active document of the host."""
        self.pull_request.emit(self.host)

    def push(self, image: Image, spec: PipelineSpec, context: object | None = None,
             name: str | None = None) -> None:
        """Ask the worker to render image with spec and place it in the host as a layer."""
        self.push_request.emit(self.host, image, spec, self.layer_name if name is None else name,
                               context)

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


__all__ = ["BridgeController", "STOP_MS"]
