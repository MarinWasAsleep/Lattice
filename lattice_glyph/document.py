"""The single render path of Lattice Glyph: load, render, export bytes (G9, §8, §11).

Every entry point of the application goes through this module. ``render_rgb8`` is
``lattice_core.pipeline.render`` and nothing else, so the CLI and the GUI cannot drift:
the GUI export dialog is handed this exact function. SVG and text export need the
``CellGrid`` the pipeline builds internally (§3); ``grid_bundle`` re-runs the same core
steps in the same order and never re-implements their maths, and a test pins its frame
to ``render`` byte for byte.

Promoted effects are raster: they are applied to PNG and not to vector or text output,
which is reported as a warning instead of being silently dropped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image as PILImage

import lattice_core.dither  # noqa: F401  (registers every algorithm this path can run)
import lattice_core.effects  # noqa: F401  (registers every effect a preset may name)
from lattice_core import color
from lattice_core import pipeline as _pipeline
from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer
from lattice_core.pipeline import PipelineSpec, resolve_palette
from lattice_core.registry import get_algorithm, resolve_params
from lattice_core.svg import render_svg
from lattice_core.textout import render_text
from lattice_core.types import RGB8, Image, Palette

FORMATS: tuple[str, ...] = ("png", "svg", "txt", "ansi", "html")
TEXT_FORMATS: tuple[str, ...] = ("txt", "ansi", "html")
SUFFIXES: dict[str, str] = {
    "png": ".png",
    "svg": ".svg",
    "txt": ".txt",
    "ansi": ".ansi",
    "html": ".html",
}
RASTER_ONLY = "post effects are raster: they are not applied to {fmt} export"


class DocumentError(Exception):
    """A typed failure of the document path: unreadable source, or an impossible export."""


class GridError(DocumentError):
    """An export format that needs a CellGrid, asked for a render that has none."""


@dataclass(frozen=True)
class GridBundle:
    """The §3 grid of one spec, with the palette, renderer and style that produced it."""

    grid: CellGrid
    palette: Palette
    renderer: CellRenderer
    style: RenderStyle


@dataclass(frozen=True)
class Export:
    """One written file: where it went, in which format, its size and its warnings."""

    path: Path
    fmt: str
    size: int
    warnings: list[str] = field(default_factory=list)


def load_image(path: str | Path) -> Image:
    """Load path as a float32 RGB image, raising DocumentError when it is unusable."""
    target = Path(path)
    if not target.is_file():
        raise DocumentError(f"image not found: {target}")
    try:
        with PILImage.open(target) as handle:
            return color.to_float(handle)
    except (OSError, ValueError) as exc:
        raise DocumentError(f"cannot read image {target}: {exc}") from None


def render_rgb8(image: Image, spec: PipelineSpec) -> RGB8:
    """Render image through the core pipeline, raising DocumentError on any failure."""
    try:
        return _pipeline.render(image, spec)
    except Exception as exc:  # noqa: BLE001 - every pipeline failure is a render error (§8)
        raise DocumentError(f"render failed: {exc}") from None


def grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
    """Return the §3 grid of spec, built with the core steps in the normative order.

    Steps 1 to 5 come from ``pipeline._prepare``, the geometry from step 6, the cell
    averages, palette, dither, sub-points and samples from the helpers the pipeline
    itself calls; nothing is re-implemented here.
    """
    if spec.algorithm_id is None or spec.palette is None:
        raise GridError(
            "continuous mode has no cell grid: export png instead of svg, txt, ansi or html"
        )
    try:
        return _grid_bundle(image, spec)
    except (KeyError, ValueError) as exc:
        raise DocumentError(f"cannot build the cell grid: {exc}") from None


def _grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
    """Build the §3 grid of spec; the caller turns a lookup failure into a DocumentError."""
    work, _ = _pipeline._prepare(image, spec, None)
    renderer = get_renderer(spec.renderer)
    style = RenderStyle(options=dict(spec.renderer_style))
    cell_w, cell_h = _pipeline._cell_geometry(renderer, spec.pixel_size)
    padded = _pipeline._pad_to_cells(work, cell_w, cell_h)
    cells = _pipeline._to_cells(padded, cell_w, cell_h)
    palette = resolve_palette(spec.palette, cells)
    info = get_algorithm(spec.algorithm_id)
    params = resolve_params(info.params, spec.algorithm_params)
    params[_pipeline.RESERVED_METRIC] = color.metric_code(spec.color_metric)
    subgrid = (int(renderer.subgrid()[0]), int(renderer.subgrid()[1]))
    subindex = None
    if subgrid != (1, 1):
        subindex = _pipeline._subindex(
            padded, palette, info.fn, params, (cell_w, cell_h), subgrid
        )
    grid = _pipeline._make_grid(
        cells,
        _pipeline._run(info.fn, params, cells, palette),
        cell_w,
        cell_h,
        palette,
        samples=_pipeline._derive_samples(renderer, padded, cells, (cell_w, cell_h), subgrid),
        subindex=subindex,
    )
    return GridBundle(grid=grid, palette=palette, renderer=renderer, style=style)


def png_bytes(rgb8: RGB8) -> bytes:
    """Return rgb8 encoded as a PNG file byte for byte as the GUI export writes it."""
    buffer = io.BytesIO()
    color.to_pil(rgb8).save(buffer, format="PNG")
    return buffer.getvalue()


def export_bytes(image: Image, spec: PipelineSpec, fmt: str = "png") -> tuple[bytes, list[str]]:
    """Return the encoded output of spec in fmt, with the warnings of that export."""
    if fmt not in FORMATS:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    if fmt == "png":
        return png_bytes(render_rgb8(image, spec)), []
    bundle = grid_bundle(image, spec)
    warnings: list[str] = []
    if spec.post_effects:
        warnings.append(RASTER_ONLY.format(fmt=fmt))
    if fmt == "svg":
        document, svg_warnings = render_svg(
            bundle.grid, bundle.palette, bundle.renderer, bundle.style
        )
        return document.encode("utf-8"), warnings + list(svg_warnings)
    text = render_text(bundle.grid, bundle.palette, bundle.renderer, bundle.style, fmt=fmt)
    return text.encode("utf-8"), warnings


def target_path(path: str | Path, fmt: str) -> Path:
    """Return path with fmt's suffix appended when it carries none of its own."""
    target = Path(path)
    if target.suffix:
        return target
    if fmt not in SUFFIXES:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return target.with_name(target.name + SUFFIXES[fmt])


def write_render(image: Image, spec: PipelineSpec, path: str | Path, fmt: str = "png") -> Export:
    """Render spec and write it to path in fmt, creating the parent directories."""
    payload, warnings = export_bytes(image, spec, fmt)
    target = target_path(path, fmt)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    except OSError as exc:
        raise DocumentError(f"cannot write {target}: {exc}") from None
    return Export(path=target, fmt=fmt, size=len(payload), warnings=warnings)


def format_of(path: str | Path) -> str:
    """Return the export format named by path's suffix, png when the suffix is unknown."""
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix if suffix in FORMATS else "png"


__all__ = [
    "DocumentError",
    "Export",
    "FORMATS",
    "GridBundle",
    "GridError",
    "SUFFIXES",
    "TEXT_FORMATS",
    "export_bytes",
    "format_of",
    "grid_bundle",
    "load_image",
    "png_bytes",
    "render_rgb8",
    "target_path",
    "write_render",
]
