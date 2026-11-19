"""The bitmask renderer family: braille, sextant, quadrant, half_block (§9).

One code path, four geometries. The sub-point decision belongs to the
dithering algorithm, run by the pipeline at subgrid resolution (S3): each
renderer packs ``grid.subindex`` into one block character per cell.

Codepoint ranges (E1, see NOTES in the card):

- ``braille`` 2x4: U+2800 + an 8-dot bitmask; all 256 patterns are assigned.
- ``sextant`` 2x3: U+1FB00..U+1FB3B (Unicode 13.0 BLOCK SEXTANT-*) plus U+0020
  and U+2588 FULL BLOCK. Dots are row-major: 1=top-left, 2=top-right,
  3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right. The block
  cannot express four patterns: empty -> U+0020, all six dots -> U+2588, and
  the two solid columns {1,3,5} / {2,4,6} -> the documented 3-dot
  approximations U+1FB06 and U+1FB0A (upper two-thirds blocks, E1).
- ``quadrant`` 2x2: U+2596..U+259F (Unicode 15.1 quadrant names) plus the
  exact half/full blocks U+2580, U+2584, U+2588, U+258C, U+2590 and U+0020.
- ``half_block`` 1x2: U+2580, U+2584, U+2588 and U+0020 (background).

The four geometries are four registered renderers sharing this class: the
pipeline derives the sub-point resolution from ``subgrid()`` before it ever
sees a style (pipeline.py §5 step 6), so the geometry cannot be a style
option. Options: ``threshold`` (0..1, default 0.5), ``fg``/``bg`` (hex
colours). There is no ``dither`` option (removed, H11/S3): an unknown option
in the style is ignored.
"""

from __future__ import annotations

import re
from typing import Final

import numpy as np
from PIL import Image as PILImage

from lattice import color
from lattice.cell import CellGrid, CellRenderer, RenderStyle, register_renderer
from lattice.types import Palette

_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_GEOMETRY_ORDER: Final = ("braille", "sextant", "quadrant", "half_block")

# Sub-point k is ordered y-major, x-minor: k = y * sx + x, matching the
# pipeline's subindex packing and its default k-point stencil (S3).
_BRAILLE_DOT_BITS: Final = (0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80)
_BRAILLE_BASE: Final = 0x2800
# Sextant: mask bit k = dot k+1, row-major (1=top-left, 2=top-right,
# 3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right), built from
# the Unicode BLOCK SEXTANT-* names (L8 FIX: the previous table was
# column-major and transposed 54 of 60 patterns). The block lacks empty, full
# and the two solid columns {1,3,5}/{2,4,6}: empty -> U+0020, full -> U+2588,
# the columns -> the documented 3-dot approximations U+1FB06 (SEXTANT-123)
# and U+1FB0A (SEXTANT-124), never a 2-dot glyph that drops a dot (E1).
_SEXTANT_CODEPOINTS: Final = (
    0x0020, 0x1FB00, 0x1FB01, 0x1FB02,
    0x1FB03, 0x1FB04, 0x1FB05, 0x1FB06,
    0x1FB07, 0x1FB08, 0x1FB09, 0x1FB0A,
    0x1FB0B, 0x1FB0C, 0x1FB0D, 0x1FB0E,
    0x1FB0F, 0x1FB10, 0x1FB11, 0x1FB12,
    0x1FB13, 0x1FB06, 0x1FB14, 0x1FB15,
    0x1FB16, 0x1FB17, 0x1FB18, 0x1FB19,
    0x1FB1A, 0x1FB1B, 0x1FB1C, 0x1FB1D,
    0x1FB1E, 0x1FB1F, 0x1FB20, 0x1FB21,
    0x1FB22, 0x1FB23, 0x1FB24, 0x1FB25,
    0x1FB26, 0x1FB27, 0x1FB0A, 0x1FB28,
    0x1FB29, 0x1FB2A, 0x1FB2B, 0x1FB2C,
    0x1FB2D, 0x1FB2E, 0x1FB2F, 0x1FB30,
    0x1FB31, 0x1FB32, 0x1FB33, 0x1FB34,
    0x1FB35, 0x1FB36, 0x1FB37, 0x1FB38,
    0x1FB39, 0x1FB3A, 0x1FB3B, 0x2588,
)
_QUADRANT_CODEPOINTS: Final = (
    0x0020, 0x2598, 0x259D, 0x2580, 0x2596, 0x258C, 0x259E, 0x259B,
    0x2597, 0x259A, 0x2590, 0x259C, 0x2584, 0x2599, 0x259F, 0x2588,
)
_HALF_BLOCK_CODEPOINTS: Final = (0x0020, 0x2580, 0x2584, 0x2588)

_GEOMETRIES: Final = {
    "braille": (2, 4, _BRAILLE_DOT_BITS, _BRAILLE_BASE),
    "sextant": (2, 3, _SEXTANT_CODEPOINTS, None),
    "quadrant": (2, 2, _QUADRANT_CODEPOINTS, None),
    "half_block": (1, 2, _HALF_BLOCK_CODEPOINTS, None),
}

_THRESHOLD = "threshold"
_FG = "fg"
_BG = "bg"
_DEFAULTS: Final = {"threshold": 0.5, "fg": "#000000", "bg": "#ffffff"}


class BitmaskRenderer:
    """Pack sub-point palette decisions into one block character per cell."""

    def __init__(self, geometry: str) -> None:
        """Store the geometry; raise ValueError on an unknown geometry name."""
        if geometry not in _GEOMETRIES:
            raise ValueError(f"unknown bitmask geometry: {geometry!r}")
        self._geometry = geometry
        self.name = geometry
        self._sx, self._sy = (
            int(value) for value in _GEOMETRIES[geometry][:2]
        )

    def cell_aspect(self) -> float:
        """Return sx / sy: width dots over height dots of one cell."""
        return self._sx / self._sy

    def subgrid(self) -> tuple[int, int]:
        """Return the (sx, sy) sub-point grid of this geometry (S3)."""
        return (self._sx, self._sy)

    def consumes(self) -> frozenset[str]:
        """Return {"subindex"}: the algorithm's sub-point decisions (S3)."""
        return frozenset({"subindex"})

    def codepoints(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the (rows, cols) int32 Unicode codepoint of every cell."""
        option = self._options(style)
        bits_or_table, base = _GEOMETRIES[self._geometry][2:]
        dots = self._on_dots(grid, palette, option[_THRESHOLD])
        masks = np.zeros((grid.rows, grid.cols), dtype=np.int64)
        if base is not None:
            for k, bit in enumerate(bits_or_table):
                masks |= dots[:, :, k].astype(np.int64) * bit
            return np.ascontiguousarray(base + masks, dtype=np.int32)
        for k in range(self._sx * self._sy):
            masks |= dots[:, :, k].astype(np.int64) << k
        table = np.asarray(bits_or_table, dtype=np.int32)
        return np.ascontiguousarray(np.take(table, masks), dtype=np.int32)

    def _on_dots(self, grid: CellGrid, palette: Palette, threshold: float) -> np.ndarray:
        """Return the (rows, cols, sx*sy) bool ink mask of the sub-points."""
        if grid.subindex is None:
            raise ValueError(
                f"{self.name!r} needs grid.subindex (S3, subgrid "
                f"{self._sx}x{self._sy}); the pipeline fills it "
                "at sub-point resolution"
            )
        expected = (grid.rows, grid.cols, self._sx * self._sy)
        if grid.subindex.shape != expected:
            raise ValueError(
                f"{self.name!r} expected grid.subindex of shape {expected}, "
                f"got {grid.subindex.shape}"
            )
        linear = color.srgb_to_linear(palette)
        lum = (np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
               + np.float32(0.0722) * linear[:, 2])
        lum_min, lum_max = float(lum.min()), float(lum.max())
        if lum_max == lum_min:
            # Degenerate palette: no contrast to threshold, so no ink — all
            # paper, matching the pipeline's _coverage_table convention where
            # coverage 0 means no ink (L8 FIX, H11).
            return np.zeros(
                (grid.rows, grid.cols, self._sx * self._sy), dtype=bool
            )
        rel = (lum - lum_min) / (lum_max - lum_min)
        return rel[grid.subindex] < np.float32(threshold)

    def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
        """Return the unrounded frame: fg dots on a bg cell, as render draws."""
        option = self._options(style)
        fg = _colour(option[_FG])
        bg = _colour(option[_BG])
        frame = np.broadcast_to(
            bg.astype(np.float32),
            (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3),
        ).copy()
        dots = self._on_dots(grid, palette, option[_THRESHOLD])
        x_spans = _spans(grid.cell_w, self._sx)
        y_spans = _spans(grid.cell_h, self._sy)
        blocks = frame.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w, 3)
        ink = fg.reshape(1, 1, 1, 1, 3)
        for k in range(self._sx * self._sy):
            if not dots[:, :, k].any():
                continue
            y0, y1 = y_spans[k // self._sx]
            x0, x1 = x_spans[k % self._sx]
            patch = blocks[:, y0:y1, :, x0:x1, :]
            on = dots[:, :, k].reshape(grid.rows, 1, grid.cols, 1, 1)
            patch[...] = np.where(on, ink, patch)
        return np.ascontiguousarray(frame, dtype=np.float32)

    def render(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> PILImage.Image:
        """Rasterise the fg/bg dots into a Pillow image of the grid geometry."""
        return color.to_pil(color.to_rgb8(self.render_frame(grid, palette, style)))

    def layout(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> list[tuple]:
        """Return one (character, x, y, width, height, fill) per cell (§3)."""
        option = self._options(style)
        codepoints = self.codepoints(grid, palette, style)
        placed: list[tuple] = []
        for r in range(grid.rows):
            for c in range(grid.cols):
                placed.append((
                    chr(int(codepoints[r, c])),
                    float(c * grid.cell_w), float(r * grid.cell_h),
                    float(grid.cell_w), float(grid.cell_h),
                    option[_FG].lower(),
                ))
        return placed

    def _options(self, style: RenderStyle) -> dict:
        """Return validated threshold/fg/bg; unknown options stay ignored."""
        threshold = float(style.options.get(_THRESHOLD, _DEFAULTS[_THRESHOLD]))
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"bitmask option {_THRESHOLD!r} must be in [0, 1], got {threshold!r}"
            )
        fg = str(style.options.get(_FG, _DEFAULTS[_FG]))
        bg = str(style.options.get(_BG, _DEFAULTS[_BG]))
        if _HEX_COLOUR.fullmatch(fg) is None:
            raise ValueError(f"bitmask option {_FG!r} must be #RRGGBB, got {fg!r}")
        if _HEX_COLOUR.fullmatch(bg) is None:
            raise ValueError(f"bitmask option {_BG!r} must be #RRGGBB, got {bg!r}")
        return {_THRESHOLD: threshold, _FG: fg, _BG: bg}


def _colour(hex_code: str) -> np.ndarray:
    """Parse #RRGGBB into a float32 (3,) sRGB row in [0, 1]."""
    return np.asarray(
        [int(hex_code[i : i + 2], 16) / 255.0 for i in (1, 3, 5)], dtype=np.float32
    )


def _spans(length: int, count: int) -> list[tuple[int, int]]:
    """Split length pixels into count [start, end) spans of at least 1 pixel.

    Identical to pipeline._spans, so the filled bands cover exactly the
    pixels the pipeline averaged into each sub-point (S3).
    """
    edges = [index * length // count for index in range(count + 1)]
    return [(start, min(length, max(start + 1, end)))
            for start, end in zip(edges, edges[1:], strict=False)]


def register_bitmask_renderers() -> tuple[CellRenderer, ...]:
    """Register the four bitmask renderers under their geometry names."""
    return tuple(register_renderer(BitmaskRenderer(geometry))
                 for geometry in _GEOMETRY_ORDER)


register_bitmask_renderers()
