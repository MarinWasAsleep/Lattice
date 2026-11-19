"""Preset serialisation: pipeline specs to and from JSON files."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from lattice.pipeline import (
    COLOR_METRICS,
    PRESET_VERSION,
    EffectInstance,
    PaletteSpec,
    PipelineSpec,
    PresetMeta,
)
from lattice.registry import get_algorithm, get_effect

APP_DIR_NAME = "LatticeDither"
PRESET_DIR_NAME = "presets"
PRESET_SUFFIX = ".json"
PALETTE_SOURCES = ("builtin", "extracted", "custom")
SUPPORTED_VERSIONS = (1, 2)


def shipped_preset_dir() -> Path:
    """Return the read-only shipped preset directory that sits next to the package."""
    return Path(__file__).resolve().parents[1] / PRESET_DIR_NAME


def user_preset_dir() -> Path:
    """Return the user preset directory under %APPDATA%, without creating it."""
    return _appdata() / APP_DIR_NAME / PRESET_DIR_NAME


def preset_search_dirs() -> tuple[Path, Path]:
    """Return the preset search order: the shipped directory first, then the user one."""
    return (shipped_preset_dir(), user_preset_dir())


def list_presets(directories: Sequence[Path] | None = None) -> list[Path]:
    """List the presets of the search directories, shipped first, a user file winning a tie."""
    dirs = tuple(directories) if directories is not None else preset_search_dirs()
    order: list[str] = []
    found: dict[str, Path] = {}
    for directory in dirs:
        for path in _scan(Path(directory)):
            if path.name not in found:
                order.append(path.name)
            found[path.name] = path
    return [found[name] for name in order]


def resolve_preset(name: str, directories: Sequence[Path] | None = None) -> Path | None:
    """Return the file a preset name resolves to, the user tier winning over the shipped one."""
    for path in list_presets(directories):
        if path.name == name:
            return path
    return None


def is_within(path: str | Path, directory: str | Path) -> bool:
    """Return True when path is directory itself or lies inside it."""
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
    except (OSError, ValueError):
        return False
    return True


def to_json(spec: PipelineSpec) -> str:
    """Serialise spec to indented JSON at the current preset version, keys in field order."""
    data = asdict(spec)
    data["version"] = PRESET_VERSION
    return json.dumps(data, indent=2)


def from_json(text: str) -> PipelineSpec:
    """Parse JSON into a PipelineSpec, validating the version, ids and metric."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid preset JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("preset JSON must be an object")
    spec = PipelineSpec()
    if "version" in data:
        spec.version = _as_int(data["version"], "version")
    if spec.version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported preset version: {spec.version}")
    if "meta" in data:
        spec.meta = _meta(data["meta"])
    if "pre_effects" in data:
        spec.pre_effects = _effect_list(data["pre_effects"], "pre_effects")
    if "post_effects" in data:
        spec.post_effects = _effect_list(data["post_effects"], "post_effects")
    if "brightness" in data:
        spec.brightness = _as_float(data["brightness"], "brightness")
    if "contrast" in data:
        spec.contrast = _as_float(data["contrast"], "contrast")
    if "gamma" in data:
        spec.gamma = _as_float(data["gamma"], "gamma")
    if "saturation" in data:
        spec.saturation = _as_float(data["saturation"], "saturation")
    if "pre_blur" in data:
        spec.pre_blur = _as_float(data["pre_blur"], "pre_blur")
    if "auto_levels" in data:
        spec.auto_levels = bool(data["auto_levels"])
    if "color_metric" in data:
        spec.color_metric = _color_metric(data["color_metric"])
    if "pixel_size" in data:
        spec.pixel_size = _as_int(data["pixel_size"], "pixel_size")
    if "algorithm_id" in data:
        spec.algorithm_id = _algorithm_id(data["algorithm_id"])
    if "algorithm_params" in data:
        spec.algorithm_params = dict(_as_dict(data["algorithm_params"], "algorithm_params"))
    if "palette" in data:
        spec.palette = _palette(data["palette"])
    if "seed" in data:
        spec.seed = _as_int(data["seed"], "seed")
    return spec


def save_preset(path: str | Path, spec: PipelineSpec) -> None:
    """Write spec as UTF-8 JSON to path, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(spec), encoding="utf-8")


def load_preset(path: str | Path) -> PipelineSpec:
    """Read a preset file and parse it into a PipelineSpec, whatever its version.

    Two readers coexist. ``from_json`` below owns versions 1 and 2 and is kept exactly as it
    was: the witness presets are pinned to v1 and to the v2 defaults, and their baselines were
    rendered through those defaults. ``lattice.preset`` owns version 3, the format every
    Lattice app ships. The shipped starters are v3, so a reader that only knew v1 and v2 could
    not open the very files it ships — that is what this dispatch fixes.
    """
    text = Path(path).read_text(encoding="utf-8")
    version = _peek_version(text)
    if version >= PRESET_VERSION:
        from lattice.preset import load_preset as read_v3
        from lattice.preset import to_pipeline_spec

        return to_pipeline_spec(read_v3(Path(path)))
    return from_json(text)


def _peek_version(text: str) -> int:
    """Return the preset version of text without parsing the whole document."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid preset JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("preset JSON must be an object")
    return _as_int(data.get("version", 1), "version")


def _appdata() -> Path:
    """Return %APPDATA%, falling back to the default Windows roaming location."""
    value = os.environ.get("APPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Roaming"


def _scan(directory: Path) -> list[Path]:
    """Return the preset files of one directory sorted by name, empty when unreadable."""
    try:
        return sorted(p for p in directory.glob(f"*{PRESET_SUFFIX}") if p.is_file())
    except OSError:
        return []


def _as_int(value: object, key: str) -> int:
    """Coerce value to int or raise ValueError naming the offending key."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"preset key {key!r} must be an integer") from exc


def _as_float(value: object, key: str) -> float:
    """Coerce value to float or raise ValueError naming the offending key."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"preset key {key!r} must be a number") from exc


def _as_dict(value: object, key: str) -> dict:
    """Return value as a dict or raise ValueError naming the offending key."""
    if not isinstance(value, dict):
        raise ValueError(f"preset key {key!r} must be an object")
    return value


def _as_list(value: object, key: str) -> list:
    """Return value as a list or raise ValueError naming the offending key."""
    if not isinstance(value, list):
        raise ValueError(f"preset key {key!r} must be a list")
    return value


def _algorithm_id(value: object) -> str:
    """Validate an algorithm id against the registry and return it."""
    if not isinstance(value, str):
        raise ValueError(f"algorithm_id must be a string, got {value!r}")
    try:
        get_algorithm(value)
    except KeyError as exc:
        raise ValueError(f"unknown algorithm id: {value!r}") from exc
    return value


def _effect_list(value: object, key: str) -> list[EffectInstance]:
    """Parse a list of effect entries, validating every effect id."""
    return [_effect_instance(entry, key) for entry in _as_list(value, key)]


def _effect_instance(entry: object, key: str) -> EffectInstance:
    """Parse one effect entry into an EffectInstance, validating its id."""
    data = _as_dict(entry, key)
    effect_id = data.get("effect_id")
    if not isinstance(effect_id, str):
        raise ValueError(f"preset key {key!r}: every effect entry needs a string 'effect_id'")
    try:
        get_effect(effect_id)
    except KeyError as exc:
        raise ValueError(f"unknown effect id: {effect_id!r}") from exc
    params = dict(_as_dict(data.get("params", {}), "params"))
    enabled = bool(data.get("enabled", True))
    return EffectInstance(effect_id=effect_id, params=params, enabled=enabled)


def _color_metric(value: object) -> str:
    """Validate a colour metric name against the contract list and return it."""
    if value not in COLOR_METRICS:
        raise ValueError(f"unknown color metric: {value!r}")
    return str(value)


def _meta(value: object) -> PresetMeta:
    """Parse the meta object of a preset, keeping the defaults for absent keys."""
    data = _as_dict(value, "meta")
    meta = PresetMeta()
    if "name" in data:
        meta.name = str(data["name"])
    if "author" in data:
        meta.author = str(data["author"])
    if "description" in data:
        meta.description = str(data["description"])
    if "tags" in data:
        meta.tags = [str(entry) for entry in _as_list(data["tags"], "tags")]
    if "thumbnail" in data:
        meta.thumbnail = str(data["thumbnail"])
    return meta


def _palette(value: object) -> PaletteSpec:
    """Parse the palette object of a preset, validating the source literal."""
    data = _as_dict(value, "palette")
    spec = PaletteSpec()
    if "source" in data:
        source = data["source"]
        if source not in PALETTE_SOURCES:
            raise ValueError(f"unknown palette source: {source!r}")
        spec.source = source
    if "name" in data:
        spec.name = str(data["name"])
    if "colors" in data:
        spec.colors = [str(entry) for entry in _as_list(data["colors"], "colors")]
    if "extract_k" in data:
        spec.extract_k = _as_int(data["extract_k"], "extract_k")
    if "extract_method" in data:
        spec.extract_method = str(data["extract_method"])
    if "locked" in data:
        spec.locked = [str(entry) for entry in _as_list(data["locked"], "locked")]
    if "order" in data:
        spec.order = [_as_int(entry, "order") for entry in _as_list(data["order"], "order")]
    return spec
