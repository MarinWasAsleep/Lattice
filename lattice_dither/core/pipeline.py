"""Render pipeline: spec dataclasses, palette resolution and the normative render order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from lattice_dither.core import color
from lattice_dither.core.registry import get_algorithm, get_effect, resolve_params
from lattice_dither.core.types import RGB8, Image, Palette

MIN_PALETTE_SIZE = 2
MAX_PALETTE_SIZE = 256
MIN_PIXEL_SIZE = 1
MAX_PIXEL_SIZE = 32
POST_EFFECT_SEED_OFFSET = 1000
COLOR_METRICS = ("srgb", "linear", "oklab", "lab2000")
PRESET_VERSION = 2
RESERVED_METRIC = "_color_metric"


@dataclass
class PresetMeta:
    """Human-readable description of a preset, carried through the JSON format."""

    name: str = ""
    author: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail: str = ""


@dataclass
class EffectInstance:
    """One configured effect in a pipeline, with its parameters and enabled flag."""

    effect_id: str
    params: dict = field(default_factory=dict)
    enabled: bool = True


@dataclass
class PaletteSpec:
    """Description of the palette a pipeline renders with."""

    source: Literal["builtin", "extracted", "custom"] = "builtin"
    name: str = "bw"
    colors: list[str] = field(default_factory=list)
    extract_k: int = 8
    extract_method: str = "kmeans"
    locked: list[int] = field(default_factory=list)
    order: list[int] = field(default_factory=list)


@dataclass
class PipelineSpec:
    """Complete, serialisable description of one render."""

    version: int = PRESET_VERSION
    pre_effects: list[EffectInstance] = field(default_factory=list)
    brightness: float = 0.0
    contrast: float = 0.0
    gamma: float = 1.0
    saturation: float = 0.0
    pre_blur: float = 0.0
    auto_levels: bool = False
    color_metric: str = "srgb"
    pixel_size: int = 1
    algorithm_id: str = "floyd_steinberg"
    algorithm_params: dict = field(default_factory=dict)
    palette: PaletteSpec = field(default_factory=PaletteSpec)
    post_effects: list[EffectInstance] = field(default_factory=list)
    seed: int = 0
    meta: PresetMeta = field(default_factory=PresetMeta)


def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
    """Return the float32 palette described by spec, extracting from img when needed."""
    palette = _palette_for(spec, img)
    _validate_order(spec.order, palette.shape[0])
    return palette


def _palette_for(spec: PaletteSpec, img: Image) -> Palette:
    """Build the palette of spec without validating its display order."""
    if spec.source == "builtin":
        from lattice_dither.palettes.builtin import get_builtin

        return np.ascontiguousarray(get_builtin(spec.name), dtype=np.float32)
    if spec.source == "custom":
        return _palette_from_hex(spec.colors)
    if spec.source == "extracted":
        from lattice_dither.palettes.extract import extract_palette

        if len(spec.locked) > int(spec.extract_k):
            raise ValueError(
                f"{len(spec.locked)} locked colours exceed extract_k={spec.extract_k}"
            )
        palette = extract_palette(img, int(spec.extract_k), spec.extract_method)
        return np.ascontiguousarray(palette, dtype=np.float32)
    raise ValueError(f"unknown palette source: {spec.source!r}")


def _validate_order(order: list[int], size: int) -> None:
    """Raise ValueError naming the offending index when order is not a permutation."""
    if not order:
        return
    seen: set[int] = set()
    for index in order:
        if not 0 <= index < size:
            raise ValueError(f"palette order index {index} is outside [0, {size})")
        if index in seen:
            raise ValueError(f"palette order index {index} is repeated")
        seen.add(index)
    if len(order) != size:
        missing = sorted(set(range(size)) - seen)[0]
        raise ValueError(f"palette order is missing index {missing}")


def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
    """Render src through the eleven normative pipeline steps and return uint8 RGB."""
    work = _as_image(src)
    work = _proxy(work, max_side)
    target = work.shape[:2]
    work = _apply_effects(work, spec.pre_effects, spec.seed, 0)
    if spec.auto_levels:
        work = color.auto_levels(work)
    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
    if spec.pre_blur > 0.0:
        work = color.gaussian_blur(work, spec.pre_blur / 3.0)
    factor = _pixel_size(spec.pixel_size)
    work = color.downscale(work, factor)
    palette = resolve_palette(spec.palette, work)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    code = color.metric_code(spec.color_metric)
    params[RESERVED_METRIC] = code
    indices = info.fn(
        color.to_working_space(work, code), color.to_working_space(palette, code), params
    )
    work = color.apply_palette(indices, palette)
    work = color.upscale_nearest(work, factor, target)
    work = _apply_effects(work, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
    return color.to_rgb8(work)


def _as_image(src: Image) -> Image:
    """Validate the source shape and return it as a contiguous float32 image."""
    array = np.asarray(src)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
    return np.ascontiguousarray(array, dtype=np.float32)


def _proxy(img: Image, max_side: int | None) -> Image:
    """Area-downscale img by an integer factor so its longest side is at most max_side."""
    if max_side is None:
        return img
    if max_side < 1:
        raise ValueError(f"max_side must be >= 1, got {max_side}")
    longest = max(img.shape[:2])
    if longest <= max_side:
        return img
    factor = -(-longest // max_side)
    return color.downscale(img, factor)


def _pixel_size(value: int) -> int:
    """Clamp pixel_size to the contract range 1..32."""
    return max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(value)))


def _apply_effects(img: Image, instances: list[EffectInstance], seed: int, offset: int) -> Image:
    """Run the enabled effects in order, seeding the i-th enabled one with seed + offset + i."""
    out = img
    index = 0
    for instance in instances:
        if not instance.enabled:
            continue
        info = get_effect(instance.effect_id)
        params = resolve_params(info.params, instance.params)
        rng = np.random.default_rng(seed + offset + index)
        out = np.ascontiguousarray(np.clip(info.fn(out, params, rng), 0.0, 1.0), dtype=np.float32)
        index += 1
    return out


def _palette_from_hex(colors: list[str]) -> Palette:
    """Parse "#RRGGBB" strings into a float32 palette, validating count and syntax."""
    if not MIN_PALETTE_SIZE <= len(colors) <= MAX_PALETTE_SIZE:
        raise ValueError(
            f"a palette needs {MIN_PALETTE_SIZE} to {MAX_PALETTE_SIZE} colours, got {len(colors)}"
        )
    rows = []
    for entry in colors:
        text = str(entry).strip().lstrip("#")
        if len(text) != 6:
            raise ValueError(f"invalid palette colour: {entry!r}")
        try:
            rows.append([int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4)])
        except ValueError as exc:
            raise ValueError(f"invalid palette colour: {entry!r}") from exc
    return np.ascontiguousarray(np.array(rows, dtype=np.float32))
