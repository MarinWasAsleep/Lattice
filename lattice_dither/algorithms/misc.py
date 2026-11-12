"""Threshold, random and Riemersma dithering algorithms (T04)."""

from __future__ import annotations

import numpy as np
from numba import njit

from lattice_dither.algorithms._strength import (
    blend_toward_nearest,
    metric_of,
    nearest_in_space,
)
from lattice_dither.core.color import luminance, nearest_index_px
from lattice_dither.core.registry import register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

_LEVEL = ParamSpec("level", "Level", "float", 0.5, 0.0, 1.0, 0.01)
_SPREAD = ParamSpec("spread", "Spread", "float", 1.0, 0.0, 2.0, 0.01)
_SEED = ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1)
_HISTORY = ParamSpec("history", "History", "int", 16, 4, 64, 1)
_RATIO = ParamSpec("ratio", "Ratio", "float", 1.0 / 16.0, 0.01, 0.5, 0.001)
_STRENGTH = ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05)


def _extremes(palette: Palette) -> tuple[int, int]:
    """Return the indices of the darkest and the lightest palette colour."""
    lum = luminance(palette.reshape(1, -1, 3))[0]
    return int(np.argmin(lum)), int(np.argmax(lum))


def _amplitude(spread: float, k: int) -> float:
    """Return the noise amplitude used by the ordered and random algorithms."""
    return spread / max(1, round(k ** (1.0 / 3.0)) - 1)


def _hilbert_xy(order: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the x and y coordinates of every point of a Hilbert curve of the given order."""
    size = 1 << order
    index = np.arange(size * size, dtype=np.int64)
    x = np.zeros_like(index)
    y = np.zeros_like(index)
    rest = index.copy()
    step = 1
    while step < size:
        rx = (rest // 2) & 1
        ry = (rest ^ rx) & 1
        swap = ry == 0
        flip = swap & (rx == 1)
        flipped_x = np.where(flip, step - 1 - x, x)
        flipped_y = np.where(flip, step - 1 - y, y)
        x = np.where(swap, flipped_y, flipped_x) + step * rx
        y = np.where(swap, flipped_x, flipped_y) + step * ry
        rest //= 4
        step *= 2
    return x, y


@njit(cache=True)
def _riemersma_kernel(
    img: np.ndarray,
    palette: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
    weights: np.ndarray,
    metric: int,
) -> np.ndarray:
    """Walk the Hilbert order, diffusing the weighted error history; numba kernel."""
    height, width = img.shape[0], img.shape[1]
    out = np.zeros((height, width), dtype=np.int32)
    count = weights.shape[0]
    history = np.zeros((count, 3), dtype=np.float32)
    for step in range(ys.shape[0]):
        y = ys[step]
        x = xs[step]
        r = img[y, x, 0]
        g = img[y, x, 1]
        b = img[y, x, 2]
        for i in range(count):
            weight = weights[i]
            r += weight * history[i, 0]
            g += weight * history[i, 1]
            b += weight * history[i, 2]
        index = nearest_index_px(r, g, b, palette, metric)
        out[y, x] = index
        for i in range(count - 1, 0, -1):
            history[i, 0] = history[i - 1, 0]
            history[i, 1] = history[i - 1, 1]
            history[i, 2] = history[i - 1, 2]
        history[0, 0] = r - palette[index, 0]
        history[0, 1] = g - palette[index, 1]
        history[0, 2] = b - palette[index, 2]
    return out


@register_algorithm("threshold", "Threshold", "other", (_LEVEL, _STRENGTH))
def threshold(img: Image, palette: Palette, params: dict) -> Indices:
    """Map pixels darker than the level to the darkest palette colour, the rest to the lightest."""
    level = float(params["level"])
    dark, light = _extremes(palette)
    indices = np.where(luminance(img) < level, dark, light).astype(np.int32)
    return blend_toward_nearest(
        img, palette, indices, float(params["strength"]), metric_of(params)
    )


@register_algorithm("random", "Random", "other", (_SPREAD, _SEED, _STRENGTH))
def random_dither(img: Image, palette: Palette, params: dict) -> Indices:
    """Add uniform white noise to every pixel, then snap to the nearest palette colour."""
    spread = float(params["spread"])
    seed = int(params["seed"])
    amplitude = np.float32(_amplitude(spread, palette.shape[0]))
    noise = np.random.default_rng(seed).random(img.shape[:2], dtype=np.float32)
    noisy = img + (noise[:, :, None] - np.float32(0.5)) * amplitude
    code = metric_of(params)
    indices = nearest_in_space(np.ascontiguousarray(noisy, dtype=np.float32), palette, code)
    return blend_toward_nearest(img, palette, indices, float(params["strength"]), code)


@register_algorithm("riemersma", "Riemersma", "other", (_HISTORY, _RATIO, _STRENGTH))
def riemersma(img: Image, palette: Palette, params: dict) -> Indices:
    """Dither along a Hilbert curve, diffusing a weighted history of past errors."""
    history = int(params["history"])
    ratio = float(params["ratio"])
    height, width = img.shape[:2]
    order = 0
    while (1 << order) < max(height, width):
        order += 1
    xs, ys = _hilbert_xy(order)
    inside = (xs < width) & (ys < height)
    exponents = np.arange(history, dtype=np.float64) / float(history - 1)
    weights = np.power(ratio, exponents)
    weights = np.ascontiguousarray(weights / weights.sum(), dtype=np.float32)
    indices = _riemersma_kernel(
        np.ascontiguousarray(img, dtype=np.float32),
        np.ascontiguousarray(palette, dtype=np.float32),
        np.ascontiguousarray(ys[inside], dtype=np.int64),
        np.ascontiguousarray(xs[inside], dtype=np.int64),
        weights,
        metric_of(params),
    )
    return blend_toward_nearest(
        img, palette, indices, float(params["strength"]), metric_of(params)
    )
