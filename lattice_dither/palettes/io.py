"""Palette import and export (T05)."""

from __future__ import annotations

import re
import string
from pathlib import Path

import numpy as np

from lattice_dither.core.types import Palette

_HEX_DIGITS = frozenset(string.hexdigits)
MIN_COLORS = 2
MAX_COLORS = 256
_GPL_HEADER = "GIMP Palette"
_GPL_KEYS = ("Name:", "Columns:")
_HEADER = re.compile(r"^[A-Za-z][A-Za-z ]*:")
_HASHED = re.compile(r"#([0-9A-Fa-f]{6})(?![0-9A-Fa-f])")
_BARE = re.compile(r"(?<![0-9A-Za-z])([0-9A-Fa-f]{6})(?![0-9A-Za-z])")


def _to_rgb8(p: Palette) -> np.ndarray:
    """Return the palette as uint8 RGB, rounding half up and clipping."""
    return np.floor(np.clip(p, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _parse_hex(text: str, where: str) -> list[float]:
    """Parse one RRGGBB token into a float colour, raising ValueError on bad input."""
    if len(text) != 6 or not set(text) <= _HEX_DIGITS:
        raise ValueError(f"{where}: invalid hex colour {text!r}")
    return [int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]


def hex_list(p: Palette) -> list[str]:
    """Return the palette as uppercase "#RRGGBB" strings."""
    return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in _to_rgb8(p)]


def from_hex_list(values: list[str]) -> Palette:
    """Parse "#RRGGBB" strings into a palette, raising ValueError on a bad entry."""
    colors = []
    for position, value in enumerate(values, start=1):
        text = value.strip()
        if text.startswith("#"):
            text = text[1:]
        colors.append(_parse_hex(text, f"line {position}"))
    return np.array(colors, dtype=np.float32).reshape(-1, 3)


def from_hex_text(text: str) -> Palette:
    """Parse a pasted list of hex colours, ignoring any surrounding prose.

    Hashed codes ("#RRGGBB") win when the text contains any, so a sentence that
    happens to hold a six-letter word is not read as a colour. Otherwise bare
    "RRGGBB" tokens delimited by non-alphanumerics are used.
    """
    hashed = _HASHED.findall(text)
    tokens = hashed if hashed else _BARE.findall(text)
    if not MIN_COLORS <= len(tokens) <= MAX_COLORS:
        raise ValueError(
            f"a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {len(tokens)}"
        )
    return np.array([_parse_hex(token, "pasted text") for token in tokens], dtype=np.float32)


def _read_hex(path: Path) -> list[list[float]]:
    """Parse a .hex file, tolerating headers, blank lines, "; " comments and CRLF.

    A line is a colour when it starts with a hex triplet, optionally followed by a
    tab-separated name. A "#" line whose body starts with a "key:" header is a
    comment, which is how the library files carry their source and licence.
    """
    colors: list[list[float]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith(";"):
            continue
        if text.startswith("#"):
            text = text[1:].strip()
            if not text or _HEADER.match(text):
                continue
        colors.append(_parse_color_line(text, f"{path}: line {number}"))
    return colors


def _parse_color_line(text: str, where: str) -> list[float]:
    """Parse "RRGGBB" or "R G B" followed by an optional name into a float colour."""
    parts = text.split()
    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
        channels = [int(part) for part in parts[:3]]
        if any(channel > 255 for channel in channels):
            raise ValueError(f"{where}: channel outside 0..255 in {text!r}")
        return [channel / 255.0 for channel in channels]
    return _parse_hex(parts[0], where)


def _read_gpl(path: Path) -> list[list[float]]:
    """Parse a GIMP .gpl file into float colours, raising ValueError on a bad line."""
    colors: list[list[float]] = []
    header_seen = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        if not header_seen:
            if text != _GPL_HEADER:
                raise ValueError(f"{path}: line {number}: expected {_GPL_HEADER!r} header")
            header_seen = True
            continue
        if text.startswith("#") or text.startswith(_GPL_KEYS):
            continue
        parts = text.split()
        if len(parts) < 3:
            raise ValueError(f"{path}: line {number}: expected 'R G B name', got {text!r}")
        try:
            channels = [int(part) for part in parts[:3]]
        except ValueError:
            raise ValueError(f"{path}: line {number}: invalid channel in {text!r}") from None
        if any(channel < 0 or channel > 255 for channel in channels):
            raise ValueError(f"{path}: line {number}: channel outside 0..255 in {text!r}")
        colors.append([channel / 255.0 for channel in channels])
    if not header_seen:
        raise ValueError(f"{path}: line 1: expected {_GPL_HEADER!r} header")
    return colors


def _gpl_text(p: Palette, name: str) -> str:
    """Render a palette in GIMP .gpl format."""
    rgb8 = _to_rgb8(p)
    lines = [_GPL_HEADER, f"Name: {name}", f"Columns: {min(len(rgb8), 16)}", "#"]
    for index, (red, green, blue) in enumerate(rgb8):
        lines.append(f"{red:3d} {green:3d} {blue:3d}\tColour {index + 1}")
    return "\n".join(lines) + "\n"


def load_palette(path: Path) -> Palette:
    """Load a palette from a .hex or .gpl file, raising ValueError on malformed input."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".hex":
        colors = _read_hex(path)
    elif suffix == ".gpl":
        colors = _read_gpl(path)
    else:
        raise ValueError(f"{path}: unsupported palette format {path.suffix!r}")
    if not MIN_COLORS <= len(colors) <= MAX_COLORS:
        raise ValueError(
            f"{path}: a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {len(colors)}"
        )
    return np.array(colors, dtype=np.float32).reshape(-1, 3)


def save_palette(path: Path, p: Palette, name: str = "Lattice Dither") -> None:
    """Write a palette as .hex or .gpl, chosen by the file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".hex":
        text = "\n".join(hex_list(p)) + "\n"
    elif suffix == ".gpl":
        text = _gpl_text(p, name)
    else:
        raise ValueError(f"{path}: unsupported palette format {path.suffix!r}")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
