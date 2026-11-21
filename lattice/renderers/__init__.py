"""Built-in CellRenderer implementations."""

from __future__ import annotations

from lattice.cell import (  # noqa: F401  (re-exported for callers)
    CellGrid,
    CellRenderer,
    FloatFrameRenderer,
    RenderStyle,
    get_renderer,
    list_renderers,
    register_renderer,
)
from lattice.renderers.pixel import PixelRenderer, register_pixel_renderer

__all__ = [
    "CellGrid",
    "CellRenderer",
    "FloatFrameRenderer",
    "GlyphShapeRenderer",
    "PixelRenderer",
    "RenderStyle",
    "get_renderer",
    "list_renderers",
    "register_pixel_renderer",
    "register_renderer",
]

register_pixel_renderer()
from lattice.renderers.bitmask import register_bitmask_renderers  # noqa: E402, F401  (bitmask family self-registers on import; DEV-208 L8)
from lattice.renderers.glyph_ramp import GlyphRampRenderer as GlyphRampRenderer  # noqa: E402
from lattice.renderers.glyph_shape import GlyphShapeRenderer  # noqa: E402  (L7 glyph_shape self-registers on import)
from lattice.renderers.text import TextRenderer as TextRenderer  # noqa: E402  (L9 text self-registers on import)
