"""Renderer option metadata of Lattice Glyph: what the panel shows and what it writes.

The tables below mirror the option names and defaults documented in §9 and §10 for the
renderers the core registers. They are the *view* side only: ``clean()`` writes a style
dict the renderers accept, and the panel drops every option still at its default so a
preset stays minimal. ``defaults_for()`` must render exactly like ``{}`` — a test pins it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["text", "colour", "float", "int", "bool", "choice"]

TRANSPARENT = "transparent"
RAMP_HINT = "darkest character first"
COLOUR_HINT = "#rrggbb or transparent"
_HEX6 = re.compile(r"#[0-9a-fA-F]{6}\Z")
_HEX8 = re.compile(r"#[0-9a-fA-F]{8}\Z")
# glyph_ramp also accepts #rrggbbaa and 'transparent' (§9); the other renderers
# parse exactly six hex digits — the validator mirrors the renderers' own parsers.
_ALPHA_COLOURS = frozenset({"glyph_ramp"})


@dataclass(frozen=True)
class OptionSpec:
    """One renderer option: its style key, its widget kind, its default and its bounds."""

    key: str
    label: str
    kind: Kind
    default: object = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    nullable: bool = False
    hint: str = ""


_RAMP = (
    OptionSpec("ramp", "Ramp", "text", "@%#*+=-:. ", hint=RAMP_HINT),
    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
    OptionSpec("fg", "Foreground", "colour", "#000000", hint=COLOUR_HINT),
    OptionSpec("bg", "Background", "colour", "#ffffff", hint=COLOUR_HINT),
    OptionSpec(
        "mode", "Mode", "choice", "mono",
        choices=("mono", "fg_colour", "bg_colour", "palette"),
        hint="palette = each glyph takes its cell colour",
    ),
    OptionSpec("offset", "Offset", "float", 0.0, minimum=-1.0, maximum=1.0, step=0.05),
    OptionSpec("invert", "Invert", "bool", False),
)

_SHAPE = (
    OptionSpec("alphabet", "Alphabet", "text", "", nullable=True,
               hint="empty = every printable ASCII character"),
    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
    OptionSpec("normalise", "Normalise by the alphabet maximum", "bool", True),
)

_BITMASK = (
    OptionSpec("threshold", "Threshold", "float", 0.5, minimum=0.0, maximum=1.0, step=0.05),
    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
)

_TEXT = (
    OptionSpec(
        "text", "Paragraph", "text",
        "Lattice renders a paragraph in a real font, one glyph at a time.",
    ),
    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
    OptionSpec("size", "Point size", "int", 0, minimum=0, maximum=512, nullable=True,
               hint="0 = fitted to the cells"),
    OptionSpec("line_distance", "Line distance", "float", 1.2, minimum=0.5, maximum=3.0,
               step=0.05),
    OptionSpec("kerning", "Kerning", "float", 1.0, minimum=0.0, maximum=2.0, step=0.05),
    OptionSpec("size_mode", "Size", "choice", "variable", choices=("fixed", "variable")),
    OptionSpec("weight_mode", "Weight", "choice", "variable", choices=("fixed", "variable")),
    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
    OptionSpec("seed", "Seed", "int", 0, minimum=0, maximum=9999),
)

OPTIONS: dict[str, tuple[OptionSpec, ...]] = {
    "pixel": (),
    "glyph_ramp": _RAMP,
    "glyph_shape": _SHAPE,
    "braille": _BITMASK,
    "sextant": _BITMASK,
    "quadrant": _BITMASK,
    "half_block": _BITMASK,
    "text": _TEXT,
}


def specs_for(renderer: str) -> tuple[OptionSpec, ...]:
    """Return the options of renderer, or no option for a renderer this table does not name."""
    return OPTIONS.get(renderer, ())


def defaults_for(renderer: str) -> dict:
    """Return every option of renderer at its declared default, as a probe of the table."""
    resolved: dict = {}
    for spec in specs_for(renderer):
        value = _coerce(spec, spec.default)
        if value is not None:
            resolved[spec.key] = value
    return resolved


def clean(renderer: str, values: Mapping) -> dict:
    """Return the style dict of renderer: known keys only, coerced, defaults dropped."""
    cleaned: dict = {}
    for spec in specs_for(renderer):
        if spec.key not in values:
            continue
        value = _coerce(spec, values[spec.key])
        if value is None or value == spec.default:
            continue
        cleaned[spec.key] = value
    return cleaned


def _coerce(spec: OptionSpec, value: object) -> object | None:
    """Coerce one option to its declared type, or return None when it is unset.

    A text option is kept verbatim: a ramp's trailing space is a real glyph, and stripping
    it would silently change what the renderer draws.
    """
    if spec.kind == "bool":
        return bool(value)
    if spec.kind == "choice":
        if value not in spec.choices:
            raise ValueError(f"{spec.key} must be one of {spec.choices}, got {value!r}")
        return str(value)
    if spec.kind == "float":
        return float(value)  # type: ignore[arg-type]
    if spec.kind == "int":
        number = int(value)  # type: ignore[arg-type]
        return None if spec.nullable and number <= 0 else number
    text = "" if value is None else str(value)
    return None if spec.nullable and not text.strip() else text


def valid(renderer: str, spec: OptionSpec, text: str) -> bool:
    """Return True when text is a usable value of one option of renderer.

    The rules mirror what the renderers themselves accept (§9, §10): a colour must
    parse (plus 'transparent' and #rrggbbaa for glyph_ramp), a ramp must not be
    empty, and a font path must name an existing file. Every other option is
    accepted verbatim.
    """
    if spec.kind == "colour":
        cleaned = text.strip().lower()
        if _HEX6.fullmatch(cleaned) is not None:
            return True
        return renderer in _ALPHA_COLOURS and (
            cleaned == TRANSPARENT or _HEX8.fullmatch(cleaned) is not None
        )
    if spec.key == "ramp":
        return bool(text)
    if spec.key == "font":
        return not text or Path(text).is_file()
    return True


def invalid_hint(renderer: str, spec: OptionSpec) -> str:
    """Return the one-line hint to show while one option value is not usable."""
    if spec.kind == "colour":
        allowed = "#rrggbbaa or transparent" if renderer in _ALPHA_COLOURS else "#rrggbb"
        return f"{spec.key} must be {allowed}"
    if spec.key == "ramp":
        return "the ramp must not be empty"
    if spec.key == "font":
        return "the font path must name an existing file"
    return ""


__all__ = ["OptionSpec", "OPTIONS", "clean", "defaults_for", "invalid_hint", "specs_for",
           "valid"]
