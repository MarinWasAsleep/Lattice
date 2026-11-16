"""Tests for the ordered dithering algorithms."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lattice_core.color import nearest_index
from lattice_core.dither import ordered
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.types import Image, Palette

MATRIX_IDS = tuple(ordered._MATRICES)
SQUARE_IDS = (
    "bayer_2",
    "bayer_4",
    "bayer_8",
    "bayer_16",
    "cluster_dot_4",
    "cluster_dot_8",
    "blue_noise",
)
LINE_IDS = ("lines_horizontal", "lines_vertical", "lines_diagonal")
BLUE_NOISE_PATH = Path(__file__).resolve().parents[1] / "data" / "blue_noise_64.npy"


def _run(matrix_id: str, img: Image, palette: Palette, **params: object) -> np.ndarray:
    """Run one registered ordered algorithm with the given parameter overrides."""
    info = get_algorithm(matrix_id)
    return info.fn(img.copy(), palette.copy(), resolve_params(info.params, params))


def _ranks(matrix_id: str) -> np.ndarray:
    """Recover the integer ranks of a square threshold matrix from its thresholds."""
    t = ordered.matrix(matrix_id)
    return np.rint(t * t.size - 0.5).astype(np.int32)


def test_registered_matrices() -> None:
    """Exactly the ten card matrices are registered with the three shared params."""
    assert set(MATRIX_IDS) == set(SQUARE_IDS) | set(LINE_IDS)
    for matrix_id in MATRIX_IDS:
        info = get_algorithm(matrix_id)
        assert info.family == "ordered"
        assert [spec.id for spec in info.params] == ["spread", "matrix_scale", "strength"]
        assert resolve_params(info.params, {}) == {
            "spread": 1.0,
            "matrix_scale": 1,
            "strength": 1.0,
        }


def test_bayer_2_is_exact() -> None:
    """The 2x2 Bayer matrix is the canonical [[0, 2], [3, 1]]."""
    assert ordered._bayer(2).tolist() == [[0, 2], [3, 1]]


@pytest.mark.parametrize("matrix_id", SQUARE_IDS)
def test_square_matrices_are_permutations(matrix_id: str) -> None:
    """Every square matrix holds each rank of 0..n*n-1 exactly once."""
    ranks = _ranks(matrix_id)
    assert ranks.shape[0] == ranks.shape[1]
    assert np.array_equal(np.sort(ranks.ravel()), np.arange(ranks.size))


def test_bayer_sizes() -> None:
    """The recursive Bayer construction yields the four card sizes."""
    for size in (2, 4, 8, 16):
        assert ordered._bayer(size).shape == (size, size)
        assert np.array_equal(np.sort(ordered._bayer(size).ravel()), np.arange(size * size))


def test_cluster_dot_ranks_follow_distance() -> None:
    """Cluster-dot ranks grow with the distance to the cell centre."""
    for size in (4, 8):
        ranks = ordered._cluster_dot(size)
        centre = (size - 1) / 2.0
        ys, xs = np.mgrid[0:size, 0:size]
        distance = np.hypot(ys - centre, xs - centre).ravel()
        order = np.argsort(ranks.ravel())
        assert np.all(np.diff(distance[order]) >= -1e-12)


def test_cluster_dot_4_is_exact() -> None:
    """The 4x4 cluster-dot ranks are the card's, ties broken by ascending atan2."""
    assert ordered._cluster_dot(4).tolist() == [
        [12, 5, 6, 13],
        [4, 0, 1, 7],
        [11, 3, 2, 8],
        [15, 10, 9, 14],
    ]


def test_cluster_dot_ties_are_broken_by_angle() -> None:
    """Cells at the same distance are ranked by ascending atan2, not by scan order."""
    for size in (4, 8):
        ranks = ordered._cluster_dot(size)
        centre = (size - 1) / 2.0
        ys, xs = np.mgrid[0:size, 0:size]
        distance = np.hypot(ys - centre, xs - centre).ravel()
        angle = np.arctan2(ys - centre, xs - centre).ravel()
        order = np.argsort(ranks.ravel())
        ranked_distance = distance[order]
        ranked_angle = angle[order]
        tied = np.isclose(ranked_distance[1:], ranked_distance[:-1], rtol=0.0, atol=1e-12)
        assert tied.any()
        assert np.all(ranked_angle[1:][tied] > ranked_angle[:-1][tied])


def test_blue_noise_file() -> None:
    """The committed blue-noise file is a 64x64 permutation of 0..4095."""
    ranks = np.load(BLUE_NOISE_PATH)
    assert ranks.shape == (64, 64)
    assert ranks.dtype == np.int32
    assert np.array_equal(np.sort(ranks.ravel()), np.arange(4096))
    assert np.array_equal(ordered.blue_noise_ranks(), ranks)


def test_blue_noise_is_cached() -> None:
    """The blue-noise array and every built matrix are cached at module level."""
    assert ordered.blue_noise_ranks() is ordered.blue_noise_ranks()
    assert ordered.matrix("blue_noise") is ordered.matrix("blue_noise")


@pytest.mark.parametrize("matrix_id", MATRIX_IDS)
def test_matrix_is_read_only(matrix_id: str) -> None:
    """A caller cannot corrupt the cached matrix: writing to it raises."""
    t = ordered.matrix(matrix_id)
    assert not t.flags.writeable
    with pytest.raises(ValueError):
        t[0, 0] = 0.5
    assert np.array_equal(ordered.matrix(matrix_id), t)


def test_blue_noise_ranks_is_read_only() -> None:
    """A caller cannot corrupt the cached blue-noise ranks: writing to them raises."""
    ranks = ordered.blue_noise_ranks()
    assert not ranks.flags.writeable
    with pytest.raises(ValueError):
        ranks[0, 0] = 7
    assert np.array_equal(ordered.blue_noise_ranks(), np.load(BLUE_NOISE_PATH))


def test_grey_half_bayer_4_is_exactly_half(pal_bw: Palette) -> None:
    """A 0.5 grey image with bayer_4 and two colours gives exactly half white."""
    grey = np.full((64, 64, 3), 0.5, dtype=np.float32)
    out = _run("bayer_4", grey, pal_bw)
    assert float((out == 1).mean()) == 0.5


def test_matrix_scale_repeats_cells() -> None:
    """matrix_scale 2 repeats every bayer_2 cell twice in both directions."""
    base = ordered.matrix("bayer_2")
    repeated = np.repeat(np.repeat(base, 2, axis=0), 2, axis=1)
    assert np.array_equal(ordered.tile(base, 8, 8, 2), ordered.tile(repeated, 8, 8, 1))
    img = np.full((8, 8, 3), 0.5, dtype=np.float32)
    palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
    scaled = _run("bayer_2", img, palette, matrix_scale=2)
    assert np.array_equal(scaled, ordered._ordered(img, palette, repeated, 1.0, 1, 1.0, 0))


def test_spread_zero_matches_nearest(gradient: Image, pal_4: Palette) -> None:
    """Zero spread disables the threshold offset and equals plain quantisation."""
    out = _run("bayer_8", gradient, pal_4, spread=0.0)
    assert np.array_equal(out, nearest_index(gradient, pal_4))


def test_amplitude_formula() -> None:
    """The amplitude follows spread / max(1, round(K ** (1/3)) - 1)."""
    assert ordered.amplitude(1.0, 2) == pytest.approx(1.0)
    assert ordered.amplitude(1.0, 8) == pytest.approx(1.0)
    assert ordered.amplitude(1.0, 16) == pytest.approx(0.5)
    assert ordered.amplitude(1.0, 64) == pytest.approx(1.0 / 3.0)
    assert ordered.amplitude(0.5, 16) == pytest.approx(0.25)


@pytest.mark.parametrize("matrix_id", LINE_IDS)
def test_lines_have_four_levels(matrix_id: str) -> None:
    """Every line matrix uses four equally frequent threshold levels."""
    t = ordered.matrix(matrix_id)
    values, counts = np.unique(t, return_counts=True)
    assert len(values) == 4
    assert np.all(counts == counts[0])
    assert np.all((values > 0.0) & (values < 1.0))


def test_lines_orientation() -> None:
    """Horizontal lines vary with y, vertical with x and diagonal with x + y."""
    horizontal = ordered.matrix("lines_horizontal")
    vertical = ordered.matrix("lines_vertical")
    diagonal = ordered.matrix("lines_diagonal")
    assert np.all(horizontal == horizontal[:, 0:1])
    assert np.all(vertical == vertical[0:1, :])
    ys, xs = np.mgrid[0:4, 0:4]
    assert np.allclose(horizontal, 0.125 + 0.25 * ys)
    assert np.allclose(vertical, 0.125 + 0.25 * xs)
    assert np.allclose(diagonal, 0.125 + 0.25 * ((xs + ys) % 4))


def test_output_dtype_and_shape(photo_like: Image, pal_4: Palette) -> None:
    """Every matrix returns int32 indices of the input shape inside [0, K)."""
    for matrix_id in MATRIX_IDS:
        out = _run(matrix_id, photo_like, pal_4)
        assert out.dtype == np.int32
        assert out.shape == photo_like.shape[:2]
        assert int(out.min()) >= 0
        assert int(out.max()) < pal_4.shape[0]


def test_inputs_are_not_mutated(photo_like: Image, pal_4: Palette) -> None:
    """The algorithms leave the caller's arrays untouched."""
    img = photo_like.copy()
    palette = pal_4.copy()
    _run("cluster_dot_8", img, palette)
    assert np.array_equal(img, photo_like)
    assert np.array_equal(palette, pal_4)
