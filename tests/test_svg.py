"""Tests for the SVG export of a CellGrid (card L11, §11, H11).

The document is verified by parsing, never by launching a browser: a document that
``xml.etree.ElementTree`` reads back, whose rectangles cover every cell exactly once and
whose colours are the palette's, is a document Inkscape, Illustrator and a browser open
without repair. Expected geometry is pinned as literals derived from the contract.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

import lattice_core.renderers  # noqa: F401  (registers the built-in renderers)
from lattice_core.cell import CellGrid, RenderStyle, get_renderer
from lattice_core.svg import (
    DEFAULT_MAX_BYTES,
    SVG_NS,
    render_svg,
)
from lattice_core.svg import _box_count as box_count
from lattice_core.svg import _encode as encode
from lattice_core.svg import _palette_codes as palette_codes
from lattice_core.svg import _rects as cell_rects
from lattice_core.types import Palette

NS = f"{{{SVG_NS}}}"
BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
FOUR: Palette = np.array(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32
)
CELL_W, CELL_H = 8, 16


def _grid(index: np.ndarray, cell_w: int = 1, cell_h: int = 1,
          luma: np.ndarray | None = None, subindex: np.ndarray | None = None,
          samples_k: int = 1) -> CellGrid:
    """Build a CellGrid with the given palette indices, luma ramp and sample stencil size."""
    rows, cols = index.shape
    shape = (rows, cols)
    return CellGrid(
        cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
        index=np.asarray(index, dtype=np.int32),
        coverage=np.full(shape, 0.5, dtype=np.float32),
        luma=np.asarray(luma, dtype=np.float32) if luma is not None else np.full(
            shape, 0.5, dtype=np.float32),
        samples=np.full(shape + (samples_k,), 0.5, dtype=np.float32),
        subindex=subindex,
    )


def _ramp(rows: int, cols: int) -> np.ndarray:
    """Return a left-to-right luma ramp from 0 to 1, the whole glyph ramp being used."""
    return np.tile(np.linspace(0.0, 1.0, cols, dtype=np.float32), (rows, 1))


def _root(svg: str) -> ET.Element:
    """Parse the document, as a browser would, and return its root element."""
    return ET.fromstring(svg)


def _rects(svg: str) -> list[ET.Element]:
    """Return the rectangle elements of the document, in document order."""
    return _root(svg).findall(f"{NS}rect")


def _texts(svg: str) -> list[ET.Element]:
    """Return the text elements of the document, in document order."""
    return _root(svg).findall(f"{NS}text")


def _painting(svg: str, cell_w: int = 1, cell_h: int = 1) -> np.ndarray:
    """Rebuild the (rows, cols) fill of every cell by reading the rectangles, never rasterising."""
    root = _root(svg)
    width = int(root.get("width", "0")) // cell_w
    height = int(root.get("height", "0")) // cell_h
    cells = np.full((height, width), "", dtype=object)
    for element in root.findall(f"{NS}rect"):
        left = int(element.get("x", "0")) // cell_w
        top = int(element.get("y", "0")) // cell_h
        run = int(element.get("width", "0")) // cell_w
        tall = int(element.get("height", "0")) // cell_h
        cells[top : top + tall, left : left + run] = str(element.get("fill"))
    return cells


def _expected(grid: CellGrid, palette: Palette) -> np.ndarray:
    """Return the #rrggbb string of every cell's palette colour."""
    rgb = np.floor(np.clip(np.asarray(palette, np.float32)[grid.index, :3], 0.0, 1.0)
                   * 255.0 + 0.5).astype(np.int32)
    return np.array([[f"#{r:02x}{g:02x}{b:02x}" for r, g, b in row] for row in rgb], dtype=object)


# --- accept: the output parses as XML and has the right root namespace ---


def test_the_document_parses_with_the_svg_namespace() -> None:
    svg, warnings = render_svg(_grid(np.zeros((4, 4), np.int32)), BW, get_renderer("pixel"))
    root = _root(svg)
    assert root.tag == f"{NS}svg"
    assert root.get("xmlns") is None  # the namespace is the tag's, not an attribute
    assert warnings == []


def test_the_root_carries_the_exact_output_geometry() -> None:
    grid = _grid(np.zeros((3, 5), np.int32), cell_w=CELL_W, cell_h=CELL_H)
    svg, _ = render_svg(grid, BW, get_renderer("pixel"))
    root = _root(svg)
    assert root.get("width") == "40"
    assert root.get("height") == "48"
    assert root.get("viewBox") == "0 0 40 48"


def test_the_document_round_trips_through_a_file(tmp_path: Path) -> None:
    svg, _ = render_svg(_grid(np.zeros((2, 3), np.int32)), BW, get_renderer("pixel"))
    target = tmp_path / "out.svg"
    target.write_text(svg, encoding="utf-8")
    assert ET.parse(target).getroot().tag == f"{NS}svg"


# --- accept: a 64x64 pixel render produces fewer <rect> elements than cells (runs merged) ---


def test_a_64x64_pixel_render_merges_its_runs() -> None:
    blocks = (np.add.outer(np.arange(64) // 4, np.arange(64) // 4) % 2).astype(np.int32)
    svg, warnings = render_svg(_grid(blocks), BW, get_renderer("pixel"))
    assert len(_rects(svg)) < 64 * 64
    assert warnings == []


def test_a_flat_pixel_render_is_a_single_rectangle() -> None:
    svg, _ = render_svg(_grid(np.zeros((16, 16), np.int32)), BW, get_renderer("pixel"))
    rects = _rects(svg)
    assert len(rects) == 1
    assert rects[0].get("width") == "16"
    assert rects[0].get("height") == "16"


def test_every_cell_is_painted_exactly_its_palette_colour() -> None:
    index = (np.add.outer(np.arange(9) // 3, np.arange(9) // 3) % 4).astype(np.int32)
    grid = _grid(index)
    svg, _ = render_svg(grid, FOUR, get_renderer("pixel"))
    painted = _painting(svg)
    assert (painted != "").all()  # no cell left unpainted, no cell painted twice
    assert (painted == _expected(grid, FOUR)).all()


def test_runs_merge_downwards_as_well_as_across() -> None:
    index = np.zeros((8, 8), np.int32)
    index[:4] = 1  # two horizontal bands: two rectangles, not eight rows
    svg, _ = render_svg(_grid(index), BW, get_renderer("pixel"))
    assert len(_rects(svg)) == 2


# --- accept: a glyph render produces exactly cols * rows <text> elements ---


@pytest.mark.parametrize("name", ["glyph_ramp", "glyph_shape", "braille", "sextant"])
def test_a_glyph_render_has_one_text_element_per_cell(name: str) -> None:
    renderer = get_renderer(name)
    sx, sy = renderer.subgrid()
    subindex = None if sx * sy == 1 else np.zeros((4, 6, sx * sy), np.int32)
    grid = _grid(np.zeros((4, 6), np.int32), CELL_W, CELL_H,
                 luma=_ramp(4, 6), subindex=subindex, samples_k=6)
    svg, warnings = render_svg(grid, BW, renderer,
                               RenderStyle(options={"text": "Lattice glyph export"}))
    assert len(_texts(svg)) == 4 * 6
    assert warnings == []


def test_a_text_element_carries_its_typography_and_ink() -> None:
    grid = _grid(np.zeros((2, 3), np.int32), CELL_W, CELL_H, luma=_ramp(2, 3))
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
    element = _texts(svg)[0]
    assert element.get("font-family") == "monospace"
    assert element.get("font-size") == str(CELL_H)
    assert element.get("fill") == "#000000"
    assert element.get("x") == "0"
    assert float(element.get("y", "0")) == pytest.approx(0.8 * CELL_H)


def test_the_glyph_text_is_the_renderer_layout() -> None:
    grid = _grid(np.zeros((3, 4), np.int32), CELL_W, CELL_H, luma=_ramp(3, 4))
    renderer = get_renderer("glyph_ramp")
    svg, _ = render_svg(grid, BW, renderer)
    placed = [glyph.character
              for glyph in renderer.layout(grid, RenderStyle(options={}))]  # type: ignore
    assert [element.text for element in _texts(svg)] == placed


def test_the_paper_is_painted_behind_the_glyphs() -> None:
    grid = _grid(np.zeros((2, 2), np.int32), CELL_W, CELL_H, luma=_ramp(2, 2))
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
    children = list(_root(svg))
    rects = [child for child in children if child.tag == f"{NS}rect"]
    texts = [child for child in children if child.tag == f"{NS}text"]
    assert len(rects) == 1  # a uniform paper merges into one rectangle
    assert rects[0].get("fill") == "#ffffff"
    assert children[: len(rects)] == rects  # paper first, glyphs painted over it
    assert len(texts) == 4


def test_a_translucent_paper_carries_its_opacity() -> None:
    grid = _grid(np.zeros((1, 1), np.int32), CELL_W, CELL_H)
    style = RenderStyle(options={"bg": "#ffffff80"})
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
    assert _rects(svg)[0].get("fill-opacity") == "0.5"


def test_glyph_text_is_escaped() -> None:
    luma = np.array([[0.0, 1.0]], dtype=np.float32)
    grid = _grid(np.zeros((1, 2), np.int32), CELL_W, CELL_H, luma=luma)
    style = RenderStyle(options={"ramp": "<&"})
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
    assert [element.text for element in _texts(svg)] == ["<", "&"]
    assert "&lt;" in svg and "&amp;" in svg


def test_the_font_option_names_the_font_family() -> None:
    grid = _grid(np.zeros((1, 1), np.int32), CELL_W, CELL_H)
    style = RenderStyle(options={"font": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"})
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
    assert _texts(svg)[0].get("font-family") == "DejaVuSansMono"


# --- accept: the 8 MB budget triggers a merge and a warning on a large render ---


def _noise(size: int, colours: int = 16) -> np.ndarray:
    """Return a size x size grid of pseudo-random palette indices, so runs never merge."""
    rng = np.random.default_rng(0)
    return rng.integers(0, colours, size=(size, size), dtype=np.int32)


def _palette16() -> Palette:
    """Return sixteen evenly spaced colours, so every index is a distinct RGB."""
    steps = np.linspace(0.0, 1.0, 16, dtype=np.float32)
    return np.stack([steps, 1.0 - steps, steps * 0.5], axis=1).astype(np.float32)


def test_a_2048_pixel_render_stays_under_the_default_budget() -> None:
    grid = _grid(_noise(2048), cell_w=1, cell_h=1)
    svg, warnings = render_svg(grid, _palette16(), get_renderer("pixel"))
    assert len(svg.encode("utf-8")) <= DEFAULT_MAX_BYTES
    assert warnings and "8000000-byte budget" in warnings[0]
    assert "blocks" in warnings[0]


def test_the_budget_warning_names_the_merge_that_was_applied() -> None:
    svg, warnings = render_svg(
        _grid(_noise(32)), _palette16(), get_renderer("pixel"), max_bytes=4000
    )
    assert len(svg.encode("utf-8")) <= 4000
    assert len(warnings) == 1
    assert "budget" in warnings[0]


def test_a_glyph_render_over_budget_degrades_to_rectangles() -> None:
    grid = _grid(_noise(48), CELL_W, CELL_H, luma=_ramp(48, 48))
    svg, warnings = render_svg(grid, _palette16(), get_renderer("glyph_ramp"),
                               max_bytes=100_000)
    assert len(_texts(svg)) == 0
    assert len(_rects(svg)) > 0
    assert warnings and "glyphs merged into cell rectangles" in warnings[0]
    assert len(svg.encode("utf-8")) <= 100_000


def test_the_degraded_glyph_rectangles_keep_the_cell_ink() -> None:
    grid = _grid(np.zeros((4, 4), np.int32), CELL_W, CELL_H, luma=np.zeros((4, 4), np.float32))
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), max_bytes=120)
    rects = _rects(svg)
    fills = {element.get("fill") for element in rects}
    assert fills == {"#000000", "#ffffff"}  # paper then ink, not one flat colour
    ink = [element for element in rects if element.get("fill") == "#000000"]
    assert ink and all(element.get("fill-opacity") == "0.5" for element in ink)


def test_a_budget_too_small_for_anything_is_reported_not_crashed() -> None:
    grid = _grid(_noise(8), CELL_W, CELL_H, luma=_ramp(8, 8))
    svg, warnings = render_svg(grid, _palette16(), get_renderer("glyph_ramp"), max_bytes=40)
    assert warnings
    assert _root(svg).tag == f"{NS}svg"


def no_text(svg: str) -> bool:
    """Return True when the document carries no glyph, i.e. it was degraded to rectangles."""
    return _texts(svg) == []


def test_a_large_structured_render_keeps_its_runs_and_is_not_degraded() -> None:
    blocks = (((np.arange(512) // 32)[:, None] + (np.arange(512) // 32)[None, :]) % 16)
    svg, warnings = render_svg(_grid(blocks.astype(np.int32)), _palette16(),
                               get_renderer("pixel"))
    assert warnings == []  # 16x16 blocks merge into 256 rectangles, far under the cap
    assert len(_rects(svg)) == 256


def test_a_glyph_export_over_budget_merges_cells_rather_than_blocks() -> None:
    grid = _grid(np.zeros((32, 32), np.int32), CELL_W, CELL_H)
    svg, warnings = render_svg(grid, BW, get_renderer("glyph_ramp"), max_bytes=600)
    assert no_text(svg) and _rects(svg)
    assert warnings and "budget" in warnings[0]
    assert len(svg.encode("utf-8")) <= 600


def test_the_rectangle_count_matches_the_emitted_rectangles() -> None:
    grid = _grid(_noise(64, colours=4))
    ids, paints = encode(palette_codes(grid, _palette16()[:4]))
    assert box_count(ids) == len(cell_rects(ids, paints, 1, 1))


def test_a_non_positive_budget_is_refused() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        render_svg(_grid(np.zeros((1, 1), np.int32)), BW, get_renderer("pixel"), max_bytes=0)


# --- accept: the file opens in a browser without repair (parsing, not launching) ---


def test_a_glyph_document_is_well_formed_and_complete() -> None:
    grid = _grid(np.zeros((6, 6), np.int32), CELL_W, CELL_H, luma=_ramp(6, 6))
    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
    root = _root(svg)
    assert root.tag == f"{NS}svg"
    assert root.get("viewBox") == f"0 0 {6 * CELL_W} {6 * CELL_H}"
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert len(_texts(svg)) == 36


# --- invariants: purity, no mutation, no application import ---


def test_render_svg_is_pure() -> None:
    grid = _grid(_noise(8), CELL_W, CELL_H, luma=_ramp(8, 8))
    renderer = get_renderer("glyph_ramp")
    assert render_svg(grid, BW, renderer) == render_svg(grid, BW, renderer)


def test_render_svg_does_not_mutate_its_inputs() -> None:
    index = _noise(8)
    grid = _grid(index, CELL_W, CELL_H, luma=_ramp(8, 8))
    before_index, before_luma = grid.index.copy(), grid.luma.copy()
    render_svg(grid, BW, get_renderer("glyph_ramp"))
    assert (grid.index == before_index).all()
    assert (grid.luma == before_luma).all()
    assert np.asarray(BW).tolist() == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]


def test_the_export_modules_import_no_application_and_no_qt() -> None:
    import ast

    root = Path(__file__).resolve().parents[1] / "lattice_core"
    forbidden = {"lattice_dither", "lattice_glyph", "lattice_glitch", "PySide6"}
    for name in ("svg.py", "textout.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden), f"{name} imports {imported & forbidden}"
