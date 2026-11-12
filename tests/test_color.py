"""Tests for the colour utilities."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image as PILImage

from lattice_dither.core import color


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
