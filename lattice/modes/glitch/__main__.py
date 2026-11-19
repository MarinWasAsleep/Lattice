"""Entry point of Lattice Glitch: ``python -m lattice.modes.glitch`` starts the window.

With a verb on the command line it runs the CLI instead, so ``python -m lattice.modes.glitch
render …`` works before the distribution is installed; without one it opens the window.
The routing rule itself is shared: ``lattice.entry``.
"""

from __future__ import annotations

import sys

from lattice.entry import entry_point

main = entry_point("lattice.modes.glitch")

if __name__ == "__main__":
    sys.exit(main())
