"""Render worker of the Glitch shell: the shared worker, rendering the glitch path.

The shared ``RenderWorker`` debounces, proxies and stages previews, but renders through
``pipeline.render``, which knows neither §18 masks nor per-module seed locks. This
subclass keeps all of that machinery and swaps only the render call for
:func:`lattice.modes.glitch.document.render_rgb8`, fed with an immutable ``RenderContext``
snapshot so the worker thread never reads a controller the GUI thread is mutating.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import Slot

from lattice.modes.glitch.document import RenderContext, render_rgb8
from lattice.pipeline import PipelineSpec
from lattice.ui.worker import (
    PREVIEW_STAGES,
    PreviewResult,
    RenderResult,
    RenderWorker,
)

LOGGER = logging.getLogger(__name__)


class GlitchWorker(RenderWorker):
    """Renders debounced, staged previews of one source through the glitch path."""

    def __init__(self, parent=None) -> None:
        """Start from the shared worker with an empty render context."""
        super().__init__(parent)
        self._context = RenderContext()

    @Slot(object)
    def set_context(self, context: RenderContext) -> None:
        """Adopt the mask ids, mask planes and stream seeds of the next renders."""
        self._context = context

    def _render_preview(self) -> None:
        """Render the latest spec through the preview stages, dropping superseded jobs."""
        spec, source = self._spec, self._source
        if spec is None or source is None:
            return
        job = self._pending_job
        if job != self._job:
            return
        previous: tuple[int, int] | None = None
        for max_side in PREVIEW_STAGES:
            if job != self._job:
                LOGGER.debug("dropping superseded preview job %d", job)
                return
            started = time.perf_counter()
            try:
                proxy, original = self._proxy_for(max_side)
                rgb8 = render_rgb8(proxy, spec, context=self._context)
            except Exception as exc:  # noqa: BLE001 - report any render failure to the user
                self.failed.emit(f"Render failed: {exc}")
                return
            if rgb8.shape == previous:
                continue
            previous = rgb8.shape
            seconds = time.perf_counter() - started
            self.preview_ready.emit(PreviewResult(job, rgb8, original, seconds, max_side))

    def _render_full(self, spec: PipelineSpec) -> RenderResult | None:
        """Render spec at full resolution through the glitch path, reporting failures."""
        source = self._source
        if source is None:
            self.failed.emit("Load an image before rendering.")
            return None
        started = time.perf_counter()
        try:
            rgb8 = render_rgb8(source, spec, context=self._context)
        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
            self.failed.emit(f"Render failed: {exc}")
            return None
        return RenderResult(self._job, rgb8, time.perf_counter() - started)


__all__ = ["GlitchWorker"]
