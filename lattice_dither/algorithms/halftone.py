"""Halftone algorithms (T04)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from lattice_dither.core.color import luminance
from lattice_dither.core.registry import register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

_CELL_SIZE = ParamSpec("cell_size", "Cell size", "int", 8, 3, 64, 1)
_ANGLE = ParamSpec("angle", "Angle", "float", 45.0, 0.0, 90.0, 1.0)
_PARAMS = (_CELL_SIZE, _ANGLE)

_SPOT_EPS = 1e-6
_SQRT_HALF = float(np.sqrt(0.5))
SpotFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _extremes(palette: Palette) -> tuple[int, int]:
    """Return the indices of the darkest and the lightest palette colour."""
    lum = luminance(palette.reshape(1, -1, 3))[0]
    return int(np.argmin(lum)), int(np.argmax(lum))


def _cell_data(
    lum: np.ndarray, cell_size: int, angle: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the in-cell coordinates and the mean luminance of every pixel's cell."""
    height, width = lum.shape
    theta = np.deg2rad(angle)
    cos_t = np.float32(np.cos(theta))
    sin_t = np.float32(np.sin(theta))
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]
    u = xs * cos_t + ys * sin_t
    v = ys * cos_t - xs * sin_t
    cu = np.floor(u / cell_size)
    cv = np.floor(v / cell_size)
    fu = u / cell_size - cu
    fv = v / cell_size - cv
    cu = cu.astype(np.int64)
    cv = cv.astype(np.int64)
    columns = int(cu.max() - cu.min()) + 1
    ids = (cv - cv.min()) * columns + (cu - cu.min())
    flat = ids.ravel()
    counts = np.bincount(flat)
    sums = np.bincount(flat, weights=lum.ravel().astype(np.float64))
    means = (sums / np.maximum(counts, 1)).astype(np.float32)
    return fu, fv, means[flat].reshape(height, width)


def _spot_dots(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised distance to the cell centre."""
    du = fu - np.float32(0.5)
    dv = fv - np.float32(0.5)
    return np.sqrt(du * du + dv * dv) / np.float32(_SQRT_HALF * (1.0 + _SPOT_EPS))


def _spot_squares(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised Chebyshev distance to the cell centre."""
    du = np.abs(fu - np.float32(0.5))
    dv = np.abs(fv - np.float32(0.5))
    return np.maximum(du, dv) / np.float32(0.5 * (1.0 + _SPOT_EPS))


def _spot_lines(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised distance to the cell's horizontal centre line."""
    return np.abs(fv - np.float32(0.5)) / np.float32(0.5 * (1.0 + _SPOT_EPS))


def _halftone(img: Image, palette: Palette, params: dict, spot: SpotFn) -> Indices:
    """Render a halftone between the darkest and the lightest palette colour."""
    dark, light = _extremes(palette)
    fu, fv, cell_lum = _cell_data(luminance(img), int(params["cell_size"]), float(params["angle"]))
    return np.where(spot(fu, fv) < (np.float32(1.0) - cell_lum), dark, light).astype(np.int32)


@register_algorithm("halftone_dots", "Halftone Dots", "halftone", _PARAMS)
def halftone_dots(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with round dots growing from the centre of every cell."""
    return _halftone(img, palette, params, _spot_dots)


@register_algorithm("halftone_squares", "Halftone Squares", "halftone", _PARAMS)
def halftone_squares(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with square spots growing from the centre of every cell."""
    return _halftone(img, palette, params, _spot_squares)


@register_algorithm("halftone_lines", "Halftone Lines", "halftone", _PARAMS)
def halftone_lines(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with lines growing from the centre line of every cell."""
    return _halftone(img, palette, params, _spot_lines)
