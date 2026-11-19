"""Bridge work shared by the Lattice shells, run on a helper thread (§7, E9).

The worker pulls the host's active document and pushes a render back as a layer. Glitch and
Glyph carried near-identical copies; the only real difference is the render call — Glitch
forward to ``render_rgb8`` with the session render context (its masks and per-slot streams),
Glyph renders without one. That difference is a constructor argument here, so the host
discovery, the error vocabulary, the ``absent`` answer and the disconnect discipline live in
one place and a fix reaches both shells.

A shell subclasses this and passes its own render function:

    class BridgeWorker(_BridgeWorker):
        def __init__(self) -> None:
            super().__init__(
                document_error=DocumentError,
                render=lambda image, spec, context: render_rgb8(image, spec, context=context),
                default_name="Lattice Glitch",
            )
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from lattice_core import color
from lattice_core.bridge import BridgeError
from lattice_core.pipeline import PipelineSpec
from lattice_core.types import RGB8, Image

LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "photocraft"
NOT_RUNNING = "{host} is not running: {app} works standalone"
RenderFn = Callable[[Image, PipelineSpec, object | None], RGB8]


class BridgeWorker(QObject):
    """Pull from and push to one host off the GUI thread."""

    pulled = Signal(object, str)
    pushed = Signal(int)
    failed = Signal(str)
    absent = Signal(str)
    progress = Signal(str)

    def __init__(self, *, render: RenderFn, app_name: str, document_error: type[Exception],
                 default_name: str, discover: Callable[[str], Any],
                 host_error: type[Exception] = BridgeError) -> None:
        """Bind the shell's render function, app name, host probe and error classes.

        `discover` stays resolved in the app module on purpose: the tests patch it there,
        and a shared module cannot see those patches.
        """
        super().__init__()
        self._render = render
        self._app = app_name
        self._document_error = document_error
        self._default_name = default_name
        self._host_error = host_error
        self._discover = discover

    @Slot(str)
    def pull(self, host: str) -> None:
        """Read the active document of host and emit it as a float32 image."""
        self.progress.emit(f"Reading the {host} document…")
        client = self._discover(host)
        if client is None:
            self.absent.emit(NOT_RUNNING.format(host=host, app=self._app))
            return
        try:
            image = color.to_float(client.render_document())
        except (self._host_error, OSError, ValueError) as exc:
            LOGGER.debug("bridge pull failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pulled.emit(image, host)

    @Slot(str, object, object, str, object)
    def push(self, host: str, image: Image, spec: PipelineSpec, name: str,
             context: object | None = None) -> None:
        """Render image with spec and the session context, then place it in host."""
        self.progress.emit(f"Placing the render in {host}…")
        client = self._discover(host)
        if client is None:
            self.absent.emit(NOT_RUNNING.format(host=host, app=self._app))
            return
        try:
            rgb8 = self._render(image, spec, context)
            object_id = client.place_as_layer(color.to_pil(rgb8), name or self._default_name)
        except (self._host_error, OSError, ValueError, self._document_error) as exc:
            LOGGER.debug("bridge push failed", exc_info=True)
            self.failed.emit(f"{host}: {exc}")
            return
        finally:
            client.disconnect()
        self.pushed.emit(int(object_id))



__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
