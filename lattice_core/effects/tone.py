"""Tone effects: gaussian blur, unsharp sharpen, glow, gaussian noise and posterize."""

from __future__ import annotations

import math

import numpy as np

from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

_BLUR_PARAMS = (ParamSpec("radius", "Radius", "float", 0.0, 0.0, 50.0, 0.5),)

_SHARPEN_PARAMS = (
    ParamSpec("amount", "Amount", "float", 1.0, 0.0, 3.0, 0.05),
    ParamSpec("radius", "Radius", "float", 1.5, 0.5, 10.0, 0.1),
)

_GLOW_PARAMS = (
    ParamSpec("threshold", "Threshold", "float", 0.7, 0.0, 1.0, 0.01),
    ParamSpec("radius", "Radius", "float", 10.0, 1.0, 50.0, 1.0),
    ParamSpec("intensity", "Intensity", "float", 1.0, 0.0, 3.0, 0.05),
)

_NOISE_PARAMS = (
    ParamSpec("amount", "Amount", "float", 0.1, 0.0, 1.0, 0.01),
    ParamSpec("monochrome", "Monochrome", "bool", True),
)

_POSTERIZE_PARAMS = (ParamSpec("levels", "Levels", "int", 4, 2, 32, 1),)

_RADIUS_TO_SIGMA = 3.0
_NOISE_SCALE = 0.5


def _as_float(img: Image) -> np.ndarray:
    """Return the image as a fresh float32 array without touching the input."""
    return np.array(img, dtype=np.float32, copy=True)


def _gaussian_kernel(sigma: float) -> np.ndarray:
    """Return a normalised 1-D gaussian kernel of radius ceil(3 * sigma)."""
    radius = max(1, int(math.ceil(3.0 * sigma)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(offsets * offsets) / np.float32(2.0 * sigma * sigma))
    return (kernel / kernel.sum()).astype(np.float32)


def _blur_axis(data: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    """Convolve data along one axis with kernel, replicating the edge samples."""
    radius = kernel.size // 2
    pad = [(0, 0)] * data.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(data, pad, mode="edge")
    length = data.shape[axis]
    out = np.zeros(data.shape, dtype=np.float32)
    for index, weight in enumerate(kernel):
        window = [slice(None)] * data.ndim
        window[axis] = slice(index, index + length)
        out += np.float32(weight) * padded[tuple(window)]
    return out


def _gaussian_blur(img: Image, sigma: float) -> Image:
    """Blur a float32 image with a separable gaussian kernel and replicated edges."""
    data = _as_float(img)
    if not sigma > 0.0:
        return data
    kernel = _gaussian_kernel(float(sigma))
    blurred = _blur_axis(data, kernel, 0)
    blurred = _blur_axis(blurred, kernel, 1)
    return np.clip(blurred, 0.0, 1.0).astype(np.float32)


def _sigma_from_radius(radius: float) -> float:
    """Map a user-facing blur radius to a gaussian sigma."""
    return max(0.0, float(radius)) / _RADIUS_TO_SIGMA


@register_effect("gaussian_blur", "Gaussian blur", _BLUR_PARAMS)
def gaussian_blur(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Blur the image with a gaussian kernel whose sigma is radius / 3."""
    return _gaussian_blur(img, _sigma_from_radius(params.get("radius", 0.0)))


@register_effect("sharpen", "Sharpen", _SHARPEN_PARAMS)
def sharpen(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Sharpen the image with an unsharp mask of the given amount and radius."""
    amount = float(params.get("amount", 1.0))
    data = _as_float(img)
    if amount <= 0.0:
        return data
    blurred = _gaussian_blur(data, _sigma_from_radius(params.get("radius", 1.5)))
    sharpened = data + np.float32(amount) * (data - blurred)
    return np.clip(sharpened, 0.0, 1.0).astype(np.float32)


@register_effect("glow", "Glow", _GLOW_PARAMS)
def glow(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Add a screen-blended bloom built from the bright pass of the image."""
    threshold = float(params.get("threshold", 0.7))
    intensity = float(params.get("intensity", 1.0))
    data = _as_float(img)
    if intensity <= 0.0:
        return data
    span = max(1.0 - threshold, 1e-6)
    bright = np.clip((data - np.float32(threshold)) / np.float32(span), 0.0, 1.0)
    halo = _gaussian_blur(bright, _sigma_from_radius(params.get("radius", 10.0)))
    layer = np.clip(np.float32(intensity) * halo, 0.0, 1.0)
    screened = 1.0 - (1.0 - data) * (1.0 - layer)
    return np.clip(screened, 0.0, 1.0).astype(np.float32)


@register_effect("noise", "Noise", _NOISE_PARAMS)
def noise(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Add gaussian noise of standard deviation amount / 2, shared or per channel."""
    amount = float(params.get("amount", 0.1))
    data = _as_float(img)
    if amount <= 0.0:
        return data
    channels = data.shape[2] if data.ndim == 3 else 1
    shape = data.shape[:2] + ((1,) if bool(params.get("monochrome", True)) else (channels,))
    delta = rng.standard_normal(shape).astype(np.float32) * np.float32(amount * _NOISE_SCALE)
    return np.clip(data + delta, 0.0, 1.0).astype(np.float32)


@register_effect("posterize", "Posterize", _POSTERIZE_PARAMS)
def posterize(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Quantise every channel to at most `levels` evenly spaced values in [0, 1]."""
    levels = max(2, int(params.get("levels", 4)))
    data = _as_float(img)
    step = np.float32(levels - 1)
    quantised = np.floor(data * step + np.float32(0.5)) / step
    return np.clip(quantised, 0.0, 1.0).astype(np.float32)
