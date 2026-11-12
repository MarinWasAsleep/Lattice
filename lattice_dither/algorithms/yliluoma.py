"""Yliluoma's arbitrary-palette positional dithering, algorithms 1 and 2.

Both build a *mixing plan*: a list of palette indices whose average colour
approximates a target, with the threshold matrix choosing which entry a pixel
takes. Algorithm 1 precomputes one plan per luminance level, so it is fast but
blind to chroma; algorithm 2 builds a plan for the pixel's own colour, which
keeps colour at a much higher cost.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from lattice_dither.algorithms._strength import blend_toward_nearest, metric_of
from lattice_dither.algorithms.ordered import blue_noise_ranks
from lattice_dither.core.color import nearest_index_px
from lattice_dither.core.registry import register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

SLOTS = 64
_CACHE_BITS = 4

_STRENGTH = ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05)
_PARAMS_1 = (ParamSpec("levels", "Levels", "int", 64, 2, 256, 1), _STRENGTH)
_PARAMS_2 = (ParamSpec("slots", "Slots", "int", 64, 8, 256, 8), _STRENGTH)


def _buckets(slots: int = SLOTS) -> np.ndarray:
    """Return the 64x64 blue-noise ranks folded into slots threshold buckets."""
    ranks = blue_noise_ranks()
    return np.ascontiguousarray((ranks.astype(np.int64) * slots) // ranks.size, dtype=np.int64)


@njit(cache=True)
def _build_plans(palette: np.ndarray, levels: int, slots: int) -> np.ndarray:
    """Greedily pick, slot by slot, the palette colour that best tracks each grey level."""
    count = palette.shape[0]
    plans = np.empty((levels, slots), dtype=np.int32)
    for level in range(levels):
        target = level / (levels - 1) if levels > 1 else 0.0
        acc_r = 0.0
        acc_g = 0.0
        acc_b = 0.0
        for slot in range(slots):
            best = 0
            best_err = 1e30
            taken = slot + 1
            for candidate in range(count):
                dr = (acc_r + palette[candidate, 0]) / taken - target
                dg = (acc_g + palette[candidate, 1]) / taken - target
                db = (acc_b + palette[candidate, 2]) / taken - target
                err = dr * dr + dg * dg + db * db
                if err < best_err:
                    best_err = err
                    best = candidate
            plans[level, slot] = best
            acc_r += palette[best, 0]
            acc_g += palette[best, 1]
            acc_b += palette[best, 2]
    return plans


@njit(cache=True)
def _apply_plans(img: np.ndarray, plans: np.ndarray, buckets: np.ndarray) -> np.ndarray:
    """Pick the plan entry of each pixel from its luminance level and matrix bucket."""
    height = img.shape[0]
    width = img.shape[1]
    levels = plans.shape[0]
    bucket_h = buckets.shape[0]
    bucket_w = buckets.shape[1]
    out = np.empty((height, width), dtype=np.int32)
    for y in range(height):
        for x in range(width):
            luma = 0.2126 * img[y, x, 0] + 0.7152 * img[y, x, 1] + 0.0722 * img[y, x, 2]
            level = int(luma * (levels - 1) + 0.5)
            if level < 0:
                level = 0
            elif level >= levels:
                level = levels - 1
            out[y, x] = plans[level, buckets[y % bucket_h, x % bucket_w]]
    return out


@njit(cache=True)
def _yliluoma2(
    img: np.ndarray,
    palette: np.ndarray,
    buckets: np.ndarray,
    slots: int,
    bits: int,
) -> np.ndarray:
    """Build one mixing plan per quantised colour, then pick a slot per pixel."""
    height = img.shape[0]
    width = img.shape[1]
    count = palette.shape[0]
    bucket_h = buckets.shape[0]
    bucket_w = buckets.shape[1]
    mask = (1 << bits) - 1
    keys = 1 << (3 * bits)
    cache = np.zeros((keys, slots), dtype=np.int32)
    done = np.zeros(keys, dtype=np.uint8)
    plan = np.empty(slots, dtype=np.int32)
    out = np.empty((height, width), dtype=np.int32)
    for y in range(height):
        for x in range(width):
            r = img[y, x, 0]
            g = img[y, x, 1]
            b = img[y, x, 2]
            qr = int(r * mask + 0.5)
            qg = int(g * mask + 0.5)
            qb = int(b * mask + 0.5)
            if qr < 0:
                qr = 0
            elif qr > mask:
                qr = mask
            if qg < 0:
                qg = 0
            elif qg > mask:
                qg = mask
            if qb < 0:
                qb = 0
            elif qb > mask:
                qb = mask
            key = (qr << (2 * bits)) | (qg << bits) | qb
            if done[key] == 0:
                start = nearest_index_px(r, g, b, palette)
                for slot in range(slots):
                    plan[slot] = start
                sum_r = palette[start, 0] * slots
                sum_g = palette[start, 1] * slots
                sum_b = palette[start, 2] * slots
                for slot in range(slots):
                    old = plan[slot]
                    best = old
                    best_err = 1e30
                    for candidate in range(count):
                        dr = (sum_r - palette[old, 0] + palette[candidate, 0]) / slots - r
                        dg = (sum_g - palette[old, 1] + palette[candidate, 1]) / slots - g
                        db = (sum_b - palette[old, 2] + palette[candidate, 2]) / slots - b
                        err = dr * dr + dg * dg + db * db
                        if err < best_err:
                            best_err = err
                            best = candidate
                    plan[slot] = best
                    sum_r += palette[best, 0] - palette[old, 0]
                    sum_g += palette[best, 1] - palette[old, 1]
                    sum_b += palette[best, 2] - palette[old, 2]
                for slot in range(slots):
                    cache[key, slot] = plan[slot]
                done[key] = 1
            out[y, x] = cache[key, buckets[y % bucket_h, x % bucket_w]]
    return out


@register_algorithm("yliluoma1", "Yliluoma 1", "ordered", _PARAMS_1)
def yliluoma1(img: Image, palette: Palette, params: dict) -> Indices:
    """Mix palette colours per luminance level; fast, but chroma is discarded."""
    levels = int(params["levels"])
    plans = _build_plans(
        np.ascontiguousarray(palette, dtype=np.float32), levels, SLOTS
    )
    indices = _apply_plans(np.ascontiguousarray(img, dtype=np.float32), plans, _buckets())
    return blend_toward_nearest(
        img, palette, indices, float(params["strength"]), metric_of(params)
    )


@register_algorithm("yliluoma2", "Yliluoma 2", "ordered", _PARAMS_2)
def yliluoma2(img: Image, palette: Palette, params: dict) -> Indices:
    """Mix palette colours per pixel colour; slower, but keeps chroma."""
    slots = int(params["slots"])
    indices = _yliluoma2(
        np.ascontiguousarray(img, dtype=np.float32),
        np.ascontiguousarray(palette, dtype=np.float32),
        _buckets(slots),
        slots,
        _CACHE_BITS,
    )
    return blend_toward_nearest(
        img, palette, indices, float(params["strength"]), metric_of(params)
    )
