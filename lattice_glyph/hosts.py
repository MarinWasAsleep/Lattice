"""Host discovery of Lattice Glyph: the single §7 probe, CLI and GUI share it.

The core's ``ArtCraftClient.discover`` already answers None for a host that is not
running; this module adds the typed-error guard the callers need, so every user of the
bridge resolves the host the same way and there is no second copy to drift (L12 FIX:
``pull_image``, ``fetch_image`` and the inlined tries were four versions of this one).
"""

from __future__ import annotations

from lattice_core.bridge import HOSTS, ArtCraftClient, BridgeError

__all__ = ["HOSTS", "discover"]


def discover(host: str) -> ArtCraftClient | None:
    """Return a live client for host, or None for every way a host can be absent (§7)."""
    if host not in HOSTS:
        return None
    try:
        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
    except (BridgeError, OSError, ValueError):
        return None
