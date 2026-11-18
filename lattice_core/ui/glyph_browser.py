"""Browsable catalogue of glyph ramps, previewed in the current font (§9, card L10).

``lattice_core/data/ramps.json`` documents one master ladder per category and every ramp is an
ordered subsequence of it, so "darkest first" is documented data, never detected per font. The
data path derives from ``__file__``. Part of ``lattice_core.ui``: it needs the ``[ui]`` extra.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NoReturn

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lattice_core import color
from lattice_core.cell import CellGrid, RenderStyle, get_renderer
from lattice_core.renderers import glyph_ramp  # noqa: F401  (self-registers "glyph_ramp")
from lattice_core.types import RGB8

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "ramps.json"
SCHEMA, MIN_CATEGORIES, MIN_NON_LATIN_RAMPS = "lattice.ramps/1", 8, 6
NON_LATIN_SCRIPTS = frozenset({"japanese", "korean", "chinese", "russian", "german", "french",
                               "spanish"})
SCRIPTS = frozenset({"latin", "braille"}) | NON_LATIN_SCRIPTS
PREVIEW_CELL = (18, 36)
DEFAULT_FG, DEFAULT_BG = "#111114", "#ffffff"
HINT_TEXT = "Pick a category, then a set: the preview draws that ramp darkest to lightest."
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_BW: np.ndarray = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)


@dataclass(frozen=True)
class GlyphRamp:
    """One named ramp of the catalogue, darkest glyph first."""

    id: str
    name: str
    script: str
    ramp: str
    category_id: str


@dataclass(frozen=True)
class GlyphCategory:
    """One catalogue category: its documented ladder and the ramps cut from it."""

    id: str
    name: str
    ladder: str
    ramps: tuple[GlyphRamp, ...]


@dataclass(frozen=True)
class Catalogue:
    """The whole ramps catalogue, in display order."""

    categories: tuple[GlyphCategory, ...]

    def ramps(self) -> tuple[GlyphRamp, ...]:
        """Return every ramp of the catalogue, category by category."""
        return tuple(ramp for category in self.categories for ramp in category.ramps)

    def get(self, ramp_id: str) -> GlyphRamp:
        """Return the ramp registered under ramp_id, or raise KeyError naming it."""
        found = {ramp.id: ramp for ramp in self.ramps()}.get(ramp_id)
        if found is None:
            raise KeyError(f"unknown glyph ramp: {ramp_id!r}")
        return found

    def category(self, category_id: str) -> GlyphCategory:
        """Return the category registered under category_id, or raise KeyError naming it."""
        found = {category.id: category for category in self.categories}.get(category_id)
        if found is None:
            raise KeyError(f"unknown glyph category: {category_id!r}")
        return found


def _fail(where: str, message: str) -> NoReturn:
    """Raise ValueError naming the offending path of the catalogue document."""
    raise ValueError(f"ramps.json: {where}: {message}")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    """Return value as an object, or raise ValueError naming where it is not one."""
    if not isinstance(value, Mapping):
        _fail(where, "expected an object")
    return value


def _unique(values: list[str], where: str) -> None:
    """Raise ValueError when values holds a duplicate, naming the repeated one."""
    repeated = {value for value in values if values.count(value) > 1}
    if repeated:
        _fail(where, f"duplicate id {min(repeated)!r}")


def _text(node: Mapping[str, object], key: str, where: str) -> str:
    """Return node[key] as a non-empty string, or raise ValueError naming it."""
    value = node.get(key)
    if not isinstance(value, str) or not value:
        _fail(f"{where}.{key}", "expected a non-empty string")
    return value


def _identifier(node: Mapping[str, object], where: str) -> str:
    """Return node["id"] as a lowercase slug, or raise ValueError naming it."""
    value = _text(node, "id", where)
    if not _IDENTIFIER.match(value):
        _fail(f"{where}.id", f"expected a lowercase slug, got {value!r}")
    return value


def _ordered(ramp: str, ladder: str, where: str) -> None:
    """Raise ValueError unless ramp is an ordered subsequence of ladder (§9: darkest first)."""
    at = 0
    for glyph in ramp:
        at = ladder.find(glyph, at)
        if at < 0:
            _fail(f"{where}.ramp", f"{glyph!r} is out of ladder order or absent from the ladder")
        at += 1


def _ramp_entry(data: object, category_id: str, where: str) -> GlyphRamp:
    """Validate one ramp object and return it."""
    node = _mapping(data, where)
    identifier = _identifier(node, where)
    name = _text(node, "name", where)
    script = _text(node, "script", where)
    if script not in SCRIPTS:
        _fail(f"{where}.script", f"expected one of {sorted(SCRIPTS)}, got {script!r}")
    ramp = _text(node, "ramp", where)
    if len(ramp) < 2:
        _fail(f"{where}.ramp", "expected at least two glyphs")
    if len(set(ramp)) != len(ramp):
        _fail(f"{where}.ramp", "contains a repeated glyph")
    return GlyphRamp(identifier, name, script, ramp, category_id)


def _category_entry(data: object, where: str) -> GlyphCategory:
    """Validate one category object, its ladder and every ramp cut from it."""
    node = _mapping(data, where)
    identifier = _identifier(node, where)
    name = _text(node, "name", where)
    ladder = _text(node, "ladder", where)
    if len(set(ladder)) != len(ladder):
        _fail(f"{where}.ladder", "contains a repeated glyph")
    raw = node.get("ramps")
    if not isinstance(raw, list) or not raw:
        _fail(f"{where}.ramps", "expected a non-empty list")
    ramps = tuple(
        _ramp_entry(item, identifier, f"{where}.ramps[{at}]") for at, item in enumerate(raw)
    )
    for at, ramp in enumerate(ramps):
        _ordered(ramp.ramp, ladder, f"{where}.ramps[{at}]")
    return GlyphCategory(identifier, name, ladder, ramps)


def validate_catalogue(data: object) -> Catalogue:
    """Validate one ramps document and return it as typed objects, or raise ValueError.

    Every ramp must be an ordered subsequence of its ladder: the data-level "darkest first".
    """
    root = _mapping(data, "$")
    if root.get("schema") != SCHEMA:
        _fail("$.schema", f"expected {SCHEMA!r}")
    raw = root.get("categories")
    if not isinstance(raw, list):
        _fail("$.categories", "expected a list")
    categories = tuple(_category_entry(item, f"$.categories[{at}]") for at, item in enumerate(raw))
    if len(categories) < MIN_CATEGORIES:
        _fail("$.categories", f"expected at least {MIN_CATEGORIES} categories")
    _unique([category.id for category in categories], "$.categories[].id")
    ramps = [ramp for category in categories for ramp in category.ramps]
    _unique([ramp.id for ramp in ramps], "$.categories[].ramps[].id")
    non_latin = sum(1 for ramp in ramps if ramp.script in NON_LATIN_SCRIPTS)
    if non_latin < MIN_NON_LATIN_RAMPS:
        _fail(
            "$.categories[].ramps[].script",
            f"expected at least {MIN_NON_LATIN_RAMPS} non-Latin ramps",
        )
    return Catalogue(categories)


@cache
def load_catalogue(path: Path | str | None = None) -> Catalogue:
    """Return the shipped catalogue, or the one at path, validated once per path."""
    target = DATA_FILE if path is None else Path(path).expanduser().resolve()
    with Path(target).open(encoding="utf-8") as handle:
        return validate_catalogue(json.load(handle))


def render_ramp_preview(
    ramp: str,
    *,
    font: str | None = None,
    cell: tuple[int, int] = PREVIEW_CELL,
    fg: str = DEFAULT_FG,
    bg: str = DEFAULT_BG,
) -> RGB8:
    """Return the ramp drawn left to right in font by the real ``glyph_ramp`` renderer.

    Always uint8 RGB: a ``transparent`` fg or bg is composited over white.
    """
    count, (cell_w, cell_h) = len(ramp), (int(cell[0]), int(cell[1]))
    positions = (np.arange(count, dtype=np.float32) + 0.5) / np.float32(count)
    luma = color.srgb_to_linear(positions)[None, :]
    grid = CellGrid(
        cols=count, rows=1, cell_w=cell_w, cell_h=cell_h,
        index=np.zeros((1, count), dtype=np.int32),
        coverage=np.zeros((1, count), dtype=np.float32),
        luma=np.ascontiguousarray(luma, dtype=np.float32),
        samples=np.zeros((1, count, 1), dtype=np.float32),
    )
    style = RenderStyle({"ramp": ramp, "font": font, "fg": fg, "bg": bg, "mode": "mono"})
    image = get_renderer("glyph_ramp").render(grid, _BW, style)
    if image.mode == "RGB":
        return np.asarray(image, dtype=np.uint8)
    over = np.asarray(image.convert("RGBA"), dtype=np.float32) / np.float32(255.0)
    alpha = over[:, :, 3:4]
    return color.to_rgb8(over[:, :, :3] * alpha + (np.float32(1.0) - alpha))


def _pixmap(rgb8: RGB8) -> QPixmap:
    """Return a QPixmap holding a private copy of a uint8 RGB array."""
    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
    height, width, stride = int(data.shape[0]), int(data.shape[1]), int(data.strides[0])
    image = QImage(data.data, width, height, stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


def _add(widget: QListWidget, text: str, data: str) -> None:
    """Append an item showing text and carrying data in its user role."""
    item = QListWidgetItem(text)
    item.setData(Qt.ItemDataRole.UserRole, data)
    widget.addItem(item)


class GlyphBrowser(QWidget):
    """Category list, set list and a live preview of every ramp in the current font."""

    ramp_chosen = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        catalogue: Catalogue | None = None,
        font: str | None = None,
        cell: tuple[int, int] = PREVIEW_CELL,
    ) -> None:
        """Build the two lists and the preview pane, then show the first set."""
        super().__init__(parent)
        self.setObjectName("glyph_browser")
        self._catalogue = load_catalogue() if catalogue is None else catalogue
        self._font = font
        self._cell = (int(cell[0]), int(cell[1]))
        self._current: GlyphRamp | None = None
        self._preview: RGB8 | None = None
        self.category_list = QListWidget(self)
        self.category_list.setObjectName("glyph_category_list")
        self.category_list.setAlternatingRowColors(True)
        self.category_list.setMaximumWidth(190)
        self.set_list = QListWidget(self)
        self.set_list.setObjectName("glyph_set_list")
        self.set_list.setAlternatingRowColors(True)
        self.name_label = QLabel("", self)
        self.name_label.setObjectName("glyph_set_name")
        self.preview_label = QLabel(self)
        self.preview_label.setObjectName("glyph_preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(self._cell[1])
        self.ramp_label = QLabel("", self)
        self.ramp_label.setObjectName("glyph_ramp_text")
        self.ramp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_label = QLabel(HINT_TEXT, self)
        self.hint_label.setObjectName("glyph_hint")
        self.hint_label.setWordWrap(True)
        self._build_layout()
        self._populate()

    def catalogue(self) -> Catalogue:
        """Return the catalogue this browser displays."""
        return self._catalogue

    def current_ramp(self) -> GlyphRamp | None:
        """Return the ramp currently previewed, or None before the first selection."""
        return self._current

    def preview_rgb8(self) -> RGB8 | None:
        """Return the pixels of the current preview, or None before the first selection."""
        return None if self._preview is None else self._preview.copy()

    def select_ramp(self, ramp_id: str) -> None:
        """Show ramp_id, selecting its category and set; the repaint is explicit on purpose.

        Lists already pointing at ramp_id emit no signal, so they are not relied on.
        """
        ramp = self._catalogue.get(ramp_id)  # KeyError naming an unknown id
        for row, category in enumerate(self._catalogue.categories):
            ids = [item.id for item in category.ramps]
            if ramp_id not in ids:
                continue
            if self.category_list.currentRow() != row:
                self.category_list.setCurrentRow(row)
            self.set_list.setCurrentRow(ids.index(ramp_id))
            if self._current is not ramp:
                self._show(ramp)
            return

    def set_font(self, font: str | None) -> None:
        """Preview every ramp in font, or in the bundled font when font is None."""
        self._font = font
        if self._current is not None:
            self._show(self._current)

    def _build_layout(self) -> None:
        """Lay out the two lists beside the name, preview and ramp text."""
        lists = QVBoxLayout()
        lists.setSpacing(4)
        lists.addWidget(QLabel("Categories", self))
        lists.addWidget(self.category_list, 1)
        lists.addWidget(QLabel("Sets", self))
        lists.addWidget(self.set_list, 1)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.name_label)
        right.addWidget(self.preview_label)
        right.addWidget(self.ramp_label)
        right.addWidget(self.hint_label)
        right.addStretch(1)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)
        outer.addLayout(lists, 1)
        outer.addLayout(right, 2)

    def _populate(self) -> None:
        """Fill the category list and select the first set of the first category."""
        for category in self._catalogue.categories:
            _add(self.category_list, category.name, category.id)
        self.category_list.currentRowChanged.connect(self._on_category_changed)
        self.set_list.currentRowChanged.connect(self._on_set_changed)
        if self._catalogue.categories:
            self.category_list.setCurrentRow(0)

    def _on_category_changed(self, row: int) -> None:
        """Refill the set list with the ramps of the selected category."""
        self.set_list.blockSignals(True)
        self.set_list.clear()
        if 0 <= row < len(self._catalogue.categories):
            for ramp in self._catalogue.categories[row].ramps:
                _add(self.set_list, ramp.name, ramp.id)
        self.set_list.blockSignals(False)
        if self.set_list.count():
            self.set_list.setCurrentRow(0)

    def _on_set_changed(self, row: int) -> None:
        """Preview the newly selected set and announce it."""
        if not 0 <= row < self.set_list.count():
            return
        ramp = self._catalogue.get(str(self.set_list.item(row).data(Qt.ItemDataRole.UserRole)))
        self._show(ramp)
        self.ramp_chosen.emit(ramp.id)

    def _show(self, ramp: GlyphRamp) -> None:
        """Render ramp in the current font and update every label of the preview pane."""
        self._preview = render_ramp_preview(ramp.ramp, font=self._font, cell=self._cell)
        self._current = ramp
        self.preview_label.setPixmap(_pixmap(self._preview))
        self.name_label.setText(ramp.name)
        self.ramp_label.setText(f"{ramp.ramp!r}")


__all__ = [
    "Catalogue", "DATA_FILE", "GlyphBrowser", "GlyphCategory", "GlyphRamp", "MIN_CATEGORIES",
    "MIN_NON_LATIN_RAMPS", "NON_LATIN_SCRIPTS", "PREVIEW_CELL", "SCHEMA", "load_catalogue",
    "render_ramp_preview", "validate_catalogue",
]
