"""Minimal SVG writer for the shared export dialog (CONTRACT §11, pixel fallback).

Writes one ``<path>`` per distinct colour, each made of horizontal runs, so the
document stays small and vector. One image pixel becomes ``cell`` units; the
document size is ``width * cell`` by ``height * cell``, matching the pipeline
output size exactly at the chosen cell scale. Glyph renderers with ``layout()``
will drive richer SVG later (card L11); this writer is the always-available
pixel fallback and never touches an application module.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lattice_core.types import RGB8

SVG_NS = "http://www.w3.org/2000/svg"
_CRISP = 'shape-rendering="crispEdges"'
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _packed_codes(rgb8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the packed 0xRRGGBB codes and the (H, W) index map of rgb8."""
    array = np.asarray(rgb8)
    packed = (
        (array[:, :, 0].astype(np.int32) << 16)
        | (array[:, :, 1].astype(np.int32) << 8)
        | array[:, :, 2].astype(np.int32)
    )
    codes, inverse = np.unique(packed, return_inverse=True)
    return codes, inverse.reshape(array.shape[:2])


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the (y, x, length) of every horizontal run of True in mask."""
    height, width = mask.shape
    padded = np.zeros((height, width + 2), dtype=np.int8)
    padded[:, 1 : width + 1] = mask
    ys, xs = np.nonzero(padded[:, 1:] != padded[:, :-1])
    starts = xs[0::2]
    return ys[0::2], starts, xs[1::2] - starts


def _path_data(ys: np.ndarray, xs: np.ndarray, lengths: np.ndarray, cell: int) -> str:
    """Return the path data of the runs, one subpath per run."""
    return "".join(
        f"M{x * cell} {y * cell}h{length * cell}v{cell}"
        for x, y, length in zip(xs.tolist(), ys.tolist(), lengths.tolist(), strict=True)
    )


def _check_background(value: str) -> str:
    """Return value as an uppercase ``#RRGGBB`` string, or raise ValueError."""
    text = str(value).strip().lstrip("#")
    if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
        raise ValueError(f"invalid colour: {value!r}")
    return "#" + text.upper()


def write_svg(
    rgb8: RGB8, path: Path, *, cell: int = 1, background: str | None = None
) -> None:
    """Write rgb8 to path as an SVG with one path element per distinct colour."""
    array = np.asarray(rgb8)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
    if int(cell) < 1:
        raise ValueError(f"cell must be >= 1, got {cell}")
    height, width = array.shape[:2]
    if height == 0 or width == 0:
        raise ValueError("cannot export an empty image")
    cell = int(cell)
    if background is not None:
        background = _check_background(background)
    codes, indices = _packed_codes(array)
    parts = [
        f'<svg xmlns="{SVG_NS}" width="{width * cell}" height="{height * cell}" '
        f'viewBox="0 0 {width * cell} {height * cell}">'
    ]
    if background is not None:
        parts.append(f'<rect width="100%" height="100%" fill="{background}"/>')
    for code in codes:
        mask = indices == code
        ys, xs, lengths = _runs(mask)
        if len(ys) == 0:
            continue
        parts.append(
            f'<path fill="#{int(code):06X}" {_CRISP} d="{_path_data(ys, xs, lengths, cell)}"/>'
        )
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


__all__ = ["SVG_NS", "write_svg"]
