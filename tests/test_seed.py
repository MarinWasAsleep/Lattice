"""Tests for the §18 seed system: determinism, per-module lock, reroll and serialisation."""

from __future__ import annotations

import numpy as np

import lattice_core.effects  # noqa: F401 — enregistre les effets (registre peuplé à l'import)
from lattice_core.pipeline import EffectInstance, PipelineSpec, render
from lattice_core.preset import Preset, from_json, from_pipeline_spec, to_json, to_pipeline_spec
from lattice_core.seed import SeedController, module_seed, render_effects

_JPEG = {"quality": 40, "corruptions": 5}


def test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline(
    rng: np.random.Generator,
) -> None:
    """Accept: the same seed produces identical output across two multi-effect runs."""
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    spec = PipelineSpec(seed=2026)
    spec.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    first = render(img, spec)
    second = render(img, spec)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, np.clip(img, 0.0, 1.0).astype(np.uint8))


def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) -> None:
    """The seed genuinely drives the pipeline: a new seed re-randomises the render."""
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    base = PipelineSpec(seed=11)
    base.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    rerolled = PipelineSpec(seed=12)
    rerolled.post_effects = list(base.post_effects)
    assert not np.array_equal(render(img, base), render(img, rerolled))


def test_controller_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
    """Running render_effects with the same controller twice gives identical stages."""
    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=99)
    first = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
                           params={"jpeg_glitch": _JPEG})
    second = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
                            params={"jpeg_glitch": _JPEG})
    for a, b in zip(first, second, strict=True):
        assert np.array_equal(a, b)


def test_locked_module_keeps_output_and_unlocked_changes(rng: np.random.Generator) -> None:
    """Accept: a locked module keeps its output on reroll; an unlocked one changes."""
    img = np.clip(rng.random((40, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=7, locked=(0,))
    before = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
                            params={"jpeg_glitch": _JPEG})
    controller.reroll(10_000)
    after = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
                           params={"jpeg_glitch": _JPEG})
    assert np.array_equal(after[0], before[0]), "locked module 0 must keep its output"
    assert not np.array_equal(after[1], before[1]), "unlocked module 1 must change"


def test_lock_and_unlock_flip_reroll_behaviour(rng: np.random.Generator) -> None:
    """Locking freezes a module; unlocking lets it follow the new seed again."""
    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=1)
    before = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    controller.lock(0)
    controller.reroll(5)
    locked = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    assert np.array_equal(locked[0], before[0])
    controller.unlock(0)
    controller.reroll(6)
    released = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    assert not np.array_equal(released[0], locked[0])
    assert controller.locked() == frozenset()


def test_module_seed_depends_on_both_seed_and_module() -> None:
    """Different modules of the same seed get independent, stable streams."""
    assert module_seed(3, 0) != module_seed(3, 1)
    assert module_seed(3, 0) == module_seed(3, 0)
    assert module_seed(3, 0) != module_seed(4, 0)


def test_reroll_without_argument_still_changes_the_seed() -> None:
    """reroll() draws a new deterministic seed that unlocked modules follow."""
    controller = SeedController(seed=1)
    old = controller.seed
    new = controller.reroll()
    assert new != old
    assert controller.seed == new


def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
    """Accept: the seed is serialised into the preset and restored on load."""
    preset = Preset(seed=123456789)
    loaded = from_json(to_json(preset))
    assert loaded.seed == 123456789
    assert from_json('{"version": 3, "seed": 55, "meta": {}}').seed == 55


def test_seed_survives_pipeline_spec_round_trip() -> None:
    """The seed crosses from spec to preset and back to the spec unchanged."""
    spec = PipelineSpec(seed=424242)
    preset = from_pipeline_spec(spec)
    restored = to_pipeline_spec(preset)
    assert preset.seed == 424242
    assert restored.seed == 424242


def test_missing_seed_defaults_to_zero() -> None:
    """An absent seed field loads as 0, never crashing."""
    assert from_json('{"version": 3, "meta": {}}').seed == 0
