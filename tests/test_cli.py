"""Tests for the command line and batch rendering (T22 / CONTRACT §17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image as PILImage

from lattice.modes.dither.cli import (
    EXIT_INPUT,
    EXIT_OK,
    EXIT_RENDER,
    EXIT_USAGE,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "data" / "baseline" / "source.png"
PRESET = ROOT / "presets" / "01_gameboy.json"
BROKEN_PARAMS = {
    "version": 1,
    "algorithm_id": "floyd_steinberg",
    "algorithm_params": {"not_a_parameter": 1},
    "palette": {"source": "builtin", "name": "bw"},
}


def _image(path: Path, size: tuple[int, int] = (48, 36)) -> Path:
    """Write a small test image and return its path."""
    with PILImage.open(SOURCE) as handle:
        handle.convert("RGB").resize(size, PILImage.LANCZOS).save(path)
    return path


def _preset(tmp_path: Path, payload: dict | None = None) -> Path:
    """Write a preset JSON file and return its path."""
    path = tmp_path / "preset.json"
    path.write_text(json.dumps(payload if payload is not None else json.loads(PRESET.read_text())))
    return path


def test_render_writes_the_output(tmp_path: Path) -> None:
    """A successful render exits 0 and creates the file."""
    out = tmp_path / "out.png"
    code = main(["render", "--preset", str(PRESET), "--in", str(_image(tmp_path / "a.png")),
                 "--out", str(out)])
    assert code == EXIT_OK
    assert out.is_file()


def test_missing_input_exits_two_without_a_traceback(tmp_path: Path, capsys) -> None:
    """A missing input file gives exit 2 and a one-line message, never a traceback."""
    code = main(["render", "--preset", str(PRESET), "--in", str(tmp_path / "nope.png"),
                 "--out", str(tmp_path / "out.png")])
    captured = capsys.readouterr()
    assert code == EXIT_INPUT
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1


def test_missing_preset_exits_two(tmp_path: Path) -> None:
    """An unreadable preset is an input error."""
    code = main(["info", "--preset", str(tmp_path / "nope.json")])
    assert code == EXIT_INPUT


def test_usage_error_exits_one(tmp_path: Path) -> None:
    """A missing required argument is a usage error, not argparse's exit 2."""
    assert main(["render", "--preset", str(PRESET)]) == EXIT_USAGE


def test_render_failure_exits_three(tmp_path: Path, capsys) -> None:
    """A preset that loads but cannot render gives exit 3 and no traceback."""
    preset = _preset(tmp_path, BROKEN_PARAMS)
    code = main(["render", "--preset", str(preset), "--in", str(_image(tmp_path / "a.png")),
                 "--out", str(tmp_path / "out.png")])
    captured = capsys.readouterr()
    assert code == EXIT_RENDER
    assert "Traceback" not in captured.err


def test_json_summary_parses(tmp_path: Path, capsys) -> None:
    """--json prints a summary with ok, files and errors."""
    out = tmp_path / "out.png"
    main(["render", "--preset", str(PRESET), "--in", str(_image(tmp_path / "a.png")),
          "--out", str(out), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["files"] == [str(out)]
    assert payload["errors"] == []


def test_json_summary_reports_errors(tmp_path: Path, capsys) -> None:
    """A failed render still prints a parseable summary with ok false."""
    main(["render", "--preset", str(PRESET), "--in", str(tmp_path / "nope.png"),
          "--out", str(tmp_path / "out.png"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["files"] == []
    assert len(payload["errors"]) == 1


def _batch(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    """Run a batch over two images and return the exit code and the output directory."""
    source_dir = tmp_path / "src"
    source_dir.mkdir(exist_ok=True)
    if not (source_dir / "a.png").exists():
        _image(source_dir / "a.png")
        _image(source_dir / "b.png", (32, 24))
    out_dir = tmp_path / "out"
    code = main(["batch", "--preset", str(PRESET), "--in-dir", str(source_dir),
                 "--out-dir", str(out_dir), *extra])
    return code, out_dir


def test_batch_writes_every_file(tmp_path: Path) -> None:
    """Batch renders each input and exits 0."""
    code, out_dir = _batch(tmp_path)
    assert code == EXIT_OK
    assert sorted(p.name for p in out_dir.iterdir()) == ["a.png", "b.png"]


def test_batch_skips_up_to_date_outputs(tmp_path: Path, capsys) -> None:
    """A second run skips the files it already wrote."""
    _batch(tmp_path)
    capsys.readouterr()
    code, _ = _batch(tmp_path)
    assert code == EXIT_OK
    assert "skip a.png" in capsys.readouterr().err


def test_batch_force_rewrites(tmp_path: Path, capsys) -> None:
    """--force rewrites an output that is already up to date."""
    _batch(tmp_path)
    capsys.readouterr()
    code, _ = _batch(tmp_path, "--force")
    assert code == EXIT_OK
    assert "skip" not in capsys.readouterr().err


def test_batch_jobs_four_matches_jobs_one(tmp_path: Path) -> None:
    """Parallel batch output is byte-identical to the sequential run."""
    serial_dir = tmp_path / "serial"
    parallel_dir = tmp_path / "parallel"
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    for index in range(4):
        _image(source_dir / f"i{index}.png", (40 + index, 30))
    for jobs, out_dir in ((1, serial_dir), (4, parallel_dir)):
        code = main(["batch", "--preset", str(PRESET), "--in-dir", str(source_dir),
                     "--out-dir", str(out_dir), "--jobs", str(jobs)])
        assert code == EXIT_OK
    names = sorted(p.name for p in serial_dir.iterdir())
    assert names == sorted(p.name for p in parallel_dir.iterdir())
    for name in names:
        assert (serial_dir / name).read_bytes() == (parallel_dir / name).read_bytes()


def test_batch_missing_directory_exits_two(tmp_path: Path) -> None:
    """A missing input directory is an input error."""
    code = main(["batch", "--preset", str(PRESET), "--in-dir", str(tmp_path / "nope"),
                 "--out-dir", str(tmp_path / "out")])
    assert code == EXIT_INPUT


def test_batch_extension_filter(tmp_path: Path) -> None:
    """--ext restricts which files are picked up."""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    _image(source_dir / "a.png")
    _image(source_dir / "b.jpg")
    out_dir = tmp_path / "out"
    code = main(["batch", "--preset", str(PRESET), "--in-dir", str(source_dir),
                 "--out-dir", str(out_dir), "--ext", "jpg"])
    assert code == EXIT_OK
    assert [p.name for p in out_dir.iterdir()] == ["b.png"]


def test_info_describes_the_preset(capsys) -> None:
    """info prints the algorithm, the palette and the effect chain without rendering."""
    assert main(["info", "--preset", str(PRESET)]) == EXIT_OK
    text = capsys.readouterr().out
    assert "algorithm:" in text
    assert "palette:" in text
    assert "effects:" in text


def test_info_json_parses(capsys) -> None:
    """info --json prints a structured description."""
    assert main(["info", "--preset", str(PRESET), "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["algorithm"]
    assert payload["palette"]["source"] == "builtin"
    assert isinstance(payload["post_effects"], list)


def test_info_lists_the_effect_chain(tmp_path: Path, capsys) -> None:
    """A preset with effects names them in the description."""
    payload = json.loads(PRESET.read_text())
    payload["post_effects"] = [{"effect_id": "glow", "params": {}, "enabled": True}]
    preset = _preset(tmp_path, payload)
    main(["info", "--preset", str(preset)])
    assert "glow" in capsys.readouterr().out


@pytest.mark.parametrize("command", ("render", "batch", "info"))
def test_help_exits_zero(command: str, capsys) -> None:
    """Every subcommand documents itself and exits 0."""
    assert main([command, "--help"]) == EXIT_OK
    assert "usage" in capsys.readouterr().out
