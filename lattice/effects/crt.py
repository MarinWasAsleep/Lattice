"""CRT / scanlines finishing effect: beam, phosphor mask, bloom, curvature (CONTRACT §17)."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from lattice.registry import register_effect
from lattice.types import Image, ParamSpec

# "none" is the neutral phosphor setting, so a fully neutral parameter set is the identity.
_MASK_TYPES = ("none", "slot", "aperture_grille", "shadow_mask")
_SCANLINE_ROWS = 2  # beam period in image rows at one device pixel per image pixel
_BLOOM_THRESHOLD = 0.6
_LEAK = 0.35  # response of a non-active phosphor stripe
_BRIDGE = 0.75  # slot-mask horizontal bridge
_DOT_GAP = 0.85  # shadow-mask row gap

# Labels reuse existing i18n catalogue keys (test_i18n / DEV-212). `output_width` is
# the device resolution in pixels: 0 means one device pixel per image pixel.
_PARAMS = (
    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
    ParamSpec("scanline_intensity", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("mask", "Dot shape", "choice", "none", choices=_MASK_TYPES),
    ParamSpec("mask_scale", "Scale", "int", 6, 1, 32, 1),
    ParamSpec("bloom", "Strength", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("curvature", "Amount", "float", 0.0, 0.0, 0.9, 0.02),
    ParamSpec("vignette", "Darkness", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("output_width", "Resolution", "int", 0, 0, 16384, 1),
    # The vertical phase of the beam, in rows. Animating it scrolls the scanlines, which is
    # what a live tube does — the old way of animating the CRT (curvature) made the whole
    # picture swell and shrink; no tube ever behaved that way.
    ParamSpec("roll", "Spacing", "float", 0.0, 0.0, 64.0, 0.5),
)


def _config(params: Mapping[str, object]) -> dict:
    """Return typed options, defaulting every field to its neutral value."""
    mask_type = str(params.get("mask", "none"))
    if mask_type not in _MASK_TYPES:
        raise ValueError(f"unknown CRT mask: {mask_type!r}")
    return {
        "scanline": float(params.get("scanline_intensity", 0.0)),
        "mask": mask_type,
        "mask_scale": max(1, int(params.get("mask_scale", 6))),
        "bloom": float(params.get("bloom", 0.0)),
        "curvature": float(params.get("curvature", 0.0)),
        "vignette": float(params.get("vignette", 0.0)),
        "output_width": max(0, int(params.get("output_width", 0))),
        "roll": float(params.get("roll", 0.0)),
    }


def _mask_plane(mask: object, shape: tuple[int, int]) -> np.ndarray:
    """Return a float32 (H, W) coverage plane, validating the mask size."""
    data = np.asarray(mask, dtype=np.float32)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2 or data.shape != shape:
        raise ValueError(f"mask must be {shape}, got {data.shape}")
    return np.clip(data, 0.0, 1.0)


def _phosphor(
    height: int, width: int, kind: str, period: int
) -> np.ndarray:
    """Return an (H, W, 3) gain volume whose horizontal period is `period`."""
    xs = np.arange(width, dtype=np.int32)[None, :]
    if kind == "shadow_mask":
        ys = np.arange(height, dtype=np.int32)[:, None]
        phase = (xs + ((ys % 3) * period) // 3) % period
    else:
        phase = xs % period
    stripe = (phase * 3) // period
    gain = np.where(
        stripe[:, :, None] == np.arange(3)[None, None, :], 1.0, _LEAK
    ).astype(np.float32)
    if kind == "slot":
        bridge = np.where(np.arange(height) % 3 == 2, _BRIDGE, 1.0)
        gain = gain * bridge[:, None, None]
    elif kind == "shadow_mask":
        gap = np.where(np.arange(height) % 2 == 1, _DOT_GAP, 1.0)
        gain = gain * gap[:, None, None]
    return gain


def _beam(height: int, amount: float, period_rows: int, phase: float = 0.0) -> np.ndarray:
    """Return an (H, 1) scanline beam profile; 1.0 means no attenuation.

    `phase` shifts the pattern down by that many rows, so animating it makes the scanlines
    scroll the way a live tube's beam drifts.
    """
    rows = np.arange(height, dtype=np.float32)[:, None] - np.float32(phase)
    wave = 0.5 + 0.5 * np.cos(2.0 * np.pi * rows / np.float32(max(1, period_rows)))
    return (1.0 - np.float32(amount) * wave).astype(np.float32)


def _box_blur(plane: np.ndarray, radius: int) -> np.ndarray:
    """Return a separable box blur of one plane with replicated edges."""
    if radius < 1:
        return plane
    padded = np.pad(plane, ((radius, radius), (radius, radius)), mode="edge")
    out = np.zeros_like(plane)
    for dy in range(2 * radius + 1):
        window = padded[dy : dy + plane.shape[0]]
        for dx in range(2 * radius + 1):
            out += window[:, dx : dx + plane.shape[1]]
    return (out / np.float32((2 * radius + 1) ** 2)).astype(np.float32)


def _bloom(source: np.ndarray, amount: float) -> np.ndarray:
    """Screen a blurred luminance bloom of the bright areas over the image."""
    bright = np.maximum(source - np.float32(_BLOOM_THRESHOLD), 0.0)
    luma = (
        0.2126 * bright[:, :, 0] + 0.7152 * bright[:, :, 1] + 0.0722 * bright[:, :, 2]
    )
    radius = 1 + int(round(amount * 2.0))
    glow = _box_blur(luma.astype(np.float32), radius)
    return np.clip(source + np.float32(amount) * glow[:, :, None], 0.0, 1.0)


def _grid(height: int, width: int) -> tuple[np.ndarray, ...]:
    """Return normalised radius maps and pixel coordinates for the geometric stages."""
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
    nx = (xs - cx) / max(float(cx), 0.5)
    ny = (ys - cy) / max(float(cy), 0.5)
    return nx, ny, xs, ys, cx, cy


def _sample(plane: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2-D plane at float coordinates, clamping to the edges."""
    height, width = plane.shape
    x0 = np.floor(sx).astype(np.intp)
    y0 = np.floor(sy).astype(np.intp)
    fx = (sx - x0).astype(np.float32)
    fy = (sy - y0).astype(np.float32)
    np.clip(x0, 0, width - 1, out=x0)
    np.clip(y0, 0, height - 1, out=y0)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    one = np.float32(1.0)
    top = plane[y0, x0] * (one - fx) + plane[y0, x1] * fx
    bottom = plane[y1, x0] * (one - fx) + plane[y1, x1] * fx
    return top * (one - fy) + bottom * fy


def _curve(source: np.ndarray, amount: float, grid: tuple[np.ndarray, ...]) -> np.ndarray:
    """Warp the image toward the edges, black outside the tube, darken the corners.

    A curved tube shows nothing where the warped screen does not reach: samples that
    land outside the source become black instead of clamping to the border pixel
    (H13b, Q1). Without that validity mask the border row and column are smeared into
    long streaks that read as artefacts, not as a CRT silhouette.
    """
    nx, ny, xs, ys, cx, cy = grid
    r2 = nx * nx + ny * ny
    warp = 1.0 + np.float32(amount) * r2
    sx, sy = cx + (xs - cx) * warp, cy + (ys - cy) * warp
    height, width = source.shape[:2]
    inside = ((sx >= 0.0) & (sx <= np.float32(width - 1))
              & (sy >= 0.0) & (sy <= np.float32(height - 1)))
    out = np.empty_like(source)
    for channel in range(3):
        plane = _sample(source[:, :, channel], sx, sy)
        out[:, :, channel] = np.where(inside, plane, np.float32(0.0))
    edge = np.clip(1.0 - np.float32(amount) * r2, 0.0, 1.0)
    return np.clip(out * edge[:, :, None], 0.0, 1.0).astype(np.float32)


@register_effect("crt", "CRT / scanlines", _PARAMS)
def crt(
    img: Image,
    params: dict,
    rng: np.random.Generator,
    *,
    mask: Image | None = None,
) -> Image:
    """Apply the static CRT finishing chain; seed and rng are accepted for interface parity.

    The phosphor pitch is specified in device pixels: doubling `output_width` doubles
    the period measured in output pixels while the visual pitch stays the same.

    `roll` is the one temporal knob: it scrolls the beam. Keep `curvature` fixed when
    animating, or the whole picture swells and shrinks like a zoom, not a tube.
    """
    cfg = _config(params)
    source = np.array(img, dtype=np.float32, copy=True, order="C")
    np.clip(source, 0.0, 1.0, out=source)
    height, width = source.shape[:2]
    coverage = _mask_plane(mask, (height, width)) if mask is not None else None
    ratio = (cfg["output_width"] / width) if cfg["output_width"] else 1.0
    out = source
    if cfg["bloom"] > 0.0:
        out = _bloom(out, cfg["bloom"])
    if cfg["scanline"] > 0.0:
        period_rows = max(1, int(round(_SCANLINE_ROWS * ratio)))
        out = out * _beam(height, cfg["scanline"], period_rows, cfg["roll"])[:, :, None]
    grid = _grid(height, width) if cfg["curvature"] > 0.0 or cfg["vignette"] > 0.0 else None
    if cfg["curvature"] > 0.0:
        assert grid is not None
        out = _curve(out, cfg["curvature"], grid)
    # Phosphor stripes live in screen space: apply them after the geometric warp so
    # out-of-bounds clamping cannot stretch the red/blue edge stripes into solid bands.
    if cfg["mask"] != "none":
        period = max(1, int(round(cfg["mask_scale"] * ratio)))
        out = out * _phosphor(height, width, cfg["mask"], period)
    if cfg["vignette"] > 0.0:
        assert grid is not None
        nx, ny = grid[0], grid[1]
        r2 = np.clip((nx * nx + ny * ny) / 2.0, 0.0, 1.0)
        out = out * (1.0 - np.float32(cfg["vignette"]) * r2)[:, :, None]
    np.clip(out, 0.0, 1.0, out=out)
    if coverage is not None:
        out = source * (1.0 - coverage[:, :, None]) + out * coverage[:, :, None]
    return np.ascontiguousarray(out, dtype=np.float32)
