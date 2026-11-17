"""Feedback buffer effect (CONTRACT §12).

Iterates ``f(n) = decay * T(f(n-1)) + input`` on a float32 RGB image,
normalising every frame so the recurrence cannot diverge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

_TRANSFORMS: tuple[str, ...] = ("identity", "translate", "rotate", "scale", "displace")
_BLENDS: tuple[str, ...] = ("add", "max", "screen")
_MAX_DECAY = 0.99

# Labels are drawn from the frozen i18n catalogue (lattice_dither/i18n/en.json),
# which is outside this card's owns; no catalogue entry may be added here.
_DECAY = ParamSpec("decay", "Strength", "float", 0.5, 0.0, _MAX_DECAY, 0.01)
_TRANSFORM = ParamSpec("transform", "Scale", "choice", "identity", choices=_TRANSFORMS)
_AMOUNT = ParamSpec("amount", "Amount", "float", 2.0, 0.0, 32.0, 0.5)
_ITERATIONS = ParamSpec("iterations", "Iterations", "int", 1, 1, 8, 1)
_BLEND = ParamSpec("blend", "Ratio", "choice", "add", choices=_BLENDS)
_PARAMS = (_DECAY, _TRANSFORM, _AMOUNT, _ITERATIONS, _BLEND)


def _transform_names(value: object) -> tuple[str, ...]:
    """Return the ordered, validated transform names from a choice or a sequence."""
    if isinstance(value, str):
        names = tuple(part for part in value.replace(",", "+").split("+") if part)
    elif isinstance(value, Sequence):
        names = tuple(str(part) for part in value)
    else:
        names = (str(value),)
    if not names:
        names = ("identity",)
    for name in names:
        if name not in _TRANSFORMS:
            raise ValueError(f"unknown feedback transform: {name!r}")
    return names


def validate_params(params: Mapping[str, object]) -> dict:
    """Validate feedback options, rejecting decay >= 1 and naming the offending value."""
    decay = float(params.get("decay", 0.5))
    if not np.isfinite(decay):
        raise ValueError(f"decay must be finite, got {decay!r}")
    if decay >= 1.0:
        raise ValueError(f"decay must be below 1, got {decay!r}")
    blend = str(params.get("blend", "add"))
    if blend not in _BLENDS:
        raise ValueError(f"unknown feedback blend: {blend!r}")
    return {
        "decay": float(np.clip(decay, 0.0, _MAX_DECAY)),
        "transform": _transform_names(params.get("transform", "identity")),
        "amount": float(np.clip(float(params.get("amount", 2.0)), 0.0, 32.0)),
        "iterations": max(1, int(params.get("iterations", 1))),
        "blend": blend,
    }


def _grid(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Return float32 (H, W) y and x coordinate maps."""
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]
    return np.broadcast_to(ys, (height, width)), np.broadcast_to(xs, (height, width))


def _displacement_field(
    rng: np.random.Generator, height: int, width: int, amount: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return seeded float32 sample coordinates for the displace transform."""
    ys, xs = _grid(height, width)
    scale = np.float32(amount)
    dx = (rng.random((height, width), dtype=np.float32) - np.float32(0.5)) * scale
    dy = (rng.random((height, width), dtype=np.float32) - np.float32(0.5)) * scale
    return xs - dx, ys - dy


def _sample(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2-D channel at float coordinates, clamping to the edges."""
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


def _apply_transform(
    frame: np.ndarray,
    name: str,
    amount: float,
    grid: tuple[np.ndarray, np.ndarray],
    field: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    """Apply one spatial transform by bilinear sampling with replicated edges."""
    if name == "identity":
        return frame
    ys, xs = grid
    height, width = frame.shape[:2]
    if name == "translate":
        sx, sy = xs - np.float32(amount), ys
    elif name == "rotate":
        angle = np.float32(np.deg2rad(np.float32(amount)))
        cos_a, sin_a = np.float32(np.cos(angle)), np.float32(np.sin(angle))
        cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
        ox, oy = xs - cx, ys - cy
        sx = cx + cos_a * ox - sin_a * oy
        sy = cy + sin_a * ox + cos_a * oy
    elif name == "scale":
        factor = np.float32(1.0 + amount / 10.0)
        cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
        sx = cx + (xs - cx) / factor
        sy = cy + (ys - cy) / factor
    else:
        assert field is not None
        sx, sy = field
    out = np.empty_like(frame)
    for channel in range(frame.shape[2]):
        out[:, :, channel] = _sample(frame[:, :, channel], sx, sy)
    return np.clip(out, 0.0, 1.0, out=out)


def _compose(
    frame: np.ndarray,
    names: tuple[str, ...],
    amount: float,
    grid: tuple[np.ndarray, np.ndarray],
    field: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    """Apply the transforms in order, so T is composable."""
    for name in names:
        frame = _apply_transform(frame, name, amount, grid, field)
    return frame


def _mix(damped: np.ndarray, source: np.ndarray, blend: str) -> np.ndarray:
    """Combine the damped previous frame with the fixed input under `blend`."""
    if blend == "add":
        return damped + source
    if blend == "max":
        return np.maximum(damped, source)
    one = np.float32(1.0)
    return one - (one - damped) * (one - source)


def _normalise(frame: np.ndarray) -> np.ndarray:
    """Scale a frame into [0, 1] by its peak when needed, then clip."""
    peak = float(frame.max())
    if peak > 1.0:
        frame = frame / np.float32(peak)
    return np.clip(frame, 0.0, 1.0).astype(np.float32, copy=False)


def iterate(
    img: Image,
    params: Mapping[str, object],
    rng: np.random.Generator,
    iterations: int | None = None,
    buffer: Image | None = None,
) -> Image:
    """Run the feedback recurrence for `iterations` steps and return the final buffer."""
    cfg = validate_params(params)
    source = np.asarray(img, dtype=np.float32)
    height, width = source.shape[:2]
    buf = np.array(source if buffer is None else buffer, dtype=np.float32, copy=True)
    if cfg["decay"] == 0.0:
        return np.ascontiguousarray(buf, dtype=np.float32)
    steps = cfg["iterations"] if iterations is None else max(1, int(iterations))
    grid = _grid(height, width)
    field = (
        _displacement_field(rng, height, width, cfg["amount"])
        if "displace" in cfg["transform"]
        else None
    )
    decay = np.float32(cfg["decay"])
    for _ in range(steps):
        transformed = _compose(buf, cfg["transform"], cfg["amount"], grid, field)
        buf = _normalise(_mix(decay * transformed, source, cfg["blend"]))
    return np.ascontiguousarray(buf, dtype=np.float32)


@register_effect("feedback", "Feedback Buffer", _PARAMS)
def feedback(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Iterate a normalised feedback buffer under the selected transform and blend."""
    return iterate(img, params, rng)
