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

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

TASK CARD
{{TASK_CARD}}

GATE RESULTS
{{GATE_SUMMARY}}

DIFF
{{DIFF}}

CODER NOTES AND DEVIATIONS
{{CODER_BLOCKS}}



CONTRACT EXCERPTS (version 0.1.0)


## §10 Text-halftone

`text` renderer. A flowing paragraph in a real font, not a character grid.

- Lay out the paragraph with real font metrics: kerning, line distance, word wrapping.
- Modulate per-glyph **weight, size and opacity** by the underlying `luma` (S2, decided
  2026-11-16): ink density must not collapse on a neutral palette.
- Cells may vary in size. `cell_aspect()` returns the nominal aspect; the renderer may vary a cell
  by ±50% and must still fill the output rectangle exactly.
- Options: `text` (string), `font`, `size`, `line_distance`, `kerning`, `size_mode`
  (`fixed` | `variable`), `weight_mode` (`fixed` | `variable`), `fg`/`bg`.
- `size_mode: fixed` keeps every glyph the same size and modulates only opacity. `variable` is the
  mode that makes the output look like art rather than ASCII.



TASK CARD
### L9b · Renderer `text` : répétition du paragraphe pour remplir la toile (H12)
- wave: 2 · deps: L9 | executor: OMH capable · review: strict · size: M
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §10
- origin: décision humaine H12 du 2026-11-18 (DEV-218). Le renderer pose son paragraphe UNE fois
  (`_flow` boucle sur `while idx < len(chars)`) : mesuré 496 caractères sur 12 960 cellules
  disponibles, soit 3 % de la hauteur de la toile à `pixel_size 10`. §10 exige que les cellules
  « must still fill the output rectangle exactly ».
- spec: boucler le texte jusqu'à ce que toutes les cellules soient couvertes. Option `repeat`
  (`fill` | `once`), défaut `fill` ; `once` conserve le comportement actuel pour qui veut un
  paragraphe unique. Ne change pas la modulation par `luma`, ni la césure, ni `size_mode`.
- accept:
  - sur un paragraphe court (une phrase) et un canevas large, la fraction de cellules portant de
    l'encre dépasse 90 % en mode `fill`.
  - `repeat: once` reproduit exactement le comportement d'avant (test de non-régression).
  - le texte bouclé respecte la césure et ne produit aucun glyphe hors du canevas (les tests de L9
    restent verts).
  - la luma du rendu d'un portrait sur fond neutre passe sous 0,90 et son contraste dépasse 0,20
    (aujourd'hui : 0,995 / 0,011).




GATE RESULTS
GATES (orchestrateur, rejoués après l'attempt 2) :
- G1 owns : ok, seuls text.py et test_text.py sont touchés (frères en vol sur glyph_ramp/ui/glitch).
- G2 pytest tests/test_text.py : 89 passed (orchestrateur, 14,7 s).
- G3 ruff (2 fichiers) : All checks passed.
- Diff attempt 2 vs HEAD : 214 insertions / 36 suppressions (additif — le fichier de tests grandit, pas de réécriture).
RE-REVUE PASS 1 (verdict FIX reçu) — VÉRIFIE finding par finding que le correctif du retry est réel :
1. [major] test_repeat_round_trips_through_json devait prouver un EFFET observable de repeat rechargé (pas une identité JSON).
2. [minor] _fit : dx/dy/bbox recalés sur le placed final (pas de sortie possible avec shift périmé).
3. [minor] _font_key(font) anticipé rétabli dans _read_options.
4. [minor] fixture PORTRAIT : plus de chemin /home/*** ; fixture déterministe dans le dépôt (ou générée), skip seulement si absente.
5. [minor] churn stylistique résorbé : variable locale font, diff limité au fonctionnel (docstrings/commentaires préservés ou rétablis).
Le codeur affirme avoir appliqué dans l'ordre du verdict. Juge le diff ATTEMPT 2 (cumulatif HEAD→arbre), pas la prose.



DIFF (cumulatif HEAD -> arbre, attempt 2)
diff --git a/lattice_core/renderers/text.py b/lattice_core/renderers/text.py
index 7946f5c..6be7fad 100644
--- a/lattice_core/renderers/text.py
+++ b/lattice_core/renderers/text.py
@@ -4,7 +4,7 @@ Glyphs use the font's advances, pair kerning and line distance, wrapped word by
 overlong word is cut character by character. Luma (S2, sRGB per AMD-010) drives each glyph's
 size, stroke and opacity. Wrapping and fit use the real rasterised ink box — the blit's own
 source of truth — so no ink leaves the canvas; a too-tall paragraph re-flows smaller. Caches
-are bounded and input-keyed (§3, H11).
+are bounded and input-keyed (§3, H11); repeat=fill loops the paragraph to the bottom (H12).
 """
 
 from __future__ import annotations
@@ -47,6 +47,7 @@ class TextOptions:
     kerning: float = 1.0
     size_mode: str = "variable"
     weight_mode: str = "variable"  # ignored when size_mode="fixed" (§10: opacity only)
+    repeat: str = "fill"  # fill loops the paragraph to the bottom (H12); once keeps L9
     fg: str = DEFAULT_FG
     bg: str = DEFAULT_BG
     seed: int = 0  # deterministic jitter; §10 omits the option but reproducibility needs it
@@ -146,6 +147,7 @@ def _read_options(style: RenderStyle) -> TextOptions:
         text=text, font=font, size=size, line_distance=line_distance, kerning=kerning,
         size_mode=_choice(raw, "size_mode", "variable", SIZE_MODES),
         weight_mode=_choice(raw, "weight_mode", "variable", WEIGHT_MODES),
+        repeat=_choice(raw, "repeat", "fill", ("fill", "once")),
         fg=cast(str, fg), bg=cast(str, bg), seed=seed)
 
 
@@ -210,7 +212,7 @@ def _ink_box(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[int
 
 
 class _Paragraph:
-    """One paragraph laid out over a fixed canvas: modulation, wrapping and fit."""
+    """One paragraph laid out over a fixed canvas: modulation, wrapping, repetition and fit."""
 
     def __init__(self, grid: CellGrid, options: TextOptions) -> None:
         """Measure the canvas, the font and the nominal point size of the paragraph."""
@@ -234,42 +236,51 @@ class _Paragraph:
         """Lay the paragraph out and return every glyph at its real, unclamped position."""
         if not self.chars or self.width <= 0 or self.height <= 0:
             return []
-        self._modulate()
+        if self.options.repeat == "once":
+            self._modulate(self._flow([self.base] * self.count))
         placed, dx, dy = self._fit()
         return self._place(placed, dx, dy)
 
-    def _modulate(self) -> None:
-        """Fill each character's ink and size factor from the cells under the nominal layout."""
-        key = self.font_key
-        jitter = np.random.default_rng(self.options.seed).uniform(-JITTER, JITTER, self.count)
+    def _modulate(self, placed: list[_Placed]) -> list[int]:
+        """Sample the luma under each placed glyph; return the sizes the next flow must use."""
+        key, fill = self.font_key, self.options.repeat == "fill"
+        n = len(placed) if fill else len(self.chars)
+        jitter = np.random.default_rng(self.options.seed).uniform(-JITTER, JITTER, n)
         table = np.ascontiguousarray(1.0 - color.linear_to_srgb(self.grid.luma), np.float32)
-        for glyph in self._flow([self.base] * self.count):
+        inks, fac = np.zeros(n, np.float32), np.ones(n, np.float32)
+        for glyph in placed:
             advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
             x = glyph.pen + 0.5 * advance
             y = glyph.baseline - 0.5 * _font(key, glyph.size).getmetrics()[0]
             col = min(self.grid.cols - 1, max(0, int(x // self.grid.cell_w)))
             row = min(self.grid.rows - 1, max(0, int(y // self.grid.cell_h)))
             ink = float(table[row, col])
-            self.inks[glyph.slot] = ink
+            inks[glyph.slot] = ink
             if self.options.size_mode == "variable":
-                self.factors[glyph.slot] = np.clip(
+                fac[glyph.slot] = np.clip(
                     MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR)
+        self.inks, self.factors, self.count = inks, fac, (len(placed) if fill else self.count)
+        return ([self.base] * self.count if self.options.size_mode == "fixed" else
+                [max(1, int(round(self.base * float(f)))) for f in self.factors])
 
     def _stroke(self, slot: int, size: int) -> int:
         """Return one glyph's §10 stroke from its ink and size (fixed mode never strokes)."""
         if self.options.size_mode == "fixed" or self.options.weight_mode == "fixed":
             return 0
-        return int(round(self.inks[slot] * max(1, size // 8)))
+        return int(round(self.inks[min(slot, len(self.inks) - 1)] * max(1, size // 8)))
 
     def _flow(self, sizes: list[int]) -> list[_Placed]:
-        """Lay characters out word by word, cutting any word too long for an empty line."""
+        """Lay words out, cutting overlong ones; fill repeats the paragraph to the bottom."""
         key, opt, chars = self.font_key, self.options, self.chars
+        fill = opt.repeat == "fill"
         asc, desc = _font(key, max(sizes) if sizes else self.base).getmetrics()
         lead = opt.line_distance * float(asc + desc)
         space = _glyph_metrics(key, self.base, " ")[0]
         placed: list[_Placed] = []
-        pen, line, idx = 0.0, 0, 0
-        while idx < len(chars):
+        pen, line, idx, occ = 0.0, 0, 0, 0
+        while idx < len(chars) or fill:
+            if idx >= len(chars):
+                idx = 0
             stop = idx
             while stop < len(chars) and chars[stop] != " ":
                 stop += 1
@@ -278,8 +289,10 @@ class _Paragraph:
                 continue
             runs, begin, used = [], idx, 0.0
             for o in range(idx, stop):  # a word too long for one line is cut here
-                box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
-                step = max(_glyph_metrics(key, sizes[o], chars[o])[0], box[2] - box[0])
+                j = o if not fill else occ + (o - idx)
+                size = sizes[j] if j < len(sizes) else self.base
+                box = _ink_box(key, chars[o], size, self._stroke(j, size))
+                step = max(_glyph_metrics(key, size, chars[o])[0], box[2] - box[0])
                 if used + step + 1.0 > self.width and o > begin:
                     runs.append((begin, o))
                     begin, used = o, 0.0
@@ -287,19 +300,26 @@ class _Paragraph:
             runs.append((begin, stop))
             for begin, end in runs:
                 word, cursor = [], 0.0
-                left = right = 0.0
+                left = right = bottom = 0.0
                 for o in range(begin, end):
-                    word.append((o, chars[o], cursor))
-                    box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
+                    j = o if not fill else occ + (o - begin)
+                    size = sizes[j] if j < len(sizes) else self.base
+                    word.append((o, chars[o], cursor, size, j))
+                    box = _ink_box(key, chars[o], size, self._stroke(j, size))
                     left, right = min(left, cursor + box[0]), max(right, cursor + box[2])
-                    cursor += _glyph_metrics(key, sizes[o], chars[o])[0]
+                    bottom = max(bottom, box[3])
+                    cursor += _glyph_metrics(key, size, chars[o])[0]
                     if o + 1 < end:
-                        cursor += opt.kerning * _kern(key, sizes[o], chars[o], chars[o + 1])
+                        cursor += opt.kerning * _kern(key, size, chars[o], chars[o + 1])
                 shift = -left if left < 0.0 else 0.0
                 if pen > 0.0 and pen + shift + max(cursor, right) + 1.0 > self.width:
                     pen, line = 0.0, line + 1
-                for o, ch, rel in word:
-                    placed.append(_Placed(ch, pen + shift + rel, asc + line * lead, sizes[o], o))
+                baseline = asc + line * lead
+                if fill and baseline + bottom > self.height:
+                    return placed
+                for _, ch, rel, size, slot in word:
+                    placed.append(_Placed(ch, pen + shift + rel, baseline, size, slot))
+                occ += end - begin
                 pen += cursor + space
             idx = stop + 1
         return placed
@@ -308,13 +328,16 @@ class _Paragraph:
         """Return placed glyphs and the shift that brings their real ink inside the canvas."""
         placed: list[_Placed] = []
         dx = dy = 0.0
-        key = self.font_key
-        for _ in range(_FIT_PASSES):
+        key, fill = self.font_key, self.options.repeat == "fill"
+        for p in range(_FIT_PASSES):
             if self.options.size_mode == "fixed":
                 sizes = [self.base] * self.count
             else:
                 sizes = [max(1, int(round(self.base * float(f)))) for f in self.factors]
             placed = self._flow(sizes)
+            # the last pass never skips: dx/dy must match the returned placed (no stale shift)
+            if fill and placed and p + 1 < _FIT_PASSES and self._modulate(placed) != sizes:
+                continue
             left = top = math.inf
             right = bottom = -math.inf
             for glyph in placed:
@@ -326,7 +349,7 @@ class _Paragraph:
             if left is math.inf:
                 left = right = top = bottom = 0.0
             dx, dy = max(0.0, -left), max(0.0, -top)
-            if right + dx <= self.width and bottom + dy <= self.height:
+            if (placed or not fill) and right + dx <= self.width and bottom + dy <= self.height:
                 break
             scale = min(self.width / max(right + dx, _EPSILON),
                         self.height / max(bottom + dy, _EPSILON)) * 0.98
@@ -344,7 +367,7 @@ class _Paragraph:
             asc, desc = _font(key, glyph.size).getmetrics()
             box_w = _glyph_metrics(key, glyph.size, glyph.character)[0]
             x, y = glyph.pen + dx, glyph.baseline + dy - asc
-            ink = float(self.inks[glyph.slot])
+            ink = float(self.inks[min(glyph.slot, len(self.inks) - 1)])
             out.append(TextGlyph(
                 glyph.character, x, y, box_w, float(asc + desc), opt.fg.lower(), opt.bg.lower(),
                 glyph.size, self._stroke(glyph.slot, glyph.size),
diff --git a/tests/test_text.py b/tests/test_text.py
index 841d4d6..3a521c9 100644
--- a/tests/test_text.py
+++ b/tests/test_text.py
@@ -1,6 +1,7 @@
-"""Tests for the text renderer (§3, §10) — card L9.
+"""Tests for the text renderer (§3, §10) — cards L9 and L9b (H12, DEV-218).
 
-Metrics are pinned against Pillow's own; renders compare across palettes (S2).
+Metrics are pinned against Pillow's own; renders compare across palettes (S2). Single-paragraph
+mechanics are pinned with repeat="once"; repeat="fill" must cover the canvas (L9b).
 """
 
 from __future__ import annotations
@@ -10,9 +11,12 @@ from pathlib import Path
 
 import numpy as np
 import pytest
+from PIL import Image as PILImage
 from PIL import ImageFont
 
+import lattice_core.dither  # noqa: F401  (registers the algorithms the pipeline resolves)
 from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer, list_renderers
+from lattice_core.pipeline import PaletteSpec, PipelineSpec, render
 from lattice_core.renderers import text as text_module
 from lattice_core.renderers.text import DEFAULT_BG, MIN_OPACITY, TextGlyph, TextRenderer
 from lattice_core.types import Palette
@@ -25,6 +29,7 @@ SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
 _WORDS = ("lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
           "canvas grid luma ink paper palette neutral source image renderer").split()
 PARAGRAPH = " ".join(_WORDS[(i * 7) % len(_WORDS)] for i in range(200))
+SHORT = "Lattice renders a paragraph in a real font."
 RENDERER = TextRenderer()
 
 
@@ -149,7 +154,7 @@ def test_ink_bbox_detects_an_artificially_thick_stroke(extra):
 
 def test_unbreakable_word_is_cut_and_reflows_on_a_narrower_canvas():
     word = "@" * 400
-    options = {"text": word, "size_mode": "fixed", "size": 8}
+    options = {"text": word, "size_mode": "fixed", "size": 8, "repeat": "once"}
     wide, narrow = _canvas(40, 20), _canvas(20, 40)
     for grid in (wide, narrow):
         glyphs = _layout(grid, **options)
@@ -165,19 +170,20 @@ def test_unbreakable_word_is_cut_and_reflows_on_a_narrower_canvas():
 def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell_w, cell_h):
     grid = _canvas(cols, rows, cell_w, cell_h)
     width, height = cols * cell_w, rows * cell_h
-    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
+    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode, repeat="once")
     assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
     assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
     assert len(_line_tops(glyphs)) >= 10
     for glyph in glyphs:  # real positions from layout(), including the stroke margin
         _assert_ink_inside(glyph, width, height)
-    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
+    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode, repeat="once")
     assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0
 
 
 def test_layout_reports_real_unclamped_positions():
     text, kern = "unclamped", 1.0
-    glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern, size_mode="fixed")
+    glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern,
+                     size_mode="fixed", repeat="once")
     font = _default_font(glyphs[0].size)
     pen = 0.0
     for index, glyph in enumerate(glyphs):
@@ -210,7 +216,7 @@ def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
     if not SYSTEM_FONT.is_file():
         pytest.skip("no system TrueType font available")
     first, second = _layout(_canvas(30, 14), font=str(SYSTEM_FONT), size=12, kerning=kerning,
-                            size_mode="fixed", text="AV")
+                            size_mode="fixed", text="AV", repeat="once")
     reference = ImageFont.truetype(str(SYSTEM_FONT), 12)
     pair = reference.getlength("AV") - reference.getlength("A") - reference.getlength("V")
     assert pair != 0.0, "the pinned font must kern AV for this test to mean anything"
@@ -222,7 +228,7 @@ def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
 def test_line_distance_scales_the_leading():
     grid = _canvas(12, 30)
     options = {"text": "one two three four five six seven eight nine ten",
-               "size": 8, "size_mode": "fixed"}
+               "size": 8, "size_mode": "fixed", "repeat": "once"}
     tight = _line_tops(_layout(grid, line_distance=1.0, **options))
     loose = _line_tops(_layout(grid, line_distance=2.0, **options))
     ascent, descent = _default_font(8).getmetrics()
@@ -234,7 +240,7 @@ def test_words_wrap_when_they_no_longer_fit_the_width():
     font = _default_font(10)
     word, space = float(font.getlength("ab")), float(font.getlength(" "))
     wide, narrow = int(3 * word + 3 * space), int(2 * word + space)
-    options = {"text": "ab ab ab", "size": 10, "size_mode": "fixed"}
+    options = {"text": "ab ab ab", "size": 10, "size_mode": "fixed", "repeat": "once"}
     assert _line_tops(_layout(_canvas(wide, 8, 1, 16), **options)) == [0.0]
     assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3
 
@@ -396,3 +402,152 @@ def test_an_empty_canvas_renders_nothing():
                      luma=np.zeros((0, 0), np.float32), samples=np.zeros((0, 0, 1), np.float32))
     assert RENDERER.layout(empty, _style(text="nothing")) == []
     assert RENDERER.render(empty, BW, _style(text="nothing")).size == (0, 0)
+
+
+# --- L9b (H12, DEV-218): repeat=fill loops the paragraph until the canvas is covered ---
+
+
+def _inked_cells(frame: np.ndarray, grid: CellGrid) -> np.ndarray:
+    """Return the (rows, cols) map of cells carrying at least one pixel off the white paper."""
+    inked = np.any(frame != np.float32(1.0), axis=-1)
+    return inked.reshape(grid.rows, grid.cell_h, grid.cols, grid.cell_w).any(axis=(1, 3))
+
+
+def _srgb_luma(rgb: np.ndarray) -> np.ndarray:
+    """Return the sRGB-coded Rec.709 luma of a uint8 RGB image (the H12 reference scale)."""
+    code = np.clip(np.asarray(rgb, np.float32) / 255.0, 0.0, 1.0)
+    return np.float32(0.2126) * code[..., 0] + np.float32(0.7152) * code[..., 1] \
+        + np.float32(0.0722) * code[..., 2]
+
+
+@pytest.mark.parametrize("flat", [0.0, 0.2, 0.5])
+def test_fill_covers_over_90_percent_of_cells_on_a_short_text_and_large_canvas(flat):
+    grid = _canvas(120, 108, 5, 10, flat=flat)  # DEV-218 geometry: 12 960 cells, pixel_size 10
+    covered = _inked_cells(_frame(grid, text=SHORT), grid)
+    assert float(covered.mean()) > 0.90, "fill must cover the canvas, not just the frame"
+    assert covered[0].mean() > 0.5 and covered[-1].mean() > 0.5, "top and bottom must be reached"
+    once = _inked_cells(_frame(grid, text=SHORT, repeat="once"), grid)
+    assert float(once.mean()) < 0.10, "once keeps the L9 behaviour: a mostly empty canvas"
+    for glyph in _layout(grid, text=SHORT):
+        _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+
+
+def test_repeat_default_is_fill_and_once_keeps_a_single_paragraph():
+    grid = _canvas(40, 30)
+    once = _layout(grid, text=SHORT, repeat="once")
+    assert len(once) == len(SHORT.replace(" ", "")), "once lays the paragraph exactly once"
+    fill = _layout(grid, text=SHORT)
+    assert fill == _layout(grid, text=SHORT, repeat="fill"), "the default must be fill"
+    assert len(fill) > len(once), "fill repeats the paragraph on a canvas taller than one pass"
+    assert np.array_equal(_frame(grid, text=SHORT), _frame(grid, text=SHORT, repeat="fill"))
+
+
+@pytest.mark.parametrize("mode", ["fixed", "variable"])
+@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
+                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16), (20, 40, 3, 5)])
+def test_fill_flows_the_paragraph_in_order_without_overflow(mode, cols, rows, cell_w, cell_h):
+    grid = _canvas(cols, rows, cell_w, cell_h)
+    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
+    assert glyphs and all(isinstance(glyph, TextGlyph) for glyph in glyphs)
+    chars = PARAGRAPH.replace(" ", "")
+    repeated = chars * (len(glyphs) // len(chars) + 1)
+    assert "".join(g.character for g in glyphs) == repeated[:len(glyphs)], "césure perdue"
+    for glyph in glyphs:  # real positions from layout(), including the stroke margin
+        _assert_ink_inside(glyph, cols * cell_w, rows * cell_h)
+
+
+def test_fill_cuts_an_unbreakable_word_and_stays_inside_the_canvas():
+    word, options = "@" * 400, {"text": "@" * 400, "size_mode": "fixed", "size": 8}
+    wide, narrow = _canvas(40, 20), _canvas(20, 40)
+    for grid in (wide, narrow):
+        glyphs = _layout(grid, **options)
+        assert len(glyphs) >= len(word), "fill must at least complete the first paragraph"
+        assert "".join(g.character for g in glyphs) == "@" * len(glyphs)
+        for glyph in glyphs:
+            _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+    assert len(_line_tops(_layout(narrow, **options))) > len(_line_tops(_layout(wide, **options)))
+
+
+def test_fill_on_a_synthetic_portrait_drops_luma_and_raises_contrast():
+    rows, cols = 40, 60  # a dark subject on a mid-tone background, deterministic
+    luma = np.full((rows, cols), 0.8, np.float32)
+    yy, xx = np.mgrid[0:rows, 0:cols]
+    luma[((yy - 20) / 16.0) ** 2 + ((xx - 30) / 22.0) ** 2 <= 1.0] = 0.08
+    grid = CellGrid(cols=cols, rows=rows, cell_w=5, cell_h=10,
+                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(),
+                    luma=luma.copy(), samples=luma[:, :, None].copy())
+    lum = _srgb_luma(_image(grid, NEUTRAL, text=SHORT))
+    assert float(lum.mean()) < 0.90, "a filled text halftone must not come out near-white"
+    assert float(lum.std()) > 0.20, "the subject must show through the modulation"
+
+
+def _portrait_fixture(tmp_path: Path) -> Path:
+    """Write a deterministic portrait (dark head and shoulders, neutral background) as PNG."""
+    width, height = 360, 480
+    yy, xx = np.mgrid[0:height, 0:width]
+    luma = np.full((height, width), 0.8, np.float32)
+    head = ((yy - 190.0) / 120.0) ** 2 + ((xx - 180.0) / 95.0) ** 2 <= 1.0
+    body = (yy > 330.0) & (((xx - 180.0) / 170.0) ** 2 + ((yy - 480.0) / 160.0) ** 2 <= 1.0)
+    luma[head | body] = 0.08
+    rgb = np.repeat((luma * 255.0)[..., None], 3, axis=-1).astype(np.uint8)
+    path = tmp_path / "portrait.png"
+    PILImage.fromarray(rgb).save(path)
+    return path
+
+
+@pytest.mark.parametrize("pixel_size", [10, 24])
+def test_fill_on_a_generated_portrait_passes_the_dev218_thresholds(pixel_size, tmp_path):
+    portrait = _portrait_fixture(tmp_path)
+    if not portrait.is_file():
+        pytest.skip("no portrait fixture available")
+    src = np.asarray(PILImage.open(portrait).convert("RGB"), np.float32) / 255.0
+    spec = PipelineSpec(pixel_size=pixel_size, algorithm_id="bayer_4",
+                        palette=PaletteSpec(source="builtin", name="grey_8"), renderer="text",
+                        renderer_style={"text": text_module.DEFAULT_TEXT, "size_mode": "variable",
+                                        "weight_mode": "variable", "fg": "#000000",
+                                        "bg": "#ffffff"})
+    lum = _srgb_luma(render(src, spec))
+    assert float(lum.mean()) < 0.90  # measured 0.9997 before L9b at pixel_size 10
+    assert float(lum.std()) > 0.20  # measured 0.0112 before L9b at pixel_size 10
+
+
+@pytest.mark.parametrize("value", ["loop", "", None, 3, True])
+def test_invalid_repeat_raises_value_error_naming_the_option(value):
+    with pytest.raises(ValueError) as excinfo:
+        RENDERER.render(_canvas(6, 3), BW, _style(text="repeat", repeat=value))
+    assert "repeat" in str(excinfo.value)
+    assert "fill" in str(excinfo.value) and "once" in str(excinfo.value)
+
+
+@pytest.mark.parametrize("repeat", ["fill", "once"])
+def test_repeat_round_trips_through_json(repeat):
+    options = {"text": SHORT, "repeat": repeat, "seed": 2}
+    style = _style(**options)
+    assert json.loads(json.dumps(dict(style.options))) == options
+    grid = _canvas(40, 30)  # taller than one paragraph pass: the reloaded option must show
+    reloaded = _style(**json.loads(json.dumps(dict(style.options))))
+    glyphs = RENDERER.layout(grid, BW, reloaded)
+    once = _layout(grid, text=SHORT, repeat="once", seed=2)
+    fill = _layout(grid, text=SHORT, repeat="fill", seed=2)
+    assert len(once) == len(SHORT.replace(" ", "")) < len(fill), "fill must repeat, once must not"
+    assert len(glyphs) == (len(once) if repeat == "once" else len(fill)), \
+        "the reloaded 'repeat' option had no observable effect on the layout"
+    assert np.array_equal(np.asarray(RENDERER.render(grid, BW, style)),
+                          np.asarray(RENDERER.render(grid, BW, reloaded)))
+
+
+def test_fill_is_deterministic_for_a_given_seed():
+    grid, options = _canvas(24, 10), {"text": SHORT, "seed": 7}
+    assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
+    assert _layout(grid, **options) == _layout(grid, **options)
+    assert not np.array_equal(_frame(grid, **options), _frame(grid, text=SHORT, seed=8))
+
+
+def test_fill_with_a_real_font_repeats_and_keeps_the_geometry():
+    if not SYSTEM_FONT.is_file():
+        pytest.skip("no system TrueType font available")
+    grid = _canvas(20, 8)
+    img = RENDERER.render(grid, BW, _style(font=str(SYSTEM_FONT), text=SHORT))
+    assert img.size == (20 * CELL_W, 8 * CELL_H)
+    glyphs = _layout(grid, font=str(SYSTEM_FONT), text=SHORT)
+    assert len(glyphs) > len(SHORT.replace(" ", "")), "a real font must repeat too"




CODER NOTES AND DEVIATIONS (attempt 2, from transcript)
(vidé)