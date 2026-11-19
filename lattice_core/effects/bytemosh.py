"""Byte-stream data moshing: swap, shift and reinterpret raster byte windows (L28)."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

_OPERATIONS = ("swap", "shift", "interpret", "drift")
_MAX_WINDOWS = 8  # most windows moshed at amount = 1

# Labels reuse existing i18n catalogue keys (test_i18n): "Scale" is the suite's
# mode-selector key (channel_shift, feedback), "Thickness" a band size, "Spread" a
# displacement. LABEL_NOTES records the honest reading of each, as ntsc does.
_PARAMS = (
    ParamSpec("amount", "Amount", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("operation", "Scale", "choice", "swap", choices=_OPERATIONS),
    # `stride` must be able to cover a large share of the raster: capped at 3072 bytes it
    # was smaller than one row of a 720px image, so swapping or pasting a "big block" was
    # silently reduced to a one-pixel sliver and never read as displaced content.
    ParamSpec("stride", "Thickness", "int", 96, 3, 4_000_000, 3),
    # `offset` must reach past a full raster: clamped to 65536 bytes it could not even
    # address the second half of a 2 MB payload, so the anchored window never moved.
    ParamSpec("offset", "Spread", "int", 0, -4_000_000, 4_000_000, 1),
    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
)

LABEL_NOTES: dict[str, str] = {
    "amount": "the intensity: how many byte windows are moshed",
    "operation": "the byte rearrangement: swap, shift or interpret",
    "stride": "the window length in bytes, kept a multiple of 3",
    "offset": "the byte displacement anchoring the windows",
    "seed": "the seed choosing random window positions",
}


def _config(params: Mapping[str, object]) -> dict:
    """Return typed options, defaulting every field to its neutral value."""
    operation = str(params.get("operation", "swap"))
    if operation not in _OPERATIONS:
        raise ValueError(f"unknown bytemosh operation: {operation!r}")
    return {
        "amount": float(params.get("amount", 0.0)),
        "operation": operation,
        "stride": int(params.get("stride", 96)),
        "offset": int(params.get("offset", 0)),
        "seed": int(params.get("seed", 0)),
    }


def _generator(seed: int, rng: np.random.Generator) -> np.random.Generator:
    """Return the position source: `seed` offsets the pipeline rng, so both drive it."""
    return np.random.default_rng([seed, int(rng.integers(0, 2**32))])


def _payload(img: Image) -> tuple[np.ndarray, tuple[int, ...]]:
    """Quantise the raster to a flat uint8 byte stream, remembering its shape."""
    data = np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0)
    flat = np.round(data * np.float32(255.0)).astype(np.uint8).ravel()
    return flat, data.shape


def _window(stride: int, size: int) -> int:
    """Snap the window to a multiple of 3 bytes, clamped to the payload length."""
    snapped = max(3, 3 * int(round(stride / 3)))
    limit = 3 * (size // 3)
    if limit >= 3:
        snapped = min(snapped, limit)
    return max(1, min(snapped, size))


def _swap(data: np.ndarray, stride: int, offset: int, count: int, rng: np.random.Generator) -> None:
    """Exchange `count` pairs of stride-byte windows; the first pair is anchored."""
    size = data.size
    for index in range(count):
        if index == 0:
            a = offset % size
            b = (offset + stride) % size
        else:
            a = int(rng.integers(0, size))
            b = int(rng.integers(0, size))
        if a == b or a + stride > size or b + stride > size:
            continue
        tmp = data[a : a + stride].copy()
        data[a : a + stride] = data[b : b + stride]
        data[b : b + stride] = tmp


def _shift(data: np.ndarray, offset: int, amount: float) -> np.ndarray:
    """Circularly rotate the whole payload by round(amount * offset) bytes, edges wrapped."""
    return np.roll(data, int(round(amount * offset)))


def _interpret(
    data: np.ndarray, stride: int, offset: int, count: int, rng: np.random.Generator
) -> None:
    """Paste the window read at `offset` onto `count` seeded destination windows."""
    size = data.size
    src = offset % size
    if src + stride > size:
        return
    block = data[src : src + stride].copy()
    for _ in range(count):
        dst = int(rng.integers(0, size))
        if dst + stride <= size:
            data[dst : dst + stride] = block


def _drift(data: np.ndarray, width: int, stride: int, offset: int, amount: float,
           rng: np.random.Generator | None = None) -> None:
    """Slide raster rows sideways by a growing, uneven amount: a torn-file lean.

    Two lessons from the visual verdicts went into this shape. First, a constant slope
    reads as a clean shear (a filter), so the step grows and whole bands restart at random
    offsets. Second, letting the displacement accumulate without a ceiling destroys the
    image even at mid intensity, so the travel is capped at a fraction of the row width
    and only a share of the rows is touched: the shapes must stay recognisable.
    """
    size = data.size
    if width <= 0 or size < width:
        return
    rows = size // width
    gen = rng if rng is not None else np.random.default_rng(0)
    payload = data[: rows * width].reshape(rows, width).copy()
    ceiling = max(1, int(width * amount * 0.75))  # never tear more than 3/4 of a row
    touched = max(1, int(round(rows * (0.25 + 0.75 * amount))))  # fraction of rows hit
    band = max(1, rows // 5)
    for row in range(rows):
        if row >= touched:
            continue
        lean = row / max(1, touched - 1)
        step = int(round(ceiling * lean * (0.6 + 0.8 * lean)))  # accelerates downward
        if band > 1 and row % band == 0 and row:
            step = min(ceiling, step + int(gen.integers(-width // 6, width // 6)) % ceiling)
        if step:
            payload[row] = np.roll(payload[row], step)
    data[: rows * width] = payload.reshape(-1)


@register_effect("bytemosh", "Byte Mosh", _PARAMS)
def bytemosh(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Mosh the raster byte stream: swap, shift or reinterpret fixed byte windows."""
    cfg = _config(params)
    source = np.array(img, dtype=np.float32, copy=True)
    amount = cfg["amount"]
    if amount <= 0.0:
        return source
    data, shape = _payload(source)
    if data.size == 0:
        return source
    stride = _window(cfg["stride"], data.size)
    count = max(1, int(round(amount * _MAX_WINDOWS)))
    gen = _generator(cfg["seed"], rng)
    if cfg["operation"] == "shift":
        data = _shift(data, cfg["offset"], amount)
    elif cfg["operation"] == "drift":
        _drift(data, shape[1] * 3 if len(shape) == 3 else shape[1], stride,
               cfg["offset"], amount, gen)
    elif cfg["operation"] == "swap":
        _swap(data, stride, cfg["offset"], count, gen)
    else:
        _interpret(data, stride, cfg["offset"], count, gen)
    out = data.reshape(shape).astype(np.float32) / np.float32(255.0)
    return np.ascontiguousarray(out, dtype=np.float32)
