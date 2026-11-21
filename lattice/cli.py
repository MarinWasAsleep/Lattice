"""The single command line of Lattice: ``lattice <mode> <verb> …``.

Lattice 1.0 ships one console script. Previously each shell carried its own executable —
``lattice-dither-cli``, ``lattice-glyph-cli``, ``lattice-glitch-cli`` — over three nearly
identical ``cli.py`` files. The verbs were already shared through ``lattice.cli_shared``; what
was still duplicated was the *dispatch*, so that is what this module owns now.

The mode is the first argument and is simply prepended to the rest, which means every existing
per-mode command keeps working unchanged one level down:

    lattice dither render --preset p.json --in a.png --out b.png
    lattice glyph presets list
    lattice glitch loop  --preset p.json --in a.png --out c.gif --frames 8

No verb and no mode imports Qt: rendering on a headless machine stays possible.
"""

from __future__ import annotations

import importlib
import sys

MODES: tuple[str, ...] = ("dither", "glyph", "glitch")
PER_MODE: dict[str, str] = {
    "dither": "Lattice Dither — dithering studio: error diffusion, ordered, halftone, palettes",
    "glyph": "Lattice Glyph — glyph, bitmask and text rendering",
    "glitch": "Lattice Glitch — feedback, displacement and signal degradation",
}


def _usage(stream) -> None:
    """Print the top-level usage: the modes, then what each one does."""
    prog = "lattice"
    print(f"usage: {prog} <mode> [args …]", file=stream)
    print(f"       {prog} --version", file=stream)
    print(file=stream)
    print("modes:", file=stream)
    for mode in MODES:
        print(f"  {mode:<8} {PER_MODE[mode]}", file=stream)
    print(file=stream)
    print(f"run '{prog} <mode> --help' for the verbs of one mode", file=stream)


def main(argv: list[str] | None = None) -> int:
    """Route to one mode's command line and return its exit code.

    ``--version`` and ``--help`` are answered here, without importing a mode, so the answer
    stays cheap and cannot fail because one mode's dependencies are missing.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)

    if not arguments:
        _usage(sys.stderr)
        return 1

    if arguments[0] in {"-h", "--help", "help"}:
        _usage(sys.stdout)
        return 0

    if arguments[0] in {"-V", "--version"}:
        from lattice import __version__

        print(f"lattice {__version__}")
        return 0

    mode, rest = arguments[0], arguments[1:]
    if mode not in MODES:
        print(f"lattice: unknown mode {mode!r}", file=sys.stderr)
        print(f"expected one of: {', '.join(MODES)}", file=sys.stderr)
        return 1

    # The mode's own command line is unchanged: it still parses `render`, `batch`, … itself.
    module = importlib.import_module(f"lattice.modes.{mode}.cli")
    return int(module.main(rest))


if __name__ == "__main__":
    raise SystemExit(main())
