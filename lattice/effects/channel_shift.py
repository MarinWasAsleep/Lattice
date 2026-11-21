"""Channel shift effect: per-channel translate, scale and radial offset (CONTRACT §15)."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from lattice.registry import register_effect
from lattice.types import Image, ParamSpec

_MODES = ("translate", "scale", "radial")
_DIRECTIONS = np.array([-1.0, 0.0, 1.0], dtype=np.float32)
DEFAULT_CHANNELS = 0b101  # R and B: the chromatic-aberration pair.
_MIN_RADIUS = 0.5
_MIN_SCALE_FACTOR = 0.1

_AMOUNT = ParamSpec("amount", "Amount (px)", "float", 4.0, 0.0, 50.0, 0.5)
_MODE = ParamSpec("mode", "Scale", "choice", "translate", choices=_MODES)
_CHANNELS = ParamSpec("channels", "Per channel", "int", DEFAULT_CHANNELS, 0, 7, 1)
_PARAMS = (_AMOUNT, _MODE, _CHANNELS)


def validate_params(params: Mapping[str, object]) -> dict:
    """Validate amount, mode and the 3-bit channel mask, naming offending values."""
    amount = float(params.get("amount", 4.0))
    if not np.isfinite(amount) or amount < 0.0:
        raise ValueError(f"amount must be finite and non-negative, got {amount!r}")
    mode = str(params.get("mode", "translate"))
    if mode not in _MODES:
        raise ValueError(f"unknown channel shift mode: {mode!r}")
    channels = int(params.get("channels", DEFAULT_CHANNELS))
    if not 0 <= channels <= 0b111:
        raise ValueError(f"channels must be a 3-bit mask, got {channels!r}")
    return {"amount": amount, "mode": mode, "channels": channels}


def _grid(height: int, width: int) -> tuple[np.ndarray, ...]:
    """Return float32 coordinate and centre-from-centre maps for an (H, W) image."""
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    cx = np.float32((width - 1) / 2.0)
    cy = np.float32((height - 1) / 2.0)
    return xs, ys, xs - cx, ys - cy, cx, cy


def _sample(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2-D channel at float coordinates, replicating edges."""
    height, width = channel.shape
    x0 = np.floor(sx).astype(np.intp)
    y0 = np.floor(sy).astype(np.intp)
    fx = (sx - x0).astype(np.float32)
    fy = (sy - y0).astype(np.float32)
    np.clip(x0, 0, width - 1, out=x0)
    np.clip(y0, 0, height - 1, out=y0)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    one = np.float32(1.0)
    top = channel[y0, x0] * (one - fx) + channel[y0, x1] * fx
    bottom = channel[y1, x0] * (one - fx) + channel[y1, x1] * fx
    return top * (one - fy) + bottom * fy


def _coordinates(
    mode: str, direction: float, amount: float, grid: tuple[np.ndarray, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Return float sample coordinates for one channel under the selected mode."""
    xs, ys, dx, dy, cx, cy = grid
    if mode == "translate":
        return xs - np.float32(direction * amount), ys
    radius = max(float(np.hypot(float(cx), float(cy))), _MIN_RADIUS)
    strength = np.float32(direction * amount / radius)
    if mode == "radial":
        return xs - strength * dx, ys - strength * dy
    factor = np.float32(max(_MIN_SCALE_FACTOR, 1.0 + float(strength)))
    return cx + dx / factor, cy + dy / factor


def shift(img: Image, params: Mapping[str, object] | None = None) -> Image:
    """Return the channel-shifted image, leaving the input untouched."""
    cfg = validate_params(params or {})
    source = np.asarray(img, dtype=np.float32)
    out = np.array(source, dtype=np.float32, copy=True, order="C")
    if cfg["amount"] == 0.0 or cfg["channels"] == 0:
        return out
    if source.ndim != 3 or source.shape[2] < 3:
        return out
    grid = _grid(source.shape[0], source.shape[1])
    for channel in range(3):
        if not cfg["channels"] & (1 << channel):
            continue
        sx, sy = _coordinates(
            cfg["mode"], float(_DIRECTIONS[channel]), cfg["amount"], grid
        )
        out[:, :, channel] = _sample(source[:, :, channel], sx, sy)
    return np.clip(out, 0.0, 1.0, out=out)


@register_effect("channel_shift", "Channel Shift", _PARAMS)
def channel_shift(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Apply the per-channel shift; deterministic, so rng is accepted but unused."""
    return shift(img, params)
