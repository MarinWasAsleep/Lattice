"""Render a contact sheet comparing the new algorithms on one test image."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lattice_core.dither  # noqa: F401
import lattice_core.effects  # noqa: F401
from lattice_core.pipeline import PaletteSpec, PipelineSpec, render

SIZE = 200
CELL = 200
LABEL = 18


def test_image() -> np.ndarray:
    """Build a colourful test image: gradients, discs and a checkerboard."""
    ys, xs = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    u = xs / (SIZE - 1)
    v = ys / (SIZE - 1)
    img = np.empty((SIZE, SIZE, 3), dtype=np.float32)
    img[:, :, 0] = 0.15 + 0.8 * u
    img[:, :, 1] = 0.15 + 0.8 * v
    img[:, :, 2] = 0.15 + 0.7 * (1.0 - u) * (1.0 - v)
    for cx, cy, radius, colour in (
        (0.28, 0.30, 0.16, (1.0, 0.95, 0.2)),
        (0.72, 0.34, 0.13, (0.1, 0.9, 1.0)),
        (0.50, 0.74, 0.19, (1.0, 0.25, 0.55)),
    ):
        dx = u - cx
        dy = v - cy
        mask = (dx * dx + dy * dy) < radius * radius
        for channel in range(3):
            img[:, :, channel] = np.where(mask, colour[channel], img[:, :, channel])
    checker = ((xs // 12 + ys // 12) % 2).astype(np.float32)
    band = (v > 0.86) & (v < 0.96)
    for channel in range(3):
        img[:, :, channel] = np.where(band, checker * 0.9 + 0.05, img[:, :, channel])
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0).astype(np.float32))


CASES = [
    ("Floyd-Steinberg", "floyd_steinberg", {}, "pico8"),
    ("Ostromoukhov", "ostromoukhov", {}, "pico8"),
    ("Fan", "fan", {}, "pico8"),
    ("Shiau-Fan", "shiau_fan", {}, "pico8"),
    ("Yliluoma 1", "yliluoma1", {"levels": 96}, "pico8"),
    ("Yliluoma 2", "yliluoma2", {"slots": 64}, "pico8"),
    ("Dot Diffusion", "dot_diffusion", {}, "pico8"),
    ("Direct Binary Search", "direct_binary_search", {"iterations": 3}, "pico8"),
]


def main() -> int:
    """Render every case into a labelled grid and save it next to the script."""
    src = test_image()
    columns = 4
    rows = (len(CASES) + columns - 1) // columns
    sheet = PILImage.new(
        "RGB", (columns * CELL, rows * (CELL + LABEL)), (24, 24, 28)
    )
    draw = ImageDraw.Draw(sheet)
    for index, (label, algorithm, params, palette) in enumerate(CASES):
        spec = PipelineSpec()
        spec.algorithm_id = algorithm
        spec.algorithm_params = dict(params)
        spec.palette = PaletteSpec(source="builtin", name=palette)
        spec.pixel_size = 1
        rgb8 = render(src, spec)
        tile = PILImage.fromarray(rgb8, "RGB")
        column = index % columns
        row = index // columns
        x = column * CELL
        y = row * (CELL + LABEL)
        sheet.paste(tile, (x, y + LABEL))
        draw.text((x + 4, y + 4), label, fill=(235, 235, 240))
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "planche_algorithmes.png")
    sheet.save(target)
    print(f"wrote {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
