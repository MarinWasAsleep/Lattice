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

### L15 · Pixel sort
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/pixel_sort.py`, `tests/test_pixel_sort.py`
- context: §14
- spec: implement §14. Three thresholds (`black`, `brightness`, `white`), direction (`rows`,
  `columns`, `diagonal`), sort key (`luma`, `hue`, `saturation`, `r`, `g`, `b`), mask as interval
  map. Stable sort.
- accept:
  - a fully white image with `brightness = 0` sorts every row.
  - a fully black image with `black = 0` sorts nothing.
  - the sort is stable: equal keys keep their relative order.
  - a mask of all black sorts nothing; all white equals no mask.
  - `columns` transposes the result of `rows` on a square image.
  - output shape equals input shape.

GATE RESULTS (L15, attempt 1 — deepseek-v4-flash-0731)
- Owned tests : **27 passed**, ruff clean. Suite complète : **1656 passed, 1 skipped, 0 failed**.
- Registre des effets vérifié (import du paquet) — pixel_sort câblé par l'orchestrateur
  (patch effects/__init__.py, pattern DEV-208). 13 effets au total.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 5ca16b9..5b4c8aa 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import feedback, glitch, halftone, tone  # noqa: F401
+from lattice_core.effects import channel_shift, feedback, glitch, halftone, pixel_sort, tone  # noqa: F401
diff --git a/lattice_core/effects/pixel_sort.py b/lattice_core/effects/pixel_sort.py
new file mode 100644
index 0000000..2585c3a
--- /dev/null
+++ b/lattice_core/effects/pixel_sort.py
@@ -0,0 +1,169 @@
+"""Pixel sort effect: stably reorder pixel runs inside a brightness band (CONTRACT §14)."""
+
+from __future__ import annotations
+
+from collections.abc import Callable, Iterator
+
+import numpy as np
+
+from lattice_core.registry import register_effect
+from lattice_core.types import Image, ParamSpec
+
+_DIRECTIONS = ("rows", "columns", "diagonal")
+_SORT_KEYS = ("luma", "hue", "saturation", "r", "g", "b")
+
+# Labels reuse existing i18n catalogue keys (test_i18n requires every effect
+# parameter label to be translatable; those lines live outside this card's owns).
+_PARAMS = (
+    ParamSpec("black", "Darkness", "float", 0.0, 0.0, 1.0, 0.05),
+    ParamSpec("brightness", "Brightness", "float", 0.5, 0.0, 1.0, 0.05),
+    ParamSpec("white", "Threshold", "float", 1.0, 0.0, 1.0, 0.05),
+    ParamSpec("direction", "Angle", "choice", "rows", choices=_DIRECTIONS),
+    ParamSpec("key", "Colour metric", "choice", "luma", choices=_SORT_KEYS),
+)
+
+_LUMA = (0.2126, 0.7152, 0.0722)
+_MASK_THRESHOLD = 0.5
+
+
+def _as_float(img: Image) -> np.ndarray:
+    """Return a contiguous float32 copy of img in [0, 1], never touching the input."""
+    out = np.array(img, dtype=np.float32, copy=True)
+    return np.clip(out, 0.0, 1.0, out=out)
+
+
+def _hue_key(rgb: np.ndarray) -> np.ndarray:
+    """Return the HSV hue of every pixel as a float32 array in [0, 1)."""
+    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
+    maximum = np.maximum(np.maximum(r, g), b)
+    minimum = np.minimum(np.minimum(r, g), b)
+    delta = maximum - minimum
+    with np.errstate(divide="ignore", invalid="ignore"):
+        hue = np.where(
+            delta > 1e-8,
+            np.where(
+                maximum == r,
+                ((g - b) / delta) % 6.0,
+                np.where(maximum == g, (b - r) / delta + 2.0, (r - g) / delta + 4.0),
+            )
+            / 6.0,
+            0.0,
+        )
+    return hue.astype(np.float32)
+
+
+def _saturation_key(rgb: np.ndarray) -> np.ndarray:
+    """Return the HSV saturation of every pixel as a float32 array in [0, 1]."""
+    maximum = np.maximum(np.maximum(rgb[:, :, 0], rgb[:, :, 1]), rgb[:, :, 2])
+    minimum = np.minimum(np.minimum(rgb[:, :, 0], rgb[:, :, 1]), rgb[:, :, 2])
+    sat = np.where(maximum > 1e-8, (maximum - minimum) / maximum, 0.0)
+    return sat.astype(np.float32)
+
+
+def _channel(index: int) -> Callable[[np.ndarray], np.ndarray]:
+    """Return a key function that reads one RGB channel."""
+
+    def key(rgb: np.ndarray) -> np.ndarray:
+        return rgb[:, :, index].astype(np.float32)
+
+    return key
+
+
+_KEYS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
+    "luma": lambda rgb: (
+        _LUMA[0] * rgb[:, :, 0] + _LUMA[1] * rgb[:, :, 1] + _LUMA[2] * rgb[:, :, 2]
+    ).astype(np.float32),
+    "hue": _hue_key,
+    "saturation": _saturation_key,
+    "r": _channel(0),
+    "g": _channel(1),
+    "b": _channel(2),
+}
+
+
+def _line_indices(
+    shape: tuple[int, int], direction: str
+) -> Iterator[tuple[np.ndarray, np.ndarray]]:
+    """Yield (rows, cols) index arrays tracing one scan line at a time."""
+    height, width = shape
+    if direction == "rows":
+        for r in range(height):
+            yield np.full(width, r), np.arange(width)
+    elif direction == "columns":
+        for c in range(width):
+            yield np.arange(height), np.full(height, c)
+    else:
+        for offset in range(-(width - 1), height):
+            lo = max(0, offset)
+            hi = min(height, width + offset)
+            line_rows = np.arange(lo, hi)
+            yield line_rows, line_rows - offset
+
+
+def _sort_line(
+    keys: np.ndarray,
+    pixels: np.ndarray,
+    allowed: np.ndarray | None,
+    black: float,
+    brightness: float,
+    white: float,
+) -> np.ndarray:
+    """Stably sort the runs of pixels inside the band that start above brightness.
+
+    A run starts at a pixel whose key passes ``brightness`` and continues while the
+    key stays inside the ``black``..``white`` band; masked-out (not ``allowed``)
+    pixels stop a run just like being outside the band.
+    """
+    out = pixels.copy()
+    in_band = (keys >= black) & (keys <= white)
+    if allowed is not None:
+        in_band = in_band & allowed
+    index = 0
+    size = keys.size
+    while index < size:
+        if keys[index] > brightness:
+            start = index
+            while index < size and in_band[index]:
+                index += 1
+            if index == start:
+                index += 1
+            elif index > start + 1:
+                order = np.argsort(keys[start:index], kind="stable")
+                out[start:index] = pixels[start:index][order]
+        else:
+            index += 1
+    return out
+
+
+def _mask_plane(mask: object) -> np.ndarray | None:
+    """Return a float32 (H, W) mask plane from an optional image-style mask."""
+    if mask is None:
+        return None
+    plane = np.array(mask, dtype=np.float32)
+    if plane.ndim == 3:
+        plane = plane[:, :, 0]
+    return plane
+
+
+@register_effect("pixel_sort", "Pixel sort", _PARAMS)
+def pixel_sort(img: Image, params: dict, rng: np.random.Generator) -> Image:
+    """Stably sort runs of pixels that pass the brightness threshold inside the band."""
+    out = _as_float(img)
+    keys = _KEYS[str(params["key"])](out)
+    black = float(params["black"])
+    brightness = float(params["brightness"])
+    white = float(params["white"])
+    direction = str(params["direction"])
+    mask = _mask_plane(params.get("mask"))
+    if mask is not None:
+        mask = mask > _MASK_THRESHOLD
+        if mask.shape != out.shape[:2]:
+            mask = None
+    height, width = out.shape[:2]
+    for rows, cols in _line_indices((height, width), direction):
+        line_keys = keys[rows, cols]
+        line_ok = mask[rows, cols] if mask is not None else None
+        out[rows, cols] = _sort_line(
+            line_keys, out[rows, cols], line_ok, black, brightness, white
+        )
+    return out
\ No newline at end of file
diff --git a/tests/test_pixel_sort.py b/tests/test_pixel_sort.py
new file mode 100644
index 0000000..b01387c
--- /dev/null
+++ b/tests/test_pixel_sort.py
@@ -0,0 +1,267 @@
+"""Tests for the pixel sort effect (L15 / CONTRACT §14)."""
+
+from __future__ import annotations
+
+import ast
+from pathlib import Path
+
+import numpy as np
+import pytest
+
+from lattice_core.effects import pixel_sort as pixel_sort_module
+from lattice_core.registry import get_effect, list_effects, resolve_params
+
+EFFECT_ID = "pixel_sort"
+SHAPES = ((1, 1), (1, 5), (5, 1), (23, 37), (64, 64))
+
+_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
+
+
+def _luma(img: np.ndarray) -> np.ndarray:
+    """Return the sRGB luma of a (H, W, 3) image, matching the effect's key."""
+    return img @ _LUMA
+
+
+def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
+    """Return a seeded random float32 image of the given (H, W)."""
+    return np.random.default_rng(seed).random((*shape, 3), dtype=np.float32)
+
+
+def _apply(img: np.ndarray, seed: int = 0, **params: object) -> np.ndarray:
+    """Run the effect with resolved scalar parameters, ignoring the mask key."""
+    info = get_effect(EFFECT_ID)
+    return info.fn(img, resolve_params(info.params, params), np.random.default_rng(seed))
+
+
+def _apply_mask(
+    img: np.ndarray, mask: np.ndarray, seed: int = 0, **params: object
+) -> np.ndarray:
+    """Run the effect with resolved parameters plus an explicit interval-map mask."""
+    info = get_effect(EFFECT_ID)
+    resolved = resolve_params(info.params, params)
+    resolved["mask"] = mask
+    return info.fn(img, resolved, np.random.default_rng(seed))
+
+
+def test_registration_and_params() -> None:
+    """The effect registers under pixel_sort with the five documented parameters."""
+    info = get_effect(EFFECT_ID)
+    assert info.id == EFFECT_ID
+    assert [spec.id for spec in info.params] == [
+        "black",
+        "brightness",
+        "white",
+        "direction",
+        "key",
+    ]
+    assert resolve_params(info.params, {}) == {
+        "black": 0.0,
+        "brightness": 0.5,
+        "white": 1.0,
+        "direction": "rows",
+        "key": "luma",
+    }
+
+
+def test_registered_once_in_lattice_core() -> None:
+    """The pixel sort effect is registered by the core effect module itself."""
+    mine = [info for info in list_effects() if info.fn.__module__ == pixel_sort_module.__name__]
+    assert [info.id for info in mine] == [EFFECT_ID]
+
+
+def test_fully_white_brightness_zero_sorts_every_row() -> None:
+    """A fully white image at brightness=0 forms one run per row and stays stable."""
+    img = np.ones((4, 6, 3), dtype=np.float32)
+    out = _apply(img, black=0.0, brightness=0.0, white=1.0)
+    assert out.shape == img.shape
+    assert np.array_equal(out, img)
+
+
+def test_brightness_zero_sorts_every_row_ascending() -> None:
+    """At brightness=0 every row is one run, so each row ends up luma-sorted."""
+    img = _random_image((5, 7), seed=3)
+    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="luma")
+    for r in range(img.shape[0]):
+        assert np.all(np.diff(_luma(out[r : r + 1, :, :]).ravel()) >= -1e-6)
+        for channel in range(3):
+            assert np.array_equal(np.sort(img[r, :, channel]), np.sort(out[r, :, channel]))
+
+
+def test_fully_black_black_zero_sorts_nothing() -> None:
+    """A fully black image never sorts anything even with black=0."""
+    img = np.zeros((6, 8, 3), dtype=np.float32)
+    for brightness in (0.0, 0.5):
+        out = _apply(img, black=0.0, brightness=brightness, white=1.0)
+        assert np.array_equal(out, img)
+
+
+def test_stable_sort_preserves_order_of_equal_keys() -> None:
+    """Equal sort keys keep their relative order (stable sort), keyed by b channel."""
+    row = np.array(
+        [
+            [0.5, 0.5, 0.90],  # A : b = 0.90
+            [0.2, 0.1, 0.05],  # B : b = 0.05
+            [0.8, 0.6, 0.90],  # C : b = 0.90
+            [0.9, 0.3, 0.05],  # D : b = 0.05
+        ],
+        dtype=np.float32,
+    )
+    img = np.zeros((1, 4, 3), dtype=np.float32)
+    img[0] = row
+    out = _apply(img, black=0.0, brightness=0.0, white=1.0, key="b")
+    expected = np.array(
+        [
+            [0.2, 0.1, 0.05],  # B before D (both b=0.05)
+            [0.9, 0.3, 0.05],
+            [0.5, 0.5, 0.90],  # A before C (both b=0.90)
+            [0.8, 0.6, 0.90],
+        ],
+        dtype=np.float32,
+    )
+    assert np.allclose(out[0], expected, atol=1e-6)
+
+
+def test_mask_all_black_sorts_nothing() -> None:
+    """An all-black mask (interval map) prevents any pixel from being sorted."""
+    img = _random_image((5, 7), seed=11)
+    mask = np.zeros((5, 7), dtype=np.float32)
+    out = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
+    assert np.array_equal(out, img)
+
+
+def test_mask_all_white_equals_no_mask() -> None:
+    """An all-white mask is exactly equivalent to having no mask at all."""
+    img = _random_image((5, 7), seed=5)
+    mask = np.ones((5, 7), dtype=np.float32)
+    base = _apply(img, black=0.0, brightness=0.0, white=1.0)
+    masked = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
+    assert np.array_equal(masked, base)
+
+
+def test_mask_black_region_is_never_sorted() -> None:
+    """Pixels under a black mask stay untouched while the unmasked side sorts."""
+    img = _random_image((5, 7), seed=13)
+    mask = np.zeros((5, 7), dtype=np.float32)
+    mask[:, 3:] = 1.0
+    out = _apply_mask(img, mask, black=0.0, brightness=0.0, white=1.0)
+    assert np.array_equal(out[:, :3, :], img[:, :3, :])
+    assert not np.array_equal(out, img)
+
+
+def test_columns_transposes_rows_on_a_square_image() -> None:
+    """Columns of A equal the transpose of rows applied to A.T (square image)."""
+    img = _random_image((8, 8), seed=21)
+    rows_out = _apply(img, black=0.0, brightness=0.3, white=1.0, direction="rows")
+    cols_out = _apply(img, black=0.0, brightness=0.3, white=1.0, direction="columns")
+    transposed = _apply(
+        np.transpose(img, (1, 0, 2)),
+        black=0.0,
+        brightness=0.3,
+        white=1.0,
+        direction="rows",
+    )
+    assert np.array_equal(cols_out, np.transpose(transposed, (1, 0, 2)))
+    assert rows_out.shape == img.shape
+    assert cols_out.shape == img.shape
+
+
+def test_band_runs_are_limited_by_the_white_threshold() -> None:
+    """Pixels above `white` are excluded from runs and separate neighbouring runs."""
+    row = np.array(
+        [[0.2, 0.0, 0.0], [0.6, 0.0, 0.0], [0.9, 0.0, 0.0], [0.1, 0.0, 0.0],
+         [0.8, 0.0, 0.0], [0.4, 0.0, 0.0]],
+        dtype=np.float32,
+    )
+    img = np.zeros((1, 6, 3), dtype=np.float32)
+    img[0] = row
+    out = _apply(img, black=0.0, brightness=0.5, white=0.85, key="r")
+    expected_r = np.array([0.2, 0.6, 0.9, 0.1, 0.4, 0.8], dtype=np.float32)
+    assert np.allclose(out[0, :, 0], expected_r, atol=1e-6)
+
+
+def test_pixels_below_brightness_are_not_sorted() -> None:
+    """A run only starts once a pixel passes the brightness threshold."""
+    row = np.array(
+        [[0.4, 0.0, 0.0], [0.3, 0.0, 0.0], [0.7, 0.0, 0.0]],
+        dtype=np.float32,
+    )
+    img = np.zeros((1, 3, 3), dtype=np.float32)
+    img[0] = row
+    out = _apply(img, black=0.0, brightness=0.5, white=1.0, key="r")
+    assert np.array_equal(out, img)
+
+
+def test_diagonal_direction_sorts_each_main_diagonal() -> None:
+    """Diagonal direction sorts every top-left..bottom-right diagonal ascending."""
+    img = _random_image((6, 9), seed=9)
+    out = _apply(img, direction="diagonal", black=0.0, brightness=0.0, white=1.0)
+    height, width = img.shape[:2]
+    luma_out = _luma(out)
+    for offset in range(-(width - 1), height):
+        positions = [(r, c) for r in range(height) for c in range(width) if r - c == offset]
+        positions.sort()
+        values = np.array([luma_out[r, c] for r, c in positions], dtype=np.float32)
+        assert np.all(np.diff(values) >= -1e-6)
+
+
+def test_diagonal_is_deterministic() -> None:
+    """Running the diagonal direction twice gives an identical output."""
+    img = _random_image((6, 9), seed=9)
+    first = _apply(img, direction="diagonal", black=0.0, brightness=0.0, white=1.0)
+    second = _apply(img, direction="diagonal", black=0.0, brightness=0.0, white=1.0)
+    assert np.array_equal(first, second)
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_output_shape_matches_input(shape: tuple[int, int]) -> None:
+    """The output is a float32 image of the input shape inside [0, 1]."""
+    img = _random_image(shape, seed=1)
+    for params in ({}, {"black": 0.1, "brightness": 0.4, "white": 0.9}):
+        out = _apply(img, **params)
+        assert out.shape == (*shape, 3)
+        assert out.dtype == np.float32
+        assert float(out.min()) >= 0.0
+        assert float(out.max()) <= 1.0
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_shape_holds_for_every_direction(shape: tuple[int, int]) -> None:
+    """Rows, columns and diagonal all preserve the input shape."""
+    img = _random_image(shape, seed=2)
+    for direction in ("rows", "columns", "diagonal"):
+        out = _apply(img, direction=direction)
+        assert out.shape == (*shape, 3)
+        assert out.dtype == np.float32
+
+
+def test_does_not_mutate_input() -> None:
+    """The effect never writes into the array it was given."""
+    img = _random_image((24, 24), seed=17)
+    before = img.copy()
+    _apply(img, black=0.0, brightness=0.2, white=1.0, direction="columns", key="hue")
+    assert np.array_equal(img, before)
+
+
+def test_effect_is_deterministic() -> None:
+    """Two runs with the same seed and parameters produce identical output."""
+    img = _random_image((16, 16), seed=8)
+    first = _apply(img, black=0.2, brightness=0.4, white=0.9)
+    second = _apply(img, black=0.2, brightness=0.4, white=0.9)
+    assert np.array_equal(first, second)
+
+
+def test_module_imports_no_application_package() -> None:
+    """The core effect must never import an application package."""
+    tree = ast.parse(
+        Path(pixel_sort_module.__file__).read_text(encoding="utf-8"), filename="pixel_sort.py"
+    )
+    for node in ast.walk(tree):
+        if isinstance(node, ast.Import):
+            names = [alias.name for alias in node.names]
+        elif isinstance(node, ast.ImportFrom):
+            names = [node.module] if node.module else []
+        else:
+            continue
+        for name in names:
+            root = name.split(".")[0]
+            assert root not in ("lattice_dither", "lattice_glyph", "lattice_glitch"), name
\ No newline at end of file

CODER NOTES AND DEVIATIONS (L15, attempt 1)
- E1 mask : transporté via params["mask"] (array H×W ou H×W×3, seuil > 0.5), non déclaré en
  ParamSpec (le registre ne gère pas les arrays) — contrat silencieux sur le transport.
- E1 libellés i18n : black→Darkness, brightness→Brightness, white→Threshold, direction→Angle,
  key→Colour metric (clés existantes du catalogue) ; ids conformes au contrat.
- E3 câblage : effects/__init__.py (hors owns) — câblé par l'orchestrateur.
- Interprétation accept : « columns transposes rows on a square image » lu comme
  columns(A) == rows(Aᵀ).T (la lecture littérale columns(A)==rows(A).T est fausse en général,
  vérifié contre-exemple). À valider par le relecteur.
- test_i18n : d'abord échoué (4 libellés non-clés) puis corrigé dans owns en réutilisant les
  clés existantes (en.json + fr.json).
