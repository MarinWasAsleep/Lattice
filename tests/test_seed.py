"""Tests for the §18 seed system: determinism, per-module lock, reroll and serialisation."""

from __future__ import annotations

import numpy as np

import lattice.effects  # noqa: F401 — enregistre les effets (registre peuplé à l'import)
from lattice.pipeline import EffectInstance, PipelineSpec, render
from lattice.preset import Preset, from_json, from_pipeline_spec, to_json, to_pipeline_spec
from lattice.seed import SeedController, module_seed, render_effects

_JPEG = {"quality": 40, "corruptions": 5}
# Two effects that both consume their rng, so a changed stream is visible.
_CHAIN = ["jpeg_glitch", "noise"]


def test_pipeline_determinism_is_the_preexisting_seed_path(rng: np.random.Generator) -> None:
    """§6 determinism of pipeline.render predates L19; L19 adds module_seed/SeedController.

    The case is kept as a regression witness for the 1.0 seeding rule
    (``default_rng(seed + offset + i)``), which L19 deliberately does not replace.
    """
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    spec = PipelineSpec(seed=2026)
    spec.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    first = render(img, spec)
    second = render(img, spec)
    assert np.array_equal(first, second)
    other = PipelineSpec(seed=2027)
    other.post_effects = list(spec.post_effects)
    assert not np.array_equal(first, render(img, other))


def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) -> None:
    """The seed genuinely drives the pipeline: a new seed re-randomises the render."""
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    base = PipelineSpec(seed=11)
    base.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    rerolled = PipelineSpec(seed=12)
    rerolled.post_effects = list(base.post_effects)
    assert not np.array_equal(render(img, base), render(img, rerolled))


def test_render_effects_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
    """Accept: the same seed gives identical output on two runs of a multi-effect chain."""
    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=99)
    first = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
    second = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
    assert len(first) == 2
    for a, b in zip(first, second, strict=True):
        assert np.array_equal(a, b)
    # The chain really is randomised: rerolling the same controller changes it.
    controller.reroll(1000)
    third = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
    assert not np.array_equal(first[0], third[0])
    assert not np.array_equal(first[1], third[1])


def test_locked_module_keeps_output_and_unlocked_changes(rng: np.random.Generator) -> None:
    """Accept: a locked module keeps its output on reroll; an unlocked one changes.

    Two real registry effects that both draw from their rng; position 0 is locked.
    Compared as arrays, not as a call counter.
    """
    img = np.clip(rng.random((40, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=7, locked=(0,))
    before = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
    controller.reroll(10_000)
    after = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
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


def test_module_start_offsets_the_lock_positions(rng: np.random.Generator) -> None:
    """Lock keys are positions: a chain started at module_start uses that offset."""
    img = np.clip(rng.random((24, 24, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=3, locked=(5,))
    before = render_effects(img, ["jpeg_glitch"], controller, module_start=5,
                            params={"jpeg_glitch": _JPEG})
    controller.reroll(77)
    after = render_effects(img, ["jpeg_glitch"], controller, module_start=5,
                           params={"jpeg_glitch": _JPEG})
    assert np.array_equal(after[0], before[0])


def test_module_seed_depends_on_both_seed_and_module() -> None:
    """Different modules of the same seed get independent, stable streams."""
    assert module_seed(3, 0) != module_seed(3, 1)
    assert module_seed(3, 0) == module_seed(3, 0)
    assert module_seed(3, 0) != module_seed(4, 0)
    assert module_seed(-1, 2) == module_seed(-1, 2)
    assert 0 <= module_seed(-1, 2) < (1 << 64)


def test_reroll_without_argument_still_changes_the_seed() -> None:
    """reroll() draws a new deterministic seed that unlocked modules follow."""
    controller = SeedController(seed=1)
    old = controller.seed
    new = controller.reroll()
    assert new != old
    assert controller.seed == new
    second = SeedController(seed=1)
    assert second.reroll() == new


def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
    """Accept: the seed is serialised into the preset and restored on load."""
    preset = Preset(seed=123456789)
    loaded = from_json(to_json(preset))
    assert loaded.seed == 123456789
    assert from_json('{"version": 3, "seed": 55, "meta": {}}').seed == 55


def test_locks_are_session_only_and_a_reloaded_preset_drops_them() -> None:
    """E1/DEV-216: only `seed` is serialised, so a lock is lost across save/load.

    Locked at seed A then rerolled to B, the controller keeps serving the frozen
    A-stream; a preset saved after the reroll carries only B, so a reloaded
    controller rebuilds module 0 from B and no longer reproduces the frozen stream.
    """
    controller = SeedController(seed=7, locked=(0,))
    frozen = controller.rng(0).bit_generator.state
    rerolled = controller.reroll(1000)
    assert controller.rng(0).bit_generator.state == frozen, "the lock still holds in session"

    loaded = from_json(to_json(Preset(seed=rerolled)))
    assert loaded.seed == 1000
    rebuilt = SeedController(seed=loaded.seed)
    assert rebuilt.locked() == frozenset()
    assert rebuilt.rng(0).bit_generator.state != frozen, "the lock did not survive the reload"
    fresh = SeedController(seed=1000)
    assert rebuilt.rng(0).bit_generator.state == fresh.rng(0).bit_generator.state


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
