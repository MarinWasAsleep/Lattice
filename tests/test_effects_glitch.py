"""Tests for the glitch effects (T07B)."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image as PILImage

from dithercraft.core.color import to_float, to_pil, to_rgb8
from dithercraft.core.registry import get_effect, list_effects, resolve_params
from dithercraft.core.types import Image
from dithercraft.effects import glitch

GLITCH_IDS = ("chromatic_aberration", "rgb_shift", "jpeg_glitch", "scanlines")
SHAPES = ((1, 1), (1, 5), (37, 23), (64, 64))


def _run(effect_id: str, img: Image, seed: int = 0, **params: object) -> Image:
    """Run one registered glitch effect with the given parameter overrides."""
    info = get_effect(effect_id)
    return info.fn(img, resolve_params(info.params, params), np.random.default_rng(seed))


def _image(shape: tuple[int, int], seed: int = 0) -> Image:
    """Return a deterministic random float32 image of the given (H, W)."""
    rng = np.random.default_rng(seed)
    return rng.random((shape[0], shape[1], 3), dtype=np.float32)


def _ramp(size: int = 33) -> Image:
    """Return an odd size x size image whose red and blue channels are a horizontal ramp."""
    ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)
    img = np.empty((size, size, 3), dtype=np.float32)
    img[:, :, 0] = ramp[None, :]
    img[:, :, 1] = np.float32(0.5)
    img[:, :, 2] = ramp[None, :]
    return img


def test_registers_exactly_four_effects() -> None:
    """The module registers exactly the four card effects."""
    registered = {info.id for info in list_effects() if info.fn.__module__ == glitch.__name__}
    assert registered == set(GLITCH_IDS)


def test_parameter_specs_match_the_card() -> None:
    """Parameter ids, kinds, defaults, min and max are the card values."""
    expected = {
        "chromatic_aberration": [("amount", "float", 4.0, 0.0, 50.0)],
        "rgb_shift": [
            ("r_x", "int", 0, -100, 100),
            ("r_y", "int", 0, -100, 100),
            ("b_x", "int", 0, -100, 100),
            ("b_y", "int", 0, -100, 100),
        ],
        "jpeg_glitch": [("quality", "int", 20, 1, 95), ("corruptions", "int", 5, 0, 50)],
        "scanlines": [
            ("spacing", "int", 3, 2, 16),
            ("thickness", "int", 1, 1, 8),
            ("darkness", "float", 0.5, 0.0, 1.0),
        ],
    }
    for effect_id, specs in expected.items():
        info = get_effect(effect_id)
        got = [(s.id, s.kind, s.default, s.min, s.max) for s in info.params]
        assert got == specs
        assert all(s.label for s in info.params)


def test_identity_parameters_are_exact() -> None:
    """amount 0, zero shifts and darkness 0 return the input unchanged."""
    img = _image((37, 23), seed=3)
    assert np.array_equal(_run("chromatic_aberration", img, amount=0.0), img)
    assert np.array_equal(_run("rgb_shift", img, r_x=0, r_y=0, b_x=0, b_y=0), img)
    assert np.array_equal(_run("scanlines", img, darkness=0.0), img)


@pytest.mark.parametrize("effect_id", GLITCH_IDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_output_contract(effect_id: str, shape: tuple[int, int]) -> None:
    """Every effect returns a new contiguous float32 image in [0, 1] of the input shape."""
    img = _image(shape, seed=11)
    before = img.copy()
    out = _run(effect_id, img, seed=5)
    assert isinstance(out, np.ndarray)
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]
    assert float(out.min()) >= 0.0 and float(out.max()) <= 1.0
    assert np.array_equal(img, before)
    assert out is not img


@pytest.mark.parametrize("effect_id", GLITCH_IDS)
def test_same_seed_gives_identical_output(effect_id: str) -> None:
    """Two generators with the same seed produce bit-identical results."""
    img = _image((37, 23), seed=2)
    first = _run(effect_id, img, seed=17)
    second = _run(effect_id, img, seed=17)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("effect_id", GLITCH_IDS)
def test_extreme_parameters_never_raise(effect_id: str) -> None:
    """Minimum and maximum parameter values work on 1x1 and on a normal image."""
    info = get_effect(effect_id)
    low = {spec.id: spec.min for spec in info.params}
    high = {spec.id: spec.max for spec in info.params}
    for shape in ((1, 1), (37, 23)):
        img = _image(shape, seed=4)
        for params in (low, high):
            out = info.fn(img, resolve_params(info.params, params), np.random.default_rng(1))
            assert out.shape == img.shape
            assert out.dtype == np.float32
            assert float(out.min()) >= 0.0 and float(out.max()) <= 1.0


def test_chromatic_aberration_is_radial() -> None:
    """Red is sampled outward and blue inward; the centre pixel is untouched."""
    img = _ramp(33)
    out = _run("chromatic_aberration", img, amount=8.0)
    assert out[16, 8, 0] < img[16, 8, 0]
    assert out[16, 8, 2] > img[16, 8, 2]
    assert out[16, 16, 0] == pytest.approx(img[16, 16, 0], abs=1e-6)
    assert out[16, 16, 2] == pytest.approx(img[16, 16, 2], abs=1e-6)
    assert np.array_equal(out[:, :, 1], img[:, :, 1])


def test_chromatic_aberration_keeps_1x1() -> None:
    """A 1x1 image has no radius, so the effect leaves it unchanged."""
    img = np.full((1, 1, 3), 0.4, dtype=np.float32)
    assert np.allclose(_run("chromatic_aberration", img, amount=50.0), img)


def test_rgb_shift_moves_red_right_and_replicates_edges() -> None:
    """r_x = 2 shifts red right by two pixels and repeats the left edge column."""
    img = _image((9, 12), seed=6)
    out = _run("rgb_shift", img, r_x=2)
    assert np.array_equal(out[:, 2:, 0], img[:, :-2, 0])
    assert np.array_equal(out[:, :2, 0], np.repeat(img[:, :1, 0], 2, axis=1))
    assert np.array_equal(out[:, :, 1], img[:, :, 1])
    assert np.array_equal(out[:, :, 2], img[:, :, 2])


def test_rgb_shift_moves_blue_up_and_replicates_edges() -> None:
    """b_y = 3 shifts blue down by three rows and repeats the top row."""
    img = _image((9, 12), seed=6)
    out = _run("rgb_shift", img, b_y=3)
    assert np.array_equal(out[3:, :, 2], img[:-3, :, 2])
    assert np.array_equal(out[:3, :, 2], np.repeat(img[:1, :, 2], 3, axis=0))
    assert np.array_equal(out[:, :, 0], img[:, :, 0])


def test_scanlines_darken_bands_only() -> None:
    """Rows with y % spacing < thickness are scaled by 1 - darkness, others untouched."""
    img = _image((16, 7), seed=8)
    out = _run("scanlines", img, spacing=4, thickness=2, darkness=0.5)
    band = (np.arange(16) % 4) < 2
    assert np.allclose(out[band], img[band] * np.float32(0.5), atol=1e-6)
    assert np.array_equal(out[~band], img[~band])


def test_scanlines_full_darkness_blacks_the_bands() -> None:
    """darkness 1 turns the band rows black."""
    img = _image((12, 5), seed=9)
    out = _run("scanlines", img, spacing=3, thickness=1, darkness=1.0)
    assert np.all(out[0::3] == 0.0)
    assert np.array_equal(out[1::3], img[1::3])


def test_jpeg_glitch_never_raises_across_50_seeds() -> None:
    """Fifty seeds and four shapes never raise and always honour the effect contract."""
    for shape in SHAPES:
        img = _image(shape, seed=13)
        for seed in range(50):
            out = _run("jpeg_glitch", img, seed=seed, quality=20, corruptions=50)
            assert out.shape == img.shape
            assert out.dtype == np.float32
            assert float(out.min()) >= 0.0 and float(out.max()) <= 1.0


def test_jpeg_glitch_zero_corruptions_is_the_clean_round_trip() -> None:
    """corruptions 0 returns exactly the plain Pillow JPEG round trip."""
    img = _image((37, 23), seed=14)
    out = _run("jpeg_glitch", img, quality=20, corruptions=0)
    buffer = io.BytesIO()
    to_pil(to_rgb8(img)).save(buffer, format="JPEG", quality=20)
    with PILImage.open(io.BytesIO(buffer.getvalue())) as pil:
        expected = to_float(pil)
    assert np.allclose(out, expected, atol=1e-6)


def test_jpeg_glitch_corruptions_change_the_image() -> None:
    """Corrupting bytes after the SOS marker visibly alters the decoded image."""
    img = _image((64, 64), seed=15)
    clean = _run("jpeg_glitch", img, quality=20, corruptions=0)
    changed = sum(
        not np.allclose(_run("jpeg_glitch", img, seed=seed, corruptions=50), clean, atol=1e-6)
        for seed in range(10)
    )
    assert changed >= 8


def test_jpeg_glitch_retries_with_half_the_corruptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed decode retries with half the corruptions and still returns an image."""
    img = _image((37, 23), seed=16)
    counts: list[int] = []
    real_corrupt = glitch._corrupt
    real_decode = glitch._decode_jpeg
    calls = {"n": 0}

    def record_corrupt(data: bytes, count: int, rng: np.random.Generator) -> bytes:
        counts.append(count)
        return real_corrupt(data, count, rng)

    def flaky_decode(data: bytes) -> Image | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else real_decode(data)

    monkeypatch.setattr(glitch, "_corrupt", record_corrupt)
    monkeypatch.setattr(glitch, "_decode_jpeg", flaky_decode)
    out = _run("jpeg_glitch", img, corruptions=5)
    assert counts == [5, 2]
    assert out.shape == img.shape
    assert out.dtype == np.float32


def test_jpeg_glitch_falls_back_to_the_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """When every decode fails the input is returned unchanged instead of raising."""
    img = _image((37, 23), seed=17)
    counts: list[int] = []
    real_corrupt = glitch._corrupt

    def record_corrupt(data: bytes, count: int, rng: np.random.Generator) -> bytes:
        counts.append(count)
        return real_corrupt(data, count, rng)

    monkeypatch.setattr(glitch, "_corrupt", record_corrupt)
    monkeypatch.setattr(glitch, "_decode_jpeg", lambda data: None)
    out = _run("jpeg_glitch", img, corruptions=5)
    assert counts == [5, 2, 1]
    assert np.array_equal(out, img)


def test_jpeg_glitch_survives_an_encoding_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An encoder exception returns the input instead of propagating."""
    img = _image((5, 5), seed=18)

    def boom(rgb8: np.ndarray, quality: int) -> bytes:
        raise OSError("encoder exploded")

    monkeypatch.setattr(glitch, "_encode_jpeg", boom)
    out = _run("jpeg_glitch", img)
    assert np.array_equal(out, img)


def test_payload_start_follows_the_sos_header() -> None:
    """The corruption window starts after the SOS marker and its length field."""
    data = glitch._encode_jpeg(to_rgb8(_image((16, 16), seed=19)), 20)
    start = glitch._payload_start(data)
    sos = data.find(b"\xff\xda")
    assert sos > 0
    assert start == sos + 2 + int.from_bytes(data[sos + 2 : sos + 4], "big")
    assert start < len(data)
    assert glitch._payload_start(b"no marker here") == -1
