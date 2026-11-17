"""Deterministic per-module seeding for the random operators of a render (§18)."""

from __future__ import annotations

import numpy as np

from lattice_core.registry import get_effect, resolve_params
from lattice_core.types import Image

_MASK64 = (1 << 64) - 1
_PHI = 0x9E3779B97F4A7C15
_G1 = 0xBF58476D1CE4E5B9
_G2 = 0x94D049BB133111EB


def _mix(value: int) -> int:
    """Return a splitmix64 mixing of value, kept inside the unsigned 64-bit range."""
    mixed = (value + _PHI) & _MASK64
    mixed = ((mixed ^ (mixed >> 30)) * _G1) & _MASK64
    mixed = ((mixed ^ (mixed >> 27)) * _G2) & _MASK64
    return (mixed ^ (mixed >> 31)) & _MASK64


def module_seed(seed: int, module: int) -> int:
    """Return the deterministic per-module stream seed derived from the global seed."""
    return _mix(_mix(int(seed)) ^ _mix(int(module) + 1))


class SeedController:
    """One global seed plus per-module streams, with optional per-module locks.

    ``rng(module)`` returns a deterministic generator for one module. A locked
    module keeps its stream when the seed is rerolled, so its output never
    changes with the global seed; every unlocked module follows the new seed.
    """

    def __init__(self, seed: int = 0, locked: tuple[int, ...] = ()) -> None:
        self._base: int = int(seed)
        self._fixed: dict[int, int] = {}
        for module in locked:
            self.lock(module)

    @property
    def seed(self) -> int:
        """The global seed driving the whole render."""
        return self._base

    def module_seed_for(self, module: int) -> int:
        """Return the stream seed of one module, fixed when the module is locked."""
        return self._fixed.get(module, module_seed(self._base, module))

    def rng(self, module: int) -> np.random.Generator:
        """Return the deterministic random generator of one module."""
        return np.random.default_rng(self.module_seed_for(module))

    def lock(self, module: int) -> None:
        """Freeze the current stream of module so a reroll does not change it."""
        if module not in self._fixed:
            self._fixed[module] = module_seed(self._base, module)

    def unlock(self, module: int) -> None:
        """Let module follow the global seed again on the next reroll."""
        self._fixed.pop(module, None)

    def locked(self) -> frozenset[int]:
        """Return the set of module indices whose streams are frozen."""
        return frozenset(self._fixed)

    def reroll(self, seed: int | None = None) -> int:
        """Reroll the global seed; locked modules keep their prior streams."""
        self._base = _mix(self._base + 1) if seed is None else int(seed)
        return self._base


def render_effects(img: Image, effects: list[str], controller: SeedController,
                   *, params: dict[str, dict] | None = None,
                   module_start: int = 0) -> list[Image]:
    """Apply the named effects in order with per-module rngs, returning each stage.

    ``params`` optionally overrides an effect's parameters by effect id; every
    stage is clipped to [0, 1] like the interactive renderer does.
    """
    overrides = params or {}
    out: Image = img
    stages: list[Image] = []
    for offset, effect_id in enumerate(effects, start=module_start):
        info = get_effect(effect_id)
        params = resolve_params(info.params, overrides.get(effect_id, {}))
        rng = controller.rng(offset)
        out = np.ascontiguousarray(
            np.clip(info.fn(out, params, rng), 0.0, 1.0), np.float32
        )
        stages.append(out)
    return stages