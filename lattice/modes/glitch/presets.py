"""Presets of Lattice Glitch: the shipped tier, the user tier, and the app default spec.

Presets are v3 documents (``lattice.preset``) read in the ``glitch`` app context.
Glitch is a continuous-mode application: the default spec nulls algorithm and palette
(§5 S1) and the effect stack lives in the preset ``effects`` entries, mask assignments
included. The user tier lives under this application's own app-data directory (§7).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import lattice.effects  # noqa: F401  (registers every effect validate() checks)
from lattice import mask
from lattice.modes.glitch.stack import EffectStack
from lattice.pipeline import PipelineSpec
from lattice.preset import (
    Preset,
    from_pipeline_spec,
    load_preset,
    to_json,
    to_pipeline_spec,
)
from lattice.presets import list_presets
from lattice.registry import get_effect

APP_CONTEXT = "glitch"
APP_DIR_NAME = "LatticeGlitch"
PRESET_DIR_NAME = "presets"
SHIPPED_PRESET_DIR = Path(__file__).resolve().parent / PRESET_DIR_NAME
CONTINUOUS_ERROR = "glitch renders continuous images: algorithm and palette must both be null"


@dataclass(frozen=True)
class PresetEntry:
    """One preset file found in a search directory."""

    name: str
    path: Path
    read_only: bool


@dataclass(frozen=True)
class PresetReport:
    """The outcome of validating one preset: its entry, its problems and its warnings."""

    name: str
    ok: bool
    errors: list[str]
    warnings: list[str]
    renderer: str = ""


def app_data_dir() -> Path:
    """Return this application's data directory: %LOCALAPPDATA% on Windows, XDG elsewhere."""
    if os.name == "nt":
        value = os.environ.get("LOCALAPPDATA")
        root = Path(value) if value else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        value = os.environ.get("XDG_DATA_HOME")
        root = Path(value) if value else Path.home() / ".local" / "share"
    return root / APP_DIR_NAME


def user_preset_dir() -> Path:
    """Return the user preset directory of this app, without creating it."""
    return app_data_dir() / PRESET_DIR_NAME


def search_dirs() -> tuple[Path, Path]:
    """Return the preset search order: the shipped tier first, the user tier second."""
    return (SHIPPED_PRESET_DIR, user_preset_dir())


def available(directories: Sequence[Path] | None = None) -> list[PresetEntry]:
    """Return every preset of the search directories, a user file winning a name tie."""
    dirs = tuple(directories) if directories is not None else search_dirs()
    return [PresetEntry(path.name, path, _is_read_only(path, dirs))
            for path in list_presets(dirs)]


def _is_read_only(path: Path, dirs: tuple[Path, ...]) -> bool:
    """Return True when path belongs to every directory but the last (the user tier)."""
    try:
        resolved = path.resolve()
    except OSError:
        return True
    return any(resolved.is_relative_to(directory.resolve()) for directory in dirs[:-1])


def default_spec() -> PipelineSpec:
    """Return the pipeline of a fresh Glitch document: continuous mode, no effect yet."""
    return PipelineSpec(pixel_size=1, renderer="pixel", algorithm_id=None, palette=None)


def _mask_section(masks: Mapping[str, object], mask_dir: Path) -> dict:
    """Return the v3 masks section: embed small planes, write the large ones to mask_dir."""
    section: dict = {}
    for mask_id, plane in masks.items():
        try:
            ref = mask.MaskRef.from_mask(plane, mask_id)
        except ValueError:
            target = mask.export_png(plane, mask_dir / f"{mask_id}.png")
            ref = mask.MaskRef.from_path(target, mask_id)
        section[mask_id] = ref.to_dict()
    return section


def to_preset(spec: PipelineSpec, *, stack: EffectStack | None = None,
              masks: Mapping[str, object] | None = None, name: str = "",
              mask_dir: Path | None = None,
              locked_streams: Mapping[int, int] | None = None) -> Preset:
    """Return the v3 preset of spec, tagged ``app: glitch``, stack masks attached.

    Locked slots carry their frozen stream as ``seed`` so a reload renders the same
    bytes (G9); the core keeps locks session-only, this is the shell's format (E1).
    """
    preset = from_pipeline_spec(spec)
    preset.app = APP_CONTEXT
    if name:
        preset.meta["name"] = name
    if stack is not None:
        pre = [entry for entry in preset.effects if entry.get("stage") == "pre"]
        entries = stack.to_entries()
        for position, stream in (locked_streams or {}).items():
            if 0 <= position < len(entries):
                entries[position]["seed"] = int(stream)
        preset.effects = pre + entries
    if masks:
        directory = mask_dir if mask_dir is not None else user_preset_dir() / "masks"
        preset.masks = _mask_section(masks, directory)
    return preset


def locked_streams_of(preset: Preset) -> dict[int, int]:
    """Return the frozen stream seed of each post slot whose entry carries one."""
    streams: dict[int, int] = {}
    position = 0
    for entry in preset.effects:
        if entry.get("stage", "post") == "pre":
            continue
        if "seed" in entry:
            streams[position] = int(entry["seed"])
        position += 1
    return streams


def spec_of(preset: Preset) -> PipelineSpec:
    """Return the PipelineSpec of a parsed preset, its renderer and style included."""
    return to_pipeline_spec(preset)


def stack_of(preset: Preset) -> EffectStack:
    """Return the effect stack a parsed preset carries, mask assignments included."""
    return EffectStack.from_entries(preset.effects)


def masks_of(preset: Preset) -> dict:
    """Return the resolved mask planes of a parsed preset, keyed by section id."""
    return mask.resolve_masks(preset.masks)


def read_preset(path: str | Path) -> Preset:
    """Read and parse one preset in this application's context."""
    return load_preset(path, app=APP_CONTEXT)


def describe(preset: Preset) -> dict:
    """Return a JSON-serialisable summary of a preset, without rendering it."""
    return {
        "name": preset.meta.get("name", ""),
        "app": preset.app,
        "renderer": preset.renderer.get("name", ""),
        "seed": preset.seed,
        "effects": [
            {"name": entry.get("name", ""), "params": dict(entry.get("params", {})),
             "enabled": bool(entry.get("enabled", True)), "mask": entry.get("mask")}
            for entry in preset.effects
        ],
        "masks": sorted(preset.masks),
        "pipeline": {key: preset.pipeline.get(key) for key in
                     ("brightness", "contrast", "gamma", "saturation", "pre_blur",
                      "auto_levels", "algorithm")},
    }


def _check_effects(preset: Preset, errors: list[str]) -> None:
    """Report unknown effect ids and mask ids the masks section does not carry."""
    known = set(preset.masks)
    for entry in preset.effects:
        name = str(entry.get("name", ""))
        try:
            get_effect(name)
        except KeyError:
            errors.append(f"effect {name!r} is not registered in this build")
        mask_id = entry.get("mask")
        if mask_id is not None and str(mask_id) not in known:
            errors.append(f"effect {name!r} names mask {mask_id!r}, absent from the masks section")


def validate(path: str | Path) -> PresetReport:
    """Parse one preset and report every problem instead of raising it."""
    name = Path(path).name
    try:
        preset = read_preset(path)
        spec = spec_of(preset)
    except (OSError, ValueError, KeyError) as exc:
        return PresetReport(name, False, [str(exc)], [])
    errors: list[str] = []
    if spec.algorithm_id is not None or spec.palette is not None:
        errors.append(CONTINUOUS_ERROR)
    _check_effects(preset, errors)
    try:
        masks_of(preset)
    except (OSError, ValueError) as exc:
        errors.append(f"cannot resolve the masks: {exc}")
    warnings = [str(entry) for entry in preset.warnings]
    return PresetReport(name, not errors, errors, warnings, spec.renderer)


def validate_all(directories: Sequence[Path] | None = None) -> list[PresetReport]:
    """Validate every preset of the search directories, shipped tier first."""
    return [validate(entry.path) for entry in available(directories)]


def save_preset(path: str | Path, preset: Preset) -> Path:
    """Write preset as UTF-8 v3 JSON, creating the parent directories, and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(preset), encoding="utf-8")
    return target


def save_spec(path: str | Path, spec: PipelineSpec, *, stack: EffectStack | None = None,
              masks: Mapping[str, object] | None = None, name: str = "",
              locked_streams: Mapping[int, int] | None = None) -> Path:
    """Write the v3 preset of spec to path, large masks landing beside the preset."""
    preset = to_preset(spec, stack=stack, masks=masks, name=name,
                       mask_dir=Path(path).parent, locked_streams=locked_streams)
    return save_preset(path, preset)


__all__ = [
    "APP_CONTEXT",
    "APP_DIR_NAME",
    "CONTINUOUS_ERROR",
    "PresetEntry",
    "PresetReport",
    "SHIPPED_PRESET_DIR",
    "app_data_dir",
    "available",
    "default_spec",
    "describe",
    "locked_streams_of",
    "masks_of",
    "read_preset",
    "save_preset",
    "save_spec",
    "search_dirs",
    "spec_of",
    "stack_of",
    "to_preset",
    "user_preset_dir",
    "validate",
    "validate_all",
]
