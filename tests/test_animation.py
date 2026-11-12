"""Tests for the animation and video export (CONTRACT §21)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import lattice_dither.algorithms  # noqa: F401
from lattice_dither.core import animation
from lattice_dither.core.animation import render_sequence
from lattice_dither.core.pipeline import (
    PaletteSpec,
    PipelineSpec,
    prepare_image,
    resolve_palette,
)
from lattice_dither.export import video
from lattice_dither.export.video import export_gif, export_video

BW = ["#000000", "#FFFFFF"]


def _spec(algorithm_id: str = "bayer_4", **overrides) -> PipelineSpec:
    """Return a spec with a two-colour palette and the given algorithm."""
    base: dict = {
        "algorithm_id": algorithm_id,
        "palette": PaletteSpec(source="custom", colors=BW),
    }
    base.update(overrides)
    return PipelineSpec(**base)


def _frame(offset: int = 0, size: int = 16) -> np.ndarray:
    """Return a grey frame whose bright band moves with offset."""
    frame = np.zeros((size, size, 3), dtype=np.float32)
    frame[:, :] = 0.25
    frame[:, (offset * 3) % size : (offset * 3) % size + 4] = 0.75
    return frame


def _frames(count: int = 5) -> list[np.ndarray]:
    """Return count distinct frames."""
    return [_frame(index) for index in range(count)]


def _rgb_frames(count: int = 5) -> list[np.ndarray]:
    """Return count distinct uint8 frames, ready for the GIF writer."""
    frames = []
    for index in range(count):
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        frame[:, index * 3 : index * 3 + 3] = 255
        frames.append(frame)
    return frames


def test_a_stable_sequence_of_identical_frames_is_identical() -> None:
    """Five copies of one frame render to five identical images."""
    frame = _frame()
    out = render_sequence([frame.copy() for _ in range(5)], _spec(), stable=True)
    assert len(out) == 5
    assert all(np.array_equal(out[0], other) for other in out)


def test_an_unstable_sequence_of_different_frames_differs() -> None:
    """With a random algorithm and moving frames, consecutive outputs differ."""
    out = render_sequence(_frames(), _spec("random"), stable=False)
    assert len(out) == 5
    assert all(not np.array_equal(out[i], out[i + 1]) for i in range(4))


def test_identical_frames_render_identically_when_unstable() -> None:
    """The seed belongs to the spec, not to the frame, so stable=False does not add noise."""
    frame = _frame()
    out = render_sequence([frame.copy() for _ in range(3)], _spec("random"), stable=False)
    assert all(np.array_equal(out[0], other) for other in out)


def test_the_palette_is_resolved_once_when_stable(monkeypatch) -> None:
    """A five-frame stable sequence resolves the palette exactly once."""
    calls: list[int] = []
    real = animation.resolve_palette

    def counting(spec, img):
        calls.append(1)
        return real(spec, img)

    monkeypatch.setattr(animation, "resolve_palette", counting)
    render_sequence(_frames(), _spec(), stable=True)
    assert len(calls) == 1


def test_the_palette_is_resolved_per_frame_when_unstable(monkeypatch) -> None:
    """An unstable sequence resolves the palette once per frame."""
    calls: list[int] = []
    real = animation.resolve_palette

    def counting(spec, img):
        calls.append(1)
        return real(spec, img)

    monkeypatch.setattr(animation, "resolve_palette", counting)
    render_sequence(_frames(), _spec(), stable=False)
    assert len(calls) == 5


def test_a_stable_sequence_keeps_one_palette_across_different_frames() -> None:
    """Every output colour comes from the palette resolved on the first frame."""
    spec = _spec(palette=PaletteSpec(source="extracted", extract_k=4))
    frames = _frames()
    expected = resolve_palette(spec.palette, prepare_image(frames[0], spec))
    allowed = {tuple(int(v) for v in row) for row in np.round(expected * 255.0).astype(np.uint8)}
    out = render_sequence(frames, spec, stable=True)
    for frame in out:
        seen = {tuple(int(v) for v in row) for row in frame.reshape(-1, 3)}
        assert seen <= allowed


def test_an_empty_sequence_renders_nothing() -> None:
    """No frames in, no frames out."""
    assert render_sequence([], _spec()) == []


def test_export_gif_writes_a_reopenable_file(tmp_path: Path) -> None:
    """The GIF reopens with the right frame count and duration."""
    target = tmp_path / "clip.gif"
    export_gif(_rgb_frames(), target, fps=10)
    with Image.open(target) as written:
        assert written.n_frames == 5
        assert written.info["duration"] == 100


def test_export_gif_rounds_the_duration_to_centiseconds(tmp_path: Path) -> None:
    """GIF stores the delay in centiseconds, so 12 fps lands on 80 ms."""
    target = tmp_path / "clip.gif"
    export_gif(_rgb_frames(), target, fps=12)
    with Image.open(target) as written:
        assert written.info["duration"] == 80


def test_export_gif_honours_the_loop_count(tmp_path: Path) -> None:
    """The loop count reaches the file."""
    target = tmp_path / "clip.gif"
    export_gif(_rgb_frames(), target, fps=10, loop=3)
    with Image.open(target) as written:
        assert written.info["loop"] == 3


def test_export_gif_rejects_an_empty_sequence(tmp_path: Path) -> None:
    """An empty sequence is rejected rather than written as a broken file."""
    with pytest.raises(ValueError, match="empty"):
        export_gif([], tmp_path / "clip.gif")


def test_export_gif_rejects_a_bad_fps(tmp_path: Path) -> None:
    """fps below one is rejected."""
    with pytest.raises(ValueError, match="fps"):
        export_gif(_rgb_frames(), tmp_path / "clip.gif", fps=0)


def test_export_video_returns_false_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    """A missing ffmpeg is a normal outcome, not an error."""
    monkeypatch.setattr(video, "_resolve_ffmpeg", lambda: None)
    target = tmp_path / "clip.mp4"
    assert export_video(_rgb_frames(), target) is False
    assert not target.exists()


def test_export_video_writes_nothing_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    """No file and no leftover frame directory are produced without ffmpeg."""
    monkeypatch.setattr(video, "_resolve_ffmpeg", lambda: None)
    export_video(_rgb_frames(), tmp_path / "clip.mp4")
    assert list(tmp_path.iterdir()) == []


def test_export_video_never_raises_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    """The absent-ffmpeg path swallows nothing but also raises nothing."""
    monkeypatch.setattr(video, "_resolve_ffmpeg", lambda: None)
    assert export_video(_rgb_frames(), tmp_path / "clip.mp4", fps=24) is False


def test_export_video_rejects_an_empty_sequence(tmp_path: Path) -> None:
    """An empty sequence is rejected before ffmpeg is looked for."""
    with pytest.raises(ValueError, match="empty"):
        export_video([], tmp_path / "clip.mp4")


needs_ffmpeg = pytest.mark.skipif(
    video._resolve_ffmpeg() is None, reason="no ffmpeg binary is available"
)
needs_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None, reason="ffprobe is not installed"
)


@needs_ffmpeg
def test_export_video_writes_a_file_when_ffmpeg_is_present(tmp_path: Path) -> None:
    """With ffmpeg on PATH the export returns True and leaves a non-empty file."""
    target = tmp_path / "clip.mp4"
    assert export_video(_rgb_frames(), target, fps=12) is True
    assert target.exists()
    assert target.stat().st_size > 0


@needs_ffmpeg
@needs_ffprobe
def test_export_video_encodes_the_requested_frame_count(tmp_path: Path) -> None:
    """The encoded stream carries every frame at the requested rate and size."""
    target = tmp_path / "clip.mp4"
    export_video(_rgb_frames(), target, fps=12)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames,r_frame_rate",
            "-of",
            "json",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (16, 16)
    assert stream["nb_frames"] == "5"
    assert stream["r_frame_rate"] == "12/1"
