"""Tests for the shared v3 preset format (card L4, contract sections 5 and 6)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from lattice_core import preset
from lattice_core.pipeline import PipelineSpec
from lattice_core.preset import (
    Preset,
    from_json,
    from_pipeline_spec,
    load_preset,
    save_preset,
    to_json,
    to_pipeline_spec,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "data" / "presets"


def _all_files() -> list[Path]:
    """Return the shipped and fixture presets in a stable order."""
    return sorted((ROOT / "presets").glob("*.json")) + sorted(FIXTURES.glob("*.json"))


def _fixture(name: str) -> str:
    """Read one fixture preset as UTF-8 text."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_shipped_presets_are_discovered() -> None:
    """The shipped preset directory is not empty, so the glob test cannot pass vacuously."""
    assert list((ROOT / "presets").glob("*.json"))
    assert _all_files()


@pytest.mark.parametrize("path", _all_files(), ids=lambda path: path.name)
def test_every_preset_loads_and_reports_its_version(path: Path) -> None:
    """Each shipped and fixture preset loads with the version written in its JSON."""
    text = path.read_text(encoding="utf-8")
    assert from_json(text).version == json.loads(text)["version"]


@pytest.mark.parametrize("name", ["dither_v3.json", "glyph_v3.json"])
def test_v3_round_trip_has_equal_presets(name: str) -> None:
    """Two v3 presets survive to_json/from_json with dataclass equality."""
    original = from_json(_fixture(name))
    assert from_json(to_json(original)) == original


def test_v3_round_trip_preserves_every_section_of_contract_six() -> None:
    """All eleven v3 sections, stages, masks and fonts survive a load/save unchanged."""
    saved = json.loads(to_json(from_json(_fixture("glyph_v3.json"))))
    for key in ("version", "app", "meta", "renderer", "palette", "pipeline", "effects",
                "masks", "fonts", "output", "seed"):
        assert key in saved
    assert [entry["stage"] for entry in saved["effects"]] == ["pre", "post"]
    assert saved["masks"]["glow_mask"] == {"kind": "v_flip"}
    assert saved["fonts"]["ramp"]["fallback"] == ["mono"]
    assert saved["output"] == {"scale": 2, "width": None, "dpi": 300}
    assert saved["seed"] == 7


def test_unknown_top_level_and_style_keys_survive_a_load_save() -> None:
    """A future top-level key and a future style option survive load/save unchanged."""
    original = from_json(_fixture("future_keys_v3.json"))
    saved = json.loads(to_json(original))
    assert saved["future"] == {"x": 1}
    assert saved["renderer"]["style"]["a_future_style_option"] == {"keep": True}
    assert from_json(to_json(original)) == original


def test_version_four_raises_value_error_naming_it() -> None:
    """An unsupported version is rejected with the offending number in the message."""
    with pytest.raises(ValueError, match=r"\b4\b"):
        from_json('{"version": 4}')


@pytest.mark.parametrize("value", [True, False, 3.7, "3", None])
def test_non_integer_version_is_rejected(value: object) -> None:
    """Bools, floats and strings never coerce into a supported version."""
    with pytest.raises(ValueError, match="version"):
        from_json(json.dumps({"version": value}))


@pytest.mark.parametrize("value", [True, 2.5, "7", None])
def test_non_integer_seed_is_rejected(value: object) -> None:
    """Bools, floats and strings are rejected for the seed key by name."""
    with pytest.raises(ValueError, match="seed"):
        from_json(json.dumps({"version": 3, "seed": value}))


@pytest.mark.parametrize(
    "section", ["meta", "renderer", "palette", "pipeline", "output", "masks", "fonts"],
)
def test_non_object_section_error_names_the_section(section: str) -> None:
    """A malformed section raises ValueError naming that section."""
    with pytest.raises(ValueError, match=section):
        from_json(json.dumps({"version": 3, section: []}))


def test_non_object_effect_entry_raises_value_error_naming_it() -> None:
    """A non-dict effect entry is a ValueError that names its index."""
    with pytest.raises(ValueError, match=r"effects\[0\]"):
        from_json(json.dumps({"version": 3, "effects": [1]}))


def test_glyph_preset_in_dither_context_keeps_its_registered_renderer() -> None:
    """Registry default keeps it; the host must pass available= for the card fallback."""
    text = _fixture("glyph_v3.json")
    loaded = from_json(text, app="dither")
    assert loaded.app == "glyph"
    assert loaded.renderer["name"] == "glyph_ramp"
    assert loaded.warnings == []
    assert from_json(text).renderer["name"] == "glyph_ramp"


def test_glyph_preset_in_dither_context_with_pixel_host_falls_back() -> None:
    """The accept item: available={'pixel'} gives pixel plus one warning naming glyph_ramp."""
    loaded = from_json(_fixture("glyph_v3.json"), app="dither", available={"pixel"})
    assert loaded.renderer["name"] == "pixel"
    assert len(loaded.warnings) == 1
    assert "glyph_ramp" in loaded.warnings[0]


def test_unregistered_renderer_falls_back_to_the_context_default() -> None:
    """A named renderer absent from the registry falls back with a warning (§6)."""
    loaded = from_json('{"version":3,"renderer":{"name":"future_renderer"}}', app="dither")
    assert loaded.renderer["name"] == "pixel"
    assert len(loaded.warnings) == 1
    assert "future_renderer" in loaded.warnings[0]


def test_available_context_can_keep_a_renderer_outside_the_app_table() -> None:
    """A host-provided availability set overrides the registry default."""
    loaded = from_json(_fixture("glyph_v3.json"), app="dither", available={"glyph_ramp"})
    assert loaded.renderer["name"] == "glyph_ramp"
    assert loaded.warnings == []


def test_unknown_app_with_registered_pixel_has_no_warning() -> None:
    """An unknown app naming a registered renderer needs no fallback (§6)."""
    loaded = from_json('{"version":3,"app":"widget","renderer":{"name":"pixel"}}')
    assert loaded.renderer["name"] == "pixel"
    assert loaded.warnings == []


def test_registered_non_table_renderer_is_kept() -> None:
    """Availability comes from list_renderers(), so braille survives load on any app."""
    loaded = from_json('{"version":3,"app":"widget","renderer":{"name":"braille"}}')
    assert loaded.renderer["name"] == "braille"
    assert loaded.warnings == []


@pytest.mark.parametrize(
    ("text", "expected", "app"),
    [
        ('{"version": 3, "app": "glyph"}', "glyph_ramp", None),
        ('{"version": 3, "app": "dither"}', "pixel", None),
        ('{"version": 3, "app": "widget"}', "pixel", None),
        ('{"version": 3}', "pixel", None),
        ('{"version": 3, "app": "glyph"}', "pixel", "dither"),
        ('{"version": 3, "renderer": {"style": {}}}', "pixel", "dither"),
    ],
)
def test_absent_renderer_uses_app_default_with_warning(
    text: str, expected: str, app: str | None,
) -> None:
    """A missing v3 renderer name becomes the context app default and records one warning."""
    loaded = from_json(text, app=app)
    assert loaded.renderer["name"] == expected
    assert len(loaded.warnings) == 1
    assert "absent" in loaded.warnings[0]


@pytest.mark.parametrize("app", [None, "glyph"])
def test_legacy_preset_without_renderer_is_pixel_without_warning(app: str | None) -> None:
    """v1/v2 without a renderer maps deterministically to dither/pixel, with no warning."""
    loaded = from_json(_fixture("legacy_v1.json"), app=app)
    assert loaded.renderer["name"] == "pixel"
    assert loaded.warnings == []


def test_available_renderer_in_context_has_no_warning() -> None:
    """A preset naming a registered renderer loads without fallback."""
    loaded = from_json(_fixture("dither_v3.json"), app="dither")
    assert loaded.renderer["name"] == "pixel"
    assert loaded.warnings == []


def test_to_json_is_byte_stable_sorted_and_indented() -> None:
    """Two serialisations are identical, with sorted keys, two-space indent and one LF."""
    text = to_json(from_json(_fixture("dither_v3.json")))
    assert text == to_json(from_json(_fixture("dither_v3.json")))
    data = json.loads(text)
    assert list(data) == sorted(data)
    assert text == json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_v1_preset_maps_to_dither_and_pixel() -> None:
    """A v1 preset reports version 1 and takes the dither app and pixel renderer."""
    loaded = from_json(_fixture("legacy_v1.json"))
    assert (loaded.version, loaded.app, loaded.renderer["name"]) == (1, "dither", "pixel")
    assert loaded.pipeline["algorithm"] == "floyd_steinberg"
    assert loaded.palette is not None
    assert loaded.palette["source"] == "integrated"
    assert loaded.effects == []


def test_v2_preset_keeps_stages_extraction_and_renderer_style() -> None:
    """A v2 preset maps both effect stages, extraction settings and L2b renderer fields."""
    loaded = from_json(_fixture("legacy_v2.json"))
    assert (loaded.version, loaded.app) == (2, "dither")
    assert loaded.renderer == {"name": "pixel", "style": {"scale": 2}}
    assert [entry["stage"] for entry in loaded.effects] == ["pre", "post"]
    assert loaded.palette is not None
    assert loaded.palette["extract"]["n_colors"] == 6
    assert loaded.palette["locked_colours"] == ["#ffffff"]
    assert loaded.meta["tags"] == ["old"]


def test_legacy_preset_serialises_as_current_v3() -> None:
    """Saving a loaded legacy preset writes the one v3 format used across the suite."""
    saved = json.loads(to_json(from_json(_fixture("legacy_v2.json"))))
    assert saved["version"] == 3
    assert saved["app"] == "dither"
    assert saved["pipeline"]["color_metric"] == "oklab"
    assert [entry["stage"] for entry in saved["effects"]] == ["pre", "post"]


def test_legacy_extra_cannot_overwrite_a_v3_section() -> None:
    """A legacy file carrying v3 keys must not corrupt the converted section on save."""
    text = json.dumps({
        "version": 1,
        "algorithm_id": "atkinson",
        "pipeline": {"algorithm": "evil"},
        "app": "glyph",
        "effects": ["evil"],
    })
    saved = json.loads(to_json(from_json(text)))
    assert saved["pipeline"]["algorithm"] == "atkinson"
    assert saved["app"] == "dither"
    assert saved["effects"] == []


def test_hand_built_extra_cannot_overwrite_a_typed_section() -> None:
    """An extra key colliding with a typed section never wins on serialisation."""
    saved = json.loads(to_json(Preset(extra={"version": 99, "seed": 12, "future": {"x": 1}})))
    assert saved["version"] == 3
    assert saved["seed"] == 0
    assert saved["future"] == {"x": 1}


def test_pipeline_spec_round_trip_carries_renderer_and_style() -> None:
    """PipelineSpec renderer and renderer_style survive the v3 bridge in both directions."""
    spec = PipelineSpec(
        algorithm_id="floyd_steinberg", renderer="glyph_ramp",
        renderer_style={"ramp": "@ .", "future": 1},
    )
    converted = from_pipeline_spec(spec)
    assert converted.renderer == {"name": "glyph_ramp", "style": {"ramp": "@ .", "future": 1}}
    rebuilt = to_pipeline_spec(converted)
    assert rebuilt.renderer == spec.renderer
    assert rebuilt.renderer_style == spec.renderer_style
    assert rebuilt.algorithm_id == spec.algorithm_id


def test_continuous_mode_nulls_survive_json_and_spec_round_trips() -> None:
    """null algorithm/palette stay null through v3 JSON and PipelineSpec (§5 S1)."""
    loaded = from_json('{"version":3,"app":"glitch","palette":null,"pipeline":{"algorithm":null}}')
    assert loaded.palette is None
    assert loaded.pipeline["algorithm"] is None
    saved = to_json(loaded)
    assert json.loads(saved)["palette"] is None
    assert json.loads(saved)["pipeline"]["algorithm"] is None
    assert from_json(saved).palette is None
    assert to_pipeline_spec(loaded).palette is None
    assert to_pipeline_spec(loaded).algorithm_id is None

    spec = PipelineSpec(algorithm_id=None, palette=None, renderer="pixel")
    converted = from_pipeline_spec(spec)
    assert converted.palette is None
    assert converted.pipeline["algorithm"] is None
    rebuilt = to_pipeline_spec(converted)
    assert rebuilt.algorithm_id is None
    assert rebuilt.palette is None


def test_legacy_explicit_nulls_keep_continuous_mode() -> None:
    """A v1 file with explicit null algorithm/palette does not re-enable quantisation."""
    loaded = from_json('{"version":1,"algorithm_id":null,"palette":null}')
    assert loaded.pipeline["algorithm"] is None
    assert loaded.palette is None
    assert to_pipeline_spec(loaded).algorithm_id is None
    assert to_pipeline_spec(loaded).palette is None


def test_to_pipeline_spec_maps_effects_and_palette() -> None:
    """The v3 bridge maps effects to their stages and the palette to a PaletteSpec."""
    spec = to_pipeline_spec(from_json(_fixture("glyph_v3.json")))
    assert [effect.effect_id for effect in spec.pre_effects] == ["scanlines"]
    assert [effect.effect_id for effect in spec.post_effects] == ["glow"]
    assert spec.palette is not None and spec.palette.source == "builtin"
    assert spec.pixel_size == 2 and spec.seed == 7


def test_missing_sections_take_defaults() -> None:
    """A minimal v3 preset takes the documented defaults and keeps unknown keys."""
    loaded = from_json('{"version": 3, "future": 1}')
    assert loaded.renderer == {"name": "pixel", "style": {}}
    assert loaded.pipeline["algorithm"] == "floyd_steinberg"
    assert loaded.output == {"scale": 1, "width": None, "dpi": None}
    assert loaded.extra == {"future": 1}


def test_save_and_load_preset_helpers(tmp_path: Path) -> None:
    """save_preset creates parents and load_preset reads back the same bytes."""
    original = from_json(_fixture("glyph_v3.json"))
    path = tmp_path / "nested" / "preset.json"
    save_preset(path, original)
    assert path.read_text(encoding="utf-8") == to_json(original)
    assert load_preset(path) == original


@pytest.mark.parametrize("text", ["{", "[]", "null"])
def test_malformed_preset_json_raises_value_error(text: str) -> None:
    """Malformed or non-object JSON is rejected with ValueError."""
    with pytest.raises(ValueError):
        from_json(text)


def test_default_preset_is_a_v3_preset() -> None:
    """A freshly built Preset is a complete v3 preset with no warnings."""
    made = Preset()
    assert made.version == 3 and made.app == "dither"
    assert made.warnings == [] and made.extra == {}
    assert from_json(to_json(made)) == made


def test_preset_module_imports_no_application_package() -> None:
    """The core preset module's real imports never name an application package."""
    tree = ast.parse(Path(preset.__file__).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert modules
    for name in ("lattice_dither", "lattice_glyph", "lattice_glitch"):
        assert not any(module == name or module.startswith(name + ".") for module in modules)
