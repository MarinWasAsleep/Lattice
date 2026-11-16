"""Tests for the palette library and pasted-hex import (T21 / CONTRACT §16)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lattice_core.palettes.io import MAX_COLORS, MIN_COLORS, from_hex_text, hex_list
from lattice_core.palettes.library import DATA_DIR, get_library, library_names

MIN_LIBRARY = 12


def _files() -> list[Path]:
    """Return the shipped .hex files."""
    return sorted(DATA_DIR.glob("*.hex"))


def _header(path: Path) -> dict[str, str]:
    """Return the "# key: value" header lines of a palette file."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        body = line[1:].strip()
        if ":" in body:
            key, _, value = body.partition(":")
            found[key.strip().lower()] = value.strip()
    return found


def test_at_least_twelve_palettes_are_shipped() -> None:
    """§16 asks for at least twelve redistributable palettes."""
    assert len(_files()) >= MIN_LIBRARY


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.stem)
def test_every_file_parses_with_a_source_and_a_licence(path: Path) -> None:
    """Each shipped palette parses, holds 2..256 colours and names its source and licence."""
    header = _header(path)
    assert header.get("source"), f"{path.name} has no source line"
    assert header.get("licence"), f"{path.name} has no licence line"
    palette = get_library(path.stem)
    assert palette.ndim == 2 and palette.shape[1] == 3
    assert MIN_COLORS <= palette.shape[0] <= MAX_COLORS
    assert palette.dtype == np.float32
    assert float(palette.min()) >= 0.0
    assert float(palette.max()) <= 1.0


def test_library_names_is_sorted_and_stable() -> None:
    """library_names returns the same sorted list on every call."""
    first = library_names()
    assert first == sorted(first)
    assert first == library_names()
    assert first == [path.stem for path in _files()]


def test_unknown_library_name_raises_key_error() -> None:
    """get_library on a name that is not shipped raises KeyError."""
    with pytest.raises(KeyError):
        get_library("no_such_palette")


def test_get_library_returns_a_copy() -> None:
    """Mutating a returned palette does not corrupt the cached one."""
    name = library_names()[0]
    palette = get_library(name)
    palette[0] = 0.123
    assert not np.array_equal(get_library(name)[0], palette[0])


def test_library_files_are_not_imported_by_the_core() -> None:
    """The fetch script is manual: nothing in the package imports it."""
    root = Path(__file__).resolve().parents[1]
    for path in (root / "lattice_dither").rglob("*.py"):
        assert "fetch_palettes" not in path.read_text(encoding="utf-8"), path


@pytest.mark.parametrize(
    "text",
    [
        "#FF0000 #00FF00 #0000FF",
        "FF0000 00FF00 0000FF",
        "FF0000,00FF00,0000FF",
        "#FF0000\n#00FF00\n#0000FF",
        "#FF0000\t#00FF00\t#0000FF",
        "Here are my colours:\n#FF0000\n#00FF00\n#0000FF\nEnjoy!",
        "  #ff0000 , #00ff00 , #0000ff  ",
    ],
)
def test_from_hex_text_accepts_every_separator(text: str) -> None:
    """Pasted hex lists parse whatever the separators and surrounding prose."""
    assert hex_list(from_hex_text(text)) == ["#FF0000", "#00FF00", "#0000FF"]


def test_from_hex_text_ignores_prose_words_that_look_like_hex() -> None:
    """A six-letter word is not read as a colour when hashed codes are present."""
    palette = from_hex_text("a facade of #123456 and #ABCDEF")
    assert hex_list(palette) == ["#123456", "#ABCDEF"]


def test_from_hex_text_rejects_too_few_colours() -> None:
    """A single colour is not a palette."""
    with pytest.raises(ValueError):
        from_hex_text("#FF0000")


def test_from_hex_text_rejects_empty_text() -> None:
    """Text with no colour at all raises rather than returning an empty palette."""
    with pytest.raises(ValueError):
        from_hex_text("nothing to see here")
