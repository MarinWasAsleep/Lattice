"""Lattice: the dithering, glyph and glitch studio.

One distribution, one window, three modes. The engine — renderers, effects, palettes, the
pipeline and the preset format — lives here at the top level; the three modes live under
``lattice.modes`` and share it.
"""

APP_NAME = "Lattice"
__version__ = "1.0.0"

__all__ = ["APP_NAME", "__version__"]
