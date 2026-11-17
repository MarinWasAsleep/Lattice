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

### L16 · Channel shift
- wave: 2 · deps: L2 · executor: OMH quick · review: full · size: S
- owns: `lattice_core/effects/channel_shift.py`, `tests/test_channel_shift.py`
- context: §15
- spec: implement §15. Per-channel translate, scale, radial. R and B pushed opposite by default.
  Per-channel effect assignment via a channel bitmask. Options: `amount`, `mode`, `channels`.
- accept:
  - `amount = 0` returns the input unchanged.
  - `mode: "translate"` shifts R and B in opposite directions by default.
  - `channels` restricted to R leaves G and B untouched.
  - `mode: "radial"` produces a larger shift at the edges than at the centre.
  - output shape equals input shape.

GATE RESULTS (L16, attempt 1 — hy4-flash-free, 3e carte du tier masse)
- Owned tests : **26 passed**, ruff clean. Suite complète : **1629 passed, 1 skipped**.
- Registre des effets vérifié (import du paquet) — channel_shift câblé par l'orchestrateur
  (patch effects/__init__.py, pattern DEV-208). 12 effets au total.
- hy4 tier masse : L4 (code final correct), L13 (strict 1er essai), L16 (1er essai).

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 5ca16b9..53a169a 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import feedback, glitch, halftone, tone  # noqa: F401
+from lattice_core.effects import channel_shift, feedback, glitch, halftone, tone  # noqa: F401
diff --git a/lattice_core/effects/channel_shift.py b/lattice_core/effects/channel_shift.py
new file mode 100644
index 0000000..edabb7d
--- /dev/null
+++ b/lattice_core/effects/channel_shift.py
@@ -0,0 +1,102 @@
+"""Channel shift effect: per-channel translate, scale and radial offset (CONTRACT §15)."""
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
+_MODES = ("translate", "scale", "radial")
+_DIRECTIONS = np.array([-1.0, 0.0, 1.0], dtype=np.float32)
+DEFAULT_CHANNELS = 0b101  # R and B: the chromatic-aberration pair.
+_MIN_RADIUS = 0.5
+_MIN_SCALE_FACTOR = 0.1
+
+_AMOUNT = ParamSpec("amount", "Amount (px)", "float", 4.0, 0.0, 50.0, 0.5)
+_MODE = ParamSpec("mode", "Scale", "choice", "translate", choices=_MODES)
+_CHANNELS = ParamSpec("channels", "Per channel", "int", DEFAULT_CHANNELS, 0, 7, 1)
+_PARAMS = (_AMOUNT, _MODE, _CHANNELS)
+
+
+def validate_params(params: Mapping[str, object]) -> dict:
+    """Validate amount, mode and the 3-bit channel mask, naming offending values."""
+    amount = float(params.get("amount", 4.0))
+    if not np.isfinite(amount) or amount < 0.0:
+        raise ValueError(f"amount must be finite and non-negative, got {amount!r}")
+    mode = str(params.get("mode", "translate"))
+    if mode not in _MODES:
+        raise ValueError(f"unknown channel shift mode: {mode!r}")
+    channels = int(params.get("channels", DEFAULT_CHANNELS))
+    if not 0 <= channels <= 0b111:
+        raise ValueError(f"channels must be a 3-bit mask, got {channels!r}")
+    return {"amount": amount, "mode": mode, "channels": channels}
+
+
+def _grid(height: int, width: int) -> tuple[np.ndarray, ...]:
+    """Return float32 coordinate and centre-from-centre maps for an (H, W) image."""
+    xs = np.arange(width, dtype=np.float32)[None, :]
+    ys = np.arange(height, dtype=np.float32)[:, None]
+    cx = np.float32((width - 1) / 2.0)
+    cy = np.float32((height - 1) / 2.0)
+    return xs, ys, xs - cx, ys - cy, cx, cy
+
+
+def _sample(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
+    """Bilinearly sample a 2-D channel at float coordinates, replicating edges."""
+    height, width = channel.shape
+    x0 = np.floor(sx).astype(np.intp)
+    y0 = np.floor(sy).astype(np.intp)
+    fx = (sx - x0).astype(np.float32)
+    fy = (sy - y0).astype(np.float32)
+    np.clip(x0, 0, width - 1, out=x0)
+    np.clip(y0, 0, height - 1, out=y0)
+    x1 = np.clip(x0 + 1, 0, width - 1)
+    y1 = np.clip(y0 + 1, 0, height - 1)
+    one = np.float32(1.0)
+    top = channel[y0, x0] * (one - fx) + channel[y0, x1] * fx
+    bottom = channel[y1, x0] * (one - fx) + channel[y1, x1] * fx
+    return top * (one - fy) + bottom * fy
+
+
+def _coordinates(
+    mode: str, direction: float, amount: float, grid: tuple[np.ndarray, ...]
+) -> tuple[np.ndarray, np.ndarray]:
+    """Return float sample coordinates for one channel under the selected mode."""
+    xs, ys, dx, dy, cx, cy = grid
+    if mode == "translate":
+        return xs - np.float32(direction * amount), ys
+    radius = max(float(np.hypot(float(cx), float(cy))), _MIN_RADIUS)
+    strength = np.float32(direction * amount / radius)
+    if mode == "radial":
+        return xs - strength * dx, ys - strength * dy
+    factor = np.float32(max(_MIN_SCALE_FACTOR, 1.0 + float(strength)))
+    return cx + dx / factor, cy + dy / factor
+
+
+def shift(img: Image, params: Mapping[str, object] | None = None) -> Image:
+    """Return the channel-shifted image, leaving the input untouched."""
+    cfg = validate_params(params or {})
+    source = np.asarray(img, dtype=np.float32)
+    out = np.array(source, dtype=np.float32, copy=True, order="C")
+    if cfg["amount"] == 0.0 or cfg["channels"] == 0:
+        return out
+    if source.ndim != 3 or source.shape[2] < 3:
+        return out
+    grid = _grid(source.shape[0], source.shape[1])
+    for channel in range(3):
+        if not cfg["channels"] & (1 << channel):
+            continue
+        sx, sy = _coordinates(
+            cfg["mode"], float(_DIRECTIONS[channel]), cfg["amount"], grid
+        )
+        out[:, :, channel] = _sample(source[:, :, channel], sx, sy)
+    return np.clip(out, 0.0, 1.0, out=out)
+
+
+@register_effect("channel_shift", "Channel Shift", _PARAMS)
+def channel_shift(img: Image, params: dict, rng: np.random.Generator) -> Image:
+    """Apply the per-channel shift; deterministic, so rng is accepted but unused."""
+    return shift(img, params)
diff --git a/tests/test_channel_shift.py b/tests/test_channel_shift.py
new file mode 100644
index 0000000..e37d504
--- /dev/null
+++ b/tests/test_channel_shift.py
@@ -0,0 +1,143 @@
+"""Tests for the L16 channel shift effect (CONTRACT §15)."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+from lattice_core.effects.channel_shift import (
+    DEFAULT_CHANNELS,
+    channel_shift,
+    validate_params,
+)
+from lattice_core.registry import get_effect, resolve_params
+
+MODES = ("translate", "scale", "radial")
+SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))
+
+
+def _apply(
+    img: np.ndarray, params: dict | None = None, seed: int = 0
+) -> np.ndarray:
+    """Run the registered effect with resolved params and a seeded generator."""
+    info = get_effect("channel_shift")
+    resolved = resolve_params(info.params, dict(params or {}))
+    return info.fn(img.copy(), resolved, np.random.default_rng(seed))
+
+
+def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
+    """Return a seeded random float32 RGB image of shape (H, W, 3)."""
+    return np.random.default_rng(seed).random((shape[0], shape[1], 3), dtype=np.float32)
+
+
+def test_registration_matches_card() -> None:
+    """The module registers one effect with the three documented options."""
+    info = get_effect("channel_shift")
+    assert info.fn is channel_shift
+    assert tuple(spec.id for spec in info.params) == ("amount", "mode", "channels")
+    assert tuple(spec.default for spec in info.params) == (4.0, "translate", DEFAULT_CHANNELS)
+    assert info.params[1].choices == MODES
+    assert DEFAULT_CHANNELS == 0b101
+
+
+def test_amount_zero_returns_input_unchanged() -> None:
+    """A zero amount yields an unchanged copy for every mode and mask."""
+    img = _random_image((13, 17))
+    for mode in MODES:
+        out = _apply(img, {"amount": 0.0, "mode": mode, "channels": 0b111})
+        np.testing.assert_array_equal(out, img)
+        assert out.dtype == np.float32
+
+
+def test_amount_zero_does_not_mutate_input() -> None:
+    """The source array is never written to, even on the no-op path."""
+    img = _random_image((9, 11), seed=5)
+    before = img.copy()
+    out = channel_shift(img, {"amount": 0.0}, np.random.default_rng(0))
+    np.testing.assert_array_equal(img, before)
+    np.testing.assert_array_equal(out, before)
+    assert out is not img
+
+
+def test_translate_shifts_red_and_blue_in_opposite_directions() -> None:
+    """A translate shifts R left and B right by the same amount; G stays put."""
+    width = 17
+    img = np.zeros((1, width, 3), dtype=np.float32)
+    img[0, 8, 0] = 1.0
+    img[0, 8, 2] = 1.0
+    img[:, :, 1] = 0.25
+    out = _apply(img, {"amount": 2.0, "mode": "translate", "channels": 0b111})
+    red_x = int(np.argmax(out[0, :, 0]))
+    blue_x = int(np.argmax(out[0, :, 2]))
+    assert red_x == 6
+    assert blue_x == 10
+    assert blue_x - red_x == 4
+    np.testing.assert_array_equal(out[:, :, 1], img[:, :, 1])
+
+
+def test_channels_restricted_to_r_leaves_g_and_b_untouched() -> None:
+    """A mask of R only changes the red channel; a zero mask changes nothing."""
+    img = _random_image((24, 32))
+    params = {"amount": 3.0, "mode": "translate", "channels": 0b001}
+    out = _apply(img, params)
+    np.testing.assert_array_equal(out[:, :, 1], img[:, :, 1])
+    np.testing.assert_array_equal(out[:, :, 2], img[:, :, 2])
+    assert not np.array_equal(out[:, :, 0], img[:, :, 0])
+    unchanged = _apply(img, {**params, "channels": 0})
+    np.testing.assert_array_equal(unchanged, img)
+
+
+def test_radial_shifts_edges_more_than_the_centre() -> None:
+    """The radial displacement grows with distance from the image centre."""
+    width = 33
+    centre = (width - 1) // 2
+    params = {"amount": 8.0, "mode": "radial", "channels": 0b001}
+
+    def displacement(x: int) -> float:
+        """Return how far a one-pixel red marker at column x is moved."""
+        img = np.zeros((1, width, 3), dtype=np.float32)
+        img[0, x, 0] = 1.0
+        out = _apply(img, params)
+        reached = float(np.average(np.arange(width), weights=out[0, :, 0]))
+        return abs(reached - x)
+
+    centre_shift = displacement(centre)
+    edge_shift = displacement(width - 3)
+    assert centre_shift < 0.5
+    assert edge_shift > centre_shift + 1.0
+
+
+@pytest.mark.parametrize("shape", SHAPES)
+@pytest.mark.parametrize("mode", MODES)
+def test_output_shape_dtype_and_no_mutation(shape: tuple[int, int], mode: str) -> None:
+    """Every mode preserves shape and dtype and leaves the input untouched."""
+    img = _random_image(shape, seed=13)
+    before = img.copy()
+    out = channel_shift(
+        img, {"amount": 2.0, "mode": mode, "channels": 0b111}, np.random.default_rng(0)
+    )
+    assert out.shape == img.shape
+    assert out.dtype == np.float32
+    assert out.flags["C_CONTIGUOUS"]
+    np.testing.assert_array_equal(img, before)
+
+
+def test_output_is_deterministic_and_bounded() -> None:
+    """The effect ignores rng and always returns values inside [0, 1]."""
+    img = _random_image((29, 41), seed=3)
+    params = {"amount": 5.0, "mode": "radial", "channels": 0b111}
+    first = _apply(img, params, seed=1)
+    second = _apply(img, params, seed=99)
+    np.testing.assert_array_equal(first, second)
+    assert np.isfinite(first).all()
+    assert first.min() >= 0.0
+    assert first.max() <= 1.0
+
+
+@pytest.mark.parametrize(
+    "params", [{"mode": "warp"}, {"amount": -1.0}, {"amount": np.nan}, {"channels": 8}]
+)
+def test_invalid_params_raise(params: dict) -> None:
+    """Unknown modes, negative amounts and out-of-range masks are rejected."""
+    with pytest.raises(ValueError):
+        validate_params(params)

CODER NOTES AND DEVIATIONS (L16, attempt 1)
- masque channels bit0=R, bit1=G, bit2=B, défaut 0b101 ; directions R=-1, G=0, B=+1 ;
  scale = zoom radial, radial = déplacement radial additif ; échantillonnage bilinéaire bords
  répliqués ; labels ParamSpec du catalogue i18n figé ; registration register_effect à l'import.
- Aucune déviation E-déclarée.
