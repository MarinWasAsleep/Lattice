"""Registries of dithering algorithms and image effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from lattice_core.types import Image, Indices, Palette, ParamSpec

AlgorithmFn = Callable[[Image, Palette, dict], Indices]
EffectFn = Callable[[Image, dict, np.random.Generator], Image]

Family = Literal["error_diffusion", "ordered", "halftone", "other"]
_FAMILY_ORDER: dict[str, int] = {"error_diffusion": 0, "ordered": 1, "halftone": 2, "other": 3}


@dataclass(frozen=True)
class AlgorithmInfo:
    """Registration record of one dithering algorithm."""

    id: str
    name: str
    family: Family
    params: tuple[ParamSpec, ...]
    fn: AlgorithmFn


@dataclass(frozen=True)
class EffectInfo:
    """Registration record of one image effect."""

    id: str
    name: str
    params: tuple[ParamSpec, ...]
    fn: EffectFn


_ALGORITHMS: dict[str, AlgorithmInfo] = {}
_EFFECTS: dict[str, EffectInfo] = {}


def register_algorithm(
    id: str, name: str, family: str, params: tuple[ParamSpec, ...] = ()
) -> Callable[[AlgorithmFn], AlgorithmFn]:
    """Return a decorator that registers an algorithm under id."""
    if family not in _FAMILY_ORDER:
        raise ValueError(f"unknown family: {family!r}")

    def decorator(fn: AlgorithmFn) -> AlgorithmFn:
        if id in _ALGORITHMS:
            raise ValueError(f"duplicate algorithm id: {id!r}")
        _ALGORITHMS[id] = AlgorithmInfo(id, name, family, tuple(params), fn)
        return fn

    return decorator


def register_effect(
    id: str, name: str, params: tuple[ParamSpec, ...] = ()
) -> Callable[[EffectFn], EffectFn]:
    """Return a decorator that registers an effect under id."""

    def decorator(fn: EffectFn) -> EffectFn:
        if id in _EFFECTS:
            raise ValueError(f"duplicate effect id: {id!r}")
        _EFFECTS[id] = EffectInfo(id, name, tuple(params), fn)
        return fn

    return decorator


def get_algorithm(id: str) -> AlgorithmInfo:
    """Return the algorithm registered under id, or raise KeyError."""
    return _ALGORITHMS[id]


def list_algorithms() -> list[AlgorithmInfo]:
    """Return every registered algorithm, sorted by family then name."""
    return sorted(_ALGORITHMS.values(), key=lambda info: (_FAMILY_ORDER[info.family], info.name))


def get_effect(id: str) -> EffectInfo:
    """Return the effect registered under id, or raise KeyError."""
    return _EFFECTS[id]


def list_effects() -> list[EffectInfo]:
    """Return every registered effect, sorted by name."""
    return sorted(_EFFECTS.values(), key=lambda info: info.name)


def resolve_params(specs: tuple[ParamSpec, ...], given: dict) -> dict:
    """Fill defaults, clamp numbers to their bounds, cast ints and validate choices."""
    known = {spec.id for spec in specs}
    for key in given:
        if key not in known:
            raise ValueError(f"unknown parameter: {key!r}")
    resolved: dict = {}
    for spec in specs:
        value = given.get(spec.id, spec.default)
        if spec.kind == "float":
            number = float(value)
            if spec.min is not None:
                number = max(spec.min, number)
            if spec.max is not None:
                number = min(spec.max, number)
            resolved[spec.id] = number
        elif spec.kind == "int":
            integer = int(round(float(value)))
            if spec.min is not None:
                integer = max(int(spec.min), integer)
            if spec.max is not None:
                integer = min(int(spec.max), integer)
            resolved[spec.id] = integer
        elif spec.kind == "bool":
            resolved[spec.id] = bool(value)
        elif spec.kind == "choice":
            if value not in spec.choices:
                raise ValueError(f"invalid choice for {spec.id!r}: {value!r}")
            resolved[spec.id] = value
        else:
            raise ValueError(f"unknown parameter kind: {spec.kind!r}")
    return resolved
