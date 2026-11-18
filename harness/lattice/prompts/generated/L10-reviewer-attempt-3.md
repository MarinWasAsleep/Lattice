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



GATE RESULTS (L10, attempt 3 — cycle 3 de revue, correctif test-only sur les findings du pass 2)
- Owned tests : 30 passed (pass 2 en comptait 27). `glyph_browser.py` 398 l, `test_ramps.py` 400 l.
- Suite complète : 2004 passed, 1 skipped (1944 au moment du rendu du codeur ; les tests de L10 sont
  désormais tous collectés). G1 ruff : all checks passed sur tout le dépôt. G3 check_contract : OK.
- Le diff ci-dessous est celui de l'attempt 3 seul (pass 2 → pass 3), pas la carte entière : tu
  vérifies les correctifs demandés, pas ce qui était déjà accepté au pass 2.

CE QUE LE CODEUR DIT AVOIR FAIT (à vérifier, ne pas croire)
1. Finding 1 (mappage) : la colonne i est byte-égale à `render_ramp_preview(ramp[i])`, plus 10
   colonnes distinctes et « densest inks / blank leaves paper » sur la rampe ASCII classique.
   Il affirme avoir muté le code (positions inversées) pour vérifier que le test échoue.
2. Finding 2 (timing) : il chronomètre `select_ramp` + flush avec les caches masque/métriques vidés
   avant chaque catégorie, et asserte que les misses de `_cached_mask` valent au moins len(ramp),
   pour qu'un run chaud ne puisse pas se faire passer pour un run froid. Pire mesure : 4,4 ms.
3. Finding 3 : exactement une émission `ramp_chosen` sur un saut inter-catégories ; il affirme que le
   test échoue sur l'ancien `select_ramp` (deux émissions).
4. Finding 4 : `target.open(...)`, `Catalogue.ramp_index`/`category_index` en cached_property,
   vérifiés par identité.
5. Finding 5 : il déclare une DÉVIATION E1 — aucun test déterministe ne peut faire échouer le
   correctif `.copy()` (lire un tampon libéré est un comportement indéfini) ; il a donc écrit un
   garde de contenu (pixels == preview après gc.collect() et 4 QImage de même taille) qui passe sur
   l'ancien code aussi, et le dit explicitement. Arbitre : est-ce acceptable, ou faut-il autre chose ?

QUESTION EXPLICITE : le timing est-il mesuré sur une vraie sélection froide, ou le test peut-il encore
être satisfait par un cache chaud malgré l'assertion de misses ?

DIFF (attempt 3 : pass 2 → HEAD, les deux fichiers de la carte)

diff --git a/lattice_core/ui/glyph_browser.py b/lattice_core/ui/glyph_browser.py
index 8a42a46..4a05a70 100644
--- a/lattice_core/ui/glyph_browser.py
+++ b/lattice_core/ui/glyph_browser.py
@@ -1,17 +1,17 @@
 """Browsable catalogue of glyph ramps, previewed in the current font (§9, card L10).
 
 ``lattice_core/data/ramps.json`` documents one master ladder per category and every ramp is an
-ordered subsequence of it, so "darkest first" is documented data, never detected per font. The
-data path derives from ``__file__``. Part of ``lattice_core.ui``: it needs the ``[ui]`` extra.
+ordered subsequence of it, so "darkest first" is documented data, never detected per font.
+Part of ``lattice_core.ui``: it needs the ``[ui]`` extra.
 """
 
 from __future__ import annotations
 
 import json
 import re
-from collections.abc import Mapping
+from collections.abc import Iterable, Mapping
 from dataclasses import dataclass
-from functools import cache
+from functools import cache, cached_property
 from pathlib import Path
 from typing import NoReturn
 
@@ -67,7 +67,7 @@ class GlyphCategory:
 
 @dataclass(frozen=True)
 class Catalogue:
-    """The whole ramps catalogue, in display order."""
+    """The whole ramps catalogue, in display order, with its ids indexed once."""
 
     categories: tuple[GlyphCategory, ...]
 
@@ -75,16 +75,26 @@ class Catalogue:
         """Return every ramp of the catalogue, category by category."""
         return tuple(ramp for category in self.categories for ramp in category.ramps)
 
+    @cached_property
+    def ramp_index(self) -> dict[str, GlyphRamp]:
+        """Return every ramp indexed by id, built on first lookup and then reused."""
+        return {ramp.id: ramp for ramp in self.ramps()}
+
+    @cached_property
+    def category_index(self) -> dict[str, GlyphCategory]:
+        """Return every category indexed by id, built on first lookup and then reused."""
+        return {category.id: category for category in self.categories}
+
     def get(self, ramp_id: str) -> GlyphRamp:
         """Return the ramp registered under ramp_id, or raise KeyError naming it."""
-        found = {ramp.id: ramp for ramp in self.ramps()}.get(ramp_id)
+        found = self.ramp_index.get(ramp_id)
         if found is None:
             raise KeyError(f"unknown glyph ramp: {ramp_id!r}")
         return found
 
     def category(self, category_id: str) -> GlyphCategory:
         """Return the category registered under category_id, or raise KeyError naming it."""
-        found = {category.id: category for category in self.categories}.get(category_id)
+        found = self.category_index.get(category_id)
         if found is None:
             raise KeyError(f"unknown glyph category: {category_id!r}")
         return found
@@ -162,19 +172,14 @@ def _category_entry(data: object, where: str) -> GlyphCategory:
     raw = node.get("ramps")
     if not isinstance(raw, list) or not raw:
         _fail(f"{where}.ramps", "expected a non-empty list")
-    ramps = tuple(
-        _ramp_entry(item, identifier, f"{where}.ramps[{at}]") for at, item in enumerate(raw)
-    )
+    ramps = tuple(_ramp_entry(x, identifier, f"{where}.ramps[{at}]") for at, x in enumerate(raw))
     for at, ramp in enumerate(ramps):
         _ordered(ramp.ramp, ladder, f"{where}.ramps[{at}]")
     return GlyphCategory(identifier, name, ladder, ramps)
 
 
 def validate_catalogue(data: object) -> Catalogue:
-    """Validate one ramps document and return it as typed objects, or raise ValueError.
-
-    Every ramp must be an ordered subsequence of its ladder: the data-level "darkest first".
-    """
+    """Validate a ramps document into typed objects; ramps must be ordered subsequences."""
     root = _mapping(data, "$")
     if root.get("schema") != SCHEMA:
         _fail("$.schema", f"expected {SCHEMA!r}")
@@ -189,10 +194,7 @@ def validate_catalogue(data: object) -> Catalogue:
     _unique([ramp.id for ramp in ramps], "$.categories[].ramps[].id")
     non_latin = sum(1 for ramp in ramps if ramp.script in NON_LATIN_SCRIPTS)
     if non_latin < MIN_NON_LATIN_RAMPS:
-        _fail(
-            "$.categories[].ramps[].script",
-            f"expected at least {MIN_NON_LATIN_RAMPS} non-Latin ramps",
-        )
+        _fail("$.categories[].ramps[].script", f"needs {MIN_NON_LATIN_RAMPS} non-Latin ramps")
     return Catalogue(categories)
 
 
@@ -200,7 +202,7 @@ def validate_catalogue(data: object) -> Catalogue:
 def load_catalogue(path: Path | str | None = None) -> Catalogue:
     """Return the shipped catalogue, or the one at path, validated once per path."""
     target = DATA_FILE if path is None else Path(path).expanduser().resolve()
-    with Path(target).open(encoding="utf-8") as handle:
+    with target.open(encoding="utf-8") as handle:
         return validate_catalogue(json.load(handle))
 
 
@@ -212,10 +214,7 @@ def render_ramp_preview(
     fg: str = DEFAULT_FG,
     bg: str = DEFAULT_BG,
 ) -> RGB8:
-    """Return the ramp drawn left to right in font by the real ``glyph_ramp`` renderer.
-
-    Always uint8 RGB: a ``transparent`` fg or bg is composited over white.
-    """
+    """Return the ramp drawn left to right by the real renderer, always as uint8 RGB."""
     count, (cell_w, cell_h) = len(ramp), (int(cell[0]), int(cell[1]))
     positions = (np.arange(count, dtype=np.float32) + 0.5) / np.float32(count)
     luma = color.srgb_to_linear(positions)[None, :]
@@ -306,21 +305,17 @@ class GlyphBrowser(QWidget):
         return None if self._preview is None else self._preview.copy()
 
     def select_ramp(self, ramp_id: str) -> None:
-        """Show ramp_id, selecting its category and set; the repaint is explicit on purpose.
+        """Show ramp_id by moving both lists silently, then repainting and announcing once.
 
-        Lists already pointing at ramp_id emit no signal, so they are not relied on.
+        A cross-category jump must never preview, nor announce, row 0 of the new category.
         """
         ramp = self._catalogue.get(ramp_id)  # KeyError naming an unknown id
-        for row, category in enumerate(self._catalogue.categories):
-            ids = [item.id for item in category.ramps]
-            if ramp_id not in ids:
-                continue
-            if self.category_list.currentRow() != row:
-                self.category_list.setCurrentRow(row)
-            self.set_list.setCurrentRow(ids.index(ramp_id))
-            if self._current is not ramp:
-                self._show(ramp)
-            return
+        category = self._catalogue.category(ramp.category_id)
+        self._move(self.category_list, self._catalogue.categories.index(category))
+        self._fill_sets(category.ramps)
+        self._move(self.set_list, [other.id for other in category.ramps].index(ramp_id))
+        self._show(ramp)
+        self.ramp_chosen.emit(ramp.id)
 
     def set_font(self, font: str | None) -> None:
         """Preview every ramp in font, or in the bundled font when font is None."""
@@ -358,14 +353,24 @@ class GlyphBrowser(QWidget):
         if self._catalogue.categories:
             self.category_list.setCurrentRow(0)
 
+    def _fill_sets(self, ramps: Iterable[GlyphRamp]) -> None:
+        """Refill the set list with ramps, moving no signal the caller has not asked for."""
+        silent = self.set_list.blockSignals(True)
+        self.set_list.clear()
+        for ramp in ramps:
+            _add(self.set_list, ramp.name, ramp.id)
+        self.set_list.blockSignals(silent)
+
+    def _move(self, widget: QListWidget, row: int) -> None:
+        """Point widget at row without emitting currentRowChanged."""
+        silent = widget.blockSignals(True)
+        widget.setCurrentRow(row)
+        widget.blockSignals(silent)
+
     def _on_category_changed(self, row: int) -> None:
         """Refill the set list with the ramps of the selected category."""
-        self.set_list.blockSignals(True)
-        self.set_list.clear()
-        if 0 <= row < len(self._catalogue.categories):
-            for ramp in self._catalogue.categories[row].ramps:
-                _add(self.set_list, ramp.name, ramp.id)
-        self.set_list.blockSignals(False)
+        categories = self._catalogue.categories
+        self._fill_sets(categories[row].ramps if 0 <= row < len(categories) else ())
         if self.set_list.count():
             self.set_list.setCurrentRow(0)
 
diff --git a/tests/test_ramps.py b/tests/test_ramps.py
index 736e9d7..dd5d40b 100644
--- a/tests/test_ramps.py
+++ b/tests/test_ramps.py
@@ -1,15 +1,14 @@
 """Card L10 acceptance: the glyph ramp catalogue and its browser (§9).
 
-Every accept item is covered: the shipped ``ramps.json`` validates against the schema test
-and every ramp is non-empty and darkest-first; the browser renders a preview for every set
-without raising; at least eight categories and six non-Latin ramps are shipped; selecting a
-set repaints the preview in under 100 ms. "Darkest first" is checked as documented data —
-each ramp is an ordered subsequence of its category ladder — never by measuring glyph ink,
-which is font-dependent (§9).
+Accept, item by item: the document validates against its schema and every ramp is non-empty and
+darkest-first (an ordered subsequence of its category ladder, never measured ink); every set
+previews without raising, and cell i of a preview is proven to hold glyph i; at least eight
+categories and six non-Latin ramps ship; a cold selection repaints within 100 ms.
 """
 
 from __future__ import annotations
 
+import gc
 import json
 import os
 import time
@@ -19,8 +18,10 @@ os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
 
 import numpy as np  # noqa: E402
 import pytest  # noqa: E402
+from PySide6.QtGui import QImage  # noqa: E402
 from PySide6.QtWidgets import QApplication  # noqa: E402
 
+from lattice_core.renderers import glyph_ramp as renderer  # noqa: E402
 from lattice_core.ui import glyph_browser as module  # noqa: E402
 from lattice_core.ui.glyph_browser import (  # noqa: E402
     DATA_FILE,
@@ -36,6 +37,8 @@ from lattice_core.ui.glyph_browser import (  # noqa: E402
 )
 
 SELECT_DEADLINE = 0.100  # accept: selecting a set updates the preview within 100 ms
+CAT, RAMP = "$.categories[0]", "$.categories[0].ramps[0]"  # paths of the mutated objects
+RGB888 = QImage.Format.Format_RGB888
 
 
 @pytest.fixture(scope="module")
@@ -62,12 +65,8 @@ def document() -> dict:
 def minimal_document() -> dict:
     """Return the smallest document that satisfies the schema, for mutation tests."""
     categories = [
-        {
-            "id": f"cat_{at}",
-            "name": f"Category {at}",
-            "ladder": "@#. ",
-            "ramps": [{"id": f"ramp_{at}", "name": "One", "script": "latin", "ramp": "@#. "}],
-        }
+        {"id": f"cat_{at}", "name": f"Category {at}", "ladder": "@#. ",
+         "ramps": [{"id": f"ramp_{at}", "name": "One", "script": "latin", "ramp": "@#. "}]}
         for at in range(MIN_CATEGORIES)
     ]
     for at in range(MIN_NON_LATIN_RAMPS):
@@ -77,11 +76,29 @@ def minimal_document() -> dict:
     return {"schema": SCHEMA, "categories": categories}
 
 
+def first_ramp(doc: dict) -> dict:
+    """Return the first ramp object of the first category of a document."""
+    return doc["categories"][0]["ramps"][0]
+
+
 def ramp_ids(catalogue: Catalogue) -> list[str]:
     """Return every ramp id of the catalogue, in display order."""
     return [ramp.id for ramp in catalogue.ramps()]
 
 
+def cells(rgb8: np.ndarray, count: int) -> list[np.ndarray]:
+    """Return a preview sliced into count cells of PREVIEW_CELL[0] columns."""
+    width = PREVIEW_CELL[0]
+    return [rgb8[:, at * width : (at + 1) * width] for at in range(count)]
+
+
+def clear_glyph_caches() -> None:
+    """Empty the renderer's glyph mask caches, so the next preview really rasterises."""
+    for glyph_cache in (renderer._cached_mask, renderer._metrics):
+        assert hasattr(glyph_cache, "cache_clear")  # the test must reach the real cache
+        glyph_cache.cache_clear()
+
+
 # --- accept 1: the document validates against the schema --------------------------
 
 
@@ -90,27 +107,22 @@ def test_shipped_catalogue_validates_against_the_schema(catalogue: Catalogue) ->
     raw = document()
     assert raw["schema"] == SCHEMA == "lattice.ramps/1"
     assert validate_catalogue(raw) == catalogue
-    assert [category.id for category in catalogue.categories] == [
-        item["id"] for item in raw["categories"]
-    ]
+    assert [c.id for c in catalogue.categories] == [item["id"] for item in raw["categories"]]
     assert len(ramp_ids(catalogue)) == len({ramp.id for ramp in catalogue.ramps()})
 
 
-def test_data_file_is_found_next_to_the_module_not_the_cwd(tmp_path: Path) -> None:
+def test_data_file_is_found_next_to_the_module_not_the_cwd(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
     """The shipped path derives from __file__, so any working directory loads the same data."""
     expected = Path(module.__file__).resolve().parents[1] / "data" / "ramps.json"
-    assert Path(DATA_FILE).resolve() == expected
-    assert DATA_FILE.is_file() and DATA_FILE.parent.name == "data"
-    previous, expected_ids = Path.cwd(), [item["id"] for item in document()["categories"]]
+    assert Path(DATA_FILE).resolve() == expected and DATA_FILE.parent.name == "data"
+    expected_ids = [item["id"] for item in document()["categories"]]
     load_catalogue.cache_clear()  # force a real read, from a directory holding no data
-    os.chdir(tmp_path)
-    try:
-        assert not Path("lattice_core/data/ramps.json").exists()
-        moved = load_catalogue()
-        assert [category.id for category in moved.categories] == expected_ids
-    finally:
-        os.chdir(previous)
-        load_catalogue.cache_clear()
+    monkeypatch.chdir(tmp_path)
+    assert not Path("lattice_core/data/ramps.json").exists()
+    assert [c.id for c in load_catalogue().categories] == expected_ids
+    load_catalogue.cache_clear()
 
 
 def test_catalogue_lookup_is_by_id(catalogue: Catalogue) -> None:
@@ -118,22 +130,15 @@ def test_catalogue_lookup_is_by_id(catalogue: Catalogue) -> None:
     first = catalogue.ramps()[0]
     assert catalogue.get(first.id) is first
     assert catalogue.category(first.category_id).id == first.category_id
+    assert catalogue.get(first.id) is catalogue.ramp_index[first.id]  # indexed once, then reused
     with pytest.raises(KeyError, match="unknown glyph ramp"):
         catalogue.get("no_such_ramp")
     with pytest.raises(KeyError, match="unknown glyph category"):
         catalogue.category("no_such_category")
 
 
-# --- accept 1: every ramp is non-empty and darkest-first --------------------------
-
-
 def test_every_ramp_is_non_empty_and_darkest_first(catalogue: Catalogue) -> None:
-    """Every ramp has ink, distinct glyphs and follows its ladder from darkest to lightest.
-
-    The check is recomputed here from the raw document rather than trusted from the module:
-    each glyph of a ramp must appear in the ladder at an index strictly after the previous
-    one, which is the data-level statement of "darkest character first, lightest last".
-    """
+    """Every ramp follows its ladder, recomputed from the document at the data level of §9."""
     raw = document()
     for category, item in zip(catalogue.categories, raw["categories"], strict=True):
         ladder = item["ladder"]
@@ -147,8 +152,7 @@ def test_every_ramp_is_non_empty_and_darkest_first(catalogue: Catalogue) -> None
 def test_every_ladder_starts_dense_and_ends_on_blank_paper(catalogue: Catalogue) -> None:
     """A ladder opens on a dense glyph and closes on a space, its documented light end."""
     for category in catalogue.categories:
-        assert category.ladder[0] not in " ·", category.id
-        assert category.ladder[-1] == " ", category.id
+        assert category.ladder[0] not in " ·" and category.ladder[-1] == " ", category.id
         assert len(category.ladder) >= len(max(category.ramps, key=lambda r: len(r.ramp)).ramp)
 
 
@@ -156,26 +160,14 @@ def test_every_ladder_starts_dense_and_ends_on_blank_paper(catalogue: Catalogue)
     ("mutate", "path"),
     [
         (lambda doc: doc.update({"schema": "lattice.ramps/2"}), "$.schema"),
-        (lambda doc: doc["categories"][0].update({"ladder": "@#. .  "}), "$.categories[0].ladder"),
-        (lambda doc: doc["categories"][0].update({"ramps": []}), "$.categories[0].ramps"),
-        (
-            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": " .#@"}),
-            "$.categories[0].ramps[0].ramp",
-        ),
-        (
-            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@#@. "}),
-            "$.categories[0].ramps[0].ramp",
-        ),
-        (
-            lambda doc: doc["categories"][0]["ramps"][0].update({"ramp": "@"}),
-            "$.categories[0].ramps[0].ramp",
-        ),
-        (
-            lambda doc: doc["categories"][0]["ramps"][0].update({"script": "klingon"}),
-            "$.categories[0].ramps[0].script",
-        ),
-        (lambda doc: doc["categories"][0].update({"id": "Not A Slug"}), "$.categories[0].id"),
-        (lambda doc: doc["categories"][0]["ramps"][0].pop("name"), "$.categories[0].ramps[0].name"),
+        (lambda doc: doc["categories"][0].update({"ladder": "@#. .  "}), f"{CAT}.ladder"),
+        (lambda doc: doc["categories"][0].update({"ramps": []}), f"{CAT}.ramps"),
+        (lambda doc: first_ramp(doc).update({"ramp": " .#@"}), f"{RAMP}.ramp"),
+        (lambda doc: first_ramp(doc).update({"ramp": "@#@. "}), f"{RAMP}.ramp"),
+        (lambda doc: first_ramp(doc).update({"ramp": "@"}), f"{RAMP}.ramp"),
+        (lambda doc: first_ramp(doc).update({"script": "klingon"}), f"{RAMP}.script"),
+        (lambda doc: doc["categories"][0].update({"id": "Not A Slug"}), f"{CAT}.id"),
+        (lambda doc: first_ramp(doc).pop("name"), f"{RAMP}.name"),
         (lambda doc: doc.update({"categories": doc["categories"][:2]}), "$.categories"),
     ],
 )
@@ -196,38 +188,44 @@ def test_minimal_document_is_accepted() -> None:
 # --- accept 3: at least 8 categories and 6 non-Latin ramps -------------------------
 
 
-def test_the_catalogue_ships_enough_categories_and_non_latin_ramps(
-    catalogue: Catalogue,
-) -> None:
-    """§9 asks for eight categories and six non-Latin ramps; the card names the seven."""
+def test_enough_categories_and_non_latin_ramps(catalogue: Catalogue) -> None:
+    """§9 asks for eight categories and six non-Latin ramps; the card names all seven scripts."""
     assert len(catalogue.categories) >= MIN_CATEGORIES == 8
     scripts = {ramp.script for ramp in catalogue.ramps()}
     non_latin = [ramp for ramp in catalogue.ramps() if ramp.script in module.NON_LATIN_SCRIPTS]
     assert len(non_latin) >= MIN_NON_LATIN_RAMPS == 6
     assert {"japanese", "korean", "chinese", "russian", "german", "french", "spanish"} <= scripts
     classic = {category.id for category in catalogue.categories}
-    assert {
-        "classic_ascii",
-        "numbers",
-        "symbols",
-        "blocks",
-        "geometric",
-        "braille",
-        "playing_cards",
-    } <= classic
+    assert {"classic_ascii", "numbers", "symbols", "blocks"} <= classic
+    assert {"geometric", "braille", "playing_cards"} <= classic
 
 
-# --- accept 2: a preview for every set, without raising ----------------------------
+# --- accept 2: cell i of a preview holds glyph i, and every set renders -----------
 
 
-def test_every_ramp_renders_a_preview(catalogue: Catalogue) -> None:
-    """render_ramp_preview returns one cell per glyph as uint8 RGB, for every shipped ramp."""
+def test_cell_i_of_a_preview_shows_glyph_i_of_the_ramp() -> None:
+    """Each column equals that glyph rendered alone, and no two columns draw alike.
+
+    The mapping proof of accept 2: a luma transform that shifted, reversed or collapsed the
+    glyph index, or drew one glyph everywhere, changes at least one column.
+    """
+    ramp = load_catalogue().get("classic_10").ramp  # dense ASCII to blank: distinct masks
+    image = render_ramp_preview(ramp)
+    drawn = cells(image, len(ramp))
+    for glyph, cell in zip(ramp, drawn, strict=True):
+        assert np.array_equal(cell, render_ramp_preview(glyph)), repr(glyph)
+    assert len({cell.tobytes() for cell in drawn}) == len(ramp)
+    assert int(drawn[0].min()) == 0x11, "the densest glyph must ink the paper"
+    assert int(drawn[-1].min()) == 255, "the blank glyph must leave the paper untouched"
+
+
+def test_every_shipped_ramp_renders_without_raising(catalogue: Catalogue) -> None:
+    """The sweep of accept 2: one cell per glyph as uint8 RGB, for every shipped ramp."""
     for ramp in catalogue.ramps():
         image = render_ramp_preview(ramp.ramp)
         assert image.dtype.name == "uint8", ramp.id
         assert image.shape == (PREVIEW_CELL[1], PREVIEW_CELL[0] * len(ramp.ramp), 3), ramp.id
-        assert 0 <= int(image.min()) and int(image.max()) <= 255
-        assert int(image.max()) > int(image.min()), f"{ramp.id} renders as one flat colour"
+        assert 0 <= int(image.min()) and int(image.max()) <= 255, ramp.id
 
 
 def test_preview_composites_a_transparent_ink_over_white() -> None:
@@ -282,30 +280,30 @@ def test_first_selection_is_previewed_on_construction(
 # --- accept 4: selecting a set updates the preview within 100 ms -------------------
 
 
-def test_selecting_a_set_updates_the_preview_within_100_ms(
-    qapp: QApplication, catalogue: Catalogue
-) -> None:
-    """The measured repaint of a selection stays under the card's 100 ms budget."""
+def test_cold_selection_repaints_within_100_ms(qapp: QApplication, catalogue: Catalogue) -> None:
+    """Each category's last set repaints inside 100 ms with the glyph caches emptied first.
+
+    Nothing of the timed ramp was rasterised before: the cold path of browsing, not a hit.
+    """
     browser = GlyphBrowser(catalogue=catalogue)
+    timings: list[tuple[float, str]] = []
     try:
-        first, second = catalogue.ramps()[0], catalogue.ramps()[-1]
-        browser.select_ramp(first.id)  # warm the glyph mask cache of the module
-        browser.select_ramp(second.id)
-        assert browser.current_ramp() is second
-        start = time.perf_counter()
-        browser.select_ramp(first.id)
-        QApplication.processEvents()
-        elapsed = time.perf_counter() - start
-        assert browser.current_ramp() is first
-        assert elapsed < SELECT_DEADLINE, f"selection took {elapsed * 1000:.1f} ms"
-        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(first.ramp))
+        for category in catalogue.categories:
+            clear_glyph_caches()
+            target = category.ramps[-1]
+            start = time.perf_counter()
+            browser.select_ramp(target.id)
+            QApplication.processEvents()
+            timings.append((time.perf_counter() - start, target.id))
+            assert renderer._cached_mask.cache_info().misses >= len(target.ramp)  # really cold
+            assert browser.current_ramp() is target
     finally:
         browser.close()
+    slowest, ramp_id = max(timings)
+    assert slowest < SELECT_DEADLINE, f"{ramp_id} took {slowest * 1000:.1f} ms"
 
 
-def test_select_ramp_repaints_when_the_lists_already_sit_there(
-    qapp: QApplication, catalogue: Catalogue
-) -> None:
+def test_select_ramp_repaints_a_silent_list(qapp: QApplication, catalogue: Catalogue) -> None:
     """A silent list (already on that row) still repaints: the preview is not left stale."""
     browser = GlyphBrowser(catalogue=catalogue)
     try:
@@ -322,6 +320,49 @@ def test_select_ramp_repaints_when_the_lists_already_sit_there(
         browser.close()
 
 
+def test_cross_category_jump_announces_once(qapp: QApplication, catalogue: Catalogue) -> None:
+    """A jump to another category emits exactly one ramp_chosen, and it is the target.
+
+    The old path refilled the set list and selected row 0 first, announcing a spurious set.
+    """
+    browser = GlyphBrowser(catalogue=catalogue)
+    chosen: list[str] = []
+    browser.ramp_chosen.connect(chosen.append)
+    try:
+        target = catalogue.categories[-1].ramps[-1]
+        browser.select_ramp(target.id)
+        QApplication.processEvents()
+        assert chosen == [target.id]
+        assert browser.current_ramp() is target
+        back = catalogue.ramps()[0]
+        browser.select_ramp(back.id)
+        QApplication.processEvents()
+        assert chosen == [target.id, back.id]
+        assert browser.current_ramp() is back
+    finally:
+        browser.close()
+
+
+def test_pixmap_keeps_its_pixels_after_gc(qapp: QApplication, catalogue: Catalogue) -> None:
+    """The pixmap owns a copy: its pixels still equal the preview after gc and image churn."""
+    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
+    try:
+        expected = browser.preview_rgb8()
+        assert expected is not None
+        height, width = int(expected.shape[0]), int(expected.shape[1])
+        for _ in range(4):  # churn same-size images over memory a dangling QImage would read
+            poison = QImage(width, height, RGB888)
+            poison.fill(0xFF00FF)
+            del poison
+        gc.collect()
+        image = browser.preview_label.pixmap().toImage().convertToFormat(RGB888)
+        raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
+        lines = raw.reshape(image.height(), image.bytesPerLine())
+        assert np.array_equal(lines[:, : width * 3].reshape(height, width, 3), expected)
+    finally:
+        browser.close()
+
+
 def test_select_ramp_names_an_unknown_id(qapp: QApplication, catalogue: Catalogue) -> None:
     """An unknown id raises KeyError instead of silently showing something else."""
     browser = GlyphBrowser(catalogue=catalogue)
@@ -333,7 +374,7 @@ def test_select_ramp_names_an_unknown_id(qapp: QApplication, catalogue: Catalogu
 
 
 def test_ramp_chosen_follows_the_selection(qapp: QApplication, catalogue: Catalogue) -> None:
-    """Every selection announces its ramp id, which is how the app learns the choice."""
+    """Every list selection announces its ramp id, which is how the app learns the choice."""
     browser = GlyphBrowser(catalogue=catalogue)
     chosen: list[str] = []
     browser.ramp_chosen.connect(chosen.append)
@@ -342,7 +383,7 @@ def test_ramp_chosen_follows_the_selection(qapp: QApplication, catalogue: Catalo
         browser.category_list.setCurrentRow(len(catalogue.categories) - 1)
         browser.set_list.setCurrentRow(len(last.ramps) - 1)
         QApplication.processEvents()
-        assert chosen and chosen[-1] == last.ramps[-1].id
+        assert chosen[-1] == last.ramps[-1].id
     finally:
         browser.close()
 


CODER NOTES AND DEVIATIONS
- 30 tests ; suite 2004 verte ; ruff clean ; limites de lignes tenues (398 / 400).
- E1 déclarée sur le finding 5 (buffer QImage) : garde de contenu jugeable, pas de test qui échoue
  sur l'ancien code — comportement indéfini, non déterminisme assumé et documenté.
