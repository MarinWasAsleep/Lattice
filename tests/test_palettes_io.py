"""Tests for the built-in palettes and the palette import/export (T05)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lattice_dither.core.types import Palette
from lattice_dither.palettes.builtin import BUILTIN, builtin_names, get_builtin
from lattice_dither.palettes.io import from_hex_list, hex_list, load_palette, save_palette

EXPECTED_COUNTS = {
    "bw": 2,
    "gameboy": 4,
    "cga_0_high": 4,
    "cga_1_high": 4,
    "ega": 16,
    "pico8": 16,
    "grey_4": 4,
    "grey_8": 8,
    "grey_16": 16,
    "rgb_8": 8,
    "cmyk_5": 5,
}

EXPECTED_HEX = {
    "bw": ["#000000", "#FFFFFF"],
    "gameboy": ["#0F380F", "#306230", "#8BAC0F", "#9BBC0F"],
    "cga_0_high": ["#000000", "#55FF55", "#FF5555", "#FFFF55"],
    "cga_1_high": ["#000000", "#55FFFF", "#FF55FF", "#FFFFFF"],
    "ega": [
        "#000000",
        "#0000AA",
        "#00AA00",
        "#00AAAA",
        "#AA0000",
        "#AA00AA",
        "#AA5500",
        "#AAAAAA",
        "#555555",
        "#5555FF",
        "#55FF55",
        "#55FFFF",
        "#FF5555",
        "#FF55FF",
        "#FFFF55",
        "#FFFFFF",
    ],
    "pico8": [
        "#000000",
        "#1D2B53",
        "#7E2553",
        "#008751",
        "#AB5236",
        "#5F574F",
        "#C2C3C7",
        "#FFF1E8",
        "#FF004D",
        "#FFA300",
        "#FFEC27",
        "#00E436",
        "#29ADFF",
        "#83769C",
        "#FF77A8",
        "#FFCCAA",
    ],
    "cmyk_5": ["#FFFFFF", "#00FFFF", "#FF00FF", "#FFFF00", "#000000"],
}


def test_builtin_names_and_counts() -> None:
    """BUILTIN holds exactly the eleven documented palettes with the documented sizes."""
    assert set(BUILTIN) == set(EXPECTED_COUNTS)
    assert builtin_names() == sorted(EXPECTED_COUNTS)
    for name, count in EXPECTED_COUNTS.items():
        palette = BUILTIN[name]
        assert palette.shape == (count, 3)
        assert palette.dtype == np.float32
        assert float(palette.min()) >= 0.0
        assert float(palette.max()) <= 1.0


@pytest.mark.parametrize("name", sorted(EXPECTED_HEX))
def test_builtin_hex_values_are_verbatim(name: str) -> None:
    """Every documented colour is present, in the documented order."""
    assert hex_list(BUILTIN[name]) == EXPECTED_HEX[name]


@pytest.mark.parametrize("name,count", [("grey_4", 4), ("grey_8", 8), ("grey_16", 16)])
def test_greys_are_evenly_spaced(name: str, count: int) -> None:
    """The grey ramps run from black to white in equal steps."""
    palette = BUILTIN[name]
    expected = np.round(np.linspace(0.0, 1.0, count) * 255.0) / 255.0
    assert np.allclose(palette[:, 0], expected, atol=1e-6)
    assert np.array_equal(palette[:, 0], palette[:, 1])
    assert np.array_equal(palette[:, 0], palette[:, 2])


def test_rgb_8_is_the_cube_corners() -> None:
    """rgb_8 contains exactly the eight corners of the RGB cube."""
    corners = {
        (red, green, blue)
        for red in (0, 255)
        for green in (0, 255)
        for blue in (0, 255)
    }
    assert {tuple(int(v) for v in row) for row in np.round(BUILTIN["rgb_8"] * 255)} == corners


def test_get_builtin_returns_a_copy() -> None:
    """Mutating the returned palette never changes the built-in table."""
    palette = get_builtin("bw")
    palette[0] = 0.5
    assert np.array_equal(BUILTIN["bw"], np.array([[0.0] * 3, [1.0] * 3], dtype=np.float32))


def test_get_builtin_unknown_name() -> None:
    """An unknown name raises KeyError."""
    with pytest.raises(KeyError):
        get_builtin("nope")


@pytest.fixture
def palette() -> Palette:
    """A six colour palette with values that survive the uint8 round trip."""
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [128.0 / 255.0, 128.0 / 255.0, 128.0 / 255.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )


@pytest.mark.parametrize("suffix", [".hex", ".gpl"])
def test_round_trip_is_exact(tmp_path: Path, palette: Palette, suffix: str) -> None:
    """Saving and loading a palette preserves every colour exactly."""
    path = tmp_path / f"pal{suffix}"
    save_palette(path, palette, name="Test")
    assert np.array_equal(load_palette(path), palette)


def test_hex_round_trip_of_every_builtin(tmp_path: Path) -> None:
    """Every built-in palette survives a .hex and a .gpl round trip."""
    for name in builtin_names():
        for suffix in (".hex", ".gpl"):
            path = tmp_path / f"{name}{suffix}"
            save_palette(path, BUILTIN[name], name=name)
            assert np.array_equal(load_palette(path), BUILTIN[name])


def test_hex_parser_tolerates_noise(tmp_path: Path) -> None:
    """A leading "#", blank lines, ";" comments and CRLF line endings are accepted."""
    path = tmp_path / "noisy.hex"
    text = "; a comment\r\n\r\n#FF0000\r\n00FF00\r\n   ; indented comment\r\n0000FF\r\n"
    path.write_text(text, encoding="utf-8")
    expected = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    assert np.array_equal(load_palette(path), expected)


def test_gpl_parser_tolerates_noise(tmp_path: Path) -> None:
    """A GIMP file with comments, a Name and a Columns line is accepted."""
    path = tmp_path / "noisy.gpl"
    text = (
        "GIMP Palette\r\n"
        "Name: Noisy\r\n"
        "Columns: 4\r\n"
        "#\r\n"
        "# a comment\r\n"
        "255   0   0\tRed\r\n"
        "  0 255   0\tGreen\r\n"
        "  0   0 255\r\n"
    )
    path.write_text(text, encoding="utf-8")
    expected = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    assert np.array_equal(load_palette(path), expected)


@pytest.mark.parametrize(
    "text,line",
    [
        ("FF0000\n00FF00\nGGGGGG\n", 3),
        ("FF0000\n00FF00\nFF00\n", 3),
        ("FF0000\n00FF00\n\nFF00001\n", 4),
    ],
)
def test_hex_malformed_line_reports_the_line_number(tmp_path: Path, text: str, line: int) -> None:
    """A malformed .hex line raises ValueError naming its line number."""
    path = tmp_path / "bad.hex"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=rf"line {line}\b"):
        load_palette(path)


@pytest.mark.parametrize(
    "text,line",
    [
        ("GIMP Palette\nName: x\n255 0 0\tRed\n300 0 0\tBad\n", 4),
        ("GIMP Palette\nName: x\n255 0\n", 3),
        ("GIMP Palette\nName: x\n255 0 red\n", 3),
        ("Not a palette\n255 0 0\n", 1),
    ],
)
def test_gpl_malformed_line_reports_the_line_number(tmp_path: Path, text: str, line: int) -> None:
    """A malformed .gpl line raises ValueError naming its line number."""
    path = tmp_path / "bad.gpl"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=rf"line {line}\b"):
        load_palette(path)


def test_unsupported_extension(tmp_path: Path, palette: Palette) -> None:
    """An unknown extension is rejected on both load and save."""
    path = tmp_path / "pal.txt"
    with pytest.raises(ValueError, match="unsupported"):
        save_palette(path, palette)
    path.write_text("FF0000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        load_palette(path)


def test_too_few_colors_is_rejected(tmp_path: Path) -> None:
    """A file with a single colour cannot be a palette."""
    path = tmp_path / "one.hex"
    path.write_text("FF0000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="2 to 256"):
        load_palette(path)


def test_hex_list_and_from_hex_list(palette: Palette) -> None:
    """hex_list emits uppercase "#RRGGBB" and from_hex_list parses it back."""
    values = hex_list(palette)
    assert values[0] == "#000000"
    assert values[1] == "#FF0000"
    assert values[4] == "#808080"
    assert np.array_equal(from_hex_list(values), palette)
    assert np.array_equal(from_hex_list([v.lstrip("#") for v in values]), palette)


def test_from_hex_list_rejects_bad_entry() -> None:
    """A malformed entry raises ValueError naming its position."""
    with pytest.raises(ValueError, match="line 2"):
        from_hex_list(["#000000", "#12345"])
