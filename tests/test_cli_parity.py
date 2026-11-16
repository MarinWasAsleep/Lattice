"""Gate G6: the CLI and the pipeline produce byte-identical renders."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage

import lattice_core.dither  # noqa: F401
import lattice_core.effects  # noqa: F401
from lattice_core import color
from lattice_core.pipeline import render
from lattice_core.presets import load_preset
from lattice_dither.cli import EXIT_OK, main

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "data" / "baseline" / "source.png"
PRESETS = ("01_gameboy", "04_halftone_print", "07_grey16_stucki")
SIZES = ((96, 72), (61, 47))


def _images(tmp_path: Path) -> list[Path]:
    """Write the two test images and return their paths."""
    paths = []
    with PILImage.open(SOURCE) as handle:
        source = handle.convert("RGB")
        for index, size in enumerate(SIZES):
            path = tmp_path / f"in{index}.png"
            source.resize(size, PILImage.LANCZOS).save(path)
            paths.append(path)
    return paths


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("index", range(len(SIZES)))
def test_cli_render_matches_the_pipeline(preset: str, index: int, tmp_path: Path) -> None:
    """The CLI writes exactly the bytes a direct pipeline.render call produces."""
    image = _images(tmp_path)[index]
    spec = load_preset(ROOT / "presets" / f"{preset}.json")
    expected = tmp_path / "expected.png"
    color.to_pil(render(color.to_float(PILImage.open(image)), spec)).save(
        expected, format="PNG"
    )
    produced = tmp_path / "produced.png"
    code = main(
        [
            "render",
            "--preset",
            str(ROOT / "presets" / f"{preset}.json"),
            "--in",
            str(image),
            "--out",
            str(produced),
        ]
    )
    assert code == EXIT_OK
    assert produced.read_bytes() == expected.read_bytes()


@pytest.mark.parametrize("preset", PRESETS)
def test_batch_matches_the_pipeline(preset: str, tmp_path: Path) -> None:
    """Every file a batch run writes is byte-identical to a direct render."""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    for image in _images(tmp_path):
        image.rename(source_dir / image.name)
    out_dir = tmp_path / "out"
    code = main(
        [
            "batch",
            "--preset",
            str(ROOT / "presets" / f"{preset}.json"),
            "--in-dir",
            str(source_dir),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == EXIT_OK
    spec = load_preset(ROOT / "presets" / f"{preset}.json")
    for image in sorted(source_dir.iterdir()):
        expected = tmp_path / f"expected_{image.stem}.png"
        color.to_pil(render(color.to_float(PILImage.open(image)), spec)).save(
            expected, format="PNG"
        )
        assert (out_dir / f"{image.stem}.png").read_bytes() == expected.read_bytes()
