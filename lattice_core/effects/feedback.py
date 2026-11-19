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
_ORIGINS: tuple[str, ...] = (
    "center",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "left",
    "right",
    "top",
    "bottom",
)
_MAX_DECAY = 0.99

# Labels are drawn from the frozen i18n catalogue (lattice_dither/i18n/en.json),
# which is outside this card's owns; no catalogue entry may be added here.
_DECAY = ParamSpec("decay", "Strength", "float", 0.5, 0.0, _MAX_DECAY, 0.01)
_TRANSFORM = ParamSpec("transform", "Scale", "choice", "identity", choices=_TRANSFORMS)
_AMOUNT = ParamSpec("amount", "Amount", "float", 2.0, 0.0, 32.0, 0.5)
_ITERATIONS = ParamSpec("iterations", "Iterations", "int", 1, 1, 16, 1)
_BLEND = ParamSpec("blend", "Ratio", "choice", "add", choices=_BLENDS)
# Where the transform pivots (rotate, scale) or starts from (translate). Before this the
# echo could only come out of the centre of the frame, whatever the user wanted.
_ORIGIN = ParamSpec("origin", "Source", "choice", "center", choices=_ORIGINS)
# The heading, in degrees: 0 = right, 90 = down. Positive rotates clockwise on screen.
_DIRECTION = ParamSpec("direction", "Angle", "float", 0.0, -180.0, 180.0, 5.0)
_PARAMS = (_DECAY, _TRANSFORM, _AMOUNT, _ITERATIONS, _BLEND, _ORIGIN, _DIRECTION)


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
        "origin": _origin_name(params.get("origin", "center")),
        "direction": float(np.clip(float(str(params.get("direction", 0.0))), -180.0, 180.0)),
    }


def _origin_name(value: object) -> str:
    """Return the validated origin name, naming the offending value."""
    name = str(value)
    if name not in _ORIGINS:
        raise ValueError(f"unknown feedback origin: {name!r}")
    return name


def _origin_point(name: str, height: int, width: int) -> tuple[float, float]:
    """Return the pivot for `name` in pixel coordinates (x, y)."""
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    points = {
        "center": (cx, cy),
        "top_left": (0.0, 0.0),
        "top_right": (float(width - 1), 0.0),
        "bottom_left": (0.0, float(height - 1)),
        "bottom_right": (float(width - 1), float(height - 1)),
        "left": (0.0, cy),
        "right": (float(width - 1), cy),
        "top": (cx, 0.0),
        "bottom": (cx, float(height - 1)),
    }
    return points[name]


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
    origin: str = "center",
    direction: float = 0.0,
) -> np.ndarray:
    """Apply one spatial transform by bilinear sampling with replicated edges.

    `origin` moves the pivot of `rotate`/`scale` and the starting edge of `translate`;
    `direction` gives `translate` a heading instead of the fixed "slide right" and biases
    `displace` so the echo can drift instead of jittering around zero.
    """
    if name == "identity":
        return frame
    ys, xs = grid
    height, width = frame.shape[:2]
    pivot_x, pivot_y = _origin_point(origin, height, width)
    if name == "translate":
        angle = np.float32(np.deg2rad(np.float32(direction)))
        # Screen convention, not maths: heading 0 sends the echo right, 90 sends it DOWN.
        # The sampling grid moves the opposite way to the visible image, hence the minus on
        # both axes — with a plus on Y the echo climbed when the user asked for "down".
        sx = xs - np.float32(amount) * np.float32(np.cos(angle))
        sy = ys - np.float32(amount) * np.float32(np.sin(angle))
    elif name == "rotate":
        angle = np.float32(np.deg2rad(np.float32(amount)))
        cos_a, sin_a = np.float32(np.cos(angle)), np.float32(np.sin(angle))
        ox, oy = xs - np.float32(pivot_x), ys - np.float32(pivot_y)
        sx = np.float32(pivot_x) + cos_a * ox - sin_a * oy
        sy = np.float32(pivot_y) + sin_a * ox + cos_a * oy
    elif name == "scale":
        factor = np.float32(1.0 + amount / 10.0)
        sx = np.float32(pivot_x) + (xs - np.float32(pivot_x)) / factor
        sy = np.float32(pivot_y) + (ys - np.float32(pivot_y)) / factor
    else:
        assert field is not None
        sx, sy = field
        angle = np.float32(np.deg2rad(np.float32(direction)))
        drift_x = np.float32(amount) * 0.25 * np.float32(np.cos(angle))
        drift_y = -np.float32(amount) * 0.25 * np.float32(np.sin(angle))
        sx, sy = sx + drift_x, sy + drift_y
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
    origin: str = "center",
    direction: float = 0.0,
) -> np.ndarray:
    """Apply the transforms in order, so T is composable."""
    for name in names:
        frame = _apply_transform(frame, name, amount, grid, field, origin, direction)
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
        transformed = _compose(buf, cfg["transform"], cfg["amount"], grid, field,
                              cfg["origin"], cfg["direction"])
        buf = _normalise(_mix(decay * transformed, source, cfg["blend"]))
    return np.ascontiguousarray(buf, dtype=np.float32)


@register_effect("feedback", "Feedback Buffer", _PARAMS)
def feedback(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Iterate a normalised feedback buffer under the selected transform and blend."""
    return iterate(img, params, rng)
