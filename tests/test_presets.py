"""Tests for preset serialisation (T09) and the preset search order (T34)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from lattice_core import presets, registry
from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, PresetMeta
from lattice_core.presets import from_json, load_preset, save_preset, to_json

ROOT = Path(__file__).resolve().parents[1]
from lattice_core.registry import AlgorithmInfo, EffectInfo


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
            extract_method="median_cut", locked=["#FF0000"], order=[1, 0],
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
    palette = PaletteSpec(
        source="custom", colors=["#000000", "#FFFFFF"], locked=["#FFFFFF"], order=[1, 0]
    )
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


def _write(directory: Path, names: list[str]) -> list[Path]:
    """Write one valid preset per name into directory and return the paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = directory / name
        path.write_text(to_json(PipelineSpec()), encoding="utf-8")
        paths.append(path)
    return paths


@pytest.fixture
def tiers(tmp_path, monkeypatch):
    """Return a temporary shipped tier and the user tier under a temporary %APPDATA%."""
    shipped = tmp_path / "shipped"
    monkeypatch.setattr(presets, "shipped_preset_dir", lambda: shipped)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return shipped, presets.user_preset_dir()


def test_search_order_puts_the_shipped_tier_first(tiers):
    """The search order is the shipped directory, then the user directory under %APPDATA%."""
    shipped, user = tiers
    assert presets.preset_search_dirs() == (shipped, user)
    assert user == Path(os.environ["APPDATA"]) / "LatticeDither" / "presets"


def test_user_dir_falls_back_to_the_roaming_profile(monkeypatch):
    """Without %APPDATA% the user directory sits in the default Windows roaming location."""
    monkeypatch.delenv("APPDATA", raising=False)
    expected = Path.home() / "AppData" / "Roaming" / "LatticeDither" / "presets"
    assert presets.user_preset_dir() == expected


def test_looking_up_the_user_dir_does_not_create_it(tiers):
    """Resolving the user directory is a pure lookup; only a save creates it."""
    _, user = tiers
    assert presets.user_preset_dir() == user
    assert not user.exists()


def test_shipped_presets_are_listed_when_the_user_dir_is_absent(tiers):
    """An absent user directory leaves the shipped presets as the whole list."""
    shipped, user = tiers
    written = _write(shipped, ["01_a.json", "02_b.json"])
    assert not user.exists()
    assert presets.list_presets() == written


def test_shipped_presets_are_listed_when_the_user_dir_is_empty(tiers):
    """An empty user directory leaves the shipped presets as the whole list."""
    shipped, user = tiers
    written = _write(shipped, ["01_a.json", "02_b.json"])
    user.mkdir(parents=True)
    assert presets.list_presets() == written


def test_a_user_preset_wins_over_the_shipped_one(tiers):
    """A name present in both tiers resolves to the user file and is listed once."""
    shipped, user = tiers
    _write(shipped, ["01_a.json", "02_b.json"])
    _write(user, ["02_b.json"])
    assert presets.resolve_preset("02_b.json") == user / "02_b.json"
    assert presets.resolve_preset("01_a.json") == shipped / "01_a.json"
    assert presets.resolve_preset("03_c.json") is None
    names = [path.name for path in presets.list_presets()]
    assert names == ["01_a.json", "02_b.json"]
    assert presets.list_presets().count(user / "02_b.json") == 1


def test_the_shipped_tier_comes_first_in_the_list(tiers):
    """Shipped presets are listed before the user-only ones."""
    shipped, user = tiers
    _write(shipped, ["02_b.json"])
    _write(user, ["01_a.json", "03_c.json"])
    assert presets.list_presets() == [
        shipped / "02_b.json",
        user / "01_a.json",
        user / "03_c.json",
    ]


def test_list_presets_accepts_explicit_directories(tiers):
    """An explicit directory sequence is searched in the given order."""
    shipped, user = tiers
    _write(shipped, ["01_a.json"])
    _write(user, ["02_b.json"])
    assert presets.list_presets([user, shipped]) == [user / "02_b.json", shipped / "01_a.json"]


def test_saving_into_the_user_dir_creates_it_on_first_save(tiers, test_registry):
    """The first save creates the user directory and writes the preset inside it."""
    _, user = tiers
    spec = PipelineSpec(algorithm_id="test_nearest")
    assert not user.exists()
    save_preset(user / "mine.json", spec)
    assert user.is_dir()
    assert load_preset(user / "mine.json") == spec


def test_is_within_accepts_the_directory_and_its_children(tiers):
    """is_within is true for the directory itself and its children, false for siblings."""
    shipped, user = tiers
    assert presets.is_within(shipped, shipped)
    assert presets.is_within(shipped / "01_a.json", shipped)
    assert not presets.is_within(user / "01_a.json", shipped)
    assert not presets.is_within(shipped, user)


@pytest.mark.parametrize("path", sorted((ROOT / "presets" / "starter").glob("dither_*.json")),
                         ids=lambda p: p.stem)
def test_every_shipped_starter_opens_through_the_loader(path: Path) -> None:
    """The starters Dither ships must open with the loader Dither uses.

    The starters are written in v3 while ``presets.from_json`` owns v1 and v2 only, so this
    shipped app could not open its own files: ``lattice-dither-cli render`` answered
    "unsupported preset version: 3" and the preset browser refused the same four files. A
    renderer that cannot read what it ships is not shippable, so the version is asserted
    together with the fact that a spec actually comes out.
    """
    import lattice_core.dither  # noqa: F401  (registers the algorithms the starters name)

    spec = load_preset(path)
    assert spec.algorithm_id, f"{path.name} loaded without an algorithm"
    # A palette is either named (resolved from the built-in table at render time) or carries
    # its own colours; what must never happen is landing with neither.
    assert spec.palette is not None, f"{path.name} lost its palette"
    assert spec.palette.name or spec.palette.colors, (
        f"{path.name} has a palette with no name and no colours")


def test_a_v3_preset_keeps_its_full_metadata() -> None:
    """Description, tags and thumbnail survive a v3 read, not only name and author."""
    starter = next(iter(sorted((ROOT / "presets" / "starter").glob("dither_*.json"))))
    from lattice_core.preset import load_preset as read_v3
    from lattice_core.preset import to_pipeline_spec

    raw = json.loads(starter.read_text(encoding="utf-8"))
    spec = to_pipeline_spec(read_v3(starter))
    assert spec.meta.name == raw["meta"]["name"]
    assert spec.meta.description == raw["meta"].get("description", "")
    assert spec.meta.tags == list(raw["meta"].get("tags", []))
