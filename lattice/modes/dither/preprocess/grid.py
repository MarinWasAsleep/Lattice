"""Pixel Snapper: detect an upscaled pixel-art lattice and snap onto it (CONTRACT §23)."""

from __future__ import annotations

import numpy as np

from lattice.types import Image

_MIN_CELL = 2
_MAX_CELL = 64
_MIN_EDGE_ENERGY = 1e-6
_TIE = 1e-6


def _luminance(img: Image) -> np.ndarray:
    """Return the float32 luminance plane of a grey or RGB image."""
    work = np.asarray(img, dtype=np.float32)
    if work.ndim == 2:
        return work
    if work.ndim != 3 or work.shape[2] < 3:
        raise ValueError("image must be HxW or HxWx3")
    red, green, blue = work[:, :, 0], work[:, :, 1], work[:, :, 2]
    return (0.299 * red + 0.587 * green + 0.114 * blue).astype(np.float32)


def _edge_profile(lum: np.ndarray, axis: int) -> np.ndarray:
    """Return the absolute first difference along axis, summed over the other axis."""
    return np.abs(np.diff(lum, axis=axis)).sum(axis=1 - axis, dtype=np.float64)


def _phase_confidence(profile: np.ndarray, cell: int) -> tuple[float, int]:
    """Return the normalised peak height of the phase histogram and the peak phase."""
    length = profile.size
    if cell < _MIN_CELL or cell > length // 2:
        return 0.0, 0
    folded = np.bincount(np.arange(length) % cell, weights=profile, minlength=cell)
    total = float(folded.sum())
    if total <= 0.0:
        return 0.0, 0
    phase = int(np.argmax(folded))
    uniform = 1.0 / cell
    concentration = float(folded[phase]) / total
    return max(0.0, (concentration - uniform) / (1.0 - uniform)), phase


def _best_cell(profile: np.ndarray) -> tuple[int, int, float]:
    """Return the (cell, phase, confidence) of the strongest lattice along one axis."""
    limit = min(_MAX_CELL, profile.size // 2)
    if limit < _MIN_CELL or float(profile.sum()) <= _MIN_EDGE_ENERGY:
        return 1, 0, 0.0
    scores = []
    for cell in range(_MIN_CELL, limit + 1):
        confidence, phase = _phase_confidence(profile, cell)
        scores.append((cell, phase, confidence))
    best = max(score[2] for score in scores)
    if best <= 0.0:
        return 1, 0, 0.0
    # A divisor of the true cell scores exactly as high as the true cell, so the
    # largest near-tie is the lattice and the smaller ones are its divisors.
    cell, phase, confidence = max(
        (score for score in scores if score[2] >= best - _TIE), key=lambda score: score[0]
    )
    return cell, phase, confidence


def detect_grid(img: Image) -> tuple[int, int, int, int, float]:
    """Return (cell_w, cell_h, offset_x, offset_y, confidence) of the pixel-art lattice.

    The confidence is the normalised peak height of the edge-magnitude phase
    histogram, taken as the weaker of the two axes: 1.0 is a perfect lattice and
    0.0 is a uniform spread of edges. Below 0.5 the caller must leave the image
    untouched.
    """
    lum = _luminance(img)
    if lum.ndim != 2 or min(lum.shape) < 2 * _MIN_CELL:
        return 1, 1, 0, 0, 0.0
    cell_w, phase_x, conf_x = _best_cell(_edge_profile(lum, axis=1))
    cell_h, phase_y, conf_y = _best_cell(_edge_profile(lum, axis=0))
    offset_x = (phase_x + 1) % cell_w if cell_w >= _MIN_CELL else 0
    offset_y = (phase_y + 1) % cell_h if cell_h >= _MIN_CELL else 0
    return cell_w, cell_h, offset_x, offset_y, float(min(conf_x, conf_y))


def snap_to_grid(img: Image, grid: tuple[int, int, int, int]) -> Image:
    """Resample img with nearest neighbour onto the lattice, removing anti-aliasing.

    The result is one sample per lattice cell, taken at the cell centre, so an
    image upscaled by an integer factor is recovered exactly. A degenerate grid
    (both cells below 2) or one that covers no cell returns an unchanged copy.
    """
    work = np.asarray(img)
    cell_w, cell_h, offset_x, offset_y = (int(value) for value in grid)
    if cell_w < _MIN_CELL and cell_h < _MIN_CELL:
        return np.array(work, copy=True)
    cell_w = max(1, cell_w)
    cell_h = max(1, cell_h)
    height, width = work.shape[:2]
    offset_x = min(max(0, offset_x), width - 1)
    offset_y = min(max(0, offset_y), height - 1)
    cols = (width - offset_x) // cell_w
    rows = (height - offset_y) // cell_h
    if cols < 1 or rows < 1:
        return np.array(work, copy=True)
    xs = offset_x + np.arange(cols) * cell_w + cell_w // 2
    ys = offset_y + np.arange(rows) * cell_h + cell_h // 2
    return np.ascontiguousarray(work[np.ix_(ys, xs)])
