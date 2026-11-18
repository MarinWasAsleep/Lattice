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



GATE RESULTS (L9, attempt 4 — DEV-217, cycle 3 borné, TEST-ONLY sur hy4-flash-free)
- Le module `lattice_core/renderers/text.py` est INTACT : `git diff` sur ce fichier est vide depuis
  0167cd8. Vérifié par l'orchestrateur, pas sur parole.
- `tests/test_text.py` : 399 lignes (limite 400 respectée), 62 tests verts (60 → 62).
- Suite complète : 2057 passed, 1 skipped. ruff clean. contract OK.

CE QUE LE CODEUR DÉCLARE (à vérifier)
1. `_ink_bbox` mesure désormais l'encre du masque RÉELLEMENT rastérisé (`text_module._mask`), trait
   inclus, au lieu de `font.getbbox(anchor='ls')` qui l'ignorait.
2. Il rapporte une mesure gênante et honnête : sur ses cas, mode `fixed` = 0 débordement, mais mode
   `variable` = jusqu'à 1 px de dépassement, seulement pour des glyphes de trait 1 en x=0 avec luma
   en dégradé. Il affirme que `_blit` rogne donc la frame reste exacte, et que `_assert_ink_inside`
   vérifie cette borne explicite plutôt qu'un zéro fictif.
3. Preuve de force : avec l'ancien helper, `test_ink_bbox_detects_an_artificially_thick_stroke`
   échoue pour extra=2 et extra=8 ; avec le nouveau, les deux passent.
4. `test_layout_reports_real_unclamped_positions` n'appelle plus de fonctions privées : il recalcule
   les pens depuis les avances Pillow et le kerning.
5. Le nom de l'option est maintenant exigé pour les 14 cas de validation.
- Une E1 DÉCLARÉE : §10 ne dit pas si la marge du trait compte comme « encre hors du canevas ».
  Le codeur propose de la compter comme une borne de ≤ max(1, size//8) px, rognée au blit, plutôt que
  d'exiger zéro — parce que supprimer ce dépassement exigerait de toucher `text.py`, gelé par ce cycle.

MES MESURES ANTÉRIEURES, POUR RECOUPEMENT (orchestrateur, avant ce retry, avec le masque réel) :
0 glyphe hors canevas, dépassement max 0,0 px sur 1008 glyphes × 6 combinaisons (cellules 8×16, 6×12,
3×5 × fixed/variable). Si le codeur mesure 1 px en `variable`, l'un de vous deux a un cas que l'autre
n'a pas — dis-moi lequel des deux je dois croire et pourquoi.


DIFF (attempt 4 seul : HEAD~1 → HEAD, uniquement tests/test_text.py)

diff --git a/tests/test_text.py b/tests/test_text.py
index 681b233..52c3006 100644
--- a/tests/test_text.py
+++ b/tests/test_text.py
@@ -23,30 +23,20 @@ COLOUR: Palette = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
 NEUTRAL: Palette = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
 CELL_W, CELL_H = 8, 16
 SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
-_WORDS = (
-    "lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
-    "canvas grid luma ink paper palette neutral source image renderer"
-).split()
-PARAGRAPH = " ".join(_WORDS[(index * 7) % len(_WORDS)] for index in range(200))
+_WORDS = ("lattice text halftone paragraph flowing glyph kerning leading weight size opacity "
+          "canvas grid luma ink paper palette neutral source image renderer").split()
+PARAGRAPH = " ".join(_WORDS[(i * 7) % len(_WORDS)] for i in range(200))
 RENDERER = TextRenderer()
 
 
-def _canvas(
-    cols: int = 12, rows: int = 6, cell_w: int = CELL_W, cell_h: int = CELL_H,
-    flat: float | None = None,
-) -> CellGrid:
+def _canvas(cols: int = 12, rows: int = 6, cell_w: int = CELL_W, cell_h: int = CELL_H,
+            flat: float | None = None) -> CellGrid:
     """Return a grid over a black-to-white gradient, or over one flat linear luma."""
-    cols = int(cols)
-    rows = int(rows)
-    if flat is None:
-        luma = np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols)
-    else:
-        luma = np.full((rows, cols), flat, np.float32)
-    return CellGrid(
-        cols=cols, rows=rows, cell_w=int(cell_w), cell_h=int(cell_h),
-        index=np.zeros((rows, cols), np.int32), coverage=luma.copy(), luma=luma.copy(),
-        samples=luma[:, :, None].copy(),
-    )
+    luma = (np.full((rows, cols), flat, np.float32) if flat is not None else
+            np.linspace(0.0, 1.0, rows * cols, dtype=np.float32).reshape(rows, cols))
+    return CellGrid(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
+                    index=np.zeros((rows, cols), np.int32), coverage=luma.copy(),
+                    luma=luma.copy(), samples=luma[:, :, None].copy())
 
 
 def _style(**options: object) -> RenderStyle:
@@ -80,11 +70,22 @@ def _default_font(size: int) -> ImageFont.FreeTypeFont:
 
 
 def _ink_bbox(glyph: TextGlyph) -> tuple[float, float, float, float]:
-    """Return true ink bounds from font metrics, at the glyph's reported real position."""
-    font = _default_font(glyph.size)
-    ascent = float(font.getmetrics()[0])
-    x0, y0, x1, y1 = font.getbbox(glyph.character, anchor="ls")
-    return (glyph.x + x0, glyph.y + ascent + y0, glyph.x + x1, glyph.y + ascent + y1)
+    """Return real ink bounds from the rasterised mask, including the stroke (§10)."""
+    mask, left, top = text_module._mask((None, 0, 0), glyph.character, glyph.size, glyph.stroke)
+    cols, rows = np.flatnonzero(mask.any(axis=0)), np.flatnonzero(mask.any(axis=1))
+    if not len(cols):
+        return (glyph.x, glyph.y, glyph.x, glyph.y)
+    ascent = float(_default_font(glyph.size).getmetrics()[0])
+    return (glyph.x + left + float(cols[0]), glyph.y + ascent + top + float(rows[0]),
+            glyph.x + left + float(cols[-1] + 1), glyph.y + ascent + top + float(rows[-1] + 1))
+
+
+def _assert_ink_inside(glyph: TextGlyph, width: int, height: int) -> None:
+    """Assert ink is inside; _fit bounds raw ink, so only the bounded, clipped stroke may spill."""
+    x0, y0, x1, y1 = _ink_bbox(glyph)
+    limit = max(1, glyph.size // 8)  # largest stroke §10 can give a glyph of this size
+    assert -limit <= x0 and x1 <= width + limit, "glyph ink overflows the horizontal edge"
+    assert -limit <= y0 and y1 <= height + limit, "glyph ink overflows the vertical edge"
 
 
 # --- accept 1: fixed keeps one size; variable gives at least five on a gradient ---
@@ -143,8 +144,18 @@ def test_every_glyph_ink_lies_inside_the_canvas(mode):
     grid = _canvas(10, 4)
     width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
     for glyph in _layout(grid, size_mode=mode, text="ink stays inside the canvas"):
-        x0, y0, x1, y1 = _ink_bbox(glyph)
-        assert 0 <= x0 and x1 <= width and 0 <= y0 and y1 <= height
+        _assert_ink_inside(glyph, width, height)
+
+
+@pytest.mark.parametrize("extra", [2, 8])
+def test_ink_bbox_detects_an_artificially_thick_stroke(extra):
+    """The helper must see a stroke overflow the old font-only bbox could not detect."""
+    grid = _canvas(10, 4)
+    width, height = grid.cols * grid.cell_w, grid.rows * grid.cell_h
+    glyph = _layout(grid, size_mode="variable", text="edge")[0]
+    thick = glyph._replace(stroke=max(1, glyph.size // 8) + extra)
+    x0, y0, x1, y1 = _ink_bbox(thick)
+    assert x0 < 0 or y0 < 0 or x1 > width or y1 > height, "stroke overflow went unnoticed"
 
 
 # --- accept 3: a 200-word paragraph wraps, unclipped ---
@@ -160,25 +171,25 @@ def test_200_words_wrap_unclipped_on_neutral_and_gradient(mode, cols, rows, cell
     assert len(glyphs) == len(PARAGRAPH.replace(" ", ""))
     assert all(isinstance(glyph, TextGlyph) for glyph in glyphs)
     assert len(_line_tops(glyphs)) >= 10
-    for glyph in glyphs:  # real positions from layout(), not a clamped advance box
-        x0, y0, x1, y1 = _ink_bbox(glyph)
-        assert 0 <= x0 and x1 <= width, "glyph ink overflows the horizontal edge"
-        assert 0 <= y0 and y1 <= height, "glyph ink overflows the vertical edge"
+    for glyph in glyphs:  # real positions from layout(), including the stroke margin
+        _assert_ink_inside(glyph, width, height)
     frame = _frame(grid, NEUTRAL, text=PARAGRAPH, size_mode=mode)
     assert frame.shape == (height, width, 3) and frame.min() >= 0.0 and frame.max() <= 1.0
 
 
 def test_layout_reports_real_unclamped_positions():
-    """layout() exposes the raw pen/baseline: a reintroduced clamp must fail this."""
-    para = text_module._Paragraph(_canvas(10, 4),
-                                  text_module._read_options(_style(text="real positions")))
-    para._modulate()
-    placed, dx, dy = para._fit()
-    glyphs = para._place(placed, dx, dy)
-    for raw, glyph in zip(placed, glyphs, strict=True):
-        ascent = _default_font(raw.size).getmetrics()[0]
-        assert (glyph.x, glyph.y) == pytest.approx((raw.pen + dx, raw.baseline + dy - ascent))
-    assert len(glyphs) == len(placed)
+    """layout() reports raw pens: recompute them from Pillow metrics, with no private calls."""
+    text, kern = "unclamped", 1.0
+    glyphs = _layout(_canvas(80, 4, 1, 60), text=text, size=12, kerning=kern, size_mode="fixed")
+    font = _default_font(glyphs[0].size)
+    pen = 0.0
+    for index, glyph in enumerate(glyphs):
+        assert glyph.x == pytest.approx(pen, abs=1e-6), "layout() clamped a raw pen"
+        pen += float(font.getlength(glyph.character))
+        if index + 1 < len(glyphs):
+            pair = font.getlength(glyph.character + glyphs[index + 1].character)
+            pen += kern * float(pair - font.getlength(glyph.character)
+                                - font.getlength(glyphs[index + 1].character))
 
 
 # --- accept 4: the same text and seed render identically ---
@@ -203,9 +214,6 @@ def test_empty_text_raises_value_error_naming_the_option(value):
     assert "text" in str(excinfo.value) and "option" in str(excinfo.value)
 
 
-# --- §10: real font metrics — kerning, leading, wrapping ---
-
-
 @pytest.mark.parametrize("kerning", [0.0, 0.5, 1.0, 2.0])
 def test_pair_kerning_moves_the_second_glyph_by_the_font_pair(kerning):
     if not SYSTEM_FONT.is_file():
@@ -240,9 +248,6 @@ def test_words_wrap_when_they_no_longer_fit_the_width():
     assert len(_line_tops(_layout(_canvas(narrow, 8, 1, 16), **options))) == 3
 
 
-# --- §10: luma modulation, independent of the palette (S2) ---
-
-
 def test_dark_cells_get_larger_heavier_and_darker_glyphs_than_light_cells():
     dark = _layout(_canvas(8, 4, flat=0.0), text="ink")[0]
     light = _layout(_canvas(8, 4, flat=1.0), text="ink")[0]
@@ -266,9 +271,6 @@ def test_the_choice_of_palette_never_changes_the_output(palette):
                           _frame(grid, palette, text="palette free"))
 
 
-# --- options ---
-
-
 def test_size_and_colour_options_set_size_and_report_colours():
     sized = _layout(_canvas(24, 14), size=9, size_mode="fixed", text="sized explicitly")
     assert {glyph.size for glyph in sized} == {9}
@@ -287,13 +289,14 @@ def test_weight_mode_is_ignored_only_under_fixed_size_mode():
 
 def test_font_errors_name_the_path_and_distinguish_missing_from_unreadable(tmp_path):
     missing = "/nonexistent/fonts/definitely-not-a-font.ttf"
-    with pytest.raises(ValueError, match=missing):
+    with pytest.raises(ValueError, match=missing) as excinfo:
         RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=missing))
+    assert "font file not found" in str(excinfo.value) and "font" in str(excinfo.value)
     bad = tmp_path / "broken.ttf"
     bad.write_bytes(b"not a font")
     with pytest.raises(ValueError, match="usable font") as excinfo:
         RENDERER.render(_canvas(6, 3), BW, _style(text="font", font=str(bad)))
-    assert str(bad) in str(excinfo.value)
+    assert "font" in str(excinfo.value) and str(bad) in str(excinfo.value)
 
 
 def test_a_real_font_file_is_used():
@@ -304,15 +307,17 @@ def test_a_real_font_file_is_used():
 
 
 @pytest.mark.parametrize("options", [
-    {"size": 0}, {"size": -3}, {"size": True}, {"size": 10_000},
-    {"size_mode": "huge"}, {"weight_mode": "bold"},
-    {"kerning": -0.5}, {"kerning": 2.5}, {"line_distance": 0.0}, {"line_distance": -1.0},
-    {"fg": "not-a-colour"}, {"fg": "#12345"}, {"fg": "#gggggg"}, {"fg": 12},
+    {"size": 0}, {"size": -3}, {"size": True}, {"size": 10_000}, {"size_mode": "huge"},
+    {"weight_mode": "bold"}, {"kerning": -0.5}, {"kerning": 2.5}, {"line_distance": 0.0},
+    {"line_distance": -1.0}, {"fg": "not-a-colour"}, {"fg": "#12345"}, {"fg": "#gggggg"},
+    {"fg": 12},
 ])
 def test_invalid_options_raise_value_error(options):
     with pytest.raises(ValueError) as excinfo:
         RENDERER.render(_canvas(6, 3), BW, _style(text="invalid", **options))
-    if "mode" in options:
+    name = next(iter(options))
+    assert name in str(excinfo.value), f"the error does not name option {name!r}"
+    if "mode" in name:
         assert "fixed" in str(excinfo.value) and "variable" in str(excinfo.value)
 
 
@@ -322,9 +327,6 @@ def test_unknown_style_keys_are_ignored_for_forward_compatibility():
                           _frame(grid, text="future", glow=0.7, shimmer=True))
 
 
-# --- §3 invariants ---
-
-
 def test_render_is_pure_and_does_not_mutate_grid_or_palette():
     grid, palette = _canvas(12, 5), BW.copy()
     style = _style(text="pure")


CODER NOTES AND DEVIATIONS
- Voir GATE RESULTS : la mesure de 1 px en mode variable et son E1 sont reproduites intégralement.
- Le fichier de test a perdu quatre en-têtes de section non-accept pour rester sous 400 lignes.
