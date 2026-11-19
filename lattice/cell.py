"""CellRenderer contract: CellGrid, RenderStyle, the renderer protocol and its registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np
from PIL import Image as PILImage

if TYPE_CHECKING:
    from lattice.types import Palette


@dataclass(frozen=True)
class CellGrid:
    """One quantised image expressed as a grid of cells for a CellRenderer."""

    cols: int
    rows: int
    cell_w: int
    cell_h: int
    index: np.ndarray  # (rows, cols) int32, palette index per cell
    coverage: np.ndarray  # (rows, cols) float32 in [0, 1], ink coverage per cell
    luma: np.ndarray  # (rows, cols) float32, linear luminance of the SOURCE cell
    samples: np.ndarray  # (rows, cols, k) float32 in [0, 1], sub-cell luminance
    subindex: np.ndarray | None = None  # (rows, cols, sx*sy) int32 per sub-point


@dataclass(frozen=True)
class RenderStyle:
    """Renderer-specific options, JSON-serialisable."""

    options: Mapping[str, object]

    def __post_init__(self) -> None:
        """Reject options that do not round-trip through JSON, then store a copy."""
        try:
            encoded = json.dumps(dict(self.options))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"render style options are not JSON-serialisable: {exc}") from exc
        decoded = json.loads(encoded)
        if decoded != dict(self.options):
            raise ValueError("render style options do not round-trip through JSON without loss")
        object.__setattr__(self, "options", decoded)


@runtime_checkable
class CellRenderer(Protocol):
    """How a quantised CellGrid is drawn; the pipeline decides which palette entry.

    Optional capabilities the pipeline probes with getattr (H11): sample_points()
    returning a (k, 2) stencil of positions in [0, 1] x [0, 1], render_frame()
    for exact float frames, and layout() for structured export.
    """

    name: str

    def cell_aspect(self) -> float:
        """Return width / height of one cell."""
        ...

    def subgrid(self) -> tuple[int, int]:
        """Return the (sx, sy) sub-point grid; (1, 1) means no sub-points."""
        ...

    def consumes(self) -> frozenset[str]:
        """Return the subset of {"index", "luma", "samples", "coverage",
        "subindex"} that this renderer reads."""
        ...

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Draw grid with palette and style into a Pillow image."""
        ...


@runtime_checkable
class FloatFrameRenderer(Protocol):
    """Optional capability: hand the pipeline a float32 frame instead of a Pillow image."""

    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the same frame as render, as float32 (rows*cell_h, cols*cell_w, 3) in [0, 1]."""
        ...


_RENDERERS: dict[str, CellRenderer] = {}


def register_renderer(renderer: CellRenderer) -> CellRenderer:
    """Register renderer under its name, raising ValueError on a duplicate name."""
    if renderer.name in _RENDERERS:
        raise ValueError(f"duplicate renderer name: {renderer.name!r}")
    _RENDERERS[renderer.name] = renderer
    return renderer


def get_renderer(name: str) -> CellRenderer:
    """Return the renderer registered under name, or raise KeyError naming it."""
    try:
        return _RENDERERS[name]
    except KeyError:
        raise KeyError(f"unknown renderer: {name!r}") from None


def list_renderers() -> list[str]:
    """Return every registered renderer name, sorted."""
    return sorted(_RENDERERS)
