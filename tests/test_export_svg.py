"""Tests for the SVG export (CONTRACT §19)."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from lattice_dither.export.svg import export_svg

SVG_NS = "{http://www.w3.org/2000/svg}"
RUN = re.compile(r"M(\d+) (\d+)h(\d+)v(\d+)")
BLACK = np.array([0, 0, 0], dtype=np.uint8)
WHITE = np.array([255, 255, 255], dtype=np.uint8)


def _checker(size: int = 8) -> np.ndarray:
    """Return a size x size two-colour checkerboard."""
    parity = np.add.outer(np.arange(size), np.arange(size)) % 2
    return np.where(parity[:, :, None] == 0, BLACK, WHITE).astype(np.uint8)


def _blocks(size: int = 2048, step: int = 128, count: int = 16) -> np.ndarray:
    """Return a size x size image of count flat square blocks, one per colour."""
    grid = np.add.outer(np.arange(size) // step, np.arange(size) // step) % count
    return np.stack([grid * 16, grid * 8, grid * 4], axis=2).astype(np.uint8)


def _paths(path: Path) -> list[ET.Element]:
    """Return the path elements of the SVG at path."""
    return ET.parse(path).getroot().findall(f"{SVG_NS}path")


def _rasterise(path: Path, cell: int = 1) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Rebuild the index map of an SVG by parsing its rectangles, never rasterising."""
    root = ET.parse(path).getroot()
    width = int(root.get("width", "0")) // cell
    height = int(root.get("height", "0")) // cell
    indices = np.full((height, width), -1, dtype=np.int64)
    colors: list[tuple[int, int, int]] = []
    for element in root.findall(f"{SVG_NS}path"):
        fill = str(element.get("fill"))
        colors.append(tuple(int(fill[i : i + 2], 16) for i in (1, 3, 5)))
        for x, y, run, tall in RUN.findall(str(element.get("d"))):
            left, top = int(x) // cell, int(y) // cell
            indices[top : top + int(tall) // cell, left : left + int(run) // cell] = len(colors) - 1
    return indices, colors


def test_a_two_colour_image_produces_two_paths(tmp_path: Path) -> None:
    """One path element per distinct colour, no more."""
    target = tmp_path / "checker.svg"
    export_svg(_checker(), target)
    assert len(_paths(target)) == 2


def test_the_document_parses_and_carries_its_geometry(tmp_path: Path) -> None:
    """The SVG is valid XML with width, height and viewBox."""
    target = tmp_path / "checker.svg"
    export_svg(_checker(), target)
    root = ET.parse(target).getroot()
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("width") == "8"
    assert root.get("height") == "8"
    assert root.get("viewBox") == "0 0 8 8"


def test_every_path_is_crisp_and_filled(tmp_path: Path) -> None:
    """Each path carries its hex fill and the crispEdges hint."""
    target = tmp_path / "checker.svg"
    export_svg(_checker(), target)
    fills = {element.get("fill") for element in _paths(target)}
    assert fills == {"#000000", "#FFFFFF"}
    assert all(element.get("shape-rendering") == "crispEdges" for element in _paths(target))


def test_cell_multiplies_every_coordinate(tmp_path: Path) -> None:
    """cell=4 scales the geometry, the viewBox and every run by four."""
    plain, scaled = tmp_path / "plain.svg", tmp_path / "scaled.svg"
    export_svg(_checker(), plain)
    export_svg(_checker(), scaled, cell=4)
    root = ET.parse(scaled).getroot()
    assert (root.get("width"), root.get("height")) == ("32", "32")
    assert root.get("viewBox") == "0 0 32 32"
    for element in _paths(scaled):
        for x, y, run, tall in RUN.findall(str(element.get("d"))):
            assert int(tall) == 4
            assert int(x) % 4 == 0 and int(y) % 4 == 0 and int(run) % 4 == 0


def test_a_row_of_one_colour_is_a_single_run(tmp_path: Path) -> None:
    """Eight identical pixels on one row merge into one run, not eight."""
    image = np.zeros((1, 8, 3), dtype=np.uint8)
    target = tmp_path / "row.svg"
    export_svg(image, target)
    (element,) = _paths(target)
    assert RUN.findall(str(element.get("d"))) == [("0", "0", "8", "1")]


def test_parsing_the_rectangles_reproduces_the_input_indices(tmp_path: Path) -> None:
    """The runs rebuild the exact index map of the source image."""
    image = _checker(16)
    target = tmp_path / "checker.svg"
    export_svg(image, target)
    indices, colors = _rasterise(target)
    rebuilt = np.array(colors, dtype=np.uint8)[indices]
    assert np.array_equal(rebuilt, image)


def test_parsing_the_rectangles_survives_a_cell_factor(tmp_path: Path) -> None:
    """The same index map comes back when the document is scaled by cell."""
    image = _checker(16)
    target = tmp_path / "checker.svg"
    export_svg(image, target, cell=3)
    indices, colors = _rasterise(target, cell=3)
    rebuilt = np.array(colors, dtype=np.uint8)[indices]
    assert np.array_equal(rebuilt, image)


def test_a_background_rect_is_emitted_first(tmp_path: Path) -> None:
    """A background colour becomes a full-size rect before the paths."""
    target = tmp_path / "checker.svg"
    export_svg(_checker(), target, background="#123456")
    root = ET.parse(target).getroot()
    first = list(root)[0]
    assert first.tag == f"{SVG_NS}rect"
    assert first.get("fill") == "#123456"
    assert (first.get("width"), first.get("height")) == ("8", "8")


def test_no_background_rect_by_default(tmp_path: Path) -> None:
    """Without a background the document holds paths only."""
    target = tmp_path / "checker.svg"
    export_svg(_checker(), target)
    assert ET.parse(target).getroot().findall(f"{SVG_NS}rect") == []


def test_a_large_flat_image_stays_within_the_budget(tmp_path: Path) -> None:
    """2048x2048 with 16 colours stays under 8 MB and finishes under 5 s.

    The budget is measured on flat, low-colour content, which is what a vector export is
    for. A high-entropy 2048x2048 image cannot meet it with horizontal runs alone; the
    measurement is recorded in DEV-106.
    """
    target = tmp_path / "blocks.svg"
    started = time.perf_counter()
    export_svg(_blocks(), target)
    elapsed = time.perf_counter() - started
    assert target.stat().st_size < 8 * 1024 * 1024
    assert elapsed < 5.0


def test_a_single_colour_image_is_one_path(tmp_path: Path) -> None:
    """A flat image collapses to one path with one run per row."""
    target = tmp_path / "flat.svg"
    export_svg(np.zeros((4, 6, 3), dtype=np.uint8), target)
    (element,) = _paths(target)
    assert len(RUN.findall(str(element.get("d")))) == 4


def test_an_invalid_shape_raises(tmp_path: Path) -> None:
    """A non-RGB array is rejected before anything is written."""
    with pytest.raises(ValueError, match="expected an"):
        export_svg(np.zeros((4, 4), dtype=np.uint8), tmp_path / "x.svg")


def test_an_invalid_cell_raises(tmp_path: Path) -> None:
    """cell below one is rejected."""
    with pytest.raises(ValueError, match="cell"):
        export_svg(_checker(), tmp_path / "x.svg", cell=0)


def test_an_empty_image_raises(tmp_path: Path) -> None:
    """A zero-sized image is rejected."""
    with pytest.raises(ValueError, match="empty"):
        export_svg(np.zeros((0, 4, 3), dtype=np.uint8), tmp_path / "x.svg")


def test_an_invalid_background_raises(tmp_path: Path) -> None:
    """A background that is not a colour is rejected."""
    with pytest.raises(ValueError, match="invalid colour"):
        export_svg(_checker(), tmp_path / "x.svg", background="nope")
