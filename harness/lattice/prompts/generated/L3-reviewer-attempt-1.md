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

CONTRACT EXCERPTS (version 0.1.0-draft)

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
    def consumes(self) -> frozenset[str]: ...  # subset of {"index", "luma", "samples"} (S2)
    def render(self, grid: CellGrid, palette: np.ndarray, style: RenderStyle) -> Image.Image: ...
```

Registry: `register_renderer`, `get_renderer(name)`, `list_renderers()`.

Normative invariants, each one a test:

1. `render` returns an image of exactly `(cols * cell_w, rows * cell_h)` pixels.
2. `render` is pure: identical inputs produce identical output, no module-level state.
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

## §5 Pipeline

Inherits Lattice Dither §13 (pre-dither conditioning) and its render order, with step 8 replaced by
the renderer call. The normative order becomes:

1. If `max_side`: area-downscale so `max(H, W) <= max_side`. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = `pre_blur / 3`).
6. Compute grid geometry from `renderer.cell_aspect()` and `pixel_size`.
7. Downscale to the grid.
8. `resolve_palette` on the image from step 7.
9. Algorithm (params through `resolve_params`) → `index`.
10. Derive `coverage` and `samples` per §3.
11. `renderer.render(grid, palette, style)`.
12. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.

Steps 3, 4 and 5 must be no-ops at their defaults. Step 11 replaces the 1.0 `apply_palette` +
`upscale_nearest` pair; `PixelRenderer` reproduces that pair exactly.

**Continuous mode (S1, decided 2026-11-16).** The pipeline may run without quantisation:
`algorithm: null` and `palette: null` are legal. In that mode steps 8 and 9 are skipped,
`grid.luma`/`samples` are derived from the step-7 cells, the renderer must be `pixel` at
cell 1×1, and `grid.index` carries nearest-source pixels (a pass-through). Lattice Glitch is an
effect-graph app that consumes the core (seed, masks, presets, bridge, CLI) without depending on
the CellRenderer quantisation chain.

TASK CARD

### L3 · Colour metrics and palette model
- wave: 0 · deps: L1 · executor: OMH deep · review: full · size: M
- owns: `lattice_core/color.py`, `lattice_core/palette.py`, `tests/test_color.py`,
  `tests/test_palette.py`
- context: §4, 1.1 §12, 1.1 §16
- spec: port the 1.1 colour metrics (`srgb`, `linear`, `oklab`, `lab2000`) into `lattice_core`.
  Add `Palette.lum_min` / `lum_max` computed once at construction in linear light. Palette import
  accepts hex lists, GPL files, PNG images and Lospec-style text; no network. `Palette.order` is a
  permutation or `None`.
- accept:
  - `srgb` output is byte-identical to the 1.0 implementation on 20 random images and 5 palettes.
  - `oklab` and `lab2000` disagree with `srgb` on at least 5 % of pixels of a saturated test image.
  - `lum_min`/`lum_max` are correct on a two-colour palette within 1e-6.
  - a GPL file, a PNG and a hex list of the same palette produce equal `Palette` objects.
  - a non-permutation `order` raises `ValueError` naming the offending index.
  - no import of `urllib`, `requests` or `socket` anywhere in `palette.py`.

GATE RESULTS (vague 0 — batterie complète sur l'arbre posé, 2026-11-16)
- G1 ruff: clean (repo entier). G2 pytest: **1287 passed, 1 skipped** (le skip est le smoke
  manuel test_bridge_smoke). G3 check_contract: OK. G4 : cette carte n'a écrit que ses owns.
- G7 témoins bit-à-bit : couverts par la suite (baselines 01/05/07 re-rendues dans G2).
- G8 registre : ["pixel"], aspect 1.0, subgrid (1,1), consumes {"index"}.

DIFF

diff --git a/lattice_core/palette.py b/lattice_core/palette.py
new file mode 100644
index 0000000..f646b2b
--- /dev/null
+++ b/lattice_core/palette.py
@@ -0,0 +1,146 @@
+"""Palette model: luminance bounds, importers and display order (CONTRACT §4, 1.1 §16).
+
+``Palette`` subclasses ``np.ndarray`` so every existing consumer that expects a
+plain float32 (K, 3) palette keeps working unchanged; the luminance bounds are
+computed once at construction in linear light and the display order is carried
+as a validated permutation.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core.color import srgb_to_linear
+from lattice_core.palettes import io as _io
+
+MIN_COLORS = 2
+MAX_COLORS = 256
+
+
+class Palette(np.ndarray):
+    """Float32 (K, 3) sRGB palette with linear-light luminance bounds and an order."""
+
+    def __new__(
+        cls,
+        colors: object,
+        *,
+        order: list[int] | None = None,
+    ) -> Palette:
+        array = np.asarray(colors, dtype=np.float32)
+        if array.ndim != 2 or array.shape[1] != 3:
+            raise ValueError(f"a palette must be a (K, 3) array, got shape {array.shape}")
+        if not MIN_COLORS <= array.shape[0] <= MAX_COLORS:
+            raise ValueError(
+                f"a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {array.shape[0]}"
+            )
+        palette = array.view(cls)
+        palette._lum_min, palette._lum_max = _luminance_bounds(palette)
+        palette._order = _validated_order(order, palette.shape[0])
+        return palette
+
+    def __array_finalize__(self, source: object) -> None:
+        """Carry the palette attributes over views, copies and slices."""
+        if source is None:
+            return
+        self._lum_min = getattr(source, "_lum_min", 0.0)
+        self._lum_max = getattr(source, "_lum_max", 0.0)
+        self._order = getattr(source, "_order", None)
+
+    @property
+    def lum_min(self) -> float:
+        """Minimum linear-light luminance of the palette colours."""
+        return self._lum_min
+
+    @property
+    def lum_max(self) -> float:
+        """Maximum linear-light luminance of the palette colours."""
+        return self._lum_max
+
+    @property
+    def order(self) -> list[int] | None:
+        """Display order as a permutation of ``range(K)``, or ``None`` for natural order."""
+        return self._order
+
+
+def _luminance_bounds(palette: np.ndarray) -> tuple[float, float]:
+    """Return (min, max) of the palette's linear-light BT.709 luminance."""
+    linear = srgb_to_linear(palette)
+    luma = 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]
+    return float(luma.min()), float(luma.max())
+
+
+def _validated_order(order: list[int] | None, size: int) -> list[int] | None:
+    """Return order as a permutation of range(size), or None, raising ValueError on a bad one."""
+    if order is None or len(order) == 0:
+        return None
+    seen: set[int] = set()
+    for index in order:
+        index = int(index)
+        if not 0 <= index < size:
+            raise ValueError(f"palette order index {index} is outside [0, {size})")
+        if index in seen:
+            raise ValueError(f"palette order index {index} is repeated")
+        seen.add(index)
+    if len(seen) != size:
+        missing = sorted(set(range(size)) - seen)[0]
+        raise ValueError(f"palette order is missing index {missing}")
+    return list(order)
+
+
+def from_hex_list(values: list[str]) -> Palette:
+    """Build a Palette from "#RRGGBB" strings, raising ValueError on a bad entry."""
+    return Palette(_io.from_hex_list(values))
+
+
+def from_hex_text(text: str) -> Palette:
+    """Parse a pasted list of hex colours (Lospec style), ignoring any surrounding prose."""
+    return Palette(_io.from_hex_text(text))
+
+
+def from_gpl(path: str | Path) -> Palette:
+    """Build a Palette from a GIMP .gpl palette file."""
+    return Palette(_io.load_palette(Path(path)))
+
+
+def from_png(source: str | Path | PILImage.Image) -> Palette:
+    """Build a Palette from the distinct colours of a PNG, in order of first appearance."""
+    if isinstance(source, PILImage.Image):
+        image = source
+    else:
+        image = PILImage.open(Path(source))
+    rgba = image.convert("RGBA")
+    background = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
+    rgb = PILImage.alpha_composite(background, rgba).convert("RGB")
+    pixels = np.asarray(rgb, dtype=np.uint8).reshape(-1, 3)
+    colors = _first_seen(pixels)
+    if not MIN_COLORS <= colors.shape[0] <= MAX_COLORS:
+        raise ValueError(
+            f"a palette needs {MIN_COLORS} to {MAX_COLORS} colours, got {colors.shape[0]}"
+        )
+    return Palette(np.ascontiguousarray(colors.astype(np.float32) / 255.0))
+
+
+def _first_seen(pixels: np.ndarray) -> np.ndarray:
+    """Return the distinct rows of a uint8 (N, 3) array, in order of first appearance."""
+    keys = (pixels[:, 0].astype(np.uint32) << 16) | (
+        pixels[:, 1].astype(np.uint32) << 8
+    ) | pixels[:, 2].astype(np.uint32)
+    seen: set[int] = set()
+    rows: list[np.ndarray] = []
+    for index in range(pixels.shape[0]):
+        key = int(keys[index])
+        if key not in seen:
+            seen.add(key)
+            rows.append(pixels[index])
+    return np.array(rows, dtype=np.uint8)
+
+
+def load(path: str | Path) -> Palette:
+    """Load a Palette from a .hex, .gpl or .png file, chosen by the file extension."""
+    path = Path(path)
+    if path.suffix.lower() == ".png":
+        return from_png(path)
+    return Palette(_io.load_palette(path))
diff --git a/tests/test_palette.py b/tests/test_palette.py
new file mode 100644
index 0000000..82d5949
--- /dev/null
+++ b/tests/test_palette.py
@@ -0,0 +1,173 @@
+"""Tests for the palette model and importers (card L3, CONTRACT §4 and 1.1 §16)."""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import numpy as np
+import pytest
+from PIL import Image as PILImage
+
+from lattice_core import color
+from lattice_core.palette import (
+    MAX_COLORS,
+    MIN_COLORS,
+    Palette,
+    from_gpl,
+    from_hex_list,
+    from_hex_text,
+    from_png,
+    load,
+)
+from lattice_core.palettes.io import hex_list
+
+TWO_COLORS = ["#000000", "#FFFFFF"]
+
+
+def test_lum_bounds_of_a_two_colour_palette() -> None:
+    """Black and white give lum_min 0.0 and lum_max 1.0 in linear light."""
+    palette = Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32))
+    assert palette.lum_min == pytest.approx(0.0, abs=1e-6)
+    assert palette.lum_max == pytest.approx(1.0, abs=1e-6)
+
+
+def test_lum_bounds_are_computed_in_linear_light() -> None:
+    """Red and white: red has linear luminance 0.2126, white has 1.0."""
+    palette = Palette(np.array([[1.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32))
+    assert palette.lum_min == pytest.approx(0.2126, abs=1e-6)
+    assert palette.lum_max == pytest.approx(1.0, abs=1e-6)
+
+
+def test_lum_bounds_are_computed_once_at_construction(tmp_path: Path) -> None:
+    """Mutating the array after construction leaves the remembered bounds untouched."""
+    colors = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
+    palette = Palette(colors)
+    before_min, before_max = palette.lum_min, palette.lum_max
+    colors[:] = 0.25
+    assert palette.lum_min == before_min
+    assert palette.lum_max == before_max
+
+
+def test_gpl_png_and_hex_list_imports_agree(tmp_path: Path) -> None:
+    """A GPL file, a PNG and a hex list of the same palette produce equal Palettes."""
+    gpl = tmp_path / "pair.gpl"
+    gpl.write_text(
+        "GIMP Palette\nName: pair\n#\n0 0 0\tBlack\n255 255 255\tWhite\n",
+        encoding="utf-8",
+    )
+    png = tmp_path / "pair.png"
+    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
+    image.putpixel((1, 0), (255, 255, 255))
+    image.save(png)
+
+    from_gpl_palette = from_gpl(gpl)
+    from_png_palette = from_png(png)
+    from_hex_palette = from_hex_list(TWO_COLORS)
+
+    for first, second in (
+        (from_gpl_palette, from_png_palette),
+        (from_gpl_palette, from_hex_palette),
+        (from_png_palette, from_hex_palette),
+    ):
+        assert np.array_equal(first, second)
+        assert first.lum_min == pytest.approx(second.lum_min, abs=1e-12)
+        assert first.lum_max == pytest.approx(second.lum_max, abs=1e-12)
+        assert first.order == second.order
+    assert hex_list(from_png_palette) == TWO_COLORS
+
+
+def test_from_png_accepts_a_pil_image() -> None:
+    """The PNG importer takes an already-open image as well as a path."""
+    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
+    image.putpixel((1, 0), (255, 255, 255))
+    assert np.array_equal(from_png(image), from_hex_list(TWO_COLORS))
+
+
+def test_from_png_composites_alpha_over_white() -> None:
+    """Transparent pixels read as white, like the image pipeline does."""
+    rgba = PILImage.new("RGBA", (2, 1))
+    rgba.putpixel((0, 0), (0, 0, 0, 0))
+    rgba.putpixel((1, 0), (255, 0, 0, 255))
+    palette = from_png(rgba)
+    assert palette.shape == (2, 3)
+    assert np.array_equal(palette, from_hex_list(["#FFFFFF", "#FF0000"]))
+
+
+def test_lospec_style_text_import() -> None:
+    """Pasted hex codes separated by commas, whitespace and prose are parsed."""
+    text = "Palette: #000000, #FFFFFF; the classic duo."
+    assert np.array_equal(from_hex_text(text), from_hex_list(TWO_COLORS))
+
+
+def test_order_defaults_to_none() -> None:
+    """A Palette constructed without an order carries order None."""
+    palette = from_hex_list(TWO_COLORS)
+    assert palette.order is None
+
+
+def test_order_accepts_a_permutation() -> None:
+    """A valid permutation is stored as given."""
+    palette = Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32), order=[1, 0])
+    assert palette.order == [1, 0]
+
+
+@pytest.mark.parametrize(
+    ("order", "pattern"),
+    [
+        ([0, 0], r"index 0 is repeated"),
+        ([0, 2], r"index 2 is outside"),
+        ([0], r"missing index 1"),
+    ],
+)
+def test_non_permutation_order_names_the_offending_index(order: list[int], pattern: str) -> None:
+    """A non-permutation order raises ValueError naming the offending index."""
+    with pytest.raises(ValueError, match=pattern):
+        Palette(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32), order=order)
+
+
+def test_palette_rejects_a_wrong_shape() -> None:
+    """A palette must be a (K, 3) array of colours."""
+    with pytest.raises(ValueError, match="K, 3"):
+        Palette(np.zeros((2, 4), dtype=np.float32))
+
+
+def test_palette_rejects_a_bad_colour_count() -> None:
+    """Palettes hold between MIN_COLORS and MAX_COLORS colours."""
+    with pytest.raises(ValueError, match=str(MIN_COLORS)):
+        Palette(np.zeros((1, 3), dtype=np.float32))
+    with pytest.raises(ValueError, match="257"):
+        Palette(np.zeros((MAX_COLORS + 1, 3), dtype=np.float32))
+
+
+def test_palette_is_usable_where_a_plain_ndarray_is_expected() -> None:
+    """Palette stays a drop-in for the (K, 3) arrays the pipeline uses."""
+    palette = from_hex_list(TWO_COLORS)
+    image = np.full((4, 4, 3), 0.25, dtype=np.float32)
+    assert np.array_equal(
+        color.nearest_index(image, palette),
+        color.nearest_index(image, np.asarray(palette)),
+    )
+    assert color.apply_palette(np.zeros((2, 2), dtype=np.int32), palette).shape == (2, 2, 3)
+
+
+def test_load_dispatches_on_the_extension(tmp_path: Path) -> None:
+    """load() routes .png to the image importer and .gpl/.hex to the library loader."""
+    png = tmp_path / "pair.png"
+    image = PILImage.new("RGB", (2, 1), (0, 0, 0))
+    image.putpixel((1, 0), (255, 255, 255))
+    image.save(png)
+    gpl = tmp_path / "pair.gpl"
+    gpl.write_text(
+        "GIMP Palette\nName: pair\n#\n0 0 0\tBlack\n255 255 255\tWhite\n",
+        encoding="utf-8",
+    )
+    assert np.array_equal(load(png), from_hex_list(TWO_COLORS))
+    assert np.array_equal(load(gpl), from_hex_list(TWO_COLORS))
+
+
+def test_palette_module_has_no_network_imports() -> None:
+    """palette.py must not import urllib, requests or socket."""
+    module = Path(__file__).resolve().parent.parent / "lattice_core" / "palette.py"
+    text = module.read_text(encoding="utf-8")
+    for banned in ("urllib", "requests", "socket"):
+        assert banned not in text


CODER NOTES AND DEVIATIONS (L3, attempt 1, deepseek-v4-flash-0731)
- `lattice_core/color.py` et `tests/test_color.py` existaient déjà (portés par L1 avec toutes
  les métriques 1.1) — non réécrits, déjà verts. Livrables réels : `lattice_core/palette.py`
  (nouveau) + `tests/test_palette.py` (17 tests).
- Palette = sous-classe de np.ndarray (drop-in (K,3)) : lum_min/lum_max calculés une fois à la
  construction en lumière linéaire (BT.709 sur srgb_to_linear) ; order = permutation validée ou
  None (ValueError nommant l'index fautif : hors bornes, répété, manquant) ; importeurs
  from_hex_list / from_hex_text (Lospec) / from_gpl / from_png (couleurs distinctes, première
  apparition, alpha composé sur blanc) + load() par extension. Aucun import réseau.
- E1 : from_png impose 2..256 couleurs distinctes (cohérent avec io.MIN_COLORS/MAX_COLORS) ;
  ordre PNG = première apparition (déterministe).
- Aucun import d'application, aucun réseau, sortie srgb inchangée (les tests 1.1 passent).
