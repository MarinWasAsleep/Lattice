"""Preset format v3: one portable, diffable preset format shared by every Lattice app."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, PresetMeta
from lattice_core.renderers import list_renderers

PRESET_VERSION = 3
SUPPORTED_VERSIONS = (1, 2, 3)
DEFAULT_APP = "dither"
# Minimal per-app default names only (§6 fallback). Availability comes from the
# renderer registry at call time; no per-app renderer table is duplicated here.
APP_DEFAULT_RENDERER: dict[str, str] = {
    "dither": "pixel",
    "glyph": "glyph_ramp",
    "glitch": "pixel",
}
_LEGACY_TOP = frozenset({
    "version", "pre_effects", "post_effects", "brightness", "contrast", "gamma",
    "saturation", "pre_blur", "auto_levels", "color_metric", "pixel_size",
    "algorithm_id", "algorithm_params", "palette", "seed", "meta", "renderer",
    "renderer_style",
})
_V3_TOP = frozenset({
    "version", "app", "meta", "renderer", "palette", "pipeline", "effects", "masks",
    "fonts", "output", "seed",
})
_LEGACY_SOURCE = {"builtin": "integrated", "extracted": "image", "custom": "imported"}
_V3_SOURCE: dict[str, Literal["builtin", "extracted", "custom"]] = {
    "integrated": "builtin",
    "image": "extracted",
    "imported": "custom",
}
# Partial bridge by design: PipelineSpec has no max_side, effect mask, masks,
# fonts or output field (§5/§6); those remain in the Preset and round-trip there.
_PIPELINE_KEYS = ("color_metric", "pixel_size", "brightness", "contrast", "gamma",
                  "saturation", "pre_blur", "auto_levels", "fit_palette")


def _default_meta() -> dict[str, Any]:
    """Return the v3 meta defaults, including the creation date field."""
    return {"name": "", "author": "", "created": ""}


def _default_renderer(app: str = DEFAULT_APP) -> dict[str, Any]:
    """Return the app default renderer name and its free-form style object."""
    return {"name": APP_DEFAULT_RENDERER.get(app, "pixel"), "style": {}}


def _default_palette() -> dict[str, Any]:
    """Return the complete v3 palette object, including extraction settings."""
    return {
        "colors": ["#000000", "#ffffff"],
        "locked": False,
        "order": None,
        "source": "integrated",
        "extract": {"from": "image", "n_colors": 16, "rows": None},
    }


def _default_pipeline() -> dict[str, Any]:
    """Return the v3 pipeline defaults from contract section 6."""
    return {
        "algorithm": "floyd_steinberg",
        "params": {},
        "color_metric": "srgb",
        "pixel_size": 1,
        "max_side": None,
        "brightness": 0.0,
        "contrast": 0.0,
        "gamma": 1.0,
        "saturation": 0.0,
        "pre_blur": 0.0,
        "auto_levels": False,
        "fit_palette": False,
    }


def _default_output() -> dict[str, Any]:
    """Return the default output size settings."""
    return {"scale": 1, "width": None, "dpi": None}


@dataclass
class Preset:
    """A v3 preset: typed sections, preserved unknown keys and load warnings."""

    version: int = PRESET_VERSION
    app: str = DEFAULT_APP
    meta: dict[str, Any] = field(default_factory=_default_meta)
    renderer: dict[str, Any] = field(default_factory=_default_renderer)
    palette: dict[str, Any] | None = field(default_factory=_default_palette)
    pipeline: dict[str, Any] = field(default_factory=_default_pipeline)
    effects: list[dict[str, Any]] = field(default_factory=list)
    masks: dict[str, Any] = field(default_factory=dict)
    fonts: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=_default_output)
    seed: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Point an untouched default renderer at a non-dither app's default."""
        if self.app != DEFAULT_APP and self.renderer == _default_renderer():
            self.renderer = _default_renderer(self.app)


def to_json(preset: Preset) -> str:
    """Serialise preset as sorted, two-space-indented v3 JSON with one trailing newline."""
    data = _preset_dict(preset)
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def from_json(
    text: str, *, app: str | None = None, available: Iterable[str] | None = None,
) -> Preset:
    """Parse a v1, v2 or v3 preset; an explicit app context resolves absent renderers."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid preset JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("preset JSON must be an object")
    version = _version(data)
    if app is not None:
        context = app
    elif version == PRESET_VERSION:
        context = str(data.get("app", DEFAULT_APP))
    else:
        context = DEFAULT_APP
    if version == PRESET_VERSION:
        return _from_v3(data, context, available)
    return _from_legacy(data, version, context, available)


def save_preset(path: str | Path, preset: Preset) -> None:
    """Write preset as UTF-8 v3 JSON, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(preset), encoding="utf-8")


def load_preset(
    path: str | Path, *, app: str | None = None, available: Iterable[str] | None = None,
) -> Preset:
    """Read a JSON preset file and parse it with an optional app context."""
    return from_json(Path(path).read_text(encoding="utf-8"), app=app, available=available)


def to_pipeline_spec(preset: Preset) -> PipelineSpec:
    """Return PipelineSpec carrying renderer/style and continuous-mode nulls (§5 S1)."""
    source = preset.pipeline
    spec = PipelineSpec()
    spec.algorithm_id = source.get("algorithm")
    spec.algorithm_params = dict(_as_dict(source.get("params", {}), "params"))
    for key in _PIPELINE_KEYS:
        if key in source:
            setattr(spec, key, source[key])
    for entry in preset.effects:
        effect = _effect_instance(entry)
        (spec.pre_effects if entry.get("stage", "post") == "pre" else spec.post_effects).append(
            effect)
    spec.palette = _spec_palette(preset.palette)
    spec.seed = preset.seed
    # The whole display metadata travels: a preset read through this path and shown in a
    # browser must keep its description, tags and thumbnail, not just name and author.
    spec.meta = PresetMeta(
        name=str(preset.meta.get("name", "")),
        author=str(preset.meta.get("author", "")),
        description=str(preset.meta.get("description", "")),
        tags=[str(tag) for tag in _as_list(preset.meta.get("tags", []), "tags")],
        thumbnail=str(preset.meta.get("thumbnail", "")),
    )
    spec.renderer = str(preset.renderer.get("name", "pixel"))
    spec.renderer_style = dict(_as_dict(preset.renderer.get("style", {}), "style"))
    return spec


def from_pipeline_spec(spec: PipelineSpec) -> Preset:
    """Build a v3 preset from a PipelineSpec, keeping renderer and renderer_style."""
    # The spec itself declares the renderer available, so no context fallback applies.
    return _from_legacy(
        asdict(spec), int(spec.version), DEFAULT_APP, frozenset({str(spec.renderer)}),
    )


def _preset_dict(preset: Preset) -> dict[str, Any]:
    """Return the JSON object of preset: typed v3 sections win over preserved keys."""
    data: dict[str, Any] = dict(preset.extra)
    data.update({
        "version": PRESET_VERSION,
        "app": preset.app,
        "meta": dict(preset.meta),
        "renderer": dict(preset.renderer),
        "palette": dict(preset.palette) if preset.palette is not None else None,
        "pipeline": dict(preset.pipeline),
        "effects": [dict(entry) for entry in preset.effects],
        "masks": dict(preset.masks),
        "fonts": dict(preset.fonts),
        "output": dict(preset.output),
        "seed": preset.seed,
    })
    return data


def _version(data: dict[str, Any]) -> int:
    """Return the parsed version, rejecting bools, floats and strings by name."""
    value = data.get("version", PRESET_VERSION)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"unsupported preset version: {value!r}")
    if value not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported preset version: {value}")
    return value


def _section(value: object, defaults: dict[str, Any], name: str) -> dict[str, Any]:
    """Merge one named JSON section over fresh defaults, keeping keys the defaults lack."""
    if value is None:
        return dict(defaults)
    if not isinstance(value, dict):
        raise ValueError(f"preset section {name!r} must be an object")
    merged = dict(defaults)
    merged.update(value)
    return merged


def _as_int(value: object, key: str) -> int:
    """Return an int or raise ValueError naming the key; bools and floats are rejected."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"preset key {key!r} must be an integer")
    return value


def _as_list(value: object, key: str) -> list:
    """Return value as a list or raise ValueError naming the offending key."""
    if not isinstance(value, list):
        raise ValueError(f"preset key {key!r} must be a list")
    return value


def _as_dict(value: object, key: str) -> dict:
    """Return value as a dict or raise ValueError naming the offending key."""
    if not isinstance(value, dict):
        raise ValueError(f"preset key {key!r} must be an object")
    return value


def _from_v3(
    data: dict[str, Any], context: str, available: Iterable[str] | None,
) -> Preset:
    """Build a Preset from v3 JSON, merging defaults and preserving unknown keys."""
    preset = Preset()
    preset.app = str(data.get("app", DEFAULT_APP))
    renderer = data.get("renderer")
    named = isinstance(renderer, dict) and "name" in renderer
    preset.renderer = _section(renderer, _default_renderer(context), "renderer")
    preset.meta = _section(data.get("meta"), _default_meta(), "meta")
    preset.palette = (
        None if "palette" in data and data["palette"] is None
        else _section(data.get("palette"), _default_palette(), "palette")
    )
    preset.pipeline = _section(data.get("pipeline"), _default_pipeline(), "pipeline")
    preset.output = _section(data.get("output"), _default_output(), "output")
    preset.effects = [
        dict(_as_dict(entry, f"effects[{index}]"))
        for index, entry in enumerate(_as_list(data.get("effects", []), "effects"))
    ]
    preset.masks = _section(data.get("masks"), {}, "masks")
    preset.fonts = _section(data.get("fonts"), {}, "fonts")
    preset.seed = _as_int(data.get("seed", 0), "seed")
    preset.extra = {key: value for key, value in data.items() if key not in _V3_TOP}
    _apply_renderer(preset, context, named, available)
    return preset


def _from_legacy(
    data: dict[str, Any], version: int, context: str = DEFAULT_APP,
    available: Iterable[str] | None = None,
) -> Preset:
    """Map a v1/v2 preset onto v3; drop colliding v3 keys so the typed v2 wins on save."""
    preset = Preset(version=version, app=DEFAULT_APP)
    preset.meta = _section(data.get("meta"), _default_meta(), "meta")
    renderer = data.get("renderer")
    named = isinstance(renderer, str) or (isinstance(renderer, dict) and "name" in renderer)
    if isinstance(renderer, str):
        preset.renderer["name"] = renderer
    elif isinstance(renderer, dict):
        preset.renderer.update(renderer)
    if "renderer_style" in data:
        preset.renderer["style"] = dict(_as_dict(data["renderer_style"], "renderer_style"))
    preset.palette = (
        None if "palette" in data and data["palette"] is None
        else _legacy_palette(data.get("palette"))
    )
    preset.pipeline = _legacy_pipeline(data)
    preset.effects = (_legacy_effects(data.get("pre_effects"), "pre")
                      + _legacy_effects(data.get("post_effects"), "post"))
    preset.seed = _as_int(data.get("seed", 0), "seed")
    preset.extra = {
        key: value for key, value in data.items()
        if key not in _LEGACY_TOP and key not in _V3_TOP
    }
    # §6: v1/v2 map deterministically to pixel; absence is normal, not a fallback.
    _apply_renderer(preset, context, named, available, default_name="pixel", warn_absent=False)
    return preset


def _legacy_palette(value: object) -> dict[str, Any]:
    """Map a v2 PaletteSpec onto the v3 palette object, keeping v2-only settings."""
    palette = _default_palette()
    if value is None:
        return palette
    source = _as_dict(value, "palette")
    palette["colors"] = [str(entry) for entry in _as_list(source.get("colors", []), "colors")]
    palette["source"] = _LEGACY_SOURCE.get(str(source.get("source", "builtin")), "imported")
    palette["extract"] = {
        "from": "image",
        "n_colors": _as_int(source.get("extract_k", 16), "extract_k"),
        "rows": None,
    }
    # v2 `locked` is a list of colours, v3 `locked` is a bool: keep the list
    # under the documented `locked_colours` key instead of coercing it.
    for key in ("name", "extract_method", "locked", "order"):
        if key in source:
            palette[key if key != "locked" else "locked_colours"] = source[key]
    return palette


def _legacy_pipeline(data: dict[str, Any]) -> dict[str, Any]:
    """Map the flat v2 pipeline fields onto the v3 pipeline object."""
    pipeline = _default_pipeline()
    if "algorithm_id" in data:
        pipeline["algorithm"] = data["algorithm_id"]
    pipeline["params"] = dict(_as_dict(data.get("algorithm_params", {}), "algorithm_params"))
    for key in _PIPELINE_KEYS:
        if key in data:
            pipeline[key] = data[key]
    return pipeline


def _legacy_effects(value: object, stage: str) -> list[dict[str, Any]]:
    """Map a v2 effect list onto v3 entries tagged with their stage."""
    entries: list[dict[str, Any]] = []
    for item in _as_list(value if value is not None else [], f"{stage}_effects"):
        source = _as_dict(item, "effect")
        entry = dict(source)
        entry["name"] = source.get("effect_id", "")
        entry.pop("effect_id", None)
        entry.setdefault("params", {})
        entry.setdefault("enabled", True)
        entry.setdefault("mask", None)
        entry["stage"] = stage
        entries.append(entry)
    return entries


def _apply_renderer(
    preset: Preset, app: str, named: bool, available: Iterable[str] | None,
    *, default_name: str | None = None, warn_absent: bool = True,
) -> None:
    """Fall back on absence or unavailability; availability comes from the registry."""
    table = frozenset(list_renderers()) if available is None else frozenset(available)
    default = default_name or APP_DEFAULT_RENDERER.get(app, "pixel")
    name = str(preset.renderer.get("name", ""))
    if not named:
        preset.renderer["name"] = default
        if warn_absent:
            preset.warnings.append(f"renderer absent in app {app!r}; using {default!r}")
        return
    if name in table:
        return
    preset.renderer["name"] = default
    preset.warnings.append(f"renderer {name!r} unavailable in app {app!r}; using {default!r}")


def _effect_instance(entry: dict[str, Any]) -> EffectInstance:
    """Build an EffectInstance from one v3 effect entry."""
    return EffectInstance(
        effect_id=str(entry.get("name", "")),
        params=dict(_as_dict(entry.get("params", {}), "params")),
        enabled=bool(entry.get("enabled", True)),
    )


def _spec_palette(palette: dict[str, Any] | None) -> PaletteSpec | None:
    """Build a PaletteSpec from a v3 palette object; null stays null (§5 S1)."""
    if palette is None:
        return None
    spec = PaletteSpec()
    spec.source = _V3_SOURCE.get(str(palette.get("source", "integrated")), "custom")
    spec.colors = [str(entry) for entry in palette.get("colors", [])]
    if palette.get("name") is not None:
        spec.name = str(palette["name"])
    extract = _as_dict(palette.get("extract", {}), "extract")
    if extract.get("n_colors") is not None:
        spec.extract_k = _as_int(extract["n_colors"], "n_colors")
    if palette.get("extract_method") is not None:
        spec.extract_method = str(palette["extract_method"])
    if palette.get("locked_colours") is not None:
        spec.locked = [str(entry) for entry in palette["locked_colours"]]
    if palette.get("order") is not None:
        spec.order = [_as_int(entry, "order") for entry in palette["order"]]
    return spec
