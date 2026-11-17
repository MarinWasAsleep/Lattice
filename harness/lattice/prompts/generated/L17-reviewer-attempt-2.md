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

GATE RESULTS (L17, attempt 2 — deepseek-v4-1-flash-1017, retry du FIX Sonnet pass 1)
- Owned tests : **61 passed** (23 → 61 ; un test par étage + seuil MAD des presets), ruff propre.
- Suite complète : **1855 passed, 1 skipped** (test_glyph_shape.py exclu — L7 retry en vol).
- Mutation testing du codeur : les 5 défauts du pass 1 sont tués (axe bandwidth → 4 échecs ;
  noyau gaussien → 3 ; roll non clampé → 3 ; snow RGB → 1 ; seed ignoré → 1).

DISPOSITION PASS 1 (attempt 2)
- blocker bandwidth : convolue désormais axis=1 (le long des lignes) ; bord vertical étalé
  horizontalement, bord horizontal intact à 6e-8.
- major ringing : vrai noyau à lobes négatifs — butterworth = réponse Butterworth ordre 4 (FFT),
  constant_k = brick-wall (Gibbs) ; sur/sous-dépassent mesurablement (0.029 / 0.033), distincts.
- major head_switching : déplacement plafonné à width*0.5, skew croissant dans la bande,
  band_height défaut 0.02.
- major toggle : MODES + params_for_mode("simple"|"advanced") ; SIMPLE_PARAMS DÉRIVÉ de _PARAMS ;
  simple=4, advanced=14 ; preset() testé avec KeyError.
- major labels : 14 labels distincts et honnêtes du catalogue gelé + LABEL_NOTES documentant
  chaque mapping (E1).
- major tests étages : un test par étage prouvant l'effet ET le no-op au neutre ; presets sur
  seuil MAD > 0.02 (min mesuré 0.122).
- minor snow : injecté dans Y avant démodulation (grain monochrome, écart R-G = 0) ;
  sharpening = peaking sur Y seul (chroma bit-identique).
- minor seed : pilote le générateur (prime sur rng) ; commentaire corrigé (I/Q signés) ;
  noyau 21 taps mélangé à une impulsion par bw → continu (0.999 vs 1.0 : 6.7e-5).

DIFF (arbre de travail vs HEAD — état complet de la carte)
diff --git a/lattice_core/effects/ntsc.py b/lattice_core/effects/ntsc.py
new file mode 100644
index 0000000..faed0f0
--- /dev/null
+++ b/lattice_core/effects/ntsc.py
@@ -0,0 +1,362 @@
+"""NTSC / VHS effect: a full RGB→YIQ→noise→demodulate signal-emulation chain (CONTRACT §16).
+
+Artefacts emerge from the composite signal rather than from an overlay: snow and
+sharpening act on the luma of the YIQ signal before demodulation, and the bandwidth
+limit runs along the scan lines. Every distortion is a no-op at its neutral value,
+so the whole chain is the identity when all parameters sit at their defaults.
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
+# NTSC YIQ encoding (FCC matrices). Y is unsigned in [0, 1]; I and Q are signed.
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
+# Bandwidth kernel: a fixed 21-tap window whose taps are mixed with an impulse by
+# `bandwidth`, so the response is continuous in the parameter and exact at 1.0.
+_BANDWIDTH_RADIUS = 10
+_FILTER_SAMPLES = 512
+_BUTTERWORTH_ORDER = 4
+
+# Labels are keys of the frozen i18n catalogue (lattice_dither/i18n/en.json), which
+# is outside this card's owns, so no NTSC-specific key can be added (E1). Each label
+# is the catalogue key that really names what its control does; LABEL_NOTES records
+# the mapping, and no two parameters share a label.
+_PARAMS = (
+    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
+    ParamSpec("chroma_lowpass", "Pre-blur", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("chroma_phase_noise", "Angle", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("luma_smear", "Radius", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("luma_noise", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("composite_noise", "Level", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("bandwidth", "Quality", "float", 1.0, 0.0, 1.0, 0.02),
+    ParamSpec("ringing", "Matrix", "choice", "butterworth", choices=_RINGING),
+    ParamSpec("head_switching", "Ratio", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("band_height", "Scale", "float", 0.02, 0.0, 1.0, 0.01),
+    ParamSpec("tracking_noise", "Spread", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("snow", "Amount", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("sharpening", "Strength", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("tape_speed", "Resolution", "choice", "sp", choices=_TAPE_SPEEDS),
+)
+
+# Why each label is the honest catalogue key for its parameter.
+LABEL_NOTES: dict[str, str] = {
+    "seed": "the noise seed, used verbatim",
+    "chroma_lowpass": "a low-pass pre-blur of the chroma planes",
+    "chroma_phase_noise": "the random chroma phase angle",
+    "luma_smear": "the horizontal smear radius of the luma",
+    "luma_noise": "the intensity of the luma noise",
+    "composite_noise": "the level of noise on the whole composite signal",
+    "bandwidth": "the horizontal signal bandwidth, i.e. the picture quality",
+    "ringing": "which convolution matrix shapes the bandwidth limit",
+    "head_switching": "the ratio of the width the bottom band is displaced by",
+    "band_height": "the scale of the band height against the frame height",
+    "tracking_noise": "the spread of the per-line horizontal jitter",
+    "snow": "the amount of monochrome snow",
+    "sharpening": "the strength of the luma edge enhancement",
+    "tape_speed": "the tape speed, i.e. the recorded resolution",
+}
+
+# The simple mode exposes exactly four parameters; everything else is behind the
+# advanced toggle. Both tuples are derived from _PARAMS, never duplicated.
+_SIMPLE_IDS: tuple[str, ...] = ("bandwidth", "chroma_lowpass", "snow", "head_switching")
+MODES: tuple[str, ...] = ("simple", "advanced")
+_BY_ID: dict[str, ParamSpec] = {spec.id: spec for spec in _PARAMS}
+
+
+def params_for_mode(mode: str) -> tuple[ParamSpec, ...]:
+    """Return the parameters a UI exposes in mode: four in simple, all in advanced."""
+    if mode == "advanced":
+        return _PARAMS
+    if mode == "simple":
+        return tuple(_BY_ID[param_id] for param_id in _SIMPLE_IDS)
+    raise ValueError(f"unknown NTSC mode {mode!r}, expected one of {MODES}")
+
+
+SIMPLE_PARAMS = params_for_mode("simple")
+SIMPLE_PARAM_IDS = tuple(spec.id for spec in SIMPLE_PARAMS)
+
+# Six named presets, each a set of non-neutral parameters on top of the defaults.
+PRESETS: dict[str, dict] = {
+    "Clean Broadcast": {"bandwidth": 0.85, "chroma_lowpass": 0.2, "luma_noise": 0.05},
+    "Vintage TV": {"bandwidth": 0.55, "chroma_lowpass": 0.45, "chroma_phase_noise": 0.35},
+    "VHS Home": {"tape_speed": "ep", "luma_smear": 0.45, "luma_noise": 0.2, "tracking_noise": 0.7},
+    "Static": {"snow": 0.6, "composite_noise": 0.35},
+    "Glitch Tape": {
+        "head_switching": 0.6,
+        "band_height": 0.35,
+        "tracking_noise": 0.9,
+        "chroma_phase_noise": 0.5,
+    },
+    "Retro": {"sharpening": 0.7, "chroma_lowpass": 0.35, "luma_noise": 0.12},
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
+def _generator(params: dict, rng: np.random.Generator) -> np.random.Generator:
+    """Return the noise source seeded by the `seed` parameter, falling back to rng."""
+    seed = params.get("seed")
+    if seed is None:
+        return rng
+    return np.random.default_rng(int(seed))
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
+    out = np.zeros(data.shape, dtype=np.float64)
+    for index, weight in enumerate(kernel):
+        window = [slice(None)] * data.ndim
+        window[axis] = slice(index, index + length)
+        out += np.float64(weight) * padded[tuple(window)]
+    return out.astype(np.float32)
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
+    """Rotate the chroma phasor by a seeded random angle per horizontal strip."""
+    if amount <= 0.0:
+        return i, q
+    height = i.shape[0]
+    strips = max(1, min(height, 8))
+    angles = rng.uniform(-1.0, 1.0, size=strips).astype(np.float32) * np.float32(amount * math.pi)
+    cut = np.linspace(0, height, strips + 1, dtype=int)
+    i_out, q_out = i.copy(), q.copy()
+    for n in range(strips):
+        rows = slice(cut[n], cut[n + 1])
+        cos, sin = np.float32(math.cos(float(angles[n]))), np.float32(math.sin(float(angles[n])))
+        ia, qa = i[rows], q[rows]
+        i_out[rows], q_out[rows] = ia * cos - qa * sin, ia * sin + qa * cos
+    return i_out, q_out
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
+def _bandwidth_kernel(bw: float, ringing: str) -> np.ndarray:
+    """Return a 1-D low-pass kernel of the given mode, mixed with an impulse by bw."""
+    offsets = np.arange(-_BANDWIDTH_RADIUS, _BANDWIDTH_RADIUS + 1, dtype=np.float32)
+    if bw >= 1.0:
+        return (offsets == 0).astype(np.float32)
+    freqs = np.fft.rfftfreq(_FILTER_SAMPLES)
+    cutoff = max(0.5 * bw, 1.0 / _FILTER_SAMPLES)
+    if ringing == "constant_k":
+        magnitude = (freqs <= cutoff).astype(np.float64)  # brick wall: strongest Gibbs lobes
+    else:
+        magnitude = 1.0 / np.sqrt(1.0 + (freqs / cutoff) ** (2 * _BUTTERWORTH_ORDER))
+    taps = np.fft.irfft(magnitude, n=_FILTER_SAMPLES)
+    proto = np.concatenate((taps[-_BANDWIDTH_RADIUS:], taps[: _BANDWIDTH_RADIUS + 1]))
+    kernel = bw * (offsets == 0) + (1.0 - bw) * proto
+    return (kernel / kernel.sum()).astype(np.float32)
+
+
+def _bandwidth_filter(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    bw: float,
+    ringing: str,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Limit the horizontal bandwidth of Y, I and Q along the scan lines."""
+    if bw >= 1.0:
+        return planes
+    kernel = _bandwidth_kernel(bw, ringing)
+    return tuple(_blur_axis(p, kernel, 1) for p in planes)  # type: ignore[return-value]
+
+
+def _head_switching(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    amount: float,
+    band_height: float,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Displace the bottom band along the scan lines, the shift growing into the band."""
+    if amount <= 0.0 or band_height <= 0.0:
+        return planes
+    height, width = planes[0].shape
+    rows = min(height, max(1, int(round(band_height * height))))
+    base = min(float(amount), 1.0) * width * 0.5  # never a whole width: that is the identity
+    shifts = [int(round(base * (index + 1) / rows)) for index in range(rows)]
+    out = []
+    for plane in planes:
+        shifted = plane.copy()
+        for index, shift in enumerate(shifts):
+            if shift:
+                row = height - rows + index
+                shifted[row] = np.roll(plane[row], shift)
+        out.append(shifted)
+    return tuple(out)  # type: ignore[return-value]
+
+
+def _tracking_noise(
+    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
+    amount: float,
+    rng: np.random.Generator,
+) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
+    """Jitter each scan line horizontally by a seeded per-line shift."""
+    if amount <= 0.0:
+        return planes
+    height, width = planes[0].shape
+    max_shift = min(max(1, int(round(amount * width * 0.25))), max(1, width // 2))
+    shifts = rng.integers(-max_shift, max_shift + 1, size=height).astype(np.intp)
+    result = []
+    for plane in planes:
+        shifted = plane.copy()
+        for row in np.nonzero(shifts)[0]:
+            shifted[row] = np.roll(plane[row], int(shifts[row]))
+        result.append(shifted)
+    return tuple(result)  # type: ignore[return-value]
+
+
+def _snow(y: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
+    """Inject monochrome white noise into the luminance signal before demodulation."""
+    if amount <= 0.0:
+        return y
+    delta = rng.standard_normal(y.shape).astype(np.float32) * np.float32(amount * 0.5)
+    return y + delta
+
+
+def _sharpen(y: np.ndarray, amount: float) -> np.ndarray:
+    """Sharpen the luminance signal horizontally, like a VCR peaking circuit."""
+    if amount <= 0.0:
+        return y
+    blurred = _blur_axis(y, _gaussian_kernel(1.0), 1)
+    return y + np.float32(min(amount, 1.0)) * (y - blurred)
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
+    gen = _generator(params, rng)
+    y, i, q = _yiq(source)
+    i, q = _chroma_lowpass(i, q, float(params["chroma_lowpass"]))
+    i, q = _phase_noise(i, q, float(params["chroma_phase_noise"]), gen)
+    y = _luma_smear(y, float(params["luma_smear"]))
+    bw = float(params["bandwidth"]) * _TAPE_BANDWIDTH[str(params["tape_speed"])]
+    y, i, q = _bandwidth_filter((y, i, q), bw, str(params["ringing"]))
+    y = _add_noise(y, float(params["luma_noise"]), gen)
+    y, i, q = _composite_noise((y, i, q), float(params["composite_noise"]), gen)
+    y = _snow(y, float(params["snow"]), gen)
+    y, i, q = _head_switching(
+        (y, i, q), float(params["head_switching"]), float(params["band_height"])
+    )
+    y, i, q = _tracking_noise((y, i, q), float(params["tracking_noise"]), gen)
+    y = _sharpen(y, float(params["sharpening"]))
+    return _rgb((y, i, q))
diff --git a/tests/test_ntsc.py b/tests/test_ntsc.py
new file mode 100644
index 0000000..e5153a5
--- /dev/null
+++ b/tests/test_ntsc.py
@@ -0,0 +1,400 @@
+"""Tests for the NTSC / VHS signal-emulation effect (L17, CONTRACT §16)."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+from lattice_core import effects  # noqa: F401  (registers the effect)
+from lattice_core.effects.ntsc import (
+    LABEL_NOTES,
+    MODES,
+    PRESET_NAMES,
+    PRESETS,
+    SIMPLE_PARAM_IDS,
+    params_for_mode,
+    preset,
+)
+from lattice_core.registry import get_effect, list_effects, resolve_params
+
+NEUTRAL = {  # every parameter at its neutral value
+    "seed": 0, "chroma_lowpass": 0.0, "chroma_phase_noise": 0.0, "luma_smear": 0.0,
+    "luma_noise": 0.0, "composite_noise": 0.0, "bandwidth": 1.0, "ringing": "butterworth",
+    "head_switching": 0.0, "band_height": 0.02, "tracking_noise": 0.0, "snow": 0.0,
+    "sharpening": 0.0, "tape_speed": "sp",
+}
+SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))
+AGGRESSIVE = {
+    "chroma_lowpass": 0.8, "chroma_phase_noise": 0.7, "luma_smear": 0.6, "luma_noise": 0.5,
+    "composite_noise": 0.5, "bandwidth": 0.4, "ringing": "constant_k", "head_switching": 0.8,
+    "band_height": 0.6, "tracking_noise": 0.7, "snow": 0.8, "sharpening": 0.7, "tape_speed": "ep",
+}
+# Parameters that only act through a companion: `ringing` shapes the bandwidth
+# kernel, so it needs a bandwidth below 1; `band_height` sizes the head-switching
+# band, so it needs a displacement to size.
+GATES: dict[str, dict] = {"ringing": {"bandwidth": 0.4}, "band_height": {"head_switching": 0.8}}
+ZERO_STAGES = ("chroma_lowpass", "chroma_phase_noise", "luma_smear", "luma_noise",
+               "composite_noise", "tracking_noise", "snow", "sharpening")
+
+
+def _apply(img: np.ndarray, overrides: dict | None = None, seed: int = 0) -> np.ndarray:
+    """Run the registered ntsc effect with resolved parameters and a seeded generator."""
+    info = get_effect("ntsc")
+    params = dict(NEUTRAL)
+    params.update(overrides or {})
+    params["seed"] = seed
+    return info.fn(img.copy(), resolve_params(info.params, params), np.random.default_rng(seed))
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
+    return float(((rgb[:, :, 0] - rgb[:, :, 2]).var() + (rgb[:, :, 1] - rgb[:, :, 2]).var()) / 2.0)
+
+
+def _horizontal_gradient(rgb: np.ndarray) -> float:
+    """Return the mean absolute horizontal luma gradient, a measure of fine detail."""
+    return float(np.abs(np.diff(_luma(rgb), axis=1)).mean())
+
+
+def _vertical_edge(width: int = 96, height: int = 8) -> np.ndarray:
+    """Return an image with one vertical step edge, constant along every row."""
+    edge = np.zeros((height, width, 3), dtype=np.float32)
+    edge[:, width // 2 :] = 0.8
+    return edge + np.float32(0.1)
+
+
+def _grey(size: int = 24) -> np.ndarray:
+    """Return a flat mid-grey image, where any chroma is noise the effect added."""
+    return np.full((size, size, 3), 0.5, dtype=np.float32)
+
+
+def _band_rows(height: int, band_height: float) -> int:
+    """Return the number of bottom rows a band_height fraction covers."""
+    return max(1, int(round(band_height * height)))
+
+
+def test_registers_an_ntsc_effect() -> None:
+    """The ntsc effect is registered, listed and carries the full description."""
+    info = get_effect("ntsc")
+    assert (info.id, info.name) == ("ntsc", "NTSC / VHS")
+    assert [spec.id for spec in info.params] == list(NEUTRAL)
+    assert "ntsc" in {effect.id for effect in list_effects()}
+
+
+def test_all_parameters_at_neutral_return_the_input() -> None:
+    """Neutral parameters are the identity within 1/255."""
+    img = _random_image((48, 36))
+    assert np.allclose(_apply(img), img, atol=1.0 / 255.0)
+
+
+def test_every_parameter_defaults_to_its_neutral_value() -> None:
+    """The registry defaults are the neutral values, so a fresh instance is the identity."""
+    assert {spec.id: spec.default for spec in get_effect("ntsc").params} == NEUTRAL
+
+
+@pytest.mark.parametrize("param_id", [key for key in NEUTRAL if key != "seed"])
+def test_every_parameter_changes_the_output_on_its_own(param_id: str) -> None:
+    """Each parameter is live: moving it alone away from neutral changes the picture."""
+    img, gate = _random_image((32, 32), seed=71), GATES.get(param_id, {})
+    base = _apply(img, gate)
+    spec = next(spec for spec in get_effect("ntsc").params if spec.id == param_id)
+    if spec.kind == "choice":
+        value = next(choice for choice in spec.choices if choice != spec.default)
+    elif spec.kind == "int":
+        assert spec.max is not None
+        value = int(spec.max)
+    else:
+        value = 1.0 if spec.default != 1.0 else 0.0
+    assert not np.allclose(_apply(img, {**gate, param_id: value}), base, atol=1e-4), param_id
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_output_shape_equals_input_shape(shape: tuple[int, int]) -> None:
+    """The effect preserves image shape and dtype on every size."""
+    out = _apply(_random_image(shape))
+    assert (out.shape, out.dtype) == (shape + (3,), np.float32)
+
+
+def test_effect_does_not_mutate_input() -> None:
+    """The ntsc effect never writes into the array it was given."""
+    img = _random_image((24, 24))
+    before = img.copy()
+    _apply(img, AGGRESSIVE)
+    assert np.array_equal(img, before)
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_extreme_params_never_raise(shape: tuple[int, int]) -> None:
+    """Maximum parameters never raise and stay inside [0, 1]."""
+    out = _apply(_random_image(shape), AGGRESSIVE)
+    assert out.shape == shape + (3,)
+    assert float(out.min()) >= 0.0
+    assert float(out.max()) <= 1.0
+
+
+def test_effect_is_deterministic_per_seed() -> None:
+    """Identical seeds give identical output; different seeds differ."""
+    img = _random_image((32, 32))
+    noisy = {"snow": 0.7, "luma_noise": 0.5}
+    assert np.array_equal(_apply(img, noisy, seed=5), _apply(img, noisy, seed=5))
+    assert not np.array_equal(_apply(img, noisy, seed=5), _apply(img, noisy, seed=6))
+
+
+def test_seed_parameter_drives_the_noise_not_the_rng_argument() -> None:
+    """The `seed` parameter is read: it wins over the rng the caller passes in."""
+    img = _random_image((24, 24))
+    info = get_effect("ntsc")
+    params = resolve_params(info.params, {**NEUTRAL, "snow": 0.6, "seed": 11})
+    first = info.fn(img.copy(), params, np.random.default_rng(0))
+    assert np.array_equal(first, info.fn(img.copy(), params, np.random.default_rng(99)))
+    other = resolve_params(info.params, {**NEUTRAL, "snow": 0.6, "seed": 12})
+    assert not np.array_equal(first, info.fn(img.copy(), other, np.random.default_rng(0)))
+
+
+def test_bandwidth_smears_a_vertical_edge_horizontally() -> None:
+    """`bandwidth < 1` blurs along the scan lines: a vertical edge gains intermediate pixels."""
+    out = _apply(_vertical_edge(), {"bandwidth": 0.3})
+    row = out[0, :, 0]
+    assert np.sum((row > 0.1 + 1e-3) & (row < 0.9 - 1e-3)) >= 6
+    assert float(np.abs(out - out[0:1]).max()) < 1e-5  # every row smeared alike: axis 1
+
+
+def test_bandwidth_leaves_a_horizontal_edge_unchanged() -> None:
+    """A horizontal edge has no horizontal detail, so the bandwidth limit cannot touch it."""
+    edge = np.zeros((32, 32, 3), dtype=np.float32)
+    edge[16:] = 0.8
+    assert float(np.abs(_apply(edge, {"bandwidth": 0.3}) - edge).max()) < 1e-4
+
+
+def test_bandwidth_reduces_horizontal_detail_monotonically() -> None:
+    """Lowering `bandwidth` removes more detail, and 0.999 is almost the identity."""
+    img = _random_image((32, 64), seed=21)
+    widths = (1.0, 0.8, 0.5, 0.2)
+    gradients = [_horizontal_gradient(_apply(img, {"bandwidth": bw})) for bw in widths]
+    assert gradients == sorted(gradients, reverse=True), gradients
+    assert gradients[0] > gradients[-1] * 2.0
+    assert float(np.abs(_apply(img, {"bandwidth": 0.999}) - _apply(img)).max()) < 5e-3
+
+
+def test_ringing_overshoots_a_step_edge() -> None:
+    """Both modes overshoot and undershoot a step, and they are different responses."""
+    rows = {
+        mode: _apply(_vertical_edge(), {"bandwidth": 0.3, "ringing": mode})[0, :, 0]
+        for mode in ("butterworth", "constant_k")
+    }
+    for mode, row in rows.items():
+        assert float(row.max()) > 0.9 + 1e-3, (mode, float(row.max()))
+        assert float(row.min()) < 0.1 - 1e-3, (mode, float(row.min()))
+    butter, constant = rows["butterworth"], rows["constant_k"]
+    assert float(np.abs(butter - constant).max()) > 1e-2
+
+
+@pytest.mark.parametrize(("amount", "band_height"), [(0.6, 0.25), (1.0, 0.1)])
+def test_head_switching_displaces_only_the_bottom_band(amount: float, band_height: float) -> None:
+    """Head switching moves the bottom band only; the maximum is not the identity."""
+    img = _random_image((64, 64))
+    rows = _band_rows(img.shape[0], band_height)
+    base = _apply(img, {"head_switching": 0.0, "band_height": band_height})
+    out = _apply(img, {"head_switching": amount, "band_height": band_height})
+    assert float(np.abs(out[:-rows] - base[:-rows]).max()) < 1e-6
+    assert float(np.abs(out[-rows:] - base[-rows:]).max()) > 0.1
+
+
+def test_head_switching_grows_towards_the_bottom_edge() -> None:
+    """The displacement is a skew: the last band row moves further than the first one."""
+    img = _random_image((64, 64), seed=31)
+    rows = _band_rows(img.shape[0], 0.1)
+    base = _apply(img, {"head_switching": 0.0, "band_height": 0.1})
+    out = _apply(img, {"head_switching": 1.0, "band_height": 0.1})
+    shifts = [
+        min(
+            range(0, img.shape[1] // 2 + 1),
+            key=lambda s, row=row: float(np.abs(out[row] - np.roll(base[row], s, axis=0)).max()),
+        )
+        for row in range(img.shape[0] - rows, img.shape[0])
+    ]
+    assert shifts == sorted(shifts), shifts
+    assert shifts[-1] > shifts[0]
+
+
+def test_band_height_is_a_parameter_of_the_displaced_band() -> None:
+    """A bigger band height moves a taller bottom slice; the rows between stay intact."""
+    img = _random_image((64, 64))
+    small_rows, large_rows = _band_rows(64, 0.2), _band_rows(64, 0.5)
+    assert large_rows > small_rows
+    steps = {"head_switching": 0.8, "band_height": 0.0}
+    base, small = _apply(img, steps), _apply(img, {**steps, "band_height": 0.2})
+    large = _apply(img, {**steps, "band_height": 0.5})
+    between = slice(64 - large_rows, 64 - small_rows)
+    assert float(np.abs(small[between] - base[between]).max()) < 1e-6
+    assert float(np.abs(large[between] - base[between]).max()) > 0.1
+
+
+def test_chroma_lowpass_reduces_chroma_variance_keeps_luma() -> None:
+    """Low-passing chroma cuts chroma variance while luma variance stays within 5%."""
+    img = _random_image((64, 64), seed=3)
+    out = _apply(img, {"chroma_lowpass": 0.8})
+    assert _chroma_variance(out) < _chroma_variance(img)
+    in_luma, out_luma = _luma(img), _luma(out)
+    ratio = float(out_luma.var() / in_luma.var()) if in_luma.var() > 0 else 1.0
+    assert abs(ratio - 1.0) <= 0.05
+    # The luma smear, by contrast, is the stage that lowers luma variance.
+    smeared = _apply(img, {"luma_smear": 0.8})
+    assert float(_luma(smeared).var()) < float(in_luma.var())
+
+
+def test_chroma_phase_noise_rotates_the_chroma_planes_only() -> None:
+    """Phase noise changes the chroma while the luma plane stays put."""
+    img = _random_image((32, 32), seed=5)
+    base = _apply(img)
+    out = _apply(img, {"chroma_phase_noise": 0.8})
+    assert float(np.abs(out - base).max()) > 0.1
+    assert float(np.abs(_luma(out) - _luma(base)).max()) < 0.15
+
+
+def test_luma_noise_adds_monochrome_noise() -> None:
+    """`luma_noise` raises luma variance and leaves the chroma planes equal."""
+    img = _grey()
+    out = _apply(img, {"luma_noise": 0.5})
+    delta = out - img
+    assert float(_luma(out).var()) > float(_luma(img).var()) * 1.5
+    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) < 1e-6
+
+
+def test_composite_noise_adds_noise_to_every_plane() -> None:
+    """`composite_noise` is chromatic: it moves Y, I and Q, so R and G drift apart."""
+    img = _grey()
+    delta = _apply(img, {"composite_noise": 0.5}) - img
+    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) > 0.1
+
+
+def test_snow_is_injected_in_the_signal_domain_as_monochrome_noise() -> None:
+    """Snow is luma noise before demodulation: it is grey, not coloured speckle."""
+    img = _grey()
+    delta = _apply(img, {"snow": 0.3}) - img
+    assert float(delta[:, :, 0].std()) > 0.02
+    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) < 1e-6
+    assert float(np.abs(delta[:, :, 0] - delta[:, :, 2]).max()) < 1e-6
+
+
+def test_sharpening_raises_the_luma_gradient_without_touching_chroma() -> None:
+    """Sharpening is a luma peaking operation: detail up, chroma bit-identical."""
+    stripes = np.zeros((16, 96, 3), dtype=np.float32)
+    stripes[:, ::6] = 0.65
+    stripes[:, 3::6] = 0.65
+    stripes += np.float32(0.15)
+    base = _apply(stripes)
+    out = _apply(stripes, {"sharpening": 0.6})
+    assert _horizontal_gradient(out) > _horizontal_gradient(base) * 1.2
+    assert float(np.abs(out[:, :, 0] - out[:, :, 1]).max()) < 1e-5
+
+
+@pytest.mark.parametrize("param_id", ZERO_STAGES)
+def test_each_noise_and_chroma_stage_is_a_noop_at_neutral(param_id: str) -> None:
+    """Every stage with a neutral value of 0 leaves the picture bit-identical."""
+    img = _random_image((24, 24), seed=6)
+    assert np.array_equal(_apply(img, {param_id: 0.0}), _apply(img))
+
+
+def test_tape_speed_narrows_the_bandwidth_in_order() -> None:
+    """sp keeps full detail, lp less, ep least; sp multiplies the bandwidth by 1."""
+    img = _random_image((32, 64), seed=41)
+    sp, lp, ep = (_horizontal_gradient(_apply(img, {"tape_speed": s})) for s in ("sp", "lp", "ep"))
+    assert sp > lp > ep, (sp, lp, ep)
+    assert np.array_equal(_apply(img, {"tape_speed": "sp"}), _apply(img))
+
+
+def test_tracking_noise_shifts_whole_scan_lines_horizontally() -> None:
+    """Every row of the output is a horizontal roll of the same row of the base image."""
+    img = _random_image((32, 32), seed=51)
+    base = _apply(img)
+    out = _apply(img, {"tracking_noise": 0.6})
+    moved = 0
+    for row in range(img.shape[0]):
+        best = min(
+            float(np.abs(out[row] - np.roll(base[row], s, axis=0)).max()) for s in range(-16, 17)
+        )
+        assert best < 1e-3, (row, best)
+        moved += not np.allclose(out[row], base[row])
+    assert moved > img.shape[0] // 2
+
+
+def test_each_preset_produces_a_distinct_output_on_the_same_input() -> None:
+    """The six presets differ from each other and from the input by a real margin."""
+    assert len(PRESET_NAMES) == 6
+    assert set(PRESET_NAMES) == set(PRESETS)
+    img = _random_image((48, 48), seed=11)
+    outputs = [_apply(img, PRESETS[name]) for name in PRESET_NAMES]
+    for index, name in enumerate(PRESET_NAMES):
+        assert float(np.abs(outputs[index] - img).mean()) > 0.01, name
+        for other in range(index + 1, len(PRESET_NAMES)):
+            difference = float(np.abs(outputs[index] - outputs[other]).mean())
+            assert difference > 0.02, (name, PRESET_NAMES[other], difference)
+
+
+def test_preset_returns_a_copy_of_the_overrides() -> None:
+    """`preset` hands back a fresh dict, so a caller cannot corrupt the table."""
+    overrides = preset("Static")
+    assert overrides == PRESETS["Static"]
+    overrides["snow"] = 0.0
+    assert PRESETS["Static"]["snow"] == 0.6
+
+
+def test_preset_rejects_an_unknown_name() -> None:
+    """An unknown preset name raises KeyError and names the offending value."""
+    with pytest.raises(KeyError, match="no such tape"):
+        preset("no such tape")
+
+
+def test_simple_mode_exposes_exactly_four_parameters() -> None:
+    """The simple mode is four parameters, each one a real parameter of the effect."""
+    simple = params_for_mode("simple")
+    assert len(simple) == 4
+    assert tuple(spec.id for spec in simple) == SIMPLE_PARAM_IDS
+    assert len(set(SIMPLE_PARAM_IDS)) == 4
+    assert set(SIMPLE_PARAM_IDS) <= {spec.id for spec in params_for_mode("advanced")}
+
+
+def test_advanced_mode_exposes_the_full_parameter_set() -> None:
+    """The advanced toggle reveals every parameter, the simple four being the same objects."""
+    advanced = params_for_mode("advanced")
+    assert tuple(spec.id for spec in advanced) == tuple(NEUTRAL)
+    assert len(advanced) == 14 > len(params_for_mode("simple"))
+    by_id = {spec.id: spec for spec in advanced}
+    for spec in params_for_mode("simple"):
+        assert by_id[spec.id] is spec
+
+
+def test_unknown_mode_raises_value_error() -> None:
+    """A mode outside MODES is rejected and the message lists the valid ones."""
+    assert MODES == ("simple", "advanced")
+    with pytest.raises(ValueError, match="simple"):
+        params_for_mode("expert")
+
+
+def test_simple_mode_parameters_reach_the_effect() -> None:
+    """Each simple-mode slider really changes the output on its own."""
+    img = _random_image((32, 32), seed=61)
+    base = _apply(img)
+    for param_id in SIMPLE_PARAM_IDS:
+        value = 0.4 if param_id == "bandwidth" else 0.5
+        assert not np.allclose(_apply(img, {param_id: value}), base, atol=1e-4), param_id
+
+
+def test_every_parameter_label_is_a_distinct_honest_catalogue_key() -> None:
+    """Each label names its own parameter: no two share one, and LABEL_NOTES covers them."""
+    info = get_effect("ntsc")
+    labels = [spec.label for spec in info.params]
+    assert len(set(labels)) == len(labels), labels
+    assert set(LABEL_NOTES) == set(NEUTRAL)
+    assert all(LABEL_NOTES[spec.id] for spec in info.params)

CODER NOTES AND DEVIATIONS (L17, attempt 2)
- E1 labels : catalogue i18n gelé hors owns ; remplacement par les clés qui VEULENT DIRE le
  paramètre, toutes distinctes + LABEL_NOTES. Carte future owns en.json → clés dédiées.
- E1 head_switching : « displaces the bottom edge » sans unité ; gardé 0..1 (fraction de largeur,
  plafonnée 0.5) pour rester dans la plage du ParamSpec.
- ringing et band_height sont conditionnels (agissent avec bandwidth<1 / head_switching>0) ;
  le test de vivacité par paramètre fournit la porte (GATES) + documentation.
- 5 échecs test_glyph_shape viennent du retry L7 en vol (fichier d'une autre carte), sans rapport.
