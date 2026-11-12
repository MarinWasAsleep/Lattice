"""Error diffusion dithering algorithms driven by data tables."""

from __future__ import annotations

import numpy as np
from numba import njit

from lattice_dither.core.color import nearest_index_px
from lattice_dither.core.registry import AlgorithmFn, register_algorithm
from lattice_dither.core.types import Image, Indices, Palette, ParamSpec

_PARAMS = (
    ParamSpec("serpentine", "Serpentine", "bool", True),
    ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0, 0.05),
)

# id -> (divisor, ((dx, dy, weight), ...)); weights are divided by the divisor at use.
KERNELS: dict[str, tuple[int, tuple[tuple[int, int, int], ...]]] = {
    "floyd_steinberg": (16, ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1))),
    "false_floyd_steinberg": (8, ((1, 0, 3), (0, 1, 3), (1, 1, 2))),
    "jarvis_judice_ninke": (
        48,
        (
            (1, 0, 7),
            (2, 0, 5),
            (-2, 1, 3),
            (-1, 1, 5),
            (0, 1, 7),
            (1, 1, 5),
            (2, 1, 3),
            (-2, 2, 1),
            (-1, 2, 3),
            (0, 2, 5),
            (1, 2, 3),
            (2, 2, 1),
        ),
    ),
    "stucki": (
        42,
        (
            (1, 0, 8),
            (2, 0, 4),
            (-2, 1, 2),
            (-1, 1, 4),
            (0, 1, 8),
            (1, 1, 4),
            (2, 1, 2),
            (-2, 2, 1),
            (-1, 2, 2),
            (0, 2, 4),
            (1, 2, 2),
            (2, 2, 1),
        ),
    ),
    "burkes": (
        32,
        (
            (1, 0, 8),
            (2, 0, 4),
            (-2, 1, 2),
            (-1, 1, 4),
            (0, 1, 8),
            (1, 1, 4),
            (2, 1, 2),
        ),
    ),
    "sierra": (
        32,
        (
            (1, 0, 5),
            (2, 0, 3),
            (-2, 1, 2),
            (-1, 1, 4),
            (0, 1, 5),
            (1, 1, 4),
            (2, 1, 2),
            (-1, 2, 2),
            (0, 2, 3),
            (1, 2, 2),
        ),
    ),
    "sierra_two_row": (
        16,
        ((1, 0, 4), (2, 0, 3), (-2, 1, 1), (-1, 1, 2), (0, 1, 3), (1, 1, 2), (2, 1, 1)),
    ),
    "sierra_lite": (4, ((1, 0, 2), (-1, 1, 1), (0, 1, 1))),
    "fan": (16, ((1, 0, 7), (-2, 1, 1), (-1, 1, 3), (0, 1, 5))),
    "shiau_fan": (16, ((1, 0, 8), (-3, 1, 1), (-2, 1, 1), (-1, 1, 2), (0, 1, 4))),
    "atkinson": (8, ((1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1))),
    "stevenson_arce": (
        200,
        (
            (2, 0, 32),
            (-3, 1, 12),
            (-1, 1, 26),
            (1, 1, 30),
            (3, 1, 16),
            (-2, 2, 12),
            (0, 2, 26),
            (2, 2, 12),
            (-3, 3, 5),
            (-1, 3, 12),
            (1, 3, 12),
            (3, 3, 5),
        ),
    ),
}

_NAMES: dict[str, str] = {
    "floyd_steinberg": "Floyd-Steinberg",
    "false_floyd_steinberg": "False Floyd-Steinberg",
    "jarvis_judice_ninke": "Jarvis-Judice-Ninke",
    "stucki": "Stucki",
    "burkes": "Burkes",
    "sierra": "Sierra",
    "sierra_two_row": "Sierra Two Row",
    "sierra_lite": "Sierra Lite",
    "fan": "Fan",
    "shiau_fan": "Shiau-Fan",
    "atkinson": "Atkinson",
    "stevenson_arce": "Stevenson-Arce",
}


@njit(cache=True)
def _diffuse(
    img: np.ndarray,
    palette: np.ndarray,
    offsets: np.ndarray,
    weights: np.ndarray,
    serpentine: bool,
    strength: float,
) -> np.ndarray:
    """Quantise every pixel and push its RGB error into the neighbour offsets; numba kernel."""
    height = img.shape[0]
    width = img.shape[1]
    work = img.copy()
    out = np.empty((height, width), dtype=np.int32)
    count = offsets.shape[0]
    for y in range(height):
        reverse = serpentine and (y % 2 == 1)
        for step in range(width):
            x = width - 1 - step if reverse else step
            r = work[y, x, 0]
            g = work[y, x, 1]
            b = work[y, x, 2]
            index = nearest_index_px(r, g, b, palette)
            out[y, x] = index
            err_r = (r - palette[index, 0]) * strength
            err_g = (g - palette[index, 1]) * strength
            err_b = (b - palette[index, 2]) * strength
            for k in range(count):
                dx = offsets[k, 0]
                if reverse:
                    dx = -dx
                nx = x + dx
                ny = y + offsets[k, 1]
                if 0 <= nx < width and 0 <= ny < height:
                    weight = weights[k]
                    work[ny, nx, 0] += err_r * weight
                    work[ny, nx, 1] += err_g * weight
                    work[ny, nx, 2] += err_b * weight
    return out


def _make_fn(kernel_id: str) -> AlgorithmFn:
    """Build the algorithm function of one diffusion kernel id."""
    divisor, entries = KERNELS[kernel_id]
    offsets = np.array([(dx, dy) for dx, dy, _ in entries], dtype=np.int64)
    weights = np.array([weight / divisor for _, _, weight in entries], dtype=np.float32)

    def fn(img: Image, palette: Palette, params: dict) -> Indices:
        """Dither img with this kernel and return palette indices."""
        work = np.ascontiguousarray(img, dtype=np.float32)
        pal = np.ascontiguousarray(palette, dtype=np.float32)
        return _diffuse(
            work,
            pal,
            offsets,
            weights,
            bool(params["serpentine"]),
            float(params["strength"]),
        )

    return fn


def _register_all() -> None:
    """Register every kernel of KERNELS in table order."""
    for kernel_id, label in _NAMES.items():
        register_algorithm(kernel_id, label, "error_diffusion", _PARAMS)(_make_fn(kernel_id))


_register_all()
