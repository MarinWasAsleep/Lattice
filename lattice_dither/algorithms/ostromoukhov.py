"""Ostromoukhov variable-coefficient error diffusion (SIGGRAPH 2001)."""

from __future__ import annotations

import numpy as np
from numba import njit

from lattice_dither.algorithms._strength import metric_of
from lattice_dither.algorithms.ostromoukhov_table import COEFFICIENTS
from lattice_dither.core.color import nearest_index_px
from lattice_dither.core.registry import register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

_PARAMS = (ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05),)

_TABLE = np.array(COEFFICIENTS, dtype=np.int64)
_TONE_COUNT = _TABLE.shape[0]


@njit(cache=True)
def _diffuse(
    img: np.ndarray, palette: np.ndarray, table: np.ndarray, strength: float, metric: int
) -> np.ndarray:
    """Diffuse with the coefficients of the current tone, serpentine; numba kernel."""
    height = img.shape[0]
    width = img.shape[1]
    tones = table.shape[0]
    work = img.copy()
    out = np.empty((height, width), dtype=np.int32)
    for y in range(height):
        reverse = y % 2 == 1
        for step in range(width):
            x = width - 1 - step if reverse else step
            r = work[y, x, 0]
            g = work[y, x, 1]
            b = work[y, x, 2]
            index = nearest_index_px(r, g, b, palette, metric)
            out[y, x] = index
            err_r = (r - palette[index, 0]) * strength
            err_g = (g - palette[index, 1]) * strength
            err_b = (b - palette[index, 2]) * strength
            tone = int((img[y, x, 0] + img[y, x, 1] + img[y, x, 2]) * 85.0)
            if tone < 0:
                tone = 0
            elif tone >= tones:
                tone = tones - 1
            right = table[tone, 0]
            down_left = table[tone, 1]
            down = table[tone, 2]
            total = right + down_left + down
            if total <= 0:
                continue
            scale = 1.0 / total
            nx = x - 1 if reverse else x + 1
            if 0 <= nx < width:
                work[y, nx, 0] += err_r * right * scale
                work[y, nx, 1] += err_g * right * scale
                work[y, nx, 2] += err_b * right * scale
            if y + 1 < height:
                nx = x + 1 if reverse else x - 1
                if 0 <= nx < width:
                    work[y + 1, nx, 0] += err_r * down_left * scale
                    work[y + 1, nx, 1] += err_g * down_left * scale
                    work[y + 1, nx, 2] += err_b * down_left * scale
                work[y + 1, x, 0] += err_r * down * scale
                work[y + 1, x, 1] += err_g * down * scale
                work[y + 1, x, 2] += err_b * down * scale
    return out


@register_algorithm("ostromoukhov", "Ostromoukhov", "error_diffusion", _PARAMS)
def ostromoukhov(img: Image, palette: Palette, params: dict) -> Indices:
    """Dither with coefficients that vary with the tone of the current pixel."""
    return _diffuse(
        np.ascontiguousarray(img, dtype=np.float32),
        np.ascontiguousarray(palette, dtype=np.float32),
        _TABLE,
        float(params["strength"]),
        metric_of(params),
    )
