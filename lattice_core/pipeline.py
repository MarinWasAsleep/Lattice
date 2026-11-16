"""Render pipeline: spec dataclasses, palette resolution and the normative render order."""

from __future__ import annotations

import math
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
    algorithm_id: str | None = "floyd_steinberg"
    algorithm_params: dict = field(default_factory=dict)
    palette: PaletteSpec | None = field(default_factory=PaletteSpec)
    post_effects: list[EffectInstance] = field(default_factory=list)
    seed: int = 0
    meta: PresetMeta = field(default_factory=PresetMeta)
    renderer: str = DEFAULT_RENDERER
    renderer_style: dict = field(default_factory=dict)


def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
    """Return the float32 palette described by spec, extracting from img when needed."""
    palette = _palette_for(spec, img)
    _validate_order(spec.order, palette.shape[0])
    return palette


def _palette_for(spec: PaletteSpec, img: Image) -> Palette:
    """Build the palette of spec without validating its display order."""
    if spec.source == "custom":
        return _rows_to_palette([_hex_row(entry) for entry in spec.colors])
    if spec.source == "builtin":
        from lattice_core.palettes.builtin import get_builtin

        return np.ascontiguousarray(get_builtin(spec.name), np.float32)
    if spec.source != "extracted":
        raise ValueError(f"unknown palette source: {spec.source!r}")
    from lattice_core.palettes.extract import MAX_K, MIN_K, extract_palette
    k = int(spec.extract_k)
    locked = list(dict.fromkeys(tuple(_hex_row(entry)) for entry in spec.locked))
    if not MIN_K <= k <= MAX_K:
        raise ValueError(f"extract_k must be in [{MIN_K}, {MAX_K}], got {k}")
    if len(locked) > k:
        raise ValueError(f"{len(locked)} locked colours exceed extract_k={k}")
    if len(locked) == k:
        return _rows_to_palette(locked)
    found = np.asarray(extract_palette(img, max(MIN_K, k - len(locked)), spec.extract_method),
                       np.float32)
    return _rows_to_palette(locked + found[: k - len(locked)].tolist())


def _validate_order(order: list[int], size: int) -> None:
    """Raise ValueError naming the offending index when order is not a permutation."""
    if not order:
        return
    for index in order:
        if not 0 <= index < size:
            raise ValueError(f"palette order index {index} is outside [0, {size})")
    if len(set(order)) != len(order):
        raise ValueError(f"palette order index {next(i for i in order if order.count(i) > 1)}"
                         " is repeated")
    if len(order) != size:
        missing = sorted(set(range(size)) - set(order))[0]
        raise ValueError(f"palette order is missing index {missing}")


def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
           renderer: str | None = None, style: RenderStyle | None = None) -> RGB8:
    """Render src through the twelve normative pipeline steps and return uint8 RGB."""
    work, target = _prepare(src, spec, max_side)
    return _finish(work, target, spec, None, renderer, style)


def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
                  renderer: str | None = None) -> Image:
    """Return src after steps 1 to 5, the image palette resolution reads."""
    work, _ = _prepare(src, spec, max_side)
    if spec.algorithm_id is None:
        return np.ascontiguousarray(work, np.float32)
    name = spec.renderer if renderer is None else renderer
    return _to_cells(work, *_cell_geometry(get_renderer(name), spec.pixel_size))


def render_with_palette(src: Image, spec: PipelineSpec, palette: Palette,
                        *, max_side: int | None = None, renderer: str | None = None,
                        style: RenderStyle | None = None) -> RGB8:
    """Render src with an already resolved palette through the twelve pipeline steps."""
    work, target = _prepare(src, spec, max_side)
    return _finish(work, target, spec, palette, renderer, style)


def _check_continuous(spec: PipelineSpec) -> None:
    """Reject a half-null spec: continuous mode needs algorithm_id and palette both None."""
    if (spec.algorithm_id is None) != (spec.palette is None):
        raise ValueError("continuous mode needs algorithm_id and palette both None")


def _prepare(src: Image, spec: PipelineSpec, max_side: int | None) -> tuple[Image, tuple[int, int]]:
    """Run steps 1 to 5 and return the working image with the target shape of step 1."""
    _check_continuous(spec)
    work = _proxy(_as_image(src), max_side)
    target = work.shape[:2]
    work = _apply_effects(work, spec.pre_effects, spec.seed, 0)
    if spec.auto_levels:
        work = color.auto_levels(work)
    work = color.adjust(work, spec.brightness, spec.contrast, spec.gamma, spec.saturation)
    if spec.pre_blur > 0.0:
        work = color.gaussian_blur(work, spec.pre_blur / 3.0)
    return work, target


def _as_image(src: Image) -> Image:
    """Validate the source shape and return it as a contiguous float32 image."""
    array = np.asarray(src)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
    return np.ascontiguousarray(array, np.float32)


def _proxy(img: Image, max_side: int | None) -> Image:
    """Area-downscale img by an integer factor so its longest side is at most max_side."""
    if max_side is None:
        return img
    if max_side < 1:
        raise ValueError(f"max_side must be >= 1, got {max_side}")
    longest = max(img.shape[:2])
    return img if longest <= max_side else color.downscale(img, -(-longest // max_side))


def _finish(work: Image, target: tuple[int, int], spec: PipelineSpec, palette: Palette | None,
            renderer_name: str | None = None, style: RenderStyle | None = None) -> RGB8:
    """Run steps 6 to 12; in continuous mode (algorithm and palette null) skip 6 to 11."""
    _check_continuous(spec)
    frame = work if spec.algorithm_id is None else _quantise(
        work, spec, palette, renderer_name, style)
    frame = _apply_effects(frame[: target[0], : target[1]], spec.post_effects, spec.seed,
                           POST_EFFECT_SEED_OFFSET)
    return color.to_rgb8(frame)


def _quantise(work: Image, spec: PipelineSpec, palette: Palette | None,
              renderer_name: str | None, style: RenderStyle | None) -> Image:
    """Run steps 6 to 11: build the grid, dither it and rasterise the renderer frame."""
    renderer = get_renderer(spec.renderer if renderer_name is None else renderer_name)
    style = RenderStyle(options=spec.renderer_style) if style is None else style
    cell_w, cell_h = _cell_geometry(renderer, spec.pixel_size)
    work = _pad_to_cells(work, cell_w, cell_h)
    cells = _to_cells(work, cell_w, cell_h)
    if palette is None:
        palette = resolve_palette(spec.palette, cells)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    params[RESERVED_METRIC] = color.metric_code(spec.color_metric)
    sx, sy = (int(value) for value in renderer.subgrid())
    if sx < 1 or sy < 1:
        raise ValueError(f"renderer {renderer.name!r} returned an invalid subgrid {(sx, sy)!r}")
    size, subgrid = (cell_w, cell_h), (sx, sy)
    sub = None if subgrid == (1, 1) else _subindex(work, palette, info.fn, params, size, subgrid)
    grid = _make_grid(cells, _run(info.fn, params, cells, palette), cell_w, cell_h, palette,
                      samples=_derive_samples(renderer, work, cells, size, subgrid), subindex=sub)
    return _render_frame(renderer, grid, palette, style)


def _run(fn, params: dict, img: Image, palette: Palette) -> np.ndarray:
    """Run one algorithm function over img in the working space of the colour metric."""
    code = params[RESERVED_METRIC]
    out = fn(color.to_working_space(img, code), color.to_working_space(palette, code), params)
    return np.ascontiguousarray(out, np.int32)


def _subindex(work: Image, palette: Palette, fn, params: dict, size: tuple[int, int],
              subgrid: tuple[int, int]) -> np.ndarray:
    """Dither the step-5 image at (rows*sy, cols*sx) sub-point resolution (§3, S3)."""
    sx, sy = subgrid
    rows, cols = work.shape[0] // size[1], work.shape[1] // size[0]
    sub = _run(fn, params, _to_subpoints(work, size, subgrid), palette)
    packed = sub.reshape(rows, sy, cols, sx).transpose(0, 2, 1, 3)
    return np.ascontiguousarray(packed.reshape(rows, cols, sx * sy), dtype=np.int32)


def _to_subpoints(work: Image, size: tuple[int, int], subgrid: tuple[int, int]) -> Image:
    """Area-average the padded step-5 image onto the (rows*sy, cols*sx) sub-point grid."""
    (cell_w, cell_h), (sx, sy) = size, subgrid
    rows, cols = work.shape[0] // cell_h, work.shape[1] // cell_w
    blocks = work.reshape(rows, cell_h, cols, cell_w, 3)
    out = np.empty((rows * sy, cols * sx, 3), dtype=np.float32)
    for i, (y0, y1) in enumerate(_spans(cell_h, sy)):
        for j, (x0, x1) in enumerate(_spans(cell_w, sx)):
            out[i::sy, j::sx] = blocks[:, y0:y1, :, x0:x1].mean(axis=(1, 3), dtype=np.float32)
    return np.ascontiguousarray(out, dtype=np.float32)


def _spans(length: int, count: int) -> list[tuple[int, int]]:
    """Split length pixels into count contiguous [start, end) spans of at least one pixel."""
    edges = [index * length // count for index in range(count + 1)]
    return [(start, min(length, max(start + 1, end))) for start, end in zip(edges, edges[1:],
                                                                           strict=False)]


def _derive_samples(renderer: CellRenderer, work: Image, cells: Image, size: tuple[int, int],
                    subgrid: tuple[int, int]) -> Image:
    """Return the (rows, cols, k) sub-cell luminance of the SOURCE cell (§3 step 10)."""
    (cell_w, cell_h) = size
    points = _stencil_points(renderer, subgrid)
    if points is None:
        return np.ascontiguousarray(_linear_luma(cells)[:, :, None], dtype=np.float32)
    lum = _linear_luma(work)
    col, row = np.arange(cells.shape[1])[None, :, None], np.arange(cells.shape[0])[:, None, None]
    x = np.clip(np.floor((col + points[None, :, 0]) * cell_w).astype(np.int64), col * cell_w,
                (col + 1) * cell_w - 1)
    y = np.clip(np.floor((row + points[None, :, 1]) * cell_h).astype(np.int64), row * cell_h,
                (row + 1) * cell_h - 1)
    return np.ascontiguousarray(lum[y, x], dtype=np.float32)


def _stencil_points(renderer: CellRenderer, subgrid: tuple[int, int]) -> np.ndarray | None:
    """Return the renderer's (k, 2) stencil, or None for the default cell-mean stencil."""
    stencil = getattr(renderer, "sample_points", None)
    if callable(stencil):
        points = np.asarray(stencil(), dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 2 or points.shape[0] == 0:
            raise ValueError(f"renderer {renderer.name!r} sample_points() must be a (k, 2) array")
        return points
    if subgrid == (1, 1):
        return None
    xs, ys = ((np.arange(n, dtype=np.float32) + 0.5) / n for n in subgrid)
    return np.ascontiguousarray(
        np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2), dtype=np.float32
    )


def _linear_luma(img: Image) -> np.ndarray:
    """Return the linear-light luminance of img as a float32 (H, W) array."""
    linear = color.srgb_to_linear(img)
    return np.ascontiguousarray(np.float32(0.2126) * linear[:, :, 0]
                                + np.float32(0.7152) * linear[:, :, 1]
                                + np.float32(0.0722) * linear[:, :, 2], dtype=np.float32)


def _pad_to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
    """Replicate the bottom and right edges so the image holds a whole number of cells."""
    pad_y, pad_x = (-work.shape[0]) % cell_h, (-work.shape[1]) % cell_w
    if not (pad_y or pad_x):
        return work
    return np.pad(work, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")


def _cell_geometry(renderer: CellRenderer, pixel_size: int) -> tuple[int, int]:
    """Return the (cell_w, cell_h) that the §5 step-6 geometry rule gives this renderer."""
    size = max(MIN_PIXEL_SIZE, min(MAX_PIXEL_SIZE, int(pixel_size)))
    aspect = float(renderer.cell_aspect())
    if not aspect > 0.0:
        raise ValueError(f"renderer {renderer.name!r} returned cell_aspect {aspect!r}")
    if aspect >= 1.0:
        return size, max(1, math.floor(size / aspect + 0.5))
    return max(1, math.floor(size * aspect + 0.5)), size


def _to_cells(work: Image, cell_w: int, cell_h: int) -> Image:
    """Average every cell_w x cell_h block of work into one cell colour."""
    if cell_w == cell_h:
        return color.downscale(work, cell_w)
    work = _pad_to_cells(work, cell_w, cell_h)
    blocks = work.reshape(work.shape[0] // cell_h, cell_h, work.shape[1] // cell_w, cell_w, 3)
    return np.ascontiguousarray(blocks.mean(axis=(1, 3), dtype=np.float32))


def _render_frame(renderer: CellRenderer, grid: CellGrid, palette: Palette,
                  style: RenderStyle) -> Image:
    """Return the renderer's frame, using render_frame when the renderer implements it."""
    exact = getattr(renderer, "render_frame", None)
    if not callable(exact):
        return color.to_float(renderer.render(grid, palette, style))
    frame = np.ascontiguousarray(np.asarray(exact(grid, palette, style), dtype=np.float32))
    expected = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
    if frame.shape != expected:
        raise ValueError(f"render_frame returned shape {frame.shape}, expected {expected}")
    return frame


def _make_grid(work: Image, indices: np.ndarray, cell_w: int, cell_h: int, palette: Palette,
               *, samples: Image | None = None, subindex: np.ndarray | None = None) -> CellGrid:
    """Assemble the CellGrid handed to the renderer from the dithered cell image."""
    luma = _linear_luma(work)
    if samples is None:
        samples = luma[:, :, None]
    return CellGrid(
        cols=indices.shape[1], rows=indices.shape[0], cell_w=cell_w, cell_h=cell_h,
        index=np.ascontiguousarray(indices, dtype=np.int32),
        coverage=np.ascontiguousarray(_coverage_table(palette)[indices], dtype=np.float32),
        luma=np.ascontiguousarray(luma, dtype=np.float32),
        samples=np.ascontiguousarray(samples, np.float32),
        subindex=np.ascontiguousarray(subindex, dtype=np.int32) if subindex is not None else None,
    )


def _coverage_table(palette: Palette) -> np.ndarray:
    """Return the ink coverage of every palette entry, from linear-light luminance."""
    linear = color.srgb_to_linear(palette)
    lum = (np.float32(0.2126) * linear[:, 0] + np.float32(0.7152) * linear[:, 1]
           + np.float32(0.0722) * linear[:, 2])
    lum_min, lum_max = float(lum.min()), float(lum.max())
    if lum_max == lum_min:
        return np.zeros(palette.shape[0], dtype=np.float32)
    return np.ascontiguousarray(((lum - lum_min) / (lum_max - lum_min)).astype(np.float32))


def _apply_effects(img: Image, instances: list[EffectInstance], seed: int, offset: int) -> Image:
    """Run the enabled effects in order, seeding the i-th enabled one with seed + offset + i."""
    out, index = img, 0
    for instance in instances:
        if not instance.enabled:
            continue
        info = get_effect(instance.effect_id)
        params = resolve_params(info.params, instance.params)
        rng = np.random.default_rng(seed + offset + index)
        out = np.ascontiguousarray(np.clip(info.fn(out, params, rng), 0.0, 1.0), dtype=np.float32)
        index += 1
    return out


def _hex_row(entry: object) -> list[float]:
    """Parse one "#RRGGBB" colour into a float32 RGB row, or raise ValueError."""
    text = str(entry).strip().lstrip("#")
    if len(text) != 6 or not _HEX_DIGITS.issuperset(text):
        raise ValueError(f"invalid palette colour: {entry!r}")
    return [int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _rows_to_palette(rows: list) -> Palette:
    """Build a float32 (K, 3) palette from parsed RGB rows, validating the count."""
    if not MIN_PALETTE_SIZE <= len(rows) <= MAX_PALETTE_SIZE:
        raise ValueError(f"a palette needs {MIN_PALETTE_SIZE}-{MAX_PALETTE_SIZE} colours, "
                         f"got {len(rows)}")
    return np.ascontiguousarray(np.array(rows, dtype=np.float32))
