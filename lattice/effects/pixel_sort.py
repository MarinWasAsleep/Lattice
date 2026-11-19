"""Pixel sort effect: stably reorder pixel runs inside a brightness band (CONTRACT §14)."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np

from lattice.registry import register_effect
from lattice.types import Image, ParamSpec

_DIRECTIONS = ("rows", "columns", "diagonal")
_SORT_KEYS = ("luma", "hue", "saturation", "r", "g", "b")

# Labels reuse existing i18n catalogue keys (test_i18n requires every effect
# parameter label to be translatable; those lines live outside this card's owns).
_PARAMS = (
    ParamSpec("black", "Darkness", "float", 0.0, 0.0, 1.0, 0.05),
    ParamSpec("brightness", "Brightness", "float", 0.5, 0.0, 1.0, 0.05),
    ParamSpec("white", "Threshold", "float", 1.0, 0.0, 1.0, 0.05),
    ParamSpec("direction", "Angle", "choice", "rows", choices=_DIRECTIONS),
    ParamSpec("key", "Colour metric", "choice", "luma", choices=_SORT_KEYS),
)

_LUMA = (0.2126, 0.7152, 0.0722)
_MASK_THRESHOLD = 0.5


def _as_float(img: Image) -> np.ndarray:
    """Return a contiguous float32 copy of img in [0, 1], never touching the input."""
    out = np.array(img, dtype=np.float32, copy=True)
    return np.clip(out, 0.0, 1.0, out=out)


def _hue_key(rgb: np.ndarray) -> np.ndarray:
    """Return the HSV hue of every pixel as a float32 array in [0, 1)."""
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    maximum = np.maximum(np.maximum(r, g), b)
    minimum = np.minimum(np.minimum(r, g), b)
    delta = maximum - minimum
    with np.errstate(divide="ignore", invalid="ignore"):
        hue = np.where(
            delta > 1e-8,
            np.where(
                maximum == r,
                ((g - b) / delta) % 6.0,
                np.where(maximum == g, (b - r) / delta + 2.0, (r - g) / delta + 4.0),
            )
            / 6.0,
            0.0,
        )
    return hue.astype(np.float32)


def _saturation_key(rgb: np.ndarray) -> np.ndarray:
    """Return the HSV saturation of every pixel as a float32 array in [0, 1]."""
    maximum = np.maximum(np.maximum(rgb[:, :, 0], rgb[:, :, 1]), rgb[:, :, 2])
    minimum = np.minimum(np.minimum(rgb[:, :, 0], rgb[:, :, 1]), rgb[:, :, 2])
    sat = np.where(maximum > 1e-8, (maximum - minimum) / maximum, 0.0)
    return sat.astype(np.float32)


def _channel(index: int) -> Callable[[np.ndarray], np.ndarray]:
    """Return a key function that reads one RGB channel."""

    def key(rgb: np.ndarray) -> np.ndarray:
        return rgb[:, :, index].astype(np.float32)

    return key


_KEYS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "luma": lambda rgb: (
        _LUMA[0] * rgb[:, :, 0] + _LUMA[1] * rgb[:, :, 1] + _LUMA[2] * rgb[:, :, 2]
    ).astype(np.float32),
    "hue": _hue_key,
    "saturation": _saturation_key,
    "r": _channel(0),
    "g": _channel(1),
    "b": _channel(2),
}


def _line_indices(
    shape: tuple[int, int], direction: str
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (rows, cols) index arrays tracing one scan line at a time."""
    height, width = shape
    if direction == "rows":
        for r in range(height):
            yield np.full(width, r), np.arange(width)
    elif direction == "columns":
        for c in range(width):
            yield np.arange(height), np.full(height, c)
    else:
        for offset in range(-(width - 1), height):
            lo = max(0, offset)
            hi = min(height, width + offset)
            line_rows = np.arange(lo, hi)
            yield line_rows, line_rows - offset


def _sort_line(
    keys: np.ndarray,
    pixels: np.ndarray,
    allowed: np.ndarray | None,
    black: float,
    brightness: float,
    white: float,
) -> np.ndarray:
    """Stably sort the runs of pixels inside the band that start above brightness.

    A run starts at a pixel whose key passes ``brightness`` and continues while the
    key stays inside the ``black``..``white`` band; masked-out (not ``allowed``)
    pixels stop a run just like being outside the band.
    """
    out = pixels.copy()
    in_band = (keys >= black) & (keys <= white)
    if allowed is not None:
        in_band = in_band & allowed
    index = 0
    size = keys.size
    while index < size:
        if keys[index] > brightness:
            start = index
            while index < size and in_band[index]:
                index += 1
            if index == start:
                index += 1
            elif index > start + 1:
                order = np.argsort(keys[start:index], kind="stable")
                out[start:index] = pixels[start:index][order]
        else:
            index += 1
    return out


def _mask_plane(mask: object, shape: tuple[int, int]) -> np.ndarray:
    """Return a float32 (H, W) interval-map plane, validating the mask size."""
    data = np.asarray(mask, dtype=np.float32)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2 or data.shape != shape:
        raise ValueError(f"mask must be {shape}, got {data.shape}")
    return data


@register_effect("pixel_sort", "Pixel sort", _PARAMS)
def pixel_sort(
    img: Image, params: dict, rng: np.random.Generator, *, mask: Image | None = None
) -> Image:
    """Stably sort runs of pixels that pass the brightness threshold inside the band.

    The sort is deterministic by construction and never draws on ``rng``, which the
    signature keeps only to match the uniform effect call interface.
    """
    out = _as_float(img)
    keys = _KEYS[str(params["key"])](out)
    black = float(params["black"])
    brightness = float(params["brightness"])
    white = float(params["white"])
    direction = str(params["direction"])
    allowed = None
    if mask is not None:
        allowed = _mask_plane(mask, out.shape[:2]) > _MASK_THRESHOLD
    height, width = out.shape[:2]
    for rows, cols in _line_indices((height, width), direction):
        line_keys = keys[rows, cols]
        line_ok = allowed[rows, cols] if allowed is not None else None
        out[rows, cols] = _sort_line(
            line_keys, out[rows, cols], line_ok, black, brightness, white
        )
    return out
