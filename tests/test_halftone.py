"""Tests for the halftone algorithms (T04, extended by T20)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice.dither import halftone
from lattice.registry import get_algorithm, resolve_params
from lattice.types import Image, Palette

IDS = ("halftone_dots", "halftone_squares", "halftone_lines")
DEFAULT_SHAPE = {"halftone_dots": "round", "halftone_squares": "square", "halftone_lines": "line"}
PARAM_IDS = ["cell_size", "angle", "dot_shape", "oversample", "per_channel", "strength"]


def _run(algorithm_id: str, img: Image, palette: Palette, **params) -> np.ndarray:
    """Run a registered halftone algorithm with resolved parameters."""
    info = get_algorithm(algorithm_id)
    return info.fn(img, palette, resolve_params(info.params, params))


def _grey(level: float, size: int = 64) -> Image:
    """Return a constant grey image."""
    return np.full((size, size, 3), level, dtype=np.float32)


def test_registration_family_and_params() -> None:
    """The three halftone algorithms share the documented parameters."""
    for algorithm_id in IDS:
        info = get_algorithm(algorithm_id)
        assert info.family == "halftone"
        assert [spec.id for spec in info.params] == PARAM_IDS
        assert resolve_params(info.params, {}) == {
            "cell_size": 8,
            "angle": 45.0,
            "dot_shape": DEFAULT_SHAPE[algorithm_id],
            "oversample": 1,
            "per_channel": False,
            "strength": 1.0,
        }


def test_angle_range_is_widened_to_180() -> None:
    """§15.1 widens the angle to 0..180 degrees."""
    spec = next(s for s in get_algorithm("halftone_dots").params if s.id == "angle")
    assert (spec.min, spec.max) == (0.0, 180.0)


def test_every_dot_shape_is_accepted_and_distinct(pal_bw: Palette) -> None:
    """All six shapes are accepted and no two of them render the same pattern."""
    outputs = {
        shape: _run("halftone_dots", _grey(0.5), pal_bw, dot_shape=shape)
        for shape in halftone.DOT_SHAPES
    }
    assert len(outputs) == 6
    shapes = list(outputs)
    for i, first in enumerate(shapes):
        for second in shapes[i + 1 :]:
            assert not np.array_equal(outputs[first], outputs[second]), (first, second)


def test_unknown_dot_shape_raises(pal_bw: Palette) -> None:
    """An unknown shape is rejected by the parameter resolver and by the spot lookup."""
    info = get_algorithm("halftone_dots")
    with pytest.raises(ValueError):
        resolve_params(info.params, {"dot_shape": "hexagon"})
    with pytest.raises(ValueError):
        halftone.spot_function("hexagon")


@pytest.mark.parametrize("shape", halftone.DOT_SHAPES)
def test_oversample_changes_the_pattern(shape: str, pal_bw: Palette) -> None:
    """Oversampling 4 times produces a different pattern than no oversampling."""
    plain = _run("halftone_dots", _grey(0.5), pal_bw, dot_shape=shape, oversample=1)
    smooth = _run("halftone_dots", _grey(0.5), pal_bw, dot_shape=shape, oversample=4)
    assert not np.array_equal(plain, smooth)


@pytest.mark.parametrize("shape", halftone.DOT_SHAPES)
def test_oversample_is_smoother(shape: str) -> None:
    """The oversampled coverage map is less bimodal, so its variance is lower."""
    spot = halftone.spot_function(shape)
    level = np.full((64, 64), 0.5, dtype=np.float32)
    plain = halftone.coverage(level, spot, 8, 45.0, 1)
    smooth = halftone.coverage(level, spot, 8, 45.0, 4)
    assert set(np.unique(plain).tolist()) == {0.0, 1.0}
    assert smooth.var() < plain.var()


def test_per_channel_screens_more_than_one_channel() -> None:
    """A saturated red image inks the green and blue plates, not the red one."""
    red = np.zeros((64, 64, 3), dtype=np.float32)
    red[:, :, 0] = 1.0
    ink = halftone.channel_coverage(red, halftone.spot_function("round"), 8, 45.0, 1)
    means = ink.reshape(-1, 3).mean(axis=0)
    assert means[0] == 0.0
    assert int((means > 0.0).sum()) > 1


def test_per_channel_differs_from_single_channel(pal_4: Palette) -> None:
    """The colour screen and the luminance screen do not produce the same indices."""
    red = np.zeros((64, 64, 3), dtype=np.float32)
    red[:, :, 0] = 1.0
    single = _run("halftone_dots", red, pal_4, per_channel=False)
    per_channel = _run("halftone_dots", red, pal_4, per_channel=True)
    assert not np.array_equal(single, per_channel)


@pytest.mark.parametrize("algorithm_id", IDS)
def test_black_is_all_dark_and_white_is_all_light(algorithm_id: str, pal_bw: Palette) -> None:
    """A black image is entirely dark and a white image entirely light."""
    assert (_run(algorithm_id, _grey(0.0), pal_bw) == 0).all()
    assert (_run(algorithm_id, _grey(1.0), pal_bw) == 1).all()


@pytest.mark.parametrize("algorithm_id", IDS)
def test_dark_fraction_grows_as_luminance_drops(algorithm_id: str, pal_bw: Palette) -> None:
    """Three grey levels produce a strictly decreasing dark fraction as the level rises."""
    fractions = [
        float((_run(algorithm_id, _grey(level), pal_bw) == 0).mean())
        for level in (0.25, 0.5, 0.75)
    ]
    assert fractions[0] > fractions[1] > fractions[2]
    assert 0.0 < fractions[1] < 1.0


def test_dots_angle_changes_the_pattern(pal_bw: Palette) -> None:
    """A rotated screen produces a different dot pattern."""
    straight = _run("halftone_dots", _grey(0.5), pal_bw, angle=0.0)
    rotated = _run("halftone_dots", _grey(0.5), pal_bw, angle=45.0)
    assert not np.array_equal(straight, rotated)


def test_cell_size_changes_the_pattern(pal_bw: Palette) -> None:
    """A larger cell produces a different pattern."""
    small = _run("halftone_dots", _grey(0.5), pal_bw, cell_size=4)
    large = _run("halftone_dots", _grey(0.5), pal_bw, cell_size=16)
    assert not np.array_equal(small, large)


def test_spot_shapes_differ(pal_bw: Palette) -> None:
    """The three spot functions give three different patterns."""
    outputs = [_run(algorithm_id, _grey(0.5), pal_bw) for algorithm_id in IDS]
    assert not np.array_equal(outputs[0], outputs[1])
    assert not np.array_equal(outputs[0], outputs[2])
    assert not np.array_equal(outputs[1], outputs[2])


def test_uses_darkest_and_lightest(pal_4: Palette) -> None:
    """Halftone maps to the darkest and lightest palette entries, not to indices 0 and 1."""
    palette = pal_4[[3, 1, 0, 2]]
    assert set(np.unique(_run("halftone_dots", _grey(0.0), palette)).tolist()) == {2}
    assert set(np.unique(_run("halftone_dots", _grey(1.0), palette)).tolist()) == {0}


@pytest.mark.parametrize("shape", [(37, 23), (1, 5), (1, 1), (3, 64)])
def test_shapes_and_dtype(shape: tuple[int, int], pal_bw: Palette) -> None:
    """Any image shape yields an int32 index map of the same shape."""
    img = np.full((*shape, 3), 0.5, dtype=np.float32)
    out = _run("halftone_dots", img, pal_bw)
    assert out.shape == shape
    assert out.dtype == np.int32
    assert set(np.unique(out).tolist()) <= {0, 1}


def test_does_not_mutate_inputs(pal_bw: Palette, photo_like: Image) -> None:
    """The image and the palette are left untouched."""
    img = photo_like.copy()
    palette = pal_bw.copy()
    for algorithm_id in IDS:
        _run(algorithm_id, img, palette)
    assert np.array_equal(img, photo_like)
    assert np.array_equal(palette, pal_bw)


@pytest.mark.parametrize("algorithm_id", IDS)
def test_cell_mean_drives_the_pattern(algorithm_id: str, pal_bw: Palette) -> None:
    """A cell whose mean is 0.5 renders like a flat 0.5 cell, whatever its pixels are."""
    ys, xs = np.mgrid[0:16, 0:16]
    checker = np.ascontiguousarray(np.repeat(((ys + xs) % 2).astype(np.float32)[:, :, None], 3, 2))
    flat = np.full((16, 16, 3), 0.5, dtype=np.float32)
    assert np.array_equal(
        _run(algorithm_id, checker, pal_bw, cell_size=8, angle=0.0),
        _run(algorithm_id, flat, pal_bw, cell_size=8, angle=0.0),
    )


def test_same_cell_pixels_share_the_cell_mean(pal_bw: Palette) -> None:
    """Two pixels of one cell with different luminance get the same index."""
    flat = np.full((8, 8, 3), 0.5, dtype=np.float32)
    perturbed = flat.copy()
    perturbed[0, 0] = 0.0
    perturbed[0, 7] = 1.0
    flat_out = _run("halftone_lines", flat, pal_bw, cell_size=8, angle=0.0)
    out = _run("halftone_lines", perturbed, pal_bw, cell_size=8, angle=0.0)
    assert out[0, 0] == out[0, 7]
    assert np.array_equal(out, flat_out)
