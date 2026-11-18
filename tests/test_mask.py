"""Tests for the §18 greyscale mask system: no-op, PNG round-trip, refs and composition."""

from __future__ import annotations

import base64
import inspect
import io
import json
from collections.abc import Callable
from typing import Any, cast

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
    resolve_masks,
    to_png,
)
from lattice_core.preset import from_json, to_json
from lattice_core.registry import get_effect, list_effects, resolve_params


def _mask_effects() -> list[str]:
    """Return every registered effect whose signature accepts a ``mask`` keyword."""
    return [info.id for info in list_effects()
            if "mask" in inspect.signature(info.fn).parameters]


def _masked_call(effect_id: str) -> Callable[..., Any]:
    """Return the effect function widened to accept its optional mask keyword.

    ``EffectFn`` in the registry declares only ``(img, params, rng)``; the mask
    keyword is a per-effect extension (§18), so the call is typed through Any.
    """
    return cast(Callable[..., Any], get_effect(effect_id).fn)


def test_the_registry_has_effects_that_accept_a_mask() -> None:
    """Discovery is not vacuous: at least one registered effect takes a mask."""
    assert _mask_effects(), "no registered effect accepts a mask"


def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(photo_like) -> None:
    """Accept: a mask of all zeros is a no-op for every effect that accepts one."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for effect_id in _mask_effects():
        info = get_effect(effect_id)
        params = resolve_params(info.params, {})
        masked = _masked_call(effect_id)(photo_like, params, np.random.default_rng(0), mask=zeros)
        assert np.allclose(masked, photo_like), effect_id


def test_zero_mask_composition_keeps_the_source(photo_like, rng: np.random.Generator) -> None:
    """apply() algebra on a zero mask; a supporting property, not the accept item."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for info in list_effects():
        params = resolve_params(info.params, {})
        effect = info.fn(photo_like, params, rng)
        assert np.allclose(apply(photo_like, effect, mask=zeros), photo_like), info.id


def test_zero_mask_composition_survives_nan_in_the_effect(photo_like) -> None:
    """A zero weight never multiplies the effect, so NaN/inf cannot leak into the source."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    broken = np.full_like(photo_like, np.nan)
    broken[0, 0, 0] = np.inf
    composed = apply(photo_like, broken, mask=zeros)
    assert np.array_equal(composed, photo_like)
    assert np.isfinite(composed).all()


def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generator) -> None:
    """The composition mask is keyword-only and raises ValueError on a shape mismatch."""
    effect = get_effect("scanlines").fn(
        photo_like, resolve_params(get_effect("scanlines").params, {}), rng)
    wrong = np.zeros((photo_like.shape[0] + 1, photo_like.shape[1]), dtype=np.float32)
    with pytest.raises(ValueError):
        apply(photo_like, effect, mask=wrong)
    with pytest.raises(TypeError):
        # The keyword-only contract is the point: a positional third argument is refused.
        apply(photo_like, effect, wrong)  # type: ignore[call-arg]


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
    """Disk export and re-import match to 1/255 and stay a single greyscale plane."""
    mask = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
    path = export_png(mask, tmp_path / "mask.png")
    assert path.exists()
    restored = import_png(path)
    assert restored.ndim == 2
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_base64_embedded_png_validates_as_greyscale(rng: np.random.Generator) -> None:
    """An embedded base64 payload is a real 8-bit greyscale PNG."""
    mask = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
    payload = to_png(mask)
    b64 = base64.b64encode(payload).decode("ascii")
    restored = from_base64(b64)
    with PILImage.open(io.BytesIO(payload)) as pil:
        assert pil.mode == "L"
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_png_16_bit_greyscale_is_not_saturated() -> None:
    """A 16-bit PNG keeps its tones instead of saturating to white through convert('L')."""
    ramp = np.linspace(0, 65535, 64, dtype=np.uint16).reshape(8, 8)
    buffer = io.BytesIO()
    PILImage.fromarray(ramp).save(buffer, format="PNG")
    restored = from_png(buffer.getvalue())
    assert restored.shape == (8, 8)
    assert restored.min() == pytest.approx(0.0, abs=1e-6)
    assert restored.max() == pytest.approx(1.0, abs=1e-6)
    assert np.max(np.abs(restored - ramp.astype(np.float32) / 65535.0)) <= 1.0 / 255.0


def test_rgba_png_is_composited_over_white() -> None:
    """A semi-transparent painted mask is flattened onto white, not onto black."""
    data = np.zeros((4, 4, 4), dtype=np.uint8)
    data[..., 0] = 255
    data[..., 3] = 128
    buffer = io.BytesIO()
    PILImage.fromarray(data, mode="RGBA").save(buffer, format="PNG")
    restored = from_png(buffer.getvalue())
    assert restored.shape == (4, 4)
    assert restored.min() > 0.5


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


def test_large_mask_without_a_path_is_rejected() -> None:
    """A mask over 64 KB cannot be embedded, so omitting the path raises ValueError."""
    rng = np.random.default_rng(1)
    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
    with pytest.raises(ValueError, match="64 KiB"):
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
    assert rebuilt.data == ref.data


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


def _preset_with_masks(section: dict) -> str:
    """Return a v3 preset text carrying section as its `masks` object."""
    data = {
        "version": 3, "app": "glitch", "meta": {},
        "effects": [{"name": "crt", "params": {}, "enabled": True, "stage": "post",
                     "mask": "gate"}],
        "masks": section,
    }
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def test_masks_section_round_trips_through_the_preset(tmp_path) -> None:
    """Accept: mask references (base64 and path) survive preset load/resolve/save intact.

    A procedural descriptor is left untouched: L19 owns references, not descriptors.
    """
    rng = np.random.default_rng(2)
    small = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
    embedded = MaskRef.from_mask(small, "gate").to_dict()
    big = np.clip(rng.random((256, 256), dtype=np.float32), 0.0, 1.0)
    target = tmp_path / "large.png"
    target.write_bytes(to_png(big))
    on_disk = MaskRef.from_mask(big, "wide", path=str(target)).to_dict()
    section = {"gate": embedded, "wide": on_disk, "flip": {"kind": "v_flip"}}

    preset = from_json(_preset_with_masks(section))
    planes = resolve_masks(preset.masks)

    assert set(planes) == {"gate", "wide"}
    assert planes["gate"].shape == (32, 32)
    assert np.max(np.abs(planes["gate"] - small)) <= 1.0 / 255.0
    assert planes["wide"].shape == (256, 256)
    assert preset.masks["flip"] == {"kind": "v_flip"}

    saved = json.loads(to_json(preset))
    assert saved["masks"] == section
    assert saved["effects"][0]["mask"] == "gate"
    assert saved["seed"] == 0


def test_resolve_masks_ignores_empty_and_unknown_entries() -> None:
    """An absent section, an empty dict and a descriptor all resolve to no planes."""
    assert resolve_masks(None) == {}
    assert resolve_masks({}) == {}
    assert resolve_masks({"flip": {"kind": "v_flip"}}) == {}


def test_resolve_masks_keys_by_section_id(tmp_path) -> None:
    """The plane is keyed by the preset id, which is what ``effects[].mask`` names."""
    mask = np.full((6, 5), 0.5, dtype=np.float32)
    path = export_png(mask, tmp_path / "m.png")
    planes = resolve_masks({"gate": {"path": str(path)}, "other": {"path": str(path)}})
    assert set(planes) == {"gate", "other"}
    assert all(plane.shape == (6, 5) for plane in planes.values())


def test_resolve_masks_rejects_a_corrupt_reference() -> None:
    """A mask entry carrying both a path and data is rejected, not silently preferred."""
    with pytest.raises(ValueError):
        resolve_masks({"bad": {"id": "bad", "width": 4, "height": 4,
                               "path": "p.png", "data": "eA=="}})
