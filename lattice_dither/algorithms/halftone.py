"""Halftone algorithms (T04, extended by T20 / CONTRACT §15.1)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from lattice_dither.algorithms._strength import (
    blend_toward_nearest,
    metric_of,
    nearest_in_space,
)
from lattice_dither.core.color import luminance
from lattice_dither.core.registry import register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

_CELL_SIZE = ParamSpec("cell_size", "Cell size", "int", 8, 3, 64, 1)
_ANGLE = ParamSpec("angle", "Angle", "float", 45.0, 0.0, 180.0, 1.0)
_OVERSAMPLE = ParamSpec("oversample", "Oversample", "int", 1, 1, 4, 1)
_PER_CHANNEL = ParamSpec("per_channel", "Per channel", "bool", False)
_STRENGTH = ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05)

_SPOT_EPS = 1e-6
_SQRT_HALF = float(np.sqrt(0.5))
_ELLIPSE_A = 0.5
_ELLIPSE_B = 0.35
_ELLIPSE_NORM = float(np.sqrt((0.5 / _ELLIPSE_A) ** 2 + (0.5 / _ELLIPSE_B) ** 2))
_CHANNEL_ANGLE_STEP = 30.0
SpotFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _extremes(palette: Palette) -> tuple[int, int]:
    """Return the indices of the darkest and the lightest palette colour."""
    lum = luminance(palette.reshape(1, -1, 3))[0]
    return int(np.argmin(lum)), int(np.argmax(lum))


def _cell_data(
    level: np.ndarray, cell_size: float, angle: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the in-cell coordinates and the mean level of every pixel's cell."""
    height, width = level.shape
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
    sums = np.bincount(flat, weights=level.ravel().astype(np.float64))
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


def _spot_diamond(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised Manhattan distance to the cell centre."""
    du = np.abs(fu - np.float32(0.5))
    dv = np.abs(fv - np.float32(0.5))
    return (du + dv) / np.float32(1.0 + _SPOT_EPS)


def _spot_lines(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised distance to the cell's horizontal centre line."""
    return np.abs(fv - np.float32(0.5)) / np.float32(0.5 * (1.0 + _SPOT_EPS))


def _spot_cross(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised distance to the nearer of the two centre lines."""
    du = np.abs(fu - np.float32(0.5))
    dv = np.abs(fv - np.float32(0.5))
    return np.minimum(du, dv) / np.float32(0.5 * (1.0 + _SPOT_EPS))


def _spot_ellipse(fu: np.ndarray, fv: np.ndarray) -> np.ndarray:
    """Return the normalised distance to the cell centre under an elliptical metric."""
    du = (fu - np.float32(0.5)) / np.float32(_ELLIPSE_A)
    dv = (fv - np.float32(0.5)) / np.float32(_ELLIPSE_B)
    return np.sqrt(du * du + dv * dv) / np.float32(_ELLIPSE_NORM * (1.0 + _SPOT_EPS))


_SPOTS: dict[str, SpotFn] = {
    "round": _spot_dots,
    "square": _spot_squares,
    "diamond": _spot_diamond,
    "line": _spot_lines,
    "cross": _spot_cross,
    "ellipse": _spot_ellipse,
}
DOT_SHAPES: tuple[str, ...] = tuple(_SPOTS)


def spot_function(shape: str) -> SpotFn:
    """Return the spot function registered under shape, or raise ValueError."""
    try:
        return _SPOTS[shape]
    except KeyError:
        raise ValueError(f"unknown dot shape: {shape!r}") from None


def coverage(
    level: np.ndarray, spot: SpotFn, cell_size: float, angle: float, oversample: int
) -> np.ndarray:
    """Return the ink coverage in [0, 1] of every pixel of a 2-D level map.

    ``level`` is 1 where the paper is bare and 0 where it is fully inked, so the
    threshold of a cell is one minus its mean. ``oversample`` evaluates the spot
    function on an oversample x oversample grid inside every pixel and averages
    the result, which anti-aliases the edge of the spot.
    """
    fu, fv, cell_level = _cell_data(level, cell_size, angle)
    threshold = np.float32(1.0) - cell_level
    if oversample <= 1:
        return (spot(fu, fv) < threshold).astype(np.float32)
    total = np.zeros(level.shape, dtype=np.float32)
    step = np.float32(1.0 / (oversample * cell_size))
    for row in range(oversample):
        for column in range(oversample):
            du = np.float32((row + 0.5) * step)
            dv = np.float32((column + 0.5) * step)
            su = np.mod(fu + du, np.float32(1.0))
            sv = np.mod(fv + dv, np.float32(1.0))
            total += (spot(su, sv) < threshold).astype(np.float32)
    return total / np.float32(oversample * oversample)


def channel_coverage(
    img: Image, spot: SpotFn, cell_size: float, angle: float, oversample: int
) -> np.ndarray:
    """Return the per-channel ink coverage of a colour screen.

    R, G and B are screened separately at ``angle``, ``angle + 30`` and
    ``angle + 60`` degrees, which is the colour-halftone look.
    """
    out = np.empty(img.shape, dtype=np.float32)
    for channel in range(3):
        out[:, :, channel] = coverage(
            img[:, :, channel],
            spot,
            cell_size,
            angle + _CHANNEL_ANGLE_STEP * channel,
            oversample,
        )
    return out


def _halftone(img: Image, palette: Palette, params: dict) -> Indices:
    """Render a halftone between the darkest and the lightest palette colour."""
    spot = spot_function(str(params["dot_shape"]))
    cell_size = int(params["cell_size"])
    angle = float(params["angle"])
    oversample = int(params["oversample"])
    code = metric_of(params)
    if bool(params["per_channel"]):
        ink = channel_coverage(img, spot, cell_size, angle, oversample)
        screened = np.ascontiguousarray(np.float32(1.0) - ink, dtype=np.float32)
        indices = nearest_in_space(screened, palette, code)
    else:
        dark, light = _extremes(palette)
        ink = coverage(luminance(img), spot, cell_size, angle, oversample)
        indices = np.where(ink > np.float32(0.5), dark, light).astype(np.int32)
    return blend_toward_nearest(img, palette, indices, float(params["strength"]), code)


def _params(default_shape: str) -> tuple[ParamSpec, ...]:
    """Return the shared parameter tuple, with the algorithm's own default shape."""
    return (
        _CELL_SIZE,
        _ANGLE,
        ParamSpec("dot_shape", "Dot shape", "choice", default_shape, choices=DOT_SHAPES),
        _OVERSAMPLE,
        _PER_CHANNEL,
        _STRENGTH,
    )


@register_algorithm("halftone_dots", "Halftone Dots", "halftone", _params("round"))
def halftone_dots(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with round dots growing from the centre of every cell."""
    return _halftone(img, palette, params)


@register_algorithm("halftone_squares", "Halftone Squares", "halftone", _params("square"))
def halftone_squares(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with square spots growing from the centre of every cell."""
    return _halftone(img, palette, params)


@register_algorithm("halftone_lines", "Halftone Lines", "halftone", _params("line"))
def halftone_lines(img: Image, palette: Palette, params: dict) -> Indices:
    """Halftone with lines growing from the centre line of every cell."""
    return _halftone(img, palette, params)
