"""GIF and video export (CONTRACT §21).

``export_gif`` uses Pillow only. ``export_video`` shells out to ffmpeg and returns
``False`` without writing anything when no binary can be found, so a missing ffmpeg is a
normal outcome rather than an error.

The binary comes from ``imageio-ffmpeg``, which ships one inside the wheel, so a plain
``pip install -r requirements.txt`` is enough. A system ffmpeg is the fallback, for the
case where the dependency is absent.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_dither.core.types import RGB8

FFMPEG = "ffmpeg"
FRAME_PATTERN = "frame_%06d.png"
EVEN_PAD = "pad=ceil(iw/2)*2:ceil(ih/2)*2"


def _resolve_ffmpeg() -> str | None:
    """Return the ffmpeg binary to run, or None when none is available."""
    try:
        import imageio_ffmpeg
    except ImportError:
        return shutil.which(FFMPEG)
    try:
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except (OSError, RuntimeError):
        return shutil.which(FFMPEG)


def _check(frames: list[RGB8], fps: int) -> int:
    """Validate the sequence and return the frame duration in milliseconds."""
    if not frames:
        raise ValueError("cannot export an empty sequence")
    if int(fps) < 1:
        raise ValueError(f"fps must be >= 1, got {fps}")
    return int(round(1000.0 / int(fps)))


def _pil(frame: RGB8) -> PILImage.Image:
    """Return one frame as a Pillow RGB image."""
    return PILImage.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB")


def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
    """Write frames to path as an animated GIF, using Pillow only."""
    duration = _check(frames, fps)
    images = [_pil(frame) for frame in frames]
    images[0].save(
        Path(path),
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=int(loop),
        optimize=False,
    )


def export_video(frames: list[RGB8], path: Path, *, fps: int = 12) -> bool:
    """Write frames to path through ffmpeg, returning False when no ffmpeg is available."""
    _check(frames, fps)
    binary = _resolve_ffmpeg()
    if binary is None:
        return False
    target = Path(path)
    with tempfile.TemporaryDirectory(prefix="lattice-video-") as folder:
        for index, frame in enumerate(frames):
            _pil(frame).save(Path(folder) / f"frame_{index:06d}.png")
        command = [
            binary,
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(int(fps)),
            "-i",
            str(Path(folder) / FRAME_PATTERN),
            "-vf",
            EVEN_PAD,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ]
        try:
            result = subprocess.run(command, capture_output=True, check=False)
        except OSError:
            return False
    return result.returncode == 0 and target.exists()
