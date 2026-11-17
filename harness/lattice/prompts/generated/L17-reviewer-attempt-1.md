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

### L17 · NTSC / VHS
- wave: 2 · deps: L2 · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/effects/ntsc.py`, `tests/test_ntsc.py`
- context: §16
- spec: implement §16. Chain: RGB → YIQ → chroma low-pass → chroma subsample → noise → demodulate
  → RGB. Parameters as listed. VHS additions: `head_switching`, `tracking_noise`, `snow`,
  `sharpening`, `tape_speed`. **Six named presets plus a simple mode with four sliders**; the full
  set behind an advanced toggle.
- accept:
  - all parameters at their neutral values return the input within 1/255.
  - `head_switching` displaces only the bottom band, and the band height is a parameter.
  - `chroma_lowpass` reduces chroma variance while leaving luma variance within 5 %.
  - each of the six presets produces a distinct output on the same input.
  - the simple mode exposes exactly four parameters.
  - output shape equals input shape.

GATE RESULTS (L17, attempt 1 — deepseek-v4-flash-0731)
- Owned tests : **23 passed**, ruff clean. Suite complète : **1759 passed, 1 skipped**.
- Registre des effets vérifié (import du paquet) — ntsc câblé par l'orchestrateur (DEV-208).
  14 effets au total.
- Carte STRICT / L (profond). La chaîne RGB→YIQ→chroma→noise→démod→RGB doit être une
  émulation de SIGNAL, pas un overlay. Six presets + mode simple 4 sliders + toggle advanced.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 5b4c8aa..4a45fcc 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import channel_shift, feedback, glitch, halftone, pixel_sort, tone  # noqa: F401
+from lattice_core.effects import channel_shift, feedback, glitch, halftone, ntsc, pixel_sort, tone  # noqa: F401
diff --git a/lattice_core/effects/ntsc.py b/lattice_core/effects/ntsc.py
new file mode 100644
index 0000000..35e4765
--- /dev/null
+++ b/lattice_core/effects/ntsc.py
@@ -0,0 +1,326 @@
+"""NTSC / VHS effect: a full RGB→YIQ→noise→demodulate signal-emulation chain (CONTRACT §16).
+
+Artefacts emerge from processing the YIQ composite signal rather than from an
+overlay. Every distortion is a no-op at its neutral value, so the whole chain is
+the identity when all parameters sit at their defaults and only the deterministic
+seed is supplied.
+"""
+
+from __future__ import annotations
+
+import math
+
+import numpy as np
+
+from lattice_core.registry import register_effect
+from lattice_core.types import Image, ParamSpec
+
+# NTSC YIQ encoding (FCC matrices, normalised to [0, 1]).
+_YIQ = np.array(
+    [[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]],
+    dtype=np.float32,
+)
+_RGB_FROM_YIQ = np.array(
+    [[1.0, 0.956, 0.621], [1.0, -0.272, -0.647], [1.0, -1.106, 1.703]],
+    dtype=np.float32,
+)
+_TAPE_BANDWIDTH = {"sp": 1.0, "lp": 0.72, "ep": 0.55}
+_RINGING = ("butterworth", "constant_k")
+_TAPE_SPEEDS = ("sp", "lp", "ep")
+
+_PARAMS = (
+    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
+    ParamSpec("chroma_lowpass", "Level", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("chroma_phase_noise", "Spread", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("luma_smear", "Spacing", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("luma_noise", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("composite_noise", "Strength", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("bandwidth", "Quality", "float", 1.0, 0.0, 1.0, 0.02),
+    ParamSpec("ringing", "Ratio", "choice", "butterworth", choices=_RINGING),
+    ParamSpec("head_switching", "Amount", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("band_height", "Level", "float", 0.25, 0.0, 1.0, 0.02),
+    ParamSpec("tracking_noise", "Threshold", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("snow", "Contrast", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("sharpening", "Darkness", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("tape_speed", "Scale", "choice", "sp", choices=_TAPE_SPEEDS),
+)
+
+# The simple mode exposes exactly these four parameters; everything else lives
+# behind the advanced toggle. Labels reuse existing i18n catalogue keys (DEV-212).
+SIMPLE_PARAMS = (
+    ParamSpec("chroma_lowpass", "Level", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("luma_noise", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("head_switching", "Amount", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("snow", "Contrast", "float", 0.0, 0.0, 1.0, 0.02),
+)
+SIMPLE_PARAM_IDS = tuple(spec.id for spec in SIMPLE_PARAMS)
+
+# Six named presets, each a set of non-neutral parameters on top of the defaults.
+PRESETS: dict[str, dict] = {
+    "Clean Broadcast": {"chroma_lowpass": 0.3, "bandwidth": 0.9, "luma_noise": 0.05},
+    "Vintage TV": {"chroma_lowpass": 0.5, "chroma_phase_noise": 0.25, "bandwidth": 0.7},
+    "VHS Home": {
+        "tape_speed": "ep",
+        "luma_smear": 0.4,
+        "luma_noise": 0.2,
+        "tracking_noise": 0.3,
+    },
+    "Static": {"snow": 0.6, "composite_noise": 0.4},
+    "Glitch Tape": {
+        "head_switching": 0.6,
+        "band_height": 0.5,
+        "tracking_noise": 0.5,
+        "chroma_phase_noise": 0.4,
+    },
+    "Retro": {"sharpening": 0.3, "chroma_lowpass": 0.4, "luma_noise": 0.1},
+}
+PRESET_NAMES = tuple(PRESETS)
+
+
+def preset(name: str) -> dict:
+    """Return the parameter overrides of one named preset."""
+    if name not in PRESETS:
+        raise KeyError(f"unknown NTSC preset: {name!r}")
+    return dict(PRESETS[name])
+
+
+def _copy(img: Image) -> Image:
+    """Return a contiguous float32 copy of img, clipped to [0, 1]."""
+    out = np.asarray(img, dtype=np.float32)
+    return np.clip(out, 0.0, 1.0, out=np.array(out, order="C", copy=True))
+
+
+def _yiq(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Return the Y, I and Q planes of a float32 RGB image."""
+    h, w, _ = rgb.shape
+    stacked = rgb.reshape(-1, 3) @ _YIQ.T
+    y, i, q = stacked[:, 0].reshape(h, w), stacked[:, 1].reshape(h, w), stacked[:, 2].reshape(h, w)
+    return y, i, q
+
+
+def _rgb(yi: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
+    """Demodulate Y, I, Q planes back into a clipped float32 RGB image."""
+    y, i, q = yi
+    h, w = y.shape
+    stacked = np.stack((y, i, q), axis=-1).reshape(-1, 3)
+    rgb = stacked @ _RGB_FROM_YIQ.T
+    return np.clip(rgb.reshape(h, w, 3), 0.0, 1.0).astype(np.float32)
+
+
+def _blur_axis(data: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
+    """Convolve data along one axis with kernel, replicating the edge samples."""
+    radius = kernel.size // 2
+    pad = [(0, 0)] * data.ndim
+    pad[axis] = (radius, radius)
+    padded = np.pad(data, pad, mode="edge")
+    length = data.shape[axis]
+    out = np.zeros(data.shape, dtype=np.float32)
+    for index, weight in enumerate(kernel):
+        window = [slice(None)] * data.ndim
+        window[axis] = slice(index, index + length)
+        out += np.float32(weight) * padded[tuple(window)]
+    return out
+
+
+def _gaussian_kernel(sigma: float) -> np.ndarray:
+    """Return a normalised 1-D gaussian kernel of radius ceil(3 * sigma)."""
+    radius = max(1, int(math.ceil(3.0 * sigma)))
+    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
+    kernel = np.exp(-(offsets * offsets) / np.float32(2.0 * sigma * sigma))
+    return (kernel / kernel.sum()).astype(np.float32)
+
+
+def _plane_blur(plane: np.ndarray, sigma: float) -> np.ndarray:
+    """Separably blur one 2-D plane with replicated edges; sigma <= 0 is a no-op."""
+    if not sigma > 0.0:
+        return plane
+    kernel = _gaussian_kernel(float(sigma))
+    out = _blur_axis(plane, kernel, 0)
+    return _blur_axis(out, kernel, 1)
+
+
+def _chroma_lowpass(i: np.ndarray, q: np.ndarray, amount: float) -> tuple[np.ndarray, np.ndarray]:
+    """Low-pass and subsample the chroma planes; amount 0 is the identity."""
+    if amount <= 0.0:
+        return i, q
+    i, q = _plane_blur(i, amount), _plane_blur(q, amount)
+    factor = max(1, int(round(amount * 8.0)))
+    if factor > 1:
+        i, q = _subsample(i, factor), _subsample(q, factor)
+    return i, q
+
+
+def _subsample(plane: np.ndarray, factor: int) -> np.ndarray:
+    """Hold-sample subsample: block-average factor columns, then replicate each."""
+    height, width = plane.shape
+    if factor <= 1 or width < 2:
+        return plane
+    out = np.empty_like(plane)
+    for x0 in range(0, width, factor):
+        x1 = min(width, x0 + factor)
+        out[:, x0:x1] = plane[:, x0:x1].mean(axis=1)[:, None]
+    return out.astype(np.float32)
+
+
+def _phase_noise(
+    i: np.ndarray, q: np.ndarray, amount: float, rng: np.random.Generator
+) -> tuple[np.ndarray, np.ndarray]:
+    """Rotate the chroma phasor by a random angle per horizontal strip."""
+    if amount <= 0.0:
+        return i, q
+    height = i.shape[0]
+    strips = max(1, min(height, 8))
+    angles = rng.uniform(-1.0, 1.0, size=strips).astype(np.float32) * np.float32(
+        amount * math.pi
+    )
+    cut = np.linspace(0, height, strips + 1, dtype=int)
+    for n in range(strips):
+        rows = slice(cut[n], cut[n + 1])
+        cos, sin = np.float32(math.cos(float(angles[n]))), np.float32(math.sin(float(angles[n])))
+        ia, qa = i[rows], q[rows]
+        i[rows], q[rows] = ia * cos - qa * sin, ia * sin + qa * cos
+    return i, q
+
+
+def _luma_smear(y: np.ndarray, amount: float) -> np.ndarray:
+    """Horizontally smear the luminance plane with a 1-D gaussian."""
+    if amount <= 0.0:
+        return y
+    kernel = _gaussian_kernel(max(0.25, amount * 4.0))
+    return _blur_axis(y, kernel, 1)
+
+
+def _bandwidth_filter(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    bw: float,
+    ringing: str,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Low-pass Y, I, Q through a kernel whose ringing depends on the mode."""
+    if bw >= 0.999:
+        return planes
+    radius = max(1, int(round((1.0 - bw) * 8.0)))
+    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
+    if ringing == "butterworth":
+        sigma = max(0.25, radius / 2.0)
+        kernel = np.exp(-(offsets * offsets) / np.float32(2.0 * sigma * sigma))
+    else:  # constant_k: rectangular box filter, produces Gibbs ringing at edges
+        kernel = np.ones_like(offsets, dtype=np.float32)
+    kernel = (kernel / kernel.sum()).astype(np.float32)
+    return tuple(_blur_axis(p, kernel, 0) for p in planes)  # type: ignore[return-value]
+
+
+def _head_switching(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    amount: float,
+    band_height: float,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Displace only the bottom band of every plane by a whole-pixel roll."""
+    if amount <= 0.0:
+        return planes
+    height, width = planes[0].shape
+    rows = max(0, int(round(band_height * height)))
+    if rows == 0:
+        return planes
+    shift = max(1, int(round(amount * width)))
+    rolled = tuple(np.roll(p[height - rows :], shift, axis=1) for p in planes)
+    out = []
+    for p, r in zip(planes, rolled, strict=True):
+        with_rows = p.copy()
+        with_rows[height - rows :] = r
+        out.append(with_rows)
+    return tuple(out)  # type: ignore[return-value]
+
+
+def _tracking_noise(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    amount: float,
+    rng: np.random.Generator,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Jitter each scan line horizontally by a deterministic per-line shift."""
+    if amount <= 0.0:
+        return planes
+    width = planes[0].shape[1]
+    max_shift = max(1, int(round(amount * width * 0.25)))
+    height = planes[0].shape[0]
+    shifts = rng.integers(-max_shift, max_shift + 1, size=height).astype(np.intp)
+    result = []
+    for p in planes:
+        shifted = p.copy()
+        for row in np.nonzero(shifts)[0]:
+            shifted[row] = np.roll(p[row], int(shifts[row]))
+        result.append(shifted)
+    return tuple(result)  # type: ignore[return-value]
+
+
+def _snow(rgb: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
+    """Add deterministic white noise on top of the demodulated RGB image."""
+    if amount <= 0.0:
+        return rgb
+    intensity = np.float32(amount * 0.4)
+    delta = rng.standard_normal(rgb.shape).astype(np.float32) * intensity
+    return np.clip(rgb + delta, 0.0, 1.0).astype(np.float32)
+
+
+def _sharpen(rgb: np.ndarray, amount: float) -> np.ndarray:
+    """Unsharp-mask sharpen the RGB image by a bounded amount."""
+    if amount <= 0.0:
+        return rgb
+    blurred = _blur_each(rgb, 1.0)
+    sharpened = rgb + np.float32(min(amount, 1.0)) * (rgb - blurred)
+    return np.clip(sharpened, 0.0, 1.0).astype(np.float32)
+
+
+def _blur_each(rgb: np.ndarray, sigma: float) -> np.ndarray:
+    """Blur each RGB channel independently with a shared gaussian kernel."""
+    out = np.empty_like(rgb)
+    kernel = _gaussian_kernel(float(sigma))
+    for channel in range(3):
+        plane = _blur_axis(rgb[:, :, channel], kernel, 0)
+        out[:, :, channel] = _blur_axis(plane, kernel, 1)
+    return out
+
+
+def _add_noise(
+    y: np.ndarray,
+    amount: float,
+    rng: np.random.Generator,
+) -> np.ndarray:
+    """Add gaussian luminance noise scaled by amount."""
+    if amount <= 0.0:
+        return y
+    delta = rng.standard_normal(y.shape).astype(np.float32) * np.float32(amount * 0.25)
+    return y + delta
+
+
+def _composite_noise(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    amount: float,
+    rng: np.random.Generator,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Add gaussian noise to every YIQ plane (the composite signal)."""
+    if amount <= 0.0:
+        return planes
+    scale = np.float32(amount * 0.25)
+    return tuple(p + rng.standard_normal(p.shape).astype(np.float32) * scale for p in planes)  # type: ignore[return-value]
+
+
+@register_effect("ntsc", "NTSC / VHS", _PARAMS)
+def ntsc(img: Image, params: dict, rng: np.random.Generator) -> Image:
+    """Emulate an NTSC / VHS composite signal chain and return the demodulated RGB."""
+    source = _copy(img)
+    y, i, q = _yiq(source)
+    lowpass = float(params["chroma_lowpass"])
+    i, q = _chroma_lowpass(i, q, lowpass)
+    i, q = _phase_noise(i, q, float(params["chroma_phase_noise"]), rng)
+    y = _luma_smear(y, float(params["luma_smear"]))
+    y = _add_noise(y, float(params["luma_noise"]), rng)
+    bw = float(params["bandwidth"]) * _TAPE_BANDWIDTH[str(params["tape_speed"])]
+    y, i, q = _bandwidth_filter((y, i, q), bw, str(params["ringing"]))
+    y, i, q = _composite_noise((y, i, q), float(params["composite_noise"]), rng)
+    y, i, q = _head_switching(
+        (y, i, q), float(params["head_switching"]), float(params["band_height"])
+    )
+    y, i, q = _tracking_noise((y, i, q), float(params["tracking_noise"]), rng)
+    rgb = _rgb((y, i, q))
+    rgb = _snow(rgb, float(params["snow"]), rng)
+    return _sharpen(rgb, float(params["sharpening"]))
diff --git a/tests/test_ntsc.py b/tests/test_ntsc.py
new file mode 100644
index 0000000..b249ce7
--- /dev/null
+++ b/tests/test_ntsc.py
@@ -0,0 +1,227 @@
+"""Tests for the NTSC / VHS signal-emulation effect (L17, CONTRACT §16)."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+# Register the effect (`__init__.py` does not import it yet; see DEVIATIONS).
+from lattice_core import effects  # noqa: F401, E402
+from lattice_core.effects.ntsc import PRESET_NAMES, PRESETS, SIMPLE_PARAM_IDS, SIMPLE_PARAMS
+from lattice_core.registry import get_effect, list_effects, resolve_params
+
+NEUTRAL = {  # every parameter at its neutral value
+    "seed": 0,
+    "chroma_lowpass": 0.0,
+    "chroma_phase_noise": 0.0,
+    "luma_smear": 0.0,
+    "luma_noise": 0.0,
+    "composite_noise": 0.0,
+    "bandwidth": 1.0,
+    "ringing": "butterworth",
+    "head_switching": 0.0,
+    "band_height": 0.25,
+    "tracking_noise": 0.0,
+    "snow": 0.0,
+    "sharpening": 0.0,
+    "tape_speed": "sp",
+}
+
+SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))
+
+
+def _apply(
+    img: np.ndarray, overrides: dict | None = None, seed: int = 0
+) -> np.ndarray:
+    """Run the registered ntsc effect with resolved parameters and a seeded generator."""
+    info = get_effect("ntsc")
+    params = dict(NEUTRAL)
+    params.update(overrides or {})
+    params["seed"] = seed
+    resolved = resolve_params(info.params, params)
+    return info.fn(img.copy(), resolved, np.random.default_rng(seed))
+
+
+def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
+    """Return a seeded random float32 (H, W, 3) image."""
+    return np.random.default_rng(seed).random(shape + (3,), dtype=np.float32)
+
+
+def _luma(rgb: np.ndarray) -> np.ndarray:
+    """Return the NTSC luma plane of an RGB float32 array."""
+    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
+
+
+def _chroma_variance(rgb: np.ndarray) -> float:
+    """Return a per-pixel chroma proxy variance (r-b and g-b differences)."""
+    cb = rgb[:, :, 0] - rgb[:, :, 2]
+    cr = rgb[:, :, 1] - rgb[:, :, 2]
+    return float((cb.var() + cr.var()) / 2.0)
+
+
+def test_registers_an_ntsc_effect() -> None:
+    """The ntsc effect is registered and carries the full description."""
+    info = get_effect("ntsc")
+    assert info.id == "ntsc"
+    assert info.name == "NTSC / VHS"
+    ids = [spec.id for spec in info.params]
+    assert ids == list(NEUTRAL)
+
+
+def test_all_parameters_at_neutral_return_the_input() -> None:
+    """Neutral parameters are the identity within 1/255."""
+    img = _random_image((48, 36))
+    out = _apply(img)
+    assert np.allclose(out, img, atol=1.0 / 255.0)
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_output_shape_equals_input_shape(shape: tuple[int, int]) -> None:
+    """The effect preserves image shape and dtype on every size."""
+    img = _random_image(shape)
+    out = _apply(img)
+    assert out.shape == img.shape
+    assert out.dtype == np.float32
+
+
+def test_effect_does_not_mutate_input() -> None:
+    """The ntsc effect never writes into the array it was given."""
+    img = _random_image((24, 24))
+    before = img.copy()
+    _apply(img, _random_aggressive())
+    assert np.array_equal(img, before)
+
+
+def _random_aggressive() -> dict:
+    """Return a high-strength parameter set that touches every stage."""
+    return {
+        "chroma_lowpass": 0.8,
+        "chroma_phase_noise": 0.7,
+        "luma_smear": 0.6,
+        "luma_noise": 0.5,
+        "composite_noise": 0.5,
+        "bandwidth": 0.4,
+        "ringing": "constant_k",
+        "head_switching": 0.8,
+        "band_height": 0.6,
+        "tracking_noise": 0.7,
+        "snow": 0.8,
+        "sharpening": 0.7,
+        "tape_speed": "ep",
+    }
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_extreme_params_never_raise(shape: tuple[int, int]) -> None:
+    """Minimum and maximum parameters never raise and stay inside [0, 1]."""
+    img = _random_image(shape)
+    for overrides in (NEUTRAL, _random_aggressive()):
+        out = _apply(img, overrides)
+        assert out.shape == img.shape
+        assert float(out.min()) >= 0.0
+        assert float(out.max()) <= 1.0
+
+
+def test_effect_is_deterministic_per_seed() -> None:
+    """Identical seeds give identical output; different seeds differ."""
+    img = _random_image((32, 32))
+    first = _apply(img, {"snow": 0.7, "luma_noise": 0.5}, seed=5)
+    second = _apply(img, {"snow": 0.7, "luma_noise": 0.5}, seed=5)
+    other = _apply(img, {"snow": 0.7, "luma_noise": 0.5}, seed=6)
+    assert np.array_equal(first, second)
+    assert not np.array_equal(first, other)
+
+
+def test_head_switching_displaces_only_the_bottom_band() -> None:
+    """Head switching displaces only the bottom `band_height` fraction; the top is intact."""
+    img = _random_image((64, 64))
+    band_height = 0.25
+    band_rows = int(round(band_height * img.shape[0]))
+    assert band_rows > 0
+    base = _apply(img, {"head_switching": 0.0, "band_height": band_height})
+    out = _apply(img, {"head_switching": 0.6, "band_height": band_height})
+    # Every row above the band matches the unaffected pipeline; only the band moves.
+    assert np.allclose(out[:-band_rows], base[:-band_rows], atol=1e-6)
+    assert not np.allclose(out[-band_rows:], base[-band_rows:], atol=1e-6)
+
+
+def test_larger_band_height_displaces_more_rows() -> None:
+    """The band height is a parameter: a bigger value moves a taller bottom slice."""
+    img = _random_image((64, 64))
+    small_rows = int(round(0.2 * img.shape[0]))
+    large_rows = int(round(0.5 * img.shape[0]))
+    assert large_rows > small_rows
+    steps = {"head_switching": 0.8, "band_height": 0.0}
+    base = _apply(img, steps)  # no displacement at all
+    small = _apply(img, {**steps, "band_height": 0.2})
+    large = _apply(img, {**steps, "band_height": 0.5})
+    # Rows between the two band heights: displaced only when the band is tall enough.
+    assert np.allclose(small[-large_rows:-small_rows], base[-large_rows:-small_rows], atol=1e-6)
+    assert not np.allclose(large[-large_rows:-small_rows], base[-large_rows:-small_rows], atol=1e-6)
+
+
+def test_chroma_lowpass_reduces_chroma_variance_keeps_luma() -> None:
+    """Low-passing chroma cuts chroma variance while luma variance stays within 5%."""
+    img = _random_image((64, 64), seed=3)
+    out = _apply(img, {"chroma_lowpass": 0.8, "luma_noise": 0.0, "luma_smear": 0.0})
+    assert _chroma_variance(out) < _chroma_variance(img)
+    in_luma, out_luma = _luma(img), _luma(out)
+    ratio = float(out_luma.var() / in_luma.var()) if in_luma.var() > 0 else 1.0
+    assert abs(ratio - 1.0) <= 0.05
+
+
+def test_luma_smear_reduces_luma_variance() -> None:
+    """Smearing lowers luma variance and leaves the chroma roughly constant."""
+    img = _random_image((64, 64), seed=4)
+    out = _apply(img, {"luma_smear": 0.8, "chroma_lowpass": 0.0})
+    assert float(_luma(out).var()) < float(_luma(img).var())
+
+
+def test_each_preset_produces_a_distinct_output_on_the_same_input() -> None:
+    """The six named presets all transform the same input into different results."""
+    assert len(PRESET_NAMES) == 6
+    assert set(PRESET_NAMES) == set(PRESETS)
+    img = _random_image((48, 48), seed=11)
+    outputs = [_apply(img, PRESETS[name]) for name in PRESET_NAMES]
+    assert all(out.shape == img.shape for out in outputs)
+    for index, name in enumerate(PRESET_NAMES):
+        for other_index, other_name in enumerate(PRESET_NAMES):
+            if index != other_index:
+                assert not np.array_equal(outputs[index], outputs[other_index]), (
+                    name,
+                    other_name,
+                )
+
+
+def test_every_preset_differs_from_the_neutral_input() -> None:
+    """No preset is degenerate: each output moves at least one pixel from the input."""
+    img = _random_image((48, 48), seed=11)
+    for name in PRESET_NAMES:
+        out = _apply(img, PRESETS[name])
+        assert not np.allclose(out, img, atol=1e-6), name
+
+
+def test_simple_mode_exposes_exactly_four_parameters() -> None:
+    """The simple mode is exactly four parameters plus a deterministic seed."""
+    assert len(SIMPLE_PARAMS) == 4
+    assert len(SIMPLE_PARAM_IDS) == 4
+    assert set(SIMPLE_PARAM_IDS) <= set(NEUTRAL)
+    ids = {spec.id for spec in SIMPLE_PARAMS}
+    assert len(ids) == 4
+
+
+def test_simple_params_carry_i18n_catalogue_labels() -> None:
+    """Every simple-mode parameter label is a key of the frozen English catalogue."""
+    import json
+    from pathlib import Path
+
+    from lattice_dither import i18n
+
+    catalogue = json.loads((Path(i18n.__file__).parent / "en.json").read_text("utf-8"))
+    for spec in (*SIMPLE_PARAMS, *get_effect("ntsc").params):
+        assert spec.label in catalogue, spec.label
+
+
+def test_registered_effect_is_listed() -> None:
+    """The ntsc effect appears among every registered effect."""
+    assert "ntsc" in {info.id for info in list_effects()}

CODER NOTES AND DEVIATIONS (L17, attempt 1)
- 14 paramètres (chroma_lowpass, chroma_phase_noise, luma_smear, luma_noise, composite_noise,
  bandwidth, ringing butterworth|constant_k, head_switching, band_height, tracking_noise,
  snow, sharpening, tape_speed sp|lp|ep, seed). 6 presets : Clean Broadcast, Vintage TV, VHS
  Home, Static, Glitch Tape, Retro. Simple mode = chroma_lowpass, luma_noise, head_switching,
  snow. Labels i18n DEV-212.
- E1 : effects/__init__.py (hors owns) — câblé par l'orchestrateur.
- Note : Pyright signale des diagnostiques LSP inoffensifs (tuple-in-type, numpy non résolu) —
  ruff + pytest passent ; _plane_blur pour _chroma_lowpass ; sharpen via _blur_each.
