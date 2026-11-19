"""Tests for the algorithm and effect registries."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from lattice import registry
from lattice.types import ParamSpec


def _noop_algorithm(img, palette, params):
    return np.zeros(img.shape[:2], dtype=np.int32)


def _noop_effect(img, params, rng):
    return img.copy()


def _load_check_contract():
    path = Path(__file__).resolve().parents[1] / "tools" / "check_contract.py"
    spec = importlib.util.spec_from_file_location("check_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_registries(monkeypatch):
    monkeypatch.setattr(registry, "_ALGORITHMS", {})
    monkeypatch.setattr(registry, "_EFFECTS", {})
    return registry


def test_resolve_params_fills_defaults():
    specs = (
        ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0),
        ParamSpec("count", "Count", "int", 3, 1, 10),
        ParamSpec("serpentine", "Serpentine", "bool", True),
        ParamSpec("mode", "Mode", "choice", "a", choices=("a", "b")),
    )
    assert registry.resolve_params(specs, {}) == {
        "strength": 1.0,
        "count": 3,
        "serpentine": True,
        "mode": "a",
    }


def test_resolve_params_clamps_and_casts():
    specs = (
        ParamSpec("strength", "Strength", "float", 1.0, 0.0, 1.0),
        ParamSpec("count", "Count", "int", 3, 1, 10),
    )
    assert registry.resolve_params(specs, {"strength": 5.0})["strength"] == 1.0
    assert registry.resolve_params(specs, {"strength": -5.0})["strength"] == 0.0
    assert registry.resolve_params(specs, {"count": 99})["count"] == 10
    assert registry.resolve_params(specs, {"count": 0})["count"] == 1
    assert isinstance(registry.resolve_params(specs, {"count": 4.0})["count"], int)


def test_resolve_params_rejects_unknown_key():
    with pytest.raises(ValueError):
        registry.resolve_params((), {"nope": 1})


def test_resolve_params_rejects_bad_choice():
    specs = (ParamSpec("mode", "Mode", "choice", "a", choices=("a", "b")),)
    with pytest.raises(ValueError):
        registry.resolve_params(specs, {"mode": "z"})


def test_duplicate_algorithm_registration_raises(clean_registries):
    clean_registries.register_algorithm("dup", "Dup", "other")(_noop_algorithm)
    with pytest.raises(ValueError):
        clean_registries.register_algorithm("dup", "Dup again", "other")(_noop_algorithm)


def test_duplicate_effect_registration_raises(clean_registries):
    clean_registries.register_effect("dup", "Dup")(_noop_effect)
    with pytest.raises(ValueError):
        clean_registries.register_effect("dup", "Dup again")(_noop_effect)


def test_list_algorithms_sorted_by_family_then_name(clean_registries):
    clean_registries.register_algorithm("z_ordered", "Zeta", "ordered")(_noop_algorithm)
    clean_registries.register_algorithm("a_other", "Alpha", "other")(_noop_algorithm)
    clean_registries.register_algorithm("b_ed", "Beta", "error_diffusion")(_noop_algorithm)
    clean_registries.register_algorithm("a_ed", "Alpha", "error_diffusion")(_noop_algorithm)
    ids = [info.id for info in clean_registries.list_algorithms()]
    assert ids == ["a_ed", "b_ed", "z_ordered", "a_other"]


def test_get_unknown_algorithm_raises(clean_registries):
    with pytest.raises(KeyError):
        clean_registries.get_algorithm("missing")


def test_check_contract_passes_with_empty_registries(clean_registries, monkeypatch):
    module = _load_check_contract()
    monkeypatch.setattr(module, "list_algorithms", clean_registries.list_algorithms)
    monkeypatch.setattr(module, "list_effects", clean_registries.list_effects)
    assert module.main() == 0


def test_check_contract_passes_with_one_dummy_algorithm(clean_registries, monkeypatch):
    clean_registries.register_algorithm("dummy", "Dummy", "other")(_noop_algorithm)
    module = _load_check_contract()
    monkeypatch.setattr(module, "list_algorithms", clean_registries.list_algorithms)
    monkeypatch.setattr(module, "list_effects", clean_registries.list_effects)
    assert module.main() == 0
