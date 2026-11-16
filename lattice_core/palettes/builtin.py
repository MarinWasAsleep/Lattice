"""Built-in palettes (T05)."""

from __future__ import annotations

import numpy as np

from lattice_core.types import Palette


def _from_hex(values: str) -> Palette:
    """Build a palette from whitespace separated RRGGBB strings."""
    tokens = values.split()
    colors = [[int(token[i : i + 2], 16) / 255.0 for i in (0, 2, 4)] for token in tokens]
    return np.array(colors, dtype=np.float32)


def _greys(count: int) -> Palette:
    """Return count evenly spaced greys from black to white, snapped to the 8-bit grid."""
    ramp = np.round(np.linspace(0.0, 1.0, count) * 255.0) / 255.0
    return np.ascontiguousarray(np.repeat(ramp.astype(np.float32)[:, None], 3, axis=1))


def _rgb_corners() -> Palette:
    """Return the eight corners of the RGB cube."""
    colors = [
        [red, green, blue]
        for red in (0.0, 1.0)
        for green in (0.0, 1.0)
        for blue in (0.0, 1.0)
    ]
    return np.array(colors, dtype=np.float32)


BUILTIN: dict[str, Palette] = {
    "bw": _from_hex("000000 FFFFFF"),
    "gameboy": _from_hex("0F380F 306230 8BAC0F 9BBC0F"),
    "cga_0_high": _from_hex("000000 55FF55 FF5555 FFFF55"),
    "cga_1_high": _from_hex("000000 55FFFF FF55FF FFFFFF"),
    "ega": _from_hex(
        "000000 0000AA 00AA00 00AAAA AA0000 AA00AA AA5500 AAAAAA "
        "555555 5555FF 55FF55 55FFFF FF5555 FF55FF FFFF55 FFFFFF"
    ),
    "pico8": _from_hex(
        "000000 1D2B53 7E2553 008751 AB5236 5F574F C2C3C7 FFF1E8 "
        "FF004D FFA300 FFEC27 00E436 29ADFF 83769C FF77A8 FFCCAA"
    ),
    "grey_4": _greys(4),
    "grey_8": _greys(8),
    "grey_16": _greys(16),
    "rgb_8": _rgb_corners(),
    "cmyk_5": _from_hex("FFFFFF 00FFFF FF00FF FFFF00 000000"),
}


def get_builtin(name: str) -> Palette:
    """Return a copy of the built-in palette registered under name."""
    try:
        return BUILTIN[name].copy()
    except KeyError:
        raise KeyError(f"unknown built-in palette: {name!r}") from None


def builtin_names() -> list[str]:
    """Return the sorted names of every built-in palette."""
    return sorted(BUILTIN)
