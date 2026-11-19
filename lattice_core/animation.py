"""Shared N-image loop: render N frames varying one axis, then export GIF or APNG.

``render_sequence`` is the 1.1 animation export moved into the core without behavioural
change (§21). ``render_loop`` generalises it: it renders N frames from one source while
varying only the declared axis — ``seed``, ``offset`` (a horizontal pixel shift),
``iterations`` (the feedback buffer iteration count) or ``param`` (one numeric effect
parameter walked A->B->A) — and keeps everything else fixed.
Stable mode resolves the palette once, on the first frame, so colours cannot flicker.
An injectable ``render_fn`` lets an application render every varied pair on its own
path (masks, streams, locks) instead of the pipeline's (L25). On the seed axis an
optional ``locked_streams`` mapping freezes the named modules while the others follow
the varied seed; it rides on a spec subclass so the caller's render path is unchanged.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_core.pipeline import (
    EffectInstance,
    PipelineSpec,
    prepare_image,
    render_with_palette,
    resolve_palette,
)
from lattice_core.seed import module_seed
from lattice_core.types import RGB8, Image

AXES = ("seed", "offset", "iterations", "param")
MAX_ITERATIONS = 8
CURVES = ("sin", "linear")


@dataclass
class StreamedSpec(PipelineSpec):
    """A PipelineSpec carrying the session-only streams of one loop frame.

    The streams travel on the spec the caller's ``render_fn`` already receives, so
    locks never become a second render path and are never written into a preset.
    """

    streams: tuple[int, ...] = ()


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
    locked_streams: Mapping[int, int] | None = None,
    param: str | None = None,
    from_value: float | None = None,
    to_value: float | None = None,
    curve: str = "sin",
) -> list[RGB8]:
    """Render count frames from src, varying only axis; other spec fields stay fixed.

    render_fn, when given, renders each varied (image, spec) pair itself, so the
    caller's own path (masks, streams, locks) applies and stable is ignored.
    On the seed axis, locked_streams maps module indices to frozen stream seeds:
    those modules keep their stream on every frame, unlocked ones follow the seed.
    On the param axis, param="<effect>.<key>" walks one numeric parameter from
    from_value to to_value and back (curve "sin" or "linear"), so frame[count-1]
    equals frame[0]; the other axes ignore the four param keywords.
    """
    if axis not in AXES:
        raise ValueError(f"unknown animation axis: {axis!r}, expected one of {AXES}")
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    shift = int(step)
    if axis == "param":
        pairs = _param_pairs(src, spec, count, param, from_value, to_value, curve)
    else:
        base = _iterations_base(spec) if axis == "iterations" else 0
        pairs = [
            _varied(src, spec, axis, index, shift, base) for index in range(count)
        ]
    if axis == "seed" and spec.post_effects:
        module_count = len(spec.post_effects)
        pairs = [
            (
                image,
                _with_streams(
                    varied,
                    _frame_streams(int(spec.seed) + shift * index, module_count,
                                   locked_streams or {}),
                ),
            )
            for index, (image, varied) in enumerate(pairs)
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


def _frame_streams(
    seed: int, module_count: int, locked: Mapping[int, int]
) -> tuple[int, ...]:
    """Return one frame's streams: frozen where locked, seed-derived otherwise."""
    return tuple(locked.get(module, module_seed(seed, module)) for module in range(module_count))


def _with_streams(spec: PipelineSpec, streams: tuple[int, ...]) -> StreamedSpec:
    """Copy spec into a StreamedSpec carrying streams, preserving every spec field."""
    data = {field.name: getattr(spec, field.name) for field in fields(spec)}
    return StreamedSpec(**data, streams=streams)


def _param_pairs(
    src: Image,
    spec: PipelineSpec,
    count: int,
    param: str | None,
    from_value: float | None,
    to_value: float | None,
    curve: str,
) -> list[tuple[Image, PipelineSpec]]:
    """Validate the param axis, then build one (src, varied spec) pair per frame."""
    if curve not in CURVES:
        raise ValueError(f"unknown param curve: {curve!r}, expected one of {CURVES}")
    if not isinstance(param, str) or param.count(".") != 1 or not all(param.split(".")):
        raise ValueError(f"param must be '<effect>.<key>', got {param!r}")
    effect_id, key = param.split(".")
    start = _finite("from_value", from_value)
    end = _finite("to_value", to_value)
    target = next(
        (e for e in (*spec.pre_effects, *spec.post_effects) if e.effect_id == effect_id),
        None,
    )
    if target is None:
        raise ValueError(f"param effect {effect_id!r} is not in the spec")
    current = target.params.get(key)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise ValueError(f"param {param!r} must hold a number in the spec, got {current!r}")
    return [
        (src, _with_param(spec, effect_id, key, _param_value(start, end, curve, i, count)))
        for i in range(count)
    ]


def _finite(name: str, value: float | None) -> float:
    """Return value as a float, rejecting non-numbers and non-finite bounds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _param_value(start: float, end: float, curve: str, index: int, count: int) -> float:
    """Return frame index's A->B->A value: a full cosine period, or a triangle walk."""
    if count <= 1:
        return start
    t = index / (count - 1)
    if curve == "sin":
        phase = (1.0 - math.cos(2.0 * math.pi * t)) / 2.0
    else:
        phase = 2.0 * t if t <= 0.5 else 2.0 * (1.0 - t)
    return start + (end - start) * phase


def _with_param(spec: PipelineSpec, effect_id: str, key: str, value: float) -> PipelineSpec:
    """Return spec with key of the first effect_id instance set to value."""
    def walk(effects: list[EffectInstance]) -> tuple[list[EffectInstance], bool]:
        out: list[EffectInstance] = []
        done = False
        for effect in effects:
            if not done and effect.effect_id == effect_id:
                out.append(replace(effect, params={**effect.params, key: value}))
                done = True
            else:
                out.append(effect)
        return out, done

    pre, done = walk(spec.pre_effects)
    post = spec.post_effects if done else walk(spec.post_effects)[0]
    return replace(spec, pre_effects=pre, post_effects=post)


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
