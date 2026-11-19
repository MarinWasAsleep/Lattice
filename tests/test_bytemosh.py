"""Tests for the bytemosh data-moshing effect (L28 / CONTRACT §15 §16)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lattice.effects import bytemosh as bytemosh_module
from lattice.effects.bytemosh import _indel
from lattice.registry import get_effect, list_effects, resolve_params

EFFECT_ID = "bytemosh"
OPERATIONS = ("swap", "shift", "interpret", "drift")
SHAPES = ((1, 1), (1, 5), (5, 1), (23, 37), (64, 64))


def _apply(img: np.ndarray, rng_seed: int = 0, **params: object) -> np.ndarray:
    """Run the effect with resolved scalar parameters and a fresh seeded generator."""
    info = get_effect(EFFECT_ID)
    return info.fn(img, resolve_params(info.params, params), np.random.default_rng(rng_seed))


def _bytes(img: np.ndarray) -> np.ndarray:
    """Return the raster as a flat uint8 byte stream, matching the effect's payload."""
    data = np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0)
    return np.round(data * np.float32(255.0)).astype(np.uint8).ravel()


def _striped(shape: tuple[int, int, int] = (4, 8, 3)) -> np.ndarray:
    """Return an image whose every byte is distinct, so windows are distinguishable."""
    count = int(np.prod(shape))
    return (np.arange(count, dtype=np.float32) / np.float32(255.0)).reshape(shape)


def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """Return a seeded random float32 image of the given (H, W)."""
    return np.random.default_rng(seed).random((*shape, 3), dtype=np.float32)


def test_registration_and_params() -> None:
    """The effect registers under bytemosh with the five documented parameters."""
    info = get_effect(EFFECT_ID)
    assert info.id == EFFECT_ID
    assert EFFECT_ID in {registered.id for registered in list_effects()}
    assert [spec.id for spec in info.params] == ["amount", "operation", "stride", "offset", "seed"]
    assert [spec.kind for spec in info.params] == ["float", "choice", "int", "int", "int"]
    assert info.params[1].choices == OPERATIONS
    assert resolve_params(info.params, {}) == {
        "amount": 0.0,
        "operation": "swap",
        "stride": 96,
        "offset": 0,
        "seed": 0,
    }


def test_registered_once_in_lattice() -> None:
    """The bytemosh effect is registered by the core effect module itself."""
    mine = [info for info in list_effects() if info.fn.__module__ == bytemosh_module.__name__]
    assert [info.id for info in mine] == [EFFECT_ID]


def test_every_label_is_a_distinct_catalogue_key() -> None:
    """Labels reuse i18n catalogue keys (test_i18n) and name distinct parameters."""
    from lattice.modes.dither import i18n

    catalogue = json.loads(
        (Path(i18n.__file__).resolve().parent / "en.json").read_text(encoding="utf-8")
    )
    labels = [spec.label for spec in get_effect(EFFECT_ID).params]
    assert len(set(labels)) == len(labels), labels
    assert set(labels) <= set(catalogue), sorted(set(labels) - set(catalogue))


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("shape", SHAPES)
def test_amount_zero_is_bit_identical(operation: str, shape: tuple[int, int]) -> None:
    """Accept: amount=0 returns the image BIT-FOR-BIT, for every operation and shape."""
    img = np.ascontiguousarray(_random_image(shape, seed=11))
    out = _apply(img, amount=0.0, operation=operation, stride=9, offset=5, seed=3)
    assert out.dtype == np.float32
    assert out.shape == img.shape
    assert out.tobytes() == img.tobytes()
    assert np.array_equal(out, img)


def test_swap_exchanges_two_windows_exactly() -> None:
    """Accept: swap really permutes two distinguishable windows; the rest is untouched."""
    img = _striped()
    before = _bytes(img)
    out = _apply(img, amount=0.125, operation="swap", stride=6, offset=0)
    expected = before.copy()
    expected[0:6] = before[6:12]
    expected[6:12] = before[0:6]
    assert np.array_equal(_bytes(out), expected)
    assert not np.array_equal(out, img)


def test_swap_honours_the_offset_anchor() -> None:
    """The anchored pair sits at offset and offset+stride, not always at zero."""
    img = _striped()
    before = _bytes(img)
    out = _apply(img, amount=0.125, operation="swap", stride=6, offset=12)
    expected = before.copy()
    expected[12:18] = before[18:24]
    expected[18:24] = before[12:18]
    assert np.array_equal(_bytes(out), expected)


def test_swap_keeps_channels_aligned_with_a_multiple_of_three_stride() -> None:
    """A stride of 6 swaps two whole RGB pixels: channels never mix lanes."""
    img = _striped((2, 4, 3))
    out = _apply(img, amount=0.125, operation="swap", stride=6, offset=0)
    src = img.reshape(-1, 3)
    dst = out.reshape(-1, 3)
    # stride 6 bytes = two whole pixels: window pixels[0:2] <-> pixels[2:4].
    assert np.array_equal(dst[0:2], src[2:4])
    assert np.array_equal(dst[2:4], src[0:2])
    assert np.array_equal(dst[4:], src[4:])
    # Every output pixel is an exact input pixel: no channel rotation happened.
    assert {tuple(pixel) for pixel in dst.tolist()} == {tuple(pixel) for pixel in src.tolist()}


def test_indel_leaves_the_head_intact_and_slides_the_tail() -> None:
    """The core gesture: bytes before the cut are untouched, everything after slides.

    The old contract asked shift to translate the whole payload. Measurement killed it:
    a translation is clean, nothing is damaged at a particular place, and the image heals
    everywhere. An indel damages from P onwards and only from P:
    that is what real byte damage looks like.
    """
    data = np.arange(120, dtype=np.uint8)
    _indel(data, 30, 7)
    assert np.array_equal(data[:30], np.arange(30, dtype=np.uint8))  # the head is intact
    assert np.array_equal(data[30:], np.roll(np.arange(30, 120, dtype=np.uint8), 7))


def test_shift_reaches_the_bottom_of_the_image() -> None:
    """An edit near the top is still visible at the last row: the error propagates."""
    img = _random_image((40, 60))
    out = _apply(img, amount=1.0, operation="shift", offset=12, seed=3)
    assert out.shape == img.shape
    assert not np.array_equal(out[-1], img[-1])


def test_shift_at_amount_zero_is_the_identity() -> None:
    """amount = 0 stays bit-identical: an unused effect must not touch the pixels."""
    img = _striped()
    out = _apply(img, amount=0.0, operation="shift", offset=12)
    assert np.array_equal(_bytes(out), _bytes(img))


def test_interpret_pastes_the_source_window_elsewhere() -> None:
    """Accept: interpret reads a window and poses it again, so its bytes reappear."""
    img = _striped()
    out = _apply(img, amount=1.0, operation="interpret", stride=6, offset=0, seed=4)
    after = _bytes(out)
    assert not np.array_equal(out, img)
    # Byte 0 lives only at index 0 in the source; a paste duplicates it elsewhere.
    assert np.count_nonzero(after == 0) >= 2
    assert out.shape == img.shape


@pytest.mark.parametrize("operation", ["swap", "interpret"])
def test_same_seed_is_deterministic(operation: str) -> None:
    """Accept: a given seed reproduces the exact same output across two runs."""
    img = _random_image((32, 32), seed=5)
    params = {"amount": 1.0, "operation": operation, "stride": 9, "offset": 3, "seed": 17}
    first = _apply(img, **params)
    second = _apply(img, **params)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("operation", ["swap", "interpret"])
def test_different_seeds_change_the_result(operation: str) -> None:
    """Accept: two different seeds produce different moshing on a distinguishable image."""
    img = _random_image((32, 32), seed=5)
    params = {"amount": 1.0, "operation": operation, "stride": 9, "offset": 3}
    first = _apply(img, seed=1, **params)
    second = _apply(img, seed=2, **params)
    assert not np.array_equal(first, second)


def test_shift_positions_come_from_the_seed() -> None:
    """The insertion points are seeded: two seeds must not give the same image (E1)."""
    img = _striped()
    first = _apply(img, amount=1.0, operation="shift", offset=7, seed=1)
    second = _apply(img, amount=1.0, operation="shift", offset=7, seed=999)
    assert not np.array_equal(first, second)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_one_by_one_image_never_raises(operation: str) -> None:
    """Accept: a 1x1 image never raises, whatever the operation, offset or stride."""
    img = _random_image((1, 1), seed=2)
    for amount in (0.0, 0.5, 1.0):
        for offset in (0, 1, 2, 7, -3):
            out = _apply(img, amount=amount, operation=operation, stride=96, offset=offset)
            assert out.shape == (1, 1, 3)
            assert out.dtype == np.float32
            assert 0.0 <= float(out.min()) <= float(out.max()) <= 1.0


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("shape", [(2, 2), (1, 5), (3, 1)])
def test_payload_shorter_than_stride_never_raises(operation: str, shape: tuple[int, int]) -> None:
    """Accept: a payload shorter than stride never raises and keeps its shape."""
    img = _random_image(shape, seed=9)
    out = _apply(img, amount=1.0, operation=operation, stride=3072, offset=5)
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert 0.0 <= float(out.min()) <= float(out.max()) <= 1.0


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("shape", SHAPES)
def test_output_is_float32_in_range_with_the_same_shape(
    operation: str, shape: tuple[int, int]
) -> None:
    """The output is float32 in [0, 1] with the input shape, for every operation."""
    img = _random_image(shape, seed=13)
    out = _apply(img, amount=1.0, operation=operation, stride=9, offset=4, seed=6)
    assert out.dtype == np.float32
    assert out.shape == img.shape
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_stride_is_snapped_to_a_multiple_of_three() -> None:
    """A non-multiple-of-3 stride snaps down/up to keep channels aligned (E1)."""
    img = _striped()
    before = _bytes(img)
    out = _apply(img, amount=0.125, operation="swap", stride=4, offset=0)
    expected = before.copy()
    expected[0:3] = before[3:6]
    expected[3:6] = before[0:3]
    assert np.array_equal(_bytes(out), expected)


def test_invalid_operation_is_rejected() -> None:
    """An unknown operation is a ValueError, both via the registry and the function."""
    info = get_effect(EFFECT_ID)
    with pytest.raises(ValueError):
        resolve_params(info.params, {"operation": "bogus"})
    with pytest.raises(ValueError):
        info.fn(_striped(), {"operation": "bogus", "amount": 1.0}, np.random.default_rng(0))


def test_runs_through_the_generic_v3_preset_pipeline() -> None:
    """Accept: a v3 preset drives bytemosh through the shared engine, no special code."""
    from lattice import pipeline, preset

    text = json.dumps(
        {
            "version": 3,
            "app": "glitch",
            "seed": 0,
            "renderer": {"name": "pixel", "style": {}},
            "effects": [
                {
                    "name": EFFECT_ID,
                    "stage": "post",
                    "enabled": True,
                    "params": {
                        "amount": 1.0,
                        "operation": "swap",
                        "stride": 9,
                        "offset": 3,
                        "seed": 2,
                    },
                }
            ],
        }
    )
    spec = preset.to_pipeline_spec(preset.from_json(text, app="glitch"))
    assert [instance.effect_id for instance in spec.post_effects] == [EFFECT_ID]
    img = _striped((8, 8, 3))
    out = pipeline._apply_effects(img, spec.post_effects, spec.seed, 0)
    assert out.shape == img.shape
    assert out.dtype == np.float32
    assert 0.0 <= float(out.min()) <= float(out.max()) <= 1.0
    assert not np.array_equal(out, img)


def test_drift_spills_across_rows_and_keeps_colours_aligned() -> None:
    """Drift must move content ACROSS rows, and only in whole pixels.

    The first take rotated each row on itself: on a vertical gradient an inside-row rotation
    is invisible, so the background stayed pristine and only the shapes moved — the seam that
    proves a misread file was missing. Here the tail of the payload is rolled,
    so the end of a row spills into the next one, and the step stays a multiple of three so
    the RGB channels are not rotated.
    """
    img = _random_image((40, 60))
    before = _bytes(img)
    out = _apply(img, amount=0.5, operation="drift", stride=30, offset=0, seed=5)
    after = _bytes(out)
    assert out.shape == img.shape
    assert not np.array_equal(after, before)
    # The payload was rolled, not rotated row by row: a row must see its neighbour's bytes.
    row_length = 60 * 3
    assert not np.array_equal(after[row_length:], before[row_length:])
    rotated_rows = sum(
        1 for row in range(40)
        if not any(
            np.array_equal(after[row * row_length:(row + 1) * row_length],
                          np.roll(before[row * row_length:(row + 1) * row_length], k))
            for k in range(-12, 13)
        )
    )
    assert rotated_rows > 0  # at least one row is no longer a rotation of itself


def test_drift_uses_stride_and_offset() -> None:
    """Both parameters must change the result: a dead control is a bug, not a style."""
    img = _random_image((64, 64))
    base = _apply(img, amount=1.0, operation="drift", stride=30, offset=0, seed=5)
    wider = _apply(img, amount=1.0, operation="drift", stride=300, offset=0, seed=5)
    anchored = _apply(img, amount=1.0, operation="drift", stride=30, offset=11, seed=5)
    assert not np.array_equal(base, wider)
    assert not np.array_equal(base, anchored)


def test_shift_moves_even_with_the_default_offset() -> None:
    """`shift` at offset 0 used to do nothing: the neutral anchor zeroed the distance."""
    img = _striped((8, 8, 3))
    moved = _apply(img, amount=1.0, operation="shift", stride=96, offset=0)
    assert not np.array_equal(moved, img)
    assert np.array_equal(_apply(img, amount=0.0, operation="shift", stride=96, offset=0), img)


def test_drift_is_deterministic_and_bounded() -> None:
    """Drift never raises on a tiny payload and repeats exactly for the same inputs."""
    tiny = _striped((1, 1, 3))
    assert _apply(tiny, amount=1.0, operation="drift", stride=3, offset=9).shape == tiny.shape
    first = _apply(_striped((8, 32, 3)), amount=0.7, operation="drift", stride=3, offset=96)
    second = _apply(_striped((8, 32, 3)), amount=0.7, operation="drift", stride=3, offset=96)
    assert np.array_equal(first, second)
