"""Algorithm gallery of Lattice Dither, bound to the shared core widget.

The widget lives in ``lattice_core.ui.algorithm_gallery``: it was written here, and Dither is
still the only shell that shows it, but the grid, the thumbnail cache and the search box are
not Dither-specific. This module keeps the names Dither's window and tests import, and hands
the core the two things that are: the translation function and the app-data folder.
"""

from __future__ import annotations

from pathlib import Path

from lattice_core.pipeline import PaletteSpec
from lattice_core.registry import list_algorithms
from lattice_core.ui.algorithm_gallery import (
    CACHE_SUFFIX,
    CELL_TIP,
    DEFAULT_PALETTE,
    FAILED_TIP,
    HASH_LENGTH,
    JOIN_MS,
    PLACEHOLDER_COLOR,
    TEST_IMAGE_SIZE,
    THUMB_COLUMNS,
    THUMB_DIR_NAME,
    THUMB_SIZE,
    ThumbnailCell,
    ThumbnailWorker,
    cache_key,
    family_label,
    fold,
    palette_hash,
    params_hash,
    render_thumbnail,
    set_translator,
    test_image,
    thumbnail_for,
)
from lattice_core.ui.algorithm_gallery import AlgorithmGallery as _AlgorithmGallery
from lattice_core.ui.algorithm_gallery import thumbs_dir as _thumbs_dir
from lattice_dither import i18n

APP_DIR_NAME = "LatticeDither"


def thumbs_dir() -> Path:
    """Return Dither's own thumbnail cache directory."""
    return _thumbs_dir(APP_DIR_NAME)


def AlgorithmGallery(  # noqa: N802 - the window and the tests import this name
    parent=None,
    *,
    cache_dir: Path | None = None,
    palette: PaletteSpec | None = None,
    size: int = THUMB_SIZE,
    columns: int = THUMB_COLUMNS,
) -> _AlgorithmGallery:
    """Build the shared grid with Dither's translations and app-data folder.

    A factory rather than a subclass on purpose: ``test_ui_no_duplicates`` forbids a class
    name living in both packages, and a subclass would satisfy the letter of the share while
    keeping a second definition of the same widget.
    """
    set_translator(i18n.tr)
    return _AlgorithmGallery(
        parent,
        cache_dir=cache_dir,
        palette=palette,
        size=size,
        columns=columns,
        app_dir_name=APP_DIR_NAME,
        translate=i18n.tr,
    )


__all__ = [
    "AlgorithmGallery", "list_algorithms", "CACHE_SUFFIX", "CELL_TIP",
    "DEFAULT_PALETTE", "FAILED_TIP",
    "HASH_LENGTH", "JOIN_MS", "PLACEHOLDER_COLOR", "TEST_IMAGE_SIZE",
    "THUMB_COLUMNS", "THUMB_DIR_NAME", "THUMB_SIZE", "ThumbnailCell", "ThumbnailWorker",
    "cache_key", "family_label", "fold", "palette_hash", "params_hash", "render_thumbnail",
    "test_image", "thumbnail_for", "thumbs_dir",
]
