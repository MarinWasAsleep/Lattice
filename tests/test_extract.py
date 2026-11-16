"""Tests for palette extraction (T06)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from lattice_core.color import luminance
from lattice_core.palettes.extract import extract_palette
from lattice_core.types import Image, Palette

METHODS = ("kmeans", "median_cut")
FLAT = np.array(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32
)


def _quadrants() -> Image:
    """Return a 64x64 image made of four flat colours, one per quadrant."""
    img = np.zeros((64, 64, 3), dtype=np.float32)
    img[:32, :32] = FLAT[0]
    img[:32, 32:] = FLAT[1]
    img[32:, :32] = FLAT[2]
    img[32:, 32:] = FLAT[3]
    return img


def _sorted_rows(palette: Palette) -> np.ndarray:
    """Return the palette rows sorted lexicographically for order-free comparison."""
    return palette[np.lexsort((palette[:, 2], palette[:, 1], palette[:, 0]))]


@pytest.mark.parametrize("method", METHODS)
def test_four_flat_colors_are_recovered(method: str) -> None:
    """An image of exactly four flat colours yields exactly those four colours."""
    palette = extract_palette(_quadrants(), 4, method)
    assert palette.shape == (4, 3)
    assert palette.dtype == np.float32
    assert np.allclose(_sorted_rows(palette), _sorted_rows(FLAT), atol=1.0 / 255.0)


@pytest.mark.parametrize("method", METHODS)
def test_single_color_image_gives_two_colors(method: str) -> None:
    """A flat image yields its own colour plus the farther of black and white."""
    dark = extract_palette(np.full((16, 16, 3), 0.2, dtype=np.float32), 4, method)
    assert dark.shape == (2, 3)
    assert np.allclose(dark[0], 0.2, atol=1.0 / 255.0)
    assert np.allclose(dark[1], 1.0, atol=1.0 / 255.0)
    light = extract_palette(np.full((16, 16, 3), 0.9, dtype=np.float32), 4, method)
    assert light.shape == (2, 3)
    assert np.allclose(light[0], 0.0, atol=1.0 / 255.0)
    assert np.allclose(light[1], 0.9, atol=1.0 / 255.0)


@pytest.mark.parametrize("method", METHODS)
def test_fewer_unique_colors_than_k(method: str) -> None:
    """An image with two colours and k=8 returns those two colours."""
    img = np.zeros((8, 8, 3), dtype=np.float32)
    img[:, 4:] = 1.0
    palette = extract_palette(img, 8, method)
    assert palette.shape == (2, 3)
    assert np.allclose(palette, [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], atol=1.0 / 255.0)


@pytest.mark.parametrize("method", METHODS)
def test_output_is_sorted_by_luminance(method: str, photo_like: Image) -> None:
    """The palette is ordered from the darkest to the lightest colour."""
    palette = extract_palette(photo_like, 8, method)
    values = luminance(palette.reshape(1, -1, 3))[0]
    assert np.all(np.diff(values) >= 0.0)
    assert palette.shape == (8, 3)
    assert float(palette.min()) >= 0.0
    assert float(palette.max()) <= 1.0


@pytest.mark.parametrize("method", METHODS)
def test_same_seed_gives_same_result(method: str, photo_like: Image) -> None:
    """Extraction is deterministic for a given seed."""
    first = extract_palette(photo_like, 6, method, seed=11)
    second = extract_palette(photo_like, 6, method, seed=11)
    assert np.array_equal(first, second)


def test_kmeans_seed_changes_the_result(photo_like: Image) -> None:
    """A different seed gives a different k-means initialisation on a rich image."""
    first = extract_palette(photo_like, 6, "kmeans", seed=1)
    second = extract_palette(photo_like, 6, "kmeans", seed=2)
    assert not np.array_equal(first, second)


@pytest.mark.parametrize("k", [1, 0, 33, 256])
def test_k_out_of_range(k: int, photo_like: Image) -> None:
    """k outside [2, 32] is rejected."""
    with pytest.raises(ValueError, match="k must be"):
        extract_palette(photo_like, k, "kmeans")


def test_unknown_method(photo_like: Image) -> None:
    """An unknown method name is rejected."""
    with pytest.raises(ValueError, match="unknown extraction method"):
        extract_palette(photo_like, 4, "octree")  # type: ignore[arg-type]


def test_does_not_mutate_input(photo_like: Image) -> None:
    """The source image is left untouched."""
    img = photo_like.copy()
    extract_palette(img, 5, "kmeans")
    assert np.array_equal(img, photo_like)


def test_large_image_is_fast() -> None:
    """A 2000x2000 image is processed in under two seconds."""
    img = np.random.default_rng(0).random((2000, 2000, 3), dtype=np.float32)
    start = time.perf_counter()
    palette = extract_palette(img, 8, "kmeans")
    elapsed = time.perf_counter() - start
    assert palette.shape == (8, 3)
    assert elapsed < 2.0


def _rare_color_image() -> tuple[Image, np.ndarray]:
    """Return a 2000x2000 flat grey image holding seven rare colours, and those colours."""
    img = np.full((2000, 2000, 3), 0.5, dtype=np.float32)
    rare = np.array([[0.1 * i, 0.2 + 0.05 * i, 0.9 - 0.1 * i] for i in range(1, 8)], np.float32)
    for index, color in enumerate(rare):
        img[index * 13, index * 7] = color
    return img, rare


@pytest.mark.parametrize("method", METHODS)
def test_rare_colors_do_not_force_a_full_image_cluster(method: str) -> None:
    """A subsample that misses rare colours still yields them, in under two seconds."""
    img, rare = _rare_color_image()
    start = time.perf_counter()
    palette = extract_palette(img, 8, method)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
    assert palette.shape == (8, 3)
    expected = np.concatenate([np.full((1, 3), 0.5, np.float32), rare], axis=0)
    assert np.allclose(_sorted_rows(palette), _sorted_rows(expected), atol=1e-6)


@pytest.mark.parametrize("method", METHODS)
def test_colors_closer_than_one_8bit_step_stay_distinct(method: str) -> None:
    """Two colours differing by less than 1/255 are two colours, returned exactly."""
    low = np.float32(0.5)
    high = low + np.float32(1e-4)
    img = np.zeros((8, 8, 3), dtype=np.float32)
    img[:, :4] = low
    img[:, 4:] = high
    palette = extract_palette(img, 8, method)
    assert palette.shape == (2, 3)
    assert np.array_equal(palette, np.array([[low] * 3, [high] * 3], dtype=np.float32))
