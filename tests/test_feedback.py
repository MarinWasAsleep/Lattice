"""Tests for the feedback buffer effect (L13 / CONTRACT §12)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_core.effects.feedback import (
    _apply_transform,
    _grid,
    feedback,
    iterate,
    validate_params,
)
from lattice_core.registry import get_effect, resolve_params

EFFECT_ID = "feedback"
TRANSFORMS = ("identity", "translate", "rotate", "scale", "displace")
BLENDS = ("add", "max", "screen")
SEED = 11


def _image(seed: int = 7, shape: tuple[int, int] = (32, 32)) -> np.ndarray:
    """Return a deterministic non-constant float32 RGB image."""
    rng = np.random.default_rng(seed)
    noise = rng.random((*shape, 3), dtype=np.float32) * np.float32(0.5)
    ramp = np.linspace(0.0, 1.0, shape[1], dtype=np.float32)[None, :, None]
    ramp = np.repeat(ramp, shape[0], axis=0)
    return np.ascontiguousarray(np.clip(noise + ramp, 0.0, 1.0))


def _ramp(shape: tuple[int, int]) -> np.ndarray:
    """Return a horizontal ramp: every column a distinct brightness."""
    ramp = np.linspace(0.0, 1.0, shape[1], dtype=np.float32)[None, :, None]
    return np.ascontiguousarray(np.repeat(np.repeat(ramp, shape[0], 0), 3, -1))


def _corners(shape: tuple[int, int]) -> np.ndarray:
    """Return a frame with a bright block in each corner, so a pivot shows a signature."""
    frame = np.zeros((*shape, 3), dtype=np.float32)
    h, w = shape
    q = max(2, min(h, w) // 8)
    frame[:q, :q] = 1.0      # top-left
    frame[:q, -q:] = 0.6     # top-right
    frame[-q:, :q] = 0.3     # bottom-left
    frame[-q:, -q:] = 0.9    # bottom-right
    return frame


def _energy(frame: np.ndarray) -> dict[str, float]:
    """Return the mean brightness of each third, to see where the echo went."""
    h, w = frame.shape[:2]
    return {
        "top": float(frame[: h // 3].mean()),
        "bottom": float(frame[-h // 3 :].mean()),
        "left": float(frame[:, : w // 3].mean()),
        "right": float(frame[:, -w // 3 :].mean()),
    }


def _params(**overrides: object) -> dict:
    """Return a full feedback parameter dict with deterministic test defaults."""
    params: dict = {
        "decay": 0.5, "transform": "identity", "amount": 3.0, "iterations": 8, "blend": "add"
    }
    params.update(overrides)
    return params


def _run(
    img: np.ndarray,
    params: dict,
    seed: int = SEED,
    iterations: int | None = None,
) -> np.ndarray:
    """Run the effect, or a longer iterate, with a freshly seeded generator."""
    rng = np.random.default_rng(seed)
    if iterations is None:
        return feedback(img, params, rng)
    return iterate(img, params, rng, iterations=iterations)


def test_registration_and_params() -> None:
    """The effect is registered with the five documented options."""
    info = get_effect(EFFECT_ID)
    assert info.name == "Feedback Buffer"
    assert [spec.id for spec in info.params] == [
        "decay",
        "transform",
        "amount",
        "iterations",
        "blend",
        "origin",
        "direction",
        "mix",
    ]
    assert resolve_params(info.params, {}) == {
        "decay": 0.5,
        "transform": "identity",
        "amount": 2.0,
        "iterations": 1,
        "blend": "add",
        "origin": "center",
        "direction": 0.0,
        "mix": 1.0,
    }


@pytest.mark.parametrize("value", [1, 1.0, 1.01, 1.5, 2.0, 100.0])
def test_decay_at_or_above_one_raises_naming_the_value(value: object) -> None:
    """A decay of 1 or more is rejected and the message names the offending value."""
    with pytest.raises(ValueError) as excinfo:
        feedback(_image(), _params(decay=value), np.random.default_rng(SEED))
    assert str(float(value)) in str(excinfo.value) or str(value) in str(excinfo.value)


def test_validate_params_rejects_decay_one() -> None:
    """The public validator rejects decay >= 1 independently of the registered effect."""
    with pytest.raises(ValueError, match="1"):
        validate_params({"decay": 1.0})
    assert validate_params({"decay": 0.99})["decay"] == 0.99
    assert validate_params({"decay": -2.0})["decay"] == 0.0


def test_decay_below_one_is_accepted() -> None:
    """Decay values below 1, including 0.99, are accepted."""
    out = _run(_image(), _params(decay=0.99))
    assert np.isfinite(out).all()


@pytest.mark.parametrize("transform", TRANSFORMS)
@pytest.mark.parametrize("blend", BLENDS)
def test_200_iterations_stay_finite_and_in_range(transform: str, blend: str) -> None:
    """200 iterations on a fixed input give no NaN and no value outside [0, 1]."""
    out = _run(
        _image(),
        _params(transform=transform, blend=blend),
        iterations=200,
    )
    assert out.shape == (32, 32, 3)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


@pytest.mark.parametrize("transform", TRANSFORMS)
@pytest.mark.parametrize("blend", BLENDS)
def test_mean_converges_between_iterations_190_and_200(transform: str, blend: str) -> None:
    """The frame mean at iteration 190 differs from iteration 200 by less than 1e-3."""
    params = _params(transform=transform, blend=blend)
    mean_190 = float(_run(_image(), params, iterations=190).mean())
    mean_200 = float(_run(_image(), params, iterations=200).mean())
    assert abs(mean_200 - mean_190) < 1e-3, (transform, blend, mean_190, mean_200)


@pytest.mark.parametrize("transform", TRANSFORMS)
@pytest.mark.parametrize("blend", BLENDS)
def test_decay_zero_returns_the_input_unchanged(transform: str, blend: str) -> None:
    """With decay 0 the feedback term vanishes and the fixed input passes through."""
    img = _image()
    out = _run(img, _params(decay=0.0, transform=transform, blend=blend), iterations=8)
    assert np.array_equal(out, img)


def test_each_transform_produces_a_different_output() -> None:
    """On the same input, no two transforms give the same output."""
    img = _image()
    outputs = {
        name: _run(img, _params(transform=name), iterations=4) for name in TRANSFORMS
    }
    for index, first in enumerate(TRANSFORMS):
        for second in TRANSFORMS[index + 1 :]:
            assert not np.array_equal(outputs[first], outputs[second]), (first, second)


@pytest.mark.parametrize("transform", TRANSFORMS)
def test_same_seed_produces_identical_output_across_two_calls(transform: str) -> None:
    """Two calls with the same seed return bit-identical buffers."""
    img = _image()
    params = _params(transform=transform)
    first = _run(img, params, seed=SEED)
    second = _run(img, params, seed=SEED)
    assert np.array_equal(first, second)


def test_different_seed_changes_the_displace_output() -> None:
    """The seed drives the displace field, so a different seed gives a different buffer."""
    img = _image()
    params = _params(transform="displace")
    first = _run(img, params, seed=SEED)
    other = _run(img, params, seed=SEED + 1)
    assert not np.array_equal(first, other)


def test_transform_is_composable() -> None:
    """A sequence of transforms composes into a different operator than a single one."""
    img = _image()
    single = _run(img, _params(transform="translate"), iterations=4)
    composed = _run(img, _params(transform=("translate", "rotate")), iterations=4)
    joined = _run(img, _params(transform="translate+rotate"), iterations=4)
    assert not np.array_equal(single, composed)
    assert np.array_equal(composed, joined)


def test_blends_give_distinct_outputs() -> None:
    """add, max and screen combine the buffer and the input differently."""
    img = _image()
    outputs = {name: _run(img, _params(blend=name), iterations=4) for name in BLENDS}
    names = list(BLENDS)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            assert not np.array_equal(outputs[first], outputs[second]), (first, second)


def test_unknown_transform_and_blend_are_rejected() -> None:
    """Unknown transform and blend names raise ValueError."""
    with pytest.raises(ValueError, match="shear"):
        _run(_image(), _params(transform="shear"))
    with pytest.raises(ValueError, match="overlay"):
        _run(_image(), _params(blend="overlay"))


def test_invalid_choice_is_rejected_by_resolve_params() -> None:
    """The registered choice parameters reject values outside their enumerations."""
    info = get_effect(EFFECT_ID)
    with pytest.raises(ValueError):
        resolve_params(info.params, {"transform": "shear"})
    with pytest.raises(ValueError):
        resolve_params(info.params, {"blend": "overlay"})


def test_resolve_params_clamps_numeric_bounds() -> None:
    """decay, amount and iterations are clamped to their contract bounds."""
    info = get_effect(EFFECT_ID)
    resolved = resolve_params(info.params, {"decay": 5.0, "amount": -4.0, "iterations": 99})
    assert resolved["decay"] == 0.99
    assert resolved["amount"] == -4.0  # a negative amount is meaningful: zoom inward
    assert resolved["iterations"] == 16
    assert resolve_params(info.params, {"amount": -99.0})["amount"] == -6.0
    assert resolve_params(info.params, {"iterations": 0})["iterations"] == 1


def test_effect_does_not_mutate_the_input() -> None:
    """Running the effect leaves the source array untouched."""
    img = _image()
    before = img.copy()
    _run(img, _params(transform="displace"), iterations=8)
    assert np.array_equal(img, before)


@pytest.mark.parametrize("shape", [(1, 1), (1, 5), (5, 1), (37, 23)])
def test_outputs_are_float32_in_range_at_small_shapes(shape: tuple[int, int]) -> None:
    """Even tiny or degenerate images produce a float32 buffer inside [0, 1]."""
    out = _run(_image(shape=shape), _params(transform="rotate"))
    assert out.shape == (*shape, 3)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def _corner_energy(frame: np.ndarray) -> dict[str, float]:
    """Return the mean brightness of each third of the frame, for pivot checks."""
    h, w = frame.shape[:2]
    return {
        "top": float(frame[: h // 3].mean()),
        "bottom": float(frame[-h // 3 :].mean()),
        "left": float(frame[:, : w // 3].mean()),
        "right": float(frame[:, -w // 3 :].mean()),
    }


@pytest.mark.parametrize("origin", ["center", "top_left", "bottom_right", "left", "top"])
def test_origin_moves_the_rotation_pivot(origin: str) -> None:
    """The pivot really moves: rotating around a corner leaves a different frame."""
    img = _ramp((48, 48))
    centred = _run(img, {"decay": 0.85, "transform": "rotate", "amount": 30.0,
                         "iterations": 4, "blend": "screen", "origin": "center"})
    moved = _run(img, {"decay": 0.85, "transform": "rotate", "amount": 30.0,
                       "iterations": 4, "blend": "screen", "origin": origin})
    if origin == "center":
        assert np.array_equal(moved, centred)
    else:
        assert not np.array_equal(moved, centred)


def test_origin_changes_where_the_zoom_stretches() -> None:
    """Scaling around a corner moves the far side, not the middle.

    Measured on a horizontal ramp, where a wrong pivot is unmistakable: a zoom anchored
    at the centre keeps the midpoint near its source value, an anchor at the top-left
    samples further right, so the midpoint brightens towards the far edge.
    """
    img = _ramp((64, 64))
    grid = _grid(64, 64)
    centred = _apply_transform(img, "scale", -4.0, grid, None, "center", 0.0)
    corner = _apply_transform(img, "scale", -4.0, grid, None, "top_left", 0.0)
    mid_center = float(centred[0, 32, 0])
    mid_corner = float(corner[0, 32, 0])
    assert abs(mid_center - 0.5) < 0.05  # the centre pivot keeps the middle put
    assert mid_corner > mid_center + 0.2  # the corner pivot drags it towards the far side


def test_origin_keeps_the_rotation_corner_sharp() -> None:
    """Rotating around the top-left leaves that corner exactly as it was."""
    img = _ramp((64, 64))
    grid = _grid(64, 64)
    centred = _apply_transform(img, "rotate", 30.0, grid, None, "center", 0.0)
    corner = _apply_transform(img, "rotate", 30.0, grid, None, "top_left", 0.0)
    assert float(centred[0, 0, 0]) > 0.1  # a centre pivot smears the corner
    assert float(corner[0, 0, 0]) == float(img[0, 0, 0])  # the pivot itself is untouched


@pytest.mark.parametrize("direction", [0.0, 90.0, 180.0, -90.0])
def test_direction_chooses_the_translate_heading(direction: float) -> None:
    """Every heading gives a different frame, and none of them is the untouched source."""
    img = _corners((64, 64))
    params = {"decay": 0.8, "transform": "translate", "amount": 6.0,
              "iterations": 3, "blend": "screen", "direction": direction}
    out = _run(img, params)
    assert not np.array_equal(out, img)
    right = _run(img, {**params, "direction": 0.0})
    down = _run(img, {**params, "direction": 90.0})
    assert not np.array_equal(right, down)


def _centroid(frame: np.ndarray) -> tuple[float, float]:
    """Return the (x, y) centre of brightness of a frame."""
    weight = frame.sum(axis=2)
    total = float(weight.sum())
    h, w = weight.shape
    xs = np.arange(w, dtype=np.float64)[None, :]
    ys = np.arange(h, dtype=np.float64)[:, None]
    return float((weight * xs).sum() / total), float((weight * ys).sum() / total)


def _dot(shape: tuple[int, int]) -> np.ndarray:
    """Return a dark frame with one bright square in the middle."""
    frame = np.zeros((*shape, 3), dtype=np.float32)
    cy, cx = shape[0] // 2, shape[1] // 2
    frame[cy - 4 : cy + 4, cx - 4 : cx + 4] = 1.0
    return frame


@pytest.mark.parametrize(("direction", "moves"), [(0.0, "x"), (180.0, "x"), (90.0, "y"),
                                                  (-90.0, "y")])
def test_direction_moves_the_echo_along_its_heading(direction: float, moves: str) -> None:
    """The bright blob ends up displaced along the chosen axis, and only along it."""
    img = _dot((64, 64))
    start_x, start_y = _centroid(img)
    out = _apply_transform(
        img, "translate", 10.0, _grid(64, 64), None, "center", direction
    )
    end_x, end_y = _centroid(out)
    if moves == "x":
        assert abs(end_x - start_x) > 3.0  # it really travelled horizontally
        assert abs(end_y - start_y) < 1.0  # and not vertically
    else:
        assert abs(end_y - start_y) > 3.0
        assert abs(end_x - start_x) < 1.0


def test_direction_opposite_headings_are_mirror_images() -> None:
    """0 and 180 send the echo to opposite sides; 90 and -90 do the same vertically."""
    img = _dot((64, 64))
    grid = _grid(64, 64)
    x0, _ = _centroid(_apply_transform(img, "translate", 10.0, grid, None, "center", 0.0))
    x180, _ = _centroid(_apply_transform(img, "translate", 10.0, grid, None, "center", 180.0))
    _, y90 = _centroid(_apply_transform(img, "translate", 10.0, grid, None, "center", 90.0))
    _, y270 = _centroid(_apply_transform(img, "translate", 10.0, grid, None, "center", -90.0))
    source_x, source_y = _centroid(img)
    assert x0 > source_x > x180
    # Screen convention: heading 90 sends the echo DOWN, -90 sends it up (Opus flagged the
    # inverted Y axis on the first take: "down" was climbing).
    assert y90 > source_y > y270


def test_unknown_origin_is_rejected_naming_the_value() -> None:
    """A bad origin is caught at validation, with the offending value in the message."""
    with pytest.raises(ValueError, match="middle"):
        validate_params({"origin": "middle"})


def test_direction_is_clamped_to_plus_minus_180() -> None:
    """Direction outside the documented range is clamped, not accepted silently."""
    assert validate_params({"direction": 400})["direction"] == 180.0
    assert validate_params({"direction": -400})["direction"] == -180.0


def test_mix_at_zero_returns_the_source() -> None:
    """`mix = 0` is the dry signal: the loop is computed and thrown away."""
    img = _ramp((32, 32))
    out = _run(img, {"decay": 0.9, "transform": "rotate", "amount": 5.0,
                     "iterations": 6, "blend": "screen", "mix": 0.0})
    assert np.allclose(out, img, atol=1e-6)


def test_mix_controls_how_far_the_mean_drifts() -> None:
    """The loop lifts the mean (the pastel wash); `mix` pulls it back towards the source.

    Measured on the real complaint: with translate + screen, the mean rose from 0.43 to
    0.72 and everything read pastel. A half mix lands in between, monotonically.
    """
    img = _ramp((48, 48))
    base = {"decay": 0.85, "transform": "translate", "amount": 7.0, "iterations": 6,
            "blend": "screen", "origin": "top", "direction": 90.0}
    full = float(_run(img, {**base, "mix": 1.0}).mean())
    half = float(_run(img, {**base, "mix": 0.5}).mean())
    dry = float(img.mean())
    assert full > half > dry
    assert full - dry > 0.05  # the wash is real, not a rounding artefact


def test_blend_add_keeps_the_hue_ratio_but_screen_does_not() -> None:
    """The pastel is caused by `screen`, not by the normalisation (measured, not assumed).

    A saturated orange keeps R/G = 2 under `add` because every channel is scaled by the
    same factor; `screen` is non-linear and lifts the weak channels proportionally more,
    which desaturates towards pastel. Documented so nobody hunts the wrong culprit again.
    """
    img = np.zeros((24, 24, 3), dtype=np.float32)
    img[...] = [0.9, 0.45, 0.1]
    base = {"decay": 0.85, "transform": "translate", "amount": 4.0, "iterations": 6,
            "origin": "center", "direction": 0.0, "mix": 1.0}
    added = _run(img, {**base, "blend": "add"})[12, 12]
    screened = _run(img, {**base, "blend": "screen"})[12, 12]
    assert abs(float(added[0] / added[1]) - 2.0) < 0.05  # add keeps the hue
    assert float(screened[0] / screened[1]) < 1.5  # screen washes it towards grey


def test_transform_accepts_a_documented_composition() -> None:
    """`rotate+scale` is a documented composition, so a preset may ask for it."""
    img = _ramp((32, 32))
    out = _run(img, {"decay": 0.85, "transform": "rotate+scale", "amount": 3.0,
                     "iterations": 4, "blend": "screen"})
    assert out.shape == img.shape
    single = _run(img, {"decay": 0.85, "transform": "rotate", "amount": 3.0,
                        "iterations": 4, "blend": "screen"})
    assert not np.array_equal(out, single)  # the composition really adds the second step


def test_negative_amount_makes_the_zoom_go_inward() -> None:
    """`scale` with a negative amount zooms IN: the factor must stay below 1.

    A negative amount used to be clamped to 0 by the ParamSpec bound, so the factor became
    exactly 1.0 and `scale` collapsed silently into `identity`. Opus scored that render
    3/10 ("aucun echo visible") without knowing the effect was doing nothing at all.
    """
    img = _ramp((64, 64))
    grid = _grid(64, 64)
    null = _apply_transform(img, "scale", 0.0, grid, None, "center", 0.0)
    inward = _apply_transform(img, "scale", -3.0, grid, None, "center", 0.0)
    assert np.array_equal(null, img)  # amount 0 really is the identity
    assert not np.array_equal(inward, img)  # and a negative amount is not
    resolved = resolve_params(get_effect(EFFECT_ID).params, {"amount": -3.0})
    assert resolved["amount"] == -3.0  # the bound no longer eats the sign


def test_negative_amount_never_divides_by_zero() -> None:
    """The lower bound stays off the singular point of `1 + amount/10`."""
    img = _ramp((32, 32))
    out = _apply_transform(img, "scale", -6.0, _grid(32, 32), None, "center", 0.0)
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0 and float(out.max()) <= 1.0
