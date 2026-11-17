"""Tests for the feedback buffer effect (L13 / CONTRACT §12)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_core.effects.feedback import feedback, iterate, validate_params
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
    ]
    assert resolve_params(info.params, {}) == {
        "decay": 0.5,
        "transform": "identity",
        "amount": 2.0,
        "iterations": 1,
        "blend": "add",
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
    assert resolved["amount"] == 0.0
    assert resolved["iterations"] == 8
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
