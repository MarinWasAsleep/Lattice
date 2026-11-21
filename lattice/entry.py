"""Entry-point factory shared by the Lattice shells.

``python -m lattice.modes.glitch`` and ``python -m lattice.modes.glyph`` behaved
identically: with a verb
on the command line run the CLI, without one open the window. Only the package name differed.
Both modules now build their entry point here, so the routing rule — and the laziness that
keeps a CLI invocation from importing Qt — is written once.

The imports stay inside the function on purpose: ``render`` must work on a machine where the
GUI extras are absent, and both app modules are only touched on the branch that needs them.
"""

from __future__ import annotations

import sys
from collections.abc import Callable


def entry_point(package: str) -> Callable[[list[str] | None], int]:
    """Return a ``main`` for `package`: CLI when a verb is given, the GUI otherwise."""

    def main(argv: list[str] | None = None) -> int:
        """Run the CLI when a verb is given, the GUI otherwise, and return the exit code."""
        arguments = list(sys.argv[1:] if argv is None else argv)
        if arguments:
            module = __import__(f"{package}.cli", fromlist=["main"])
            return int(module.main(arguments))
        module = __import__(f"{package}.app", fromlist=["main"])
        return int(module.main([]))

    return main


__all__ = ["entry_point"]
