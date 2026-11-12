"""Tests for the export subcommands of the command line (T33 / CONTRACT §17, §19 to §21)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image as PILImage

import lattice_dither.algorithms  # noqa: F401  (importing the package registers every algorithm)
import lattice_dither.effects  # noqa: F401  (importing the package registers every effect)
from lattice_dither import cli
from lattice_dither.cli import EXIT_INPUT, EXIT_OK, EXIT_RENDER, EXIT_USAGE, main
from lattice_dither.core import color
from lattice_dither.core.animation import render_sequence
from lattice_dither.core.pipeline import render
from lattice_dither.core.presets import load_preset
from lattice_dither.core.types import RGB8
from lattice_dither.export import video as video_module
from lattice_dither.export.print import export_print
from lattice_dither.export.svg import export_svg
from lattice_dither.export.video import export_gif, export_video

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "data" / "baseline" / "source.png"
PRESET = ROOT / "presets" / "01_gameboy.json"
SIZE = (48, 36)
COMMANDS = ("export-svg", "export-print", "export-anim")
needs_ffmpeg = pytest.mark.skipif(
    video_module._resolve_ffmpeg() is None, reason="no ffmpeg binary is available"
)


def _image(path: Path, size: tuple[int, int] = SIZE) -> Path:
    """Write a small test image and return its path."""
    with PILImage.open(SOURCE) as handle:
        handle.convert("RGB").resize(size, PILImage.LANCZOS).save(path)
    return path


def _frames(folder: Path, count: int = 3) -> Path:
    """Write count rotated frames into folder and return the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    with PILImage.open(SOURCE) as handle:
        source = handle.convert("RGB").resize(SIZE, PILImage.LANCZOS)
        for index in range(count):
            source.rotate(index * 10).save(folder / f"frame_{index:02d}.png")
    return folder


def _run(command: str, source: Path, out: Path, *extra: str) -> int:
    """Run one export subcommand with the witness preset and return its exit code."""
    return main([command, "--preset", str(PRESET), "--in", str(source), "--out", str(out), *extra])


def _rgb8(path: Path) -> RGB8:
    """Render one image with the witness preset and return its uint8 RGB result."""
    with PILImage.open(path) as handle:
        return render(color.to_float(handle), load_preset(PRESET))


def _frames_rgb8(folder: Path) -> list[RGB8]:
    """Render every frame of folder with the witness preset, in sorted order."""
    spec = load_preset(PRESET)
    frames = []
    for path in sorted(folder.glob("*.png")):
        with PILImage.open(path) as handle:
            frames.append(color.to_float(handle))
    return render_sequence(frames, spec)


def test_export_svg_matches_a_python_call(tmp_path: Path) -> None:
    """The CLI writes exactly the bytes a direct export_svg call produces."""
    image = _image(tmp_path / "in.png")
    expected = tmp_path / "expected.svg"
    export_svg(_rgb8(image), expected, cell=2, background="#102030")
    produced = tmp_path / "produced.svg"
    code = _run("export-svg", image, produced, "--cell", "2", "--background", "#102030")
    assert code == EXIT_OK
    assert produced.read_bytes() == expected.read_bytes()


def test_export_print_matches_a_python_call(tmp_path: Path) -> None:
    """The CLI writes the same five files as a direct export_print call."""
    image = _image(tmp_path / "in.png")
    expected = export_print(
        _rgb8(image),
        tmp_path / "expected.png",
        dpi=150,
        bleed_mm=3.0,
        crop_marks=True,
        separations=True,
    )
    produced = tmp_path / "produced.png"
    code = _run(
        "export-print",
        image,
        produced,
        "--dpi",
        "150",
        "--bleed-mm",
        "3",
        "--crop-marks",
        "--separations",
    )
    assert code == EXIT_OK
    assert len(expected) == 5
    for source in expected:
        twin = produced.with_name(source.name.replace("expected", "produced"))
        assert twin.read_bytes() == source.read_bytes()


def test_export_anim_gif_matches_a_python_call(tmp_path: Path) -> None:
    """The CLI writes exactly the GIF bytes a direct export_gif call produces."""
    folder = _frames(tmp_path / "frames")
    expected = tmp_path / "expected.gif"
    export_gif(_frames_rgb8(folder), expected, fps=8, loop=2)
    produced = tmp_path / "produced.gif"
    code = _run("export-anim", folder, produced, "--fps", "8", "--loop", "2")
    assert code == EXIT_OK
    assert produced.read_bytes() == expected.read_bytes()


@needs_ffmpeg
def test_export_anim_video_matches_a_python_call(tmp_path: Path) -> None:
    """The CLI writes exactly the video bytes a direct export_video call produces."""
    folder = _frames(tmp_path / "frames")
    expected = tmp_path / "expected.mp4"
    assert export_video(_frames_rgb8(folder), expected, fps=8)
    produced = tmp_path / "produced.mp4"
    code = _run("export-anim", folder, produced, "--fps", "8")
    assert code == EXIT_OK
    assert produced.read_bytes() == expected.read_bytes()


def test_export_anim_accepts_a_single_image(tmp_path: Path) -> None:
    """A single image is a one-frame animation."""
    out = tmp_path / "one.gif"
    code = _run("export-anim", _image(tmp_path / "in.png"), out)
    assert code == EXIT_OK
    with PILImage.open(out) as handle:
        assert handle.n_frames == 1


def test_export_anim_video_passes_the_frames_and_fps(tmp_path: Path, monkeypatch) -> None:
    """The video branch hands every rendered frame and the fps to export_video."""
    folder = _frames(tmp_path / "frames")
    seen: dict[str, object] = {}

    def fake(frames: list[RGB8], path: Path, *, fps: int = 12) -> bool:
        seen["frames"] = len(frames)
        seen["fps"] = fps
        Path(path).write_bytes(b"video")
        return True

    monkeypatch.setattr(cli, "export_video", fake)
    out = tmp_path / "out.mp4"
    code = _run("export-anim", folder, out, "--fps", "6")
    assert code == EXIT_OK
    assert seen == {"frames": 3, "fps": 6}
    assert out.read_bytes() == b"video"


def test_export_anim_reports_a_missing_ffmpeg(tmp_path: Path, monkeypatch, capsys) -> None:
    """No ffmpeg is a render error with a one-line message, not a traceback."""
    folder = _frames(tmp_path / "frames")
    monkeypatch.setattr(cli, "export_video", lambda frames, path, *, fps=12: False)
    out = tmp_path / "out.mp4"
    code = _run("export-anim", folder, out)
    captured = capsys.readouterr()
    assert code == EXIT_RENDER
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert not out.exists()


@pytest.mark.parametrize("command", COMMANDS)
def test_missing_input_exits_two_without_a_traceback(command, tmp_path, capsys) -> None:
    """A missing input file gives exit 2 and a one-line message, never a traceback."""
    out = tmp_path / "out.bin"
    code = _run(command, tmp_path / "nope.png", out)
    captured = capsys.readouterr()
    assert code == EXIT_INPUT
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert not out.exists()


@pytest.mark.parametrize("command", COMMANDS)
def test_missing_preset_exits_two(command, tmp_path, capsys) -> None:
    """A missing preset file gives exit 2 and a one-line message."""
    image = _image(tmp_path / "in.png")
    out = tmp_path / "out.bin"
    code = main(
        [command, "--preset", str(tmp_path / "nope.json"), "--in", str(image), "--out", str(out)]
    )
    captured = capsys.readouterr()
    assert code == EXIT_INPUT
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert not out.exists()


def test_an_empty_frame_directory_exits_two(tmp_path: Path, capsys) -> None:
    """A frame directory with no image in it is an input error."""
    folder = tmp_path / "frames"
    folder.mkdir()
    code = _run("export-anim", folder, tmp_path / "out.gif")
    assert code == EXIT_INPUT
    assert "no frames" in capsys.readouterr().err


def test_json_reports_the_files_written(tmp_path: Path, capsys) -> None:
    """--json prints the §17 summary with the file written."""
    out = tmp_path / "out.svg"
    code = _run("export-svg", _image(tmp_path / "in.png"), out, "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload == {"ok": True, "files": [str(out)], "errors": []}


def test_json_reports_a_failure(tmp_path: Path, capsys) -> None:
    """--json prints ok false and the error on the failure path too."""
    code = _run("export-print", tmp_path / "nope.png", tmp_path / "out.png", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_INPUT
    assert payload["ok"] is False
    assert payload["files"] == []
    assert len(payload["errors"]) == 1


@pytest.mark.parametrize("extra", [["--cell", "0"], ["--cell", "abc"]])
def test_a_bad_cell_is_a_usage_error(extra, tmp_path, capsys) -> None:
    """A cell below 1, or not a number, exits 1 without a traceback."""
    image = _image(tmp_path / "in.png")
    code = _run("export-svg", image, tmp_path / "out.svg", *extra)
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "Traceback" not in captured.err


def test_a_bad_background_is_a_usage_error(tmp_path: Path, capsys) -> None:
    """A background that is not a hex colour exits 1 with a one-line message."""
    image = _image(tmp_path / "in.png")
    code = _run("export-svg", image, tmp_path / "out.svg", "--background", "not-a-colour")
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1


@pytest.mark.parametrize("extra", [["--dpi", "0"], ["--bleed-mm", "-1"]])
def test_bad_print_options_are_usage_errors(extra, tmp_path, capsys) -> None:
    """A dpi below 1, or a negative bleed, exits 1 without a traceback."""
    image = _image(tmp_path / "in.png")
    code = _run("export-print", image, tmp_path / "out.png", *extra)
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "Traceback" not in captured.err


def test_the_output_directory_is_created(tmp_path: Path) -> None:
    """A missing output directory is created rather than reported as an error."""
    out = tmp_path / "nested" / "deep" / "out.svg"
    code = _run("export-svg", _image(tmp_path / "in.png"), out)
    assert code == EXIT_OK
    assert out.is_file()


def test_max_side_renders_a_proxy(tmp_path: Path) -> None:
    """--max-side downscales the render before it is exported."""
    image = _image(tmp_path / "in.png", (96, 72))
    out = tmp_path / "out.svg"
    code = _run("export-svg", image, out, "--max-side", "24")
    assert code == EXIT_OK
    assert 'width="24"' in out.read_text(encoding="utf-8")
