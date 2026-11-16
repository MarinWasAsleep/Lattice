"""Palette model: luminance bounds, importers and display order (CONTRACT §4, 1.1 §16).

``Palette`` subclasses ``np.ndarray`` so every existing consumer that expects a
plain float32 (K, 3) palette keeps working unchanged; the luminance bounds are
computed once at construction in linear light and the display order is carried
as a validated permutation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_core.color import srgb_to_linear
from lattice_core.palettes import io as _io

MIN_COLORS = 2
MAX_COLORS = 256


class Palette(np.ndarray):
    """Float32 (K, 3) sRGB palette with linear-light luminance bounds and an order."""

    def __new__(
        cls,
        colors: object,
        *,
        order: list[int] | None = None,
    ) -> Palette:
        array = np.asarray(colors, dtype=np.float32)
        if array.ndim != 2 or array.shape[1] != 3:
            raise ValueError(f"a palette must be a (K, 3) array, got shape {array.shape}")
        if not MIN_COLORS <= array.shape[0] <= MAX_COLORS:
            raise ValueError(
                f"a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {array.shape[0]}"
            )
        palette = array.view(cls)
        palette._lum_min, palette._lum_max = _luminance_bounds(palette)
        palette._order = _validated_order(order, palette.shape[0])
        return palette

    def __array_finalize__(self, source: object) -> None:
        """Carry the palette attributes over views, copies and slices."""
        if source is None:
            return
        self._lum_min = getattr(source, "_lum_min", 0.0)
        self._lum_max = getattr(source, "_lum_max", 0.0)
        self._order = getattr(source, "_order", None)

    @property
    def lum_min(self) -> float:
        """Minimum linear-light luminance of the palette colours."""
        return self._lum_min

    @property
    def lum_max(self) -> float:
        """Maximum linear-light luminance of the palette colours."""
        return self._lum_max

    @property
    def order(self) -> list[int] | None:
        """Display order as a permutation of ``range(K)``, or ``None`` for natural order."""
        return self._order


def _luminance_bounds(palette: np.ndarray) -> tuple[float, float]:
    """Return (min, max) of the palette's linear-light BT.709 luminance."""
    linear = srgb_to_linear(palette)
    luma = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
    return float(luma.min()), float(luma.max())


def _validated_order(order: list[int] | None, size: int) -> list[int] | None:
    """Return order as a permutation of range(size), or None, raising ValueError on a bad one."""
    if order is None or len(order) == 0:
        return None
    seen: set[int] = set()
    for index in order:
        index = int(index)
        if not 0 <= index < size:
            raise ValueError(f"palette order index {index} is outside [0, {size})")
        if index in seen:
            raise ValueError(f"palette order index {index} is repeated")
        seen.add(index)
    if len(seen) != size:
        missing = sorted(set(range(size)) - seen)[0]
        raise ValueError(f"palette order is missing index {missing}")
    return list(order)


def from_hex_list(values: list[str]) -> Palette:
    """Build a Palette from "#RRGGBB" strings, raising ValueError on a bad entry."""
    return Palette(_io.from_hex_list(values))


def from_hex_text(text: str) -> Palette:
    """Parse a pasted list of hex colours (Lospec style), ignoring any surrounding prose."""
    return Palette(_io.from_hex_text(text))


def from_gpl(path: str | Path) -> Palette:
    """Build a Palette from a GIMP .gpl palette file."""
    return Palette(_io.load_palette(Path(path)))


def from_png(source: str | Path | PILImage.Image) -> Palette:
    """Build a Palette from the distinct colours of a PNG, in order of first appearance."""
    if isinstance(source, PILImage.Image):
        image = source
    else:
        image = PILImage.open(Path(source))
    rgba = image.convert("RGBA")
    background = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
    rgb = PILImage.alpha_composite(background, rgba).convert("RGB")
    pixels = np.asarray(rgb, dtype=np.uint8).reshape(-1, 3)
    colors = _first_seen(pixels)
    if not MIN_COLORS <= colors.shape[0] <= MAX_COLORS:
        raise ValueError(
            f"a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {colors.shape[0]}"
        )
    return Palette(np.ascontiguousarray(colors.astype(np.float32) / 255.0))


def _first_seen(pixels: np.ndarray) -> np.ndarray:
    """Return the distinct rows of a uint8 (N, 3) array, in order of first appearance."""
    keys = (pixels[:, 0].astype(np.uint32) << 16) | (
        pixels[:, 1].astype(np.uint32) << 8
    ) | pixels[:, 2].astype(np.uint32)
    seen: set[int] = set()
    rows: list[np.ndarray] = []
    for index in range(pixels.shape[0]):
        key = int(keys[index])
        if key not in seen:
            seen.add(key)
            rows.append(pixels[index])
    return np.array(rows, dtype=np.uint8)


def load(path: str | Path) -> Palette:
    """Load a Palette from a .hex, .gpl or .png file, chosen by the file extension."""
    path = Path(path)
    if path.suffix.lower() == ".png":
        return from_png(path)
    return Palette(_io.load_palette(path))
