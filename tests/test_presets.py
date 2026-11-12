"""Tests for preset serialisation (T09), using test-only registry entries."""

from __future__ import annotations

import json

import numpy as np
import pytest

from lattice_dither.core import registry
from lattice_dither.core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, PresetMeta
from lattice_dither.core.presets import from_json, load_preset, save_preset, to_json
from lattice_dither.core.registry import AlgorithmInfo, EffectInfo


def _nearest(img, palette, params):
    """Test algorithm: plain nearest-colour mapping."""
    return np.zeros(img.shape[:2], dtype=np.int32)


def _invert(img, params, rng):
    """Test effect: invert every channel."""
    return np.ascontiguousarray(1.0 - img, dtype=np.float32)


@pytest.fixture
def test_registry(monkeypatch):
    """Register the test-only algorithm and effect ids used by the presets."""
    monkeypatch.setitem(
        registry._ALGORITHMS,
        "test_nearest",
        AlgorithmInfo(
            id="test_nearest", name="Test nearest", family="other", params=(), fn=_nearest
        ),
    )
    monkeypatch.setitem(
        registry._EFFECTS,
        "test_invert",
        EffectInfo(id="test_invert", name="Test invert", params=(), fn=_invert),
    )


def _full_spec() -> PipelineSpec:
    """Return a spec that exercises every field."""
    return PipelineSpec(
        version=2,
        pre_effects=[
            EffectInstance("test_invert", {"amount": 0.5}, True),
            EffectInstance("test_invert", {}, False),
        ],
        brightness=0.1,
        contrast=-0.2,
        gamma=1.5,
        saturation=0.3,
        pre_blur=2.0,
        auto_levels=True,
        color_metric="oklab",
        pixel_size=4,
        algorithm_id="test_nearest",
        algorithm_params={"level": 0.25},
        palette=PaletteSpec(
            source="custom", name="mine", colors=["#000000", "#FF0000"], extract_k=6,
            extract_method="median_cut", locked=[0], order=[1, 0],
        ),
        post_effects=[EffectInstance("test_invert", {"amount": 1.0}, True)],
        seed=42,
        meta=PresetMeta(
            name="Mine", author="Marin", description="A preset", tags=["test"], thumbnail="t.png"
        ),
    )


def test_to_json_uses_field_names_and_indent(test_registry):
    """The JSON object has exactly the dataclass field names and two-space indent."""
    text = to_json(PipelineSpec())
    data = json.loads(text)
    assert set(data) == set(PipelineSpec.__dataclass_fields__)
    assert '\n  "version": 2' in text


def test_round_trip_full_spec(test_registry):
    """A fully populated spec survives a JSON round trip unchanged."""
    spec = _full_spec()
    assert from_json(to_json(spec)) == spec


def test_round_trip_defaults(test_registry):
    """A spec with only the algorithm set survives a JSON round trip unchanged."""
    spec = PipelineSpec(algorithm_id="test_nearest")
    assert from_json(to_json(spec)) == spec


def test_missing_keys_take_defaults(test_registry):
    """Only the given keys are applied; the rest keep their defaults."""
    spec = from_json('{"algorithm_id": "test_nearest"}')
    assert spec == PipelineSpec(algorithm_id="test_nearest")


def test_unknown_top_level_keys_ignored(test_registry):
    """Unknown top-level keys are ignored instead of raising."""
    spec = from_json('{"algorithm_id": "test_nearest", "future_field": [1, 2]}')
    assert spec.algorithm_id == "test_nearest"


def test_unknown_algorithm_id_names_it(test_registry):
    """An unknown algorithm id raises ValueError naming the id."""
    with pytest.raises(ValueError, match="no_such_algorithm"):
        from_json('{"algorithm_id": "no_such_algorithm"}')


def test_unknown_effect_id_names_it(test_registry):
    """An unknown effect id raises ValueError naming the id."""
    text = '{"pre_effects": [{"effect_id": "no_such_effect"}]}'
    with pytest.raises(ValueError, match="no_such_effect"):
        from_json(text)


def test_effect_entry_without_id(test_registry):
    """An effect entry without an id is rejected."""
    with pytest.raises(ValueError):
        from_json('{"post_effects": [{"params": {}}]}')


def test_effect_enabled_flag_round_trip(test_registry):
    """The enabled flag is preserved, including False."""
    spec = from_json('{"pre_effects": [{"effect_id": "test_invert", "enabled": false}]}')
    assert spec.pre_effects == [EffectInstance("test_invert", {}, False)]


def test_unknown_palette_source(test_registry):
    """An unknown palette source raises ValueError."""
    with pytest.raises(ValueError, match="bogus"):
        from_json('{"palette": {"source": "bogus"}}')


def test_palette_defaults_when_partial(test_registry):
    """A partial palette object keeps the remaining palette defaults."""
    spec = from_json('{"palette": {"colors": ["#000000", "#FFFFFF"]}}')
    assert spec.palette == PaletteSpec(colors=["#000000", "#FFFFFF"])


@pytest.mark.parametrize("text", ["{", "[]", '"text"', "null"])
def test_invalid_json_raises_value_error(test_registry, text):
    """Malformed or non-object JSON raises ValueError."""
    with pytest.raises(ValueError):
        from_json(text)


def test_bad_number_raises(test_registry):
    """A non-numeric value for a numeric key raises ValueError."""
    with pytest.raises(ValueError, match="pixel_size"):
        from_json('{"pixel_size": "big"}')


def test_save_and_load_preset(test_registry, tmp_path):
    """save_preset writes UTF-8 JSON and load_preset reads it back."""
    spec = _full_spec()
    path = tmp_path / "nested" / "preset.json"
    save_preset(path, spec)
    assert path.read_text(encoding="utf-8") == to_json(spec)
    assert load_preset(path) == spec


def test_save_preset_accepts_str_path(test_registry, tmp_path):
    """save_preset and load_preset accept plain strings."""
    path = str(tmp_path / "preset.json")
    save_preset(path, PipelineSpec(algorithm_id="test_nearest"))
    assert load_preset(path).algorithm_id == "test_nearest"


def test_v1_preset_loads_with_version_one(test_registry):
    """A version 1 preset loads, reports version 1 and takes the v2 defaults."""
    spec = from_json('{"version": 1, "algorithm_id": "test_nearest"}')
    assert spec.version == 1
    assert spec.saturation == 0.0
    assert spec.pre_blur == 0.0
    assert spec.auto_levels is False
    assert spec.color_metric == "srgb"
    assert spec.meta == PresetMeta()


def test_to_json_always_writes_the_current_version(test_registry):
    """Saving a v1 spec upgrades it to the current preset version."""
    text = to_json(PipelineSpec(version=1, algorithm_id="test_nearest"))
    assert json.loads(text)["version"] == 2


@pytest.mark.parametrize("version", [0, 3, 4, -1])
def test_unsupported_version_names_it(test_registry, version):
    """Any version outside 1 and 2 raises ValueError naming the version."""
    with pytest.raises(ValueError, match=str(version)):
        from_json(f'{{"version": {version}}}')


def test_unknown_color_metric_names_it(test_registry):
    """An unknown colour metric raises ValueError naming it."""
    with pytest.raises(ValueError, match="cmyk"):
        from_json('{"color_metric": "cmyk"}')


def test_meta_round_trips(test_registry):
    """Every meta field survives a round trip, including tags."""
    meta = PresetMeta(
        name="N", author="A", description="D", tags=["x", "y"], thumbnail="t.png"
    )
    spec = PipelineSpec(algorithm_id="test_nearest", meta=meta)
    assert from_json(to_json(spec)).meta == meta


def test_partial_meta_keeps_defaults(test_registry):
    """A meta object with one key leaves the other fields at their defaults."""
    spec = from_json('{"meta": {"author": "Marin"}}')
    assert spec.meta == PresetMeta(author="Marin")


def test_locked_and_order_round_trip(test_registry):
    """The palette lock list and display order survive a round trip."""
    palette = PaletteSpec(source="custom", colors=["#000000", "#FFFFFF"], locked=[1], order=[1, 0])
    spec = PipelineSpec(algorithm_id="test_nearest", palette=palette)
    assert from_json(to_json(spec)).palette == palette


def test_conditioning_fields_round_trip(test_registry):
    """The four conditioning fields survive a round trip."""
    spec = PipelineSpec(
        algorithm_id="test_nearest",
        saturation=-0.5,
        pre_blur=7.5,
        auto_levels=True,
        color_metric="lab2000",
    )
    assert from_json(to_json(spec)) == spec


def test_to_json_is_byte_stable(test_registry):
    """Two calls on the same spec produce identical bytes."""
    spec = _full_spec()
    assert to_json(spec) == to_json(spec)
