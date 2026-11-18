"""Bridge work of the Glitch shell, run on a helper thread (§7, E9).

The window never talks to a host on the GUI thread: a slow connection would freeze the
preview. ``BridgeWorker`` does exactly three things — pull the active document, render
and place a render as a layer, or explain why neither was possible. A host that is not
running is the normal ``absent`` answer, shown in the status bar; only a real bridge
failure is ``failed``. The push render runs here, in the worker thread, through the
CLI's own function with the session's render context, so a full-resolution send never
freezes the window (G9).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from lattice_core import color
from lattice_core.bridge import BridgeError
from lattice_core.pipeline import PipelineSpec
from lattice_core.types import Image
from lattice_glitch.document import DocumentError, RenderContext, render_rgb8
from lattice_glitch.hosts import discover

LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "photocraft"
DEFAULT_NAME = "Lattice Glitch"
NOT_RUNNING = "{host} is not running: Lattice Glitch works standalone"


class BridgeWorker(QObject):
    """Pulls documents from a host and pushes renders to it, off the GUI thread."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    absent = Signal(str)
    progress = Signal(str)

    @Slot(str)
    def pull(self, host: str) -> None:
        """Read the active document of host and emit it as a float32 image."""
        self.progress.emit(f"Reading the {host} document…")
        client = discover(host)
        if client is None:
            self.absent.emit(NOT_RUNNING.format(host=host))
            return
        try:
            image = color.to_float(client.render_document())
        except (BridgeError, OSError, ValueError) as exc:
            LOGGER.debug("bridge pull failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pulled.emit(image, host)

    @Slot(str, object, object, str, object)
    def push(self, host: str, image: Image, spec: PipelineSpec, name: str,
             context: RenderContext) -> None:
        """Render image with spec and the session context, then place it in host."""
        self.progress.emit(f"Placing the render in {host}…")
        client = discover(host)
        if client is None:
            self.absent.emit(NOT_RUNNING.format(host=host))
            return
        try:
            rgb8 = render_rgb8(image, spec, context=context)
            object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
        except (BridgeError, OSError, ValueError, DocumentError) as exc:
            LOGGER.debug("bridge push failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pushed.emit(int(object_id))


__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
