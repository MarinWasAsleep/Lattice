"""Generic export writers for the shared dialog: print PNG and animated GIF.

Pillow and numpy only, no application import and no external binary: the video
writer stays injectable because ffmpeg lives outside core (CONTRACT §20, §21).
The print layout is the contract one: the trim, an edge-replicated bleed and a
transparent margin holding the crop marks; separations are CMYK plates at full
black pullout, written as single-channel PNGs where 255 means full ink.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice.effects.halftone import plates
from lattice.types import RGB8

MM_PER_INCH = 25.4
MARK_MM = 3.0
MARK_THICKNESS_MM = 0.25
SEPARATION_PULLOUT = 1.0
INKS = ("C", "M", "Y", "K")


def _mm_to_px(mm: float, dpi: int) -> int:
    """Convert a length in millimetres to whole pixels at dpi."""
    return int(round(mm / MM_PER_INCH * dpi))


def _mark(canvas: np.ndarray, top: int, left: int, height: int, width: int) -> None:
    """Paint one black crop mark onto the RGBA canvas."""
    canvas[top : top + height, left : left + width] = (0, 0, 0, 255)


def _draw_marks(canvas: np.ndarray, margin: int, bleed: int, dpi: int) -> None:
    """Draw the eight crop marks in the margin, aligned with the trim edges."""
    height, width = canvas.shape[:2]
    thick = max(1, _mm_to_px(MARK_THICKNESS_MM, dpi))
    top, left = margin + bleed, margin + bleed
    bottom, right = height - margin - bleed, width - margin - bleed
    for y in (top, bottom):
        _mark(canvas, y, 0, thick, margin)
        _mark(canvas, y, width - margin, thick, margin)
    for x in (left, right):
        _mark(canvas, 0, x, margin, thick)
        _mark(canvas, height - margin, x, margin, thick)


def _canvas(array: np.ndarray, bleed: int, margin: int, dpi: int) -> np.ndarray:
    """Return the printable canvas: trim, then bleed, then the transparent margin."""
    work = array
    if bleed:
        work = np.pad(work, ((bleed, bleed), (bleed, bleed), (0, 0)), mode="edge")
    if not margin:
        return work
    height, width = work.shape[:2]
    canvas = np.zeros((height + 2 * margin, width + 2 * margin, 4), dtype=np.uint8)
    canvas[margin : margin + height, margin : margin + width, :3] = work
    canvas[margin : margin + height, margin : margin + width, 3] = 255
    _draw_marks(canvas, margin, bleed, dpi)
    return canvas


def _save(canvas: np.ndarray, path: Path, dpi: int) -> None:
    """Write the canvas as a PNG carrying dpi in its metadata."""
    mode = "RGBA" if canvas.shape[2] == 4 else "RGB"
    PILImage.fromarray(canvas, mode=mode).save(path, format="PNG", dpi=(dpi, dpi))


def _save_plate(plate: np.ndarray, path: Path, dpi: int) -> None:
    """Write one ink plate as a single-channel PNG where 255 is full ink."""
    data = np.clip(np.asarray(plate, dtype=np.float32) * 255.0, 0.0, 255.0).astype(np.uint8)
    PILImage.fromarray(data, mode="L").save(path, format="PNG", dpi=(dpi, dpi))


def write_print(
    rgb8: RGB8,
    path: Path,
    *,
    dpi: int = 300,
    bleed_mm: float = 0.0,
    crop_marks: bool = False,
    separations: bool = False,
) -> list[Path]:
    """Write rgb8 as a print-ready PNG and return every file created, in write order."""
    array = np.asarray(rgb8)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
    if int(dpi) < 1:
        raise ValueError(f"dpi must be >= 1, got {dpi}")
    if float(bleed_mm) < 0.0:
        raise ValueError(f"bleed_mm must be >= 0, got {bleed_mm}")
    if array.shape[0] == 0 or array.shape[1] == 0:
        raise ValueError("cannot export an empty image")
    target = Path(path)
    bleed = _mm_to_px(float(bleed_mm), int(dpi))
    margin = _mm_to_px(MARK_MM, int(dpi)) if crop_marks else 0
    canvas = _canvas(array, bleed, margin, int(dpi))
    _save(canvas, target, int(dpi))
    written = [target]
    if separations:
        work = np.ascontiguousarray(array, dtype=np.float32) / 255.0
        for ink, plate in zip(INKS, plates(work, SEPARATION_PULLOUT), strict=True):
            plate_path = target.with_name(f"{target.stem}_{ink}.png")
            _save_plate(plate, plate_path, int(dpi))
            written.append(plate_path)
    return written


def _check_sequence(frames: list[RGB8], fps: int) -> int:
    """Validate the sequence and return the frame duration in milliseconds."""
    if not frames:
        raise ValueError("cannot export an empty sequence")
    if int(fps) < 1:
        raise ValueError(f"fps must be >= 1, got {fps}")
    return int(round(1000.0 / int(fps)))


def write_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
    """Write frames to path as an animated GIF, using Pillow only."""
    duration = _check_sequence(frames, fps)
    images = [PILImage.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB") for frame in frames]
    images[0].save(
        Path(path),
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=int(loop),
        optimize=False,
    )


__all__ = ["write_gif", "write_print"]
