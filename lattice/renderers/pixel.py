"""The PixelRenderer: the 1.0 apply_palette + upscale_nearest pair as a CellRenderer."""

from __future__ import annotations

import numpy as np
from PIL import Image as PILImage

from lattice import color
from lattice.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
from lattice.types import Palette

_PIXEL = "pixel"


class PixelRenderer:
    """Draw each cell as a solid square of its palette colour (name "pixel")."""

    name = _PIXEL

    def cell_aspect(self) -> float:
        """Return 1.0: one cell is one pixel wide and one pixel tall."""
        return 1.0

    def subgrid(self) -> tuple[int, int]:
        """Return (1, 1): pixels carry no sub-points."""
        return (1, 1)

    def consumes(self) -> frozenset[str]:
        """Return {"index"}: only the palette index per cell is drawn."""
        return frozenset({"index"})

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Reproduce the 1.0 apply_palette + upscale_nearest pair exactly."""
        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))

    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the unrounded frame: palette colours repeated by cell_w and cell_h."""
        work = color.apply_palette(grid.index, palette)
        if grid.cell_h > 1:
            work = np.repeat(work, grid.cell_h, axis=0)
        if grid.cell_w > 1:
            work = np.repeat(work, grid.cell_w, axis=1)
        return np.ascontiguousarray(work, dtype=np.float32)


def register_pixel_renderer() -> CellRenderer:
    """Register the PixelRenderer under "pixel" and return it."""
    return register_renderer(PixelRenderer())
