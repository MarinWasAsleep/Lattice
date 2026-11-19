"""Entry point of Lattice Glyph: ``python -m lattice_glyph`` starts the window.

With a verb on the command line it runs the CLI instead, so ``python -m lattice_glyph
render …`` works before the distribution is installed; without one it opens the window.
The routing rule itself is shared: ``lattice_core.entry``.
"""

from __future__ import annotations

import sys

from lattice_core.entry import entry_point

main = entry_point("lattice_glyph")

if __name__ == "__main__":
    sys.exit(main())
