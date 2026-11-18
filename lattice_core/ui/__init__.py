"""Shared Qt widgets of the Lattice suite (imported only under the ``[ui]`` extra).

This package is owned by card L-UI and hosts the widgets every application
reuses instead of reimplementing: the preview canvas with its render worker,
the Looks grid, the full-resolution export dialog, the bridge status dot, the
preset indicator and the empty state. It never imports an application module;
applications import it under ``lattice-core[ui]``.
"""

from __future__ import annotations

from lattice_core.ui.bridge import BridgeStatusDot, ConnectionProbe
from lattice_core.ui.canvas import MODES, Mode, PreviewCanvas
from lattice_core.ui.empty import EmptyState
from lattice_core.ui.export_dialog import ExportDialog, ExportError, run_export_dialog
from lattice_core.ui.looks import Look, LookCell, LookGallery
from lattice_core.ui.preset_indicator import PresetIndicator
from lattice_core.ui.worker import (
    MAX_SOURCE_SIDE,
    PREVIEW_MAX_SIDE,
    PREVIEW_STAGES,
    PaletteExtraction,
    PreviewResult,
    RenderResult,
    RenderWorker,
    oversize_message,
    preview_proxy,
    proxy_factor,
)

__all__ = [
    "BridgeStatusDot",
    "ConnectionProbe",
    "EmptyState",
    "ExportDialog",
    "ExportError",
    "Look",
    "LookCell",
    "LookGallery",
    "MAX_SOURCE_SIDE",
    "MODES",
    "Mode",
    "PREVIEW_MAX_SIDE",
    "PREVIEW_STAGES",
    "PaletteExtraction",
    "PresetIndicator",
    "PreviewCanvas",
    "PreviewResult",
    "RenderResult",
    "RenderWorker",
    "oversize_message",
    "preview_proxy",
    "proxy_factor",
    "run_export_dialog",
]
