"""Generate ``assets/lattice.modes.dither.ico``: a 256 px Bayer-dithered icon.

Run once from the project root: ``python tools/make_icon.py``.
The result is committed; the application never regenerates it at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 256
MATRIX_SIZE = 8
ICO_SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "lattice.modes.dither.ico"


def bayer_matrix(size: int) -> np.ndarray:
    """Return the size x size Bayer threshold matrix normalized to (0, 1)."""
    matrix = np.zeros((1, 1), dtype=np.int32)
    while matrix.shape[0] < size:
        matrix = np.block(
            [
                [4 * matrix, 4 * matrix + 2],
                [4 * matrix + 3, 4 * matrix + 1],
            ]
        )
    return (matrix.astype(np.float64) + 0.5) / float(size * size)


def radial_gradient(size: int) -> np.ndarray:
    """Return a size x size luminance ramp, bright in the centre and dark at the rim."""
    axis = (np.arange(size, dtype=np.float64) + 0.5) / size * 2.0 - 1.0
    radius = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2)
    return np.clip(1.3 - 1.1 * radius, 0.0, 1.0)


def render(size: int = SIZE) -> Image.Image:
    """Return the Bayer-dithered icon as a black and white 8-bit image."""
    cell = size // MATRIX_SIZE
    thresholds = np.tile(bayer_matrix(MATRIX_SIZE), (cell, cell))
    lit = radial_gradient(size) > thresholds
    return Image.fromarray(np.where(lit, 255, 0).astype(np.uint8))


def main() -> int:
    """Render the icon, write the .ico file and verify that Pillow reopens it."""
    image = render()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="ICO", sizes=list(ICO_SIZES))
    with Image.open(OUTPUT) as reopened:
        sizes = sorted(reopened.ico.sizes())
    print(f"wrote {OUTPUT} ({len(sizes)} sizes, largest {sizes[-1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
