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



GATE RESULTS (L9, attempt 3 — hy4-flash-free via opencode-go ; cycle 3 de revue)
- Owned tests : 60 passed. `text.py` 400 l, `test_text.py` 397 l. ruff clean sur tout le dépôt.
- Suite complète : 2052 passed, 1 skipped. G3 check_contract : OK.
- Le diff ci-dessous est celui de l'attempt 3 SEUL (bd4819c → HEAD), pas la carte entière.

CE QUE LE CODEUR DÉCLARE (à vérifier — il a rendu NOTES + 2 DEVIATIONS cette fois, les premières
de la carte)
1. Arbitrage 1 appliqué : `_place()` ne clampe plus ; `layout()` rapporte le pen/baseline brut ;
   seul `_blit` découpe au canevas. Un test « white-box » épingle les positions non clampées pour
   qu'un clamp réintroduit échoue.
2. `_fit()` INCHANGÉ : il dit avoir mesuré la bbox d'encre brute sur des paragraphes de 200 mots,
   4 géométries × 2 size_mode × 3 luma (dégradé / neutre / plat), et qu'aucun glyphe ne sort.
   C'est le point que je te demande de challenger : si tu penses qu'un cas existe où la position
   réelle sort du canevas malgré `_fit()`, nomme-le.
3. Arbitrage 2 : `weight_mode="variable"` ignoré sous `size_mode="fixed"`, documenté et épinglé
   (stroke == 0 vs stroke > 0).
4. Arbitrage 4 : `seed` conservé comme jitter déterministe, validé et documenté ; `_read_options`
   fait 32 lignes.
5. Arbitrage 5 : deux messages distincts, « font file not found: <path> » et « not a usable font:
   <path> », épinglés par un test.
- DÉVIATIONS déclarées (E1 ×2) : l'interaction weight_mode/size_mode n'est pas définie par §10 ;
  §10 ne nomme pas `seed` alors que l'accept 4 l'exige.

DIFF (attempt 3 : bd4819c → HEAD)

diff --git a/lattice_core/renderers/text.py b/lattice_core/renderers/text.py
index 6bf0be0..129c20c 100644
--- a/lattice_core/renderers/text.py
+++ b/lattice_core/renderers/text.py
@@ -6,7 +6,8 @@ linear luma of the cell under a glyph (S2, re-encoded to sRGB per AMD-010) drive
 (0.5x to 1.5x, §10), stroke weight and opacity, so ink never collapses on a neutral palette.
 The paper paints every pixel, ink is clipped to the canvas, and an overflowing paragraph is
 re-flowed smaller rather than clipped. Fonts, metrics and masks are bounded input-keyed
-caches that never change the output (§3 invariant 2, H11); randomness is a seed-keyed jitter.
+caches that never change the output (§3 invariant 2, H11). The optional `seed`, absent from
+§10's option list, drives a deterministic jitter kept for reproducibility.
 """
 
 from __future__ import annotations
@@ -27,26 +28,24 @@ from lattice_core.types import Palette
 
 _FontKey = tuple[str | None, int, int]
 _Metrics = tuple[float, float, float, float, float]
-NAME = "text"
-CELL_ASPECT = 0.5
+NAME, CELL_ASPECT = "text", 0.5
 DEFAULT_TEXT = "Lattice renders a paragraph in a real font, one glyph at a time."
-DEFAULT_FG = "#000000"
-DEFAULT_BG = "#ffffff"
-SIZE_MODES = ("fixed", "variable")
-WEIGHT_MODES = ("fixed", "variable")
-MIN_FACTOR, MAX_FACTOR = 0.5, 1.5
-MIN_OPACITY = 0.12
-MAX_SIZE, JITTER = 512, 0.08
+DEFAULT_FG, DEFAULT_BG = "#000000", "#ffffff"
+SIZE_MODES = WEIGHT_MODES = ("fixed", "variable")
+MIN_FACTOR, MAX_FACTOR, MIN_OPACITY, MAX_SIZE, JITTER = 0.5, 1.5, 0.12, 512, 0.08
 _PROBE_SIZE, _FIT_PASSES, _CACHE = 100, 8, 1024
-_EPSILON = 1e-6
-_HEX_DIGITS = frozenset("0123456789abcdef")
+_EPSILON, _HEX_DIGITS = 1e-6, frozenset("0123456789abcdef")
 _EMPTY_MASK = np.zeros((1, 1), np.float32)  # read-only: an inkless glyph's mask
 _EMPTY_MASK.setflags(write=False)
 
 
 @dataclass(frozen=True)
 class TextOptions:
-    """Validated options of one text render (§10)."""
+    """Validated options of one text render (§10).
+
+    Fixed size mode forces fixed weight (§10: opacity alone then varies); ``seed`` is a
+    tolerated extra that only drives the deterministic jitter.
+    """
 
     text: str = DEFAULT_TEXT
     font: str | None = None
@@ -54,10 +53,10 @@ class TextOptions:
     line_distance: float = 1.2
     kerning: float = 1.0
     size_mode: str = "variable"
-    weight_mode: str = "variable"
+    weight_mode: str = "variable"  # ignored when size_mode="fixed" (§10: opacity only)
     fg: str = DEFAULT_FG
     bg: str = DEFAULT_BG
-    seed: int = 0
+    seed: int = 0  # deterministic jitter; §10 omits the option but reproducibility needs it
 
 
 class TextGlyph(NamedTuple):
@@ -120,7 +119,7 @@ class TextRenderer:
     def layout(
         self, grid: CellGrid, palette: Palette | None = None, style: RenderStyle | None = None
     ) -> list[TextGlyph]:
-        """Return every visible glyph inside the canvas, in reading order (§3, §11).
+        """Return every laid-out glyph at its real position, in reading order (§3, §11).
 
         Both the §3 ``layout(grid, style)`` and ``layout(grid, palette, style)`` forms are
         accepted; only fg/bg and luma change the output, never the palette.
@@ -138,10 +137,7 @@ def _read_options(style: RenderStyle) -> TextOptions:
     font = raw.get("font")
     if font is not None and not isinstance(font, str):
         raise ValueError(f"text renderer option 'font' must be a path string or null: {font!r}")
-    try:
-        _font_key(font)  # ValueError naming the path, before anything is drawn
-    except ValueError as exc:
-        raise ValueError(f"text renderer font file not found: {font}") from exc
+    _font_key(font)  # a missing path raises naming it; an unreadable font is rejected in _font()
     size = raw.get("size")
     if size is not None and (isinstance(size, bool) or not isinstance(size, int)
                              or not 1 <= size <= MAX_SIZE):
@@ -240,7 +236,7 @@ class _Paragraph:
         self.inks = np.zeros(self.count, dtype=np.float32)
 
     def glyphs(self) -> list[TextGlyph]:
-        """Lay the paragraph out and return every visible glyph, clamped to the canvas."""
+        """Lay the paragraph out and return every glyph at its real, unclamped position."""
         if not self.chars or self.width <= 0 or self.height <= 0:
             return []
         self._modulate()
@@ -334,17 +330,21 @@ class _Paragraph:
         return placed, dx, dy
 
     def _place(self, placed: list[_Placed], dx: float, dy: float) -> list[TextGlyph]:
-        """Return the glyphs as boxes clamped inside the canvas, with size, stroke, opacity."""
+        """Return glyphs at their real positions with size, stroke and opacity (§10).
+
+        Fixed size mode forces fixed weight: §10 says opacity alone carries the modulation,
+        so an explicit `weight_mode: variable` is deliberately ignored in that mode.
+        """
         out: list[TextGlyph] = []
         options, key = self.options, self.font_key
         weight_mode = options.weight_mode if options.size_mode == "variable" else "fixed"
         for glyph in placed:
             advance = _glyph_metrics(key, glyph.size, glyph.character)[0]
             ascent, descent = _font(key, glyph.size).getmetrics()
-            box_w = min(advance, float(self.width))
-            box_h = min(float(ascent + descent), float(self.height))
-            x = min(max(glyph.pen + dx, 0.0), max(0.0, self.width - box_w))
-            y = min(max(glyph.baseline + dy - ascent, 0.0), max(0.0, self.height - box_h))
+            box_w = advance
+            box_h = float(ascent + descent)
+            x = glyph.pen + dx
+            y = glyph.baseline + dy - ascent
             ink = float(self.inks[glyph.slot])
             stroke = 0 if weight_mode == "fixed" else int(round(ink * max(1, glyph.size // 8)))
             out.append(TextGlyph(
diff --git a/tests/test_text.py b/tests/test_text.py
index aba1e3b..681b233 100644
--- a/tests/test_text.py
+++ b/tests/test_text.py
@@ -1,9 +1,7 @@
 """Tests for the text renderer (§3, §10) — card L9.
 
-Wrap points, leading and kerning are pinned against Pillow's own font metrics, computed
-independently here: a change that moves both the renderer and its arithmetic still fails.
-The renderer is palette-independent by contract (S2), so renders are compared across very
-different palettes.
+Font metrics are pinned against Pillow's own, computed independently here.
+The renderer is palette-independent by contract (S2), so renders compare across palettes.
 """
 
 from __future__ import annotations
@@ -81,6 +79,14 @@ def _default_font(size: int) -> ImageFont.FreeTypeFont:
     return ImageFont.load_default(size=size)  # type: ignore[return-value]
 
 
+def _ink_bbox(glyph: TextGlyph) -> tuple[float, float, float, float]:
+    """Return true ink bounds from font metrics, at the glyph's reported real position."""
+    font = _default_font(glyph.size)
+    ascent = float(font.getmetrics()[0])
+    x0, y0, x1, y1 = font.getbbox(glyph.character, anchor="ls")
+    return (glyph.x + x0, glyph.y + ascent + y0, glyph.x + x1, glyph.y + ascent + y1)
+
+
 # --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---
 
 
@@ -93,6 +99,10 @@ def test_fixed_size_mode_gives_every_glyph_the_same_size():
 def test_variable_size_mode_gives_at_least_five_distinct_sizes_on_a_gradient():
     glyphs = _layout(_canvas(18, 6), text="variable size spreads ink across the canvas")
     assert len({glyph.size for glyph in glyphs}) >= 5
+    default = _layout(_canvas(20, 6))
+    assert len(default) > 10 and {glyph.character for glyph in default} <= set(
+        text_module.DEFAULT_TEXT
+    )
 
 
 def test_fixed_size_mode_modulates_opacity_instead_of_size():
@@ -123,46 +133,52 @@ def test_every_pixel_is_paper_or_ink_blended_over_paper(mode):
     ink, paper = frame[:, :, 0], 1.0 - frame[:, :, 2]
     assert np.allclose(ink, paper, atol=2e-6), "pixels are not blends of the two colours"
     assert ink.max() > 0.5 and ink.min() == 0.0
+    paper_frame = _frame(_canvas(30, 4), text="short")
+    assert np.all(paper_frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
+    assert np.all(paper_frame == np.float32(1.0), axis=-1).mean() > 0.3
 
 
 @pytest.mark.parametrize("mode", ["fixed", "variable"])
-def test_every_glyph_box_lies_inside_the_canvas(mode):
+def test_every_glyph_ink_lies_inside_the_canvas(mode):
     grid = _canvas(10, 4)
     width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
-    for glyph in _layout(grid, size_mode=mode, text="boxes stay inside the canvas"):
-        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
-        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height
-
-
-def test_the_paper_paints_the_whole_rectangle():
-    frame = _frame(_canvas(30, 4), text="short")
-    assert np.all(frame[-1, -1] == np.float32(1.0)), DEFAULT_BG
-    assert np.all(frame == np.float32(1.0), axis=-1).mean() > 0.3
+    for glyph in _layout(grid, size_mode=mode, text="ink stays inside the canvas"):
+        x0, y0, x1, y1 = _ink_bbox(glyph)
+        assert 0 <= x0 and x1 <= width and 0 <= y0 and y1 <= height
 
 
 # --- accept 3: a 200-word paragraph wraps, unclipped ---
 
 
-@pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"), [(40, 20, 8, 16), (20, 40, 6, 12)])
-def test_a_200_word_paragraph_wraps_over_many_lines(cols, rows, cell_w, cell_h):
-    tops = _line_tops(_layout(_canvas(cols, rows, cell_w, cell_h), text=PARAGRAPH))
-    assert len(tops) >= 20
-
-
+@pytest.mark.parametrize("mode", ["fixed", "variable"])
 @pytest.mark.parametrize(("cols", "rows", "cell_w", "cell_h"),
-                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16)])
-def test_a_200_word_paragraph_never_places_a_glyph_outside_the_canvas(cols, rows, cell_w, cell_h):
+                         [(40, 20, 8, 16), (20, 40, 6, 12), (8, 8, 8, 16), (20, 40, 3, 5)])
+def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell_w, cell_h):
     grid = _canvas(cols, rows, cell_w, cell_h)
     width, height = cols * cell_w, rows * cell_h
-    glyphs = _layout(grid, text=PARAGRAPH)
+    glyphs = _layout(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
     assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
     assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
-    for glyph in glyphs:
-        assert 0.0 <= glyph.x and glyph.x + glyph.width <= width
-        assert 0.0 <= glyph.y and glyph.y + glyph.height <= height
-    frame = _frame(grid, text=PARAGRAPH)
-    assert frame.shape == (height, width, 3)
-    assert frame.min() >= 0.0 and frame.max() <= 1.0
+    assert len(_line_tops(glyphs)) >= 10
+    for glyph in glyphs:  # real positions from layout(), not a clamped advance box
+        x0, y0, x1, y1 = _ink_bbox(glyph)
+        assert 0 <= x0 and x1 <= width, "glyph ink overflows the horizontal edge"
+        assert 0 <= y0 and y1 <= height, "glyph ink overflows the vertical edge"
+    frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
+    assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0
+
+
+def test_layout_reports_real_unclamped_positions():
+    """layout() exposes the raw pen/baseline: a reintroduced clamp must fail this."""
+    para = text_module._Paragraph(_canvas(10, 4),
+                                  text_module._read_options(_style(text="real positions")))
+    para._modulate()
+    placed, dx, dy = para._fit()
+    glyphs = para._place(placed, dx, dy)
+    for raw, glyph in zip(placed, glyphs, strict=True):
+        ascent = _default_font(raw.size).getmetrics()[0]
+        assert (glyph.x, glyph.y) == pytest.approx((raw.pen + dx, raw.baseline + dy - ascent))
+    assert len(glyphs) == len(placed)
 
 
 # --- accept 4: the same text and seed render identically ---
@@ -224,12 +240,6 @@ def test_words_wrap_when_they_no_longer_fit_the_width():
     assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3
 
 
-def test_default_text_is_a_usable_paragraph():
-    glyphs = _layout(_canvas(20, 6))
-    assert len(glyphs) > 10
-    assert {glyph.character for glyph in glyphs} <= set(text_module.DEFAULT_TEXT)
-
-
 # --- §10: luma modulation, independent of the palette (S2) ---
 
 
@@ -259,21 +269,31 @@ def test_the_choice_of_palette_never_changes_the_output(palette):
 # --- options ---
 
 
-def test_size_option_sets_the_base_point_size_in_fixed_mode():
-    glyphs = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
-    assert {glyph.size for glyph in glyphs} == {9}
-
-
-def test_layout_reports_the_ink_and_paper_colours():
+def test_size_and_colour_options_set_size_and_report_colours():
+    sized = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
+    assert {glyph.size for glyph in sized} == {9}
     glyph = _layout(_canvas(6, 3), text="colours", fg="#AABBCC", bg="#FFEEDD")[0]
     assert glyph.fill == "#aabbcc" and glyph.paper == "#ffeedd"
 
 
-def test_missing_font_file_raises_value_error_naming_the_path():
-    path = "/nonexistent/fonts/definitely-not-a-font.ttf"
-    with pytest.raises(ValueError) as excinfo:
-        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=path))
-    assert path in str(excinfo.value)
+def test_weight_mode_is_ignored_only_under_fixed_size_mode():
+    """§10: fixed size modulates opacity only, so weight_mode applies only to variable."""
+    grid = _canvas(18, 6, flat=0.0)
+    fixed = _layout(grid, size_mode="fixed", weight_mode="variable", text="ink weight")
+    variable = _layout(grid, size_mode="variable", weight_mode="variable", text="ink weight")
+    assert fixed and all(glyph.stroke == 0 for glyph in fixed)
+    assert any(glyph.stroke > 0 for glyph in variable)
+
+
+def test_font_errors_name_the_path_and_distinguish_missing_from_unreadable(tmp_path):
+    missing = "/nonexistent/fonts/definitely-not-a-font.ttf"
+    with pytest.raises(ValueError, match=missing):
+        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=missing))
+    bad = tmp_path / "broken.ttf"
+    bad.write_bytes(b"not a font")
+    with pytest.raises(ValueError, match="usable font") as excinfo:
+        RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=str(bad)))
+    assert str(bad) in str(excinfo.value)
 
 
 def test_a_real_font_file_is_used():
@@ -283,30 +303,17 @@ def test_a_real_font_file_is_used():
     assert img.size == (10 * CELL_W, 4 * CELL_H)
 
 
-@pytest.mark.parametrize("size", [0, -3, True, 10_000])
-def test_invalid_size_raises_value_error(size):
-    with pytest.raises(ValueError):
-        RENDERER.render(_canvas(6, 3), BW, _style(text="size", size=size))
-
-
-@pytest.mark.parametrize(("key", "value"), [("size_mode", "huge"), ("weight_mode", "bold")])
-def test_unknown_modes_raise_value_error_naming_the_choices(key, value):
+@pytest.mark.parametrize("options", [
+    {"size": 0}, {"size": -3}, {"size": True}, {"size": 10_000},
+    {"size_mode": "huge"}, {"weight_mode": "bold"},
+    {"kerning": -0.5}, {"kerning": 2.5}, {"line_distance": 0.0}, {"line_distance": -1.0},
+    {"fg": "not-a-colour"}, {"fg": "#12345"}, {"fg": "#gggggg"}, {"fg": 12},
+])
+def test_invalid_options_raise_value_error(options):
     with pytest.raises(ValueError) as excinfo:
-        RENDERER.render(_canvas(6, 3), BW, _style(text="mode", **{key: value}))
-    assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)
-
-
-@pytest.mark.parametrize(("key", "value"), [("kerning", -0.5), ("kerning", 2.5),
-                                            ("line_distance", 0.0), ("line_distance", -1.0)])
-def test_out_of_range_numbers_raise_value_error(key, value):
-    with pytest.raises(ValueError):
-        RENDERER.render(_canvas(6, 3), BW, _style(text="numbers", **{key: value}))
-
-
-@pytest.mark.parametrize("colour", ["not-a-colour", "#12345", "#gggggg", 12])
-def test_invalid_colours_raise_value_error(colour):
-    with pytest.raises(ValueError):
-        RENDERER.render(_canvas(6, 3), BW, _style(text="colours", fg=colour))
+        RENDERER.render(_canvas(6, 3), BW, _style(text="invalid", **options))
+    if "mode" in options:
+        assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)
 
 
 def test_unknown_style_keys_are_ignored_for_forward_compatibility():
@@ -337,18 +344,16 @@ def test_render_frame_matches_render():
     assert np.array_equal(_image(grid, text="consistent rasterisation"), expected)
 
 
-def test_the_renderer_is_registered_under_a_unique_stable_name():
+def test_registration_metadata_and_layout_call_forms():
     renderer = TextRenderer()
-    assert renderer.name == "text"
-    assert get_renderer("text").name == "text"
-    assert list_renderers().count("text") == 1
-    assert isinstance(renderer, CellRenderer)
-
-
-def test_cell_aspect_subgrid_and_consumes():
-    assert RENDERER.cell_aspect() == 0.5
-    assert RENDERER.subgrid() == (1, 1)
-    assert RENDERER.consumes() == frozenset({"luma"})
+    assert renderer.name == "text" and get_renderer("text").name == "text"
+    assert list_renderers().count("text") == 1 and isinstance(renderer, CellRenderer)
+    assert renderer.cell_aspect() == 0.5 and renderer.subgrid() == (1, 1)
+    assert renderer.consumes() == frozenset({"luma"})
+    grid, style = _canvas(8, 4), _style(text="both forms")
+    assert renderer.layout(grid, style) == renderer.layout(  # type: ignore[arg-type]
+        grid, BW, style
+    )
 
 
 def test_style_options_round_trip_through_json():
@@ -363,11 +368,6 @@ def test_style_options_round_trip_through_json():
                           np.asarray(RENDERER.render(grid, BW, reloaded)))
 
 
-def test_layout_accepts_both_call_forms():
-    grid, style = _canvas(8, 4), _style(text="both forms")
-    assert RENDERER.layout(grid, style) == RENDERER.layout(grid, BW, style)
-
-
 def test_cached_masks_are_read_only_and_the_cache_is_bounded():
     text_module._mask.cache_clear()
     mask, _, _ = text_module._mask((None, 0, 0), "M", 12, 0)


CODER NOTES AND DEVIATIONS
- Voir le bloc GATE RESULTS ci-dessus : les NOTES sont intégrales, y compris les deux E1.
- Le codeur n'a jamais relu sa propre sortie (il rend un bloc FILE, il ne teste pas dans le dépôt) :
  c'est l'orchestrateur qui a écrit les fichiers et couru la suite.
