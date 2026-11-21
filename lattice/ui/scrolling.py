"""One scrolling page per dock tab: a short window costs a scrollbar, not a cut-off control.

The settings panels were plain widgets stacked vertically. On a 1366x768 laptop the tallest of
them asked for 686 pixels, which pushed the whole window past the screen and put the status bar
out of reach. A panel cannot shrink below the sum of its children's minima, so the fix is not to
squeeze it harder — it is to put it in a viewport that scrolls when the height is not there.

Two rules make the difference between "it scrolls" and "it silently collapses":

* ``setWidgetResizable(True)`` so the panel keeps stretching above its own minimum: in a tall
  window nothing changes, the stretch factors still apply.
* a *usable* minimum on the scrollable children. A ``QListWidget`` minimum is about ten pixels,
  so without a floor the panel would compress to a sliver instead of scrolling, and the scrollbar
  would never appear. That floor is set in the stylesheet, not here.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QTabWidget, QWidget

# Tight margins: every pixel of padding is taken from the canvas on a small screen.
PANEL_MARGIN = 6
PANEL_SPACING = 4


def scrolled(panel: QWidget) -> QScrollArea:
    """Wrap one panel in a scroll area and tighten its top-level layout.

    The margins and spacing of a layout cannot be set from a stylesheet, so they are set here —
    this function is the one place that decides how much air a panel gets.
    """
    layout = panel.layout()
    if layout is not None:
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.setSpacing(PANEL_SPACING)
    area = QScrollArea()
    area.setObjectName("panel_scroll")
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    # Not AlwaysOff: the panel is exactly as wide as the viewport, and a vertical bar would clip
    # its right edge rather than make the page narrower.
    area.setWidget(panel)
    return area


def page_of(tabs: QTabWidget, index: int) -> QWidget:
    """Return the panel of tab index, looking through its scroll area.

    Callers that need the panel itself — to read its values, to connect a signal — must not
    assume the tab holds it directly.
    """
    page = tabs.widget(index)
    return page.widget() if isinstance(page, QScrollArea) else page


def unwrap(area: QScrollArea) -> QWidget | None:
    """Return the panel inside a scroll area, or None when there is none."""
    return area.widget() if isinstance(area, QScrollArea) else None


__all__ = ["PANEL_MARGIN", "PANEL_SPACING", "page_of", "scrolled", "unwrap"]
