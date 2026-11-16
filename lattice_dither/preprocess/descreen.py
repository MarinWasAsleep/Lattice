"""Descreen: notch a periodic halftone screen out of the spectrum (CONTRACT §23)."""

from __future__ import annotations

import numpy as np

from lattice_core.types import Image
from lattice_dither.preprocess.grid import _luminance

_NOTCH_RADIUS = 4
_DC_RADIUS = _NOTCH_RADIUS + 2
_MAX_PEAKS = 6
_PEAK_RATIO = 10.0
_PEAK_FRACTION = 0.1
_PROMINENCE = 20.0
_RING_INNER = _NOTCH_RADIUS + 1
_RING_OUTER = _NOTCH_RADIUS + 5
_MIN_SIDE = 4


def _centred_spectrum(plane: np.ndarray) -> np.ndarray:
    """Return the DC-centred complex spectrum of a 2-D plane."""
    return np.fft.fftshift(np.fft.fft2(plane))


def _local_maxima(magnitude: np.ndarray) -> np.ndarray:
    """Return a mask of the bins that are the maximum of their 3x3 neighbourhood."""
    peak = np.ones(magnitude.shape, dtype=bool)
    for shift_y in (-1, 0, 1):
        for shift_x in (-1, 0, 1):
            if shift_y == 0 and shift_x == 0:
                continue
            rolled = np.roll(np.roll(magnitude, shift_y, axis=0), shift_x, axis=1)
            peak &= magnitude >= rolled
    return peak


def _ring_median(magnitude: np.ndarray, row: int, col: int) -> float:
    """Return the median magnitude of the annulus around one bin, wrapping at the edges."""
    height, width = magnitude.shape
    offsets = np.arange(-_RING_OUTER, _RING_OUTER + 1)
    window = magnitude[np.ix_((row + offsets) % height, (col + offsets) % width)]
    distance = np.hypot(*np.meshgrid(offsets, offsets, indexing="ij"))
    ring = window[(distance >= _RING_INNER) & (distance <= _RING_OUTER)]
    return float(np.median(ring)) if ring.size else 0.0


def _find_peaks(magnitude: np.ndarray) -> list[tuple[int, int]]:
    """Return the strongest off-centre spectral peaks as (row, col) indices.

    A bin qualifies only if it is a local maximum, sits outside the DC
    neighbourhood, is a sizeable fraction of the strongest off-centre bin and
    stands well clear of the annulus around it: a halftone screen is a narrow
    spike, whereas the low-frequency content of a photograph is a broad plateau
    and is left alone.
    """
    height, width = magnitude.shape
    centre_y, centre_x = height // 2, width // 2
    work = magnitude.copy()
    rows, cols = np.ogrid[:height, :width]
    work[(rows - centre_y) ** 2 + (cols - centre_x) ** 2 <= _DC_RADIUS**2] = 0.0
    positive = work[work > 0.0]
    if positive.size == 0:
        return []
    threshold = max(float(np.median(positive)) * _PEAK_RATIO, float(work.max()) * _PEAK_FRACTION)
    candidates = np.argwhere(_local_maxima(work) & (work >= threshold))
    scored = []
    for row, col in candidates:
        value = float(work[row, col])
        background = _ring_median(work, int(row), int(col))
        if background <= 0.0 or value >= _PROMINENCE * background:
            scored.append((value, int(row), int(col)))
    scored.sort(reverse=True)
    return [(row, col) for _, row, col in scored[:_MAX_PEAKS]]


def _notch_mask(shape: tuple[int, int], peaks: list[tuple[int, int]]) -> np.ndarray:
    """Return a mask covering a disc around every peak and its conjugate."""
    height, width = shape
    mask = np.zeros(shape, dtype=bool)
    rows, cols = np.ogrid[:height, :width]
    for row, col in peaks:
        mirror = ((height - row) % height, (width - col) % width)
        for centre_row, centre_col in ((row, col), mirror):
            mask |= (rows - centre_row) ** 2 + (cols - centre_col) ** 2 <= _NOTCH_RADIUS**2
    return mask


def _notch_plane(plane: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return the plane with the masked spectral bins removed."""
    spectrum = _centred_spectrum(plane)
    spectrum[mask] = 0.0
    return np.real(np.fft.ifft2(np.fft.ifftshift(spectrum))).astype(np.float32)


def _median3(plane: np.ndarray) -> np.ndarray:
    """Return a 3x3 median filtered copy of a 2-D plane, replicating the edges."""
    height, width = plane.shape
    padded = np.pad(plane, 1, mode="edge")
    stack = np.empty((9, height, width), dtype=np.float32)
    index = 0
    for shift_y in range(3):
        for shift_x in range(3):
            stack[index] = padded[shift_y : shift_y + height, shift_x : shift_x + width]
            index += 1
    return np.median(stack, axis=0).astype(np.float32)


def _filter_channels(work: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return the image with the notch and the light median applied to every channel."""
    if work.ndim == 2:
        return _median3(_notch_plane(work, mask))
    out = np.empty(work.shape, dtype=np.float32)
    for channel in range(work.shape[2]):
        out[:, :, channel] = _median3(_notch_plane(work[:, :, channel], mask))
    return out


def descreen(img: Image, *, strength: float = 1.0) -> Image:
    """Suppress a periodic halftone screen; strength blends from the original to the result.

    The dominant off-centre peaks of the luminance spectrum are notched out of
    every channel, then a 3x3 median removes what is left of the screen.
    ``strength`` is clamped to 0..1; 0 returns an unchanged copy and the result is
    clipped to 0..1.
    """
    work = np.asarray(img, dtype=np.float32)
    if work.ndim not in (2, 3):
        raise ValueError("image must be HxW or HxWx3")
    original = np.array(work, dtype=np.float32, copy=True)
    amount = float(np.clip(strength, 0.0, 1.0))
    if amount <= 0.0 or min(work.shape[:2]) < _MIN_SIDE:
        return original
    plane = _luminance(work)
    peaks = _find_peaks(np.abs(_centred_spectrum(plane)))
    if not peaks:
        return original
    filtered = _filter_channels(work, _notch_mask(plane.shape, peaks))
    blended = original + np.float32(amount) * (filtered - original)
    return np.clip(blended, 0.0, 1.0).astype(np.float32)
