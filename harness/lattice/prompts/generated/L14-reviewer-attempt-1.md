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

### L14 · Displacement
- wave: 2 · deps: L13 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/displace.py`, `tests/test_displace.py`
- context: §13
- spec: implement §13. Map source: still, sequence, noise field, or the feedback buffer. Modes:
  `luma`, `r`, `g`, `b`, `hue`. `dst(x, y) = src(x + k*(mapR-0.5), y + k*(mapG-0.5))`.
  `iterations` repeats with decay. `mask` restricts spatially. Bilinear sampling, clamped edges.
- accept:
  - a flat grey map leaves the image unchanged.
  - a horizontal ramp map shifts pixels by exactly `k/2` at the extremes.
  - `iterations = 3` produces a visibly longer smear than `iterations = 1` (measured by edge
    spread).
  - a mask of all zeros leaves the image unchanged; all ones equals no mask.
  - output shape equals input shape for every mode.

GATE RESULTS (L14, attempt 1 — deepseek-v4-1-flash-1017)
- Owned tests : **80 passed** (29 fonctions), ruff clean + ruff format --check clean,
  check_contract OK. Suite complète : **1759 passed, 1 skipped**.
- Registre des effets vérifié (import du paquet) — displace câblé par l'orchestrateur (DEV-208).
  15 effets au total.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 5b4c8aa..4d1f956 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import channel_shift, feedback, glitch, halftone, pixel_sort, tone  # noqa: F401
+from lattice_core.effects import channel_shift, displace, feedback, glitch, halftone, ntsc, pixel_sort, tone  # noqa: F401
diff --git a/lattice_core/effects/displace.py b/lattice_core/effects/displace.py
new file mode 100644
index 0000000..257f006
--- /dev/null
+++ b/lattice_core/effects/displace.py
@@ -0,0 +1,229 @@
+"""Displacement effect (CONTRACT §13).
+
+``dst(x, y) = src(x + k * (mapR - 0.5), y + k * (mapG - 0.5))``. The map is an
+RGB image: its red channel is ``mapR`` and drives the horizontal shift, its green
+channel is ``mapG`` and drives the vertical one. ``mode`` picks which field of the
+map supplies ``mapR`` — ``r`` reproduces the formula verbatim, ``luma``/``hue``/
+``g``/``b`` read the fields the rest of the suite reads. A greyscale map is
+promoted to R = G = B, so it drives both axes with the same value.
+
+The map is the source image, a seeded noise field, or an array the caller passes
+(a sequence frame, a feedback-buffer snapshot, a painted flow map). Sampling is
+bilinear and the edges clamp. ``iterations`` applies the shift again to its own
+output and averages the passes with a decaying weight, which smears the image
+without a feedback loop. ``mask`` (§18) blends the result back over the source:
+0 keeps the source, 1 keeps the effect.
+"""
+
+from __future__ import annotations
+
+import numpy as np
+
+from lattice_core.registry import register_effect
+from lattice_core.types import Image, ParamSpec
+
+_MODES: tuple[str, ...] = ("luma", "r", "g", "b", "hue")
+# §13's four map sources. `sequence` and `feedback` are both "an array the caller
+# passes" — core cannot tell a sequence frame from a feedback snapshot — so the
+# three non-noise sources all read the same map_img argument (E1).
+_MAP_SOURCES: tuple[str, ...] = ("image", "sequence", "noise", "feedback")
+_CHANNEL_INDEX: dict[str, int] = {"r": 0, "g": 1, "b": 2}
+# sRGB luma, summed in float64 so every neutral grey reads back as that exact grey.
+_LUMA_WEIGHTS: tuple[float, float, float] = (0.2126, 0.7152, 0.0722)
+_NEUTRAL = np.float32(0.5)
+_MAX_DECAY = 0.99
+_MAX_ITERATIONS = 8
+
+# Labels are keys of the frozen i18n catalogue (lattice_dither/i18n/en.json),
+# which is outside this card's owns; no catalogue entry may be added here.
+_PARAMS = (
+    ParamSpec("amount", "Amount (px)", "float", 8.0, 0.0, 64.0, 0.5),
+    ParamSpec("mode", "Per channel", "choice", "luma", choices=_MODES),
+    ParamSpec("map_source", "Source", "choice", "image", choices=_MAP_SOURCES),
+    ParamSpec("iterations", "Iterations", "int", 1, 1, _MAX_ITERATIONS, 1),
+    ParamSpec("decay", "Strength", "float", 0.5, 0.0, _MAX_DECAY, 0.01),
+)
+
+
+def _as_rgb(img: Image) -> np.ndarray:
+    """Return img as a float32 (H, W, 3) array, promoting a greyscale plane to R = G = B."""
+    data = np.asarray(img, dtype=np.float32)
+    if data.ndim == 2:
+        return np.repeat(data[:, :, None], 3, axis=2)
+    if data.ndim != 3 or data.shape[2] != 3:
+        raise ValueError(f"displacement needs an (H, W, 3) image, got shape {data.shape}")
+    return data
+
+
+def _luma(rgb: np.ndarray) -> np.ndarray:
+    """Return the sRGB luma of every pixel as float32, exact on every neutral grey."""
+    total = rgb[:, :, 0].astype(np.float64) * _LUMA_WEIGHTS[0]
+    total += rgb[:, :, 1].astype(np.float64) * _LUMA_WEIGHTS[1]
+    total += rgb[:, :, 2].astype(np.float64) * _LUMA_WEIGHTS[2]
+    return total.astype(np.float32)
+
+
+def _hue(rgb: np.ndarray) -> np.ndarray:
+    """Return the hue of every pixel in [0, 1]; a neutral pixel reads exactly 0.5."""
+    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
+    high = np.maximum(np.maximum(red, green), blue)
+    low = np.minimum(np.minimum(red, green), blue)
+    delta = high - low
+    chroma = delta > 0.0
+    safe = np.where(chroma, delta, np.float32(1.0))
+    red_max = chroma & (high == red)
+    green_max = chroma & (high == green) & ~red_max
+    turn = np.where(
+        red_max,
+        ((green - blue) / safe) % np.float32(6.0),
+        np.where(
+            green_max,
+            (blue - red) / safe + np.float32(2.0),
+            (red - green) / safe + np.float32(4.0),
+        ),
+    )
+    hue = np.where(chroma, turn / np.float32(6.0), _NEUTRAL)
+    return np.clip(hue, 0.0, 1.0).astype(np.float32)
+
+
+def _field(map_rgb: np.ndarray, mode: str) -> np.ndarray:
+    """Return the (H, W) float32 field that `mode` reads from an RGB map."""
+    if mode == "luma":
+        return _luma(map_rgb)
+    if mode == "hue":
+        return _hue(map_rgb)
+    return np.ascontiguousarray(map_rgb[:, :, _CHANNEL_INDEX[mode]])
+
+
+def _map_rgb(
+    img_rgb: np.ndarray,
+    params: dict,
+    rng: np.random.Generator,
+    map_img: Image | None,
+) -> np.ndarray:
+    """Return the RGB map the drivers are read from, per the selected map source."""
+    source = str(params.get("map_source", "image"))
+    if source not in _MAP_SOURCES:
+        raise ValueError(f"unknown displacement map source: {source!r}")
+    if source == "image":
+        return img_rgb
+    if source == "noise":
+        return rng.random(img_rgb.shape, dtype=np.float32)
+    if map_img is None:
+        raise ValueError(f"map_source {source!r} needs a map image")
+    mapped = _as_rgb(map_img)
+    if mapped.shape[:2] != img_rgb.shape[:2]:
+        raise ValueError(f"map must be {img_rgb.shape[:2]}, got {mapped.shape[:2]}")
+    return mapped
+
+
+def _sample_coordinates(
+    map_r: np.ndarray, map_g: np.ndarray, amount: float
+) -> tuple[np.ndarray, np.ndarray]:
+    """Return the float32 x and y source coordinates of dst(x, y)."""
+    height, width = map_r.shape
+    xs = np.arange(width, dtype=np.float32)[None, :]
+    ys = np.arange(height, dtype=np.float32)[:, None]
+    scale = np.float32(amount)
+    return xs + (map_r - _NEUTRAL) * scale, ys + (map_g - _NEUTRAL) * scale
+
+
+def _is_identity(sx: np.ndarray, sy: np.ndarray) -> bool:
+    """Return True when the sample coordinates are exactly the source pixel grid."""
+    height, width = sx.shape
+    xs = np.arange(width, dtype=np.float32)[None, :]
+    ys = np.arange(height, dtype=np.float32)[:, None]
+    return bool(np.array_equal(sx, np.broadcast_to(xs, sx.shape))) and bool(
+        np.array_equal(sy, np.broadcast_to(ys, sy.shape))
+    )
+
+
+def _bilinear(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
+    """Bilinearly sample a 2-D channel at float coordinates, clamping to the edges."""
+    height, width = channel.shape
+    x = np.clip(sx, 0.0, np.float32(width - 1))
+    y = np.clip(sy, 0.0, np.float32(height - 1))
+    x0 = np.floor(x).astype(np.intp)
+    y0 = np.floor(y).astype(np.intp)
+    fx = (x - x0).astype(np.float32)
+    fy = (y - y0).astype(np.float32)
+    x1 = np.minimum(x0 + 1, width - 1)
+    y1 = np.minimum(y0 + 1, height - 1)
+    one = np.float32(1.0)
+    top = channel[y0, x0] * (one - fx) + channel[y0, x1] * fx
+    bottom = channel[y1, x0] * (one - fx) + channel[y1, x1] * fx
+    return top * (one - fy) + bottom * fy
+
+
+def _displace_once(source: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
+    """Return one displacement of every channel of source to the given coordinates."""
+    out = np.empty(source.shape, dtype=np.float32)
+    for channel in range(source.shape[2]):
+        out[:, :, channel] = _bilinear(source[:, :, channel], sx, sy)
+    return out
+
+
+def _smear(
+    source: np.ndarray, sx: np.ndarray, sy: np.ndarray, iterations: int, decay: float
+) -> np.ndarray:
+    """Average the displacement applied 1..iterations times, weighting step i by decay**i."""
+    current = _displace_once(source, sx, sy)
+    if iterations <= 1:
+        return current
+    accumulated = current.copy()
+    weight = np.float32(1.0)
+    total = np.float32(1.0)
+    for _ in range(1, iterations):
+        current = _displace_once(current, sx, sy)
+        weight *= np.float32(decay)
+        accumulated += weight * current
+        total += weight
+    return accumulated / total
+
+
+def _mask_weights(mask: object, shape: tuple[int, int]) -> np.ndarray:
+    """Return the (H, W) float32 mask weights, validating the size and clipping to [0, 1]."""
+    data = np.asarray(mask, dtype=np.float32)
+    if data.ndim == 3 and data.shape[2] == 1:
+        data = data[:, :, 0]
+    if data.ndim != 2 or data.shape != shape:
+        raise ValueError(f"mask must be {shape}, got {data.shape}")
+    return np.clip(data, 0.0, 1.0)
+
+
+def _apply_mask(source: np.ndarray, displaced: np.ndarray, weights: np.ndarray) -> np.ndarray:
+    """Blend displaced over source by the mask: 0 keeps the source, 1 keeps the effect."""
+    weight = weights[:, :, None]
+    one = np.float32(1.0)
+    return (one - weight) * source + weight * displaced
+
+
+@register_effect("displace", "Displacement", _PARAMS)
+def displace(
+    img: Image,
+    params: dict,
+    rng: np.random.Generator,
+    *,
+    mask: Image | None = None,
+    map_img: Image | None = None,
+) -> Image:
+    """Displace the image by a map field, with decayed iterations and an optional mask."""
+    source = np.asarray(img, dtype=np.float32)
+    greyscale_input = source.ndim == 2
+    rgb = _as_rgb(source)
+    mode = str(params.get("mode", "luma"))
+    if mode not in _MODES:
+        raise ValueError(f"unknown displacement mode: {mode!r}")
+    amount = float(params.get("amount", 8.0))
+    iterations = max(1, min(int(params.get("iterations", 1)), _MAX_ITERATIONS))
+    decay = float(np.clip(float(params.get("decay", 0.5)), 0.0, _MAX_DECAY))
+    map_rgb = _map_rgb(rgb, params, rng, map_img)
+    sx, sy = _sample_coordinates(_field(map_rgb, mode), map_rgb[:, :, 1], amount)
+    if _is_identity(sx, sy):
+        displaced = np.array(rgb, dtype=np.float32, copy=True)
+    else:
+        displaced = _smear(rgb, sx, sy, iterations, decay)
+    if mask is not None:
+        displaced = _apply_mask(rgb, displaced, _mask_weights(mask, sx.shape))
+    out = np.ascontiguousarray(np.clip(displaced, 0.0, 1.0), dtype=np.float32)
+    return out[:, :, 0] if greyscale_input else out
diff --git a/tests/test_displace.py b/tests/test_displace.py
new file mode 100644
index 0000000..920b1bf
--- /dev/null
+++ b/tests/test_displace.py
@@ -0,0 +1,400 @@
+"""Tests for the displacement effect (card L14 / CONTRACT §13)."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+from lattice_core.effects.displace import displace
+from lattice_core.registry import get_effect, resolve_params
+
+EFFECT_ID = "displace"
+MODES = ("luma", "r", "g", "b", "hue")
+SHAPES = ((1, 1), (1, 7), (7, 1), (37, 23), (64, 64))
+SEED = 11
+K = 8.0
+
+
+def _params(**overrides: object) -> dict:
+    """Return a full displacement parameter dict with deterministic test defaults."""
+    params: dict = {
+        "amount": K,
+        "mode": "r",
+        "map_source": "sequence",
+        "iterations": 1,
+        "decay": 0.5,
+    }
+    params.update(overrides)
+    return params
+
+
+def _run(
+    img: np.ndarray,
+    overrides: dict | None = None,
+    seed: int = SEED,
+    **kwargs: object,
+) -> np.ndarray:
+    """Run the effect with a freshly seeded generator and the given overrides."""
+    return displace(img, _params(**(overrides or {})), np.random.default_rng(seed), **kwargs)
+
+
+def _noise_image(shape: tuple[int, int] = (32, 32), seed: int = 7) -> np.ndarray:
+    """Return a deterministic non-constant float32 RGB image."""
+    return np.random.default_rng(seed).random((*shape, 3), dtype=np.float32)
+
+
+def _x_ramp(width: int, height: int) -> np.ndarray:
+    """Return an (H, W) field rising linearly from 0 to 1 across the width."""
+    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
+    return np.repeat(ramp, height, axis=0)
+
+
+def _plateau(width: int, height: int, low: float, high: float) -> np.ndarray:
+    """Return an (H, W) field that is 0 left of low, 1 right of high, linear between."""
+    x = np.arange(width, dtype=np.float32)
+    ramp = np.clip((x - np.float32(low)) / np.float32(high - low), 0.0, 1.0)[None, :]
+    return np.repeat(ramp, height, axis=0)
+
+
+def _x_gradient_image(width: int, height: int) -> np.ndarray:
+    """Return an (H, W, 3) image whose value encodes its own x coordinate."""
+    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
+    return np.ascontiguousarray(np.repeat(np.repeat(ramp, height, axis=0), 3, axis=2))
+
+
+def _y_gradient_image(width: int, height: int) -> np.ndarray:
+    """Return an (H, W, 3) image whose value encodes its own y coordinate."""
+    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
+    return np.ascontiguousarray(np.repeat(np.repeat(ramp, width, axis=1), 3, axis=2))
+
+
+def _edge_image(height: int, width: int, split: int) -> np.ndarray:
+    """Return a black image with a white right half."""
+    img = np.zeros((height, width, 3), dtype=np.float32)
+    img[:, split:, :] = 1.0
+    return img
+
+
+def _edge_spread(img: np.ndarray, row: int) -> int:
+    """Return how many pixels of row are strictly between black and white."""
+    values = img[row, :, 0]
+    return int(np.count_nonzero((values > 0.02) & (values < 0.98)))
+
+
+def test_registration_and_name() -> None:
+    """The effect is registered under the card id with a human name."""
+    info = get_effect(EFFECT_ID)
+    assert info.name == "Displacement"
+    assert info.fn is displace
+
+
+def test_param_specs_cover_the_contract_options() -> None:
+    """The five options carry the ids, kinds, defaults and bounds the card needs."""
+    info = get_effect(EFFECT_ID)
+    actual = tuple((s.id, s.kind, s.default, s.min, s.max) for s in info.params)
+    assert actual == (
+        ("amount", "float", 8.0, 0.0, 64.0),
+        ("mode", "choice", "luma", None, None),
+        ("map_source", "choice", "image", None, None),
+        ("iterations", "int", 1, 1, 8),
+        ("decay", "float", 0.5, 0.0, 0.99),
+    )
+    assert get_effect(EFFECT_ID).params[1].choices == MODES
+    assert get_effect(EFFECT_ID).params[2].choices == ("image", "sequence", "noise", "feedback")
+
+
+def test_resolve_params_fills_defaults_and_clamps() -> None:
+    """Defaults resolve cleanly and every numeric bound clamps."""
+    info = get_effect(EFFECT_ID)
+    assert resolve_params(info.params, {}) == {
+        "amount": 8.0,
+        "mode": "luma",
+        "map_source": "image",
+        "iterations": 1,
+        "decay": 0.5,
+    }
+    clamped = resolve_params(info.params, {"amount": 999.0, "iterations": 99, "decay": 5.0})
+    assert clamped["amount"] == 64.0
+    assert clamped["iterations"] == 8
+    assert clamped["decay"] == 0.99
+    assert resolve_params(info.params, {"amount": -3.0, "iterations": 0})["amount"] == 0.0
+    assert resolve_params(info.params, {"iterations": 0})["iterations"] == 1
+
+
+@pytest.mark.parametrize("mode", MODES)
+@pytest.mark.parametrize("iterations", [1, 2, 3, 8])
+def test_a_flat_grey_map_leaves_the_image_unchanged(mode: str, iterations: int) -> None:
+    """A map of constant 0.5 drives no shift, so the image comes back bit-identical."""
+    img = _noise_image()
+    grey = np.full(img.shape[:2], 0.5, dtype=np.float32)
+    out = _run(img, {"mode": mode, "iterations": iterations}, map_img=grey)
+    assert np.array_equal(out, img)
+
+
+@pytest.mark.parametrize("mode", MODES)
+def test_a_flat_grey_three_channel_map_also_leaves_the_image_unchanged(mode: str) -> None:
+    """A grey RGB map has R = G = B = 0.5, so neither driver moves."""
+    img = _noise_image()
+    grey = np.full((*img.shape[:2], 3), 0.5, dtype=np.float32)
+    out = _run(img, {"mode": mode, "iterations": 3}, map_img=grey)
+    assert np.array_equal(out, img)
+
+
+@pytest.mark.parametrize("mode", MODES)
+def test_a_flat_grey_source_is_its_own_map_and_stays_unchanged(mode: str) -> None:
+    """With the source as map, a grey image has a neutral field on both axes."""
+    img = np.full((16, 16, 3), 0.5, dtype=np.float32)
+    out = _run(img, {"mode": mode, "map_source": "image", "iterations": 3})
+    assert np.array_equal(out, img)
+
+
+def test_a_horizontal_ramp_shifts_by_exactly_half_k_at_the_extremes() -> None:
+    """Where the ramp saturates at 0 and 1 the shift is exactly -k/2 and +k/2."""
+    height, width = 64, 192
+    src = _x_gradient_image(width, height)
+    field = _plateau(width, height, 48.0, 96.0)
+    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
+    half = int(K // 2)
+    for px in (10, 20, 40, 48):
+        assert np.array_equal(out[0, px], src[0, px - half]), px
+    for px in (96, 120, 150):
+        assert np.array_equal(out[0, px], src[0, px + half]), px
+    assert float(out[0, 10, 0]) * (width - 1) - 10 == pytest.approx(-K / 2, abs=1e-4)
+    assert float(out[0, 150, 0]) * (width - 1) - 150 == pytest.approx(K / 2, abs=1e-4)
+
+
+def test_the_shift_follows_the_formula_along_a_linear_ramp() -> None:
+    """On the linear part of the ramp the shift is k * (mapR - 0.5) in pixels."""
+    height, width = 32, 128
+    src = _x_gradient_image(width, height)
+    field = _x_ramp(width, height)
+    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
+    for px in (16, 32, 48, 64, 80, 96):
+        shift = float(out[0, px, 0]) * (width - 1) - px
+        assert shift == pytest.approx(K * (float(field[0, px]) - 0.5), abs=1e-3)
+
+
+def test_the_vertical_driver_is_the_green_channel() -> None:
+    """A neutral red channel with a green ramp shifts vertically and not horizontally."""
+    height, width = 64, 192
+    src = _y_gradient_image(width, height)
+    field = _plateau(width, height, 48.0, 96.0)
+    neutral = np.full((height, width), 0.5, dtype=np.float32)
+    map_rgb = np.stack([neutral, field, neutral], axis=-1)
+    out = _run(src, {"mode": "r", "amount": K}, map_img=map_rgb)
+    half = int(K // 2)
+    assert np.array_equal(out[0, 96], src[half, 96])
+    assert np.array_equal(out[60, 10], src[60 - half, 10])
+    # The red driver is neutral, so an image that varies only along x does not move.
+    # The vertical bilinear pass of a y-constant image is exact up to float32 rounding.
+    x_src = _x_gradient_image(width, height)
+    moved = _run(x_src, {"mode": "r", "amount": K}, map_img=map_rgb)
+    assert np.allclose(moved, x_src, atol=1e-6)
+
+
+def test_hue_mode_reads_the_hue_of_the_map() -> None:
+    """A red map reads hue 0 and shifts by -k/2; a grey map reads 0.5 and does not."""
+    height, width = 32, 128
+    src = _x_gradient_image(width, height)
+    red = np.zeros((height, width, 3), dtype=np.float32)
+    red[:, :, 0] = 1.0
+    shifted = _run(src, {"mode": "hue", "amount": K}, map_img=red)
+    assert np.array_equal(shifted[0, 40], src[0, 40 - int(K // 2)])
+    grey = np.full((height, width), 0.5, dtype=np.float32)
+    assert np.array_equal(_run(src, {"mode": "hue", "amount": K}, map_img=grey), src)
+
+
+def test_every_mode_produces_a_distinct_output() -> None:
+    """The five modes read five different fields, so no two agree on one image."""
+    img = _noise_image((48, 48))
+    outputs = {
+        mode: _run(img, {"mode": mode, "map_source": "image", "iterations": 2}) for mode in MODES
+    }
+    for index, first in enumerate(MODES):
+        for second in MODES[index + 1 :]:
+            assert not np.array_equal(outputs[first], outputs[second]), (first, second)
+
+
+def test_three_iterations_smear_further_than_one() -> None:
+    """Iterations widen the transition of a hard edge: that is the measured smear."""
+    height, width = 64, 192
+    src = _edge_image(height, width, 96)
+    field = _plateau(width, height, 48.0, 96.0)
+    single = _run(src, {"mode": "r", "amount": 24.0, "iterations": 1}, map_img=field)
+    triple = _run(src, {"mode": "r", "amount": 24.0, "iterations": 3}, map_img=field)
+    spread_one = _edge_spread(single, 32)
+    spread_three = _edge_spread(triple, 32)
+    assert spread_three > spread_one
+    assert spread_three >= _edge_spread(
+        _run(src, {"mode": "r", "amount": 24.0, "iterations": 2}, map_img=field), 32
+    )
+
+
+def test_the_smear_grows_with_the_iteration_count() -> None:
+    """Edge spread is non-decreasing in iterations and strictly larger at the card value."""
+    height, width = 64, 192
+    src = _edge_image(height, width, 96)
+    field = _plateau(width, height, 48.0, 96.0)
+    spreads = [
+        _edge_spread(
+            _run(
+                src,
+                {"mode": "r", "amount": 24.0, "iterations": n, "decay": 0.6},
+                map_img=field,
+            ),
+            32,
+        )
+        for n in (1, 2, 3, 4, 8)
+    ]
+    assert spreads == sorted(spreads)
+    assert spreads[2] > spreads[0]
+
+
+def test_decay_zero_keeps_only_the_first_pass() -> None:
+    """With decay 0 every later pass is weighted out, so iterations stop mattering."""
+    img = _noise_image()
+    field = _x_ramp(32, 32)
+    once = _run(img, {"mode": "r", "amount": 6.0, "iterations": 1}, map_img=field)
+    many = _run(img, {"mode": "r", "amount": 6.0, "iterations": 6, "decay": 0.0}, map_img=field)
+    assert np.allclose(once, many, atol=1e-6)
+
+
+def test_a_mask_of_zeros_leaves_the_image_unchanged() -> None:
+    """Mask 0 means no effect anywhere, so the source passes through untouched."""
+    img = _noise_image()
+    mask = np.zeros(img.shape[:2], dtype=np.float32)
+    out = _run(img, {"map_source": "noise", "iterations": 3}, mask=mask)
+    assert np.array_equal(out, img)
+
+
+def test_a_mask_of_ones_equals_no_mask() -> None:
+    """Mask 1 means full effect everywhere, which is exactly the unmasked result."""
+    img = _noise_image()
+    mask = np.ones(img.shape[:2], dtype=np.float32)
+    unmasked = _run(img, {"map_source": "noise", "iterations": 3}, seed=5)
+    masked = _run(img, {"map_source": "noise", "iterations": 3}, seed=5, mask=mask)
+    assert np.array_equal(masked, unmasked)
+
+
+def test_a_half_mask_blends_half_way() -> None:
+    """A uniform 0.5 mask returns the midpoint of the source and the displaced image."""
+    img = _noise_image()
+    mask = np.full(img.shape[:2], 0.5, dtype=np.float32)
+    unmasked = _run(img, {"map_source": "noise", "iterations": 2}, seed=3)
+    masked = _run(img, {"map_source": "noise", "iterations": 2}, seed=3, mask=mask)
+    assert np.allclose(masked, 0.5 * img + 0.5 * unmasked, atol=1e-6)
+
+
+def test_a_mask_of_the_wrong_size_is_rejected() -> None:
+    """A mask that does not match the image is a programming error, not a silent no-op."""
+    img = _noise_image((16, 16))
+    with pytest.raises(ValueError, match="mask must be"):
+        _run(img, {"map_source": "noise"}, mask=np.zeros((8, 8), dtype=np.float32))
+
+
+@pytest.mark.parametrize("mode", MODES)
+@pytest.mark.parametrize("shape", SHAPES)
+def test_output_shape_equals_input_shape_for_every_mode(mode: str, shape: tuple[int, int]) -> None:
+    """Every mode on every shape returns the input shape, float32 and contiguous."""
+    img = np.random.default_rng(1).random((*shape, 3), dtype=np.float32)
+    out = _run(img, {"mode": mode, "map_source": "noise"})
+    assert out.shape == img.shape
+    assert out.dtype == np.float32
+    assert out.flags["C_CONTIGUOUS"]
+    assert np.isfinite(out).all()
+    assert float(out.min()) >= 0.0
+    assert float(out.max()) <= 1.0
+
+
+def test_sampling_is_bilinear_not_nearest() -> None:
+    """A half-pixel shift returns the average of the two neighbours, not one of them."""
+    width, height = 9, 8
+    src = _x_gradient_image(width, height)
+    field = np.full((height, width), 0.625, dtype=np.float32)
+    out = _run(src, {"mode": "r", "amount": 4.0}, map_img=field)
+    midpoint = 0.5 * (src[0, :-1, 0] + src[0, 1:, 0])
+    assert np.allclose(out[0, :-1, 0], midpoint, atol=1e-6)
+    assert not np.array_equal(out[0, :-1, 0], src[0, :-1, 0])
+
+
+def test_edges_clamp() -> None:
+    """Coordinates past the border read the border pixel instead of wrapping."""
+    width, height = 32, 16
+    src = _x_gradient_image(width, height)
+    field = np.ones((height, width), dtype=np.float32)
+    out = _run(src, {"mode": "r", "amount": K}, map_img=field)
+    assert np.array_equal(out[0, -1], src[0, -1])
+    assert np.array_equal(out[0, -2], src[0, -1])
+    assert np.array_equal(out[0, 0], src[0, int(K // 2)])
+
+
+def test_the_noise_source_is_seeded_and_seed_dependent() -> None:
+    """The noise field is drawn from the generator: same seed equal, other seed not."""
+    img = _noise_image()
+    first = _run(img, {"map_source": "noise", "iterations": 2}, seed=4)
+    again = _run(img, {"map_source": "noise", "iterations": 2}, seed=4)
+    other = _run(img, {"map_source": "noise", "iterations": 2}, seed=5)
+    assert np.array_equal(first, again)
+    assert not np.array_equal(first, other)
+
+
+def test_the_sequence_and_feedback_sources_read_the_supplied_map() -> None:
+    """Both external sources consume the same map_img and give the same result."""
+    img = _noise_image()
+    field = _x_ramp(32, 32)
+    sequence = _run(img, {"mode": "r", "map_source": "sequence"}, map_img=field)
+    feedback = _run(img, {"mode": "r", "map_source": "feedback"}, map_img=field)
+    assert np.array_equal(sequence, feedback)
+    assert not np.array_equal(sequence, img)
+
+
+def test_the_image_source_reads_the_source_itself() -> None:
+    """map_source 'image' is the same as passing the source as the map."""
+    img = _noise_image()
+    implicit = _run(img, {"mode": "g", "map_source": "image", "iterations": 2})
+    explicit = _run(img, {"mode": "g", "map_source": "sequence", "iterations": 2}, map_img=img)
+    assert np.array_equal(implicit, explicit)
+
+
+def test_unknown_mode_and_source_are_rejected() -> None:
+    """Unknown enumerations raise ValueError naming the offending value."""
+    img = _noise_image((8, 8))
+    with pytest.raises(ValueError, match="shear"):
+        _run(img, {"mode": "shear", "map_source": "noise"})
+    with pytest.raises(ValueError, match="webcam"):
+        _run(img, {"map_source": "webcam"})
+
+
+def test_a_missing_or_mismatched_map_is_rejected() -> None:
+    """An external source without a map, or with the wrong size, raises ValueError."""
+    img = _noise_image((16, 16))
+    with pytest.raises(ValueError, match="needs a map"):
+        _run(img, {"map_source": "sequence"})
+    with pytest.raises(ValueError, match="map must be"):
+        _run(img, {"map_source": "sequence"}, map_img=np.zeros((8, 8), dtype=np.float32))
+
+
+def test_amount_zero_is_the_identity() -> None:
+    """A zero amount multiplies the field to nothing, whatever the mode."""
+    img = _noise_image()
+    for mode in MODES:
+        out = _run(img, {"mode": mode, "map_source": "noise", "amount": 0.0})
+        assert np.array_equal(out, img), mode
+
+
+def test_the_effect_does_not_mutate_its_input() -> None:
+    """Running the effect leaves the source array and the map untouched."""
+    img = _noise_image()
+    field = _x_ramp(32, 32)
+    before, map_before = img.copy(), field.copy()
+    _run(img, {"mode": "r", "map_source": "sequence", "iterations": 3}, map_img=field)
+    assert np.array_equal(img, before)
+    assert np.array_equal(field, map_before)
+
+
+def test_a_greyscale_input_comes_back_greyscale() -> None:
+    """A 2-D source returns a 2-D image of the same shape."""
+    img = np.random.default_rng(2).random((24, 24), dtype=np.float32)
+    out = _run(img, {"map_source": "noise", "iterations": 2})
+    assert out.shape == img.shape
+    assert out.dtype == np.float32

CODER NOTES AND DEVIATIONS (L14, attempt 1)
- Items accept vérifiés PAR EXÉCUTION (grise plate bit-identique it 1/3/8 × 5 modes ; rampe
  horizontale -4.0000/+3.999996 px pour k=8 = ±k/2 ; smear bord 0→5→9 px ; masque zéros
  inchangé / uns = bit-identique au sans-masque ; forme/dtype 5 modes × 5 formes).
- E1 map_source : sequence | feedback lisent le même argument map_img — le core ne distingue
  pas une frame de séquence d'un instantané du buffer ; aucune sémantique perdue.
- E1 mode : une carte monoplan (R=G=B) pilote les deux axes via la même valeur — décalerait en
  diagonale, ce que l'accept « rampe horizontale k/2 » interdit ; l'implémentation ne décale
  que l'axe horizontal (pilote vertical neutre). À trancher : conforme à l'intention ?
- E3 câblage : effects/__init__.py — câblé par l'orchestrateur.
- E3 pipeline : PipelineSpec n'a pas de champ masque (§18 documenté dans preset.py) → le
  masque est exposé en keyword-only, pas via params.
