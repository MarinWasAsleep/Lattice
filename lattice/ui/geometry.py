"""One geometry for the three modes, so the canvas does not jump between tabs.

Each mode used to carry its own dock widths — 418, 340 and 360 pixels for the right panel — so
switching tab moved the canvas edge and the user lost their place. A tool whose subject is an
image must keep the image still while you work; the panels adapt around it, not the reverse.

The values below are one decision, taken once:

* the right panel is wide enough for a labelled field and its value on one line (320), and no
  wider: every pixel it takes is a pixel the image does not get;
* the gallery is a browsing strip, not a workspace: three columns of thumbnails, which is enough
  to compare algorithms without pushing the canvas off-centre;
* the canvas keeps a floor so a narrow window degrades into scrollbars, not into a sliver.
"""

from __future__ import annotations

# Right-hand settings panel. Same value in all three modes.
PANEL_WIDTH = 320

# Left-hand algorithm gallery, used by Dither only. Three columns of 96-pixel thumbnails keep
# the strip narrow enough that the canvas stays the largest thing on screen; four columns pushed
# the gallery to 446 pixels, nearly a third of a 1440-pixel window.
GALLERY_WIDTH = 330
GALLERY_COLUMNS = 3

# Below this the canvas stops shrinking and the view scrolls instead.
CANVAS_MIN_WIDTH = 420

# A vertical scrollbar costs this much width; a dock that scrolls must be that much wider so the
# content keeps its own 320 pixels and no panel ever needs a horizontal bar.
SCROLLBAR_EXTENT = 12
PANEL_DOCK_WIDTH = PANEL_WIDTH + SCROLLBAR_EXTENT

# The height below which the window refuses to shrink: 1366x768 laptops are the target, and the
# status bar must stay reachable there. The width is left to the layout, which needs more.
WINDOW_MIN_HEIGHT = 600

__all__ = [
    "CANVAS_MIN_WIDTH", "GALLERY_COLUMNS", "GALLERY_WIDTH", "PANEL_DOCK_WIDTH",
    "PANEL_WIDTH", "SCROLLBAR_EXTENT", "WINDOW_MIN_HEIGHT",
]
