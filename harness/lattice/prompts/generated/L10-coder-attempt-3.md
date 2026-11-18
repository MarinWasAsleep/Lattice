# Coder prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are a senior Python engineer implementing one task of the Lattice project: a family of free,
open-source desktop applications that transform images, each running standalone and also plugging
into the ArtCraft suite (Python + numpy + numba + Pillow + PySide6, Windows and Linux).

The suite has four packages: `lattice-core` (the shared engine), `lattice-dither` (the existing
dithering application, 33 algorithms, 10 effects, ~1212 passing tests), `lattice-glyph` and
`lattice-glitch` (new). You work alone on this task; other tasks run in parallel on other files.

HARD RULES
1. Write only the files listed in `owns`. Any other file you need changed → DEVIATIONS block, not code.
2. Follow the contract excerpts exactly: names, signatures, dtypes, value ranges, ordering, error types.
   If the contract is silent, choose the simplest conservative behaviour and record it as E1.
   If the task is impossible without changing the contract, output no FILE blocks, only an E2 deviation.
3. No new dependency. No network. Only numpy, numba (where allowed), Pillow, PySide6, stdlib, pytest.
   `lattice-core` base install must not import PySide6; Qt lives behind the `[ui]` extra.
4. **Core must not import any application.** `lattice_core` may not reference `lattice_dither`,
   `lattice_glyph` or `lattice_glitch`. If you need application-specific behaviour in core, that is
   an E8 deviation: stop and declare it.
5. **Every application must work with no host present.** A missing ArtCraft, a refused connection or
   an absent token file is a normal state, never a crash. If your change makes an app depend on a
   running host, that is an E9 deviation.
6. Each file ≤ 400 lines, each function ≤ 60 lines, typed public API, 1 to 3 line docstrings.
7. Tests: cover every `accept` item of the card, deterministic seeds, fast.
8. **Do not regress the dithering application.** Any behaviour that existed before your task must
   still hold. If your change alters a 1.0 or 1.1 output, that is an E6 deviation: stop and declare
   it, do not ship it.
9. Output full file contents (no diffs, no ellipsis, no "rest unchanged"). Nothing outside the blocks below.
10. Do not explain your code. NOTES is for facts the reviewer needs, ≤ 10 lines.

OUTPUT FORMAT
```
=== FILE: <relative path> ===
<complete content>
=== END FILE ===
(repeat per owned file you write)
=== NOTES ===
<≤ 10 lines or "none">
=== DEVIATIONS ===
<"none", or one block per deviation:
class: E1|E2|E3|E4|E5|E6|E8|E9
facts: <quote the contract or card line involved>
assumption_or_proposal: <...>
(E3 scope : déclarer une sortie hors `owns` ne l'autorise pas — G4 et le relecteur décident.
E7 product : déclarée par le relecteur ou l'humain, jamais par le codeur.)
```

CONTRACT EXCERPTS (version 0.1.0)

## §9 Glyph renderers

Four renderers, one per mechanism.

**`glyph_ramp`** — one monospace character per cell. `luma` (S2, decided 2026-11-16) indexes an
ordered ramp, darkest first, independently of the palette: a black/white palette still uses the
full ramp. Options: `ramp` (string), `font` (path), `fg`/`bg` (colour or `transparent`),
`mode` (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset` (float, shifts the
luma-to-glyph mapping), `invert` (bool). There is no `size` option (H11, decided 2026-11-16):
the glyph font size is derived from `cell_h` (§5 step 6), so each glyph covers its cell exactly.

- The ramp contract is explicit: **darkest character first, lightest last**. A ramp that violates
  it is not detected, it is documented.
- `offset` is animatable and is the cheapest way to make a still image shimmer.
- Aspect correction uses `cell_aspect()`; the default font ratio is 1/2 (width/height).

**`glyph_shape`** — one monospace character per cell, chosen by shape rather than by density.

- For each glyph, place `k = 6` sampling circles inside the cell (top/middle/bottom × left/right).
  For each circle, sample many points and compute the fraction inside the glyph's ink. That is the
  glyph's shape vector.
- **Normalise each component by the maximum across the alphabet.** Without this every vector
  clusters in the bottom-left and every cell maps to the same few characters.
- Per cell, compute the same vector from `samples` and take the nearest neighbour.
- Shape vectors are precomputed per (font, size) and cached at module level.
- Budget: 1024×1024, 64 glyphs, under 200 ms after warm-up. If missed, a precomputed lookup table
  over quantised vectors is allowed.

**`bitmask`** — sub-cell dots. One code path, four geometries:

| Geometry | Sub-grid | Codepoints |
|---|---|---|
| `braille` | 2×4 | U+2800 + bitmask |
| `sextant` | 2×3 | U+1FB00..U+1FB3B |
| `quadrant` | 2×2 | U+2596..U+259F |
| `half_block` | 1×2 | U+2580, U+2584, U+2588 |

Threshold `samples` into on/off sub-dots. Options: `threshold` (0..1), `fg`/`bg`. The sub-dot
decision belongs to the algorithm, run at subgrid resolution (S3): there is no `dither` option
(removed; H11 coherence pass).

**`pixel`** — one solid square per cell. This is Lattice Dither's current behaviour, expressed through
the abstraction. It must reproduce the 1.0 output byte for byte.



TASK CARD

### L10 · Glyph set browser and non-Latin ramps
- wave: 1 · deps: L6 · executor: OMH capable · review: light · size: M
- owns: `lattice_core/ui/glyph_browser.py`, `lattice_core/data/ramps.json`,
  `tests/test_ramps.py`
- context: §9
- spec: a browsable catalogue of glyph sets with a **live preview of the actual ramp rendered in the
  current font**, which almost nobody ships. Categories: classic ASCII, numbers, symbols, blocks,
  geometric, braille, playing cards, and non-Latin ramps (Japanese, Korean, Chinese, Russian,
  German, French, Spanish). `ramps.json` holds the data; the browser renders it.
- accept:
  - `ramps.json` validates against a schema test and every ramp is non-empty and darkest-first.
  - the browser renders a preview for every set without raising.
  - at least 8 categories and at least 6 non-Latin ramps are present.
  - selecting a set updates the preview within 100 ms.



CURRENT CONTENT OF `lattice_core/ui/glyph_browser.py`

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


CURRENT CONTENT OF `tests/test_ramps.py`

"""Card L10 acceptance: the glyph ramp catalogue and its browser (§9).

Every accept item is covered: the shipped ``ramps.json`` validates against the schema test
and every ramp is non-empty and darkest-first; the browser renders a preview for every set
without raising; at least eight categories and six non-Latin ramps are shipped; selecting a
set repaints the preview in under 100 ms. "Darkest first" is checked as documented data —
each ramp is an ordered subsequence of its category ladder — never by measuring glyph ink,
which is font-dependent (§9).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lattice_core.ui import glyph_browser as module  # noqa: E402
from lattice_core.ui.glyph_browser import (  # noqa: E402
    DATA_FILE,
    MIN_CATEGORIES,
    MIN_NON_LATIN_RAMPS,
    PREVIEW_CELL,
    SCHEMA,
    Catalogue,
    GlyphBrowser,
    load_catalogue,
    render_ramp_preview,
    validate_catalogue,
)

SELECT_DEADLINE = 0.100  # accept: selecting a set updates the preview within 100 ms


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    """Return the shipped catalogue, parsed once for the whole module."""
    return load_catalogue()


def document() -> dict:
    """Return the shipped ramps document as raw JSON."""
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def minimal_document() -> dict:
    """Return the smallest document that satisfies the schema, for mutation tests."""
    categories = [
        {
            "id": f"cat_{at}",
            "name": f"Category {at}",
            "ladder": "@#. ",
            "ramps": [{"id": f"ramp_{at}", "name": "One", "script": "latin", "ramp": "@#. "}],
        }
        for at in range(MIN_CATEGORIES)
    ]
    for at in range(MIN_NON_LATIN_RAMPS):
        categories[at]["ramps"].append(
            {"id": f"nonlatin_{at}", "name": "Two", "script": "japanese", "ramp": "@. "}
        )
    return {"schema": SCHEMA, "categories": categories}


def ramp_ids(catalogue: Catalogue) -> list[str]:
    """Return every ramp id of the catalogue, in display order."""
    return [ramp.id for ramp in catalogue.ramps()]


# --- accept 1: the document validates against the schema --------------------------


def test_shipped_catalogue_validates_against_the_schema(catalogue: Catalogue) -> None:
    """The shipped ramps.json loads as typed objects that name its own schema version."""
    raw = document()
    assert raw["schema"] == SCHEMA == "lattice.ramps/1"
    assert validate_catalogue(raw) == catalogue
    assert [category.id for category in catalogue.categories] == [
        item["id"] for item in raw["categories"]
    ]
    assert len(ramp_ids(catalogue)) == len({ramp.id for ramp in catalogue.ramps()})


def test_data_file_is_found_next_to_the_module_not_the_cwd(tmp_path: Path) -> None:
    """The shipped path derives from __file__, so any working directory loads the same data."""
    expected = Path(module.__file__).resolve().parents[1] / "data" / "ramps.json"
    assert Path(DATA_FILE).resolve() == expected
    assert DATA_FILE.is_file() and DATA_FILE.parent.name == "data"
    previous, expected_ids = Path.cwd(), [item["id"] for item in document()["categories"]]
    load_catalogue.cache_clear()  # force a real read, from a directory holding no data
    os.chdir(tmp_path)
    try:
        assert not Path("lattice_core/data/ramps.json").exists()
        moved = load_catalogue()
        assert [category.id for category in moved.categories] == expected_ids
    finally:
        os.chdir(previous)
        load_catalogue.cache_clear()


def test_catalogue_lookup_is_by_id(catalogue: Catalogue) -> None:
    """Catalogue.get and Catalogue.category resolve ids and name unknown ones in a KeyError."""
    first = catalogue.ramps()[0]
    assert catalogue.get(first.id) is first
    assert catalogue.category(first.category_id).id == first.category_id
    with pytest.raises(KeyError, match="unknown glyph ramp"):
        catalogue.get("no_such_ramp")
    with pytest.raises(KeyError, match="unknown glyph category"):
        catalogue.category("no_such_category")


# --- accept 1: every ramp is non-empty and darkest-first --------------------------


def test_every_ramp_is_non_empty_and_darkest_first(catalogue: Catalogue) -> None:
    """Every ramp has ink, distinct glyphs and follows its ladder from darkest to lightest.

    The check is recomputed here from the raw document rather than trusted from the module:
    each glyph of a ramp must appear in the ladder at an index strictly after the previous
    one, which is the data-level statement of "darkest character first, lightest last".
    """
    raw = document()
    for category, item in zip(catalogue.categories, raw["categories"], strict=True):
        ladder = item["ladder"]
        assert ladder and len(set(ladder)) == len(ladder)
        for ramp in category.ramps:
            assert 2 <= len(ramp.ramp) <= len(ladder)
            positions = [ladder.index(glyph) for glyph in ramp.ramp]
            assert positions == sorted(set(positions)), f"{ramp.id} is not darkest-first"


def test_every_ladder_starts_dense_and_ends_on_blank_paper(catalogue: Catalogue) -> None:
    """A ladder opens on a dense glyph and closes on a space, its documented light end."""
    for category in catalogue.categories:
        assert category.ladder[0] not in " ·", category.id
        assert category.ladder[-1] == " ", category.id
        assert len(category.ladder) >= len(max(category.ramps, key=lambda r: len(r.ramp)).ramp)


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda doc: doc.update({"schema": "lattice.ramps/2"}), "$.schema"),
        (lambda doc: doc["categories"][0].update({"ladder": "@#. .  "}), "$.categories[0].ladder"),
        (lambda doc: doc["categories"][0].update({"ramps": []}), "$.categories[0].ramps"),
        (
            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": " .#@"}),
            "$.categories[0].ramps[0].ramp",
        ),
        (
            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@#@. "}),
            "$.categories[0].ramps[0].ramp",
        ),
        (
            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@"}),
            "$.categories[0].ramps[0].ramp",
        ),
        (
            lambda doc: doc["categories"][0]["ramps"][0].update({"script": "klingon"}),
            "$.categories[0].ramps[0].script",
        ),
        (lambda doc: doc["categories"][0].update({"id": "Not A Slug"}), "$.categories[0].id"),
        (lambda doc: doc["categories"][0]["ramps"][0].pop("name"), "$.categories[0].ramps[0].name"),
        (lambda doc: doc.update({"categories": doc["categories"][:2]}), "$.categories"),
    ],
)
def test_the_schema_rejects_invalid_documents(mutate, path: str) -> None:
    """A broken document raises ValueError naming the offending path of the catalogue."""
    doc = minimal_document()
    mutate(doc)
    with pytest.raises(ValueError) as error:
        validate_catalogue(doc)
    assert path in str(error.value)


def test_minimal_document_is_accepted() -> None:
    """The fixture used by the mutation tests is itself valid, so each case proves one rule."""
    assert len(validate_catalogue(minimal_document()).categories) == MIN_CATEGORIES


# --- accept 3: at least 8 categories and 6 non-Latin ramps -------------------------


def test_the_catalogue_ships_enough_categories_and_non_latin_ramps(
    catalogue: Catalogue,
) -> None:
    """§9 asks for eight categories and six non-Latin ramps; the card names the seven."""
    assert len(catalogue.categories) >= MIN_CATEGORIES == 8
    scripts = {ramp.script for ramp in catalogue.ramps()}
    non_latin = [ramp for ramp in catalogue.ramps() if ramp.script in module.NON_LATIN_SCRIPTS]
    assert len(non_latin) >= MIN_NON_LATIN_RAMPS == 6
    assert {"japanese", "korean", "chinese", "russian", "german", "french", "spanish"} <= scripts
    classic = {category.id for category in catalogue.categories}
    assert {
        "classic_ascii",
        "numbers",
        "symbols",
        "blocks",
        "geometric",
        "braille",
        "playing_cards",
    } <= classic


# --- accept 2: a preview for every set, without raising ----------------------------


def test_every_ramp_renders_a_preview(catalogue: Catalogue) -> None:
    """render_ramp_preview returns one cell per glyph as uint8 RGB, for every shipped ramp."""
    for ramp in catalogue.ramps():
        image = render_ramp_preview(ramp.ramp)
        assert image.dtype.name == "uint8", ramp.id
        assert image.shape == (PREVIEW_CELL[1], PREVIEW_CELL[0] * len(ramp.ramp), 3), ramp.id
        assert 0 <= int(image.min()) and int(image.max()) <= 255
        assert int(image.max()) > int(image.min()), f"{ramp.id} renders as one flat colour"


def test_preview_composites_a_transparent_ink_over_white() -> None:
    """A transparent colour still yields uint8 RGB, white where no ink is drawn."""
    image = render_ramp_preview("@. ", fg="transparent", bg="transparent")
    assert image.shape[2] == 3
    assert int(image.min()) == 255


def test_preview_uses_the_font_it_is_given() -> None:
    """A font path that does not exist is refused instead of silently drawing nothing."""
    with pytest.raises(ValueError, match="font file not found"):
        render_ramp_preview("@. ", font="/nonexistent/font.ttf")


def test_browser_renders_a_preview_for_every_set(qapp: QApplication, catalogue: Catalogue) -> None:
    """Walking every category and every set repaints the preview without raising."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        assert browser.category_list.count() == len(catalogue.categories)
        seen: list[str] = []
        for row, category in enumerate(catalogue.categories):
            browser.category_list.setCurrentRow(row)
            QApplication.processEvents()
            assert browser.set_list.count() == len(category.ramps), category.id
            for at, ramp in enumerate(category.ramps):
                browser.set_list.setCurrentRow(at)
                QApplication.processEvents()
                preview = browser.preview_rgb8()
                assert browser.current_ramp() is ramp
                assert preview is not None and preview.shape[2] == 3
                assert browser.preview_label.pixmap().size().width() == preview.shape[1]
                assert browser.name_label.text() == ramp.name
                seen.append(ramp.id)
        assert seen == ramp_ids(catalogue)
    finally:
        browser.close()


def test_first_selection_is_previewed_on_construction(
    qapp: QApplication, catalogue: Catalogue
) -> None:
    """A fresh browser already shows the first set of the first category."""
    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
    try:
        assert browser.current_ramp() is catalogue.categories[0].ramps[0]
        assert browser.preview_rgb8() is not None
    finally:
        browser.close()


# --- accept 4: selecting a set updates the preview within 100 ms -------------------


def test_selecting_a_set_updates_the_preview_within_100_ms(
    qapp: QApplication, catalogue: Catalogue
) -> None:
    """The measured repaint of a selection stays under the card's 100 ms budget."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        first, second = catalogue.ramps()[0], catalogue.ramps()[-1]
        browser.select_ramp(first.id)  # warm the glyph mask cache of the module
        browser.select_ramp(second.id)
        assert browser.current_ramp() is second
        start = time.perf_counter()
        browser.select_ramp(first.id)
        QApplication.processEvents()
        elapsed = time.perf_counter() - start
        assert browser.current_ramp() is first
        assert elapsed < SELECT_DEADLINE, f"selection took {elapsed * 1000:.1f} ms"
        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(first.ramp))
    finally:
        browser.close()


def test_select_ramp_repaints_when_the_lists_already_sit_there(
    qapp: QApplication, catalogue: Catalogue
) -> None:
    """A silent list (already on that row) still repaints: the preview is not left stale."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        first, second = catalogue.categories[0].ramps[:2]
        browser.select_ramp(first.id)
        browser.set_list.blockSignals(True)  # the lists now point at `second`, the pane at `first`
        browser.set_list.setCurrentRow(1)
        browser.set_list.blockSignals(False)
        assert browser.current_ramp() is first
        browser.select_ramp(second.id)  # setCurrentRow(1) is a no-op, so no signal is emitted
        assert browser.current_ramp() is second
        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(second.ramp))
    finally:
        browser.close()


def test_select_ramp_names_an_unknown_id(qapp: QApplication, catalogue: Catalogue) -> None:
    """An unknown id raises KeyError instead of silently showing something else."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        with pytest.raises(KeyError, match="unknown glyph ramp"):
            browser.select_ramp("no_such_ramp")
    finally:
        browser.close()


def test_ramp_chosen_follows_the_selection(qapp: QApplication, catalogue: Catalogue) -> None:
    """Every selection announces its ramp id, which is how the app learns the choice."""
    browser = GlyphBrowser(catalogue=catalogue)
    chosen: list[str] = []
    browser.ramp_chosen.connect(chosen.append)
    try:
        last = catalogue.categories[-1]
        browser.category_list.setCurrentRow(len(catalogue.categories) - 1)
        browser.set_list.setCurrentRow(len(last.ramps) - 1)
        QApplication.processEvents()
        assert chosen and chosen[-1] == last.ramps[-1].id
    finally:
        browser.close()


def test_set_font_repaints_the_current_ramp(qapp: QApplication, catalogue: Catalogue) -> None:
    """set_font(None) restores the bundled font and keeps the selection."""
    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
    try:
        browser.select_ramp(catalogue.ramps()[1].id)
        browser.set_font(None)
        assert browser.current_ramp() is catalogue.ramps()[1]
        assert browser.preview_rgb8() is not None
    finally:
        browser.close()


RETRY attempt 3 (cycle 2 de revue). Fix exactly what is reported below, change nothing else,
keep passing tests passing. Verdict du pass 2 : FIX, **test-only** — le code produit est jugé
correct sur ses cinq correctifs ; ce sont les TESTS qui ne prouvent rien.

CE QUI EST EXIGÉ, FINDING PAR FINDING

1. major tests/test_ramps.py:223 `test_every_ramp_renders_a_preview` — il n'asserte que dtype,
   shape et « pas une seule couleur ». Il passe même si toutes les cellules sont identiques ou
   mal mappées. À remplacer par une preuve de MAPPAGE : pour une rampe donnée, découper l'image en
   `len(ramp)` cellules de largeur `PREVIEW_CELL[0]` et asserter que la cellule i correspond bien au
   glyphe i (par exemple : la couverture d'encre décroît monotone le long de la rampe pour une rampe
   classique dense→espace, ET deux cellules non adjacentes de glyphes différents ne sont pas
   identiques). Si la police par défaut rend certains glyphes identiques (ton argument des blocs),
   choisis une rampe ASCII classique pour la preuve de mappage et garde le balayage « ne lève pas »
   comme test séparé, nommé comme tel.

2. major tests/test_ramps.py:285 `test_selecting_a_set_updates_the_preview_within_100_ms` — il
   pré-chauffe le cache avec la première ET la dernière rampe puis chronomètre la première : il ne
   mesure qu'un cache hit. À corriger : chronométrer une sélection dont la rampe n'a JAMAIS été
   rendue, ou vider explicitement le cache avant (`load_catalogue.cache_clear()` ne suffit pas —
   c'est le cache de glyphes du module renderer qu'il faut viser ; s'il n'est pas exposé, chronomètre
   la première sélection après construction du widget sur une rampe non encore dessinée et dis en
   NOTES quelle propriété tu mesures réellement).

3. minor `glyph_browser.py:316` — `select_ramp` vers une autre catégorie déclenche
   `_on_category_changed`, qui sélectionne la ligne 0 de la nouvelle catégorie : le widget rend et
   émet `ramp_chosen` pour la MAUVAISE rampe avant d'arriver à la bonne. Corrige (bloque les signaux
   pendant la bascule, ou sélectionne la ligne cible avant le repaint) et ajoute un test qui compte
   les émissions de `ramp_chosen` d'une sélection inter-catégories : une seule, la bonne.

4. minor `glyph_browser.py:193` — `Path(target).open(...)` sur un objet déjà `Path` ; `Catalogue.get`
   et `Catalogue.category` reconstruisent un dict à chaque appel. Nettoyage.

5. minor tests/test_ramps.py:232 — le correctif du buffer QImage (`.copy()`) n'a aucun test capable
   d'échouer sur l'ancien code. Ajoute un test qui échouerait sur un QImage construit sur un tampon
   temporaire : garder la référence du buffer, forcer une relecture du pixmap après que le temporaire
   serait mort (par exemple en provoquant un GC), et asserter que les pixels sont toujours ceux de
   la rampe. Si tu juges qu'aucun test déterministe ne peut attraper ça en Python, dis-le en
   déviation E1 avec la raison — ne laisse pas un trou muet.

CONTRAINTE : `tests/test_ramps.py` reste ≤ 400 lignes et chaque fonction ≤ 60 lignes ;
`glyph_browser.py` reste ≤ 400 lignes et ruff-clean (le SEUL rouge du dépôt doit rester
`text.py`, qui appartient à une autre carte en cours).

FINDINGS DU REVIEWER (verbatim)
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "tests/test_ramps.py",
      "line": 182,
      "what": "test_every_ramp_renders_a_preview only checks dtype, shape and 'not one flat colour'. It never checks that cell i shows ramp[i], or that the cells differ from each other.",
      "why": "The preview is the point of the card. The module passes `srgb_to_linear(positions)` as luma, and the test would still pass if the luma transform were wrong or every cell drew the same glyph. Only one inked pixel is needed for `max > min`. A wrong luma-to-glyph mapping would also not be caught.",
      "fix": "Render each ramp and slice the image into columns of width PREVIEW_CELL[0]. Assert that the column ink pattern equals what `glyph_ramp` draws for that glyph alone (for example a 1-glyph ramp rendered separately). At minimum assert that distinct glyphs of a ramp, one with distinct masks, give distinct column bytes."
    },
    {
      "severity": "major",
      "file": "tests/test_ramps.py",
      "line": 243,
      "what": "The 100 ms test warms the cache with the first and last ramp, then times the first one again. It therefore measures only a cache hit.",
      "why": "Accept says 'selecting a set updates the preview within 100 ms'. A cold selection of a CJK, braille or card ramp (glyph rasterisation and font fallback) is never timed, so the budget is unproven for the path a user actually hits.",
      "fix": "Time every ramp once after a single global warm-up. Alternatively time the cold selection of each category's first ramp and assert the maximum is under 100 ms. If the cold cost is too high, pre-warm the glyph masks off-thread."
    },
    {
      "severity": "minor",
      "file": "lattice_core/ui/glyph_browser.py",
      "line": 316,
      "what": "`select_ramp` across categories triggers `_on_category_changed`, which selects row 0 of the new category. That renders and emits `ramp_chosen` for the wrong ramp, and then the target ramp is rendered and emitted a second time.",
      "why": "A host listening to `ramp_chosen` sees a spurious intermediate choice, and every cross-category selection renders the preview twice. The 100 ms budget gets less headroom.",
      "fix": "Wrap the programmatic selection in `blockSignals` on both lists, refill the set list by hand, then call `_show` once. Decide explicitly whether programmatic selection should emit `ramp_chosen`."
    },
    {
      "severity": "minor",
      "file": "lattice_core/ui/glyph_browser.py",
      "line": 193,
      "what": "`Path(target).open(...)` wraps a value that is already a Path. `Catalogue.get` and `Catalogue.category` rebuild a dict on every call.",
      "why": "Redundant code, no wrong result.",
      "fix": "Use `target.open(...)`. Build the id indexes once."
    },
    {
      "severity": "minor",
      "file": "tests/test_ramps.py",
      "line": 232,
      "what": "The `_pixmap` dangling-buffer fix (defect 4) has no test that can fail on the old code.",
      "why": "`QImage(...).copy()` is the fix, but the test only compares pixmap width. Reading from a freed buffer may not show up under offscreen Qt.",
      "fix": "Accept that it cannot be tested, or assert the pixmap pixel content (`toImage()`) equals `preview_rgb8` after a `gc.collect()`."
    }
  ],
  "regression": "none — two new files plus a package-data line; no existing module is modified. The suite is reported green (1941). I did not re-run it.",
  "renderer_invariants": "all six hold — the module only calls `get_renderer(\"glyph_ramp\").render(grid, palette, style)` on locally built inputs. It builds a fresh CellGrid and _BW per call and mutates nothing it was given. Output size is cols*cell_w by cell_h, and the test asserts that shape. Not re-verified against the renderer source.",
  "tests_that_cannot_fail": [
    "test_every_ramp_renders_a_preview: the `max > min` check passes even if all cells are identical or wrongly mapped",
    "test_selecting_a_set_updates_the_preview_within_100_ms: measures only a warm, cached selection",
    "Defect 4 (dangling QImage buffer): no test can fail on the old code"
  ],
  "notes": "I could not run anything (the command needed approval), so this is static review only. I did not run the old WIP.\nYour five fixes, from the diff and tests:\n1. Transparent colours: fixed. The test asserts shape[2]==3 and min==255, which fails on the old HxWx4 output. It only covers fg and bg both transparent.\n2. Stale preview on the same row: fixed. The blocked-signals test fails on the old code.\n3. `_ordered` path: fixed. The mutation test matches `ramps[0].ramp`, so it fails on the old text.\n4. QImage buffer: fixed by `.copy()`, but no test can fail on it.\n5. Cached `load_catalogue`: done. The cwd test calls `cache_clear`, which would raise AttributeError on the old code, so it fails for a different reason.\nNo E8 or E9 deviation: the module imports only lattice_core and Qt, and nothing needs the host."
}

