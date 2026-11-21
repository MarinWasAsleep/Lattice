"""Tests for the palette model and importers (card L3, CONTRACT §4 and 1.1 §16)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from lattice import color
from lattice.palette import (
    MAX_COLORS,
    MIN_COLORS,
    Palette,
    from_gpl,
    from_hex_list,
    from_hex_text,
    from_png,
    load,
)
from lattice.palettes.io import hex_list

TWO_COLORS = ["#000000", "#FFFFFF"]


def test_lum_bounds_of_a_two_colour_palette() -> None:
    """Black and white give lum_min 0.0 and lum_max 1.0 in linear light."""
    palette = Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32))
    assert palette.lum_min == pytest.approx(0.0, abs=1e-6)
    assert palette.lum_max == pytest.approx(1.0, abs=1e-6)


def test_lum_bounds_are_computed_in_linear_light() -> None:
    """Red and white: red has linear luminance 0.2126, white has 1.0."""
    palette = Palette(np.array([[1.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32))
    assert palette.lum_min == pytest.approx(0.2126, abs=1e-6)
    assert palette.lum_max == pytest.approx(1.0, abs=1e-6)


def test_lum_bounds_are_computed_once_at_construction(tmp_path: Path) -> None:
    """Mutating the array after construction leaves the remembered bounds untouched."""
    colors = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
    palette = Palette(colors)
    before_min, before_max = palette.lum_min, palette.lum_max
    colors[:] = 0.25
    assert palette.lum_min == before_min
    assert palette.lum_max == before_max


def test_gpl_png_and_hex_list_imports_agree(tmp_path: Path) -> None:
    """A GPL file, a PNG and a hex list of the same palette produce equal Palettes."""
    gpl = tmp_path / "pair.gpl"
    gpl.write_text(
        "GIMP Palette\nName: pair\n#\n0 0 0\tBlack\n255 255 255\tWhite\n",
        encoding="utf-8",
    )
    png = tmp_path / "pair.png"
    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
    image.putpixel((1, 0), (255, 255, 255))
    image.save(png)

    from_gpl_palette = from_gpl(gpl)
    from_png_palette = from_png(png)
    from_hex_palette = from_hex_list(TWO_COLORS)

    for first, second in (
        (from_gpl_palette, from_png_palette),
        (from_gpl_palette, from_hex_palette),
        (from_png_palette, from_hex_palette),
    ):
        assert np.array_equal(first, second)
        assert first.lum_min == pytest.approx(second.lum_min, abs=1e-12)
        assert first.lum_max == pytest.approx(second.lum_max, abs=1e-12)
        assert first.order == second.order
    assert hex_list(from_png_palette) == TWO_COLORS


def test_from_png_accepts_a_pil_image() -> None:
    """The PNG importer takes an already-open image as well as a path."""
    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
    image.putpixel((1, 0), (255, 255, 255))
    assert np.array_equal(from_png(image), from_hex_list(TWO_COLORS))


def test_from_png_composites_alpha_over_white() -> None:
    """Transparent pixels read as white, like the image pipeline does."""
    rgba = PILImage.new("RGBA", (2, 1))
    rgba.putpixel((0, 0), (0, 0, 0, 0))
    rgba.putpixel((1, 0), (255, 0, 0, 255))
    palette = from_png(rgba)
    assert palette.shape == (2, 3)
    assert np.array_equal(palette, from_hex_list(["#FFFFFF", "#FF0000"]))


def test_lospec_style_text_import() -> None:
    """Pasted hex codes separated by commas, whitespace and prose are parsed."""
    text = "Palette: #000000, #FFFFFF; the classic duo."
    assert np.array_equal(from_hex_text(text), from_hex_list(TWO_COLORS))


def test_order_defaults_to_none() -> None:
    """A Palette constructed without an order carries order None."""
    palette = from_hex_list(TWO_COLORS)
    assert palette.order is None


def test_order_accepts_a_permutation() -> None:
    """A valid permutation is stored as given."""
    palette = Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32), order=[1, 0])
    assert palette.order == [1, 0]


@pytest.mark.parametrize(
    ("order", "pattern"),
    [
        ([0, 0], r"index 0 is repeated"),
        ([0, 2], r"index 2 is outside"),
        ([0], r"missing index 1"),
    ],
)
def test_non_permutation_order_names_the_offending_index(order: list[int], pattern: str) -> None:
    """A non-permutation order raises ValueError naming the offending index."""
    with pytest.raises(ValueError, match=pattern):
        Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32), order=order)


def test_palette_rejects_a_wrong_shape() -> None:
    """A palette must be a (K, 3) array of colours."""
    with pytest.raises(ValueError, match="K, 3"):
        Palette(np.zeros((2, 4), dtype=np.float32))


def test_palette_rejects_a_bad_colour_count() -> None:
    """Palettes hold between MIN_COLORS and MAX_COLORS colours."""
    with pytest.raises(ValueError, match=str(MIN_COLORS)):
        Palette(np.zeros((1, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="257"):
        Palette(np.zeros((MAX_COLORS + 1, 3), dtype=np.float32))


def test_palette_is_usable_where_a_plain_ndarray_is_expected() -> None:
    """Palette stays a drop-in for the (K, 3) arrays the pipeline uses."""
    palette = from_hex_list(TWO_COLORS)
    image = np.full((4, 4, 3), 0.25, dtype=np.float32)
    assert np.array_equal(
        color.nearest_index(image, palette),
        color.nearest_index(image, np.asarray(palette)),
    )
    assert color.apply_palette(np.zeros((2, 2), dtype=np.int32), palette).shape == (2, 2, 3)


def test_load_dispatches_on_the_extension(tmp_path: Path) -> None:
    """load() routes .png to the image importer and .gpl/.hex to the library loader."""
    png = tmp_path / "pair.png"
    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
    image.putpixel((1, 0), (255, 255, 255))
    image.save(png)
    gpl = tmp_path / "pair.gpl"
    gpl.write_text(
        "GIMP Palette\nName: pair\n#\n0 0 0\tBlack\n255 255 255\tWhite\n",
        encoding="utf-8",
    )
    assert np.array_equal(load(png), from_hex_list(TWO_COLORS))
    assert np.array_equal(load(gpl), from_hex_list(TWO_COLORS))


def test_palette_module_has_no_network_imports() -> None:
    """palette.py must not import urllib, requests or socket."""
    module = Path(__file__).resolve().parent.parent / "lattice" / "palette.py"
    text = module.read_text(encoding="utf-8")
    for banned in ("urllib", "requests", "socket"):
        assert banned not in text
