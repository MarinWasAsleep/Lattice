"""Tests for the shared N-image loop and its GIF/APNG exports (card L-LOOP)."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

import lattice_core.animation as animation
import lattice_core.dither  # noqa: F401  (registers the algorithms)
import lattice_core.effects  # noqa: F401  (registers the effects)
from lattice_core.animation import (
    AXES,
    export_apng,
    export_gif,
    render_loop,
    render_sequence,
)
from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, render
from lattice_core.types import RGB8, Image

BW = ["#000000", "#FFFFFF"]


def _spec(**overrides: object) -> PipelineSpec:
    """Return a deterministic two-colour spec with the requested overrides."""
    base: dict = {
        "algorithm_id": "bayer_4",
        "palette": PaletteSpec(source="custom", colors=BW),
    }
    base.update(overrides)
    return PipelineSpec(**base)


def _feedback(seed: int = 7) -> PipelineSpec:
    """Return a spec whose post-effect feedback is seeded and spatially displaced."""
    effect = EffectInstance(
        "feedback",
        {"decay": 0.5, "transform": "displace", "amount": 4.0, "iterations": 1},
    )
    return _spec(seed=seed, post_effects=[effect])


def _src(size: int = 16) -> Image:
    """Return a grey image with a bright band, so horizontal shifts are visible."""
    img = np.full((size, size, 3), 0.25, dtype=np.float32)
    img[:, :4] = 0.75
    return img


def _gradient(size: int = 16) -> Image:
    """Return a horizontal ramp whose columns are all distinct."""
    ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)
    return np.ascontiguousarray(np.broadcast_to(ramp[None, :, None], (size, size, 3)))


def _rgb_frames(count: int = 5) -> list[RGB8]:
    """Return count distinct uint8 frames, ready for an image writer."""
    frames = []
    for index in range(count):
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        frame[:, index * 3 : index * 3 + 3] = 255
        frames.append(frame)
    return frames


def _with_iterations(spec: PipelineSpec, value: int) -> PipelineSpec:
    """Build the reference spec used to check the iterations axis independently."""
    effects = [
        replace(effect, params={**effect.params, "iterations": value})
        if effect.effect_id == "feedback"
        else effect
        for effect in spec.post_effects
    ]
    return replace(spec, post_effects=effects)


def test_render_sequence_is_the_moved_dither_function() -> None:
    """The core function reproduces the Dither 1.1 export on the same input."""
    from lattice_dither.core.animation import render_sequence as dither_sequence

    frames = [_src() for _ in range(3)]
    for core, dither in zip(
        render_sequence(frames, _spec()), dither_sequence(frames, _spec()), strict=True
    ):
        assert np.array_equal(core, dither)
    assert render_sequence([], _spec()) == []


def test_seed_axis_changes_only_seed() -> None:
    """Each frame equals an independent render whose seed alone was incremented."""
    spec = _feedback()
    out = render_loop(_src(), spec, count=4, axis="seed")
    assert len(out) == 4
    for index, frame in enumerate(out):
        expected = render(_src(), replace(spec, seed=spec.seed + index))
        assert np.array_equal(frame, expected)
    assert any(not np.array_equal(out[0], other) for other in out[1:])


def test_iterations_axis_changes_only_feedback_iterations() -> None:
    """Each frame equals a render whose feedback iteration count alone was incremented."""
    spec = _feedback()
    out = render_loop(_src(), spec, count=4, axis="iterations")
    assert len(out) == 4
    for index, frame in enumerate(out):
        expected = render(_src(), _with_iterations(spec, 1 + index))
        assert np.array_equal(frame, expected)
    assert any(not np.array_equal(out[0], other) for other in out[1:])


def test_iterations_axis_saturates_at_eight() -> None:
    """Feedback iterations never exceed the contract maximum of eight."""
    spec = _feedback()
    out = render_loop(_src(), spec, count=11, axis="iterations")
    assert len(out) == 11
    assert all(np.array_equal(out[7], frame) for frame in out[8:])


def test_offset_axis_changes_only_a_horizontal_shift() -> None:
    """Each frame equals a render of the source rolled by the frame index."""
    spec = _spec()
    src = _gradient()
    out = render_loop(src, spec, count=4, axis="offset")
    for index, frame in enumerate(out):
        assert np.array_equal(frame, render(np.roll(src, index, axis=1), spec))
    assert not np.array_equal(out[0], out[1])


def test_offset_axis_honours_the_step() -> None:
    """The step multiplies the horizontal shift without touching the spec."""
    spec = _spec()
    src = _gradient()
    out = render_loop(src, spec, count=3, axis="offset", step=2)
    for index, frame in enumerate(out):
        assert np.array_equal(frame, render(np.roll(src, 2 * index, axis=1), spec))


def test_loop_is_deterministic_and_does_not_mutate_its_inputs() -> None:
    """Two identical calls render identical bytes and leave spec and src untouched."""
    spec = _feedback()
    src = _src()
    first = render_loop(src, spec, count=4, axis="seed")
    second = render_loop(src, spec, count=4, axis="seed")
    assert all(np.array_equal(a, b) for a, b in zip(first, second, strict=True))
    assert spec.seed == 7
    assert spec.post_effects[0].params["iterations"] == 1
    assert np.array_equal(src, _src())


def test_unstable_loop_resolves_the_palette_per_frame(monkeypatch) -> None:
    """stable=False re-resolves the palette once for every frame."""
    calls: list[int] = []
    real = animation.resolve_palette

    def counting(spec, img):
        calls.append(1)
        return real(spec, img)

    monkeypatch.setattr(animation, "resolve_palette", counting)
    render_loop(_src(), _spec(), count=3, axis="offset", stable=False)
    assert len(calls) == 3


def test_unknown_axis_and_negative_count_are_rejected() -> None:
    """An undeclared axis and a negative count raise ValueError; zero is empty."""
    with pytest.raises(ValueError, match="axis"):
        render_loop(_src(), _spec(), count=3, axis="time")
    with pytest.raises(ValueError, match="count"):
        render_loop(_src(), _spec(), count=-1)
    assert render_loop(_src(), _spec(), count=0) == []


def test_axis_constants_are_the_three_declared_axes() -> None:
    """Only seed, offset and feedback iterations are variation axes."""
    assert AXES == ("seed", "offset", "iterations")


def test_gif_has_exactly_n_frames(tmp_path: Path) -> None:
    """A GIF written from N frames reopens with exactly N frames."""
    target = tmp_path / "clip.gif"
    export_gif(_rgb_frames(), target, fps=10)
    with PILImage.open(target) as written:
        assert written.format == "GIF"
        assert written.n_frames == 5
        assert written.info["duration"] == 100


def test_apng_has_exactly_n_frames(tmp_path: Path) -> None:
    """An APNG written from N frames reopens with exactly N frames."""
    target = tmp_path / "clip.png"
    export_apng(_rgb_frames(), target, fps=10)
    with PILImage.open(target) as written:
        assert written.format == "PNG"
        assert written.n_frames == 5
        assert written.info["duration"] == 100


@pytest.mark.parametrize("writer", [export_gif, export_apng])
def test_exports_honour_the_loop_count(tmp_path: Path, writer) -> None:
    """Both writers pass the loop count into the file."""
    target = tmp_path / "clip"
    writer(_rgb_frames(3), target, fps=10, loop=3)
    with PILImage.open(target) as written:
        assert written.info["loop"] == 3
        assert written.n_frames == 3


@pytest.mark.parametrize("writer", [export_gif, export_apng])
def test_exports_reject_an_empty_sequence(tmp_path: Path, writer) -> None:
    """An empty sequence is rejected rather than written as a broken file."""
    with pytest.raises(ValueError, match="empty"):
        writer([], tmp_path / "clip", fps=10)


@pytest.mark.parametrize("writer", [export_gif, export_apng])
def test_exports_reject_a_bad_fps(tmp_path: Path, writer) -> None:
    """An fps below one is rejected by both writers."""
    with pytest.raises(ValueError, match="fps"):
        writer(_rgb_frames(3), tmp_path / "clip", fps=0)


@pytest.mark.parametrize("fmt,writer,expected", [("gif", export_gif, "GIF"),
                                                ("apng", export_apng, "PNG")])
def test_loop_frames_are_writable_to_both_formats(
    tmp_path: Path, fmt: str, writer, expected: str
) -> None:
    """Rendered loop frames survive a full render-then-export round trip."""
    frames = render_loop(_src(), _feedback(), count=3, axis="iterations")
    target = tmp_path / f"loop.{fmt}"
    writer(frames, target, fps=12)
    with PILImage.open(target) as written:
        assert written.format == expected
        assert written.n_frames == 3


def test_animation_module_imports_no_application() -> None:
    """lattice_core/animation.py imports no application module."""
    tree = ast.parse(Path(animation.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots & {"lattice_dither", "lattice_glyph", "lattice_glitch"}


def test_dither_video_exports_are_left_intact(tmp_path: Path) -> None:
    """The Dither 1.1 export path still writes a GIF and owns the video writer."""
    from lattice_dither.core.animation import render_sequence as dither_sequence
    from lattice_dither.export.video import export_gif as dither_gif
    from lattice_dither.export.video import export_video as dither_video

    frames = _rgb_frames(3)
    target = tmp_path / "dither.gif"
    dither_gif(frames, target, fps=10)
    with PILImage.open(target) as written:
        assert written.n_frames == 3
    assert callable(dither_video)
    assert len(dither_sequence([_src()], _spec())) == 1


def test_render_fn_renders_every_frame_without_the_pipeline(monkeypatch) -> None:
    """An injected render_fn produces every frame; the 1.0 pipeline path is bypassed."""
    def forbidden(*args, **kwargs):
        raise AssertionError("the injected loop must not ride the pipeline render path")

    monkeypatch.setattr(animation, "render_with_palette", forbidden)
    monkeypatch.setattr(animation, "resolve_palette", forbidden)
    calls: list[tuple[Image, PipelineSpec]] = []

    def render_fn(image: Image, spec: PipelineSpec) -> RGB8:
        calls.append((image, spec))
        return np.full((16, 16, 3), len(calls), dtype=np.uint8)

    out = render_loop(_src(), _feedback(), count=4, axis="seed", render_fn=render_fn)
    assert len(calls) == 4 and len(out) == 4
    assert [int(frame[0, 0, 0]) for frame in out] == [1, 2, 3, 4]


@pytest.mark.parametrize("axis", AXES)
def test_render_fn_frame_zero_gets_the_unvaried_inputs(axis: str) -> None:
    """On every axis the first injected call receives the original image and spec values."""
    src = _src()
    seen: list[tuple[Image, PipelineSpec]] = []

    def render_fn(image: Image, spec: PipelineSpec) -> RGB8:
        seen.append((image, spec))
        return np.zeros((16, 16, 3), dtype=np.uint8)

    render_loop(src, _feedback(), count=3, axis=axis, render_fn=render_fn)
    image0, spec0 = seen[0]
    assert np.array_equal(image0, src)
    assert spec0.seed == 7
    assert spec0.post_effects[0].params["iterations"] == 1


@pytest.mark.parametrize("axis", AXES)
def test_render_fn_receives_only_the_varied_axis(axis: str) -> None:
    """The injected pairs vary exactly the declared axis, the step included."""
    src = _gradient()
    seen: list[tuple[Image, PipelineSpec]] = []

    def render_fn(image: Image, spec: PipelineSpec) -> RGB8:
        seen.append((image, spec))
        return np.zeros((16, 16, 3), dtype=np.uint8)

    render_loop(src, _feedback(), count=4, axis=axis, step=2, render_fn=render_fn)
    assert len(seen) == 4
    for index, (image, spec) in enumerate(seen):
        if axis == "seed":
            assert spec.seed == 7 + 2 * index
            assert np.array_equal(image, src)
        elif axis == "offset":
            assert np.array_equal(image, np.roll(src, 2 * index, axis=1))
            assert spec.seed == 7
        else:
            assert spec.post_effects[0].params["iterations"] == min(8, 1 + 2 * index)
            assert np.array_equal(image, src)


def test_render_fn_keeps_validation_and_the_empty_count() -> None:
    """Axis and count validation still apply with an injected renderer; zero stays empty."""
    def render_fn(image: Image, spec: PipelineSpec) -> RGB8:
        return np.zeros((16, 16, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="axis"):
        render_loop(_src(), _spec(), count=3, axis="time", render_fn=render_fn)
    with pytest.raises(ValueError, match="count"):
        render_loop(_src(), _spec(), count=-1, render_fn=render_fn)
    assert render_loop(_src(), _spec(), count=0, render_fn=render_fn) == []


def test_render_fn_none_keeps_the_pipeline_path() -> None:
    """The default (no injection) stays byte-for-byte the L-LOOP pipeline behaviour."""
    first = render_loop(_src(), _feedback(), count=3, axis="seed")
    second = render_loop(_src(), _feedback(), count=3, axis="seed", render_fn=None)
    assert all(np.array_equal(a, b) for a, b in zip(first, second, strict=True))


@pytest.mark.parametrize("writer", [export_gif, export_apng])
def test_writers_keep_unchanged_regions_across_frames(tmp_path: Path, writer) -> None:
    """A frame that changes only a small spot keeps the rest of the image intact."""
    base = np.zeros((32, 32, 3), dtype=np.uint8)
    base[:, :, 1] = 100
    base[:, :, 2] = np.linspace(0, 255, 32, dtype=np.uint8)[None, :]
    frames = []
    for index in range(4):
        frame = base.copy()
        frame[4 + index * 5 : 7 + index * 5, 4:7] = 255
        frames.append(frame)
    target = tmp_path / "spot"
    writer(frames, target, fps=12)
    with PILImage.open(target) as written:
        assert written.n_frames == 4
        for index in range(4):
            written.seek(index)
            assert np.array_equal(np.asarray(written.convert("RGB")), frames[index])
