"""Host discovery of Lattice Glyph, re-exported from the shared core module.

Glitch and Glyph carried identical copies; the single implementation now lives in
``lattice_core.bridge_hosts``, so a fix applied for one app cannot drift from the other.
"""

from __future__ import annotations

from lattice_core.bridge_hosts import HOSTS, discover

__all__ = ["HOSTS", "discover"]
