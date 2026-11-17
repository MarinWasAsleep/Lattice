"""Tests for the §18 greyscale mask system: no-op, PNG round-trip, refs and composition."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image as PILImage

import lattice_core.effects  # noqa: F401  (registers every effect)
from lattice_core.mask import (
    MAX_EMBED_BYTES,
    MaskRef,
    apply,
    export_png,
    from_base64,
    from_png,
    import_png,
    load_ref,
    to_png,
)
from lattice_core.registry import get_effect, list_effects, resolve_params

# Effects that accept a mask keyword directly (DEV-214 convention).
MASK_EFFECTS = ("displace", "pixel_sort", "crt")


def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(
    photo_like, rng: np.random.Generator,
) -> None:
    """Accept: a mask of all zeros is a no-op for every effect that accepts one."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for effect_id in MASK_EFFECTS:
        info = get_effect(effect_id)
        params = resolve_params(info.params, {})
        masked = info.fn(photo_like, params, rng, mask=zeros)
        assert np.allclose(masked, photo_like), effect_id


def test_zero_mask_composition_is_a_no_op_for_every_registered_effect(
    photo_like, rng: np.random.Generator,
) -> None:
    """Composition (the §18 localised form) keeps the source for any effect's zero mask."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for info in list_effects():
        params = resolve_params(info.params, {})
        effect = info.fn(photo_like, params, rng)
        assert np.allclose(apply(photo_like, effect, mask=zeros), photo_like), info.id


def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generator) -> None:
    """The composition mask is keyword-only and raises ValueError on a shape mismatch."""
    effect = get_effect("scanlines").fn(
        photo_like, resolve_params(get_effect("scanlines").params, {}), rng)
    wrong = np.zeros((photo_like.shape[0] + 1, photo_like.shape[1]), dtype=np.float32)
    with pytest.raises(ValueError):
        apply(photo_like, effect, mask=wrong)
    with pytest.raises(TypeError):
        apply(photo_like, effect, wrong)  # shape mismatch is caught before this; mask is kw-only


def test_apply_blends_by_mask_value(photo_like, rng: np.random.Generator) -> None:
    """Mask 1 keeps the effect; values in between interpolate between source and effect."""
    effect = np.clip(photo_like[::-1], 0.0, 1.0)
    all_one = np.ones(photo_like.shape[:2], dtype=np.float32)
    assert np.allclose(apply(photo_like, effect, mask=all_one), effect)
    half = np.full(photo_like.shape[:2], 0.5, dtype=np.float32)
    blended = apply(photo_like, effect, mask=half)
    expected = 0.5 * photo_like + 0.5 * effect
    assert np.allclose(blended, expected, atol=1e-6)


def test_png_round_trip_is_within_255th(rng: np.random.Generator) -> None:
    """Accept: a mask round-trips through PNG export/import within 1/255."""
    mask = np.clip(rng.random((64, 80), dtype=np.float32), 0.0, 1.0)
    restored = from_png(to_png(mask))
    assert mask.shape == restored.shape
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_png_export_import_round_trip(tmp_path, rng: np.random.Generator) -> None:
    """disk export and re-import match to 1/255 and stay a single greyscale plane."""
    mask = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
    path = export_png(mask, tmp_path / "mask.png")
    assert path.exists()
    restored = import_png(path)
    assert restored.ndim == 2
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_base64_embedded_png_validates_as_greyscale(rng: np.random.Generator) -> None:
    """An embedded base64 payload is a real 8-bit greyscale PNG."""
    mask = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
    b64 = __import__("base64").b64encode(to_png(mask)).decode("ascii")
    restored = from_base64(b64)
    with PILImage.open(io.BytesIO(__import__("base64").b64decode(b64))) as pil:
        assert pil.mode == "L"
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_mask_over_64kb_is_referenced_by_path_not_embedded(tmp_path) -> None:
    """Accept: a mask over 64 KB is referenced by path, not embedded."""
    rng = np.random.default_rng(0)
    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
    payload = to_png(big)
    assert len(payload) >= MAX_EMBED_BYTES
    target = tmp_path / "big_mask.png"
    target.write_bytes(payload)
    ref = MaskRef.from_mask(big, "large", path=str(target))
    assert not ref.embedded
    assert ref.path == str(target)
    assert ref.data is None
    assert ref.to_dict()["path"] == str(target)
    assert "data" not in ref.to_dict()


def test_large_mask_without_a_path_is_rejected(rng: np.random.Generator) -> None:
    """A mask over 64 KB cannot be embedded, so omitting the path raises ValueError."""
    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
    with pytest.raises(ValueError):
        MaskRef.from_mask(big, "large")


def test_small_mask_is_embedded_and_loads_back(rng: np.random.Generator) -> None:
    """A mask under 64 KB is embedded as base64 and resolves to the same plane."""
    small = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
    ref = MaskRef.from_mask(small, "tiny")
    assert ref.embedded
    assert ref.path is None
    assert ref.to_dict()["data"]
    restored = load_ref(ref)
    assert restored.shape == small.shape
    assert np.max(np.abs(restored - small)) <= 1.0 / 255.0


def test_mask_ref_round_trips_through_its_dict(rng: np.random.Generator) -> None:
    """to_dict()/from_dict() preserve an embedded mask reference exactly."""
    mask = np.clip(rng.random((40, 40), dtype=np.float32), 0.0, 1.0)
    ref = MaskRef.from_mask(mask, "ref")
    rebuilt = MaskRef.from_dict(ref.to_dict())
    assert rebuilt == ref
    assert MaskRef.from_dict(ref.to_dict()).data == ref.data


def test_mask_ref_to_dict_has_exactly_one_of_path_or_data(tmp_path, rng) -> None:
    """A path reference serialises with path and no data; a corrupt dict is rejected."""
    mask = np.clip(rng.random((8, 8), dtype=np.float32), 0.0, 1.0)
    path = export_png(mask, tmp_path / "mask.png")
    assert MaskRef.from_path(path, "x").to_dict()["path"] == str(path)
    with pytest.raises(ValueError):
        MaskRef.from_dict({"id": "a", "width": 4, "height": 4})
    with pytest.raises(ValueError):
        MaskRef.from_dict({"id": "a", "width": 4, "height": 4,
                           "path": "p", "data": "d"})