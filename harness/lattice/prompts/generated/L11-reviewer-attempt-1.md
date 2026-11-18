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



## §8 CLI

Every application exposes the same four verbs:

```
<app> render  --preset P --in IMG --out IMG
<app> batch   --preset P --in DIR --out DIR [--recursive]
<app> presets list|show|validate
<app> bridge  status|pull|push
```

- `render` and the GUI must produce **byte-identical** output for the same preset and image (G9).
- Exit codes: 0 success, 1 usage error, 2 render error, 3 bridge error.
- `--json` on any verb prints a machine-readable result on stdout and nothing else.
- No verb may require a display. `import lattice_core.ui` must not happen on the CLI path.



## §11 Vector export

Every renderer can emit SVG.

- `pixel` → one `<rect>` per cell, merged into runs where adjacent cells share a colour.
- `glyph_ramp`, `glyph_shape`, `bitmask`, `text` → export driven by the renderer's `layout()`
  when it is available (H11): one `<text>` element per glyph, with `font-family`,
  `font-size` and `fill` set. The output is **editable typography**, not traced paths.
- Budget: 2048×2048 source, 16 colours, output under 8 MB. Beyond that, merge cells into rectangles
  and record a warning.
- SVG output must open in Inkscape, Illustrator and a browser without repair.

**Text export (P3, decided 2026-11-16).** `glyph_ramp`, `glyph_shape` and `bitmask` also emit
text — from `layout()` when available (H11): `.txt` (UTF-8, space-separated cells, `\n` line
breaks), `.ansi` (24-bit colour, SGR escapes; terminal-safe ordering), `.html` (a coloured `<pre>`
block in a standalone page). Shared CLI verb: `render --format png|svg|txt|ansi|html`. The ANSI
exporter must not leak escape codes into the text path; HTML output escapes text content.



TASK CARD

### L11 · SVG export · text export
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/svg.py`, `lattice_core/textout.py`, `tests/test_svg.py`, `tests/test_textout.py`
- context: §11 (incl. text export — P3, decided 2026-11-16)
- spec: implement §11, **depuis `layout()` quand le renderer l'implémente (H11/Q2)**.
  `pixel` → `<rect>` per cell, merged into runs. `glyph_ramp`, `glyph_shape`,
  `bitmask` → one `<text>` per glyph avec `font-family`, `font-size`, `fill` — via `layout()`.
  `text` → one `<text>` per glyph preserving layout. Budget: 2048×2048, 16 colours, under 8 MB,
  else merge and warn.
  **Text export**: `render --format txt|ansi|html` for `glyph_ramp`, `glyph_shape`, `bitmask` —
  from `layout()` (H11) : `.txt` UTF-8, `.ansi` 24-bit SGR, `.html` `<pre>`; HTML escapes text,
  ANSI never leaks into the text path.
- accept:
  - the output parses as XML and has the right root namespace.
  - a 64×64 pixel render produces fewer `<rect>` elements than cells (runs are merged).
  - a glyph render produces exactly `cols * rows` `<text>` elements.
  - the 8 MB budget triggers a merge and a warning on a large render.
  - the file opens in a browser without repair (checked by parsing, not by launching a browser).
  - `txt` output has `cols * rows` tokens and `rows` lines; `ansi` contains SGR 24-bit sequences
    only; `html` renders the same grid and escapes `<`/`&` in glyph text.



GATE RESULTS (L11, attempt 1 — codeur mistral deepseek-v4-1-flash-1017, il a rendu un rapport complet)
- Owned tests : 51 passed (30 test_svg + 21 test_textout). svg.py 395 l, textout.py 149 l.
- Suite complète : 2055 passed, 1 skipped. G1 ruff : all checks passed. G3 check_contract : OK.
- Indépendance vérifiée par l'orchestrateur APRÈS import : `PySide6` absent de sys.modules,
  aucun module `lattice_dither*` chargé — les deux modules sont utilisables sans l'extra [ui].

MESURES INDÉPENDANTES DE L'ORCHESTRATEUR (faites hors des tests du codeur, à recouper avec les tiennes)
- pixel 64×64 aléatoire 4 couleurs : 2756 `<rect>` pour 4096 cellules → runs fusionnés, aucun warning.
  (Le codeur annonce 2 rects sur un cas plus structuré ; les deux mesures sont compatibles, un bruit
  aléatoire se fusionne peu.)
- glyph_ramp 32×8 : exactement 256 `<text>` pour 256 cellules.
- txt : 8 lignes, 512 caractères ; ANSI : SGR présents ; HTML : `<pre>`, aucun ESC dans txt ni html.

LES TROIS DÉVIATIONS E1 DÉCLARÉES PAR LE CODEUR — À ARBITRER PAR TOI
1. Une cellule blanche est écrite `·` (U+00B7) dans txt/ansi/html. Argument : un espace littéral
   disparaîtrait au split et décalerait la ligne. Je trouve l'argument solide, mais c'est une entorse
   visible à « espace-séparé » : dis si tu l'acceptes.
2. Quand le budget 8 MB est dépassé, un export de glycophes dégrade en rectangles couleur d'encre à
   l'opacité de `coverage` (papier puis encre), puis en blocs 2×2, 4×4… couleur du coin supérieur
   gauche, les deux étapes étant rapportées dans les warnings.
3. `text.layout()` place un paragraphe (52 placements pour 4608 cellules) : son SVG émet un `<text>`
   par placement et remplit le reste avec le `bg` du style ; son export txt/ansi/html est REFUSÉ
   avec un ValueError nommant renderer et format, faute de grille par cellule.

DIFF (les quatre fichiers de la carte, créés de zéro)

diff --git a/lattice_core/svg.py b/lattice_core/svg.py
new file mode 100644
index 0000000..f698c50
--- /dev/null
+++ b/lattice_core/svg.py
@@ -0,0 +1,395 @@
+"""SVG export of a CellGrid, from ``layout()`` when the renderer has one (§11, H11).
+
+``pixel`` exports merged ``<rect>`` runs of palette colour; a renderer with ``layout()``
+exports editable typography, the paper as rects plus one ``<text>`` per placed glyph. The
+document is capped in UTF-8 bytes by ``max_bytes``: a glyph export over the cap degrades to
+rectangles of cell ink at its coverage, and a body that still does not fit is coalesced into
+square blocks, each step recorded as a warning naming the cap. Strings only, no file.
+"""
+
+from __future__ import annotations
+
+import inspect
+from collections.abc import Callable
+from dataclasses import dataclass
+from pathlib import Path
+from typing import Any
+
+import numpy as np
+
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle
+from lattice_core.types import Palette
+
+SVG_NS = "http://www.w3.org/2000/svg"
+DEFAULT_MAX_BYTES = 8_000_000
+TRANSPARENT = "transparent"
+NONE = 'fill="none"'
+MONOSPACE = "monospace"
+_HEX_DIGITS = frozenset("0123456789abcdef")
+_PLACEMENT_FIELDS = 6
+_BASELINE = 0.8  # baseline as a fraction of the font size, measured from a glyph box's top
+_MIN_RECT_BYTES = 40  # lower bound on one <rect>; below it a run merge is worth attempting
+_Layer = tuple[np.ndarray, list[str]]
+
+
+@dataclass(frozen=True)
+class Glyph:
+    """One placed glyph, normalised from any renderer's layout entry (§3, §11)."""
+
+    character: str
+    x: float
+    y: float
+    width: float
+    height: float
+    fill: str
+    paper: str | None = None
+    size: float | None = None
+    opacity: float | None = None
+
+
+def render_svg(
+    grid: CellGrid,
+    palette: Palette,
+    renderer: CellRenderer,
+    style: RenderStyle | None = None,
+    *,
+    max_bytes: int = DEFAULT_MAX_BYTES,
+) -> tuple[str, list[str]]:
+    """Return the SVG document of grid and the warnings raised while keeping its budget.
+
+    A renderer with ``layout()`` exports one ``<text>`` per placed glyph over its paper; any
+    other renderer exports merged ``<rect>`` runs of palette colour (§11). A document that
+    would exceed max_bytes is degraded to rectangles, then to blocks, with a warning each.
+    """
+    if max_bytes <= 0:
+        raise ValueError(f"max_bytes must be a positive number of UTF-8 bytes, got {max_bytes!r}")
+    style = RenderStyle(options={}) if style is None else style
+    header = _header(grid.cols * grid.cell_w, grid.rows * grid.cell_h)
+    allowance = int(max_bytes) - _size([header, "</svg>"])
+    glyphs = _placements(grid, palette, renderer, style)
+    warnings: list[str] = []
+    parts: list[str] | None = None
+    if glyphs is not None:
+        parts = _text_body(glyphs, grid, style, allowance)
+        if parts is None:
+            warnings.append(
+                f"svg export exceeded the {int(max_bytes)}-byte budget: "
+                f"{len(glyphs)} glyphs merged into cell rectangles"
+            )
+    if parts is None:
+        parts, warning = _rect_body(grid, palette, glyphs, style, allowance)
+        if warning is not None:
+            warnings.append(f"svg export over the {int(max_bytes)}-byte budget: {warning}")
+    return "\n".join([header, *parts, "</svg>"]) + "\n", warnings
+
+
+def _size(parts: list[str]) -> int:
+    """Return the UTF-8 size of a body in bytes."""
+    return sum(len(part.encode("utf-8")) for part in parts)
+
+
+def _header(width: int, height: int) -> str:
+    """Return the root element, carrying the exact output pixel geometry."""
+    return (
+        f'<svg xmlns="{SVG_NS}" version="1.1" width="{width}" height="{height}" '
+        f'viewBox="0 0 {width} {height}" xml:space="preserve">'
+    )
+
+
+def _text_body(
+    glyphs: list[Glyph], grid: CellGrid, style: RenderStyle, allowance: int
+) -> list[str] | None:
+    """Return the paper rects then one <text> per glyph, or None once the body is too large.
+
+    Sizes are charged as the fragments are built, so a document that cannot fit never
+    materialises: memory stays bounded by the budget, not by the glyph count (§11).
+    """
+    paper = _rects(*_encode(_paper_codes(glyphs, grid, style)), grid.cell_w, grid.cell_h)
+    used = _size(paper)
+    if used > allowance:
+        return None
+    family = _family(style)
+    parts = list(paper)
+    for glyph in glyphs:
+        element = _text_element(glyph, family)
+        used += len(element.encode("utf-8"))
+        if used > allowance:
+            return None
+        parts.append(element)
+    return parts
+
+
+def _rect_body(grid: CellGrid, palette: Palette, glyphs: list[Glyph] | None,
+               style: RenderStyle, allowance: int) -> tuple[list[str], str | None]:
+    """Return the rectangle body and the warning of the degradation applied to fit it.
+
+    Runs of equal cells give the finest body; one that does not fit is coalesced into 2x2,
+    4x4, ... blocks painted with their top-left cell (E1). The exact count picks the first
+    block size, so a huge source is never expanded into millions of fragments.
+    """
+    layers = _layers(grid, palette, glyphs, style)
+
+    def at(step: int) -> list[str]:
+        """Return the rect elements of every layer sampled every step cells."""
+        return [rect for ids, paints in layers
+                for rect in _rects(ids[::step, ::step], paints,
+                                   grid.cell_w * step, grid.cell_h * step)]
+
+    limit = max(grid.rows, grid.cols)
+    block = 1
+    while block < limit and sum(_box_count(ids[::block, ::block]) for ids, _ in layers
+                                ) * _MIN_RECT_BYTES > allowance:
+        block *= 2
+    parts = at(block)
+    while _size(parts) > allowance and block < limit:
+        block *= 2
+        parts = at(block)
+    if _size(parts) > allowance:
+        return parts, f"one {limit}-cell block still does not fit"
+    return parts, None if block == 1 else f"cells coalesced into {block}x{block} blocks"
+
+
+def _box_count(ids: np.ndarray) -> int:
+    """Return the exact number of merged rectangles ``_rects`` emits for ids.
+
+    One per horizontal run, minus the runs continuing the run above with the same label,
+    start and end; each row is numpy work, so 2048x2048 costs seconds (§11).
+    """
+    rows, cols = ids.shape
+    if rows == 0 or cols == 0:
+        return 0
+    span = np.int64(cols + 1)
+    boxes, previous = 0, np.empty(0, dtype=np.int64)
+    for row in range(rows):
+        line = ids[row]
+        starts = np.ones(cols, dtype=bool)
+        if cols > 1:
+            starts[1:] = line[1:] != line[:-1]
+        at = np.nonzero(starts)[0].astype(np.int64)
+        ends = np.empty(at.size, dtype=np.int64)
+        ends[:-1], ends[-1] = at[1:], cols
+        keys = line[at] * span * span + at * span + ends
+        boxes += int(at.size) - (np.intersect1d(keys, previous).size if previous.size else 0)
+        previous = keys
+    return boxes
+
+
+def _layers(
+    grid: CellGrid, palette: Palette, glyphs: list[Glyph] | None, style: RenderStyle
+) -> list[_Layer]:
+    """Return the paint layers of the rectangle body, painted in order: paper, then ink."""
+    if glyphs is None:
+        return [_encode(_palette_codes(grid, palette))]
+    paper = _paper_codes(glyphs, grid, style)
+    ink = _layout_codes(glyphs, grid, "fill")
+    coverage = np.asarray(grid.coverage, dtype=np.float32).reshape(grid.rows, grid.cols)
+    alpha = np.where(ink == TRANSPARENT, np.float32(0.0), coverage)
+    return [_encode(paper), _encode(ink, alpha)]
+
+
+def _family(style: RenderStyle) -> str:
+    """Return the SVG font-family of style: the font file's stem, or monospace."""
+    font = style.options.get("font")
+    if isinstance(font, str) and font.strip():
+        stem = Path(font).stem.strip().replace("_", " ")
+        if stem:
+            return _escape(stem)
+    return MONOSPACE
+
+
+def _escape(text: str) -> str:
+    """Return text with the XML metacharacters escaped, quotes included."""
+    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
+    return out.replace('"', "&quot;").replace("'", "&apos;")
+
+
+def _placements(
+    grid: CellGrid, palette: Palette, renderer: CellRenderer, style: RenderStyle
+) -> list[Glyph] | None:
+    """Return the placed glyphs of renderer's layout(), or None when it has none (§11)."""
+    layout = getattr(renderer, "layout", None)
+    if not callable(layout):
+        return None
+    background = _style_colour(style, "bg") or TRANSPARENT
+    return [_glyph(item, background) for item in _call_layout(layout, grid, palette, style)]
+
+
+def _call_layout(
+    layout: Callable[..., Any], grid: CellGrid, palette: Palette, style: RenderStyle
+) -> list[Any]:
+    """Call layout() in the three-argument form, or §3's two-argument form if it takes it.
+
+    ``glyph_ramp`` and ``glyph_shape`` accept ``layout(grid, style)``; ``bitmask`` and
+    ``text`` need ``layout(grid, palette, style)``. The signature decides, never a retry.
+    """
+    try:
+        parameters = list(inspect.signature(layout).parameters.values())
+    except (TypeError, ValueError):
+        return list(layout(grid, palette, style))
+    positional = [
+        value for value in parameters
+        if value.kind in (value.POSITIONAL_ONLY, value.POSITIONAL_OR_KEYWORD)
+    ]
+    if len(positional) >= 3 or any(value.kind is value.VAR_POSITIONAL for value in parameters):
+        return list(layout(grid, palette, style))
+    return list(layout(grid, style))
+
+
+def _style_colour(style: RenderStyle, key: str) -> str | None:
+    """Return one style colour option as normalised text when it is a colour, else None."""
+    value = style.options.get(key)
+    if isinstance(value, str) and _digits(value) is not None:
+        return value.strip().lower()
+    return None
+
+
+def _glyph(item: Any, background: str) -> Glyph:
+    """Normalise one layout entry (GlyphPlacement, TextGlyph or 6-tuple), paper defaulting to bg."""
+    fields = tuple(item)
+    if len(fields) < _PLACEMENT_FIELDS:
+        raise ValueError(
+            f"layout() must place at least {_PLACEMENT_FIELDS} fields per glyph, got {fields!r}"
+        )
+    character, x, y, width, height, fill = fields[:_PLACEMENT_FIELDS]
+    paper = fields[6] if len(fields) > 6 and isinstance(fields[6], str) else background
+    size = fields[7] if len(fields) > 7 and isinstance(fields[7], (int, float)) else None
+    opacity = getattr(item, "opacity", None)
+    return Glyph(
+        character=str(character), x=float(x), y=float(y), width=float(width),
+        height=float(height), fill=str(fill).strip().lower(),
+        paper=str(paper).strip().lower(),
+        size=float(size) if size is not None else None,
+        opacity=float(opacity) if isinstance(opacity, (int, float)) else None,
+    )
+
+
+def _text_element(glyph: Glyph, family: str) -> str:
+    """Return one <text> element: its position, font size, family and ink colour (§11)."""
+    size = glyph.size if glyph.size and glyph.size > 0.0 else glyph.height
+    baseline = glyph.y + _BASELINE * size
+    return (
+        f'<text x="{_number(glyph.x)}" y="{_number(baseline)}" '
+        f'font-family="{_escape(family)}" font-size="{_number(size)}" '
+        f'{_paint(glyph.fill, glyph.opacity)}>{_escape(glyph.character)}</text>'
+    )
+
+
+def _number(value: float) -> str:
+    """Format one coordinate or size without trailing zeros."""
+    return str(int(value)) if float(value).is_integer() else f"{round(float(value), 3):g}"
+
+
+def _digits(colour: str | None) -> str | None:
+    """Return the hex digits of #rrggbb or #rrggbbaa, or None for transparent or unknown."""
+    digits = "" if colour is None else str(colour).strip().lower().lstrip("#")
+    if len(digits) in (6, 8) and _HEX_DIGITS.issuperset(digits):
+        return digits
+    return None
+
+
+def _paint(colour: str | None, opacity: float | None = None) -> str:
+    """Return the fill attributes of one colour: a hex fill with its opacity, or fill="none"."""
+    digits = _digits(colour)
+    if digits is None:
+        return NONE
+    attributes = f'fill="#{digits[:6]}"'
+    alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
+    if opacity is not None:
+        alpha *= min(1.0, max(0.0, opacity))
+    if alpha < 1.0:
+        attributes += f' fill-opacity="{round(alpha, 2):g}"'
+    return attributes
+
+
+def _palette_codes(grid: CellGrid, palette: Palette) -> np.ndarray:
+    """Return the (rows, cols) string array of #rrggbb cell colours of a pixel render."""
+    array = np.asarray(palette, dtype=np.float32)[np.asarray(grid.index, dtype=np.intp), :3]
+    rgb8 = np.floor(np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.int32)
+    packed = (rgb8[..., 0] << 16) | (rgb8[..., 1] << 8) | rgb8[..., 2]
+    codes, ids = np.unique(packed, return_inverse=True)
+    return np.array([f"#{int(code):06x}" for code in codes], dtype=object)[
+        np.asarray(ids).reshape(grid.rows, grid.cols)]
+
+
+def _layout_codes(glyphs: list[Glyph], grid: CellGrid, field: str) -> np.ndarray:
+    """Return one layout colour per cell, row-major when the layout is exactly one per cell."""
+    codes = np.full((grid.rows, grid.cols), TRANSPARENT, dtype=object)
+    if len(glyphs) == grid.rows * grid.cols:
+        codes.flat[:] = [getattr(glyph, field) or TRANSPARENT for glyph in glyphs]
+        return codes
+    for glyph in glyphs:
+        row, col = _cell_of(glyph, grid)
+        codes[row, col] = getattr(glyph, field) or TRANSPARENT
+    return codes
+
+
+def _paper_codes(glyphs: list[Glyph], grid: CellGrid, style: RenderStyle) -> np.ndarray:
+    """Return the paper colour of every cell, complete when the layout does not tile the grid.
+
+    A renderer whose layout does not place one glyph per cell (``text`` lays out a paragraph,
+    not a grid) leaves cells uncovered: those cells take the style's ``bg`` colour, exactly as
+    its rasterisation paints them, so the vector and raster outputs agree (§3, §11, E1).
+    """
+    codes = _layout_codes(glyphs, grid, "paper")
+    if len(glyphs) == grid.rows * grid.cols:
+        return codes
+    background = _style_colour(style, "bg") or TRANSPARENT
+    return np.where(codes == TRANSPARENT, background, codes)
+
+
+def _cell_of(glyph: Glyph, grid: CellGrid) -> tuple[int, int]:
+    """Return the (row, col) cell a placed glyph box starts in, clamped to the grid."""
+    col = int(glyph.x // grid.cell_w) if grid.cell_w > 0 else 0
+    row = int(glyph.y // grid.cell_h) if grid.cell_h > 0 else 0
+    return min(grid.rows - 1, max(0, row)), min(grid.cols - 1, max(0, col))
+
+
+def _encode(codes: np.ndarray, alpha: np.ndarray | None = None) -> _Layer:
+    """Return the (rows, cols) int32 ids of codes and the paint string of every label."""
+    labels, ids = np.unique(np.asarray(codes, dtype=object).astype(str), return_inverse=True)
+    ids = np.asarray(ids).reshape(np.shape(codes)).astype(np.int64)
+    if alpha is None:
+        return ids.astype(np.int32), [_paint(str(label)) for label in labels]
+    levels = np.round(np.clip(np.asarray(alpha, np.float32), 0.0, 1.0), 2)
+    alphas, aid = np.unique(levels, return_inverse=True)
+    aid = np.asarray(aid).reshape(ids.shape).astype(np.int64)
+    keys, combined = np.unique(ids * alphas.size + aid, return_inverse=True)
+    paints = [
+        _paint(str(labels[int(key) // alphas.size]), float(alphas[int(key) % alphas.size]))
+        for key in keys
+    ]
+    return np.asarray(combined).reshape(ids.shape).astype(np.int32), paints
+
+
+def _rects(ids: np.ndarray, paints: list[str], cell_w: int, cell_h: int) -> list[str]:
+    """Return one <rect> per rectangle of equal cells, merged along rows then down columns."""
+    ids = np.asarray(ids)
+    open_runs: dict[tuple[int, int, int], list[int]] = {}
+    boxes: list[tuple[int, int, int, int, int]] = []
+    for row in range(ids.shape[0]):
+        line = ids[row]
+        changes = (np.nonzero(np.diff(line))[0] + 1).tolist() if line.size > 1 else []
+        starts = [0, *changes]
+        ends = [*changes, int(line.size)]
+        current: dict[tuple[int, int, int], list[int]] = {}
+        for start, end in zip(starts, ends, strict=True):
+            key = (int(line[start]), start, end - start)
+            current[key] = [open_runs[key][0] if key in open_runs else row, row]
+        for key, (first, last) in open_runs.items():
+            if key not in current:
+                boxes.append((first, key[1], key[2], last - first + 1, key[0]))
+        open_runs = current
+    for key, (first, last) in open_runs.items():
+        boxes.append((first, key[1], key[2], last - first + 1, key[0]))
+    parts: list[str] = []
+    for top, left, width, height, label in sorted(boxes):
+        paint = paints[label]
+        if paint != NONE:
+            parts.append(
+                f'<rect x="{left * cell_w}" y="{top * cell_h}" '
+                f'width="{width * cell_w}" height="{height * cell_h}" {paint}/>'
+            )
+    return parts
+
+
+__all__ = ["DEFAULT_MAX_BYTES", "SVG_NS", "Glyph", "render_svg"]
diff --git a/lattice_core/textout.py b/lattice_core/textout.py
new file mode 100644
index 0000000..38a6052
--- /dev/null
+++ b/lattice_core/textout.py
@@ -0,0 +1,149 @@
+"""Text export of a CellGrid from the renderer's ``layout()``: txt, ansi and html (§11, P3).
+
+One placement per cell is the premise of every format: a renderer whose layout does not place
+exactly ``cols * rows`` boxes has no cell grid to print, so this module raises instead of
+producing a misleading file. ``.txt`` is UTF-8, cells separated by one space, one ``\\n`` per
+row. ``.ansi`` is truecolor only: each cell sets its 24-bit background then foreground, and
+every line ends with a bare SGR reset, so no 8- or 16-colour code is ever emitted. ``.html``
+is a standalone page whose ``<pre>`` carries the same grid, with the glyph text escaped.
+Strings only: this module never writes a file (the caller does).
+"""
+
+from __future__ import annotations
+
+import html
+import re
+
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle
+from lattice_core.svg import Glyph, _digits, _placements
+from lattice_core.types import Palette
+
+FORMATS = ("txt", "ansi", "html")
+BLANK = "\u00b7"  # the token written for a cell whose glyph is whitespace (E1, §11)
+_RESET = "\x1b[0m"
+_WHITESPACE = re.compile(r"[\t\r\n]+")
+
+
+def render_text(
+    grid: CellGrid,
+    palette: Palette,
+    renderer: CellRenderer,
+    style: RenderStyle | None = None,
+    *,
+    fmt: str = "txt",
+) -> str:
+    """Return grid printed in fmt ("txt", "ansi" or "html"), one token per cell.
+
+    fmt is case-sensitive; any other value raises ValueError naming it. A renderer without a
+    layout, or whose layout does not place exactly cols * rows glyphs, raises ValueError
+    naming the renderer and the format (§11: no misleading text export is written).
+    """
+    if fmt not in FORMATS:
+        raise ValueError(f"unknown text format {fmt!r}; expected one of {FORMATS}")
+    style = RenderStyle(options={}) if style is None else style
+    placements = _placements(grid, palette, renderer, style)
+    cells = _cell_rows(placements, grid, renderer, fmt)
+    if fmt == "ansi":
+        return _ansi(cells)
+    if fmt == "html":
+        return _html(cells, grid)
+    return _txt(cells)
+
+
+def _cell_rows(
+    placements: list[Glyph] | None, grid: CellGrid, renderer: CellRenderer, fmt: str
+) -> list[list[Glyph]]:
+    """Return the placements as rows of cells, refusing a layout that is not one per cell."""
+    name = getattr(renderer, "name", type(renderer).__name__)
+    if placements is None:
+        raise ValueError(f"renderer {name!r} has no layout() and cannot export {fmt!r}")
+    expected = grid.cols * grid.rows
+    if len(placements) != expected:
+        raise ValueError(
+            f"renderer {name!r} cannot export {fmt!r}: its layout places "
+            f"{len(placements)} glyphs for {expected} cells"
+        )
+    return [[placements[row * grid.cols + col] for col in range(grid.cols)]
+            for row in range(grid.rows)]
+
+
+def _token(glyph: Glyph) -> str:
+    """Return one glyph's text token: never blank, so every cell stays exactly one token.
+
+    A renderer may place a space (a blank glyph, a white cell); space-separated, such a token
+    would vanish and shift the row's columns. A whitespace glyph is therefore written as a
+    middle dot (E1, §11): the grid keeps ``cols * rows`` tokens over ``rows`` lines, and the
+    dot reads as the empty cell.
+    """
+    token = _WHITESPACE.sub(" ", glyph.character)
+    return BLANK if not token.strip() else token
+
+
+def _txt(cells: list[list[Glyph]]) -> str:
+    """Return the cells space-separated, one newline-terminated line per row."""
+    return "".join(" ".join(_token(glyph) for glyph in row) + "\n" for row in cells)
+
+
+def _rgb(colour: str | None) -> tuple[int, int, int] | None:
+    """Return the (r, g, b) bytes of a colour, or None when it paints nothing."""
+    digits = _digits(colour)
+    if digits is None:
+        return None
+    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
+
+
+def _ansi(cells: list[list[Glyph]]) -> str:
+    """Return the cells as 24-bit SGR coloured characters, one reset-terminated line per row."""
+    lines: list[str] = []
+    for row in cells:
+        parts: list[str] = []
+        coloured = False
+        for glyph in row:
+            sequence = _sgr(glyph)
+            coloured = coloured or bool(sequence)
+            parts.append(sequence + _token(glyph))
+        lines.append("".join(parts) + (_RESET if coloured else "") + "\n")
+    return "".join(lines)
+
+
+def _sgr(glyph: Glyph) -> str:
+    """Return the 24-bit background then foreground SGR of a cell, empty if it paints nothing."""
+    sequence = ""
+    background = _rgb(glyph.paper)
+    if background is not None:
+        sequence += f"\x1b[48;2;{background[0]};{background[1]};{background[2]}m"
+    foreground = _rgb(glyph.fill)
+    if foreground is not None:
+        sequence += f"\x1b[38;2;{foreground[0]};{foreground[1]};{foreground[2]}m"
+    return sequence
+
+
+def _html(cells: list[list[Glyph]], grid: CellGrid) -> str:
+    """Return a standalone HTML page whose <pre> renders the same grid, text escaped."""
+    body = "".join("".join(_span(glyph) for glyph in row) + "\n" for row in cells)
+    return (
+        "<!DOCTYPE html>\n"
+        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
+        f"<title>Lattice export ({grid.cols}x{grid.rows})</title>\n"
+        "<style>pre{font-family:monospace;line-height:1;margin:0;padding:0}</style>\n"
+        "</head>\n<body>\n"
+        f'<pre data-cols="{grid.cols}" data-rows="{grid.rows}">'
+        + body
+        + "</pre>\n</body>\n</html>\n"
+    )
+
+
+def _span(glyph: Glyph) -> str:
+    """Return one escaped <span> carrying the cell's ink and paper colours."""
+    styles: list[str] = []
+    paper = _rgb(glyph.paper)
+    if paper is not None:
+        styles.append(f"background:#{paper[0]:02x}{paper[1]:02x}{paper[2]:02x}")
+    ink = _rgb(glyph.fill)
+    if ink is not None:
+        styles.append(f"color:#{ink[0]:02x}{ink[1]:02x}{ink[2]:02x}")
+    attributes = f' style="{";".join(styles)}"' if styles else ""
+    return f"<span{attributes}>{html.escape(_token(glyph))}</span>"
+
+
+__all__ = ["FORMATS", "render_text"]
diff --git a/tests/test_svg.py b/tests/test_svg.py
new file mode 100644
index 0000000..c050ffa
--- /dev/null
+++ b/tests/test_svg.py
@@ -0,0 +1,365 @@
+"""Tests for the SVG export of a CellGrid (card L11, §11, H11).
+
+The document is verified by parsing, never by launching a browser: a document that
+``xml.etree.ElementTree`` reads back, whose rectangles cover every cell exactly once and
+whose colours are the palette's, is a document Inkscape, Illustrator and a browser open
+without repair. Expected geometry is pinned as literals derived from the contract.
+"""
+
+from __future__ import annotations
+
+import xml.etree.ElementTree as ET
+from pathlib import Path
+
+import numpy as np
+import pytest
+
+import lattice_core.renderers  # noqa: F401  (registers the built-in renderers)
+from lattice_core.cell import CellGrid, RenderStyle, get_renderer
+from lattice_core.svg import (
+    DEFAULT_MAX_BYTES,
+    SVG_NS,
+    render_svg,
+)
+from lattice_core.svg import _box_count as box_count
+from lattice_core.svg import _encode as encode
+from lattice_core.svg import _palette_codes as palette_codes
+from lattice_core.svg import _rects as cell_rects
+from lattice_core.types import Palette
+
+NS = f"{{{SVG_NS}}}"
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+FOUR: Palette = np.array(
+    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32
+)
+CELL_W, CELL_H = 8, 16
+
+
+def _grid(index: np.ndarray, cell_w: int = 1, cell_h: int = 1,
+          luma: np.ndarray | None = None, subindex: np.ndarray | None = None,
+          samples_k: int = 1) -> CellGrid:
+    """Build a CellGrid with the given palette indices, luma ramp and sample stencil size."""
+    rows, cols = index.shape
+    shape = (rows, cols)
+    return CellGrid(
+        cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
+        index=np.asarray(index, dtype=np.int32),
+        coverage=np.full(shape, 0.5, dtype=np.float32),
+        luma=np.asarray(luma, dtype=np.float32) if luma is not None else np.full(
+            shape, 0.5, dtype=np.float32),
+        samples=np.full(shape + (samples_k,), 0.5, dtype=np.float32),
+        subindex=subindex,
+    )
+
+
+def _ramp(rows: int, cols: int) -> np.ndarray:
+    """Return a left-to-right luma ramp from 0 to 1, the whole glyph ramp being used."""
+    return np.tile(np.linspace(0.0, 1.0, cols, dtype=np.float32), (rows, 1))
+
+
+def _root(svg: str) -> ET.Element:
+    """Parse the document, as a browser would, and return its root element."""
+    return ET.fromstring(svg)
+
+
+def _rects(svg: str) -> list[ET.Element]:
+    """Return the rectangle elements of the document, in document order."""
+    return _root(svg).findall(f"{NS}rect")
+
+
+def _texts(svg: str) -> list[ET.Element]:
+    """Return the text elements of the document, in document order."""
+    return _root(svg).findall(f"{NS}text")
+
+
+def _painting(svg: str, cell_w: int = 1, cell_h: int = 1) -> np.ndarray:
+    """Rebuild the (rows, cols) fill of every cell by reading the rectangles, never rasterising."""
+    root = _root(svg)
+    width = int(root.get("width", "0")) // cell_w
+    height = int(root.get("height", "0")) // cell_h
+    cells = np.full((height, width), "", dtype=object)
+    for element in root.findall(f"{NS}rect"):
+        left = int(element.get("x", "0")) // cell_w
+        top = int(element.get("y", "0")) // cell_h
+        run = int(element.get("width", "0")) // cell_w
+        tall = int(element.get("height", "0")) // cell_h
+        cells[top : top + tall, left : left + run] = str(element.get("fill"))
+    return cells
+
+
+def _expected(grid: CellGrid, palette: Palette) -> np.ndarray:
+    """Return the #rrggbb string of every cell's palette colour."""
+    rgb = np.floor(np.clip(np.asarray(palette, np.float32)[grid.index, :3], 0.0, 1.0)
+                   * 255.0 + 0.5).astype(np.int32)
+    return np.array([[f"#{r:02x}{g:02x}{b:02x}" for r, g, b in row] for row in rgb], dtype=object)
+
+
+# --- accept: the output parses as XML and has the right root namespace ---
+
+
+def test_the_document_parses_with_the_svg_namespace() -> None:
+    svg, warnings = render_svg(_grid(np.zeros((4, 4), np.int32)), BW, get_renderer("pixel"))
+    root = _root(svg)
+    assert root.tag == f"{NS}svg"
+    assert root.get("xmlns") is None  # the namespace is the tag's, not an attribute
+    assert warnings == []
+
+
+def test_the_root_carries_the_exact_output_geometry() -> None:
+    grid = _grid(np.zeros((3, 5), np.int32), cell_w=CELL_W, cell_h=CELL_H)
+    svg, _ = render_svg(grid, BW, get_renderer("pixel"))
+    root = _root(svg)
+    assert root.get("width") == "40"
+    assert root.get("height") == "48"
+    assert root.get("viewBox") == "0 0 40 48"
+
+
+def test_the_document_round_trips_through_a_file(tmp_path: Path) -> None:
+    svg, _ = render_svg(_grid(np.zeros((2, 3), np.int32)), BW, get_renderer("pixel"))
+    target = tmp_path / "out.svg"
+    target.write_text(svg, encoding="utf-8")
+    assert ET.parse(target).getroot().tag == f"{NS}svg"
+
+
+# --- accept: a 64x64 pixel render produces fewer <rect> elements than cells (runs merged) ---
+
+
+def test_a_64x64_pixel_render_merges_its_runs() -> None:
+    blocks = (np.add.outer(np.arange(64) // 4, np.arange(64) // 4) % 2).astype(np.int32)
+    svg, warnings = render_svg(_grid(blocks), BW, get_renderer("pixel"))
+    assert len(_rects(svg)) < 64 * 64
+    assert warnings == []
+
+
+def test_a_flat_pixel_render_is_a_single_rectangle() -> None:
+    svg, _ = render_svg(_grid(np.zeros((16, 16), np.int32)), BW, get_renderer("pixel"))
+    rects = _rects(svg)
+    assert len(rects) == 1
+    assert rects[0].get("width") == "16"
+    assert rects[0].get("height") == "16"
+
+
+def test_every_cell_is_painted_exactly_its_palette_colour() -> None:
+    index = (np.add.outer(np.arange(9) // 3, np.arange(9) // 3) % 4).astype(np.int32)
+    grid = _grid(index)
+    svg, _ = render_svg(grid, FOUR, get_renderer("pixel"))
+    painted = _painting(svg)
+    assert (painted != "").all()  # no cell left unpainted, no cell painted twice
+    assert (painted == _expected(grid, FOUR)).all()
+
+
+def test_runs_merge_downwards_as_well_as_across() -> None:
+    index = np.zeros((8, 8), np.int32)
+    index[:4] = 1  # two horizontal bands: two rectangles, not eight rows
+    svg, _ = render_svg(_grid(index), BW, get_renderer("pixel"))
+    assert len(_rects(svg)) == 2
+
+
+# --- accept: a glyph render produces exactly cols * rows <text> elements ---
+
+
+@pytest.mark.parametrize("name", ["glyph_ramp", "glyph_shape", "braille", "sextant"])
+def test_a_glyph_render_has_one_text_element_per_cell(name: str) -> None:
+    renderer = get_renderer(name)
+    sx, sy = renderer.subgrid()
+    subindex = None if sx * sy == 1 else np.zeros((4, 6, sx * sy), np.int32)
+    grid = _grid(np.zeros((4, 6), np.int32), CELL_W, CELL_H,
+                 luma=_ramp(4, 6), subindex=subindex, samples_k=6)
+    svg, warnings = render_svg(grid, BW, renderer,
+                               RenderStyle(options={"text": "Lattice glyph export"}))
+    assert len(_texts(svg)) == 4 * 6
+    assert warnings == []
+
+
+def test_a_text_element_carries_its_typography_and_ink() -> None:
+    grid = _grid(np.zeros((2, 3), np.int32), CELL_W, CELL_H, luma=_ramp(2, 3))
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
+    element = _texts(svg)[0]
+    assert element.get("font-family") == "monospace"
+    assert element.get("font-size") == str(CELL_H)
+    assert element.get("fill") == "#000000"
+    assert element.get("x") == "0"
+    assert float(element.get("y", "0")) == pytest.approx(0.8 * CELL_H)
+
+
+def test_the_glyph_text_is_the_renderer_layout() -> None:
+    grid = _grid(np.zeros((3, 4), np.int32), CELL_W, CELL_H, luma=_ramp(3, 4))
+    renderer = get_renderer("glyph_ramp")
+    svg, _ = render_svg(grid, BW, renderer)
+    placed = [glyph.character
+              for glyph in renderer.layout(grid, RenderStyle(options={}))]  # type: ignore
+    assert [element.text for element in _texts(svg)] == placed
+
+
+def test_the_paper_is_painted_behind_the_glyphs() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), CELL_W, CELL_H, luma=_ramp(2, 2))
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
+    children = list(_root(svg))
+    rects = [child for child in children if child.tag == f"{NS}rect"]
+    texts = [child for child in children if child.tag == f"{NS}text"]
+    assert len(rects) == 1  # a uniform paper merges into one rectangle
+    assert rects[0].get("fill") == "#ffffff"
+    assert children[: len(rects)] == rects  # paper first, glyphs painted over it
+    assert len(texts) == 4
+
+
+def test_a_translucent_paper_carries_its_opacity() -> None:
+    grid = _grid(np.zeros((1, 1), np.int32), CELL_W, CELL_H)
+    style = RenderStyle(options={"bg": "#ffffff80"})
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
+    assert _rects(svg)[0].get("fill-opacity") == "0.5"
+
+
+def test_glyph_text_is_escaped() -> None:
+    luma = np.array([[0.0, 1.0]], dtype=np.float32)
+    grid = _grid(np.zeros((1, 2), np.int32), CELL_W, CELL_H, luma=luma)
+    style = RenderStyle(options={"ramp": "<&"})
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
+    assert [element.text for element in _texts(svg)] == ["<", "&"]
+    assert "&lt;" in svg and "&amp;" in svg
+
+
+def test_the_font_option_names_the_font_family() -> None:
+    grid = _grid(np.zeros((1, 1), np.int32), CELL_W, CELL_H)
+    style = RenderStyle(options={"font": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"})
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), style)
+    assert _texts(svg)[0].get("font-family") == "DejaVuSansMono"
+
+
+# --- accept: the 8 MB budget triggers a merge and a warning on a large render ---
+
+
+def _noise(size: int, colours: int = 16) -> np.ndarray:
+    """Return a size x size grid of pseudo-random palette indices, so runs never merge."""
+    rng = np.random.default_rng(0)
+    return rng.integers(0, colours, size=(size, size), dtype=np.int32)
+
+
+def _palette16() -> Palette:
+    """Return sixteen evenly spaced colours, so every index is a distinct RGB."""
+    steps = np.linspace(0.0, 1.0, 16, dtype=np.float32)
+    return np.stack([steps, 1.0 - steps, steps * 0.5], axis=1).astype(np.float32)
+
+
+def test_a_2048_pixel_render_stays_under_the_default_budget() -> None:
+    grid = _grid(_noise(2048), cell_w=1, cell_h=1)
+    svg, warnings = render_svg(grid, _palette16(), get_renderer("pixel"))
+    assert len(svg.encode("utf-8")) <= DEFAULT_MAX_BYTES
+    assert warnings and "8000000-byte budget" in warnings[0]
+    assert "blocks" in warnings[0]
+
+
+def test_the_budget_warning_names_the_merge_that_was_applied() -> None:
+    svg, warnings = render_svg(
+        _grid(_noise(32)), _palette16(), get_renderer("pixel"), max_bytes=4000
+    )
+    assert len(svg.encode("utf-8")) <= 4000
+    assert len(warnings) == 1
+    assert "budget" in warnings[0]
+
+
+def test_a_glyph_render_over_budget_degrades_to_rectangles() -> None:
+    grid = _grid(_noise(48), CELL_W, CELL_H, luma=_ramp(48, 48))
+    svg, warnings = render_svg(grid, _palette16(), get_renderer("glyph_ramp"),
+                               max_bytes=100_000)
+    assert len(_texts(svg)) == 0
+    assert len(_rects(svg)) > 0
+    assert warnings and "glyphs merged into cell rectangles" in warnings[0]
+    assert len(svg.encode("utf-8")) <= 100_000
+
+
+def test_the_degraded_glyph_rectangles_keep_the_cell_ink() -> None:
+    grid = _grid(np.zeros((4, 4), np.int32), CELL_W, CELL_H, luma=np.zeros((4, 4), np.float32))
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"), max_bytes=120)
+    rects = _rects(svg)
+    fills = {element.get("fill") for element in rects}
+    assert fills == {"#000000", "#ffffff"}  # paper then ink, not one flat colour
+    ink = [element for element in rects if element.get("fill") == "#000000"]
+    assert ink and all(element.get("fill-opacity") == "0.5" for element in ink)
+
+
+def test_a_budget_too_small_for_anything_is_reported_not_crashed() -> None:
+    grid = _grid(_noise(8), CELL_W, CELL_H, luma=_ramp(8, 8))
+    svg, warnings = render_svg(grid, _palette16(), get_renderer("glyph_ramp"), max_bytes=40)
+    assert warnings
+    assert _root(svg).tag == f"{NS}svg"
+
+
+def no_text(svg: str) -> bool:
+    """Return True when the document carries no glyph, i.e. it was degraded to rectangles."""
+    return _texts(svg) == []
+
+
+def test_a_large_structured_render_keeps_its_runs_and_is_not_degraded() -> None:
+    blocks = (((np.arange(512) // 32)[:, None] + (np.arange(512) // 32)[None, :]) % 16)
+    svg, warnings = render_svg(_grid(blocks.astype(np.int32)), _palette16(),
+                               get_renderer("pixel"))
+    assert warnings == []  # 16x16 blocks merge into 256 rectangles, far under the cap
+    assert len(_rects(svg)) == 256
+
+
+def test_a_glyph_export_over_budget_merges_cells_rather_than_blocks() -> None:
+    grid = _grid(np.zeros((32, 32), np.int32), CELL_W, CELL_H)
+    svg, warnings = render_svg(grid, BW, get_renderer("glyph_ramp"), max_bytes=600)
+    assert no_text(svg) and _rects(svg)
+    assert warnings and "budget" in warnings[0]
+    assert len(svg.encode("utf-8")) <= 600
+
+
+def test_the_rectangle_count_matches_the_emitted_rectangles() -> None:
+    grid = _grid(_noise(64, colours=4))
+    ids, paints = encode(palette_codes(grid, _palette16()[:4]))
+    assert box_count(ids) == len(cell_rects(ids, paints, 1, 1))
+
+
+def test_a_non_positive_budget_is_refused() -> None:
+    with pytest.raises(ValueError, match="max_bytes"):
+        render_svg(_grid(np.zeros((1, 1), np.int32)), BW, get_renderer("pixel"), max_bytes=0)
+
+
+# --- accept: the file opens in a browser without repair (parsing, not launching) ---
+
+
+def test_a_glyph_document_is_well_formed_and_complete() -> None:
+    grid = _grid(np.zeros((6, 6), np.int32), CELL_W, CELL_H, luma=_ramp(6, 6))
+    svg, _ = render_svg(grid, BW, get_renderer("glyph_ramp"))
+    root = _root(svg)
+    assert root.tag == f"{NS}svg"
+    assert root.get("viewBox") == f"0 0 {6 * CELL_W} {6 * CELL_H}"
+    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
+    assert len(_texts(svg)) == 36
+
+
+# --- invariants: purity, no mutation, no application import ---
+
+
+def test_render_svg_is_pure() -> None:
+    grid = _grid(_noise(8), CELL_W, CELL_H, luma=_ramp(8, 8))
+    renderer = get_renderer("glyph_ramp")
+    assert render_svg(grid, BW, renderer) == render_svg(grid, BW, renderer)
+
+
+def test_render_svg_does_not_mutate_its_inputs() -> None:
+    index = _noise(8)
+    grid = _grid(index, CELL_W, CELL_H, luma=_ramp(8, 8))
+    before_index, before_luma = grid.index.copy(), grid.luma.copy()
+    render_svg(grid, BW, get_renderer("glyph_ramp"))
+    assert (grid.index == before_index).all()
+    assert (grid.luma == before_luma).all()
+    assert np.asarray(BW).tolist() == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]
+
+
+def test_the_export_modules_import_no_application_and_no_qt() -> None:
+    import ast
+
+    root = Path(__file__).resolve().parents[1] / "lattice_core"
+    forbidden = {"lattice_dither", "lattice_glyph", "lattice_glitch", "PySide6"}
+    for name in ("svg.py", "textout.py"):
+        tree = ast.parse((root / name).read_text(encoding="utf-8"))
+        imported: set[str] = set()
+        for node in ast.walk(tree):
+            if isinstance(node, ast.Import):
+                imported |= {alias.name.split(".")[0] for alias in node.names}
+            elif isinstance(node, ast.ImportFrom) and node.module:
+                imported.add(node.module.split(".")[0])
+        assert not (imported & forbidden), f"{name} imports {imported & forbidden}"
diff --git a/tests/test_textout.py b/tests/test_textout.py
new file mode 100644
index 0000000..44b2fe2
--- /dev/null
+++ b/tests/test_textout.py
@@ -0,0 +1,220 @@
+"""Tests for the text export of a CellGrid (card L11, §11, P3).
+
+``.txt`` must contain ``cols * rows`` tokens over ``rows`` lines, ``.ansi`` must carry 24-bit
+SGR sequences and nothing else, and ``.html`` must render the same grid while escaping its
+glyph text. Every format is derived from the renderer's ``layout()`` (H11), so the tests pin
+the layout's characters rather than re-deriving them from luma.
+"""
+
+from __future__ import annotations
+
+import re
+
+import numpy as np
+import pytest
+
+import lattice_core.renderers  # noqa: F401  (registers the built-in renderers)
+from lattice_core.cell import CellGrid, RenderStyle, get_renderer
+from lattice_core.textout import BLANK, FORMATS, render_text
+from lattice_core.types import Palette
+
+BW: Palette = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+FOUR: Palette = np.array(
+    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32
+)
+CELL_W, CELL_H = 8, 16
+SGR = re.compile(r"\x1b\[([0-9;]*)m")
+TRUECOLOR = re.compile(r"^(0|38;2;\d{1,3};\d{1,3};\d{1,3}|48;2;\d{1,3};\d{1,3};\d{1,3})$")
+
+
+def _grid(index: np.ndarray, cell_w: int = CELL_W, cell_h: int = CELL_H,
+          luma: np.ndarray | None = None, subindex: np.ndarray | None = None,
+          samples_k: int = 6) -> CellGrid:
+    """Build a CellGrid with the given indices, luma and optional sub-point indices."""
+    rows, cols = index.shape
+    shape = (rows, cols)
+    return CellGrid(
+        cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
+        index=np.asarray(index, dtype=np.int32),
+        coverage=np.full(shape, 0.5, dtype=np.float32),
+        luma=np.asarray(luma, dtype=np.float32) if luma is not None else np.full(
+            shape, 0.5, dtype=np.float32),
+        samples=np.full(shape + (samples_k,), 0.5, dtype=np.float32),
+        subindex=subindex,
+    )
+
+
+def _ramp(rows: int, cols: int) -> np.ndarray:
+    """Return a left-to-right luma ramp from 0 to 1 over the whole glyph ramp."""
+    return np.tile(np.linspace(0.0, 1.0, cols, dtype=np.float32), (rows, 1))
+
+
+def _chars(rows: int, cols: int) -> list[str]:
+    """Return the tokens glyph_ramp places for a ramp grid, row-major, blanks as the dot."""
+    grid = _grid(np.zeros((rows, cols), np.int32), luma=_ramp(rows, cols))
+    renderer = get_renderer("glyph_ramp")
+    return [BLANK if not entry.character.strip() else entry.character
+            for entry in renderer.layout(grid, RenderStyle(options={}))]  # type: ignore
+
+
+# --- accept: txt has cols * rows tokens and rows lines ---
+
+
+def test_txt_has_one_token_per_cell_and_one_line_per_row() -> None:
+    grid = _grid(np.zeros((5, 7), np.int32), luma=_ramp(5, 7))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"))
+    lines = text.splitlines()
+    assert len(lines) == 5
+    assert sum(len(line.split(" ")) for line in lines) == 35
+
+
+def test_txt_tokens_are_the_layout_characters() -> None:
+    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"))
+    assert [token for line in text.splitlines() for token in line.split(" ")] == _chars(3, 4)
+
+
+def test_txt_ends_every_line_with_a_newline() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"))
+    assert text.endswith("\n")
+    assert text.count("\n") == 2
+
+
+def test_txt_is_utf8_without_escape_codes() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"))
+    assert "\x1b" not in text
+    assert text.encode("utf-8").decode("utf-8") == text
+
+
+def test_txt_keeps_a_blank_glyph_as_its_own_token() -> None:
+    grid = _grid(np.zeros((1, 3), np.int32),
+                 luma=np.array([[0.0, 1.0, 0.0]], dtype=np.float32))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"))
+    tokens = text.rstrip("\n").split(" ")
+    assert len(tokens) == 3
+    assert tokens[1] == BLANK  # the white cell's space glyph stays one token (E1)
+
+
+@pytest.mark.parametrize(("name", "geometry"), [("braille", (2, 4)), ("sextant", (2, 3))])
+def test_a_bitmask_render_exports_txt_from_its_layout(name: str, geometry: tuple[int, int]) -> None:
+    sx, sy = geometry
+    grid = _grid(np.zeros((3, 3), np.int32), subindex=np.zeros((3, 3, sx * sy), np.int32))
+    text = render_text(grid, BW, get_renderer(name))
+    lines = text.splitlines()
+    assert len(lines) == 3
+    assert sum(len(line.split(" ")) for line in lines) == 9
+
+
+# --- accept: ansi contains SGR 24-bit sequences only ---
+
+
+def test_ansi_uses_only_24_bit_sequences() -> None:
+    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
+    sequences = SGR.findall(text)
+    assert sequences
+    assert all(TRUECOLOR.match(sequence) for sequence in sequences)
+
+
+def test_ansi_carries_the_cell_ink_and_paper() -> None:
+    grid = _grid(np.zeros((1, 1), np.int32), luma=np.zeros((1, 1), np.float32))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
+    assert "\x1b[48;2;255;255;255m" in text  # paper #ffffff
+    assert "\x1b[38;2;0;0;0m" in text  # ink #000000
+    assert text.endswith("\x1b[0m\n")
+
+
+def test_ansi_resets_each_line() -> None:
+    grid = _grid(np.zeros((3, 3), np.int32), luma=_ramp(3, 3))
+    lines = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi").splitlines()
+    assert len(lines) == 3
+    assert all(line.endswith("\x1b[0m") for line in lines)
+
+
+def test_ansi_strips_back_to_the_same_characters() -> None:
+    grid = _grid(np.zeros((2, 3), np.int32), luma=_ramp(2, 3))
+    ansi = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
+    plain = SGR.sub("", ansi)
+    # ANSI paints one terminal cell per cell, so it carries no separators: the stripped
+    # output is the row tokens joined, with no space between them.
+    rows = ["".join(_chars(2, 3)[row * 3 : row * 3 + 3]) for row in range(2)]
+    assert plain.splitlines() == rows
+
+
+def test_ansi_never_leaks_into_the_text_path() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    assert "\x1b" not in render_text(grid, BW, get_renderer("glyph_ramp"))
+
+
+# --- accept: html renders the same grid and escapes < / & ---
+
+
+def test_html_renders_the_same_grid() -> None:
+    grid = _grid(np.zeros((2, 3), np.int32), luma=_ramp(2, 3))
+    page = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="html")
+    spans = re.findall(r"<span[^>]*>(.*?)</span>", page)
+    assert spans == _chars(2, 3)
+    assert page.count("\n") >= 2
+    assert page.startswith("<!DOCTYPE html>")
+
+
+def test_html_escapes_glyph_text() -> None:
+    grid = _grid(np.zeros((1, 2), np.int32),
+                 luma=np.array([[0.0, 1.0]], dtype=np.float32))
+    page = render_text(grid, BW, get_renderer("glyph_ramp"),
+                       RenderStyle(options={"ramp": "<&"}), fmt="html")
+    assert "&lt;" in page and "&amp;" in page
+    assert "<&" not in page
+
+
+def test_html_states_the_grid_accessibly() -> None:
+    grid = _grid(np.zeros((4, 5), np.int32), luma=_ramp(4, 5))
+    page = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="html")
+    assert '<meta charset="utf-8">' in page
+    assert 'data-cols="5"' in page and 'data-rows="4"' in page
+    assert "<pre" in page and "</pre>" in page
+
+
+# --- interface: format validation and refusal to mislead ---
+
+
+def test_every_documented_format_is_accepted() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    assert FORMATS == ("txt", "ansi", "html")
+    for fmt in FORMATS:
+        assert render_text(grid, BW, get_renderer("glyph_ramp"), fmt=fmt)
+
+
+def test_an_unknown_format_is_named() -> None:
+    grid = _grid(np.zeros((1, 1), np.int32))
+    with pytest.raises(ValueError, match="rtf"):
+        render_text(grid, BW, get_renderer("glyph_ramp"), fmt="rtf")
+
+
+def test_a_renderer_without_layout_is_refused() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32))
+    with pytest.raises(ValueError, match="pixel"):
+        render_text(grid, BW, get_renderer("pixel"))
+
+
+def test_a_layout_that_is_not_one_per_cell_is_refused() -> None:
+    grid = _grid(np.zeros((3, 4), np.int32), luma=_ramp(3, 4))
+    with pytest.raises(ValueError, match="text"):
+        render_text(grid, BW, get_renderer("text"), fmt="ansi")
+
+
+def test_render_text_is_pure_and_writes_no_file(tmp_path) -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    renderer = get_renderer("glyph_ramp")
+    before = sorted(tmp_path.iterdir())
+    assert render_text(grid, BW, renderer) == render_text(grid, BW, renderer)
+    assert sorted(tmp_path.iterdir()) == before
+
+
+def test_the_ansi_escapes_are_only_resets_and_truecolor() -> None:
+    grid = _grid(np.zeros((2, 2), np.int32), luma=_ramp(2, 2))
+    text = render_text(grid, BW, get_renderer("glyph_ramp"), fmt="ansi")
+    heads = {sequence.split(";")[0] for sequence in SGR.findall(text)}
+    assert heads <= {"0", "38", "48"}


CODER NOTES AND DEVIATIONS
- Voir le bloc GATE RESULTS : les trois E1 y sont reproduites intégralement, ainsi que les mesures
  que le codeur dit avoir faites (rects fusionnés, 4608 `<text>` sur un rendu 48×96, budget 512×512
  dégradé à 15,8 KB avec warning, 2048×2048 non structuré coalescé en blocs 8×8 en 2,3 s).
- Un avertissement du harnais : le codeur a tenté d'écrire un fichier de sonde hors du dépôt
  (`probe_l11.py`) et l'écriture a été refusée. Cela ne concerne pas le livrable, mais il a donc
  sondé hors des quatre fichiers de la carte : vérifie que les tests ne dépendent d'aucun artefact
  externe resté sur disque.
