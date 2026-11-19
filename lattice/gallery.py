"""Reference gallery and preset interchange: every algorithm and renderer side by side.

The gallery renders one cell per registered algorithm and per registered renderer on a
single reference image and composes them into one labelled contact sheet (L21, §6 §11).
The interchange helpers load a preset written by any app in another app's context, with
the §6 warning and fallback renderer, and render it through the core pipeline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw

from lattice import color
from lattice.pipeline import PaletteSpec, PipelineSpec, render
from lattice.preset import Preset, load_preset, to_pipeline_spec
from lattice.registry import list_algorithms
from lattice.renderers import list_renderers
from lattice.types import RGB8, Image

REFERENCE_SIDE = 200
CELL_SIZE = 128
LABEL_HEIGHT = 18
COLUMNS = 6
SHEET_BACKGROUND = (24, 24, 28)
LABEL_COLOR = (235, 235, 240)
PLACEHOLDER_COLOR = (42, 42, 48)
MAX_GALLERY_BYTES = 4 * 1024 * 1024
MIN_SHEET_SIDE = 64
ALGORITHM_PIXEL_SIZE = 2
RENDERER_PIXEL_SIZE = 8
DEFAULT_PALETTE = "pico8"
STARTER_DIR_NAME = "starter"
_DISCS = (
    (0.28, 0.30, 0.16, (1.0, 0.95, 0.2)),
    (0.72, 0.34, 0.13, (0.1, 0.9, 1.0)),
    (0.50, 0.74, 0.19, (1.0, 0.25, 0.55)),
)


def reference_image(size: int = REFERENCE_SIDE) -> Image:
    """Build the deterministic reference image: gradients, three discs, a checker band."""
    if size < 8:
        raise ValueError(f"reference image side must be >= 8, got {size}")
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    u, v = xs / (size - 1), ys / (size - 1)
    img = np.empty((size, size, 3), dtype=np.float32)
    img[:, :, 0] = 0.15 + 0.8 * u
    img[:, :, 1] = 0.15 + 0.8 * v
    img[:, :, 2] = 0.15 + 0.7 * (1.0 - u) * (1.0 - v)
    for cx, cy, radius, colour in _DISCS:
        disc = (u - cx) * (u - cx) + (v - cy) * (v - cy) < radius * radius
        for channel in range(3):
            img[:, :, channel] = np.where(disc, colour[channel], img[:, :, channel])
    checker = ((xs // 12 + ys // 12) % 2).astype(np.float32)
    band = (v > 0.86) & (v < 0.96)
    for channel in range(3):
        img[:, :, channel] = np.where(band, checker * 0.9 + 0.05, img[:, :, channel])
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0), dtype=np.float32)


def square_proxy(source: Image, side: int) -> Image:
    """Return source box-resized to a side×side float32 proxy, whatever its shape."""
    if side < 1:
        raise ValueError(f"proxy side must be >= 1, got {side}")
    pil = color.to_pil(color.to_rgb8(np.asarray(source, dtype=np.float32)))
    return color.to_float(pil.resize((side, side), PILImage.Resampling.BOX))


def _default_algorithm() -> str | None:
    """Return floyd_steinberg when registered, else the first algorithm, else None."""
    ids = [info.id for info in list_algorithms()]
    if "floyd_steinberg" in ids:
        return "floyd_steinberg"
    return ids[0] if ids else None


@dataclass(frozen=True)
class GalleryEntry:
    """One gallery cell: an algorithm or a renderer, with the spec that draws it."""

    id: str
    label: str
    kind: str
    spec: PipelineSpec


def gallery_entries(*, palette: str = DEFAULT_PALETTE) -> list[GalleryEntry]:
    """Return one entry per registered algorithm, then one per registered renderer."""
    entries: list[GalleryEntry] = []
    for info in list_algorithms():
        spec = PipelineSpec(algorithm_id=info.id, pixel_size=ALGORITHM_PIXEL_SIZE,
                            palette=PaletteSpec(source="builtin", name=palette))
        entries.append(GalleryEntry(f"algorithm:{info.id}", info.name, "algorithm", spec))
    algorithm = _default_algorithm()
    for name in list_renderers():
        spec = PipelineSpec(algorithm_id=algorithm, pixel_size=RENDERER_PIXEL_SIZE,
                            palette=PaletteSpec(source="builtin", name=palette), renderer=name)
        if algorithm is None:
            spec.palette = None
        entries.append(GalleryEntry(f"renderer:{name}", name, "renderer", spec))
    return entries


@dataclass(frozen=True)
class GalleryCell:
    """One rendered gallery cell: its entry identity and its square thumbnail."""

    entry_id: str
    label: str
    kind: str
    rgb8: RGB8


@dataclass(frozen=True)
class GallerySheet:
    """The whole gallery: every cell, the composed contact sheet and the warnings."""

    cells: list[GalleryCell]
    image: RGB8
    warnings: list[str] = field(default_factory=list)


def _resize(rgb8: RGB8, size: int) -> RGB8:
    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
    if rgb8.shape[:2] == (size, size):
        return np.ascontiguousarray(rgb8, dtype=np.uint8)
    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def _render_cell(entry: GalleryEntry, proxy: Image, size: int) -> tuple[RGB8, str]:
    """Render one entry on the proxy; a failure yields a placeholder and its message."""
    try:
        return _resize(render(proxy, entry.spec), size), ""
    except Exception as exc:  # noqa: BLE001 - one broken entry must not stop the gallery
        placeholder = np.empty((size, size, 3), dtype=np.uint8)
        placeholder[:, :] = PLACEHOLDER_COLOR
        return placeholder, f"{entry.id}: {exc}"


def _compose_sheet(cells: list[GalleryCell], size: int, columns: int) -> RGB8:
    """Paste the cells into one labelled contact sheet, columns per row."""
    rows = max(1, (len(cells) + columns - 1) // columns)
    sheet = PILImage.new("RGB", (columns * size, rows * (size + LABEL_HEIGHT)),
                         SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for index, cell in enumerate(cells):
        x = (index % columns) * size
        y = (index // columns) * (size + LABEL_HEIGHT)
        draw.text((x + 4, y + 4), cell.label, fill=LABEL_COLOR)
        sheet.paste(color.to_pil(cell.rgb8), (x, y + LABEL_HEIGHT))
    return np.ascontiguousarray(np.asarray(sheet, dtype=np.uint8))


def render_gallery(source: Image | None = None, *, cell_size: int = CELL_SIZE,
                   columns: int = COLUMNS, palette: str = DEFAULT_PALETTE) -> GallerySheet:
    """Render every registered algorithm and renderer on one image, side by side."""
    if cell_size < 8:
        raise ValueError(f"cell_size must be >= 8, got {cell_size}")
    proxy = square_proxy(reference_image() if source is None else source, cell_size)
    cells: list[GalleryCell] = []
    warnings: list[str] = []
    for entry in gallery_entries(palette=palette):
        rgb8, problem = _render_cell(entry, proxy, cell_size)
        if problem:
            warnings.append(problem)
        cells.append(GalleryCell(entry.id, entry.label, entry.kind, rgb8))
    image = _compose_sheet(cells, cell_size, max(1, int(columns)))
    return GallerySheet(cells, image, warnings)


def gallery_png_bytes(sheet: GallerySheet) -> bytes:
    """Encode the sheet as one PNG, downscaling until it fits the 4 MB budget."""
    image = color.to_pil(sheet.image)
    while True:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        payload = buffer.getvalue()
        if len(payload) <= MAX_GALLERY_BYTES or min(image.size) <= MIN_SHEET_SIDE:
            return payload
        image = image.resize((max(MIN_SHEET_SIDE, image.width * 3 // 4),
                              max(MIN_SHEET_SIDE, image.height * 3 // 4)),
                             PILImage.Resampling.BOX)


def save_gallery(path: str | Path, source: Image | None = None, *,
                 cell_size: int = CELL_SIZE, columns: int = COLUMNS,
                 palette: str = DEFAULT_PALETTE) -> Path:
    """Render the gallery and write it as a single PNG under 4 MB, returning its path."""
    sheet = render_gallery(source, cell_size=cell_size, columns=columns, palette=palette)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gallery_png_bytes(sheet))
    return target


@dataclass(frozen=True)
class InterchangeResult:
    """One cross-app load and render: the preset, its renderer, the image, the warnings."""

    preset: Preset
    renderer: str
    rgb8: RGB8
    warnings: list[str]


def load_for_app(path: str | Path, app: str, *,
                 available: frozenset[str] | set[str] | None = None) -> Preset:
    """Load a preset in app's context; an app mismatch is a warning, never an error (§6)."""
    preset = load_preset(path, app=app, available=available)
    if preset.app != app:
        preset.warnings.append(f"preset written for app {preset.app!r}; loaded in app {app!r}")
    return preset


def render_for_app(source: Image, preset: Preset | str | Path, app: str, *,
                   available: frozenset[str] | set[str] | None = None,
                   max_side: int | None = None) -> InterchangeResult:
    """Load preset for app when needed, then render it through the core pipeline."""
    if not isinstance(preset, Preset):
        preset = load_for_app(preset, app, available=available)
    spec = to_pipeline_spec(preset)
    rgb8 = render(source, spec, max_side=max_side)
    return InterchangeResult(preset, spec.renderer, rgb8, list(preset.warnings))


def starter_preset_dir() -> Path:
    """Return the suite starter preset directory: presets/starter next to the package."""
    return Path(__file__).resolve().parents[1] / "presets" / STARTER_DIR_NAME


def starter_presets(directory: str | Path | None = None) -> list[Path]:
    """Return the starter preset files of directory, sorted by name."""
    base = Path(directory) if directory is not None else starter_preset_dir()
    return sorted(path for path in base.glob("*.json") if path.is_file())


__all__ = [
    "CELL_SIZE",
    "COLUMNS",
    "DEFAULT_PALETTE",
    "MAX_GALLERY_BYTES",
    "REFERENCE_SIDE",
    "GalleryCell",
    "GalleryEntry",
    "GallerySheet",
    "InterchangeResult",
    "gallery_entries",
    "gallery_png_bytes",
    "load_for_app",
    "reference_image",
    "render_for_app",
    "render_gallery",
    "save_gallery",
    "square_proxy",
    "starter_preset_dir",
    "starter_presets",
]
