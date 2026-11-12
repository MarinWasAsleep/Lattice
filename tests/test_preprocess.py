"""Tests for the source pre-processing package: Pixel Snapper and descreen (CONTRACT §23)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_dither.preprocess import descreen, detect_grid, snap_to_grid

_LEVELS = 4
_SCREEN_CYCLES_X = 16.4
_SCREEN_CYCLES_Y = 12.3
_SCREEN_AMPLITUDE = 0.25


def _pixel_art(size: int = 16, seed: int = 7) -> np.ndarray:
    """Return a deterministic pixel-art image drawn from a four-level grey palette."""
    rng = np.random.default_rng(seed)
    steps = rng.integers(0, _LEVELS, size=(size, size)).astype(np.float32)
    grey = steps / np.float32(_LEVELS - 1)
    return np.ascontiguousarray(np.repeat(grey[:, :, None], 3, axis=2))


def _upscale(img: np.ndarray, factor: int) -> np.ndarray:
    """Return img upscaled by an integer factor with nearest neighbour."""
    return np.ascontiguousarray(np.repeat(np.repeat(img, factor, axis=0), factor, axis=1))


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Return img blurred with a separable gaussian kernel, replicating the edges."""
    radius = max(1, int(3.0 * sigma))
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(offsets * offsets) / np.float32(2.0 * sigma * sigma))
    kernel = kernel / kernel.sum()
    out = np.asarray(img, dtype=np.float32)
    for axis in (0, 1):
        pad = [(radius, radius) if index == axis else (0, 0) for index in range(out.ndim)]
        padded = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for index, weight in enumerate(kernel):
            window = [slice(None)] * out.ndim
            window[axis] = slice(index, index + out.shape[axis])
            acc += weight * padded[tuple(window)]
        out = acc
    return out.astype(np.float32)


def _photo(height: int = 128, width: int = 128, seed: int = 5) -> np.ndarray:
    """Return a smooth, aperiodic, photo-like image with no periodic screen."""
    rng = np.random.default_rng(seed)
    noise = rng.random((height, width, 3), dtype=np.float32)
    smooth = _blur(noise, 3.0)
    scaled = 0.5 + 0.9 * (smooth - smooth.mean()) / max(float(smooth.std()), 1e-6) * 0.18
    return np.clip(scaled, 0.02, 0.98).astype(np.float32)


def _screened(base: np.ndarray, amplitude: float = _SCREEN_AMPLITUDE) -> np.ndarray:
    """Return base with a rotated halftone screen of the given amplitude laid over it."""
    height, width = base.shape[:2]
    rows, cols = np.mgrid[0:height, 0:width].astype(np.float64)
    phase = 2.0 * np.pi * (_SCREEN_CYCLES_X * cols / width + _SCREEN_CYCLES_Y * rows / height)
    return np.clip(base + amplitude * np.cos(phase)[:, :, None], 0.0, 1.0).astype(np.float32)


def _luminance(img: np.ndarray) -> np.ndarray:
    """Return the luminance plane of an RGB image as float64."""
    work = np.asarray(img, dtype=np.float64)
    return 0.299 * work[:, :, 0] + 0.587 * work[:, :, 1] + 0.114 * work[:, :, 2]


def _spectrum(img: np.ndarray) -> np.ndarray:
    """Return the DC-centred magnitude spectrum of the image luminance."""
    return np.abs(np.fft.fftshift(np.fft.fft2(_luminance(img))))


def _dominant_peak(img: np.ndarray, dc_radius: int = 6) -> tuple[int, int]:
    """Return the (row, col) offset of the strongest off-centre spectral peak."""
    spectrum = _spectrum(img)
    height, width = spectrum.shape
    centre_y, centre_x = height // 2, width // 2
    work = spectrum.copy()
    rows, cols = np.ogrid[:height, :width]
    work[(rows - centre_y) ** 2 + (cols - centre_x) ** 2 <= dc_radius**2] = 0.0
    row, col = np.unravel_index(int(np.argmax(work)), work.shape)
    return int(row) - centre_y, int(col) - centre_x


def _peak_energy(img: np.ndarray, row: int, col: int, radius: int = 3) -> float:
    """Return the spectral energy in a square window around one frequency."""
    spectrum = _spectrum(img)
    height, width = spectrum.shape
    centre_y, centre_x = height // 2, width // 2
    window = spectrum[
        centre_y + row - radius : centre_y + row + radius + 1,
        centre_x + col - radius : centre_x + col + radius + 1,
    ]
    return float(np.sum(window**2))


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    """Return the Pearson correlation of two images' luminance planes."""
    first = _luminance(left).ravel()
    second = _luminance(right).ravel()
    first = first - first.mean()
    second = second - second.mean()
    return float(np.dot(first, second) / np.sqrt(np.dot(first, first) * np.dot(second, second)))


def test_detect_grid_finds_a_four_times_upscale() -> None:
    """A 4x nearest-neighbour upscale is reported as a 4x4 lattice at offset zero."""
    upscaled = _upscale(_pixel_art(), 4)
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(upscaled)
    assert (cell_w, cell_h, offset_x, offset_y) == (4, 4, 0, 0)
    assert confidence > 0.8


def test_snap_to_grid_recovers_the_original_exactly() -> None:
    """Snapping a 4x upscale returns the original pixel art, value for value."""
    original = _pixel_art()
    upscaled = _upscale(original, 4)
    recovered = snap_to_grid(upscaled, detect_grid(upscaled)[:4])
    assert recovered.shape == original.shape
    assert np.array_equal(recovered, original)


@pytest.mark.parametrize("factor", [2, 3, 5, 6])
def test_detect_grid_scales_with_the_upscale_factor(factor: int) -> None:
    """The reported cell follows the real upscale factor, so confidence is measured."""
    original = _pixel_art()
    upscaled = _upscale(original, factor)
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(upscaled)
    assert (cell_w, cell_h, offset_x, offset_y) == (factor, factor, 0, 0)
    assert confidence > 0.8
    assert np.array_equal(snap_to_grid(upscaled, (cell_w, cell_h, offset_x, offset_y)), original)


def test_detect_grid_reports_a_non_zero_offset() -> None:
    """A lattice that does not start at the origin reports its real offset."""
    original = _pixel_art()
    padded = np.pad(_upscale(original, 4), ((2, 0), (2, 0), (0, 0)), mode="edge")
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(padded)
    assert (cell_w, cell_h, offset_x, offset_y) == (4, 4, 2, 2)
    assert confidence > 0.8
    assert np.array_equal(snap_to_grid(padded, (cell_w, cell_h, offset_x, offset_y)), original)


def test_detect_grid_rejects_a_smooth_photo() -> None:
    """A smooth photo scores below the 0.5 gate, so the caller leaves it untouched."""
    photo = _photo()
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(photo)
    assert confidence < 0.5
    assert 0.0 <= confidence <= 1.0
    assert cell_w >= 1 and cell_h >= 1


def test_detect_grid_confidence_drops_when_the_lattice_is_broken() -> None:
    """Jittering every pixel destroys the lattice and the confidence with it."""
    upscaled = _upscale(_pixel_art(), 4)
    rng = np.random.default_rng(19)
    jitter = rng.normal(0.0, 0.25, size=upscaled.shape).astype(np.float32)
    broken = np.clip(upscaled + jitter, 0.0, 1.0).astype(np.float32)
    assert detect_grid(upscaled)[4] > 0.8
    assert detect_grid(broken)[4] < 0.5


def test_descreen_reduces_the_screen_peak() -> None:
    """The notch removes at least 80 % of the peak energy and keeps the mean within 2 %."""
    screened = _screened(_photo())
    row, col = _dominant_peak(screened)
    assert abs(abs(row) - _SCREEN_CYCLES_Y) <= 1.5
    assert abs(abs(col) - _SCREEN_CYCLES_X) <= 1.5
    before = _peak_energy(screened, row, col)
    cleaned = descreen(screened)
    after = _peak_energy(cleaned, row, col)
    assert after <= 0.2 * before
    assert abs(float(cleaned.mean()) - float(screened.mean())) <= 0.02 * abs(float(screened.mean()))


def test_descreen_keeps_the_underlying_image() -> None:
    """The screen goes away without dragging the low-frequency content with it."""
    base = _photo()
    screened = _screened(base)
    cleaned = descreen(screened)
    assert _correlation(screened, base) < 0.7
    assert _correlation(cleaned, base) > 0.9


def test_descreen_leaves_a_photo_alone() -> None:
    """A photo with no periodic screen has no dominant peak, so nothing is notched."""
    photo = _photo()
    assert np.array_equal(descreen(photo), photo)


def test_descreen_strength_zero_is_the_identity() -> None:
    """strength=0 returns the input unchanged, bit for bit."""
    screened = _screened(_photo())
    assert np.array_equal(descreen(screened, strength=0.0), screened)


def test_descreen_strength_blends_between_the_two_ends() -> None:
    """A half strength result removes part of the screen, between the two ends."""
    screened = _screened(_photo())
    row, col = _dominant_peak(screened)
    half = descreen(screened, strength=0.5)
    full = descreen(screened, strength=1.0)
    assert not np.array_equal(half, screened)
    assert not np.array_equal(half, full)
    assert _peak_energy(full, row, col) < _peak_energy(half, row, col)
    assert _peak_energy(half, row, col) < _peak_energy(screened, row, col)


def test_descreen_does_not_mutate_its_input() -> None:
    """The caller's array is left untouched."""
    screened = _screened(_photo())
    before = screened.copy()
    descreen(screened)
    assert np.array_equal(screened, before)


@pytest.mark.parametrize("shape", [(1, 1), (37, 23)])
def test_small_inputs_do_not_raise(shape: tuple[int, int]) -> None:
    """Tiny and odd-sized images go through all three entry points without raising."""
    height, width = shape
    rng = np.random.default_rng(23)
    img = rng.random((height, width, 3), dtype=np.float32)
    cell_w, cell_h, offset_x, offset_y, confidence = detect_grid(img)
    assert cell_w >= 1 and cell_h >= 1
    assert 0.0 <= confidence <= 1.0
    snapped = snap_to_grid(img, (cell_w, cell_h, offset_x, offset_y))
    assert snapped.ndim == 3 and snapped.shape[2] == 3
    cleaned = descreen(img)
    assert cleaned.shape == img.shape
    assert cleaned.dtype == np.float32


def test_snap_to_grid_with_a_degenerate_grid_is_a_no_op() -> None:
    """A 1x1 grid and a grid wider than the image both return an unchanged copy."""
    img = _upscale(_pixel_art(), 4)
    assert np.array_equal(snap_to_grid(img, (1, 1, 0, 0)), img)
    assert np.array_equal(snap_to_grid(img, (128, 128, 0, 0)), img)
