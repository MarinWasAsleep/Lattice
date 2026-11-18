# Reviewer prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are reviewing one task of the Lattice project: a family of free, open-source image-transformation
applications sharing one engine, each running standalone and also plugging into the ArtCraft suite.
You see the task card, the contract sections it must satisfy, the git diff, the gate results and the
coder's notes. You do not see the rest of the repository, and you do not need to.

The dithering application is frozen and shipped (harness 1.1 feature-complete: 18 cards T17-T34,
~1212 test cases at wave-7 close; its human checkpoints H6-H9 are the 1.1 harness's business),
with a public release. Your job is to decide whether this diff can join it.

WHAT TO CHECK, IN THIS ORDER
1. **Contract conformance.** Names, signatures, dtypes, ranges, ordering, error types. A deviation
   from the contract is a blocker even if the tests pass.
2. **Regression.** Does anything that worked before behave differently? Gate G7 (core regression)
   exists for this. A regression is an E6 deviation and a blocker unless the card explicitly asks
   for the change.
3. **The abstraction holds.** Gate G8 checks that every registered `CellRenderer` satisfies §3. Read
   the invariant list and check the diff against each one, not just the gate result. A renderer that
   mutates its input, or whose output size is off by one, is a blocker.
4. **No abstraction leak.** Does `lattice_core` reference an application? Does an application import
   from another application? That is an E8 deviation and a blocker.
5. **No host coupling.** Does the application still work with no ArtCraft running? A missing token
   file, a refused connection or an absent host must be a normal state. That is an E9 deviation and a
   blocker.
6. **Test quality.** Do the tests actually fail on the old code? A test that passes before and after
   the change proves nothing. Look for assertions that restate the implementation, tests that would
   pass with the feature removed, and missing edge cases named in `accept`.
7. **Correctness of the maths.** For renderer and effect cards, check the formulas against the
   contract, not against intuition. Off-by-one in a kernel, a missing normalisation, a wrong colour
   space, a mask applied in the wrong order.
8. **Product quality** (cards L10, L12, L20, L21 only). Is the control discoverable? Does the default
   surprise? Does the message say what to do next? A task can pass every test and still be an E7.
9. **Hygiene.** File length, function length, typing, docstrings, no dead code, no commented-out
   blocks, no debug prints.

SEVERITY
- **blocker**: wrong result, contract violation, regression, crash, data loss, abstraction leak,
  host coupling.
- **major**: missing acceptance item, test that cannot fail, wrong default, misleading message.
- **minor**: style, naming, a docstring that lies.

VERDICT
- `PASS` — no blocker, no major. Minors are listed but do not block.
- `FIX` — at least one blocker or major. The coder gets one more cycle with your findings.
- `ESCALATE` — the task cannot be done as specified, or the fix needs a contract change. Name the
  deviation class (E2, E4, E6, E7, E8, E9).

OUTPUT FORMAT, nothing else:
```json
{
  "verdict": "PASS | FIX | ESCALATE",
  "findings": [
    {"severity": "blocker|major|minor", "file": "...", "line": 0,
     "what": "...", "why": "...", "fix": "..."}
  ],
  "regression": "none | <what changed vs the frozen behaviour>",
  "renderer_invariants": "all six hold | <which one fails and how>",
  "tests_that_cannot_fail": ["..."],
  "notes": "<≤ 5 lines>"
}
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



GATE RESULTS (L10, attempt 2 — codeur mistral deepseek-v4-1-flash-1017)
- Owned tests : 27 passed (tests/test_ramps.py, 0,26 s).
- Suite complète : 1941 passed, 1 skipped (1942 collectés). G3 check_contract : OK.
- G1 ruff : l'arbre porte 1 erreur E501 dans `lattice_core/renderers/text.py:141` — fichier d'une
  AUTRE carte (L9) en cours d'écriture par un autre codeur au moment de la mesure ; ce n'est pas
  imputable à L10. Les deux fichiers de L10 sont ruff-clean (max 99 colonnes, vérifié).
- G4 : le codeur a écrit directement dans le dépôt (convention du harness) et a DÉCLARÉ en E3 le
  seul changement hors owns qu'il jugeait nécessaire : une ligne `[tool.setuptools.package-data]`
  pour embarquer `lattice_core/data/ramps.json` dans la wheel. L'orchestrateur a appliqué cette
  ligne lui-même après vérification par construction de wheel + installation en venv propre.

FAITS VÉRIFIÉS PAR L'ORCHESTRATEUR (indépendamment des NOTES du codeur)
- wheel construite à partir de l'arbre : `lattice_core/data/ramps.json` présent ; installée dans un
  venv vierge, le chemin résolu depuis `__file__` donne site-packages/lattice_core/data/ramps.json,
  et le JSON s'y charge (12 catégories, 30 rampes).
- `glyph_browser.py` = 393 lignes (< 400), `test_ramps.py` = 359 lignes.
- Le module n'est PAS enregistré dans un __init__ applicatif et n'importe aucune application.

DÉFAUTS QUE LE CODEUR DIT AVOIR CORRIGÉS DANS LE WIP (à vérifier, pas à croire)
1. `render_ramp_preview` renvoyait HxWx4 quand fg/bg valait `transparent`, réinterprété en RGB888
   → couleurs corrompues et stride faux ; composite sur blanc, sortie uint8 RGB.
2. `select_ramp` ne repeignait pas quand la ligne sélectionnée était déjà courante (aperçu périmé).
3. `_ordered` citait `$.categories[0].ramp` au lieu de `...ramps[1].ramp`.
4. `_pixmap` gardait un `bytes` temporaire comme buffer de QImage (dangling).
5. `_load`/`load_catalogue` fusionnés en un cache mémoïsé, `cache_clear()` exposé.
Question que je te pose explicitement : ces cinq-là sont-elles réellement corrigées, et les tests
correspondants échouent-ils sur le WIP d'origine ?

lattice_core/data/ramps.json (269 lignes, non inclus dans le diff pour la lisibilité) :
schema "lattice.ramps/1", 12 catégories, 30 rampes. Catégories : classic_ascii, numbers, symbols,
blocks, geometric, braille, playing_cards, japanese, korean, chinese, russian, german_french_spanish.
Vérifié par l'orchestrateur : le fichier est identique octet pour octet au WIP fourni au codeur.

DIFF (les deux fichiers de la carte, créés de zéro contre /dev/null)

diff --git a/lattice_core/ui/glyph_browser.py b/lattice_core/ui/glyph_browser.py
new file mode 100644
index 0000000..8a42a46
--- /dev/null
+++ b/lattice_core/ui/glyph_browser.py
@@ -0,0 +1,393 @@
+"""Browsable catalogue of glyph ramps, previewed in the current font (§9, card L10).
+
+``lattice_core/data/ramps.json`` documents one master ladder per category and every ramp is an
+ordered subsequence of it, so "darkest first" is documented data, never detected per font. The
+data path derives from ``__file__``. Part of ``lattice_core.ui``: it needs the ``[ui]`` extra.
+"""
+
+from __future__ import annotations
+
+import json
+import re
+from collections.abc import Mapping
+from dataclasses import dataclass
+from functools import cache
+from pathlib import Path
+from typing import NoReturn
+
+import numpy as np
+from PySide6.QtCore import Qt, Signal
+from PySide6.QtGui import QImage, QPixmap
+from PySide6.QtWidgets import (
+    QHBoxLayout,
+    QLabel,
+    QListWidget,
+    QListWidgetItem,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_core import color
+from lattice_core.cell import CellGrid, RenderStyle, get_renderer
+from lattice_core.renderers import glyph_ramp  # noqa: F401  (self-registers "glyph_ramp")
+from lattice_core.types import RGB8
+
+DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "ramps.json"
+SCHEMA, MIN_CATEGORIES, MIN_NON_LATIN_RAMPS = "lattice.ramps/1", 8, 6
+NON_LATIN_SCRIPTS = frozenset({"japanese", "korean", "chinese", "russian", "german", "french",
+                               "spanish"})
+SCRIPTS = frozenset({"latin", "braille"}) | NON_LATIN_SCRIPTS
+PREVIEW_CELL = (18, 36)
+DEFAULT_FG, DEFAULT_BG = "#111114", "#ffffff"
+HINT_TEXT = "Pick a category, then a set: the preview draws that ramp darkest to lightest."
+_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
+_BW: np.ndarray = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+
+
+@dataclass(frozen=True)
+class GlyphRamp:
+    """One named ramp of the catalogue, darkest glyph first."""
+
+    id: str
+    name: str
+    script: str
+    ramp: str
+    category_id: str
+
+
+@dataclass(frozen=True)
+class GlyphCategory:
+    """One catalogue category: its documented ladder and the ramps cut from it."""
+
+    id: str
+    name: str
+    ladder: str
+    ramps: tuple[GlyphRamp, ...]
+
+
+@dataclass(frozen=True)
+class Catalogue:
+    """The whole ramps catalogue, in display order."""
+
+    categories: tuple[GlyphCategory, ...]
+
+    def ramps(self) -> tuple[GlyphRamp, ...]:
+        """Return every ramp of the catalogue, category by category."""
+        return tuple(ramp for category in self.categories for ramp in category.ramps)
+
+    def get(self, ramp_id: str) -> GlyphRamp:
+        """Return the ramp registered under ramp_id, or raise KeyError naming it."""
+        found = {ramp.id: ramp for ramp in self.ramps()}.get(ramp_id)
+        if found is None:
+            raise KeyError(f"unknown glyph ramp: {ramp_id!r}")
+        return found
+
+    def category(self, category_id: str) -> GlyphCategory:
+        """Return the category registered under category_id, or raise KeyError naming it."""
+        found = {category.id: category for category in self.categories}.get(category_id)
+        if found is None:
+            raise KeyError(f"unknown glyph category: {category_id!r}")
+        return found
+
+
+def _fail(where: str, message: str) -> NoReturn:
+    """Raise ValueError naming the offending path of the catalogue document."""
+    raise ValueError(f"ramps.json: {where}: {message}")
+
+
+def _mapping(value: object, where: str) -> Mapping[str, object]:
+    """Return value as an object, or raise ValueError naming where it is not one."""
+    if not isinstance(value, Mapping):
+        _fail(where, "expected an object")
+    return value
+
+
+def _unique(values: list[str], where: str) -> None:
+    """Raise ValueError when values holds a duplicate, naming the repeated one."""
+    repeated = {value for value in values if values.count(value) > 1}
+    if repeated:
+        _fail(where, f"duplicate id {min(repeated)!r}")
+
+
+def _text(node: Mapping[str, object], key: str, where: str) -> str:
+    """Return node[key] as a non-empty string, or raise ValueError naming it."""
+    value = node.get(key)
+    if not isinstance(value, str) or not value:
+        _fail(f"{where}.{key}", "expected a non-empty string")
+    return value
+
+
+def _identifier(node: Mapping[str, object], where: str) -> str:
+    """Return node["id"] as a lowercase slug, or raise ValueError naming it."""
+    value = _text(node, "id", where)
+    if not _IDENTIFIER.match(value):
+        _fail(f"{where}.id", f"expected a lowercase slug, got {value!r}")
+    return value
+
+
+def _ordered(ramp: str, ladder: str, where: str) -> None:
+    """Raise ValueError unless ramp is an ordered subsequence of ladder (§9: darkest first)."""
+    at = 0
+    for glyph in ramp:
+        at = ladder.find(glyph, at)
+        if at < 0:
+            _fail(f"{where}.ramp", f"{glyph!r} is out of ladder order or absent from the ladder")
+        at += 1
+
+
+def _ramp_entry(data: object, category_id: str, where: str) -> GlyphRamp:
+    """Validate one ramp object and return it."""
+    node = _mapping(data, where)
+    identifier = _identifier(node, where)
+    name = _text(node, "name", where)
+    script = _text(node, "script", where)
+    if script not in SCRIPTS:
+        _fail(f"{where}.script", f"expected one of {sorted(SCRIPTS)}, got {script!r}")
+    ramp = _text(node, "ramp", where)
+    if len(ramp) < 2:
+        _fail(f"{where}.ramp", "expected at least two glyphs")
+    if len(set(ramp)) != len(ramp):
+        _fail(f"{where}.ramp", "contains a repeated glyph")
+    return GlyphRamp(identifier, name, script, ramp, category_id)
+
+
+def _category_entry(data: object, where: str) -> GlyphCategory:
+    """Validate one category object, its ladder and every ramp cut from it."""
+    node = _mapping(data, where)
+    identifier = _identifier(node, where)
+    name = _text(node, "name", where)
+    ladder = _text(node, "ladder", where)
+    if len(set(ladder)) != len(ladder):
+        _fail(f"{where}.ladder", "contains a repeated glyph")
+    raw = node.get("ramps")
+    if not isinstance(raw, list) or not raw:
+        _fail(f"{where}.ramps", "expected a non-empty list")
+    ramps = tuple(
+        _ramp_entry(item, identifier, f"{where}.ramps[{at}]") for at, item in enumerate(raw)
+    )
+    for at, ramp in enumerate(ramps):
+        _ordered(ramp.ramp, ladder, f"{where}.ramps[{at}]")
+    return GlyphCategory(identifier, name, ladder, ramps)
+
+
+def validate_catalogue(data: object) -> Catalogue:
+    """Validate one ramps document and return it as typed objects, or raise ValueError.
+
+    Every ramp must be an ordered subsequence of its ladder: the data-level "darkest first".
+    """
+    root = _mapping(data, "$")
+    if root.get("schema") != SCHEMA:
+        _fail("$.schema", f"expected {SCHEMA!r}")
+    raw = root.get("categories")
+    if not isinstance(raw, list):
+        _fail("$.categories", "expected a list")
+    categories = tuple(_category_entry(item, f"$.categories[{at}]") for at, item in enumerate(raw))
+    if len(categories) < MIN_CATEGORIES:
+        _fail("$.categories", f"expected at least {MIN_CATEGORIES} categories")
+    _unique([category.id for category in categories], "$.categories[].id")
+    ramps = [ramp for category in categories for ramp in category.ramps]
+    _unique([ramp.id for ramp in ramps], "$.categories[].ramps[].id")
+    non_latin = sum(1 for ramp in ramps if ramp.script in NON_LATIN_SCRIPTS)
+    if non_latin < MIN_NON_LATIN_RAMPS:
+        _fail(
+            "$.categories[].ramps[].script",
+            f"expected at least {MIN_NON_LATIN_RAMPS} non-Latin ramps",
+        )
+    return Catalogue(categories)
+
+
+@cache
+def load_catalogue(path: Path | str | None = None) -> Catalogue:
+    """Return the shipped catalogue, or the one at path, validated once per path."""
+    target = DATA_FILE if path is None else Path(path).expanduser().resolve()
+    with Path(target).open(encoding="utf-8") as handle:
+        return validate_catalogue(json.load(handle))
+
+
+def render_ramp_preview(
+    ramp: str,
+    *,
+    font: str | None = None,
+    cell: tuple[int, int] = PREVIEW_CELL,
+    fg: str = DEFAULT_FG,
+    bg: str = DEFAULT_BG,
+) -> RGB8:
+    """Return the ramp drawn left to right in font by the real ``glyph_ramp`` renderer.
+
+    Always uint8 RGB: a ``transparent`` fg or bg is composited over white.
+    """
+    count, (cell_w, cell_h) = len(ramp), (int(cell[0]), int(cell[1]))
+    positions = (np.arange(count, dtype=np.float32) + 0.5) / np.float32(count)
+    luma = color.srgb_to_linear(positions)[None, :]
+    grid = CellGrid(
+        cols=count, rows=1, cell_w=cell_w, cell_h=cell_h,
+        index=np.zeros((1, count), dtype=np.int32),
+        coverage=np.zeros((1, count), dtype=np.float32),
+        luma=np.ascontiguousarray(luma, dtype=np.float32),
+        samples=np.zeros((1, count, 1), dtype=np.float32),
+    )
+    style = RenderStyle({"ramp": ramp, "font": font, "fg": fg, "bg": bg, "mode": "mono"})
+    image = get_renderer("glyph_ramp").render(grid, _BW, style)
+    if image.mode == "RGB":
+        return np.asarray(image, dtype=np.uint8)
+    over = np.asarray(image.convert("RGBA"), dtype=np.float32) / np.float32(255.0)
+    alpha = over[:, :, 3:4]
+    return color.to_rgb8(over[:, :, :3] * alpha + (np.float32(1.0) - alpha))
+
+
+def _pixmap(rgb8: RGB8) -> QPixmap:
+    """Return a QPixmap holding a private copy of a uint8 RGB array."""
+    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
+    height, width, stride = int(data.shape[0]), int(data.shape[1]), int(data.strides[0])
+    image = QImage(data.data, width, height, stride, QImage.Format.Format_RGB888).copy()
+    return QPixmap.fromImage(image)
+
+
+def _add(widget: QListWidget, text: str, data: str) -> None:
+    """Append an item showing text and carrying data in its user role."""
+    item = QListWidgetItem(text)
+    item.setData(Qt.ItemDataRole.UserRole, data)
+    widget.addItem(item)
+
+
+class GlyphBrowser(QWidget):
+    """Category list, set list and a live preview of every ramp in the current font."""
+
+    ramp_chosen = Signal(str)
+
+    def __init__(
+        self,
+        parent: QWidget | None = None,
+        *,
+        catalogue: Catalogue | None = None,
+        font: str | None = None,
+        cell: tuple[int, int] = PREVIEW_CELL,
+    ) -> None:
+        """Build the two lists and the preview pane, then show the first set."""
+        super().__init__(parent)
+        self.setObjectName("glyph_browser")
+        self._catalogue = load_catalogue() if catalogue is None else catalogue
+        self._font = font
+        self._cell = (int(cell[0]), int(cell[1]))
+        self._current: GlyphRamp | None = None
+        self._preview: RGB8 | None = None
+        self.category_list = QListWidget(self)
+        self.category_list.setObjectName("glyph_category_list")
+        self.category_list.setAlternatingRowColors(True)
+        self.category_list.setMaximumWidth(190)
+        self.set_list = QListWidget(self)
+        self.set_list.setObjectName("glyph_set_list")
+        self.set_list.setAlternatingRowColors(True)
+        self.name_label = QLabel("", self)
+        self.name_label.setObjectName("glyph_set_name")
+        self.preview_label = QLabel(self)
+        self.preview_label.setObjectName("glyph_preview")
+        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.preview_label.setMinimumHeight(self._cell[1])
+        self.ramp_label = QLabel("", self)
+        self.ramp_label.setObjectName("glyph_ramp_text")
+        self.ramp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
+        self.hint_label = QLabel(HINT_TEXT, self)
+        self.hint_label.setObjectName("glyph_hint")
+        self.hint_label.setWordWrap(True)
+        self._build_layout()
+        self._populate()
+
+    def catalogue(self) -> Catalogue:
+        """Return the catalogue this browser displays."""
+        return self._catalogue
+
+    def current_ramp(self) -> GlyphRamp | None:
+        """Return the ramp currently previewed, or None before the first selection."""
+        return self._current
+
+    def preview_rgb8(self) -> RGB8 | None:
+        """Return the pixels of the current preview, or None before the first selection."""
+        return None if self._preview is None else self._preview.copy()
+
+    def select_ramp(self, ramp_id: str) -> None:
+        """Show ramp_id, selecting its category and set; the repaint is explicit on purpose.
+
+        Lists already pointing at ramp_id emit no signal, so they are not relied on.
+        """
+        ramp = self._catalogue.get(ramp_id)  # KeyError naming an unknown id
+        for row, category in enumerate(self._catalogue.categories):
+            ids = [item.id for item in category.ramps]
+            if ramp_id not in ids:
+                continue
+            if self.category_list.currentRow() != row:
+                self.category_list.setCurrentRow(row)
+            self.set_list.setCurrentRow(ids.index(ramp_id))
+            if self._current is not ramp:
+                self._show(ramp)
+            return
+
+    def set_font(self, font: str | None) -> None:
+        """Preview every ramp in font, or in the bundled font when font is None."""
+        self._font = font
+        if self._current is not None:
+            self._show(self._current)
+
+    def _build_layout(self) -> None:
+        """Lay out the two lists beside the name, preview and ramp text."""
+        lists = QVBoxLayout()
+        lists.setSpacing(4)
+        lists.addWidget(QLabel("Categories", self))
+        lists.addWidget(self.category_list, 1)
+        lists.addWidget(QLabel("Sets", self))
+        lists.addWidget(self.set_list, 1)
+        right = QVBoxLayout()
+        right.setSpacing(6)
+        right.addWidget(self.name_label)
+        right.addWidget(self.preview_label)
+        right.addWidget(self.ramp_label)
+        right.addWidget(self.hint_label)
+        right.addStretch(1)
+        outer = QHBoxLayout(self)
+        outer.setContentsMargins(6, 6, 6, 6)
+        outer.setSpacing(8)
+        outer.addLayout(lists, 1)
+        outer.addLayout(right, 2)
+
+    def _populate(self) -> None:
+        """Fill the category list and select the first set of the first category."""
+        for category in self._catalogue.categories:
+            _add(self.category_list, category.name, category.id)
+        self.category_list.currentRowChanged.connect(self._on_category_changed)
+        self.set_list.currentRowChanged.connect(self._on_set_changed)
+        if self._catalogue.categories:
+            self.category_list.setCurrentRow(0)
+
+    def _on_category_changed(self, row: int) -> None:
+        """Refill the set list with the ramps of the selected category."""
+        self.set_list.blockSignals(True)
+        self.set_list.clear()
+        if 0 <= row < len(self._catalogue.categories):
+            for ramp in self._catalogue.categories[row].ramps:
+                _add(self.set_list, ramp.name, ramp.id)
+        self.set_list.blockSignals(False)
+        if self.set_list.count():
+            self.set_list.setCurrentRow(0)
+
+    def _on_set_changed(self, row: int) -> None:
+        """Preview the newly selected set and announce it."""
+        if not 0 <= row < self.set_list.count():
+            return
+        ramp = self._catalogue.get(str(self.set_list.item(row).data(Qt.ItemDataRole.UserRole)))
+        self._show(ramp)
+        self.ramp_chosen.emit(ramp.id)
+
+    def _show(self, ramp: GlyphRamp) -> None:
+        """Render ramp in the current font and update every label of the preview pane."""
+        self._preview = render_ramp_preview(ramp.ramp, font=self._font, cell=self._cell)
+        self._current = ramp
+        self.preview_label.setPixmap(_pixmap(self._preview))
+        self.name_label.setText(ramp.name)
+        self.ramp_label.setText(f"{ramp.ramp!r}")
+
+
+__all__ = [
+    "Catalogue", "DATA_FILE", "GlyphBrowser", "GlyphCategory", "GlyphRamp", "MIN_CATEGORIES",
+    "MIN_NON_LATIN_RAMPS", "NON_LATIN_SCRIPTS", "PREVIEW_CELL", "SCHEMA", "load_catalogue",
+    "render_ramp_preview", "validate_catalogue",
+]
diff --git a/tests/test_ramps.py b/tests/test_ramps.py
new file mode 100644
index 0000000..736e9d7
--- /dev/null
+++ b/tests/test_ramps.py
@@ -0,0 +1,359 @@
+"""Card L10 acceptance: the glyph ramp catalogue and its browser (§9).
+
+Every accept item is covered: the shipped ``ramps.json`` validates against the schema test
+and every ramp is non-empty and darkest-first; the browser renders a preview for every set
+without raising; at least eight categories and six non-Latin ramps are shipped; selecting a
+set repaints the preview in under 100 ms. "Darkest first" is checked as documented data —
+each ramp is an ordered subsequence of its category ladder — never by measuring glyph ink,
+which is font-dependent (§9).
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import time
+from pathlib import Path
+
+os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
+
+import numpy as np  # noqa: E402
+import pytest  # noqa: E402
+from PySide6.QtWidgets import QApplication  # noqa: E402
+
+from lattice_core.ui import glyph_browser as module  # noqa: E402
+from lattice_core.ui.glyph_browser import (  # noqa: E402
+    DATA_FILE,
+    MIN_CATEGORIES,
+    MIN_NON_LATIN_RAMPS,
+    PREVIEW_CELL,
+    SCHEMA,
+    Catalogue,
+    GlyphBrowser,
+    load_catalogue,
+    render_ramp_preview,
+    validate_catalogue,
+)
+
+SELECT_DEADLINE = 0.100  # accept: selecting a set updates the preview within 100 ms
+
+
+@pytest.fixture(scope="module")
+def qapp() -> QApplication:
+    """Return the shared offscreen QApplication."""
+    app = QApplication.instance()
+    if not isinstance(app, QApplication):
+        app = QApplication([])
+    return app
+
+
+@pytest.fixture(scope="module")
+def catalogue() -> Catalogue:
+    """Return the shipped catalogue, parsed once for the whole module."""
+    return load_catalogue()
+
+
+def document() -> dict:
+    """Return the shipped ramps document as raw JSON."""
+    with DATA_FILE.open(encoding="utf-8") as handle:
+        return json.load(handle)
+
+
+def minimal_document() -> dict:
+    """Return the smallest document that satisfies the schema, for mutation tests."""
+    categories = [
+        {
+            "id": f"cat_{at}",
+            "name": f"Category {at}",
+            "ladder": "@#. ",
+            "ramps": [{"id": f"ramp_{at}", "name": "One", "script": "latin", "ramp": "@#. "}],
+        }
+        for at in range(MIN_CATEGORIES)
+    ]
+    for at in range(MIN_NON_LATIN_RAMPS):
+        categories[at]["ramps"].append(
+            {"id": f"nonlatin_{at}", "name": "Two", "script": "japanese", "ramp": "@. "}
+        )
+    return {"schema": SCHEMA, "categories": categories}
+
+
+def ramp_ids(catalogue: Catalogue) -> list[str]:
+    """Return every ramp id of the catalogue, in display order."""
+    return [ramp.id for ramp in catalogue.ramps()]
+
+
+# --- accept 1: the document validates against the schema --------------------------
+
+
+def test_shipped_catalogue_validates_against_the_schema(catalogue: Catalogue) -> None:
+    """The shipped ramps.json loads as typed objects that name its own schema version."""
+    raw = document()
+    assert raw["schema"] == SCHEMA == "lattice.ramps/1"
+    assert validate_catalogue(raw) == catalogue
+    assert [category.id for category in catalogue.categories] == [
+        item["id"] for item in raw["categories"]
+    ]
+    assert len(ramp_ids(catalogue)) == len({ramp.id for ramp in catalogue.ramps()})
+
+
+def test_data_file_is_found_next_to_the_module_not_the_cwd(tmp_path: Path) -> None:
+    """The shipped path derives from __file__, so any working directory loads the same data."""
+    expected = Path(module.__file__).resolve().parents[1] / "data" / "ramps.json"
+    assert Path(DATA_FILE).resolve() == expected
+    assert DATA_FILE.is_file() and DATA_FILE.parent.name == "data"
+    previous, expected_ids = Path.cwd(), [item["id"] for item in document()["categories"]]
+    load_catalogue.cache_clear()  # force a real read, from a directory holding no data
+    os.chdir(tmp_path)
+    try:
+        assert not Path("lattice_core/data/ramps.json").exists()
+        moved = load_catalogue()
+        assert [category.id for category in moved.categories] == expected_ids
+    finally:
+        os.chdir(previous)
+        load_catalogue.cache_clear()
+
+
+def test_catalogue_lookup_is_by_id(catalogue: Catalogue) -> None:
+    """Catalogue.get and Catalogue.category resolve ids and name unknown ones in a KeyError."""
+    first = catalogue.ramps()[0]
+    assert catalogue.get(first.id) is first
+    assert catalogue.category(first.category_id).id == first.category_id
+    with pytest.raises(KeyError, match="unknown glyph ramp"):
+        catalogue.get("no_such_ramp")
+    with pytest.raises(KeyError, match="unknown glyph category"):
+        catalogue.category("no_such_category")
+
+
+# --- accept 1: every ramp is non-empty and darkest-first --------------------------
+
+
+def test_every_ramp_is_non_empty_and_darkest_first(catalogue: Catalogue) -> None:
+    """Every ramp has ink, distinct glyphs and follows its ladder from darkest to lightest.
+
+    The check is recomputed here from the raw document rather than trusted from the module:
+    each glyph of a ramp must appear in the ladder at an index strictly after the previous
+    one, which is the data-level statement of "darkest character first, lightest last".
+    """
+    raw = document()
+    for category, item in zip(catalogue.categories, raw["categories"], strict=True):
+        ladder = item["ladder"]
+        assert ladder and len(set(ladder)) == len(ladder)
+        for ramp in category.ramps:
+            assert 2 <= len(ramp.ramp) <= len(ladder)
+            positions = [ladder.index(glyph) for glyph in ramp.ramp]
+            assert positions == sorted(set(positions)), f"{ramp.id} is not darkest-first"
+
+
+def test_every_ladder_starts_dense_and_ends_on_blank_paper(catalogue: Catalogue) -> None:
+    """A ladder opens on a dense glyph and closes on a space, its documented light end."""
+    for category in catalogue.categories:
+        assert category.ladder[0] not in " ·", category.id
+        assert category.ladder[-1] == " ", category.id
+        assert len(category.ladder) >= len(max(category.ramps, key=lambda r: len(r.ramp)).ramp)
+
+
+@pytest.mark.parametrize(
+    ("mutate", "path"),
+    [
+        (lambda doc: doc.update({"schema": "lattice.ramps/2"}), "$.schema"),
+        (lambda doc: doc["categories"][0].update({"ladder": "@#. .  "}), "$.categories[0].ladder"),
+        (lambda doc: doc["categories"][0].update({"ramps": []}), "$.categories[0].ramps"),
+        (
+            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": " .#@"}),
+            "$.categories[0].ramps[0].ramp",
+        ),
+        (
+            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@#@. "}),
+            "$.categories[0].ramps[0].ramp",
+        ),
+        (
+            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@"}),
+            "$.categories[0].ramps[0].ramp",
+        ),
+        (
+            lambda doc: doc["categories"][0]["ramps"][0].update({"script": "klingon"}),
+            "$.categories[0].ramps[0].script",
+        ),
+        (lambda doc: doc["categories"][0].update({"id": "Not A Slug"}), "$.categories[0].id"),
+        (lambda doc: doc["categories"][0]["ramps"][0].pop("name"), "$.categories[0].ramps[0].name"),
+        (lambda doc: doc.update({"categories": doc["categories"][:2]}), "$.categories"),
+    ],
+)
+def test_the_schema_rejects_invalid_documents(mutate, path: str) -> None:
+    """A broken document raises ValueError naming the offending path of the catalogue."""
+    doc = minimal_document()
+    mutate(doc)
+    with pytest.raises(ValueError) as error:
+        validate_catalogue(doc)
+    assert path in str(error.value)
+
+
+def test_minimal_document_is_accepted() -> None:
+    """The fixture used by the mutation tests is itself valid, so each case proves one rule."""
+    assert len(validate_catalogue(minimal_document()).categories) == MIN_CATEGORIES
+
+
+# --- accept 3: at least 8 categories and 6 non-Latin ramps -------------------------
+
+
+def test_the_catalogue_ships_enough_categories_and_non_latin_ramps(
+    catalogue: Catalogue,
+) -> None:
+    """§9 asks for eight categories and six non-Latin ramps; the card names the seven."""
+    assert len(catalogue.categories) >= MIN_CATEGORIES == 8
+    scripts = {ramp.script for ramp in catalogue.ramps()}
+    non_latin = [ramp for ramp in catalogue.ramps() if ramp.script in module.NON_LATIN_SCRIPTS]
+    assert len(non_latin) >= MIN_NON_LATIN_RAMPS == 6
+    assert {"japanese", "korean", "chinese", "russian", "german", "french", "spanish"} <= scripts
+    classic = {category.id for category in catalogue.categories}
+    assert {
+        "classic_ascii",
+        "numbers",
+        "symbols",
+        "blocks",
+        "geometric",
+        "braille",
+        "playing_cards",
+    } <= classic
+
+
+# --- accept 2: a preview for every set, without raising ----------------------------
+
+
+def test_every_ramp_renders_a_preview(catalogue: Catalogue) -> None:
+    """render_ramp_preview returns one cell per glyph as uint8 RGB, for every shipped ramp."""
+    for ramp in catalogue.ramps():
+        image = render_ramp_preview(ramp.ramp)
+        assert image.dtype.name == "uint8", ramp.id
+        assert image.shape == (PREVIEW_CELL[1], PREVIEW_CELL[0] * len(ramp.ramp), 3), ramp.id
+        assert 0 <= int(image.min()) and int(image.max()) <= 255
+        assert int(image.max()) > int(image.min()), f"{ramp.id} renders as one flat colour"
+
+
+def test_preview_composites_a_transparent_ink_over_white() -> None:
+    """A transparent colour still yields uint8 RGB, white where no ink is drawn."""
+    image = render_ramp_preview("@. ", fg="transparent", bg="transparent")
+    assert image.shape[2] == 3
+    assert int(image.min()) == 255
+
+
+def test_preview_uses_the_font_it_is_given() -> None:
+    """A font path that does not exist is refused instead of silently drawing nothing."""
+    with pytest.raises(ValueError, match="font file not found"):
+        render_ramp_preview("@. ", font="/nonexistent/font.ttf")
+
+
+def test_browser_renders_a_preview_for_every_set(qapp: QApplication, catalogue: Catalogue) -> None:
+    """Walking every category and every set repaints the preview without raising."""
+    browser = GlyphBrowser(catalogue=catalogue)
+    try:
+        assert browser.category_list.count() == len(catalogue.categories)
+        seen: list[str] = []
+        for row, category in enumerate(catalogue.categories):
+            browser.category_list.setCurrentRow(row)
+            QApplication.processEvents()
+            assert browser.set_list.count() == len(category.ramps), category.id
+            for at, ramp in enumerate(category.ramps):
+                browser.set_list.setCurrentRow(at)
+                QApplication.processEvents()
+                preview = browser.preview_rgb8()
+                assert browser.current_ramp() is ramp
+                assert preview is not None and preview.shape[2] == 3
+                assert browser.preview_label.pixmap().size().width() == preview.shape[1]
+                assert browser.name_label.text() == ramp.name
+                seen.append(ramp.id)
+        assert seen == ramp_ids(catalogue)
+    finally:
+        browser.close()
+
+
+def test_first_selection_is_previewed_on_construction(
+    qapp: QApplication, catalogue: Catalogue
+) -> None:
+    """A fresh browser already shows the first set of the first category."""
+    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
+    try:
+        assert browser.current_ramp() is catalogue.categories[0].ramps[0]
+        assert browser.preview_rgb8() is not None
+    finally:
+        browser.close()
+
+
+# --- accept 4: selecting a set updates the preview within 100 ms -------------------
+
+
+def test_selecting_a_set_updates_the_preview_within_100_ms(
+    qapp: QApplication, catalogue: Catalogue
+) -> None:
+    """The measured repaint of a selection stays under the card's 100 ms budget."""
+    browser = GlyphBrowser(catalogue=catalogue)
+    try:
+        first, second = catalogue.ramps()[0], catalogue.ramps()[-1]
+        browser.select_ramp(first.id)  # warm the glyph mask cache of the module
+        browser.select_ramp(second.id)
+        assert browser.current_ramp() is second
+        start = time.perf_counter()
+        browser.select_ramp(first.id)
+        QApplication.processEvents()
+        elapsed = time.perf_counter() - start
+        assert browser.current_ramp() is first
+        assert elapsed < SELECT_DEADLINE, f"selection took {elapsed * 1000:.1f} ms"
+        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(first.ramp))
+    finally:
+        browser.close()
+
+
+def test_select_ramp_repaints_when_the_lists_already_sit_there(
+    qapp: QApplication, catalogue: Catalogue
+) -> None:
+    """A silent list (already on that row) still repaints: the preview is not left stale."""
+    browser = GlyphBrowser(catalogue=catalogue)
+    try:
+        first, second = catalogue.categories[0].ramps[:2]
+        browser.select_ramp(first.id)
+        browser.set_list.blockSignals(True)  # the lists now point at `second`, the pane at `first`
+        browser.set_list.setCurrentRow(1)
+        browser.set_list.blockSignals(False)
+        assert browser.current_ramp() is first
+        browser.select_ramp(second.id)  # setCurrentRow(1) is a no-op, so no signal is emitted
+        assert browser.current_ramp() is second
+        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(second.ramp))
+    finally:
+        browser.close()
+
+
+def test_select_ramp_names_an_unknown_id(qapp: QApplication, catalogue: Catalogue) -> None:
+    """An unknown id raises KeyError instead of silently showing something else."""
+    browser = GlyphBrowser(catalogue=catalogue)
+    try:
+        with pytest.raises(KeyError, match="unknown glyph ramp"):
+            browser.select_ramp("no_such_ramp")
+    finally:
+        browser.close()
+
+
+def test_ramp_chosen_follows_the_selection(qapp: QApplication, catalogue: Catalogue) -> None:
+    """Every selection announces its ramp id, which is how the app learns the choice."""
+    browser = GlyphBrowser(catalogue=catalogue)
+    chosen: list[str] = []
+    browser.ramp_chosen.connect(chosen.append)
+    try:
+        last = catalogue.categories[-1]
+        browser.category_list.setCurrentRow(len(catalogue.categories) - 1)
+        browser.set_list.setCurrentRow(len(last.ramps) - 1)
+        QApplication.processEvents()
+        assert chosen and chosen[-1] == last.ramps[-1].id
+    finally:
+        browser.close()
+
+
+def test_set_font_repaints_the_current_ramp(qapp: QApplication, catalogue: Catalogue) -> None:
+    """set_font(None) restores the bundled font and keeps the selection."""
+    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
+    try:
+        browser.select_ramp(catalogue.ramps()[1].id)
+        browser.set_font(None)
+        assert browser.current_ramp() is catalogue.ramps()[1]
+        assert browser.preview_rgb8() is not None
+    finally:
+        browser.close()


CODER NOTES AND DEVIATIONS
- 27 tests, un par item d'accept ; suite 1941 verte ; ruff clean sur les deux fichiers de la carte.
- « darkest first » vérifié comme DONNÉE documentée (chaque rampe est une sous-séquence ordonnée de
  son ladder, indices strictement croissants), pas par mesure d'encre : le codeur argue qu'à la police
  par défaut plusieurs glyphes (blocs) rendent identiques, donc un test d'encre mesurerait le font,
  pas le contrat, et §9 dit explicitement que la rampe n'est pas détectée.
- Deux tests anti-tautologie : repeint sur la même ligne avec signaux bloqués ; preview comparé à
  `render_ramp_preview` et non au widget lui-même.
- `DATA_FILE = Path(__file__).parents[1]/"data"/"ramps.json"`, jamais le cwd.
- E3 : la ligne `[tool.setuptools.package-data]` était hors owns — appliquée par l'orchestrateur.
