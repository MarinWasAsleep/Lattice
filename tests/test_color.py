"""Tests for the colour utilities."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image as PILImage

from lattice import color
from lattice.palettes.builtin import get_builtin


def test_to_float_composites_transparent_pixel_over_white():
    img = PILImage.new("RGBA", (2, 2), (0, 0, 0, 0))
    out = color.to_float(img)
    assert out.shape == (2, 2, 3)
    assert out.dtype == np.float32
    assert np.allclose(out, 1.0)


def test_to_rgb8_round_trips_uint8():
    rng = np.random.default_rng(0)
    rgb8 = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
    back = color.to_rgb8(color.to_float(PILImage.fromarray(rgb8, "RGB")))
    assert np.array_equal(back, rgb8)


def test_nearest_index_thresholds_on_bw(pal_bw):
    img = np.array([[[0.2, 0.2, 0.2], [0.8, 0.8, 0.8]]], dtype=np.float32)
    idx = color.nearest_index(img, pal_bw)
    assert idx.dtype == np.int32
    assert idx.tolist() == [[0, 1]]


def test_nearest_index_chunking_matches_unchunked(pal_4, monkeypatch):
    rng = np.random.default_rng(1)
    img = rng.random((300, 300, 3), dtype=np.float32)
    reference = color.nearest_index(img, pal_4)
    monkeypatch.setattr(color, "_CHUNK_BYTES", 4096)
    chunked = color.nearest_index(img, pal_4)
    assert np.array_equal(chunked, reference)


def test_downscale_upscale_round_trip_keeps_shape():
    img = np.random.default_rng(2).random((37, 23, 3), dtype=np.float32)
    small = color.downscale(img, 4)
    assert small.shape == (10, 6, 3)
    back = color.upscale_nearest(small, 4, (37, 23))
    assert back.shape == (37, 23, 3)


def test_adjust_identity():
    img = np.random.default_rng(3).random((8, 8, 3), dtype=np.float32)
    out = color.adjust(img, 0.0, 0.0, 1.0)
    assert np.allclose(out, img, atol=1e-6)


def test_luminance_weights():
    img = np.array([[[1.0, 0.0, 0.0]]], dtype=np.float32)
    assert color.luminance(img)[0, 0] == pytest.approx(0.2126, abs=1e-6)


def test_apply_palette_returns_image(pal_4):
    idx = np.array([[0, 1], [2, 3]], dtype=np.int32)
    out = color.apply_palette(idx, pal_4)
    assert out.shape == (2, 2, 3)
    assert out.dtype == np.float32
    assert np.allclose(out[0, 1], [1.0, 0.0, 0.0])


METRICS = ("srgb", "linear", "oklab", "lab2000")

SHARMA_PAIRS = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA_PAIRS)
def test_ciede2000_matches_the_published_reference(lab1, lab2, expected):
    """CIEDE2000 reproduces the Sharma et al. reference pairs to the published precision."""
    got = color._ciede2000(np.array(lab1, np.float64), np.array(lab2, np.float64))
    assert got == pytest.approx(expected, abs=1e-4)


def test_srgb_metric_is_the_1_0_behaviour():
    """The default metric reproduces the pre-1.1 nearest_index on 20 images and 5 palettes."""
    rng = np.random.default_rng(0)
    for _ in range(20):
        img = rng.random((17, 13, 3), dtype=np.float32)
        for name in ("bw", "gameboy", "pico8", "cga_0_high", "grey_16"):
            palette = get_builtin(name)
            assert np.array_equal(
                color.nearest_index(img, palette), color._nearest_euclidean(img, palette)
            )


@pytest.mark.parametrize("metric", METRICS)
def test_a_palette_colour_maps_to_itself(metric):
    """A pixel equal to a palette entry picks that entry under every metric."""
    palette = get_builtin("pico8")
    img = np.ascontiguousarray(palette.reshape(1, -1, 3))
    assert np.array_equal(color.nearest_index(img, palette, metric)[0], np.arange(len(palette)))


@pytest.mark.parametrize("metric", ("oklab", "lab2000"))
def test_perceptual_metrics_disagree_with_srgb(metric):
    """oklab and lab2000 pick a different entry on at least 5 % of a saturated image."""
    img = np.zeros((64, 64, 3), dtype=np.float32)
    img[:, :32] = [1.0, 0.0, 0.0]
    img[:, 32:] = [0.0, 0.0, 1.0]
    palette = get_builtin("pico8")
    base = color.nearest_index(img, palette, "srgb")
    other = color.nearest_index(img, palette, metric)
    assert (base != other).mean() >= 0.05


def test_unknown_metric_names_it():
    """An unknown metric name raises ValueError naming it."""
    with pytest.raises(ValueError, match="cmyk"):
        color.metric_code("cmyk")


def test_metric_code_accepts_an_int_code():
    """An int code passes through and an out-of-range one is rejected."""
    assert color.metric_code(2) == color.METRIC_OKLAB
    with pytest.raises(ValueError, match="9"):
        color.metric_code(9)


def test_linear_conversion_uses_the_exact_transfer_function():
    """0.5 sRGB decodes to 0.2140 in linear light, not to 0.5 ** 2.2."""
    img = np.full((1, 1, 3), 0.5, dtype=np.float32)
    assert float(color.srgb_to_linear(img)[0, 0, 0]) == pytest.approx(0.21404114, abs=1e-6)
    assert np.allclose(color.linear_to_srgb(color.srgb_to_linear(img)), img, atol=1e-6)


def test_oklab_of_white_and_black():
    """White is L = 1 and black is L = 0 in Oklab, with no chroma."""
    white = color.srgb_to_oklab(np.ones((1, 1, 3), dtype=np.float32))[0, 0]
    black = color.srgb_to_oklab(np.zeros((1, 1, 3), dtype=np.float32))[0, 0]
    assert white[0] == pytest.approx(1.0, abs=1e-4)
    assert black[0] == pytest.approx(0.0, abs=1e-6)
    assert abs(white[1]) < 1e-4 and abs(white[2]) < 1e-4


def test_lab_of_white_is_l100():
    """White is L* = 100, a* = b* = 0 in CIELAB under D65."""
    lab = color.srgb_to_lab(np.ones((1, 1, 3), dtype=np.float32))[0, 0]
    assert lab[0] == pytest.approx(100.0, abs=1e-3)
    assert abs(lab[1]) < 1e-3 and abs(lab[2]) < 1e-3


@pytest.mark.perf
def test_metric_budget():
    """Informative: 1024x1024, K=16, each metric under 150 ms after warm-up."""
    import time

    rng = np.random.default_rng(1)
    img = rng.random((1024, 1024, 3), dtype=np.float32)
    palette = get_builtin("grey_16")
    for metric in METRICS:
        color.nearest_index(img[:64, :64], palette, metric)
        start = time.perf_counter()
        color.nearest_index(img, palette, metric)
        elapsed = (time.perf_counter() - start) * 1000.0
        print(f"{metric}: {elapsed:.0f} ms")
