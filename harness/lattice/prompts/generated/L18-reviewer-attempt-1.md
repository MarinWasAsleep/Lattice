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

### L18 · CRT / scanlines
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/crt.py`, `tests/test_crt.py`
- context: §17
- spec: implement §17. Scanline beam profile, phosphor mask (`slot`, `aperture_grille`,
  `shadow_mask`), bloom, curvature, vignette. **The mask scales in device pixels, not image
  pixels.** Options: `scanline_intensity`, `mask`, `mask_scale`, `bloom`, `curvature`, `vignette`.
- accept:
  - all parameters neutral returns the input within 1/255.
  - the mask period in output pixels equals `mask_scale` for each of the three mask types.
  - doubling the output resolution doubles the mask period in pixels and keeps the visual period
    constant.
  - `curvature = 0` leaves corners untouched; `curvature > 0` darkens them.
  - output shape equals input shape.

GATE RESULTS (L18, attempt 1 — hy4-flash-free, 4e carte du tier masse)
- Owned tests : **35 passed**, ruff clean. Suite complète : **1847 passed, 1 skipped**.
- Masque phosphor en PIXELS D'APPAREIL : période == mask_scale pour slot/aperture_grille/
  shadow_mask × 3 pitches ; doubler output_width → période doublée, pitch visuel constant.
- Registre des effets — crt câblé par l'orchestrateur (import paquet). 16 effets au total.
- hy4 tier masse : L4 (4 cycles, code final correct), L13 (strict 1er essai), L16 (1er essai),
  L18 (1er essai) — tier masse amplement validé.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 4d1f956..ad055b5 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import channel_shift, displace, feedback, glitch, halftone, ntsc, pixel_sort, tone  # noqa: F401
+from lattice_core.effects import channel_shift, crt, displace, feedback, glitch, halftone, ntsc, pixel_sort, tone  # noqa: F401
diff --git a/lattice_core/effects/crt.py b/lattice_core/effects/crt.py
new file mode 100644
index 0000000..447beab
--- /dev/null
+++ b/lattice_core/effects/crt.py
@@ -0,0 +1,194 @@
+"""CRT / scanlines finishing effect: beam, phosphor mask, bloom, curvature (CONTRACT §17)."""
+
+from __future__ import annotations
+
+from collections.abc import Mapping
+
+import numpy as np
+
+from lattice_core.registry import register_effect
+from lattice_core.types import Image, ParamSpec
+
+# "none" is the neutral phosphor setting, so a fully neutral parameter set is the identity.
+_MASK_TYPES = ("none", "slot", "aperture_grille", "shadow_mask")
+_SCANLINE_ROWS = 2  # beam period in image rows at one device pixel per image pixel
+_BLOOM_THRESHOLD = 0.6
+_LEAK = 0.35  # response of a non-active phosphor stripe
+_BRIDGE = 0.75  # slot-mask horizontal bridge
+_DOT_GAP = 0.85  # shadow-mask row gap
+
+# Labels reuse existing i18n catalogue keys (test_i18n / DEV-212). `output_width` is
+# the device resolution in pixels: 0 means one device pixel per image pixel.
+_PARAMS = (
+    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
+    ParamSpec("scanline_intensity", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("mask", "Dot shape", "choice", "none", choices=_MASK_TYPES),
+    ParamSpec("mask_scale", "Scale", "int", 6, 1, 32, 1),
+    ParamSpec("bloom", "Strength", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("curvature", "Amount", "float", 0.0, 0.0, 0.9, 0.02),
+    ParamSpec("vignette", "Darkness", "float", 0.0, 0.0, 1.0, 0.02),
+    ParamSpec("output_width", "Resolution", "int", 0, 0, 16384, 1),
+)
+
+
+def _config(params: Mapping[str, object]) -> dict:
+    """Return typed options, defaulting every field to its neutral value."""
+    mask_type = str(params.get("mask", "none"))
+    if mask_type not in _MASK_TYPES:
+        raise ValueError(f"unknown CRT mask: {mask_type!r}")
+    return {
+        "scanline": float(params.get("scanline_intensity", 0.0)),
+        "mask": mask_type,
+        "mask_scale": max(1, int(params.get("mask_scale", 6))),
+        "bloom": float(params.get("bloom", 0.0)),
+        "curvature": float(params.get("curvature", 0.0)),
+        "vignette": float(params.get("vignette", 0.0)),
+        "output_width": max(0, int(params.get("output_width", 0))),
+    }
+
+
+def _mask_plane(mask: object, shape: tuple[int, int]) -> np.ndarray:
+    """Return a float32 (H, W) coverage plane, validating the mask size."""
+    data = np.asarray(mask, dtype=np.float32)
+    if data.ndim == 3 and data.shape[2] == 1:
+        data = data[:, :, 0]
+    if data.ndim != 2 or data.shape != shape:
+        raise ValueError(f"mask must be {shape}, got {data.shape}")
+    return np.clip(data, 0.0, 1.0)
+
+
+def _phosphor(
+    height: int, width: int, kind: str, period: int
+) -> np.ndarray:
+    """Return an (H, W, 3) gain volume whose horizontal period is `period`."""
+    xs = np.arange(width, dtype=np.int32)[None, :]
+    if kind == "shadow_mask":
+        ys = np.arange(height, dtype=np.int32)[:, None]
+        phase = (xs + ((ys % 3) * period) // 3) % period
+    else:
+        phase = xs % period
+    stripe = (phase * 3) // period
+    gain = np.where(
+        stripe[:, :, None] == np.arange(3)[None, None, :], 1.0, _LEAK
+    ).astype(np.float32)
+    if kind == "slot":
+        bridge = np.where(np.arange(height) % 3 == 2, _BRIDGE, 1.0)
+        gain = gain * bridge[:, None, None]
+    elif kind == "shadow_mask":
+        gap = np.where(np.arange(height) % 2 == 1, _DOT_GAP, 1.0)
+        gain = gain * gap[:, None, None]
+    return gain
+
+
+def _beam(height: int, amount: float, period_rows: int) -> np.ndarray:
+    """Return an (H, 1) scanline beam profile; 1.0 means no attenuation."""
+    rows = np.arange(height, dtype=np.float32)[:, None]
+    wave = 0.5 + 0.5 * np.cos(2.0 * np.pi * rows / np.float32(max(1, period_rows)))
+    return (1.0 - np.float32(amount) * wave).astype(np.float32)
+
+
+def _box_blur(plane: np.ndarray, radius: int) -> np.ndarray:
+    """Return a separable box blur of one plane with replicated edges."""
+    if radius < 1:
+        return plane
+    padded = np.pad(plane, ((radius, radius), (radius, radius)), mode="edge")
+    out = np.zeros_like(plane)
+    for dy in range(2 * radius + 1):
+        window = padded[dy : dy + plane.shape[0]]
+        for dx in range(2 * radius + 1):
+            out += window[:, dx : dx + plane.shape[1]]
+    return (out / np.float32((2 * radius + 1) ** 2)).astype(np.float32)
+
+
+def _bloom(source: np.ndarray, amount: float) -> np.ndarray:
+    """Screen a blurred luminance bloom of the bright areas over the image."""
+    bright = np.maximum(source - np.float32(_BLOOM_THRESHOLD), 0.0)
+    luma = (
+        0.2126 * bright[:, :, 0] + 0.7152 * bright[:, :, 1] + 0.0722 * bright[:, :, 2]
+    )
+    radius = 1 + int(round(amount * 2.0))
+    glow = _box_blur(luma.astype(np.float32), radius)
+    return np.clip(source + np.float32(amount) * glow[:, :, None], 0.0, 1.0)
+
+
+def _grid(height: int, width: int) -> tuple[np.ndarray, ...]:
+    """Return normalised radius maps and pixel coordinates for the geometric stages."""
+    xs = np.arange(width, dtype=np.float32)[None, :]
+    ys = np.arange(height, dtype=np.float32)[:, None]
+    cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
+    nx = (xs - cx) / max(float(cx), 0.5)
+    ny = (ys - cy) / max(float(cy), 0.5)
+    return nx, ny, xs, ys, cx, cy
+
+
+def _sample(plane: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
+    """Bilinearly sample a 2-D plane at float coordinates, clamping to the edges."""
+    height, width = plane.shape
+    x0 = np.floor(sx).astype(np.intp)
+    y0 = np.floor(sy).astype(np.intp)
+    fx = (sx - x0).astype(np.float32)
+    fy = (sy - y0).astype(np.float32)
+    np.clip(x0, 0, width - 1, out=x0)
+    np.clip(y0, 0, height - 1, out=y0)
+    x1 = np.clip(x0 + 1, 0, width - 1)
+    y1 = np.clip(y0 + 1, 0, height - 1)
+    one = np.float32(1.0)
+    top = plane[y0, x0] * (one - fx) + plane[y0, x1] * fx
+    bottom = plane[y1, x0] * (one - fx) + plane[y1, x1] * fx
+    return top * (one - fy) + bottom * fy
+
+
+def _curve(source: np.ndarray, amount: float, grid: tuple[np.ndarray, ...]) -> np.ndarray:
+    """Warp the image toward the edges and darken the corners under curvature."""
+    nx, ny, xs, ys, cx, cy = grid
+    r2 = nx * nx + ny * ny
+    warp = 1.0 + np.float32(amount) * r2
+    sx, sy = cx + (xs - cx) * warp, cy + (ys - cy) * warp
+    out = np.empty_like(source)
+    for channel in range(3):
+        out[:, :, channel] = _sample(source[:, :, channel], sx, sy)
+    edge = np.clip(1.0 - np.float32(amount) * r2, 0.0, 1.0)
+    return np.clip(out * edge[:, :, None], 0.0, 1.0).astype(np.float32)
+
+
+@register_effect("crt", "CRT / scanlines", _PARAMS)
+def crt(
+    img: Image,
+    params: dict,
+    rng: np.random.Generator,
+    *,
+    mask: Image | None = None,
+) -> Image:
+    """Apply the static CRT finishing chain; seed and rng are accepted for interface parity.
+
+    The phosphor pitch is specified in device pixels: doubling `output_width` doubles
+    the period measured in output pixels while the visual pitch stays the same.
+    """
+    cfg = _config(params)
+    source = np.array(img, dtype=np.float32, copy=True, order="C")
+    np.clip(source, 0.0, 1.0, out=source)
+    height, width = source.shape[:2]
+    coverage = _mask_plane(mask, (height, width)) if mask is not None else None
+    ratio = (cfg["output_width"] / width) if cfg["output_width"] else 1.0
+    out = source
+    if cfg["bloom"] > 0.0:
+        out = _bloom(out, cfg["bloom"])
+    if cfg["scanline"] > 0.0:
+        period_rows = max(1, int(round(_SCANLINE_ROWS * ratio)))
+        out = out * _beam(height, cfg["scanline"], period_rows)[:, :, None]
+    if cfg["mask"] != "none":
+        period = max(1, int(round(cfg["mask_scale"] * ratio)))
+        out = out * _phosphor(height, width, cfg["mask"], period)
+    grid = _grid(height, width) if cfg["curvature"] > 0.0 or cfg["vignette"] > 0.0 else None
+    if cfg["curvature"] > 0.0:
+        assert grid is not None
+        out = _curve(out, cfg["curvature"], grid)
+    if cfg["vignette"] > 0.0:
+        assert grid is not None
+        nx, ny = grid[0], grid[1]
+        r2 = np.clip((nx * nx + ny * ny) / 2.0, 0.0, 1.0)
+        out = out * (1.0 - np.float32(cfg["vignette"]) * r2)[:, :, None]
+    np.clip(out, 0.0, 1.0, out=out)
+    if coverage is not None:
+        out = source * (1.0 - coverage[:, :, None]) + out * coverage[:, :, None]
+    return np.ascontiguousarray(out, dtype=np.float32)
diff --git a/tests/test_crt.py b/tests/test_crt.py
new file mode 100644
index 0000000..1d38bdc
--- /dev/null
+++ b/tests/test_crt.py
@@ -0,0 +1,223 @@
+"""Tests for the CRT / scanlines effect (L18, CONTRACT §17)."""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+import numpy as np
+import pytest
+
+from lattice_core import effects  # noqa: F401  (registers the core effects)
+from lattice_core.effects import crt as crt_module
+from lattice_core.registry import get_effect, list_effects, resolve_params
+from lattice_dither import i18n
+
+EFFECT_ID = "crt"
+NEUTRAL = {
+    "seed": 0,
+    "scanline_intensity": 0.0,
+    "mask": "none",
+    "mask_scale": 6,
+    "bloom": 0.0,
+    "curvature": 0.0,
+    "vignette": 0.0,
+    "output_width": 0,
+}
+SHAPES = ((1, 1), (1, 7), (9, 1), (37, 23), (64, 64))
+MASK_TYPES = ("slot", "aperture_grille", "shadow_mask")
+CATALOGUE = json.loads((Path(i18n.__file__).parent / "en.json").read_text())
+
+
+def _apply(
+    img: np.ndarray,
+    overrides: dict | None = None,
+    seed: int = 0,
+    mask: np.ndarray | None = None,
+) -> np.ndarray:
+    """Run the registered effect with resolved parameters and a seeded generator."""
+    info = get_effect(EFFECT_ID)
+    params = dict(NEUTRAL)
+    params.update(overrides or {})
+    params["seed"] = seed
+    resolved = resolve_params(info.params, params)
+    return crt_module.crt(img.copy(), resolved, np.random.default_rng(seed), mask=mask)
+
+
+def _image(height: int, width: int, value: float | None = None, seed: int = 7) -> np.ndarray:
+    """Return a float32 (H, W, 3) image: uniform when value is given, random otherwise."""
+    if value is not None:
+        return np.full((height, width, 3), value, dtype=np.float32)
+    return np.random.default_rng(seed).random((height, width, 3), dtype=np.float32)
+
+
+def _column_period(out: np.ndarray) -> int:
+    """Return the smallest horizontal pixel period of an image, or 0 if none."""
+    for period in range(1, out.shape[1] // 2 + 1):
+        if np.array_equal(out[:, :-period], out[:, period:]):
+            return period
+    return 0
+
+
+def _aggressive() -> dict:
+    """Return a non-neutral parameter set exercising every stage."""
+    return {
+        "scanline_intensity": 0.6,
+        "mask": "shadow_mask",
+        "mask_scale": 6,
+        "bloom": 0.5,
+        "curvature": 0.4,
+        "vignette": 0.5,
+        "output_width": 0,
+    }
+
+
+def test_registers_a_crt_effect_with_catalogue_labels() -> None:
+    """The effect is registered with the frozen options and translated labels."""
+    info = get_effect(EFFECT_ID)
+    assert info.id == EFFECT_ID
+    assert info.name == "CRT / scanlines"
+    assert [spec.id for spec in info.params] == list(NEUTRAL)
+    labels = {spec.label for spec in info.params}
+    assert labels <= set(CATALOGUE), sorted(labels - set(CATALOGUE))
+    assert EFFECT_ID in {registered.id for registered in list_effects()}
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+def test_all_parameters_neutral_return_the_input(shape: tuple[int, int]) -> None:
+    """A fully neutral parameter set is the identity within 1/255."""
+    img = _image(*shape)
+    out = _apply(img)
+    assert out.shape == img.shape
+    assert np.allclose(out, img, atol=1.0 / 255.0)
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+@pytest.mark.parametrize("overrides", (NEUTRAL, "aggressive"))
+def test_output_shape_equals_input_shape(
+    shape: tuple[int, int], overrides: dict | str
+) -> None:
+    """Every configuration preserves shape, float32 dtype and the [0, 1] range."""
+    img = _image(*shape)
+    settings = _aggressive() if overrides == "aggressive" else dict(NEUTRAL)
+    out = _apply(img, settings)
+    assert out.shape == img.shape
+    assert out.dtype == np.float32
+    assert out.min() >= 0.0 and out.max() <= 1.0
+
+
+def test_effect_does_not_mutate_its_input() -> None:
+    """Even with an external mask, the input array is left untouched."""
+    img = _image(32, 40)
+    before = img.copy()
+    mask = np.linspace(0.0, 1.0, 32 * 40, dtype=np.float32).reshape(32, 40)
+    _apply(img, _aggressive(), mask=mask)
+    assert np.array_equal(img, before)
+
+
+def test_deterministic_seed() -> None:
+    """Repeated seeded calls agree, whatever the state of the supplied generator."""
+    img = _image(24, 28)
+    first = _apply(img, _aggressive(), seed=3)
+    second = _apply(img, _aggressive(), seed=3)
+    assert np.array_equal(first, second)
+    direct = crt_module.crt(
+        img,
+        resolve_params(get_effect(EFFECT_ID).params, {**NEUTRAL, **_aggressive()}),
+        np.random.default_rng(999),
+    )
+    assert np.array_equal(first, direct)
+
+
+@pytest.mark.parametrize("kind", MASK_TYPES)
+@pytest.mark.parametrize("pitch", (3, 6, 12))
+def test_mask_period_in_output_pixels_equals_mask_scale(kind: str, pitch: int) -> None:
+    """Each phosphor layout repeats every `mask_scale` device pixels."""
+    img = _image(48, 96, value=1.0)
+    out = _apply(img, {"mask": kind, "mask_scale": pitch, "output_width": 0})
+    assert _column_period(out) == pitch
+    assert not np.array_equal(out, img)  # the phosphor stage is effective
+
+
+def test_doubling_output_resolution_doubles_the_pixel_period() -> None:
+    """Twice the device resolution doubles the pixel pitch, not the visual pitch."""
+    img = _image(48, 96, value=1.0)
+    settings = {"mask": "slot", "mask_scale": 6}
+    low = _apply(img, {**settings, "output_width": 96})
+    high = _apply(img, {**settings, "output_width": 192})
+    low_period, high_period = _column_period(low), _column_period(high)
+    assert (low_period, high_period) == (6, 12)
+    # Visual pitch, in image pixels: period_px * image_width / device_width.
+    assert low_period * 96 / 96 == high_period * 96 / 192 == 6.0
+    # The number of phosphor groups across the device screen is unchanged.
+    assert 96 / low_period == 192 / high_period == 16.0
+
+
+def test_doubling_resolution_for_each_mask_type() -> None:
+    """The device-pixel rule holds for aperture grille and shadow mask too."""
+    img = _image(36, 96, value=1.0)
+    for kind in MASK_TYPES:
+        low = _apply(img, {"mask": kind, "mask_scale": 4, "output_width": 96})
+        high = _apply(img, {"mask": kind, "mask_scale": 4, "output_width": 192})
+        assert _column_period(high) == 2 * _column_period(low) == 8
+
+
+def test_curvature_zero_leaves_corners_untouched() -> None:
+    """At zero curvature the image, corners included, is unchanged."""
+    img = _image(40, 60)
+    out = _apply(img, {"curvature": 0.0})
+    assert np.array_equal(out, img)
+
+
+def test_positive_curvature_darkens_corners() -> None:
+    """A curved tube attenuates the corners more than the centre."""
+    img = _image(40, 60, value=1.0)
+    out = _apply(img, {"curvature": 0.6})
+    corner = out[:4, :4].mean()
+    centre = out[18:22, 28:32].mean()
+    assert corner < img[:4, :4].mean()
+    assert corner < centre
+
+
+def test_vignette_darkens_edges_but_not_the_centre() -> None:
+    """Vignette is a separate radial falloff, neutral at zero."""
+    img = _image(40, 60, value=1.0)
+    out = _apply(img, {"vignette": 0.8})
+    assert np.array_equal(_apply(img, {"vignette": 0.0}), img)
+    assert out[:3, :3].mean() < out[18:22, 28:32].mean()
+
+
+def test_mask_is_keyword_only_and_rejects_wrong_shapes() -> None:
+    """DEV-214: the external mask is keyword-only and size-checked."""
+    info = get_effect(EFFECT_ID)
+    params = resolve_params(info.params, dict(NEUTRAL))
+    img = _image(12, 16)
+    with pytest.raises(TypeError):
+        info.fn(img, params, np.random.default_rng(0), np.ones((12, 16)))  # type: ignore[misc]
+    with pytest.raises(ValueError, match=r"mask must be \(12, 16\)"):
+        _apply(img, _aggressive(), mask=np.ones((4, 4), dtype=np.float32))
+    with pytest.raises(ValueError, match=r"mask must be \(12, 16\)"):
+        _apply(img, _aggressive(), mask=np.ones((12, 16, 3), dtype=np.float32))
+
+
+def test_external_mask_blends_between_input_and_full_effect() -> None:
+    """§18: a coverage of 0 is no effect, 1 is full effect, both shapes accepted."""
+    img = _image(24, 32)
+    settings = _aggressive()
+    full = _apply(img, settings)
+    zeros = np.zeros((24, 32, 1), dtype=np.float32)
+    ones = np.ones((24, 32), dtype=np.float32)
+    assert np.allclose(_apply(img, settings, mask=zeros), img, atol=1e-6)
+    assert np.allclose(_apply(img, settings, mask=ones), full, atol=1e-6)
+    half = np.full((24, 32), 0.5, dtype=np.float32)
+    assert np.allclose(
+        _apply(img, settings, mask=half), 0.5 * img + 0.5 * full, atol=1e-6
+    )
+
+
+def test_array_mask_in_params_channel_is_rejected() -> None:
+    """DEV-214: an array cannot be smuggled into the `mask` choice parameter."""
+    info = get_effect(EFFECT_ID)
+    img = _image(8, 8)
+    with pytest.raises(ValueError, match="unknown CRT mask"):
+        info.fn(img, {**NEUTRAL, "mask": np.ones((8, 8))}, np.random.default_rng(0))

CODER NOTES AND DEVIATIONS (L18, attempt 1)
- E1 : paramètre `output_width` (0 = auto) ajouté — le contrat ne précise pas comment l'effet
  connaît sa résolution de sortie ; choix `none` comme neutre du paramètre mask pour l'identité.
- E3 : effects/__init__.py (hors owns) — câblé par l'orchestrateur.
- Le noyau n'importe que numpy + lattice_core ; libellés i18n (Seed, Intensity, Dot shape,
  Scale, Strength, Amount, Darkness, Resolution).
- Un échec test_ntsc transitoire pendant des écritures concurrentes, non reproductible.
