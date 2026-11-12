"""Glitch effects: chromatic aberration, RGB shift, JPEG glitch and scanlines."""

from __future__ import annotations

import io
import warnings

import numpy as np
from PIL import Image as PILImage

from lattice_dither.core.color import to_float, to_pil, to_rgb8
from lattice_dither.core.registry import register_effect
from lattice_dither.core.types import Image, ParamSpec

_SOS_MARKER = b"\xff\xda"
_MAX_DECODE_ATTEMPTS = 8

_CHROMATIC_PARAMS = (ParamSpec("amount", "Amount (px)", "float", 4.0, 0.0, 50.0, 0.5),)

_RGB_SHIFT_PARAMS = (
    ParamSpec("r_x", "Red X", "int", 0, -100, 100, 1),
    ParamSpec("r_y", "Red Y", "int", 0, -100, 100, 1),
    ParamSpec("b_x", "Blue X", "int", 0, -100, 100, 1),
    ParamSpec("b_y", "Blue Y", "int", 0, -100, 100, 1),
)

_JPEG_PARAMS = (
    ParamSpec("quality", "Quality", "int", 20, 1, 95, 1),
    ParamSpec("corruptions", "Corruptions", "int", 5, 0, 50, 1),
)

_SCANLINE_PARAMS = (
    ParamSpec("spacing", "Spacing", "int", 3, 2, 16, 1),
    ParamSpec("thickness", "Thickness", "int", 1, 1, 8, 1),
    ParamSpec("darkness", "Darkness", "float", 0.5, 0.0, 1.0, 0.05),
)


def _copy(img: Image) -> Image:
    """Return a contiguous float32 copy of img, clipped to [0, 1]."""
    out = np.array(img, dtype=np.float32, copy=True)
    return np.clip(out, 0.0, 1.0, out=out)


def _radial_offsets(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Return float32 (1, W) x and (H, 1) y offsets from the image centre."""
    centre_x = np.float32((width - 1) / 2.0)
    centre_y = np.float32((height - 1) / 2.0)
    xs = np.arange(width, dtype=np.float32)[None, :] - centre_x
    ys = np.arange(height, dtype=np.float32)[:, None] - centre_y
    return xs, ys


def _sample_channel(channel: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2D channel at broadcastable float coordinates, clamping to the edges."""
    height, width = channel.shape
    x0 = np.floor(xs).astype(np.intp)
    y0 = np.floor(ys).astype(np.intp)
    fx = (xs - x0).astype(np.float32)
    fy = (ys - y0).astype(np.float32)
    np.clip(x0, 0, width - 1, out=x0)
    np.clip(y0, 0, height - 1, out=y0)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    top = channel[y0, x0] * (1.0 - fx)
    top += channel[y0, x1] * fx
    bottom = channel[y1, x0] * (1.0 - fx)
    bottom += channel[y1, x1] * fx
    bottom *= fy
    top *= 1.0 - fy
    top += bottom
    return top


@register_effect("chromatic_aberration", "Chromatic Aberration", _CHROMATIC_PARAMS)
def chromatic_aberration(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Scale the red channel outward and the blue channel inward from the centre."""
    amount = float(params["amount"])
    if amount == 0.0:
        return _copy(img)
    source = np.asarray(img, dtype=np.float32)
    height, width = source.shape[:2]
    centre_y = (height - 1) / 2.0
    centre_x = (width - 1) / 2.0
    dx, dy = _radial_offsets(height, width)
    radius = float(np.hypot(max(centre_x, 0.5), max(centre_y, 0.5)))
    scale = amount / radius
    out = np.empty((height, width, 3), dtype=np.float32)
    out[:, :, 0] = _sample_channel(
        source[:, :, 0],
        np.float32(centre_x) + dx * np.float32(1.0 + scale),
        np.float32(centre_y) + dy * np.float32(1.0 + scale),
    )
    out[:, :, 1] = source[:, :, 1]
    out[:, :, 2] = _sample_channel(
        source[:, :, 2],
        np.float32(centre_x) + dx * np.float32(1.0 - scale),
        np.float32(centre_y) + dy * np.float32(1.0 - scale),
    )
    return np.clip(out, 0.0, 1.0, out=out)


@register_effect("rgb_shift", "RGB Shift", _RGB_SHIFT_PARAMS)
def rgb_shift(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Shift the red and blue channels by whole pixels, replicating the edges."""
    red_x = int(params["r_x"])
    red_y = int(params["r_y"])
    blue_x = int(params["b_x"])
    blue_y = int(params["b_y"])
    if not (red_x or red_y or blue_x or blue_y):
        return _copy(img)
    source = np.asarray(img, dtype=np.float32)
    height, width = source.shape[:2]
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    out = np.empty((height, width, 3), dtype=np.float32)
    out[:, :, 1] = source[:, :, 1]
    for channel, (shift_x, shift_y) in ((0, (red_x, red_y)), (2, (blue_x, blue_y))):
        src_rows = np.clip(rows - shift_y, 0, height - 1)
        src_cols = np.clip(cols - shift_x, 0, width - 1)
        out[:, :, channel] = source[src_rows, src_cols, channel]
    return np.clip(out, 0.0, 1.0, out=out)


def _encode_jpeg(rgb8: np.ndarray, quality: int) -> bytes:
    """Encode a uint8 RGB array as JPEG bytes with the given quality."""
    buffer = io.BytesIO()
    to_pil(rgb8).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _payload_start(data: bytes) -> int:
    """Return the offset of the entropy-coded data after the SOS marker, or -1."""
    index = data.find(_SOS_MARKER)
    if index < 0 or index + 4 > len(data):
        return -1
    length = int.from_bytes(data[index + 2 : index + 4], "big")
    start = index + 2 + length
    return start if start < len(data) else -1


def _corrupt(data: bytes, count: int, rng: np.random.Generator) -> bytes:
    """Overwrite count random bytes after the SOS marker with random values."""
    start = _payload_start(data)
    if count <= 0 or start < 0:
        return data
    buffer = bytearray(data)
    positions = rng.integers(start, len(buffer), size=count)
    values = rng.integers(0, 256, size=count)
    for position, value in zip(positions.tolist(), values.tolist(), strict=True):
        buffer[position] = value
    return bytes(buffer)


def _decode_jpeg(data: bytes) -> Image | None:
    """Decode JPEG bytes to a float32 image, returning None when decoding fails."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with PILImage.open(io.BytesIO(data)) as pil:
                pil.load()
                return to_float(pil)
    except Exception:
        return None


@register_effect("jpeg_glitch", "JPEG Glitch", _JPEG_PARAMS)
def jpeg_glitch(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Round-trip the image through JPEG with random byte corruption after the SOS marker."""
    quality = int(params["quality"])
    count = max(0, int(params["corruptions"]))
    source = np.asarray(img, dtype=np.float32)
    try:
        data = _encode_jpeg(to_rgb8(source), quality)
    except Exception:
        return _copy(source)
    for _ in range(_MAX_DECODE_ATTEMPTS):
        decoded = _decode_jpeg(_corrupt(data, count, rng) if count > 0 else data)
        if decoded is not None:
            return np.ascontiguousarray(np.clip(decoded, 0.0, 1.0), dtype=np.float32)
        if count == 0:
            break
        count //= 2
    return _copy(source)


@register_effect("scanlines", "Scanlines", _SCANLINE_PARAMS)
def scanlines(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Darken horizontal bands of thickness rows every spacing rows."""
    spacing = max(1, int(params["spacing"]))
    thickness = max(1, int(params["thickness"]))
    darkness = float(params["darkness"])
    if darkness <= 0.0:
        return _copy(img)
    source = np.asarray(img, dtype=np.float32)
    height = source.shape[0]
    out = np.array(source, dtype=np.float32, copy=True)
    band = (np.arange(height) % spacing) < thickness
    out[band] *= np.float32(1.0 - darkness)
    return np.clip(out, 0.0, 1.0, out=out)
