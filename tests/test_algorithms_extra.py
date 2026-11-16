"""Tests for the algorithms added after the harness cards: Ostromoukhov, Fan,
Shiau-Fan, Yliluoma 1 and 2, dot diffusion and direct binary search."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

import lattice_core.effects  # noqa: F401
from lattice_core.color import nearest_index
from lattice_core.dither import dbs, dot_diffusion, ostromoukhov, ostromoukhov_table, yliluoma
from lattice_core.dither.error_diffusion import KERNELS
from lattice_core.pipeline import PaletteSpec, PipelineSpec, render
from lattice_core.presets import load_preset
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.types import Image, Palette

PRESET_DIR = Path(__file__).resolve().parents[1] / "presets"

NEW_IDS = (
    "ostromoukhov",
    "fan",
    "shiau_fan",
    "yliluoma1",
    "yliluoma2",
    "dot_diffusion",
    "direct_binary_search",
)


def _run(algorithm_id: str, img: Image, palette: Palette, **params: object) -> np.ndarray:
    """Run a registered algorithm with resolved parameters, on copies."""
    info = get_algorithm(algorithm_id)
    return info.fn(img.copy(), palette.copy(), resolve_params(info.params, params))


def _grey(level: float, height: int = 64, width: int = 64) -> Image:
    """Return a constant grey image."""
    return np.full((height, width, 3), level, dtype=np.float32)


def _block_error(rendered: Image, truth: Image, block: int = 8) -> float:
    """Return the mean absolute difference of block averages, a local-colour score."""
    height, width = truth.shape[:2]
    rows = height // block
    cols = width // block
    assert rows and cols, f"image {truth.shape} is smaller than the {block} block"
    left = rendered[: rows * block, : cols * block].reshape(rows, block, cols, block, 3)
    right = truth[: rows * block, : cols * block].reshape(rows, block, cols, block, 3)
    return float(np.abs(left.mean(axis=(1, 3)) - right.mean(axis=(1, 3))).mean())


def _perceived_error(out: np.ndarray, img: Image, palette: Palette, radius: int = 2) -> float:
    """Return the Gaussian-blurred squared error, the objective DBS minimises."""
    weights = dbs.separable_weights(radius)
    rendered = np.ascontiguousarray(palette[out], dtype=np.float32)
    difference = dbs._blur(img, weights, radius) - dbs._blur(rendered, weights, radius)
    return float((difference * difference).mean())


@pytest.fixture
def colour_photo(rng: np.random.Generator) -> Image:
    """96x64 smooth colour image with structure in every channel."""
    img = rng.random((96, 64, 3), dtype=np.float32)
    for _ in range(3):
        img = (img + np.roll(img, 1, axis=0) + np.roll(img, 1, axis=1)) / 3.0
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0).astype(np.float32))


@pytest.fixture
def pal_8() -> Palette:
    """Eight saturated colours plus black and white."""
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )


def test_registration_families_names_and_defaults() -> None:
    """Every new algorithm is registered with the expected name, family and defaults."""
    expected = {
        "ostromoukhov": ("Ostromoukhov", "error_diffusion", {"strength": 1.0}),
        "fan": ("Fan", "error_diffusion", {"serpentine": True, "strength": 1.0}),
        "shiau_fan": ("Shiau-Fan", "error_diffusion", {"serpentine": True, "strength": 1.0}),
        "yliluoma1": ("Yliluoma 1", "ordered", {"levels": 64, "strength": 1.0}),
        "yliluoma2": ("Yliluoma 2", "ordered", {"slots": 64, "strength": 1.0}),
        "dot_diffusion": ("Dot Diffusion", "other", {"strength": 1.0}),
        "direct_binary_search": (
            "Direct Binary Search",
            "other",
            {"iterations": 2, "radius": 2, "strength": 1.0},
        ),
    }
    for algorithm_id, (name, family, defaults) in expected.items():
        info = get_algorithm(algorithm_id)
        assert info.name == name, algorithm_id
        assert info.family == family, algorithm_id
        assert resolve_params(info.params, {}) == pytest.approx(defaults), algorithm_id


def test_ostromoukhov_table_pins_published_rows() -> None:
    """Spot-check the transcribed table against the author's reference implementation."""
    table = ostromoukhov_table.COEFFICIENTS
    assert len(table) == 256
    assert table[0] == (13, 0, 5)
    assert table[64] == (1, 1, 0)
    assert table[128] == (4, 1, 1)
    assert table[255] == (13, 0, 5)
    for tone, row in enumerate(table):
        assert sum(row) > 0, tone
        assert table[255 - tone] == row, tone


def test_ostromoukhov_coefficients_vary_with_tone(
    gradient: Image, pal_bw: Palette, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing the table with one repeated row changes the result, so tone drives the kernel."""
    variable = _run("ostromoukhov", gradient, pal_bw)
    monkeypatch.setattr(
        ostromoukhov, "_TABLE", np.tile(ostromoukhov._TABLE[128], (256, 1))
    )
    fixed = _run("ostromoukhov", gradient, pal_bw)
    assert not np.array_equal(variable, fixed)


def test_ostromoukhov_strength_zero_matches_nearest(gradient: Image, pal_4: Palette) -> None:
    """Zero strength disables propagation and equals plain quantisation."""
    out = _run("ostromoukhov", gradient, pal_4, strength=0.0)
    assert np.array_equal(out, nearest_index(gradient, pal_4))


def test_ostromoukhov_differs_from_floyd_steinberg(gradient: Image, pal_bw: Palette) -> None:
    """The variable coefficients do not reproduce the fixed Floyd-Steinberg kernel."""
    variable = _run("ostromoukhov", gradient, pal_bw)
    fixed = _run("floyd_steinberg", gradient, pal_bw)
    assert not np.array_equal(variable, fixed)


@pytest.mark.parametrize(
    ("kernel_id", "expected"),
    [
        ("fan", (16, ((1, 0, 7), (-2, 1, 1), (-1, 1, 3), (0, 1, 5)))),
        ("shiau_fan", (16, ((1, 0, 8), (-3, 1, 1), (-2, 1, 1), (-1, 1, 2), (0, 1, 4)))),
    ],
)
def test_new_kernels_match_published_weights(
    kernel_id: str, expected: tuple[int, tuple[tuple[int, int, int], ...]]
) -> None:
    """Fan and Shiau-Fan carry their published taps, not a copy of another kernel."""
    assert KERNELS[kernel_id] == expected


@pytest.mark.parametrize("kernel_id", ["fan", "shiau_fan"])
def test_new_kernels_differ_from_floyd_steinberg(
    kernel_id: str, gradient: Image, pal_bw: Palette
) -> None:
    """Each new kernel produces a different halftone than Floyd-Steinberg on a ramp."""
    assert not np.array_equal(
        _run(kernel_id, gradient, pal_bw), _run("floyd_steinberg", gradient, pal_bw)
    )


@pytest.mark.parametrize("algorithm_id", ["yliluoma1", "yliluoma2", "dot_diffusion"])
@pytest.mark.parametrize(("height", "width"), [(64, 64), (32, 32)])
def test_flat_grey_keeps_the_density(
    algorithm_id: str, height: int, width: int, pal_bw: Palette
) -> None:
    """A 0.5 grey dithers to roughly half white pixels."""
    out = _run(algorithm_id, _grey(0.5, height, width), pal_bw)
    assert 0.45 <= float((out == 1).mean()) <= 0.55


@pytest.mark.parametrize("iterations", [1, 2, 4])
def test_direct_binary_search_keeps_the_density(iterations: int, pal_bw: Palette) -> None:
    """DBS converges to the right density on a flat grey whatever the iteration count."""
    out = _run("direct_binary_search", _grey(0.5), pal_bw, iterations=iterations)
    assert 0.45 <= float((out == 1).mean()) <= 0.55


def test_direct_binary_search_lowers_its_own_objective(
    colour_photo: Image, pal_8: Palette
) -> None:
    """Each extra iteration strictly reduces the blurred squared error the search minimises."""
    errors = [
        _perceived_error(
            _run("direct_binary_search", colour_photo, pal_8, iterations=count),
            colour_photo,
            pal_8,
        )
        for count in (1, 2, 3)
    ]
    assert errors[1] < errors[0]
    assert errors[2] <= errors[1]


def test_direct_binary_search_beats_plain_quantisation(
    colour_photo: Image, pal_8: Palette
) -> None:
    """The search lowers the local colour error below nearest-colour quantisation."""
    plain = pal_8[nearest_index(colour_photo, pal_8)]
    searched = pal_8[_run("direct_binary_search", colour_photo, pal_8)]
    assert _block_error(searched, colour_photo) < _block_error(plain, colour_photo)


def test_yliluoma2_keeps_colour_better_than_yliluoma1(
    colour_photo: Image, pal_8: Palette
) -> None:
    """Algorithm 2 plans per pixel colour, so it beats the luminance-only algorithm 1."""
    plain = _block_error(pal_8[nearest_index(colour_photo, pal_8)], colour_photo)
    first = _block_error(pal_8[_run("yliluoma1", colour_photo, pal_8)], colour_photo)
    second = _block_error(pal_8[_run("yliluoma2", colour_photo, pal_8)], colour_photo)
    assert first < plain
    assert second < plain
    assert second < first


def test_yliluoma1_is_chroma_blind_and_yliluoma2_is_not(pal_8: Palette) -> None:
    """On a flat colour, algorithm 1 mixes two colours while algorithm 2 mixes several."""
    flat = np.full((32, 32, 3), [0.3, 0.6, 0.2], dtype=np.float32)
    first = set(_run("yliluoma1", flat, pal_8).ravel().tolist())
    second = set(_run("yliluoma2", flat, pal_8).ravel().tolist())
    assert len(first) <= 2
    assert len(second) > 2


def test_dot_diffusion_class_matrix_pins_rows() -> None:
    """The class matrix is Knuth's, not an arbitrary permutation of 0..63."""
    matrix = dot_diffusion.CLASS_MATRIX
    assert matrix.shape == (8, 8)
    assert sorted(matrix.ravel().tolist()) == list(range(64))
    assert matrix[0].tolist() == [35, 48, 40, 32, 28, 15, 23, 31]
    assert matrix[7].tolist() == [24, 16, 8, 26, 39, 47, 55, 37]


def test_dot_diffusion_leaves_few_pixels_without_a_later_neighbour() -> None:
    """Knuth's matrix keeps the error flowing: almost every pixel has a later neighbour."""
    classes = dot_diffusion.class_map(64, 64)
    height, width = classes.shape
    dead = 0
    for y in range(height):
        for x in range(width):
            own = classes[y, x]
            if not any(
                0 <= y + dy < height
                and 0 <= x + dx < width
                and classes[y + dy, x + dx] > own
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
                if (dy, dx) != (0, 0)
            ):
                dead += 1
    assert dead / (height * width) < 0.05


@pytest.mark.parametrize(("level", "expected"), [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)])
def test_dot_diffusion_keeps_the_density_exactly(
    level: float, expected: float, pal_bw: Palette
) -> None:
    """Class ordering conserves the error, so a flat grey keeps its exact density."""
    out = _run("dot_diffusion", _grey(level), pal_bw)
    assert float((out == 1).mean()) == pytest.approx(expected, abs=0.005)


def test_dot_diffusion_class_map_tiles() -> None:
    """The class map repeats the matrix over the image."""
    classes = dot_diffusion.class_map(20, 20)
    assert classes.shape == (20, 20)
    assert np.array_equal(classes[:8, :8], dot_diffusion.CLASS_MATRIX)
    assert np.array_equal(classes[8:16, 8:16], dot_diffusion.CLASS_MATRIX)


def test_direct_binary_search_stencils_sum_to_zero() -> None:
    """Each swap stencil sums to zero, so a swap never changes the local average."""
    kernel = dbs.gaussian_kernel(2)
    stencils = dbs.swap_stencils(kernel, 2)
    assert stencils.shape[0] == len(dbs._SWAP_OFFSETS)
    assert stencils.shape[1] == stencils.shape[2] >= 2 * 2 + 1
    for index in range(stencils.shape[0]):
        assert abs(float(stencils[index].sum())) < 1e-6, index


def test_autocorrelation_reproduces_the_stencil_energy() -> None:
    """The fast path replaces the stencil energy with 2 * (sum(w^2) - A(offset))."""
    kernel = dbs.gaussian_kernel(2)
    autocorr = dbs.autocorrelation(kernel, 2)
    stencils = dbs.swap_stencils(kernel, 2)
    energy = float((kernel * kernel).sum())
    assert autocorr[4, 4] == pytest.approx(energy)
    for index, (ox, oy) in enumerate(dbs._SWAP_OFFSETS):
        expected = 2.0 * (energy - autocorr[int(oy) + 4, int(ox) + 4])
        assert float((stencils[index] ** 2).sum()) == pytest.approx(expected)


def test_direct_binary_search_stencil_matches_its_offset() -> None:
    """The stencil of an offset is w(u) - w(u - offset), not the mirrored difference."""
    kernel = dbs.gaussian_kernel(2)
    stencils = dbs.swap_stencils(kernel, 2)
    pad = 3
    for index, (ox, oy) in enumerate(dbs._SWAP_OFFSETS):
        for uy in range(-2, 3):
            for ux in range(-2, 3):
                here = float(kernel[uy + 2, ux + 2])
                back_y = uy - int(oy)
                back_x = ux - int(ox)
                back = (
                    float(kernel[back_y + 2, back_x + 2])
                    if -2 <= back_y <= 2 and -2 <= back_x <= 2
                    else 0.0
                )
                assert stencils[index, uy + pad, ux + pad] == pytest.approx(here - back)


@pytest.mark.parametrize("algorithm_id", NEW_IDS)
def test_outputs_are_valid(algorithm_id: str, colour_photo: Image, pal_8: Palette) -> None:
    """Every new algorithm returns int32 indices of the input shape inside [0, K)."""
    out = _run(algorithm_id, colour_photo, pal_8)
    assert out.dtype == np.int32
    assert out.shape == colour_photo.shape[:2]
    assert int(out.min()) >= 0
    assert int(out.max()) < pal_8.shape[0]


@pytest.mark.parametrize("algorithm_id", NEW_IDS)
@pytest.mark.parametrize(("height", "width"), [(1, 5), (5, 1), (1, 1)])
def test_degenerate_shapes_are_valid(
    algorithm_id: str, height: int, width: int, pal_8: Palette
) -> None:
    """Thin and single-pixel images still return indices of the right shape."""
    img = np.full((height, width, 3), 0.5, dtype=np.float32)
    out = _run(algorithm_id, img, pal_8)
    assert out.shape == (height, width)
    assert int(out.min()) >= 0
    assert int(out.max()) < pal_8.shape[0]


@pytest.mark.parametrize("algorithm_id", NEW_IDS)
def test_outputs_are_deterministic(algorithm_id: str, colour_photo: Image, pal_8: Palette) -> None:
    """Two runs on the same input give the same indices."""
    first = _run(algorithm_id, colour_photo, pal_8)
    second = _run(algorithm_id, colour_photo, pal_8)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("algorithm_id", NEW_IDS)
def test_inputs_are_not_mutated(algorithm_id: str, colour_photo: Image, pal_8: Palette) -> None:
    """The algorithms work on copies and leave the caller's arrays untouched."""
    info = get_algorithm(algorithm_id)
    img = colour_photo.copy()
    palette = pal_8.copy()
    info.fn(img, palette, resolve_params(info.params, {}))
    assert np.array_equal(img, colour_photo)
    assert np.array_equal(palette, pal_8)


@pytest.mark.parametrize(
    ("algorithm_id", "params"),
    [
        ("ostromoukhov", {"strength": 0.5}),
        ("fan", {"serpentine": False}),
        ("shiau_fan", {"serpentine": False}),
        ("yliluoma1", {"levels": 4}),
        ("yliluoma2", {"slots": 8}),
        ("dot_diffusion", {"strength": 0.5}),
        ("direct_binary_search", {"radius": 1}),
    ],
)
def test_parameters_change_the_output(
    algorithm_id: str, params: dict, colour_photo: Image, pal_8: Palette
) -> None:
    """Every exposed parameter actually reaches the algorithm."""
    default = _run(algorithm_id, colour_photo, pal_8)
    changed = _run(algorithm_id, colour_photo, pal_8, **params)
    assert not np.array_equal(default, changed), algorithm_id


@pytest.mark.perf
def test_perf_direct_binary_search_256(rng: np.random.Generator) -> None:
    """DBS on 256x256 with K=16 stays under 0.15 s after warm-up."""
    img = rng.random((256, 256, 3), dtype=np.float32)
    palette = np.array([[i / 15] * 3 for i in range(16)], dtype=np.float32)
    _run("direct_binary_search", img, palette)
    start = time.perf_counter()
    _run("direct_binary_search", img, palette)
    assert time.perf_counter() - start < 0.15


def test_yliluoma_buckets_cover_every_slot() -> None:
    """The blue-noise ranks spread evenly over the threshold buckets."""
    buckets = yliluoma._buckets()
    assert buckets.shape == (64, 64)
    counts = np.bincount(buckets.ravel(), minlength=yliluoma.SLOTS)
    assert np.array_equal(counts, np.full(yliluoma.SLOTS, 64))


@pytest.mark.parametrize("path", sorted(PRESET_DIR.glob("*.json")), ids=lambda p: p.name)
def test_shipped_presets_render(path: Path) -> None:
    """Every preset in presets/ loads and renders, so no stale parameter ships."""
    src = np.random.default_rng(0).random((24, 24, 3), dtype=np.float32)
    out = render(src, load_preset(path))
    assert out.shape == (24, 24, 3)
    assert out.dtype == np.uint8


@pytest.mark.parametrize("algorithm_id", NEW_IDS)
@pytest.mark.parametrize("pixel_size", [1, 3, 32])
def test_pipeline_renders_new_algorithms(algorithm_id: str, pixel_size: int) -> None:
    """The pipeline downsamples, dithers and upsamples every new algorithm."""
    src = np.random.default_rng(0).random((20, 20, 3), dtype=np.float32)
    spec = PipelineSpec(
        algorithm_id=algorithm_id,
        pixel_size=pixel_size,
        palette=PaletteSpec(source="builtin", name="bw"),
    )
    out = render(src, spec)
    assert out.shape == (20, 20, 3)
    assert out.dtype == np.uint8
