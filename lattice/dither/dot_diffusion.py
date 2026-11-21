"""Knuth dot diffusion: block-wise class ordering with restricted error diffusion.

Pixels are quantised in the order given by an 8x8 class matrix, so the whole
image can be split into 64 independent passes. Each pixel's error is spread
over its eight neighbours that belong to a later class, which is what makes the
passes independent. The diffused weights are a fixed 3x3 kernel normalised over
the neighbours that are still unprocessed.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from lattice.color import nearest_index_px
from lattice.dither._strength import metric_of
from lattice.registry import register_algorithm
from lattice.types import Image, Indices, Palette, ParamSpec

_PARAMS = (ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05),)

CLASS_MATRIX = np.array(
    [
        [35, 48, 40, 32, 28, 15, 23, 31],
        [43, 59, 56, 52, 20, 4, 7, 11],
        [51, 62, 60, 44, 12, 1, 3, 19],
        [38, 46, 54, 36, 25, 17, 9, 27],
        [29, 14, 22, 30, 34, 49, 41, 33],
        [21, 5, 6, 10, 42, 58, 57, 53],
        [13, 0, 2, 18, 50, 63, 61, 45],
        [24, 16, 8, 26, 39, 47, 55, 37],
    ],
    dtype=np.int32,
)

_OFFSETS = np.array(
    [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)],
    dtype=np.int64,
)
_WEIGHTS = np.array([1.0, 2.0, 1.0, 2.0, 2.0, 1.0, 2.0, 1.0], dtype=np.float32)


def class_map(height: int, width: int) -> np.ndarray:
    """Return the class of every pixel of a height x width image."""
    rows = np.arange(height) % CLASS_MATRIX.shape[0]
    cols = np.arange(width) % CLASS_MATRIX.shape[1]
    return np.ascontiguousarray(CLASS_MATRIX[np.ix_(rows, cols)])


@njit(cache=True)
def _diffuse(
    img: np.ndarray,
    palette: np.ndarray,
    classes: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
    offsets: np.ndarray,
    weights: np.ndarray,
    strength: float,
    metric: int,
) -> np.ndarray:
    """Quantise in class order, pushing each error onto later-class neighbours."""
    height = img.shape[0]
    width = img.shape[1]
    class_h = classes.shape[0]
    class_w = classes.shape[1]
    count = offsets.shape[0]
    work = img.copy()
    out = np.empty((height, width), dtype=np.int32)
    for step in range(ys.shape[0]):
        y = ys[step]
        x = xs[step]
        r = work[y, x, 0]
        g = work[y, x, 1]
        b = work[y, x, 2]
        index = nearest_index_px(r, g, b, palette, metric)
        out[y, x] = index
        err_r = (r - palette[index, 0]) * strength
        err_g = (g - palette[index, 1]) * strength
        err_b = (b - palette[index, 2]) * strength
        own = classes[y % class_h, x % class_w]
        total = 0.0
        for k in range(count):
            ny = y + offsets[k, 1]
            nx = x + offsets[k, 0]
            if 0 <= ny < height and 0 <= nx < width:
                if classes[ny % class_h, nx % class_w] > own:
                    total += weights[k]
        if total <= 0.0:
            continue
        for k in range(count):
            ny = y + offsets[k, 1]
            nx = x + offsets[k, 0]
            if 0 <= ny < height and 0 <= nx < width:
                if classes[ny % class_h, nx % class_w] > own:
                    share = weights[k] / total
                    work[ny, nx, 0] += err_r * share
                    work[ny, nx, 1] += err_g * share
                    work[ny, nx, 2] += err_b * share
    return out


@register_algorithm("dot_diffusion", "Dot Diffusion", "other", _PARAMS)
def dot_diffusion(img: Image, palette: Palette, params: dict) -> Indices:
    """Dither in class-matrix order, diffusing only to not-yet-processed neighbours."""
    height, width = img.shape[:2]
    classes = class_map(height, width)
    order = np.argsort(classes, axis=None, kind="stable")
    ys, xs = np.unravel_index(order, (height, width))
    return _diffuse(
        np.ascontiguousarray(img, dtype=np.float32),
        np.ascontiguousarray(palette, dtype=np.float32),
        classes,
        np.ascontiguousarray(ys, dtype=np.int64),
        np.ascontiguousarray(xs, dtype=np.int64),
        _OFFSETS,
        _WEIGHTS,
        float(params["strength"]),
        metric_of(params),
    )
