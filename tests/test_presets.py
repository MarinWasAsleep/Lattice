"""Tests for preset serialisation (T09), using test-only registry entries."""

from __future__ import annotations

import json

import numpy as np
import pytest

from dithercraft.core import registry
from dithercraft.core.pipeline import EffectInstance, PaletteSpec, PipelineSpec
from dithercraft.core.presets import from_json, load_preset, save_preset, to_json
from dithercraft.core.registry import AlgorithmInfo, EffectInfo


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
        version=1,
        pre_effects=[
            EffectInstance("test_invert", {"amount": 0.5}, True),
            EffectInstance("test_invert", {}, False),
        ],
        brightness=0.1,
        contrast=-0.2,
        gamma=1.5,
        pixel_size=4,
        algorithm_id="test_nearest",
        algorithm_params={"level": 0.25},
        palette=PaletteSpec(
            source="custom", name="mine", colors=["#000000", "#FF0000"], extract_k=6,
            extract_method="median_cut",
        ),
        post_effects=[EffectInstance("test_invert", {"amount": 1.0}, True)],
        seed=42,
    )


def test_to_json_uses_field_names_and_indent(test_registry):
    """The JSON object has exactly the dataclass field names and two-space indent."""
    text = to_json(PipelineSpec())
    data = json.loads(text)
    assert set(data) == set(PipelineSpec.__dataclass_fields__)
    assert '\n  "version": 1' in text


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
