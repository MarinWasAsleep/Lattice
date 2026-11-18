"""Presets of Lattice Glyph: the shipped tier, the user tier, and the app default spec.

Presets are v3 documents (``lattice_core.preset``) read in the ``glyph`` app context, so a
preset that names no renderer falls back on ``glyph_ramp`` and a preset naming a renderer
this build does not ship is reported as a warning instead of raising. The user tier lives
under the platform app-data directory of this application, never in the Dither one (§7).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lattice_core.pipeline import PaletteSpec, PipelineSpec
from lattice_core.preset import (
    Preset,
    from_pipeline_spec,
    load_preset,
    to_json,
    to_pipeline_spec,
)
from lattice_core.preset import from_json as preset_from_json
from lattice_core.presets import list_presets
from lattice_core.renderers import list_renderers

APP_CONTEXT = "glyph"
APP_DIR_NAME = "LatticeGlyph"
PRESET_DIR_NAME = "presets"
SHIPPED_PRESET_DIR = Path(__file__).resolve().parent / PRESET_DIR_NAME
DEFAULT_RENDERER = "glyph_ramp"
DEFAULT_PIXEL_SIZE = 8
DEFAULT_PALETTE = "gameboy"
DEFAULT_RAMP = "@%#*+=-:. "


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
    entries: list[PresetEntry] = []
    for path in list_presets(dirs):
        entries.append(PresetEntry(path.name, path, _is_read_only(path, dirs)))
    return entries


def _is_read_only(path: Path, dirs: tuple[Path, ...]) -> bool:
    """Return True when path belongs to every directory but the last (the user tier)."""
    try:
        resolved = path.resolve()
    except OSError:
        return True
    return any(resolved.is_relative_to(directory.resolve()) for directory in dirs[:-1])


def default_spec() -> PipelineSpec:
    """Return the pipeline of a fresh Glyph document: glyph ramp, gameboy, 8 px cells."""
    spec = PipelineSpec(pixel_size=DEFAULT_PIXEL_SIZE, renderer=DEFAULT_RENDERER)
    spec.renderer_style = {"ramp": DEFAULT_RAMP}
    spec.palette = PaletteSpec(source="builtin", name=DEFAULT_PALETTE)
    return spec


def default_preset() -> Preset:
    """Return the v3 preset of a fresh document, tagged with this application's context."""
    return to_preset(default_spec())


def to_preset(spec: PipelineSpec, name: str = "") -> Preset:
    """Return the v3 preset of spec, its renderer kept, tagged ``app: glyph``."""
    preset = from_pipeline_spec(spec)
    preset.app = APP_CONTEXT
    if name:
        preset.meta["name"] = name
    return preset


def spec_of(preset: Preset) -> PipelineSpec:
    """Return the PipelineSpec of a parsed preset, its renderer and style included."""
    return to_pipeline_spec(preset)


def read_preset(path: str | Path) -> Preset:
    """Read and parse one preset in this application's context."""
    return load_preset(path, app=APP_CONTEXT)


def read_text(text: str) -> Preset:
    """Parse one preset document in this application's context."""
    return preset_from_json(text, app=APP_CONTEXT)


def spec_from_text(text: str) -> PipelineSpec:
    """Parse a preset document straight into its pipeline spec."""
    return spec_of(read_text(text))


def describe(preset: Preset) -> dict:
    """Return a JSON-serialisable summary of a preset, without rendering it."""
    style = dict(preset.renderer.get("style", {}))
    palette = preset.palette or {}
    pipeline = preset.pipeline
    return {
        "name": preset.meta.get("name", ""),
        "app": preset.app,
        "renderer": preset.renderer.get("name", ""),
        "options": style,
        "palette": {
            "source": palette.get("source", ""),
            "name": palette.get("name", ""),
            "colors": list(palette.get("colors", [])),
            "n_colors": (palette.get("extract") or {}).get("n_colors"),
        },
        "algorithm": pipeline.get("algorithm"),
        "pixel_size": pipeline.get("pixel_size"),
        "color_metric": pipeline.get("color_metric"),
        "seed": preset.seed,
        "effects": [entry.get("name", "") for entry in preset.effects],
    }


def validate(path: str | Path) -> PresetReport:
    """Parse one preset and report every problem instead of raising it."""
    name = Path(path).name
    errors: list[str] = []
    warnings: list[str] = []
    renderer = ""
    try:
        preset = read_preset(path)
        spec = spec_of(preset)
    except (OSError, ValueError, KeyError) as exc:
        return PresetReport(name, False, [str(exc)], [])
    renderer = spec.renderer
    if renderer not in list_renderers():
        errors.append(f"renderer {renderer!r} is not registered in this build")
    if spec.algorithm_id is None and spec.palette is not None:
        errors.append("continuous mode needs both algorithm and palette null")
    if spec.palette is None and spec.algorithm_id is not None:
        errors.append("continuous mode needs both algorithm and palette null")
    warnings.extend(str(entry) for entry in preset.warnings)
    return PresetReport(name, not errors, errors, warnings, renderer)


def validate_all(directories: Sequence[Path] | None = None) -> list[PresetReport]:
    """Validate every preset of the search directories, shipped tier first."""
    return [validate(entry.path) for entry in available(directories)]


def save_preset(path: str | Path, preset: Preset) -> Path:
    """Write preset as UTF-8 v3 JSON, creating the parent directories, and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(preset), encoding="utf-8")
    return target


def save_spec(path: str | Path, spec: PipelineSpec) -> Path:
    """Write the v3 preset of spec to path."""
    return save_preset(path, to_preset(spec))


__all__ = [
    "APP_CONTEXT",
    "APP_DIR_NAME",
    "DEFAULT_RENDERER",
    "PresetEntry",
    "PresetReport",
    "SHIPPED_PRESET_DIR",
    "app_data_dir",
    "available",
    "default_preset",
    "default_spec",
    "describe",
    "read_preset",
    "read_text",
    "save_preset",
    "save_spec",
    "search_dirs",
    "spec_from_text",
    "spec_of",
    "to_preset",
    "user_preset_dir",
    "validate",
    "validate_all",
]
