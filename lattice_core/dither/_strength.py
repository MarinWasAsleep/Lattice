"""Shared helpers for the dither strength parameter (CONTRACT §14)."""

from __future__ import annotations

import numpy as np

from lattice_core.color import METRIC_LAB2000, _nearest_euclidean, _nearest_lab2000
from lattice_core.types import Image, Indices, Palette

STRENGTH = "strength"
METRIC_KEY = "_color_metric"


def metric_of(params: dict) -> int:
    """Return the colour metric code the pipeline injected, defaulting to sRGB."""
    return int(params.get(METRIC_KEY, 0))


def nearest_in_space(img: Image, palette: Palette, code: int) -> Indices:
    """Return the nearest palette index for data already in the metric's working space."""
    if code == METRIC_LAB2000:
        return _nearest_lab2000(img, palette)
    return _nearest_euclidean(img, palette)


def blend_toward_nearest(
    img: Image, palette: Palette, indices: Indices, strength: float, code: int
) -> Indices:
    """Blend an algorithm result toward the nearest-colour map, in colour space.

    ``strength = 0`` returns the nearest-colour map exactly and ``strength = 1``
    returns the algorithm result untouched, which is the invariant of §14.
    """
    if strength >= 1.0:
        return indices
    nearest = nearest_in_space(img, palette, code)
    if strength <= 0.0:
        return nearest
    weight = np.float32(strength)
    mixed = palette[indices] * weight + palette[nearest] * np.float32(1.0 - strength)
    return nearest_in_space(np.ascontiguousarray(mixed, dtype=np.float32), palette, code)
