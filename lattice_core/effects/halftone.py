"""CMYK halftone post-effect (CONTRACT §15.2)."""

from __future__ import annotations

import numpy as np

from lattice_core.dither.halftone import coverage, spot_function
from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

_CMYK_SHAPES = ("round", "square", "diamond", "ellipse")

_LPI = ParamSpec("lpi", "Lines per inch", "int", 60, 20, 200, 1)
_DOT_SHAPE = ParamSpec("dot_shape", "Dot shape", "choice", "round", choices=_CMYK_SHAPES)
_BLACK_PULLOUT = ParamSpec("black_pullout", "Black pullout", "float", 0.5, 0.0, 1.0, 0.05)
_OVERSAMPLE = ParamSpec("oversample", "Oversample", "int", 2, 1, 4, 1)
_INK_COLORS = ParamSpec("ink_colors", "Ink colours", "bool", False)

_PARAMS = (_LPI, _DOT_SHAPE, _BLACK_PULLOUT, _OVERSAMPLE, _INK_COLORS)

_REFERENCE_DPI = 300.0
_ANGLES = (15.0, 75.0, 0.0, 45.0)
_INKS = np.array(
    [[0.0, 1.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
    dtype=np.float32,
)


def plates(img: Image, black_pullout: float) -> tuple[np.ndarray, ...]:
    """Return the C, M, Y and K ink amounts of every pixel.

    ``black_pullout`` moves the grey component out of C, M and Y and into K: at 0
    the black plate is empty and the three chromatic plates carry everything, at 1
    the grey component is entirely on K.
    """
    work = np.asarray(img, dtype=np.float32)
    cyan = np.float32(1.0) - work[:, :, 0]
    magenta = np.float32(1.0) - work[:, :, 1]
    yellow = np.float32(1.0) - work[:, :, 2]
    black = np.minimum(np.minimum(cyan, magenta), yellow)
    pull = np.float32(black_pullout)
    return (
        cyan - black * pull,
        magenta - black * pull,
        yellow - black * pull,
        black * pull,
    )


def _screen(plate: np.ndarray, spot, cell_size: float, angle: float, oversample: int) -> np.ndarray:
    """Return the ink coverage of one plate, screened at angle."""
    return coverage(np.float32(1.0) - plate, spot, cell_size, angle, oversample)


@register_effect("halftone_cmyk", "CMYK Halftone", _PARAMS)
def halftone_cmyk(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Screen the four CMYK plates at the print angles and recombine them."""
    spot = spot_function(str(params["dot_shape"]))
    cell_size = max(1.0, _REFERENCE_DPI / float(params["lpi"]))
    oversample = int(params["oversample"])
    coverages = [
        _screen(plate, spot, cell_size, angle, oversample)
        for plate, angle in zip(plates(img, float(params["black_pullout"])), _ANGLES, strict=True)
    ]
    if bool(params["ink_colors"]):
        out = np.ones(np.shape(img), dtype=np.float32)
        for ink, amount in zip(_INKS, coverages, strict=True):
            out *= np.float32(1.0) - amount[:, :, None] * (np.float32(1.0) - ink)
        return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)
    total = np.clip(sum(coverages), 0.0, 1.0)
    grey = np.float32(1.0) - total
    return np.ascontiguousarray(np.repeat(grey[:, :, None], 3, axis=2), dtype=np.float32)
