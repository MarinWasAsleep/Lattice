"""Tests for the bitmask renderer family (L8, §3 §9, contract 0.1.0)."""

from __future__ import annotations

import unicodedata

import numpy as np
import pytest

import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
from lattice_core.cell import (
    CellGrid,
    CellRenderer,
    RenderStyle,
    get_renderer,
    list_renderers,
)
from lattice_core.pipeline import PipelineSpec, render_with_palette
from lattice_core.renderers.bitmask import (
    _HALF_BLOCK_CODEPOINTS,
    _QUADRANT_CODEPOINTS,
    _SEXTANT_CODEPOINTS,
    register_bitmask_renderers,
)

BW: np.ndarray = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
# (geometry, sx, sy, sub-point count) — the documented sub-cell counts (§9).
GEOMETRIES: dict[str, tuple[int, int, int]] = {
    "braille": (2, 4, 8),
    "sextant": (2, 3, 6),
    "quadrant": (2, 2, 4),
    "half_block": (1, 2, 2),
}
# The all-ink codepoint of each geometry (E1: sextant/quadrant/half_block
# express "full" with U+2588 FULL BLOCK; braille with U+28FF).
FULL: dict[str, int] = {
    "braille": 0x28FF, "sextant": 0x2588, "quadrant": 0x2588,
    "half_block": 0x2588,
}
# The all-paper codepoint (empty or background, E1 for the three geometries
# whose block has no blank glyph: U+0020).
EMPTY: dict[str, int] = {
    "braille": 0x2800, "sextant": 0x20, "quadrant": 0x20, "half_block": 0x20,
}


def _style(**options) -> RenderStyle:
    """Return a RenderStyle carrying the given JSON-serialisable options."""
    return RenderStyle(options=options)


def _grid(geometry: str, subindex: np.ndarray, rows: int = 1, cols: int = 1,
          cell_w: int = 2, cell_h: int = 4) -> CellGrid:
    """Build a CellGrid whose sub-points carry the given palette indices."""
    sx, sy, count = GEOMETRIES[geometry]
    if subindex.ndim == 1:
        if subindex.size == count:
            filled = np.broadcast_to(
                np.asarray(subindex, dtype=np.int32).reshape(1, 1, count),
                (rows, cols, count),
            ).copy()
        else:
            filled = np.asarray(subindex, dtype=np.int32).reshape(rows, cols, count)
    else:
        filled = np.asarray(subindex, dtype=np.int32)
    if filled.shape != (rows, cols, count):
        raise ValueError(f"subindex shape {filled.shape} != {(rows, cols, count)}")
    return CellGrid(
        cols=cols,
        rows=rows,
        cell_w=cell_w,
        cell_h=cell_h,
        index=np.zeros((rows, cols), dtype=np.int32),
        coverage=np.full((rows, cols), 0.5, dtype=np.float32),
        luma=np.full((rows, cols), 0.5, dtype=np.float32),
        samples=np.full((rows, cols, count), 0.5, dtype=np.float32),
        subindex=filled,
    )


def _all_patterns(geometry: str) -> list[np.ndarray]:
    """Return one subindex row per possible sub-point pattern (0..2^count)."""
    _, _, count = GEOMETRIES[geometry]
    return [np.array([(mask >> k) & 1 for k in range(count)], dtype=np.int32)
            for mask in range(1 << count)]


# --- accept: the four geometries expose the documented sub-cell counts ---


@pytest.mark.parametrize(("name", "sx", "sy", "count"),
                         sorted((n, *g) for n, g in GEOMETRIES.items()))
def test_geometry_subcell_counts(name, sx, sy, count):
    renderer = get_renderer(name)
    assert renderer.subgrid() == (sx, sy)
    assert renderer.cell_aspect() == pytest.approx(sx / sy)


# --- accept: black cell → full codepoint, white cell → empty codepoint ---


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_black_cell_produces_the_full_codepoint(name):
    sx, sy, count = GEOMETRIES[name]
    grid = _grid(name, np.zeros(count, dtype=np.int32))
    codepoint = int(get_renderer(name).codepoints(grid, BW, _style())[0, 0])
    assert codepoint == FULL[name]
    assert codepoint == ord(get_renderer(name).layout(grid, BW, _style())[0][0])


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_white_cell_produces_the_empty_codepoint(name):
    sx, sy, count = GEOMETRIES[name]
    grid = _grid(name, np.ones(count, dtype=np.int32))
    codepoint = int(get_renderer(name).codepoints(grid, BW, _style())[0, 0])
    assert codepoint == EMPTY[name]


# --- accept: threshold 0.5 on a half-black cell → a half-filled codepoint ---


@pytest.mark.parametrize(("name", "half"), [("braille", 4), ("sextant", 3),
                                            ("quadrant", 2), ("half_block", 1)])
def test_half_black_cell_is_half_filled(name, half):
    tables = {"sextant": _SEXTANT_CODEPOINTS, "quadrant": _QUADRANT_CODEPOINTS,
              "half_block": _HALF_BLOCK_CODEPOINTS}
    _, _, count = GEOMETRIES[name]
    subindex = np.array([0] * half + [1] * (count - half), dtype=np.int32)
    grid = _grid(name, subindex)
    codepoint = int(get_renderer(name).codepoints(grid, BW, _style(threshold=0.5))[0, 0])
    if name == "braille":
        assert bin(codepoint - 0x2800).count("1") == half
    else:
        mask_value = (1 << half) - 1  # the first `half` sub-points are ink
        assert codepoint == tables[name][mask_value]
    img = np.asarray(get_renderer(name).render(grid, BW, _style(threshold=0.5)))
    # ink dots and paper both survive the rasterisation of a half-filled cell.
    assert (img == 0).any() and (img == 255).any()
    assert (img[:, :, 0] == img[:, :, 1]).all()


# --- accept (S3): the pattern follows the algorithm's subgrid decision ---


def test_pattern_packs_subindex_not_samples():
    renderer = get_renderer("braille")
    # Mid-grey samples (0.5 at threshold 0.5 would threshold to all-paper);
    # the sub-points keep an explicit checkerboard from the algorithm.
    subindex = np.array([0, 1, 1, 0, 0, 1, 1, 0], dtype=np.int32)
    grid = _grid("braille", subindex)
    expected = 0x2800 + 0x01 + 0x10 + 0x04 + 0x80  # k in (0, 3, 4, 7)
    assert int(renderer.codepoints(grid, BW, _style(threshold=0.5))[0, 0]) == expected
    frame = renderer.render_frame(grid, BW, _style(threshold=0.5))
    assert frame.shape == (4, 2, 3)  # dots follow the same k-order as subindex


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_mid_grey_cell_is_deterministic(name):
    grid = _grid(name, np.array([0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1][:GEOMETRIES[name][2]],
                                dtype=np.int32))
    renderer = get_renderer(name)
    first = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
    second = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
    assert np.array_equal(first, second)


def test_removed_dither_option_changes_nothing():
    grid = _grid("braille", np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int32))
    renderer = get_renderer("braille")
    plain = np.asarray(renderer.render(grid, BW, _style(threshold=0.5)))
    with_dither = np.asarray(renderer.render(grid, BW, _style(threshold=0.5, dither=True)))
    assert np.array_equal(plain, with_dither)


# --- accept: every emitted codepoint is a valid scalar, in the documented range ---


_DOCUMENTED = {
    "braille": lambda cp: 0x2800 <= cp <= 0x28FF,
    "sextant": lambda cp: cp in (0x20, 0x2588) or 0x1FB00 <= cp <= 0x1FB3B,
    "quadrant": lambda cp: cp in (0x20, 0x2580, 0x2584, 0x2588, 0x258C, 0x2590)
    or 0x2596 <= cp <= 0x259F,
    "half_block": lambda cp: cp in (0x20, 0x2580, 0x2584, 0x2588),
}


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_every_emitted_codepoint_is_valid_and_documented(name):
    renderer = get_renderer(name)
    for subindex in _all_patterns(name):
        grid = _grid(name, subindex)
        codepoint = int(renderer.codepoints(grid, BW, _style())[0, 0])
        assert 0 < codepoint <= 0x10FFFF
        assert not 0xD800 <= codepoint <= 0xDFFF
        assert _DOCUMENTED[name](codepoint), (name, subindex, hex(codepoint))


def test_sextant_table_matches_unicode_names():
    """Derive the dot numbering from Unicode names, never from the table.

    BLOCK SEXTANT names are row-major: dot 1=top-left, 2=top-right,
    3=middle-left, 4=middle-right, 5=bottom-left, 6=bottom-right. The table
    must agree for every expressible pattern; the four patterns the block
    cannot express must use the documented stand-ins. A transposed table
    fails on mask 2 (top-right: SEXTANT-2, not SEXTANT-4) or the missing mask
    set {0, 21, 42, 63}.
    """
    if unicodedata.unidata_version < "13.0":
        pytest.skip(f"needs Unicode >= 13.0, got {unicodedata.unidata_version}")
    present = {}
    for cp in range(0x1FB00, 0x1FB3C):
        name = unicodedata.name(chr(cp))
        if "SEXTANT-" not in name:
            continue
        mask = sum(1 << (int(d) - 1) for d in name.split("SEXTANT-")[1])
        assert mask not in present, (mask, hex(cp))
        present[mask] = cp
    # 60 of the 64 patterns exist in U+1FB00..U+1FB3B; the block lacks empty,
    # full, and the two solid columns {1,3,5}/{2,4,6} (row-major dots).
    assert set(present) == set(range(64)) - {0, 21, 42, 63}, \
        sorted(set(range(64)) - set(present))
    for mask, cp in present.items():
        assert _SEXTANT_CODEPOINTS[mask] == cp, (mask, hex(cp))
    # Documented stand-ins (E1): empty, full, and 3-dot column approximations.
    assert _SEXTANT_CODEPOINTS[0] == 0x0020
    assert _SEXTANT_CODEPOINTS[63] == 0x2588
    assert _SEXTANT_CODEPOINTS[21] == 0x1FB06  # SEXTANT-123, upper two-thirds
    assert _SEXTANT_CODEPOINTS[42] == 0x1FB0A  # SEXTANT-124, its mirror
    # Single-dot positional guards: mask bit k = dot k+1 (identity, row-major).
    assert [_SEXTANT_CODEPOINTS[1 << k] for k in range(6)] == [
        0x1FB00, 0x1FB01, 0x1FB03, 0x1FB07, 0x1FB0F, 0x1FB1E]


def test_degenerate_palette_renders_all_paper():
    """A zero-luminance-range palette has no contrast: all sub-dots stay paper.

    Matches the pipeline's _coverage_table convention (coverage 0 = no ink);
    the previous behaviour rel = 0 < threshold turned every cell into the
    all-ink codepoint.
    """
    flat = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
    for name in sorted(GEOMETRIES):
        renderer = get_renderer(name)
        grid = _grid(name, np.zeros(GEOMETRIES[name][2], dtype=np.int32))
        codepoint = int(renderer.codepoints(grid, flat, _style(threshold=0.5))[0, 0])
        assert codepoint == EMPTY[name], name
        assert (np.asarray(renderer.render(grid, flat, _style())) == 255).all(), name


def test_quadrant_codepoint_names():
    from lattice_core.renderers.bitmask import _QUADRANT_CODEPOINTS
    quadrants = {
        "UPPER LEFT": 0x1, "UPPER RIGHT": 0x2, "LOWER LEFT": 0x4,
        "LOWER RIGHT": 0x8,
    }
    blocks = {0x2580: 0b0011, 0x258C: 0b0101, 0x2590: 0b1010,
              0x2584: 0b1100, 0x2588: 0b1111}
    for mask, cp in enumerate(_QUADRANT_CODEPOINTS):
        if cp == 0x20:
            assert mask == 0
            continue
        if cp in blocks:
            assert blocks[cp] == mask, (mask, hex(cp))
            continue
        assert 0x2596 <= cp <= 0x259F, (mask, hex(cp))
        name = unicodedata.name(chr(cp))
        expected = 0
        for word, bit in quadrants.items():
            if word in name:
                expected |= bit
        assert expected == mask, (mask, hex(cp), name)


# --- §3 invariants ---


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_render_size_matches_grid_geometry(name):
    renderer = get_renderer(name)
    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 6)
    grid = _grid(name, subindex, rows=3, cols=2, cell_w=2, cell_h=4)
    assert renderer.render(grid, BW, _style()).size == (2 * 2, 3 * 4)
    frame = renderer.render_frame(grid, BW, _style())
    assert frame.shape == (3 * 4, 2 * 2, 3)


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_render_is_pure_and_mutates_nothing(name):
    renderer = get_renderer(name)
    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 4)
    grid = _grid(name, subindex, rows=2, cols=2)
    palette = BW.copy()
    snapshot = grid.subindex.copy()
    first = np.asarray(renderer.render(grid, palette, _style(threshold=0.4)))
    second = np.asarray(renderer.render(grid, palette, _style(threshold=0.4)))
    assert np.array_equal(first, second)
    assert np.array_equal(grid.subindex, snapshot)
    assert np.array_equal(palette, BW)


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_render_frame_matches_render(name):
    renderer = get_renderer(name)
    subindex = np.tile(np.arange(GEOMETRIES[name][2], dtype=np.int32) % 2, 4)
    grid = _grid(name, subindex, rows=2, cols=2, cell_w=3, cell_h=2)
    frame = renderer.render_frame(grid, BW, _style())
    rounded = np.floor(np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    assert np.array_equal(rounded, np.asarray(renderer.render(grid, BW, _style())))


def test_registered_under_geometry_names_and_contract_protocol():
    for name in GEOMETRIES:
        renderer = get_renderer(name)
        assert isinstance(renderer, CellRenderer)
        assert renderer.name == name
    assert set(GEOMETRIES) <= set(list_renderers())
    assert len({get_renderer(name).name for name in GEOMETRIES}) == len(GEOMETRIES)
    with pytest.raises(ValueError):
        register_bitmask_renderers()  # duplicate names


def test_layout_positions_match_codepoints():
    renderer = get_renderer("braille")
    subindex = np.tile(np.arange(8, dtype=np.int32) % 2, 4).reshape(2, 2, 8)
    grid = _grid("braille", subindex, rows=2, cols=2, cell_w=2, cell_h=4)
    placed = renderer.layout(grid, BW, _style(fg="#ff0000"))
    assert len(placed) == 4
    for cell, (char, x, y, width, height, fill) in enumerate(placed):
        expected_char = int(
            renderer.codepoints(grid, BW, _style(fg="#ff0000"))[cell // 2, cell % 2]
        )
        assert char == chr(expected_char)
        assert (x, y) == ((cell % 2) * 2, (cell // 2) * 4)
        assert (width, height) == (2, 4)
        assert fill == "#ff0000"


# --- options ---


def test_option_validation():
    grid = _grid("braille", np.zeros(8, dtype=np.int32))
    renderer = get_renderer("braille")
    with pytest.raises(ValueError, match="threshold"):
        renderer.render(grid, BW, _style(threshold=1.5))
    with pytest.raises(ValueError, match="threshold"):
        renderer.render(grid, BW, _style(threshold=-0.1))
    with pytest.raises(ValueError, match="fg"):
        renderer.render(grid, BW, _style(fg="red"))
    with pytest.raises(ValueError, match="bg"):
        renderer.render(grid, BW, _style(bg="#12345"))
    # a fully black braille cell renders every sub-dot in the default black fg.
    assert (np.asarray(renderer.render(grid, BW, _style())) == 0).all()


def test_fg_and_bg_colours_reach_the_pixels():
    renderer = get_renderer("braille")
    black = _grid("braille", np.zeros(8, dtype=np.int32))
    white = _grid("braille", np.ones(8, dtype=np.int32))
    pixels = np.asarray(renderer.render(black, BW, _style(fg="#ff0000", bg="#0000ff")))
    assert (pixels == (255, 0, 0)).all()
    pixels = np.asarray(renderer.render(white, BW, _style(fg="#ff0000", bg="#0000ff")))
    assert (pixels == (0, 0, 255)).all()


def test_missing_or_mis_shaped_subindex_raises():
    from dataclasses import replace
    renderer = get_renderer("sextant")
    grid = _grid("sextant", np.zeros(6, dtype=np.int32))
    with pytest.raises(ValueError, match="subindex"):
        renderer.render(replace(grid, subindex=None), BW, _style())
    with pytest.raises(ValueError, match="subindex"):
        renderer.render(replace(grid, subindex=np.zeros((1, 1, 4), dtype=np.int32)),
                        BW, _style())


# --- pipeline integration (S3): the pipeline fills grid.subindex and renders ---


@pytest.mark.parametrize(("renderer", "pixel_size", "src_h", "src_w"),
                         [("braille", 4, 16, 16), ("sextant", 3, 12, 12)])
def test_pipeline_renders_bitmask_renderer(renderer, pixel_size, src_h, src_w):
    src = np.zeros((src_h, src_w, 3), dtype=np.float32)
    src[: src_h // 2, :, :] = 1.0
    spec = PipelineSpec(pixel_size=pixel_size)
    first = render_with_palette(src, spec, BW, renderer=renderer)
    second = render_with_palette(src, spec, BW, renderer=renderer)
    assert np.array_equal(first, second)
    assert first.shape == (src_h, src_w, 3)
    # black and white halves both appear: ink and paper survive the pipeline.
    assert (first[: src_h // 2] == 0).all() or (first[src_h // 2 :] == 0).all() \
        or (first[: src_h // 2, :, 0] != first[src_h // 2 :, :, 0]).any()
