"""Tests for the pixel sort effect (L15 / CONTRACT §14)."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from lattice_core.effects import pixel_sort as pixel_sort_module
from lattice_core.effects.pixel_sort import pixel_sort
from lattice_core.registry import get_effect, list_effects, resolve_params

EFFECT_ID = "pixel_sort"
SHAPES = ((1, 1), (1, 5), (5, 1), (23, 37), (64, 64))

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _luma(img: np.ndarray) -> np.ndarray:
    """Return the sRGB luma of a (H, W, 3) image, matching the effect's key."""
    return img @ _LUMA


def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """Return a seeded random float32 image of the given (H, W)."""
    return np.random.default_rng(seed).random((*shape, 3), dtype=np.float32)


def _apply(img: np.ndarray, seed: int = 0, **params: object) -> np.ndarray:
    """Run the effect with resolved scalar parameters."""
    info = get_effect(EFFECT_ID)
    return info.fn(img, resolve_params(info.params, params), np.random.default_rng(seed))


def _apply_mask(
    img: np.ndarray, mask: np.ndarray, seed: int = 0, **params: object
) -> np.ndarray:
    """Run the effect with resolved parameters plus an explicit interval-map mask."""
    info = get_effect(EFFECT_ID)
    resolved = resolve_params(info.params, params)
    return pixel_sort(img, resolved, np.random.default_rng(seed), mask=mask)


def test_registration_and_params() -> None:
    """The effect registers under pixel_sort with the five documented parameters."""
    info = get_effect(EFFECT_ID)
    assert info.id == EFFECT_ID
    assert [spec.id for spec in info.params] == [
        "black",
        "brightness",
        "white",
        "direction",
        "key",
    ]
    assert resolve_params(info.params, {}) == {
        "black": 0.0,
        "brightness": 0.5,
        "white": 1.0,
        "direction": "rows",
        "key": "luma",
    }


def test_registered_once_in_lattice_core() -> None:
    """The pixel sort effect is registered by the core effect module itself."""
    mine = [info for info in list_effects() if info.fn.__module__ == pixel_sort_module.__name__]
    assert [info.id for info in mine] == [EFFECT_ID]


def test_brightness_zero_sorts_every_row_ascending() -> None:
    """At brightness=0 every row is one run, so each row ends up luma-sorted."""
    img = _random_image((5, 7), seed=3)
    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="luma")
    for r in range(img.shape[0]):
        assert np.all(np.diff(_luma(out[r : r + 1, :, :]).ravel()) >= -1e-6)
        for channel in range(3):
            assert np.array_equal(np.sort(img[r, :, channel]), np.sort(out[r, :, channel]))


def test_black_zero_on_nonconstant_image_still_sorts() -> None:
    """black=0 does not disable sorting: runs sort whenever brightness is passed.

    An all-black constant image could never prove a missing sort (any reordering of
    equal pixels is a no-op), so this probes the accept with distinct values instead.
    """
    img = _random_image((4, 6), seed=41)
    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="luma")
    assert not np.array_equal(out, img)
    for r in range(img.shape[0]):
        assert np.all(np.diff(_luma(out[r : r + 1, :, :]).ravel()) >= -1e-6)


def test_not_fully_white_image_sorts_every_row_at_brightness_zero() -> None:
    """The all-white accept is covered by testing with non-constant luma rows so the
    sort is observable: even near-white values reorder to ascending luma."""
    img = _random_image((3, 5), seed=52)
    assert float(img.min()) < 1.0
    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="luma")
    for r in range(img.shape[0]):
        assert np.all(np.diff(_luma(out[r : r + 1, :, :]).ravel()) >= -1e-6)


def test_stable_sort_preserves_order_of_equal_keys() -> None:
    """Equal sort keys keep their relative order (stable sort), keyed by b channel."""
    row = np.array(
        [
            [0.5, 0.5, 0.90],  # A : b = 0.90
            [0.2, 0.1, 0.05],  # B : b = 0.05
            [0.8, 0.6, 0.90],  # C : b = 0.90
            [0.9, 0.3, 0.05],  # D : b = 0.05
        ],
        dtype=np.float32,
    )
    img = np.zeros((1, 4, 3), dtype=np.float32)
    img[0] = row
    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="b")
    expected = np.array(
        [
            [0.2, 0.1, 0.05],  # B before D (both b=0.05)
            [0.9, 0.3, 0.05],
            [0.5, 0.5, 0.90],  # A before C (both b=0.90)
            [0.8, 0.6, 0.90],
        ],
        dtype=np.float32,
    )
    assert np.allclose(out[0], expected, atol=1e-6)


def test_mask_all_black_sorts_nothing() -> None:
    """An all-black mask (interval map) prevents any pixel from being sorted."""
    img = _random_image((5, 7), seed=11)
    mask = np.zeros((5, 7), dtype=np.float32)
    out = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
    assert np.array_equal(out, img)


def test_mask_all_white_equals_no_mask() -> None:
    """An all-white mask is exactly equivalent to having no mask at all."""
    img = _random_image((5, 7), seed=5)
    mask = np.ones((5, 7), dtype=np.float32)
    base = _apply(img, black=0.0, brightness=0.0, white=1.0)
    masked = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
    assert np.array_equal(masked, base)


def test_mask_black_region_is_never_sorted() -> None:
    """Pixels under a black mask stay untouched while the unmasked side sorts."""
    img = _random_image((5, 7), seed=13)
    mask = np.zeros((5, 7), dtype=np.float32)
    mask[:, 3:] = 1.0
    out = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
    assert np.array_equal(out[:, :3, :], img[:, :3, :])
    assert not np.array_equal(out, img)


def test_mask_shape_mismatch_raises_value_error() -> None:
    """A mask whose spatial size disagrees with the image raises, never silently drops."""
    img = _random_image((5, 7), seed=13)
    wrong = np.zeros((8, 8), dtype=np.float32)
    with pytest.raises(ValueError, match="mask must be"):
        _apply_mask(img, wrong, black=0.0, brightness=0.0, white=1.0)
    with pytest.raises(ValueError, match="mask must be"):
        _apply_mask(img, np.zeros((5, 7, 3), dtype=np.float32), brightness=0.0)


def test_columns_transposes_rows_on_a_square_image() -> None:
    """Columns of A equal the transpose of rows applied to A.T (square image)."""
    img = _random_image((8, 8), seed=21)
    rows_out = _apply(img, black=0.0, brightness=0.3, white=1.0, direction="rows")
    cols_out = _apply(img, black=0.0, brightness=0.3, white=1.0, direction="columns")
    transposed = _apply(
        np.transpose(img, (1, 0, 2)),
        black=0.0,
        brightness=0.3,
        white=1.0,
        direction="rows",
    )
    assert np.array_equal(cols_out, np.transpose(transposed, (1, 0, 2)))
    assert rows_out.shape == img.shape
    assert cols_out.shape == img.shape


def test_band_runs_are_limited_by_the_white_threshold() -> None:
    """Pixels above `white` are excluded from runs and separate neighbouring runs."""
    row = np.array(
        [[0.2, 0.0, 0.0], [0.6, 0.0, 0.0], [0.9, 0.0, 0.0], [0.1, 0.0, 0.0],
         [0.8, 0.0, 0.0], [0.4, 0.0, 0.0]],
        dtype=np.float32,
    )
    img = np.zeros((1, 6, 3), dtype=np.float32)
    img[0] = row
    out = _apply(img, black=0.0, brightness=0.5, white=0.85, key="r")
    expected_r = np.array([0.2, 0.6, 0.9, 0.1, 0.4, 0.8], dtype=np.float32)
    assert np.allclose(out[0, :, 0], expected_r, atol=1e-6)


def test_pixels_below_brightness_are_not_sorted() -> None:
    """A run only starts once a pixel passes the brightness threshold."""
    row = np.array(
        [[0.4, 0.0, 0.0], [0.3, 0.0, 0.0], [0.7, 0.0, 0.0]],
        dtype=np.float32,
    )
    img = np.zeros((1, 3, 3), dtype=np.float32)
    img[0] = row
    out = _apply(img, black=0.0, brightness=0.5, white=1.0, key="r")
    assert np.array_equal(out, img)


def test_diagonal_direction_sorts_each_main_diagonal() -> None:
    """Diagonal direction sorts every top-left..bottom-right diagonal ascending."""
    img = _random_image((6, 9), seed=9)
    out = _apply(img, direction="diagonal", black=0.0, brightness=0.0, white=1.0)
    height, width = img.shape[:2]
    luma_out = _luma(out)
    for offset in range(-(width - 1), height):
        positions = [(r, c) for r in range(height) for c in range(width) if r - c == offset]
        positions.sort()
        values = np.array([luma_out[r, c] for r, c in positions], dtype=np.float32)
        assert np.all(np.diff(values) >= -1e-6)


@pytest.mark.parametrize("shape", SHAPES)
def test_output_shape_matches_input(shape: tuple[int, int]) -> None:
    """The output is a float32 image of the input shape inside [0, 1]."""
    img = _random_image(shape, seed=1)
    for params in ({}, {"black": 0.1, "brightness": 0.4, "white": 0.9}):
        out = _apply(img, **params)
        assert out.shape == (*shape, 3)
        assert out.dtype == np.float32
        assert float(out.min()) >= 0.0
        assert float(out.max()) <= 1.0


@pytest.mark.parametrize("shape", SHAPES)
def test_shape_holds_for_every_direction(shape: tuple[int, int]) -> None:
    """Rows, columns and diagonal all preserve the input shape."""
    img = _random_image(shape, seed=2)
    for direction in ("rows", "columns", "diagonal"):
        out = _apply(img, direction=direction)
        assert out.shape == (*shape, 3)
        assert out.dtype == np.float32


def test_does_not_mutate_input() -> None:
    """The effect never writes into the array it was given."""
    img = _random_image((24, 24), seed=17)
    before = img.copy()
    _apply(img, black=0.0, brightness=0.2, white=1.0, direction="columns", key="hue")
    assert np.array_equal(img, before)


def test_effect_is_deterministic_across_rng_values() -> None:
    """The output is identical for different rng streams (the effect is rng-free)."""
    img = _random_image((16, 16), seed=8)
    params = {"black": 0.2, "brightness": 0.4, "white": 0.9}
    info = get_effect(EFFECT_ID)
    resolved = resolve_params(info.params, params)
    out_a = pixel_sort(img, resolved, np.random.default_rng(1))
    out_b = pixel_sort(img, resolved, np.random.default_rng(999))
    assert np.array_equal(out_a, out_b)


def test_diagonal_is_deterministic_across_rng_values() -> None:
    """Diagonal output is identical across rng streams, proving determinism."""
    img = _random_image((6, 9), seed=9)
    params = {"direction": "diagonal", "black": 0.0, "brightness": 0.0, "white": 1.0}
    info = get_effect(EFFECT_ID)
    resolved = resolve_params(info.params, params)
    first = pixel_sort(img, resolved, np.random.default_rng(2))
    second = pixel_sort(img, resolved, np.random.default_rng(3))
    assert np.array_equal(first, second)


def test_module_imports_no_application_package() -> None:
    """The core effect must never import an application package."""
    tree = ast.parse(
        Path(pixel_sort_module.__file__).read_text(encoding="utf-8"), filename="pixel_sort.py"
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else []
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            assert root not in ("lattice_dither", "lattice_glyph", "lattice_glitch"), name
