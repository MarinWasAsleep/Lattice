"""Entry point of Lattice: the window when given nothing, the command line otherwise.

``python -m lattice`` behaves like the frozen binary, which matters because everything else in
the project — the specs, the tests, the documentation — describes one program. With arguments
the CLI runs (``lattice dither render …``); with none, the window opens on the three tabs.

The imports stay inside the branches: a ``render`` call must work on a machine with no GUI
toolkit installed, and opening the window must not pay for the CLI's argument parser.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the CLI when arguments are given, the window otherwise."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        from lattice.cli import main as cli_main

        return int(cli_main(arguments))
    from lattice.app import main as gui_main

    return int(gui_main([]))


if __name__ == "__main__":
    raise SystemExit(main())
