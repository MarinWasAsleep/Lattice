"""The single render path of Lattice Glitch: load, stack render, export bytes (G9, §8).

Every entry point goes through this module. ``render_rgb8`` runs the core pipeline's
steps 1 to 5 (``prepare_image``), then applies the effect stack itself so the §18
per-module seed streams and masks are honoured — ``pipeline.render`` keeps the 1.0
seeding rule and knows no masks, so the glitch chain cannot ride on it. The CLI and
the GUI export call the same function with the same inputs, so their PNG bytes are
identical by construction (G9). Glitch renders continuous images only: algorithm and
palette stay null (§5 S1).
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

import lattice.effects  # noqa: F401  (registers every effect a preset may name)
from lattice import color, mask
from lattice import pipeline as _pipeline
from lattice.pipeline import PipelineSpec
from lattice.preset import Preset, to_pipeline_spec
from lattice.registry import get_effect, resolve_params
from lattice.seed import SeedController, module_seed
from lattice.types import RGB8, Image

FORMATS: tuple[str, ...] = ("png",)
SUFFIXES: dict[str, str] = {"png": ".png"}


class DocumentError(Exception):
    """A typed failure of the document path: unreadable source, or an impossible render."""


@dataclass(frozen=True)
class Export:
    """One written file: where it went, in which format, its size and its warnings."""

    path: Path
    fmt: str
    size: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderContext:
    """The session side of one glitch render: mask ids, mask planes and stream seeds.

    ``streams`` carries one seed per stack position (``SeedController.module_seed_for``),
    so a worker thread renders an immutable snapshot of the session's locks; when it is
    empty the render falls back on ``controller`` or on a fresh ``SeedController(seed)``.
    """

    mask_ids: tuple[str | None, ...] = ()
    masks: Mapping[str, Image] = field(default_factory=dict)
    streams: tuple[int, ...] = ()
    # The seed these streams were derived from. A caller that steps `spec.seed` (the param
    # axis with reseed) must not be answered from a snapshot built on the old seed.
    seed: int | None = None


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


def fit_mask(plane: Image, shape: tuple[int, int]) -> Image:
    """Resample a mask plane to shape: area-average down, bilinear up, exact when equal."""
    data = np.ascontiguousarray(np.asarray(plane, dtype=np.float32))
    if data.shape == shape:
        return data
    pil = PILImage.fromarray(data, mode="F")
    resample = PILImage.Resampling.BOX if data.size >= shape[0] * shape[1] \
        else PILImage.Resampling.BILINEAR
    resized = pil.resize((shape[1], shape[0]), resample)
    return np.ascontiguousarray(np.clip(np.asarray(resized, dtype=np.float32), 0.0, 1.0))


def _module_rng(position: int, context: RenderContext,
                controller: SeedController, spec: PipelineSpec | None = None,
                ) -> np.random.Generator:
    """Return the generator of one stack position: frame streams, snapshot, controller.

    A loop frame arrives as a ``StreamedSpec`` carrying its own streams (L26): those
    win, which is how unlocked modules vary from frame to frame while a locked one
    keeps the stream the caller pinned for it. Without them the session snapshot
    (``context.streams``) applies, so every existing path is unchanged.
    """
    frame_streams = tuple(getattr(spec, "streams", ()) or ())
    if frame_streams:
        # A loop frame owns its streams for the whole stack: that is what makes the
        # seed axis vary every unlocked module while a locked one keeps its stream.
        return np.random.default_rng(frame_streams[position % len(frame_streams)])
    # The spec's own seed must beat the session snapshot. `context_of_preset` pins a stream
    # per slot from the preset seed, so when the caller steps `spec.seed` (the param axis
    # with reseed) the snapshot would silently answer with the OLD seed and the frames came
    # out byte-identical (measured: md5 equal with and without --reseed).
    if spec is not None and context.seed is not None and int(spec.seed) != int(context.seed):
        return np.random.default_rng(module_seed(int(spec.seed), position))
    if position < len(context.streams):
        return np.random.default_rng(context.streams[position])
    return controller.rng(position)


def _render(image: Image, spec: PipelineSpec, context: RenderContext,
            controller: SeedController | None) -> RGB8:
    """Run steps 1 to 5, then the masked, per-module-seeded effect stack."""
    if spec.algorithm_id is not None or spec.palette is not None:
        raise DocumentError(
            "glitch renders continuous images: algorithm and palette must both be null"
        )
    work = _pipeline.prepare_image(image, spec)
    controller = controller if controller is not None else SeedController(spec.seed)
    for position, instance in enumerate(spec.post_effects):
        if not instance.enabled:
            continue
        info = get_effect(instance.effect_id)
        params = resolve_params(info.params, instance.params)
        rng = _module_rng(position, context, controller, spec)
        before = work
        out = np.ascontiguousarray(
            np.clip(info.fn(work, params, rng), 0.0, 1.0), dtype=np.float32
        )
        mask_id = context.mask_ids[position] if position < len(context.mask_ids) else None
        if mask_id is not None:
            if mask_id not in context.masks:
                raise DocumentError(f"mask {mask_id!r} is not in the document")
            plane = fit_mask(context.masks[mask_id], work.shape[:2])
            out = mask.apply(before, out, mask=plane)
        work = out
    return color.to_rgb8(work)


def render_rgb8(image: Image, spec: PipelineSpec, *, context: RenderContext | None = None,
                controller: SeedController | None = None) -> RGB8:
    """Render image through the glitch path, raising DocumentError on any failure."""
    try:
        return _render(image, spec, context or RenderContext(), controller)
    except DocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 - every render failure is a render error (§8)
        raise DocumentError(f"render failed: {exc}") from None


def _entry_stream(entry: dict, seed: int, position: int) -> int:
    """Return the frozen stream of one effect entry, or the seed-derived default."""
    if "seed" not in entry:
        return module_seed(seed, position)
    value = entry["seed"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"effect stream seed must be an integer, got {value!r}")
    return value


def context_of_preset(preset: Preset) -> RenderContext:
    """Return the mask ids, planes and per-slot stream seeds a v3 preset carries."""
    post = [entry for entry in preset.effects if entry.get("stage", "post") != "pre"]
    mask_ids = tuple(entry.get("mask") for entry in post)
    try:
        streams = tuple(_entry_stream(entry, preset.seed, position)
                        for position, entry in enumerate(post))
        planes = mask.resolve_masks(preset.masks)
    except (OSError, ValueError) as exc:
        raise DocumentError(f"cannot resolve the preset context: {exc}") from None
    return RenderContext(mask_ids=mask_ids, masks=planes, streams=streams,
                         seed=int(preset.seed))


def render_preset(image: Image, preset: Preset) -> RGB8:
    """Render image with a parsed v3 preset: its seed, its stack and its masks."""
    return render_rgb8(image, to_pipeline_spec(preset), context=context_of_preset(preset))


def png_bytes(rgb8: RGB8) -> bytes:
    """Return rgb8 encoded as a PNG file byte for byte as the GUI export writes it."""
    buffer = io.BytesIO()
    color.to_pil(rgb8).save(buffer, format="PNG")
    return buffer.getvalue()


def export_bytes(image: Image, preset: Preset, fmt: str = "png") -> tuple[bytes, list[str]]:
    """Return the encoded output of preset in fmt, with the warnings of that export."""
    if fmt not in FORMATS:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return png_bytes(render_preset(image, preset)), []


def target_path(path: str | Path, fmt: str) -> Path:
    """Return path with fmt's suffix appended when it carries none of its own."""
    target = Path(path)
    if target.suffix:
        return target
    if fmt not in SUFFIXES:
        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return target.with_name(target.name + SUFFIXES[fmt])


def write_render(image: Image, preset: Preset, path: str | Path, fmt: str = "png") -> Export:
    """Render preset and write it to path in fmt, creating the parent directories."""
    payload, warnings = export_bytes(image, preset, fmt)
    target = target_path(path, fmt)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    except OSError as exc:
        raise DocumentError(f"cannot write {target}: {exc}") from None
    return Export(path=target, fmt=fmt, size=len(payload), warnings=warnings)


def format_of(path: str | Path) -> str:
    """Return the export format named by path's suffix; a suffix outside FORMATS raises.

    A bare path (no suffix) still defaults to png, but a named suffix is a contract:
    writing PNG bytes into ``photo.jpg`` would lie about the file, so the caller hears
    a ``DocumentError`` naming the suffix instead of a silent fallback.
    """
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix and suffix not in FORMATS:
        raise DocumentError(
            f"cannot infer the format of {Path(path).name!r}: suffix '.{suffix}' is not"
            f" one of {', '.join(FORMATS)}"
        )
    return suffix if suffix in FORMATS else "png"


__all__ = [
    "FORMATS",
    "SUFFIXES",
    "DocumentError",
    "Export",
    "RenderContext",
    "context_of_preset",
    "export_bytes",
    "fit_mask",
    "format_of",
    "load_image",
    "png_bytes",
    "render_preset",
    "render_rgb8",
    "target_path",
    "write_render",
]
