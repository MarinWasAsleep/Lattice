"""SVG export (CONTRACT §19).

One ``<path>`` per distinct colour, each made of horizontal runs. A run is emitted as
``M x y h w v cell``: the fill rule closes the subpath implicitly, so the rectangle is
complete without a ``z`` and without a return leg.

``cell`` multiplies the coordinate system, so one image pixel becomes ``cell`` units and
the document is ``width * cell`` by ``height * cell`` pixels. The ``viewBox`` uses the
same multiplied space, which keeps the drawing 1:1 at ``cell = 1``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lattice_dither.core.types import RGB8

SVG_NS = "http://www.w3.org/2000/svg"
CRISP = 'shape-rendering="crispEdges"'
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _hex(code: int) -> str:
    """Return a packed 0xRRGGBB colour as an uppercase "#RRGGBB" string."""
    return f"#{code:06X}"


def _check_color(value: str) -> str:
    """Return value as an uppercase "#RRGGBB" string, or raise ValueError."""
    text = str(value).strip().lstrip("#")
    if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
        raise ValueError(f"invalid colour: {value!r}")
    return "#" + text.upper()


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the (y, x, length) of every horizontal run of True in mask.

    The mask is padded with a False column on each side, so every row starts and ends on
    a value change. The changes therefore pair up as (start, end) within each row, and
    the even stride picks the starts while the odd stride picks the ends.
    """
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


def _codes(rgb8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the distinct packed colours and the index map of rgb8."""
    array = np.asarray(rgb8)
    packed = (
        (array[:, :, 0].astype(np.int32) << 16)
        | (array[:, :, 1].astype(np.int32) << 8)
        | array[:, :, 2].astype(np.int32)
    )
    codes, inverse = np.unique(packed, return_inverse=True)
    return codes, inverse.reshape(array.shape[:2])


def export_svg(
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
    codes, indices = _codes(array)
    parts = [
        f'<svg xmlns="{SVG_NS}" width="{width * cell}" height="{height * cell}" '
        f'viewBox="0 0 {width * cell} {height * cell}">'
    ]
    if background is not None:
        parts.append(
            f'<rect width="{width * cell}" height="{height * cell}" '
            f'fill="{_check_color(background)}"/>'
        )
    for position, code in enumerate(codes.tolist()):
        ys, xs, lengths = _runs(indices == position)
        if ys.size == 0:
            continue
        parts.append(
            f'<path fill="{_hex(code)}" {CRISP} d="{_path_data(ys, xs, lengths, cell)}"/>'
        )
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")
