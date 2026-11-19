"""Source pre-processing: Pixel Snapper and descreen (CONTRACT §23)."""

from lattice.modes.dither.preprocess.descreen import descreen
from lattice.modes.dither.preprocess.grid import detect_grid, snap_to_grid

__all__ = ["descreen", "detect_grid", "snap_to_grid"]
