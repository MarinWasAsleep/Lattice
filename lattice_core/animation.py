"""Shared N-image loop: render N frames varying one axis, then export GIF or APNG.

``render_sequence`` is the 1.1 animation export moved into the core without behavioural
change (§21). ``render_loop`` generalises it: it renders N frames from one source while
varying only the declared axis — ``seed``, ``offset`` (a horizontal pixel shift) or
``iterations`` (the feedback buffer iteration count) — and keeps everything else fixed.
Stable mode resolves the palette once, on the first frame, so colours cannot flicker.
An injectable ``render_fn`` lets an application render every varied pair on its own
path (masks, streams, locks) instead of the pipeline's (L25).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_core.pipeline import (
    PipelineSpec,
    prepare_image,
    render_with_palette,
    resolve_palette,
)
from lattice_core.types import RGB8, Image

AXES = ("seed", "offset", "iterations")
MAX_ITERATIONS = 8


def render_sequence(
    frames: list[Image], spec: PipelineSpec, *, stable: bool = True
) -> list[RGB8]:
    """Render frames through spec, resolving the palette once when stable."""
    return _render(frames, [spec] * len(frames), stable)


def render_loop(
    src: Image,
    spec: PipelineSpec,
    *,
    count: int,
    axis: str = "seed",
    stable: bool = True,
    step: int = 1,
    render_fn: Callable[[Image, PipelineSpec], RGB8] | None = None,
) -> list[RGB8]:
    """Render count frames from src, varying only axis; other spec fields stay fixed.

    render_fn, when given, renders each varied (image, spec) pair itself, so the
    caller's own path (masks, streams, locks) applies and stable is ignored.
    """
    if axis not in AXES:
        raise ValueError(f"unknown animation axis: {axis!r}, expected one of {AXES}")
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    shift = int(step)
    base = _iterations_base(spec) if axis == "iterations" else 0
    pairs = [
        _varied(src, spec, axis, index, shift, base) for index in range(count)
    ]
    if render_fn is not None:
        return [render_fn(image, varied) for image, varied in pairs]
    return _render([pair[0] for pair in pairs], [pair[1] for pair in pairs], stable)


def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
    """Write frames to path as an animated GIF, using Pillow only."""
    duration = _check(frames, fps)
    images = [_pil(frame) for frame in frames]
    images[0].save(
        Path(path),
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=int(loop),
        optimize=False,
    )


def export_apng(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
    """Write frames to path as an animated APNG, using Pillow only.

    Disposal is NONE: Pillow delta-encodes the changed region of each frame, so
    disposing to background would blank everything the next frame does not repaint.
    """
    duration = _check(frames, fps)
    images = [_pil(frame) for frame in frames]
    images[0].save(
        Path(path),
        format="PNG",
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=int(loop),
        disposal=0,
    )


def _render(frames: list[Image], specs: list[PipelineSpec], stable: bool) -> list[RGB8]:
    """Render frames against parallel specs, pinning one palette when stable."""
    if not frames:
        return []
    if stable:
        palette = resolve_palette(specs[0].palette, prepare_image(frames[0], specs[0]))
        return [
            render_with_palette(frame, spec, palette)
            for frame, spec in zip(frames, specs, strict=True)
        ]
    return [
        render_with_palette(frame, spec, resolve_palette(spec.palette, prepare_image(frame, spec)))
        for frame, spec in zip(frames, specs, strict=True)
    ]


def _varied(
    src: Image, spec: PipelineSpec, axis: str, index: int, step: int, base: int
) -> tuple[Image, PipelineSpec]:
    """Return the source and spec of frame index with only axis changed."""
    if axis == "seed":
        return src, replace(spec, seed=int(spec.seed) + step * index)
    if axis == "offset":
        return np.roll(src, step * index, axis=1), spec
    return src, _with_iterations(spec, min(MAX_ITERATIONS, base + step * index))


def _iterations_base(spec: PipelineSpec) -> int:
    """Return the iteration count declared by the first enabled feedback effect."""
    for effect in (*spec.pre_effects, *spec.post_effects):
        if effect.effect_id == "feedback" and effect.enabled:
            return max(1, int(effect.params.get("iterations", 1)))
    return 1


def _with_iterations(spec: PipelineSpec, value: int) -> PipelineSpec:
    """Return spec with every enabled feedback effect set to value iterations."""
    def bump(effect):
        if effect.effect_id != "feedback" or not effect.enabled:
            return effect
        return replace(effect, params={**effect.params, "iterations": value})

    return replace(
        spec,
        pre_effects=[bump(effect) for effect in spec.pre_effects],
        post_effects=[bump(effect) for effect in spec.post_effects],
    )


def _check(frames: list[RGB8], fps: int) -> int:
    """Validate the sequence and return the frame duration in milliseconds."""
    if not frames:
        raise ValueError("cannot export an empty sequence")
    if int(fps) < 1:
        raise ValueError(f"fps must be >= 1, got {fps}")
    return int(round(1000.0 / int(fps)))


def _pil(frame: RGB8) -> PILImage.Image:
    """Return one frame as a Pillow RGB image."""
    return PILImage.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB")
