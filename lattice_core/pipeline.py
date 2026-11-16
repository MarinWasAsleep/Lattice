"""Render pipeline: spec dataclasses, palette resolution and the normative render order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from lattice_core import color
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle
from lattice_core.registry import get_algorithm, get_effect, resolve_params
from lattice_core.renderers import get_renderer
from lattice_core.types import RGB8, Image, Palette

MIN_PALETTE_SIZE = 2
MAX_PALETTE_SIZE = 256
MIN_PIXEL_SIZE = 1
MAX_PIXEL_SIZE = 32
POST_EFFECT_SEED_OFFSET = 1000
DEFAULT_RENDERER = "pixel"
COLOR_METRICS = ("srgb", "linear", "oklab", "lab2000")
PRESET_VERSION = 2
RESERVED_METRIC = "_color_metric"
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


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
    locked: list[str] = field(default_factory=list)
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
        from lattice_core.palettes.builtin import get_builtin

        return np.ascontiguousarray(get_builtin(spec.name), dtype=np.float32)
    if spec.source == "custom":
        return _palette_from_hex(spec.colors)
    if spec.source == "extracted":
        from lattice_core.palettes.extract import MAX_K, MIN_K, extract_palette

        k = int(spec.extract_k)
        if not MIN_K <= k <= MAX_K:
            raise ValueError(f"extract_k must be in [{MIN_K}, {MAX_K}], got {k}")
        locked = _locked_colors(spec.locked)
        if len(locked) > k:
            raise ValueError(f"{len(locked)} locked colours exceed extract_k={k}")
        if len(locked) == k:
            return _palette_from_hex(locked)
        wanted = max(MIN_K, k - len(locked))
        palette = extract_palette(img, wanted, spec.extract_method)
        rows = [_hex_row(entry) for entry in locked]
        rows.extend(np.asarray(palette, dtype=np.float32)[: k - len(locked)].tolist())
        return np.ascontiguousarray(np.array(rows, dtype=np.float32))
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


def render(
    src: Image,
    spec: PipelineSpec,
    *,
    max_side: int | None = None,
    renderer: str = DEFAULT_RENDERER,
    style: RenderStyle | None = None,
) -> RGB8:
    """Render src through the eleven normative pipeline steps and return uint8 RGB."""
    work, target = _prepare(src, spec, max_side)
    return _finish(work, target, spec, None, renderer, style)


def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None) -> Image:
    """Return src after steps 1 to 5, the image palette resolution reads."""
    work, _ = _prepare(src, spec, max_side)
    cell_w, cell_h = _cell_geometry(get_renderer(DEFAULT_RENDERER), spec.pixel_size)
    return _to_cells(work, cell_w, cell_h)


def render_with_palette(
    src: Image,
    spec: PipelineSpec,
    palette: Palette,
    *,
    max_side: int | None = None,
    renderer: str = DEFAULT_RENDERER,
    style: RenderStyle | None = None,
) -> RGB8:
    """Render src with an already resolved palette, skipping step 5's resolution."""
    work, target = _prepare(src, spec, max_side)
    return _finish(work, target, spec, palette, renderer, style)


def _prepare(
    src: Image, spec: PipelineSpec, max_side: int | None
) -> tuple[Image, tuple[int, int]]:
    """Run steps 1 to 5 and return the working image with the target shape of step 1."""
    work = _as_image(src)
    work = _proxy(work, max_side)
    target = work.shape[:2]
    work = _apply_effects(work, spec.pre_effects, spec.seed, 0)
    if spec.auto_levels:
        work = color.auto_levels(work)
    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
    if spec.pre_blur > 0.0:
        work = color.gaussian_blur(work, spec.pre_blur / 3.0)
    return work, target


def _finish(
    work: Image,
    target: tuple[int, int],
    spec: PipelineSpec,
    palette: Palette | None,
    renderer_name: str = DEFAULT_RENDERER,
    style: RenderStyle | None = None,
) -> RGB8:
    """Run steps 6 to 12: choose the grid, quantise, render, then the post-effects."""
    renderer = get_renderer(renderer_name)
    cell_w, cell_h = _cell_geometry(renderer, spec.pixel_size)
    cells = _to_cells(work, cell_w, cell_h)
    if palette is None:
        palette = resolve_palette(spec.palette, cells)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    code = color.metric_code(spec.color_metric)
    params[RESERVED_METRIC] = code
    indices = info.fn(
        color.to_working_space(cells, code), color.to_working_space(palette, code), params
    )
    grid = _make_grid(cells, indices, cell_w, cell_h, palette)
    style = RenderStyle(options={}) if style is None else style
    frame = _render_frame(renderer, grid, palette, style)
    frame = frame[: target[0], : target[1]]
    frame = _apply_effects(frame, spec.post_effects, spec.seed, POST_EFFECT_SEED_OFFSET)
    return color.to_rgb8(frame)


def _cell_geometry(renderer: CellRenderer, pixel_size: int) -> tuple[int, int]:
    """Return (cell_w, cell_h) from the renderer's cell aspect and the clamped pixel size."""
    size = _pixel_size(pixel_size)
    aspect = float(renderer.cell_aspect())
    if not aspect > 0.0:
        raise ValueError(f"renderer {renderer.name!r} returned cell_aspect {aspect!r}")
    return size, max(1, int(round(size / aspect)))


def _to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
    """Step 7: downscale the prepared image to the grid of cell_w x cell_h blocks."""
    if cell_w == cell_h:
        return color.downscale(work, cell_w)
    pad_y = (-work.shape[0]) % cell_h
    pad_x = (-work.shape[1]) % cell_w
    if pad_y or pad_x:
        work = np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
    rows = work.shape[0] // cell_h
    cols = work.shape[1] // cell_w
    blocks = work.reshape(rows, cell_h, cols, cell_w, 3)
    return np.ascontiguousarray(blocks.mean(axis=(1, 3), dtype=np.float32))


def _render_frame(
    renderer: CellRenderer, grid: CellGrid, palette: Palette, style: RenderStyle
) -> Image:
    """Return the step-11 frame as float32, skipping the uint8 round-trip when exact."""
    exact = getattr(renderer, "render_frame", None)
    if callable(exact):
        return np.ascontiguousarray(np.asarray(exact(grid, palette, style), dtype=np.float32))
    return color.to_float(renderer.render(grid, palette, style))


def _make_grid(
    work: Image, indices: np.ndarray, cell_w: int, cell_h: int, palette: Palette
) -> CellGrid:
    """Build the CellGrid of step 10: index, coverage, luma and samples per cell."""
    rows, cols = indices.shape
    linear = color.srgb_to_linear(work)
    luma = (
        np.float32(0.2126) * linear[:, :, 0]
        + np.float32(0.7152) * linear[:, :, 1]
        + np.float32(0.0722) * linear[:, :, 2]
    ).astype(np.float32)
    samples = luma[:, :, None].copy()
    coverage = _coverage_table(palette)[np.ascontiguousarray(indices, dtype=np.int32)]
    return CellGrid(
        cols=cols,
        rows=rows,
        cell_w=cell_w,
        cell_h=cell_h,
        index=np.ascontiguousarray(indices, dtype=np.int32),
        coverage=np.ascontiguousarray(coverage, dtype=np.float32),
        luma=np.ascontiguousarray(luma, dtype=np.float32),
        samples=np.ascontiguousarray(samples, dtype=np.float32),
    )


def _coverage_table(palette: Palette) -> np.ndarray:
    """Derive ink coverage per palette entry, 0.0 on a single-luminance palette."""
    linear = color.srgb_to_linear(palette)
    lum = (
        np.float32(0.2126) * linear[:, 0]
        + np.float32(0.7152) * linear[:, 1]
        + np.float32(0.0722) * linear[:, 2]
    )
    lum_min = float(lum.min())
    lum_max = float(lum.max())
    if lum_max == lum_min:
        return np.zeros(palette.shape[0], dtype=np.float32)
    return np.ascontiguousarray(((lum - lum_min) / (lum_max - lum_min)).astype(np.float32))


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


def _hex_text(entry: object) -> str:
    """Return entry as an uppercase "#RRGGBB" string, or raise ValueError."""
    text = str(entry).strip().lstrip("#")
    if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
        raise ValueError(f"invalid palette colour: {entry!r}")
    return "#" + text.upper()


def _hex_row(entry: object) -> list[float]:
    """Parse one colour into a float32 RGB row."""
    text = _hex_text(entry)[1:]
    return [int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _locked_colors(values: list[str]) -> list[str]:
    """Return the locked colours as unique uppercase "#RRGGBB" strings, in order."""
    unique: list[str] = []
    for entry in values:
        text = _hex_text(entry)
        if text not in unique:
            unique.append(text)
    return unique


def _palette_from_hex(colors: list[str]) -> Palette:
    """Parse "#RRGGBB" strings into a float32 palette, validating count and syntax."""
    if not MIN_PALETTE_SIZE <= len(colors) <= MAX_PALETTE_SIZE:
        raise ValueError(
            f"a palette needs {MIN_PALETTE_SIZE} to {MAX_PALETTE_SIZE} colours, got {len(colors)}"
        )
    rows = [_hex_row(entry) for entry in colors]
    return np.ascontiguousarray(np.array(rows, dtype=np.float32))
