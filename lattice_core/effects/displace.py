"""Displacement effect (CONTRACT §13).

``dst(x, y) = src(x + k * (mapR - 0.5), y + k * (mapG - 0.5))``. The map is an
RGB image: its red channel is ``mapR`` and drives the horizontal shift, its green
channel is ``mapG`` and drives the vertical one. ``mode`` picks which field of the
map supplies ``mapR`` — ``r`` reproduces the formula verbatim, ``luma``/``hue``/
``g``/``b`` read the fields the rest of the suite reads. A greyscale map is
promoted to R = G = B, so it drives both axes with the same value.

The map is the source image, a seeded noise field, or an array the caller passes
(a sequence frame, a feedback-buffer snapshot, a painted flow map). Sampling is
bilinear and the edges clamp. ``iterations`` applies the shift again to its own
output and averages the passes with a decaying weight, which smears the image
without a feedback loop. ``mask`` (§18) blends the result back over the source:
0 keeps the source, 1 keeps the effect.
"""

from __future__ import annotations

import numpy as np

from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

_MODES: tuple[str, ...] = ("luma", "r", "g", "b", "hue")
# §13's four map sources. `sequence` and `feedback` are both "an array the caller
# passes" — core cannot tell a sequence frame from a feedback snapshot — so the
# three non-noise sources all read the same map_img argument (E1).
_MAP_SOURCES: tuple[str, ...] = ("image", "sequence", "noise", "feedback")
_CHANNEL_INDEX: dict[str, int] = {"r": 0, "g": 1, "b": 2}
# sRGB luma, summed in float64 so every neutral grey reads back as that exact grey.
_LUMA_WEIGHTS: tuple[float, float, float] = (0.2126, 0.7152, 0.0722)
_NEUTRAL = np.float32(0.5)
_MAX_DECAY = 0.99
_MAX_ITERATIONS = 8

# Labels are keys of the frozen i18n catalogue (lattice_dither/i18n/en.json),
# which is outside this card's owns; no catalogue entry may be added here.
_PARAMS = (
    ParamSpec("amount", "Amount (px)", "float", 8.0, 0.0, 64.0, 0.5),
    ParamSpec("mode", "Per channel", "choice", "luma", choices=_MODES),
    ParamSpec("map_source", "Source", "choice", "image", choices=_MAP_SOURCES),
    ParamSpec("iterations", "Iterations", "int", 1, 1, _MAX_ITERATIONS, 1),
    ParamSpec("decay", "Strength", "float", 0.5, 0.0, _MAX_DECAY, 0.01),
)


def _as_rgb(img: Image) -> np.ndarray:
    """Return img as a float32 (H, W, 3) array, promoting a greyscale plane to R = G = B."""
    data = np.asarray(img, dtype=np.float32)
    if data.ndim == 2:
        return np.repeat(data[:, :, None], 3, axis=2)
    if data.ndim != 3 or data.shape[2] != 3:
        raise ValueError(f"displacement needs an (H, W, 3) image, got shape {data.shape}")
    return data


def _luma(rgb: np.ndarray) -> np.ndarray:
    """Return the sRGB luma of every pixel as float32, exact on every neutral grey."""
    total = rgb[:, :, 0].astype(np.float64) * _LUMA_WEIGHTS[0]
    total += rgb[:, :, 1].astype(np.float64) * _LUMA_WEIGHTS[1]
    total += rgb[:, :, 2].astype(np.float64) * _LUMA_WEIGHTS[2]
    return total.astype(np.float32)


def _hue(rgb: np.ndarray) -> np.ndarray:
    """Return the hue of every pixel in [0, 1]; a neutral pixel reads exactly 0.5."""
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    high = np.maximum(np.maximum(red, green), blue)
    low = np.minimum(np.minimum(red, green), blue)
    delta = high - low
    chroma = delta > 0.0
    safe = np.where(chroma, delta, np.float32(1.0))
    red_max = chroma & (high == red)
    green_max = chroma & (high == green) & ~red_max
    turn = np.where(
        red_max,
        ((green - blue) / safe) % np.float32(6.0),
        np.where(
            green_max,
            (blue - red) / safe + np.float32(2.0),
            (red - green) / safe + np.float32(4.0),
        ),
    )
    hue = np.where(chroma, turn / np.float32(6.0), _NEUTRAL)
    return np.clip(hue, 0.0, 1.0).astype(np.float32)


def _field(map_rgb: np.ndarray, mode: str) -> np.ndarray:
    """Return the (H, W) float32 field that `mode` reads from an RGB map."""
    if mode == "luma":
        return _luma(map_rgb)
    if mode == "hue":
        return _hue(map_rgb)
    return np.ascontiguousarray(map_rgb[:, :, _CHANNEL_INDEX[mode]])


def _map_rgb(
    img_rgb: np.ndarray,
    params: dict,
    rng: np.random.Generator,
    map_img: Image | None,
) -> np.ndarray:
    """Return the RGB map the drivers are read from, per the selected map source."""
    source = str(params.get("map_source", "image"))
    if source not in _MAP_SOURCES:
        raise ValueError(f"unknown displacement map source: {source!r}")
    if source == "image":
        return img_rgb
    if source == "noise":
        return rng.random(img_rgb.shape, dtype=np.float32)
    if map_img is None:
        raise ValueError(f"map_source {source!r} needs a map image")
    mapped = _as_rgb(map_img)
    if mapped.shape[:2] != img_rgb.shape[:2]:
        raise ValueError(f"map must be {img_rgb.shape[:2]}, got {mapped.shape[:2]}")
    return mapped


def _sample_coordinates(
    map_r: np.ndarray, map_g: np.ndarray, amount: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return the float32 x and y source coordinates of dst(x, y)."""
    height, width = map_r.shape
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    scale = np.float32(amount)
    return xs + (map_r - _NEUTRAL) * scale, ys + (map_g - _NEUTRAL) * scale


def _is_identity(sx: np.ndarray, sy: np.ndarray) -> bool:
    """Return True when the sample coordinates are exactly the source pixel grid."""
    height, width = sx.shape
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    return bool(np.array_equal(sx, np.broadcast_to(xs, sx.shape))) and bool(
        np.array_equal(sy, np.broadcast_to(ys, sy.shape))
    )


def _bilinear(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2-D channel at float coordinates, clamping to the edges."""
    height, width = channel.shape
    x = np.clip(sx, 0.0, np.float32(width - 1))
    y = np.clip(sy, 0.0, np.float32(height - 1))
    x0 = np.floor(x).astype(np.intp)
    y0 = np.floor(y).astype(np.intp)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    one = np.float32(1.0)
    top = channel[y0, x0] * (one - fx) + channel[y0, x1] * fx
    bottom = channel[y1, x0] * (one - fx) + channel[y1, x1] * fx
    return top * (one - fy) + bottom * fy


def _displace_once(source: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Return one displacement of every channel of source to the given coordinates."""
    out = np.empty(source.shape, dtype=np.float32)
    for channel in range(source.shape[2]):
        out[:, :, channel] = _bilinear(source[:, :, channel], sx, sy)
    return out


def _smear(
    source: np.ndarray, sx: np.ndarray, sy: np.ndarray, iterations: int, decay: float
) -> np.ndarray:
    """Average the displacement applied 1..iterations times, weighting step i by decay**i."""
    current = _displace_once(source, sx, sy)
    if iterations <= 1:
        return current
    accumulated = current.copy()
    weight = np.float32(1.0)
    total = np.float32(1.0)
    for _ in range(1, iterations):
        current = _displace_once(current, sx, sy)
        weight *= np.float32(decay)
        accumulated += weight * current
        total += weight
    return accumulated / total


def _mask_weights(mask: object, shape: tuple[int, int]) -> np.ndarray:
    """Return the (H, W) float32 mask weights, validating the size and clipping to [0, 1]."""
    data = np.asarray(mask, dtype=np.float32)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2 or data.shape != shape:
        raise ValueError(f"mask must be {shape}, got {data.shape}")
    return np.clip(data, 0.0, 1.0)


def _apply_mask(source: np.ndarray, displaced: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Blend displaced over source by the mask: 0 keeps the source, 1 keeps the effect."""
    weight = weights[:, :, None]
    one = np.float32(1.0)
    return (one - weight) * source + weight * displaced


@register_effect("displace", "Displacement", _PARAMS)
def displace(
    img: Image,
    params: dict,
    rng: np.random.Generator,
    *,
    mask: Image | None = None,
    map_img: Image | None = None,
) -> Image:
    """Displace the image by a map field, with decayed iterations and an optional mask."""
    source = np.asarray(img, dtype=np.float32)
    greyscale_input = source.ndim == 2
    rgb = _as_rgb(source)
    mode = str(params.get("mode", "luma"))
    if mode not in _MODES:
        raise ValueError(f"unknown displacement mode: {mode!r}")
    amount = float(params.get("amount", 8.0))
    iterations = max(1, min(int(params.get("iterations", 1)), _MAX_ITERATIONS))
    decay = float(np.clip(float(params.get("decay", 0.5)), 0.0, _MAX_DECAY))
    map_rgb = _map_rgb(rgb, params, rng, map_img)
    sx, sy = _sample_coordinates(_field(map_rgb, mode), map_rgb[:, :, 1], amount)
    if _is_identity(sx, sy):
        displaced = np.array(rgb, dtype=np.float32, copy=True)
    else:
        displaced = _smear(rgb, sx, sy, iterations, decay)
    if mask is not None:
        displaced = _apply_mask(rgb, displaced, _mask_weights(mask, sx.shape))
    out = np.ascontiguousarray(np.clip(displaced, 0.0, 1.0), dtype=np.float32)
    return out[:, :, 0] if greyscale_input else out
