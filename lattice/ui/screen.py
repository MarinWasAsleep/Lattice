"""Keep the window inside the screen it is opened on.

A saved geometry is a promise about *the screen it was saved on*. Someone who works on a 2560-wide
monitor and then opens Lattice on a laptop would get a window taller and wider than the display,
with its bottom edge — the status bar, the last row of a panel — physically off the screen and no
way to reach it. The saved rectangle is therefore always reconciled with the current screen.

Pure functions over ``QRect`` so the rule can be tested without a display.
"""

from __future__ import annotations

from PySide6.QtCore import QRect

# A window smaller than this is unusable whatever the screen says.
MIN_USEFUL_SIZE = (640, 480)


def clamp_to_area(rect: QRect, area: QRect) -> QRect:
    """Return rect shrunk to fit inside area, then moved wholly inside it.

    Shrinking comes first: a rect that is too tall must lose height before it can be positioned,
    otherwise it would be pushed to a negative y and its title bar would vanish under the screen
    edge — the classic "the window is there but you cannot grab it" failure.
    """
    width = min(rect.width(), area.width())
    height = min(rect.height(), area.height())
    width = max(width, min(MIN_USEFUL_SIZE[0], area.width()))
    height = max(height, min(MIN_USEFUL_SIZE[1], area.height()))
    x = min(max(rect.x(), area.left()), area.right() - width + 1)
    y = min(max(rect.y(), area.top()), area.bottom() - height + 1)
    return QRect(x, y, width, height)


def fits(rect: QRect, area: QRect) -> bool:
    """Return whether rect lies wholly inside area."""
    return area.contains(rect)


__all__ = ["MIN_USEFUL_SIZE", "clamp_to_area", "fits"]
