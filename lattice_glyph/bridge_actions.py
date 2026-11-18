"""Bridge work of the Glyph shell, run on a helper thread (§7).

The window never talks to a host on the GUI thread: a slow connection would freeze the
preview. ``BridgeWorker`` does exactly three things — pull the active document, place a
render as a layer, or report why neither was possible — and a missing host is the normal
``failed`` case, reported in the status bar, never an exception.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from lattice_core import color
from lattice_core.bridge import ArtCraftClient, BridgeError
from lattice_core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

HOSTS = ("photocraft", "designcraft")
DEFAULT_HOST = "photocraft"
DEFAULT_NAME = "Lattice Glyph"
NOT_RUNNING = "{host} is not running: Lattice Glyph works standalone"


class BridgeWorker(QObject):
    """Pulls documents from a host and pushes renders to it, off the GUI thread."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    progress = Signal(str)

    @Slot(str)
    def pull(self, host: str) -> None:
        """Read the active document of host and emit it as a float32 image."""
        self.progress.emit(f"Reading the {host} document…")
        client = _discover(host)
        if client is None:
            self.failed.emit(NOT_RUNNING.format(host=host))
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

    @Slot(str, object, str)
    def push(self, host: str, rgb8: RGB8, name: str) -> None:
        """Place one rendered image in host as a layer and emit the object id."""
        self.progress.emit(f"Placing the render in {host}…")
        client = _discover(host)
        if client is None:
            self.failed.emit(NOT_RUNNING.format(host=host))
            return
        try:
            object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
        except (BridgeError, OSError, ValueError) as exc:
            LOGGER.debug("bridge push failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pushed.emit(int(object_id))


def _discover(host: str) -> ArtCraftClient | None:
    """Return a live client for host, or None for every way a host can be absent."""
    if host not in HOSTS:
        return None
    try:
        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
    except (BridgeError, OSError, ValueError):
        LOGGER.debug("host discovery failed", exc_info=True)
        return None


def pull_image(host: str = DEFAULT_HOST) -> Image | None:
    """Synchronously read a host document, returning None when the host is absent."""
    client = _discover(host)
    if client is None:
        return None
    try:
        return color.to_float(client.render_document())
    except (BridgeError, OSError, ValueError):
        return None
    finally:
        client.disconnect()


__all__ = ["BridgeWorker", "DEFAULT_HOST", "HOSTS", "NOT_RUNNING", "pull_image"]
