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

## §3 The CellRenderer contract

This is the architectural bet of the project. Everything else is an implementation detail.

```python
@dataclass(frozen=True)
class CellGrid:
    cols: int
    rows: int
    cell_w: int
    cell_h: int
    index: np.ndarray      # (rows, cols) int32, palette index per cell
    coverage: np.ndarray   # (rows, cols) float32 in [0, 1], ink coverage per cell
    luma: np.ndarray       # (rows, cols) float32, linear luminance of the SOURCE cell
                           # computed before quantisation (S2, decided 2026-11-16)
    samples: np.ndarray    # (rows, cols, k) float32 in [0, 1], sub-cell luminance
    subindex: np.ndarray | None = None  # (rows, cols, sx*sy) int32, palette index per
                                        # sub-point, present when subgrid != (1, 1) (S3)

@dataclass(frozen=True)
class RenderStyle:
    options: Mapping[str, object]   # renderer-specific, JSON-serialisable

class CellRenderer(Protocol):
    name: str
    def cell_aspect(self) -> float: ...
    def subgrid(self) -> tuple[int, int]: ...  # default (1, 1); braille (2, 4), sextant (2, 3) (S3)
    def consumes(self) -> frozenset[str]: ...  # subset of {"index", "luma", "samples",
                                               # "coverage", "subindex"} (H11)
    def render(self, grid: CellGrid, palette: np.ndarray, style: RenderStyle) -> Image.Image: ...
```

Registry: `register_renderer`, `get_renderer(name)`, `list_renderers()`.

Normative invariants, each one a test:

1. `render` returns an image of exactly `(cols * cell_w, rows * cell_h)` pixels.
2. `render` is pure: identical inputs produce identical output. Module-level state is restricted
   to deterministic, input-keyed caches (e.g. glyph shape vectors, §9); a cache never changes the
   output (H11, decided 2026-11-16).
3. `render` does not mutate `grid` or `palette`.
4. `cell_aspect()` returns width/height of one cell. The pipeline uses it to choose the grid so the
   output preserves the source aspect ratio.
5. `name` is unique across the registry and stable across versions.
6. `style.options` round-trips through JSON without loss.

**Why the split.** The dithering stage decides *which palette entry* each cell receives. The
renderer decides *how to draw that entry*: a solid square, a glyph whose density matches the
entry's luminance, a braille bitmask, a paragraph of text. This is what lets 33 dithering
algorithms serve three applications without being rewritten.

`coverage` is derived once, in the pipeline, not by the renderer:

```
lum(c)      = 0.2126 R + 0.7152 G + 0.0722 B, computed in linear light
coverage    = (lum(palette[index]) - lum_min) / (lum_max - lum_min)
coverage    = 0.0 where lum_max == lum_min
```

`samples` is produced by supersampling the source cell on a `k`-point stencil. `k` is a renderer
property: 1 for `pixel`, 6 for `glyph_shape`, 8 for braille, 6 for sextant, 4 for quadrant.
The stencil geometry is renderer-specific and declared by the optional `sample_points()` method
when it matters (glyph_shape: six circles at top/middle/bottom × left/right); the default is a
uniform grid of `k` points over the cell, sampled by the pipeline (H11, decided 2026-11-16).

**Luma — independent of the palette (S2, decided 2026-11-16).** `grid.luma` is the linear
luminance of the source cell (step-7 pixels, computed in linear light) taken BEFORE quantisation.
Each renderer declares what it consumes via `consumes()`; `glyph_ramp` and `glyph_shape` consume
`luma` for ink-density ramps, so a black/white palette still uses the full glyph ramp. The L2
"coverage is monotone" test stays; a new L2 test asserts "luma is continuous and independent of
the palette".

**Sub-point dithering (S3, decided 2026-11-16).** A renderer may declare `subgrid = (sx, sy)`
(braille 2×4, sextant 2×3). The pipeline then runs the chosen algorithm at resolution
`(rows·sy, cols·sx)` and hands the renderer `grid.subindex: (rows, cols, sx·sy) int32`. The
bitmask and text renderers only pack sub-points into codepoints; the single boolean `dither`
option is removed. New L2 test: sub-point coverage is monotone at the subgrid resolution.

**Float frames (H11, decided 2026-11-16).** A renderer may implement the optional
`render_frame(grid, palette, style) -> np.ndarray float32 (H, W, 3)` in [0, 1]. When available,
step 11 uses it and the pipeline passes that unrounded frame to step 12: post-effects must never
receive an 8-bit-rounded frame when the palette mapping is exact (L2 blocker, resolved). `pixel`
implements `render_frame` as `apply_palette` + per-axis repeat; `render()` remains its
rasterisation and every renderer must keep the two consistent.

**Structured output (H11, decided 2026-11-16).** Glyph renderers may implement the optional
`layout(grid, style)` returning the placed glyphs (character, x, y, width, height, fill) that
`render()` rasterises. When available, §11 export consumes solely `layout()`, so PNG, SVG and
text exports cannot diverge. Without it, a renderer renders pixels only.



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

### L9 · Text-halftone renderer
- wave: 1 · deps: L2b · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §3 §10
- spec: implement `text` per §10. Lay out a flowing paragraph with real font metrics: kerning, line
  distance, word wrapping. Modulate per-glyph weight, size and opacity by `luma` (S2/H11 —
  l'encre ne doit pas s'effondrer sur une palette neutre). Cells may vary
  in size by ±50 % and must still fill the output rectangle exactly. Options: `text`, `font`,
  `size`, `line_distance`, `kerning`, `size_mode` (`fixed` | `variable`), `weight_mode`
  (`fixed` | `variable`), `fg`, `bg`.
- accept:
  - `size_mode: "fixed"` produces glyphs of identical size; `"variable"` produces at least 5
    distinct sizes on a gradient.
  - the output rectangle is filled exactly, with no gap and no overflow, for both modes.
  - a 200-word paragraph wraps without clipping and without a single glyph outside the canvas.
  - the same text and seed produce identical output across two calls.
  - an empty `text` raises `ValueError` naming the option.



GATE RESULTS (L9, attempt 5 — DEV-217 étendue, cycle 4 borné, sur hy4-flash-free)
- `text.py` 396 l, `test_text.py` 398 l, 64 tests owned verts, suite 2059 passed / 1 skipped,
  ruff clean, contract OK.
- Le diff ci-dessous est celui de l'attempt 5 SEUL (HEAD~1 → HEAD).

CE QUE LE CODEUR DÉCLARE
1. `_ink_box()` dérive la bbox réelle de `_mask` (trait inclus) ; `_flow` décale chaque mot par son
   encre gauche et coupe selon l'encre ; `_fit` mesure cette même bbox.
2. `_flow` découpe tout mot ne tenant pas sur une ligne vide. Il annonce : 400 « @ » sur 320×320
   passent de 80 glyphes dehors à 0, 8 lignes à 320 px et 16 à 160 px.
3. Il annonce aussi : « MWMWMW »×200 110 → 0 ; « lattice text halftone »×40 13 → 0 ; balayage de
   5 canevas × 2 luma × 4 textes × 2 modes = 0 débordement.
4. `_fit` reste borné à 8 passes, s'arrête à size 1, pas de boucle infinie. Opacité, kerning,
   modulation de taille et couleurs inchangés.
5. `_assert_ink_inside` exige zéro débordement (plus de tolérance `size//8`).

MES MESURES INDÉPENDANTES — ET UNE CORRECTION QUE JE DOIS TE SIGNALER
Mon protocole de mesure de l'attempt précédent (celui qui avait révélé A et B) était FAUX sur un
point : je mesurais la bbox du masque renvoyé par `_mask`, qui inclut un padding de `stroke + 1` px.
Ce padding comptait comme de l'encre et fabriquait un dépassement fictif de 1,0 px systématique.
En mesurant la bbox des pixels d'encre NON NULS, puis en rejouant 15 combinaisons
(5 textes × 3 tailles de cellule, modes fixed et variable) :
- « @ »×400 : 0 débordement sur les 6 combinaisons ; « lattice text halftone »×40 : 0 sur les 5 ;
  « MWMWMW »×200 : 0 sur 4 des 6.
- Les 2 cas restants sont un canevas littéralement trop petit (cellule 3×5 sur 40×10 cellules =
  120×50 px, mode variable, 1400 caractères). J'ai cherché la frontière : en 3×5 il faut H ≥ 80 px ;
  dès la cellule 4×6 (160×60) ou 8×16 (320×160), 0 débordement.

QUESTION EXPLICITE : le comportement sur un canevas où le texte ne peut PAS tenir même à size 1 est-il
acceptable tel quel (arrêt à size 1, positions réelles rapportées par `layout()`, clipping au blit),
ou faut-il une erreur typée / un warning ? La déviation E1 du codeur porte exactement là-dessus.

DIFF (attempt 5 : HEAD~1 → HEAD)

diff --git a/lattice_core/renderers/text.py b/lattice_core/renderers/text.py
index 129c20c..7946f5c 100644
--- a/lattice_core/renderers/text.py
+++ b/lattice_core/renderers/text.py
@@ -1,13 +1,10 @@
-"""The text renderer: a flowing paragraph in a real font, modulated by luma (§10).
-
-Glyphs are laid out with the font's own advances, pair kerning and line distance, wrapped
-word by word to the canvas width, so the output reads as a paragraph and not a grid. The
-linear luma of the cell under a glyph (S2, re-encoded to sRGB per AMD-010) drives its size
-(0.5x to 1.5x, §10), stroke weight and opacity, so ink never collapses on a neutral palette.
-The paper paints every pixel, ink is clipped to the canvas, and an overflowing paragraph is
-re-flowed smaller rather than clipped. Fonts, metrics and masks are bounded input-keyed
-caches that never change the output (§3 invariant 2, H11). The optional `seed`, absent from
-§10's option list, drives a deterministic jitter kept for reproducibility.
+"""The text renderer: a flowing paragraph modulated by luma (§10).
+
+Glyphs use the font's advances, pair kerning and line distance, wrapped word by word; an
+overlong word is cut character by character. Luma (S2, sRGB per AMD-010) drives each glyph's
+size, stroke and opacity. Wrapping and fit use the real rasterised ink box — the blit's own
+source of truth — so no ink leaves the canvas; a too-tall paragraph re-flows smaller. Caches
+are bounded and input-keyed (§3, H11).
 """
 
 from __future__ import annotations
@@ -41,11 +38,7 @@ _EMPTY_MASK.setflags(write=False)
 
 @dataclass(frozen=True)
 class TextOptions:
-    """Validated options of one text render (§10).
-
-    Fixed size mode forces fixed weight (§10: opacity alone then varies); ``seed`` is a
-    tolerated extra that only drives the deterministic jitter.
-    """
+    """Validated options of one render (§10); fixed size forces fixed weight (opacity only)."""
 
     text: str = DEFAULT_TEXT
     font: str | None = None
@@ -107,23 +100,18 @@ class TextRenderer:
 
     def render_frame(self, grid: CellGrid, palette: Palette, style: RenderStyle) -> np.ndarray:
         """Return the unrounded frame: ink over a fully painted paper, float32 in [0, 1]."""
-        options = _read_options(style)
-        fg = _parse_colour(options.fg)
+        opt = _read_options(style)
+        fg, key = _parse_colour(opt.fg), _font_key(opt.font)
         shape = (grid.rows * grid.cell_h, grid.cols * grid.cell_w, 3)
-        frame = np.full(shape, _parse_colour(options.bg), np.float32)
-        font_key = _font_key(options.font)
-        for glyph in _Paragraph(grid, options).glyphs():
-            _blit(frame, glyph, fg, font_key)
+        frame = np.full(shape, _parse_colour(opt.bg), np.float32)
+        for glyph in _Paragraph(grid, opt).glyphs():
+            _blit(frame, glyph, fg, key)
         return np.ascontiguousarray(frame, dtype=np.float32)
 
     def layout(
         self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
     ) -> list[TextGlyph]:
-        """Return every laid-out glyph at its real position, in reading order (§3, §11).
-
-        Both the §3 ``layout(grid, style)`` and ``layout(grid, palette, style)`` forms are
-        accepted; only fg/bg and luma change the output, never the palette.
-        """
+        """Return every laid-out glyph at its real position (both §3 call forms accepted)."""
         _, style = _layout_arguments(palette, style)
         return _Paragraph(grid, _read_options(style)).glyphs()
 
@@ -158,8 +146,7 @@ def _read_options(style: RenderStyle) -> TextOptions:
         text=text, font=font, size=size, line_distance=line_distance, kerning=kerning,
         size_mode=_choice(raw, "size_mode", "variable", SIZE_MODES),
         weight_mode=_choice(raw, "weight_mode", "variable", WEIGHT_MODES),
-        fg=cast(str, fg), bg=cast(str, bg), seed=seed,
-    )
+        fg=cast(str, fg), bg=cast(str, bg), seed=seed)
 
 
 def _number(raw: dict, key: str, default: float) -> float:
@@ -212,6 +199,16 @@ def _kern(font_key: _FontKey, size: int, left: str, right: str) -> float:
     return float(font.getlength(left + right) - font.getlength(left) - font.getlength(right))
 
 
+@lru_cache(maxsize=_CACHE)
+def _ink_box(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[int, ...]:
+    """Return the glyph's real rasterised ink box (x0, y0, x1, y1), stroke included (§10)."""
+    mask, left, top = _mask(font_key, char, size, stroke)
+    cols, rows = np.flatnonzero(mask.any(axis=0)), np.flatnonzero(mask.any(axis=1))
+    if not len(cols) or not len(rows):
+        return (0, 0, 0, 0)
+    return (left + cols[0], top + rows[0], left + cols[-1] + 1, top + rows[-1] + 1)
+
+
 class _Paragraph:
     """One paragraph laid out over a fixed canvas: modulation, wrapping and fit."""
 
@@ -220,12 +217,10 @@ class _Paragraph:
         if np.shape(grid.luma) != (grid.rows, grid.cols):
             raise ValueError(
                 f"text renderer needs grid.luma of shape {(grid.rows, grid.cols)}, "
-                f"got {np.shape(grid.luma)}"
-            )
+                f"got {np.shape(grid.luma)}")
         self.grid = grid
         self.options = options
-        self.width = grid.cols * grid.cell_w
-        self.height = grid.rows * grid.cell_h
+        self.width, self.height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
         self.chars = list(" ".join(options.text.split()))
         self.font_key = _font_key(options.font)
         ratio = sum(_font(self.font_key, _PROBE_SIZE).getmetrics()) / float(_PROBE_SIZE)
@@ -245,8 +240,8 @@ class _Paragraph:
 
     def _modulate(self) -> None:
         """Fill each character's ink and size factor from the cells under the nominal layout."""
-        options, key = self.options, self.font_key
-        jitter = np.random.default_rng(options.seed).uniform(-JITTER, JITTER, self.count)
+        key = self.font_key
+        jitter = np.random.default_rng(self.options.seed).uniform(-JITTER, JITTER, self.count)
         table = np.ascontiguousarray(1.0 - color.linear_to_srgb(self.grid.luma), np.float32)
         for glyph in self._flow([self.base] * self.count):
             advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
@@ -256,52 +251,64 @@ class _Paragraph:
             row = min(self.grid.rows - 1, max(0, int(y // self.grid.cell_h)))
             ink = float(table[row, col])
             self.inks[glyph.slot] = ink
-            if options.size_mode == "variable":
+            if self.options.size_mode == "variable":
                 self.factors[glyph.slot] = np.clip(
-                    MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR
-                )
+                    MIN_FACTOR + ink + jitter[glyph.slot], MIN_FACTOR, MAX_FACTOR)
+
+    def _stroke(self, slot: int, size: int) -> int:
+        """Return one glyph's §10 stroke from its ink and size (fixed mode never strokes)."""
+        if self.options.size_mode == "fixed" or self.options.weight_mode == "fixed":
+            return 0
+        return int(round(self.inks[slot] * max(1, size // 8)))
 
     def _flow(self, sizes: list[int]) -> list[_Placed]:
-        """Lay the characters out word by word and wrap each line at the canvas width."""
-        key, options, chars = self.font_key, self.options, self.chars
-        lead_size = max(sizes) if sizes else self.base
-        ascent, descent = _font(key, lead_size).getmetrics()
-        lead = options.line_distance * float(ascent + descent)
+        """Lay characters out word by word, cutting any word too long for an empty line."""
+        key, opt, chars = self.font_key, self.options, self.chars
+        asc, desc = _font(key, max(sizes) if sizes else self.base).getmetrics()
+        lead = opt.line_distance * float(asc + desc)
+        space = _glyph_metrics(key, self.base, " ")[0]
         placed: list[_Placed] = []
-        pen, line, index = 0.0, 0, 0
-        while index < len(chars):
-            stop = index
+        pen, line, idx = 0.0, 0, 0
+        while idx < len(chars):
+            stop = idx
             while stop < len(chars) and chars[stop] != " ":
                 stop += 1
-            if stop == index:  # a separator: nothing to draw, its advance is added below
-                index += 1
+            if stop == idx:  # a separator: nothing to draw
+                idx += 1
                 continue
-            word: list[tuple[int, str, float]] = []
-            cursor = right = left = 0.0
-            for offset in range(index, stop):
-                step, x0, _, x1, _ = _glyph_metrics(key, sizes[offset], chars[offset])
-                word.append((offset, chars[offset], cursor))
-                left = min(left, cursor + x0)
-                right = max(right, cursor + x1)
-                cursor += step
-                if offset + 1 < stop:
-                    cursor += options.kerning * _kern(
-                        key, sizes[offset], chars[offset], chars[offset + 1]
-                    )
-            if pen > 0.0 and pen + max(cursor, right) + 1.0 > self.width:
-                pen, line = 0.0, line + 1
-            shift = -left if left < 0.0 else 0.0
-            for offset, char, relative in word:
-                placed.append(_Placed(char, pen + shift + relative, ascent + line * lead,
-                                      sizes[offset], offset))
-            pen += cursor + _glyph_metrics(key, self.base, " ")[0]
-            index = stop + 1
+            runs, begin, used = [], idx, 0.0
+            for o in range(idx, stop):  # a word too long for one line is cut here
+                box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
+                step = max(_glyph_metrics(key, sizes[o], chars[o])[0], box[2] - box[0])
+                if used + step + 1.0 > self.width and o > begin:
+                    runs.append((begin, o))
+                    begin, used = o, 0.0
+                used += step
+            runs.append((begin, stop))
+            for begin, end in runs:
+                word, cursor = [], 0.0
+                left = right = 0.0
+                for o in range(begin, end):
+                    word.append((o, chars[o], cursor))
+                    box = _ink_box(key, chars[o], sizes[o], self._stroke(o, sizes[o]))
+                    left, right = min(left, cursor + box[0]), max(right, cursor + box[2])
+                    cursor += _glyph_metrics(key, sizes[o], chars[o])[0]
+                    if o + 1 < end:
+                        cursor += opt.kerning * _kern(key, sizes[o], chars[o], chars[o + 1])
+                shift = -left if left < 0.0 else 0.0
+                if pen > 0.0 and pen + shift + max(cursor, right) + 1.0 > self.width:
+                    pen, line = 0.0, line + 1
+                for o, ch, rel in word:
+                    placed.append(_Placed(ch, pen + shift + rel, asc + line * lead, sizes[o], o))
+                pen += cursor + space
+            idx = stop + 1
         return placed
 
     def _fit(self) -> tuple[list[_Placed], float, float]:
-        """Return the placed glyphs and the shift that brings their ink inside the canvas."""
+        """Return placed glyphs and the shift that brings their real ink inside the canvas."""
         placed: list[_Placed] = []
         dx = dy = 0.0
+        key = self.font_key
         for _ in range(_FIT_PASSES):
             if self.options.size_mode == "fixed":
                 sizes = [self.base] * self.count
@@ -311,15 +318,15 @@ class _Paragraph:
             left = top = math.inf
             right = bottom = -math.inf
             for glyph in placed:
-                x0, y0, x1, y1 = _glyph_metrics(self.font_key, glyph.size, glyph.character)[1:]
-                left = min(left, glyph.pen + x0)
-                right = max(right, glyph.pen + x1)
-                top = min(top, glyph.baseline + y0)
-                bottom = max(bottom, glyph.baseline + y1)
+                stroke = self._stroke(glyph.slot, glyph.size)
+                box = _ink_box(key, glyph.character, glyph.size, stroke)
+                left, right = min(left, glyph.pen + box[0]), max(right, glyph.pen + box[2])
+                top = min(top, glyph.baseline + box[1])
+                bottom = max(bottom, glyph.baseline + box[3])
             if left is math.inf:
                 left = right = top = bottom = 0.0
             dx, dy = max(0.0, -left), max(0.0, -top)
-            if right + dx + 1.0 <= self.width and bottom + dy + 1.0 <= self.height:
+            if right + dx <= self.width and bottom + dy <= self.height:
                 break
             scale = min(self.width / max(right + dx, _EPSILON),
                         self.height / max(bottom + dy, _EPSILON)) * 0.98
@@ -330,27 +337,18 @@ class _Paragraph:
         return placed, dx, dy
 
     def _place(self, placed: list[_Placed], dx: float, dy: float) -> list[TextGlyph]:
-        """Return glyphs at their real positions with size, stroke and opacity (§10).
-
-        Fixed size mode forces fixed weight: §10 says opacity alone carries the modulation,
-        so an explicit `weight_mode: variable` is deliberately ignored in that mode.
-        """
+        """Return glyphs at their real positions with size, stroke and opacity (§10)."""
         out: list[TextGlyph] = []
-        options, key = self.options, self.font_key
-        weight_mode = options.weight_mode if options.size_mode == "variable" else "fixed"
+        opt, key = self.options, self.font_key
         for glyph in placed:
-            advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
-            ascent, descent = _font(key, glyph.size).getmetrics()
-            box_w = advance
-            box_h = float(ascent + descent)
-            x = glyph.pen + dx
-            y = glyph.baseline + dy - ascent
+            asc, desc = _font(key, glyph.size).getmetrics()
+            box_w = _glyph_metrics(key, glyph.size, glyph.character)[0]
+            x, y = glyph.pen + dx, glyph.baseline + dy - asc
             ink = float(self.inks[glyph.slot])
-            stroke = 0 if weight_mode == "fixed" else int(round(ink * max(1, glyph.size // 8)))
             out.append(TextGlyph(
-                glyph.character, x, y, box_w, box_h, options.fg.lower(), options.bg.lower(),
-                glyph.size, stroke, MIN_OPACITY + (1.0 - MIN_OPACITY) * ink,
-            ))
+                glyph.character, x, y, box_w, float(asc + desc), opt.fg.lower(), opt.bg.lower(),
+                glyph.size, self._stroke(glyph.slot, glyph.size),
+                MIN_OPACITY + (1.0 - MIN_OPACITY) * ink))
         return out
 
 
@@ -366,9 +364,7 @@ def _mask(font_key: _FontKey, char: str, size: int, stroke: int) -> tuple[np.nda
         return _EMPTY_MASK, 0, 0
     canvas = PILImage.new("L", (right - left, bottom - top), 0)
     ImageDraw.Draw(canvas).text(
-        (-left, -top), char, font=font, fill=255, anchor="ls",
-        stroke_width=stroke, stroke_fill=255,
-    )
+        (-left, -top), char, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
     mask = np.asarray(canvas, np.float32) / 255.0
     mask.setflags(write=False)
     return mask, left, top
diff --git a/tests/test_text.py b/tests/test_text.py
index 52c3006..841d4d6 100644
--- a/tests/test_text.py
+++ b/tests/test_text.py
@@ -1,7 +1,6 @@
 """Tests for the text renderer (§3, §10) — card L9.
 
-Font metrics are pinned against Pillow's own, computed independently here.
-The renderer is palette-independent by contract (S2), so renders compare across palettes.
+Metrics are pinned against Pillow's own; renders compare across palettes (S2).
 """
 
 from __future__ import annotations
@@ -81,14 +80,10 @@ def _ink_bbox(glyph: TextGlyph) -> tuple[float, float, float, float]:
 
 
 def _assert_ink_inside(glyph: TextGlyph, width: int, height: int) -> None:
-    """Assert ink is inside; _fit bounds raw ink, so only the bounded, clipped stroke may spill."""
+    """Assert the real ink box (stroke included) lies wholly inside the canvas."""
     x0, y0, x1, y1 = _ink_bbox(glyph)
-    limit = max(1, glyph.size // 8)  # largest stroke §10 can give a glyph of this size
-    assert -limit <= x0 and x1 <= width + limit, "glyph ink overflows the horizontal edge"
-    assert -limit <= y0 and y1 <= height + limit, "glyph ink overflows the vertical edge"
-
-
-# --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---
+    assert 0.0 <= x0 and x1 <= width, "glyph ink overflows the horizontal edge"
+    assert 0.0 <= y0 and y1 <= height, "glyph ink overflows the vertical edge"
 
 
 def test_fixed_size_mode_gives_every_glyph_the_same_size():
@@ -101,9 +96,7 @@ def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
     glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
     assert len({glyph.size for glyph in glyphs}) >= 5
     default = _layout(_canvas(20, 6))
-    assert len(default) > 10 and {glyph.character for glyph in default} <= set(
-        text_module.DEFAULT_TEXT
-    )
+    assert len(default) > 10 and {g.character for g in default} <= set(text_module.DEFAULT_TEXT)
 
 
 def test_fixed_size_mode_modulates_opacity_instead_of_size():
@@ -111,9 +104,6 @@ def test_fixed_size_mode_modulates_opacity_instead_of_size():
     assert len({round(glyph.opacity, 6) for glyph in glyphs}) >= 5
 
 
-# --- accept 2: the rectangle is filled exactly, with no gap and no overflow ---
-
-
 @pytest.mark.parametrize("mode", ["fixed", "variable"])
 def test_the_output_rectangle_is_exactly_the_grid_geometry(mode):
     grid = _canvas(12, 5, 6, 18)
@@ -149,7 +139,6 @@ def test_every_glyph_ink_lies_inside_the_canvas(mode):
 
 @pytest.mark.parametrize("extra", [2, 8])
 def test_ink_bbox_detects_an_artificially_thick_stroke(extra):
-    """The helper must see a stroke overflow the old font-only bbox could not detect."""
     grid = _canvas(10, 4)
     width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
     glyph = _layout(grid, size_mode="variable", text="edge")[0]
@@ -158,7 +147,16 @@ def test_ink_bbox_detects_an_artificially_thick_stroke(extra):
     assert x0 < 0 or y0 < 0 or x1 > width or y1 > height, "stroke overflow went unnoticed"
 
 
-# --- accept 3: a 200-word paragraph wraps, unclipped ---
+def test_unbreakable_word_is_cut_and_reflows_on_a_narrower_canvas():
+    word = "@" * 400
+    options = {"text": word, "size_mode": "fixed", "size": 8}
+    wide, narrow = _canvas(40, 20), _canvas(20, 40)
+    for grid in (wide, narrow):
+        glyphs = _layout(grid, **options)
+        assert len(glyphs) == len(word), "cutting a word must not drop glyphs"
+        for glyph in glyphs:
+            _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+    assert len(_line_tops(_layout(narrow, **options))) > len(_line_tops(_layout(wide, **options)))
 
 
 @pytest.mark.parametrize("mode", ["fixed", "variable"])
@@ -178,7 +176,6 @@ def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell
 
 
 def test_layout_reports_real_unclamped_positions():
-    """layout() reports raw pens: recompute them from Pillow metrics, with no private calls."""
     text, kern = "unclamped", 1.0
     glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern, size_mode="fixed")
     font = _default_font(glyphs[0].size)
@@ -192,9 +189,6 @@ def test_layout_reports_real_unclamped_positions():
                                 - font.getlength(glyphs[index + 1].character))
 
 
-# --- accept 4: the same text and seed render identically ---
-
-
 def test_the_same_text_and_seed_render_and_lay_out_identically():
     grid, options = _canvas(14, 6), {"text": "seed me", "seed": 3}
     assert np.array_equal(_frame(grid, **options), _frame(grid, **options))
@@ -204,9 +198,6 @@ def test_the_same_text_and_seed_render_and_lay_out_identically():
     assert not np.array_equal(_frame(grid, **options), _frame(grid, text="seed me", seed=4))
 
 
-# --- accept 5: empty text raises ValueError naming the option ---
-
-
 @pytest.mark.parametrize("value", ["", "   ", "\n\t ", " \r\n "])
 def test_empty_text_raises_value_error_naming_the_option(value):
     with pytest.raises(ValueError) as excinfo:
@@ -257,6 +248,17 @@ def test_dark_cells_get_larger_heavier_and_darker_glyphs_than_light_cells():
     assert light.opacity == pytest.approx(MIN_OPACITY, abs=1e-6)
 
 
+def test_low_luma_first_glyph_at_left_edge_has_max_size_and_no_overflow():
+    grid = _canvas(8, 4, flat=0.0)
+    glyphs = _layout(grid, text="MWMWMW")
+    first = glyphs[0]
+    assert first.x == 0.0, "a first glyph that fits must not be shifted right"
+    assert first.size == max(g.size for g in glyphs) and first.stroke >= 1
+    assert first.opacity == pytest.approx(1.0)
+    for glyph in glyphs:
+        _assert_ink_inside(glyph, grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+
+
 def test_ink_never_collapses_on_a_neutral_palette():
     grid = _canvas(18, 6)
     glyphs = _layout(grid, NEUTRAL, text="neutral ink must survive the palette")
@@ -279,7 +281,6 @@ def test_size_and_colour_options_set_size_and_report_colours():
 
 
 def test_weight_mode_is_ignored_only_under_fixed_size_mode():
-    """§10: fixed size modulates opacity only, so weight_mode applies only to variable."""
     grid = _canvas(18, 6, flat=0.0)
     fixed = _layout(grid, size_mode="fixed", weight_mode="variable", text="ink weight")
     variable = _layout(grid, size_mode="variable", weight_mode="variable", text="ink weight")
@@ -353,9 +354,7 @@ def test_registration_metadata_and_layout_call_forms():
     assert renderer.cell_aspect() == 0.5 and renderer.subgrid() == (1, 1)
     assert renderer.consumes() == frozenset({"luma"})
     grid, style = _canvas(8, 4), _style(text="both forms")
-    assert renderer.layout(grid, style) == renderer.layout(  # type: ignore[arg-type]
-        grid, BW, style
-    )
+    assert renderer.layout(grid, style) == renderer.layout(grid, BW, style)  # type: ignore[arg-type]
 
 
 def test_style_options_round_trip_through_json():


CODER NOTES AND DEVIATIONS
- Voir GATE RESULTS (les NOTES du codeur y sont reprises, y compris les chiffres qu'il annonce).
- E1 déclarée : canevas physiquement plus petit qu'un glyphe à size 1 (trait §10 inclus = 4×3 px) —
  le code s'arrête à size 1, `layout()` rapporte les positions réelles non clampées, seul `_blit`
  clippe. Tous les cas testés (cellules 3×5 sur 60×200 px) passent à zéro débordement.
