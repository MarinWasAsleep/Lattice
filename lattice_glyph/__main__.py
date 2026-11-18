"""Entry point of Lattice Glyph: ``python -m lattice_glyph`` starts the window.

With a verb on the command line it runs the CLI instead, so ``python -m lattice_glyph
render …`` works before the distribution is installed; without one it opens the window.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the CLI when a verb is given, the GUI otherwise, and return the exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        from lattice_glyph.cli import main as cli_main

        return cli_main(arguments)
    from lattice_glyph.app import main as app_main

    return app_main([])


if __name__ == "__main__":
    sys.exit(main())
