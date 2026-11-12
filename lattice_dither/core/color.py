"""Colour conversions and image helpers shared by the whole application."""

from __future__ import annotations

import numpy as np
from numba import njit
from PIL import Image as PILImage

from lattice_dither.core.types import RGB8, Image, Indices, Palette

_CHUNK_BYTES = 256 * 1024 * 1024
_BYTES_PER_PALETTE_ENTRY = 16


def to_float(img: PILImage.Image) -> Image:
    """Convert any Pillow image to float32 RGB in [0, 1], compositing alpha over white."""
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = PILImage.alpha_composite(background, rgba).convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return np.ascontiguousarray(np.asarray(img, dtype=np.float32) / 255.0)


def to_rgb8(img: Image) -> RGB8:
    """Convert a float32 image in [0, 1] to uint8, rounding half up and clipping."""
    return np.floor(np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def to_pil(rgb8: RGB8) -> PILImage.Image:
    """Wrap a uint8 RGB array in a Pillow image."""
    return PILImage.fromarray(np.ascontiguousarray(rgb8), "RGB")


def luminance(img: Image) -> np.ndarray:
    """Return the sRGB luminance of every pixel as a float32 (H, W) array."""
    return (0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2]).astype(
        np.float32
    )


def nearest_index(img: Image, palette: Palette) -> Indices:
    """Return the index of the closest palette colour for every pixel."""
    height, width = img.shape[:2]
    flat = np.ascontiguousarray(img, dtype=np.float32).reshape(-1, 3)
    k = palette.shape[0]
    step = max(1, _CHUNK_BYTES // (k * _BYTES_PER_PALETTE_ENTRY))
    out = np.empty(flat.shape[0], dtype=np.int32)
    for start in range(0, flat.shape[0], step):
        chunk = flat[start : start + step]
        diff = chunk[:, None, :] - palette[None, :, :]
        dist = np.einsum("ijk,ijk->ij", diff, diff)
        out[start : start + step] = np.argmin(dist, axis=1)
    return out.reshape(height, width)


def apply_palette(idx: Indices, palette: Palette) -> Image:
    """Map palette indices back to float32 colours."""
    return np.ascontiguousarray(palette[idx])


def adjust(
    img: Image, brightness: float, contrast: float, gamma: float, saturation: float = 0.0
) -> Image:
    """Apply gamma, contrast around 0.5, brightness and saturation, clipping to [0, 1]."""
    out = np.clip(img, 0.0, 1.0).astype(np.float32)
    if gamma != 1.0:
        out = np.power(out, np.float32(1.0 / gamma))
    if contrast != 0.0:
        out = (out - 0.5) * np.float32(1.0 + contrast) + 0.5
    if brightness != 0.0:
        out = out + np.float32(brightness)
    out = np.clip(out, 0.0, 1.0).astype(np.float32)
    if saturation != 0.0:
        out = _saturate(out, saturation)
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0).astype(np.float32))


def srgb_to_linear(img: Image) -> Image:
    """Decode sRGB-encoded values in [0, 1] to linear light with the exact transfer function."""
    values = np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0)
    low = values / np.float32(12.92)
    high = np.power((values + np.float32(0.055)) / np.float32(1.055), np.float32(2.4))
    return np.ascontiguousarray(np.where(values <= 0.04045, low, high), dtype=np.float32)


def linear_to_srgb(img: Image) -> Image:
    """Encode linear-light values in [0, 1] back to sRGB with the exact transfer function."""
    values = np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0)
    low = values * np.float32(12.92)
    high = np.float32(1.055) * np.power(values, np.float32(1.0 / 2.4)) - np.float32(0.055)
    return np.ascontiguousarray(np.where(values <= 0.0031308, low, high), dtype=np.float32)


def _saturate(img: Image, saturation: float) -> Image:
    """Scale every pixel's chroma away from its luminance in linear light.

    ``saturation = -1`` collapses to grey, ``0`` is the identity and ``1`` doubles the
    distance to the luminance. The chroma is scaled rather than normalised so that the
    control stays smooth on nearly grey pixels.
    """
    linear = srgb_to_linear(img)
    lum = (
        np.float32(0.2126) * linear[:, :, 0]
        + np.float32(0.7152) * linear[:, :, 1]
        + np.float32(0.0722) * linear[:, :, 2]
    )[:, :, None]
    scaled = lum + (linear - lum) * np.float32(1.0 + saturation)
    return linear_to_srgb(scaled)


def auto_levels(img: Image, low: float = 0.5, high: float = 99.5) -> Image:
    """Stretch each channel between its low and high percentiles, clipping to [0, 1]."""
    out = np.array(img, dtype=np.float32, copy=True)
    for channel in range(3):
        plane = out[:, :, channel]
        bottom, top = np.percentile(plane, [low, high])
        if top > bottom:
            out[:, :, channel] = (plane - bottom) / (top - bottom)
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)


def gaussian_blur(img: Image, sigma: float) -> Image:
    """Blur img with a separable Gaussian of the given sigma; sigma <= 0 is a no-op."""
    if sigma <= 0.0:
        return np.ascontiguousarray(img, dtype=np.float32)
    radius = max(1, int(np.ceil(3.0 * float(sigma))))
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (offsets / np.float32(sigma)) ** 2)
    kernel = kernel / kernel.sum()
    return _convolve_axis(_convolve_axis(img, kernel, 0), kernel, 1)


def _convolve_axis(img: Image, kernel: np.ndarray, axis: int) -> Image:
    """Convolve img along one axis with a 1-D kernel, replicating the edges."""
    radius = kernel.shape[0] // 2
    padding = [(0, 0)] * img.ndim
    padding[axis] = (radius, radius)
    padded = np.pad(np.asarray(img, dtype=np.float32), padding, mode="edge")
    out = np.zeros(img.shape, dtype=np.float32)
    for index, weight in enumerate(kernel):
        window = [slice(None)] * img.ndim
        window[axis] = slice(index, index + img.shape[axis])
        out += weight * padded[tuple(window)]
    return np.ascontiguousarray(out, dtype=np.float32)


def downscale(img: Image, factor: int) -> Image:
    """Average factor x factor blocks, replicating the edge when the size is not divisible."""
    if factor <= 1:
        return np.ascontiguousarray(img, dtype=np.float32)
    height, width = img.shape[:2]
    pad_y = (-height) % factor
    pad_x = (-width) % factor
    work = img
    if pad_y or pad_x:
        work = np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
    out_h = work.shape[0] // factor
    out_w = work.shape[1] // factor
    blocks = work.reshape(out_h, factor, out_w, factor, 3)
    return np.ascontiguousarray(blocks.mean(axis=(1, 3), dtype=np.float32))


def upscale_nearest(img: Image, factor: int, shape: tuple[int, int]) -> Image:
    """Repeat every pixel factor times, then crop to shape."""
    if factor <= 1:
        return np.ascontiguousarray(img[: shape[0], : shape[1]], dtype=np.float32)
    out = np.repeat(np.repeat(img, factor, axis=0), factor, axis=1)
    return np.ascontiguousarray(out[: shape[0], : shape[1]], dtype=np.float32)


@njit(cache=True)
def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray) -> int:
    """Return the index of the palette colour closest to (r, g, b); numba kernel."""
    best = 0
    best_dist = np.inf
    for i in range(palette.shape[0]):
        dr = r - palette[i, 0]
        dg = g - palette[i, 1]
        db = b - palette[i, 2]
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best = i
    return best
