"""Palette library backed by the .hex files in palettes/data (CONTRACT §16)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from lattice_core.palettes.io import load_palette
from lattice_core.types import Palette

DATA_DIR = Path(__file__).resolve().parent / "data"


def _paths() -> dict[str, Path]:
    """Return the shipped .hex files keyed by palette name."""
    return {path.stem: path for path in sorted(DATA_DIR.glob("*.hex"))}


def library_names() -> list[str]:
    """Return the sorted names of every shipped library palette."""
    return sorted(_paths())


@cache
def _load(name: str) -> Palette:
    """Load and cache one library palette, read-only."""
    palette = load_palette(_paths()[name])
    palette.setflags(write=False)
    return palette


def get_library(name: str) -> Palette:
    """Return a writable copy of the library palette registered under name."""
    if name not in _paths():
        raise KeyError(f"unknown library palette: {name!r}")
    return _load(name).copy()
