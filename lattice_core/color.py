"""Colour conversions and image helpers shared by the whole application."""

from __future__ import annotations

import numpy as np
from numba import njit
from PIL import Image as PILImage

from lattice_core.gamma_table import (
    GAMMA_GRID_COUNT,
    GAMMA_GRID_START,
    GAMMA_GRID_STEP,
    GAMMA_LUT,
)
from lattice_core.types import RGB8, Image, Indices, Palette

_CHUNK_BYTES = 256 * 1024 * 1024
_BYTES_PER_PALETTE_ENTRY = 16

METRIC_SRGB = 0
METRIC_LINEAR = 1
METRIC_OKLAB = 2
METRIC_LAB2000 = 3
METRIC_CODES: dict[str, int] = {
    "srgb": METRIC_SRGB,
    "linear": METRIC_LINEAR,
    "oklab": METRIC_OKLAB,
    "lab2000": METRIC_LAB2000,
}


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


def nearest_index(img: Image, palette: Palette, metric: str = "srgb") -> Indices:
    """Return the index of the closest palette colour for every pixel, under metric."""
    code = metric_code(metric)
    if code == METRIC_SRGB:
        return _nearest_euclidean(img, palette)
    work = to_working_space(img, code)
    converted = to_working_space(palette, code)
    if code == METRIC_LAB2000:
        return _nearest_lab2000(work, converted)
    return _nearest_euclidean(work, converted)


def _nearest_euclidean(img: Image, palette: Palette) -> Indices:
    """Return the index of the closest palette colour by squared euclidean distance."""
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


def metric_code(metric: str | int) -> int:
    """Return the kernel code of a colour metric name, or pass an int code through."""
    if isinstance(metric, int):
        if metric not in METRIC_CODES.values():
            raise ValueError(f"unknown colour metric code: {metric}")
        return metric
    try:
        return METRIC_CODES[metric]
    except KeyError as exc:
        raise ValueError(f"unknown colour metric: {metric!r}") from exc


def to_working_space(img: Image, metric: str | int) -> Image:
    """Convert an sRGB image or palette to the space the metric compares in."""
    code = metric_code(metric)
    values = np.asarray(img, dtype=np.float32)
    if code == METRIC_SRGB:
        return np.ascontiguousarray(values)
    if code == METRIC_LINEAR:
        return srgb_to_linear(values)
    if code == METRIC_OKLAB:
        return srgb_to_oklab(values)
    return srgb_to_lab(values)


def srgb_to_oklab(img: Image) -> Image:
    """Convert sRGB values in [0, 1] to Oklab (Ottosson's matrices, no axis scaling)."""
    linear = srgb_to_linear(img)
    red, green, blue = linear[..., 0], linear[..., 1], linear[..., 2]
    long_ = np.float32(0.4122214708) * red + np.float32(0.5363325363) * green
    long_ = long_ + np.float32(0.0514459929) * blue
    medium = np.float32(0.2119034982) * red + np.float32(0.6806995451) * green
    medium = medium + np.float32(0.1073969566) * blue
    short = np.float32(0.0883024619) * red + np.float32(0.2817188376) * green
    short = short + np.float32(0.6299787005) * blue
    l_root, m_root, s_root = np.cbrt(long_), np.cbrt(medium), np.cbrt(short)
    lightness = np.float32(0.2104542553) * l_root + np.float32(0.7936177850) * m_root
    lightness = lightness - np.float32(0.0040720468) * s_root
    axis_a = np.float32(1.9779984951) * l_root - np.float32(2.4285922050) * m_root
    axis_a = axis_a + np.float32(0.4505937099) * s_root
    axis_b = np.float32(0.0259040371) * l_root + np.float32(0.7827717662) * m_root
    axis_b = axis_b - np.float32(0.8086757660) * s_root
    return np.ascontiguousarray(np.stack([lightness, axis_a, axis_b], axis=-1), dtype=np.float32)


def srgb_to_lab(img: Image) -> Image:
    """Convert sRGB values in [0, 1] to CIELAB under the D65 white point."""
    linear = srgb_to_linear(img)
    red, green, blue = linear[..., 0], linear[..., 1], linear[..., 2]
    x = np.float32(0.4124564) * red + np.float32(0.3575761) * green
    x = x + np.float32(0.1804375) * blue
    y = np.float32(0.2126729) * red + np.float32(0.7151522) * green
    y = y + np.float32(0.0721750) * blue
    z = np.float32(0.0193339) * red + np.float32(0.1191920) * green
    z = z + np.float32(0.9503041) * blue
    fx = _lab_curve(x / np.float32(0.95047))
    fy = _lab_curve(y)
    fz = _lab_curve(z / np.float32(1.08883))
    lightness = np.float32(116.0) * fy - np.float32(16.0)
    axis_a = np.float32(500.0) * (fx - fy)
    axis_b = np.float32(200.0) * (fy - fz)
    return np.ascontiguousarray(np.stack([lightness, axis_a, axis_b], axis=-1), dtype=np.float32)


def _lab_curve(values: np.ndarray) -> np.ndarray:
    """Apply the CIELAB companding function to normalised tristimulus values."""
    delta = np.float32(6.0 / 29.0)
    linear = values / (np.float32(3.0) * delta * delta) + np.float32(4.0 / 29.0)
    return np.where(values > delta**3, np.cbrt(values), linear)


@njit(cache=True)
def _ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """Return the CIEDE2000 colour difference between two CIELAB triples."""
    l1, a1, b1 = lab1[0], lab1[1], lab1[2]
    l2, a2, b2 = lab2[0], lab2[1], lab2[2]
    c1 = np.sqrt(a1 * a1 + b1 * b1)
    c2 = np.sqrt(a2 * a2 + b2 * b2)
    c_bar = (c1 + c2) / 2.0
    c_bar7 = c_bar**7
    g = 0.5 * (1.0 - np.sqrt(c_bar7 / (c_bar7 + 25.0**7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.sqrt(a1p * a1p + b1 * b1)
    c2p = np.sqrt(a2p * a2p + b2 * b2)
    h1p = _hue_degrees(b1, a1p)
    h2p = _hue_degrees(b2, a2p)
    delta_l = l2 - l1
    delta_c = c2p - c1p
    if c1p * c2p == 0.0:
        delta_h_angle = 0.0
    else:
        delta_h_angle = h2p - h1p
        if delta_h_angle > 180.0:
            delta_h_angle -= 360.0
        elif delta_h_angle < -180.0:
            delta_h_angle += 360.0
    delta_h = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(delta_h_angle) / 2.0)
    l_bar = (l1 + l2) / 2.0
    c_bar_p = (c1p + c2p) / 2.0
    if c1p * c2p == 0.0:
        h_bar = h1p + h2p
    else:
        h_bar = (h1p + h2p) / 2.0
        if abs(h1p - h2p) > 180.0:
            if h1p + h2p < 360.0:
                h_bar += 180.0
            else:
                h_bar -= 180.0
    t = (
        1.0
        - 0.17 * np.cos(np.radians(h_bar - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_bar))
        + 0.32 * np.cos(np.radians(3.0 * h_bar + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_bar - 63.0))
    )
    delta_theta = 30.0 * np.exp(-(((h_bar - 275.0) / 25.0) ** 2))
    c_bar_p7 = c_bar_p**7
    r_c = 2.0 * np.sqrt(c_bar_p7 / (c_bar_p7 + 25.0**7))
    l_offset = (l_bar - 50.0) ** 2
    s_l = 1.0 + (0.015 * l_offset) / np.sqrt(20.0 + l_offset)
    s_c = 1.0 + 0.045 * c_bar_p
    s_h = 1.0 + 0.015 * c_bar_p * t
    r_t = -np.sin(np.radians(2.0 * delta_theta)) * r_c
    term_l = delta_l / s_l
    term_c = delta_c / s_c
    term_h = delta_h / s_h
    return np.sqrt(term_l * term_l + term_c * term_c + term_h * term_h + r_t * term_c * term_h)


@njit(cache=True)
def _hue_degrees(b: float, a: float) -> float:
    """Return the hue angle in degrees, in [0, 360), and 0 when the chroma is zero."""
    if a == 0.0 and b == 0.0:
        return 0.0
    angle = np.degrees(np.arctan2(b, a))
    if angle < 0.0:
        angle += 360.0
    return angle


@njit(cache=True)
def _nearest_lab2000(lab_img: np.ndarray, palette_lab: np.ndarray) -> np.ndarray:
    """Return the CIEDE2000-nearest palette index for every pixel of a CIELAB image."""
    height, width = lab_img.shape[0], lab_img.shape[1]
    out = np.empty((height, width), dtype=np.int32)
    for y in range(height):
        for x in range(width):
            best = 0
            best_distance = np.inf
            for index in range(palette_lab.shape[0]):
                distance = _ciede2000(lab_img[y, x], palette_lab[index])
                if distance < best_distance:
                    best_distance = distance
                    best = index
            out[y, x] = best
    return out


def apply_palette(idx: Indices, palette: Palette) -> Image:
    """Map palette indices back to float32 colours."""
    return np.ascontiguousarray(palette[idx])


def adjust(
    img: Image, brightness: float, contrast: float, gamma: float, saturation: float = 0.0
) -> Image:
    """Apply gamma, contrast around 0.5, brightness and saturation, clipping to [0, 1]."""
    out = np.clip(img, 0.0, 1.0).astype(np.float32)
    if gamma != 1.0:
        # Discrete 8-bit curve from the committed table (see gamma_table.py):
        # index the grid, never call libm — so the render is bit-identical on
        # every platform. A gamma outside the grid clamps to the nearest curve.
        gi = int(round((float(gamma) - GAMMA_GRID_START) / GAMMA_GRID_STEP))
        gi = min(max(gi, 0), GAMMA_GRID_COUNT - 1)
        lut = np.asarray(GAMMA_LUT[gi], dtype=np.float32) / 255.0
        levels = np.clip(np.round(out * 255.0), 0, 255).astype(np.intp)
        out = lut[levels]
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
def nearest_index_px(r: float, g: float, b: float, palette: np.ndarray, metric: int = 0) -> int:
    """Return the index of the palette colour closest to (r, g, b); numba kernel.

    The pixel and the palette are expected in the working space of the metric: squared
    euclidean distance for codes 0 to 2, CIEDE2000 on CIELAB for code 3.
    """
    best = 0
    best_dist = np.inf
    if metric == 3:
        lab = np.empty(3, dtype=np.float64)
        lab[0], lab[1], lab[2] = r, g, b
        for i in range(palette.shape[0]):
            dist = _ciede2000(lab, palette[i])
            if dist < best_dist:
                best_dist = dist
                best = i
        return best
    for i in range(palette.shape[0]):
        dr = r - palette[i, 0]
        dg = g - palette[i, 1]
        db = b - palette[i, 2]
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best = i
    return best
