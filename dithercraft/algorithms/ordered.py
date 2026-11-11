"""Ordered dithering algorithms based on threshold matrices."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np

from dithercraft.core.color import nearest_index
from dithercraft.core.registry import AlgorithmFn, register_algorithm
from dithercraft.core.types import Image, Indices, Palette, ParamSpec

_PARAMS = (
    ParamSpec("spread", "Spread", "float", 1.0, 0.0, 2.0, 0.05),
    ParamSpec("matrix_scale", "Matrix scale", "int", 1, 1, 8, 1),
)

_BLUE_NOISE_PATH = Path(__file__).resolve().parents[2] / "data" / "blue_noise_64.npy"
_blue_noise_ranks: np.ndarray | None = None
_matrix_cache: dict[str, np.ndarray] = {}


def _thresholds(ranks: np.ndarray, levels: int) -> np.ndarray:
    """Normalise integer ranks to thresholds t = (rank + 0.5) / levels."""
    return ((ranks.astype(np.float32) + np.float32(0.5)) / np.float32(levels)).astype(np.float32)


def _bayer(size: int) -> np.ndarray:
    """Return the size x size Bayer rank matrix built recursively from [[0, 2], [3, 1]]."""
    matrix = np.array([[0, 2], [3, 1]], dtype=np.int32)
    while matrix.shape[0] < size:
        matrix = np.block(
            [
                [4 * matrix, 4 * matrix + 2],
                [4 * matrix + 3, 4 * matrix + 1],
            ]
        ).astype(np.int32)
    return matrix


def _cluster_dot(size: int) -> np.ndarray:
    """Return ranks ordered by distance to the cell centre, ties broken by angle."""
    centre = (size - 1) / 2.0
    ys, xs = np.mgrid[0:size, 0:size]
    dy = ys - centre
    dx = xs - centre
    distance = np.hypot(dy, dx)
    angle = np.arctan2(dy, dx)
    order = np.lexsort((angle.ravel(), distance.ravel()))
    ranks = np.empty(size * size, dtype=np.int32)
    ranks[order] = np.arange(size * size, dtype=np.int32)
    return ranks.reshape(size, size)


def _lines(axis: str) -> np.ndarray:
    """Return the 4-level rank tile of one line orientation."""
    if axis == "horizontal":
        return np.arange(4, dtype=np.int32).reshape(4, 1)
    if axis == "vertical":
        return np.arange(4, dtype=np.int32).reshape(1, 4)
    ys, xs = np.mgrid[0:4, 0:4]
    return ((xs + ys) % 4).astype(np.int32)


def _bayer_matrix(size: int) -> np.ndarray:
    """Return the normalised Bayer threshold matrix of the given size."""
    return _thresholds(_bayer(size), size * size)


def _cluster_dot_matrix(size: int) -> np.ndarray:
    """Return the normalised cluster-dot threshold matrix of the given size."""
    return _thresholds(_cluster_dot(size), size * size)


def _lines_matrix(axis: str) -> np.ndarray:
    """Return the normalised line threshold matrix of one orientation."""
    return _thresholds(_lines(axis), 4)


def blue_noise_ranks() -> np.ndarray:
    """Return the committed 64x64 blue-noise rank array, loading it once."""
    global _blue_noise_ranks
    if _blue_noise_ranks is None:
        _blue_noise_ranks = np.load(_BLUE_NOISE_PATH).astype(np.int32)
    return _blue_noise_ranks


def _blue_noise_matrix() -> np.ndarray:
    """Return the normalised blue-noise threshold matrix."""
    ranks = blue_noise_ranks()
    return _thresholds(ranks, ranks.size)


_MATRICES: dict[str, tuple[str, Callable[[], np.ndarray]]] = {
    "bayer_2": ("Bayer 2x2", partial(_bayer_matrix, 2)),
    "bayer_4": ("Bayer 4x4", partial(_bayer_matrix, 4)),
    "bayer_8": ("Bayer 8x8", partial(_bayer_matrix, 8)),
    "bayer_16": ("Bayer 16x16", partial(_bayer_matrix, 16)),
    "cluster_dot_4": ("Cluster Dot 4x4", partial(_cluster_dot_matrix, 4)),
    "cluster_dot_8": ("Cluster Dot 8x8", partial(_cluster_dot_matrix, 8)),
    "blue_noise": ("Blue Noise", _blue_noise_matrix),
    "lines_horizontal": ("Lines Horizontal", partial(_lines_matrix, "horizontal")),
    "lines_vertical": ("Lines Vertical", partial(_lines_matrix, "vertical")),
    "lines_diagonal": ("Lines Diagonal", partial(_lines_matrix, "diagonal")),
}


def matrix(matrix_id: str) -> np.ndarray:
    """Return the normalised threshold matrix of matrix_id, building it once."""
    if matrix_id not in _matrix_cache:
        _matrix_cache[matrix_id] = _MATRICES[matrix_id][1]()
    return _matrix_cache[matrix_id]


def tile(t_matrix: np.ndarray, height: int, width: int, scale: int = 1) -> np.ndarray:
    """Repeat every matrix cell scale times, then tile the result over a height x width image."""
    if scale > 1:
        t_matrix = np.repeat(np.repeat(t_matrix, scale, axis=0), scale, axis=1)
    rows = np.arange(height) % t_matrix.shape[0]
    cols = np.arange(width) % t_matrix.shape[1]
    return np.ascontiguousarray(t_matrix[np.ix_(rows, cols)], dtype=np.float32)


def amplitude(spread: float, palette_size: int) -> float:
    """Return the threshold amplitude for a palette of palette_size colours."""
    levels = max(1, int(round(palette_size ** (1.0 / 3.0))) - 1)
    return spread / levels


def _ordered(
    img: Image, palette: Palette, t_matrix: np.ndarray, spread: float, scale: int
) -> Indices:
    """Offset every channel by the tiled threshold and quantise to the palette."""
    height, width = img.shape[:2]
    t = tile(t_matrix, height, width, scale)
    offset = (t[:, :, None] - np.float32(0.5)) * np.float32(amplitude(spread, palette.shape[0]))
    value = np.ascontiguousarray(img + offset, dtype=np.float32)
    return nearest_index(value, palette)


def _make_fn(matrix_id: str) -> AlgorithmFn:
    """Build the algorithm function of one threshold matrix id."""

    def fn(img: Image, palette: Palette, params: dict) -> Indices:
        """Dither img with this threshold matrix and return palette indices."""
        return _ordered(
            img,
            palette,
            matrix(matrix_id),
            float(params["spread"]),
            int(params["matrix_scale"]),
        )

    return fn


def _register_all() -> None:
    """Register every threshold matrix of _MATRICES in table order."""
    for matrix_id, (label, _) in _MATRICES.items():
        register_algorithm(matrix_id, label, "ordered", _PARAMS)(_make_fn(matrix_id))


_register_all()
