"""Render pipeline: spec dataclasses, palette resolution and the normative render order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from dithercraft.core import color
from dithercraft.core.registry import get_algorithm, get_effect, resolve_params
from dithercraft.core.types import RGB8, Image, Palette

MIN_PALETTE_SIZE = 2
MAX_PALETTE_SIZE = 256
MIN_PIXEL_SIZE = 1
MAX_PIXEL_SIZE = 32
POST_EFFECT_SEED_OFFSET = 1000


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


@dataclass
class PipelineSpec:
    """Complete, serialisable description of one render."""

    version: int = 1
    pre_effects: list[EffectInstance] = field(default_factory=list)
    brightness: float = 0.0
    contrast: float = 0.0
    gamma: float = 1.0
    pixel_size: int = 1
    algorithm_id: str = "floyd_steinberg"
    algorithm_params: dict = field(default_factory=dict)
    palette: PaletteSpec = field(default_factory=PaletteSpec)
    post_effects: list[EffectInstance] = field(default_factory=list)
    seed: int = 0


def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
    """Return the float32 palette described by spec, extracting from img when needed."""
    if spec.source == "builtin":
        from dithercraft.palettes.builtin import get_builtin

        return np.ascontiguousarray(get_builtin(spec.name), dtype=np.float32)
    if spec.source == "custom":
        return _palette_from_hex(spec.colors)
    if spec.source == "extracted":
        from dithercraft.palettes.extract import extract_palette

        palette = extract_palette(img, int(spec.extract_k), spec.extract_method)
        return np.ascontiguousarray(palette, dtype=np.float32)
    raise ValueError(f"unknown palette source: {spec.source!r}")


def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> RGB8:
    """Render src through the nine normative pipeline steps and return uint8 RGB."""
    work = _as_image(src)
    work = _proxy(work, max_side)
    target = work.shape[:2]
    work = _apply_effects(work, spec.pre_effects, spec.seed, 0)
    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma)
    factor = _pixel_size(spec.pixel_size)
    work = color.downscale(work, factor)
    palette = resolve_palette(spec.palette, work)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    indices = info.fn(work, palette, params)
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
    """Run the enabled effects in order, seeding effect i with seed + offset + i."""
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
