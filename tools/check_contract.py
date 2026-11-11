"""Contract conformance checker (gate G3).

Imports the algorithm and effect packages, then exercises every registered item
against the shapes, palettes and invariants fixed by CONTRACT.md section 11.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dithercraft.algorithms  # noqa: E402, F401
import dithercraft.effects  # noqa: E402, F401
from dithercraft.core.registry import list_algorithms, list_effects, resolve_params  # noqa: E402

SHAPES: tuple[tuple[int, int], ...] = ((37, 23), (64, 64), (1, 5))
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _test_images() -> list[tuple[str, np.ndarray]]:
    """Return the seeded random and constant images used for every check."""
    rng = np.random.default_rng(1234)
    images = [(f"random {h}x{w}", rng.random((h, w, 3), dtype=np.float32)) for h, w in SHAPES]
    images.append(("constant", np.full((16, 16, 3), 0.5, dtype=np.float32)))
    return images


def _test_palettes() -> dict[int, np.ndarray]:
    """Return the K=2 and K=5 palettes used for every check."""
    return {
        2: np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32),
        5: np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 1.0, 1.0],
            ],
            dtype=np.float32,
        ),
    }


def _check_specs(owner: str, specs: tuple, failures: list[str]) -> None:
    """Check id shape, default bounds and choice lists of a parameter tuple."""
    seen: set[str] = set()
    for spec in specs:
        where = f"{owner}: param {spec.id!r}"
        if not SNAKE_CASE.match(spec.id):
            failures.append(f"{where}: id is not snake_case")
        if spec.id in seen:
            failures.append(f"{where}: duplicate param id")
        seen.add(spec.id)
        if spec.kind in ("float", "int"):
            if spec.min is None or spec.max is None:
                failures.append(f"{where}: min and max are required")
                continue
            if not spec.min <= spec.default <= spec.max:
                failures.append(f"{where}: default {spec.default} outside [{spec.min}, {spec.max}]")
        elif spec.kind == "choice":
            if not spec.choices:
                failures.append(f"{where}: choices is empty")
            elif spec.default not in spec.choices:
                failures.append(f"{where}: default {spec.default!r} not in choices")
        elif spec.kind != "bool":
            failures.append(f"{where}: unknown kind {spec.kind!r}")


def _check_algorithms(failures: list[str]) -> None:
    """Run every registered algorithm on every image and palette."""
    seen: set[str] = set()
    for info in list_algorithms():
        if info.id in seen:
            failures.append(f"algorithm {info.id!r}: duplicate id")
        seen.add(info.id)
        if not SNAKE_CASE.match(info.id):
            failures.append(f"algorithm {info.id!r}: id is not snake_case")
        _check_specs(f"algorithm {info.id}", info.params, failures)
        params = resolve_params(info.params, {})
        for label, img in _test_images():
            for k, palette in _test_palettes().items():
                where = f"algorithm {info.id} on {label}, K={k}"
                try:
                    out = info.fn(img.copy(), palette.copy(), dict(params))
                except Exception as exc:
                    failures.append(f"{where}: raised {type(exc).__name__}: {exc}")
                    continue
                if not isinstance(out, np.ndarray):
                    failures.append(f"{where}: returned {type(out).__name__}, not ndarray")
                    continue
                if out.dtype != np.int32:
                    failures.append(f"{where}: dtype {out.dtype}, expected int32")
                if out.shape != img.shape[:2]:
                    failures.append(f"{where}: shape {out.shape}, expected {img.shape[:2]}")
                    continue
                if out.size and (int(out.min()) < 0 or int(out.max()) >= k):
                    failures.append(f"{where}: values outside [0, {k})")


def _check_effects(failures: list[str]) -> None:
    """Run every registered effect on every image."""
    seen: set[str] = set()
    for info in list_effects():
        if info.id in seen:
            failures.append(f"effect {info.id!r}: duplicate id")
        seen.add(info.id)
        if not SNAKE_CASE.match(info.id):
            failures.append(f"effect {info.id!r}: id is not snake_case")
        _check_specs(f"effect {info.id}", info.params, failures)
        params = resolve_params(info.params, {})
        for label, img in _test_images():
            where = f"effect {info.id} on {label}"
            try:
                out = info.fn(img.copy(), dict(params), np.random.default_rng(0))
            except Exception as exc:
                failures.append(f"{where}: raised {type(exc).__name__}: {exc}")
                continue
            if not isinstance(out, np.ndarray):
                failures.append(f"{where}: returned {type(out).__name__}, not ndarray")
                continue
            if out.shape != img.shape:
                failures.append(f"{where}: shape {out.shape}, expected {img.shape}")
                continue
            if out.dtype != np.float32:
                failures.append(f"{where}: dtype {out.dtype}, expected float32")
            if out.size and (float(out.min()) < 0.0 or float(out.max()) > 1.0):
                failures.append(f"{where}: values outside [0, 1]")


def main() -> int:
    """Run every check, print one line per failure and return the exit code."""
    failures: list[str] = []
    _check_algorithms(failures)
    _check_effects(failures)
    for line in failures:
        print(line)
    if failures:
        print(f"{len(failures)} contract failure(s)")
        return 1
    print("contract OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
