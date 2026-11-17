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

### L13 · Feedback buffer
- wave: 2 · deps: L2 · executor: OMH capable · review: strict · size: M
- owns: `lattice_core/effects/feedback.py`, `tests/test_feedback.py`
- context: §12
- spec: implement §12. `f(n) = decay * T(f(n-1)) + input`, `decay` in `[0, 0.99]`, `T` in
  `{translate, rotate, scale, displace, identity}`, composable. Normalise per frame. Options:
  `decay`, `transform`, `amount`, `iterations` (1..8), `blend` (`add` | `max` | `screen`).
- accept:
  - `decay >= 1` raises `ValueError` naming the value.
  - 200 iterations on a fixed input produce no NaN and no value outside `[0, 1]`.
  - the mean converges (difference under 1e-3 between iterations 190 and 200).
  - `decay = 0` returns the input unchanged.
  - each transform produces a different output on the same input.
  - the same seed produces identical output across two calls.

GATE RESULTS (L13, attempt 1 — hy4-flash-free, 2e carte de l'épreuve masse)
- Owned tests : **71 passed** (test_feedback.py, graines déterministes), ruff clean.
- Suite complète : **1593 passed, 1 skipped** (1522 avant + 71 ; aucune régression).
- Registre des effets vérifié par l'orchestrateur : 11 effets dont `feedback` (import du paquet
  lattice_core.effects ; l'orchestrateur a câblé la ligne d'import dans effects/__init__.py,
  pattern DEV-208).
- Attention relecture : effet STRICT (L13 est listé strict dans TASKS). Vérifiez la
  récurrence decay*T(f(n-1)) + input, la normalisation par frame, l'identité bit-exacte
  decay=0 (court-circuit), le rejet decay>=1, la stabilité 200 itérations.

DIFF (arbre de travail vs HEAD)
diff --git a/lattice_core/effects/__init__.py b/lattice_core/effects/__init__.py
index 6da60e9..5ca16b9 100644
--- a/lattice_core/effects/__init__.py
+++ b/lattice_core/effects/__init__.py
@@ -1,3 +1,3 @@
 """Effect modules; importing this package registers every effect."""
 
-from lattice_core.effects import glitch, halftone, tone  # noqa: F401
+from lattice_core.effects import feedback, glitch, halftone, tone  # noqa: F401
diff --git a/lattice_core/effects/feedback.py b/lattice_core/effects/feedback.py
new file mode 100644
index 0000000..073d855
--- /dev/null
+++ b/lattice_core/effects/feedback.py
@@ -0,0 +1,197 @@
+"""Feedback buffer effect (CONTRACT §12).
+
+Iterates ``f(n) = decay * T(f(n-1)) + input`` on a float32 RGB image,
+normalising every frame so the recurrence cannot diverge.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Mapping, Sequence
+
+import numpy as np
+
+from lattice_core.registry import register_effect
+from lattice_core.types import Image, ParamSpec
+
+_TRANSFORMS: tuple[str, ...] = ("identity", "translate", "rotate", "scale", "displace")
+_BLENDS: tuple[str, ...] = ("add", "max", "screen")
+_MAX_DECAY = 0.99
+
+# Labels are drawn from the frozen i18n catalogue (lattice_dither/i18n/en.json),
+# which is outside this card's owns; no catalogue entry may be added here.
+_DECAY = ParamSpec("decay", "Strength", "float", 0.5, 0.0, _MAX_DECAY, 0.01)
+_TRANSFORM = ParamSpec("transform", "Scale", "choice", "identity", choices=_TRANSFORMS)
+_AMOUNT = ParamSpec("amount", "Amount", "float", 2.0, 0.0, 32.0, 0.5)
+_ITERATIONS = ParamSpec("iterations", "Iterations", "int", 1, 1, 8, 1)
+_BLEND = ParamSpec("blend", "Ratio", "choice", "add", choices=_BLENDS)
+_PARAMS = (_DECAY, _TRANSFORM, _AMOUNT, _ITERATIONS, _BLEND)
+
+
+def _transform_names(value: object) -> tuple[str, ...]:
+    """Return the ordered, validated transform names from a choice or a sequence."""
+    if isinstance(value, str):
+        names = tuple(part for part in value.replace(",", "+").split("+") if part)
+    elif isinstance(value, Sequence):
+        names = tuple(str(part) for part in value)
+    else:
+        names = (str(value),)
+    if not names:
+        names = ("identity",)
+    for name in names:
+        if name not in _TRANSFORMS:
+            raise ValueError(f"unknown feedback transform: {name!r}")
+    return names
+
+
+def validate_params(params: Mapping[str, object]) -> dict:
+    """Validate feedback options, rejecting decay >= 1 and naming the offending value."""
+    decay = float(params.get("decay", 0.5))
+    if not np.isfinite(decay):
+        raise ValueError(f"decay must be finite, got {decay!r}")
+    if decay >= 1.0:
+        raise ValueError(f"decay must be below 1, got {decay!r}")
+    blend = str(params.get("blend", "add"))
+    if blend not in _BLENDS:
+        raise ValueError(f"unknown feedback blend: {blend!r}")
+    return {
+        "decay": float(np.clip(decay, 0.0, _MAX_DECAY)),
+        "transform": _transform_names(params.get("transform", "identity")),
+        "amount": float(np.clip(float(params.get("amount", 2.0)), 0.0, 32.0)),
+        "iterations": max(1, int(params.get("iterations", 1))),
+        "blend": blend,
+    }
+
+
+def _grid(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
+    """Return float32 (H, W) y and x coordinate maps."""
+    ys = np.arange(height, dtype=np.float32)[:, None]
+    xs = np.arange(width, dtype=np.float32)[None, :]
+    return np.broadcast_to(ys, (height, width)), np.broadcast_to(xs, (height, width))
+
+
+def _displacement_field(
+    rng: np.random.Generator, height: int, width: int, amount: float
+) -> tuple[np.ndarray, np.ndarray]:
+    """Return seeded float32 sample coordinates for the displace transform."""
+    ys, xs = _grid(height, width)
+    scale = np.float32(amount)
+    dx = (rng.random((height, width), dtype=np.float32) - np.float32(0.5)) * scale
+    dy = (rng.random((height, width), dtype=np.float32) - np.float32(0.5)) * scale
+    return xs - dx, ys - dy
+
+
+def _sample(channel: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
+    """Bilinearly sample a 2-D channel at float coordinates, clamping to the edges."""
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
+def _apply_transform(
+    frame: np.ndarray,
+    name: str,
+    amount: float,
+    grid: tuple[np.ndarray, np.ndarray],
+    field: tuple[np.ndarray, np.ndarray] | None,
+) -> np.ndarray:
+    """Apply one spatial transform by bilinear sampling with replicated edges."""
+    if name == "identity":
+        return frame
+    ys, xs = grid
+    height, width = frame.shape[:2]
+    if name == "translate":
+        sx, sy = xs - np.float32(amount), ys
+    elif name == "rotate":
+        angle = np.float32(np.deg2rad(np.float32(amount)))
+        cos_a, sin_a = np.float32(np.cos(angle)), np.float32(np.sin(angle))
+        cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
+        ox, oy = xs - cx, ys - cy
+        sx = cx + cos_a * ox - sin_a * oy
+        sy = cy + sin_a * ox + cos_a * oy
+    elif name == "scale":
+        factor = np.float32(1.0 + amount / 10.0)
+        cx, cy = np.float32((width - 1) / 2.0), np.float32((height - 1) / 2.0)
+        sx = cx + (xs - cx) / factor
+        sy = cy + (ys - cy) / factor
+    else:
+        assert field is not None
+        sx, sy = field
+    out = np.empty_like(frame)
+    for channel in range(frame.shape[2]):
+        out[:, :, channel] = _sample(frame[:, :, channel], sx, sy)
+    return np.clip(out, 0.0, 1.0, out=out)
+
+
+def _compose(
+    frame: np.ndarray,
+    names: tuple[str, ...],
+    amount: float,
+    grid: tuple[np.ndarray, np.ndarray],
+    field: tuple[np.ndarray, np.ndarray] | None,
+) -> np.ndarray:
+    """Apply the transforms in order, so T is composable."""
+    for name in names:
+        frame = _apply_transform(frame, name, amount, grid, field)
+    return frame
+
+
+def _mix(damped: np.ndarray, source: np.ndarray, blend: str) -> np.ndarray:
+    """Combine the damped previous frame with the fixed input under `blend`."""
+    if blend == "add":
+        return damped + source
+    if blend == "max":
+        return np.maximum(damped, source)
+    one = np.float32(1.0)
+    return one - (one - damped) * (one - source)
+
+
+def _normalise(frame: np.ndarray) -> np.ndarray:
+    """Scale a frame into [0, 1] by its peak when needed, then clip."""
+    peak = float(frame.max())
+    if peak > 1.0:
+        frame = frame / np.float32(peak)
+    return np.clip(frame, 0.0, 1.0).astype(np.float32, copy=False)
+
+
+def iterate(
+    img: Image,
+    params: Mapping[str, object],
+    rng: np.random.Generator,
+    iterations: int | None = None,
+    buffer: Image | None = None,
+) -> Image:
+    """Run the feedback recurrence for `iterations` steps and return the final buffer."""
+    cfg = validate_params(params)
+    source = np.asarray(img, dtype=np.float32)
+    height, width = source.shape[:2]
+    buf = np.array(source if buffer is None else buffer, dtype=np.float32, copy=True)
+    if cfg["decay"] == 0.0:
+        return np.ascontiguousarray(buf, dtype=np.float32)
+    steps = cfg["iterations"] if iterations is None else max(1, int(iterations))
+    grid = _grid(height, width)
+    field = (
+        _displacement_field(rng, height, width, cfg["amount"])
+        if "displace" in cfg["transform"]
+        else None
+    )
+    decay = np.float32(cfg["decay"])
+    for _ in range(steps):
+        transformed = _compose(buf, cfg["transform"], cfg["amount"], grid, field)
+        buf = _normalise(_mix(decay * transformed, source, cfg["blend"]))
+    return np.ascontiguousarray(buf, dtype=np.float32)
+
+
+@register_effect("feedback", "Feedback Buffer", _PARAMS)
+def feedback(img: Image, params: dict, rng: np.random.Generator) -> Image:
+    """Iterate a normalised feedback buffer under the selected transform and blend."""
+    return iterate(img, params, rng)
diff --git a/tests/test_feedback.py b/tests/test_feedback.py
new file mode 100644
index 0000000..1de2120
--- /dev/null
+++ b/tests/test_feedback.py
@@ -0,0 +1,216 @@
+"""Tests for the feedback buffer effect (L13 / CONTRACT §12)."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+from lattice_core.effects.feedback import feedback, iterate, validate_params
+from lattice_core.registry import get_effect, resolve_params
+
+EFFECT_ID = "feedback"
+TRANSFORMS = ("identity", "translate", "rotate", "scale", "displace")
+BLENDS = ("add", "max", "screen")
+SEED = 11
+
+
+def _image(seed: int = 7, shape: tuple[int, int] = (32, 32)) -> np.ndarray:
+    """Return a deterministic non-constant float32 RGB image."""
+    rng = np.random.default_rng(seed)
+    noise = rng.random((*shape, 3), dtype=np.float32) * np.float32(0.5)
+    ramp = np.linspace(0.0, 1.0, shape[1], dtype=np.float32)[None, :, None]
+    ramp = np.repeat(ramp, shape[0], axis=0)
+    return np.ascontiguousarray(np.clip(noise + ramp, 0.0, 1.0))
+
+
+def _params(**overrides: object) -> dict:
+    """Return a full feedback parameter dict with deterministic test defaults."""
+    params: dict = {"decay": 0.5, "transform": "identity", "amount": 3.0, "iterations": 8, "blend": "add"}
+    params.update(overrides)
+    return params
+
+
+def _run(
+    img: np.ndarray,
+    params: dict,
+    seed: int = SEED,
+    iterations: int | None = None,
+) -> np.ndarray:
+    """Run the effect, or a longer iterate, with a freshly seeded generator."""
+    rng = np.random.default_rng(seed)
+    if iterations is None:
+        return feedback(img, params, rng)
+    return iterate(img, params, rng, iterations=iterations)
+
+
+def test_registration_and_params() -> None:
+    """The effect is registered with the five documented options."""
+    info = get_effect(EFFECT_ID)
+    assert info.name == "Feedback Buffer"
+    assert [spec.id for spec in info.params] == [
+        "decay",
+        "transform",
+        "amount",
+        "iterations",
+        "blend",
+    ]
+    assert resolve_params(info.params, {}) == {
+        "decay": 0.5,
+        "transform": "identity",
+        "amount": 2.0,
+        "iterations": 1,
+        "blend": "add",
+    }
+
+
+@pytest.mark.parametrize("value", [1, 1.0, 1.01, 1.5, 2.0, 100.0])
+def test_decay_at_or_above_one_raises_naming_the_value(value: object) -> None:
+    """A decay of 1 or more is rejected and the message names the offending value."""
+    with pytest.raises(ValueError) as excinfo:
+        feedback(_image(), _params(decay=value), np.random.default_rng(SEED))
+    assert str(float(value)) in str(excinfo.value) or str(value) in str(excinfo.value)
+
+
+def test_validate_params_rejects_decay_one() -> None:
+    """The public validator rejects decay >= 1 independently of the registered effect."""
+    with pytest.raises(ValueError, match="1"):
+        validate_params({"decay": 1.0})
+    assert validate_params({"decay": 0.99})["decay"] == 0.99
+    assert validate_params({"decay": -2.0})["decay"] == 0.0
+
+
+def test_decay_below_one_is_accepted() -> None:
+    """Decay values below 1, including 0.99, are accepted."""
+    out = _run(_image(), _params(decay=0.99))
+    assert np.isfinite(out).all()
+
+
+@pytest.mark.parametrize("transform", TRANSFORMS)
+@pytest.mark.parametrize("blend", BLENDS)
+def test_200_iterations_stay_finite_and_in_range(transform: str, blend: str) -> None:
+    """200 iterations on a fixed input give no NaN and no value outside [0, 1]."""
+    out = _run(
+        _image(),
+        _params(transform=transform, blend=blend),
+        iterations=200,
+    )
+    assert out.shape == (32, 32, 3)
+    assert out.dtype == np.float32
+    assert np.isfinite(out).all()
+    assert float(out.min()) >= 0.0
+    assert float(out.max()) <= 1.0
+
+
+@pytest.mark.parametrize("transform", TRANSFORMS)
+@pytest.mark.parametrize("blend", BLENDS)
+def test_mean_converges_between_iterations_190_and_200(transform: str, blend: str) -> None:
+    """The frame mean at iteration 190 differs from iteration 200 by less than 1e-3."""
+    params = _params(transform=transform, blend=blend)
+    mean_190 = float(_run(_image(), params, iterations=190).mean())
+    mean_200 = float(_run(_image(), params, iterations=200).mean())
+    assert abs(mean_200 - mean_190) < 1e-3, (transform, blend, mean_190, mean_200)
+
+
+@pytest.mark.parametrize("transform", TRANSFORMS)
+@pytest.mark.parametrize("blend", BLENDS)
+def test_decay_zero_returns_the_input_unchanged(transform: str, blend: str) -> None:
+    """With decay 0 the feedback term vanishes and the fixed input passes through."""
+    img = _image()
+    out = _run(img, _params(decay=0.0, transform=transform, blend=blend), iterations=8)
+    assert np.array_equal(out, img)
+
+
+def test_each_transform_produces_a_different_output() -> None:
+    """On the same input, no two transforms give the same output."""
+    img = _image()
+    outputs = {
+        name: _run(img, _params(transform=name), iterations=4) for name in TRANSFORMS
+    }
+    for index, first in enumerate(TRANSFORMS):
+        for second in TRANSFORMS[index + 1 :]:
+            assert not np.array_equal(outputs[first], outputs[second]), (first, second)
+
+
+@pytest.mark.parametrize("transform", TRANSFORMS)
+def test_same_seed_produces_identical_output_across_two_calls(transform: str) -> None:
+    """Two calls with the same seed return bit-identical buffers."""
+    img = _image()
+    params = _params(transform=transform)
+    first = _run(img, params, seed=SEED)
+    second = _run(img, params, seed=SEED)
+    assert np.array_equal(first, second)
+
+
+def test_different_seed_changes_the_displace_output() -> None:
+    """The seed drives the displace field, so a different seed gives a different buffer."""
+    img = _image()
+    params = _params(transform="displace")
+    first = _run(img, params, seed=SEED)
+    other = _run(img, params, seed=SEED + 1)
+    assert not np.array_equal(first, other)
+
+
+def test_transform_is_composable() -> None:
+    """A sequence of transforms composes into a different operator than a single one."""
+    img = _image()
+    single = _run(img, _params(transform="translate"), iterations=4)
+    composed = _run(img, _params(transform=("translate", "rotate")), iterations=4)
+    joined = _run(img, _params(transform="translate+rotate"), iterations=4)
+    assert not np.array_equal(single, composed)
+    assert np.array_equal(composed, joined)
+
+
+def test_blends_give_distinct_outputs() -> None:
+    """add, max and screen combine the buffer and the input differently."""
+    img = _image()
+    outputs = {name: _run(img, _params(blend=name), iterations=4) for name in BLENDS}
+    names = list(BLENDS)
+    for index, first in enumerate(names):
+        for second in names[index + 1 :]:
+            assert not np.array_equal(outputs[first], outputs[second]), (first, second)
+
+
+def test_unknown_transform_and_blend_are_rejected() -> None:
+    """Unknown transform and blend names raise ValueError."""
+    with pytest.raises(ValueError, match="shear"):
+        _run(_image(), _params(transform="shear"))
+    with pytest.raises(ValueError, match="overlay"):
+        _run(_image(), _params(blend="overlay"))
+
+
+def test_invalid_choice_is_rejected_by_resolve_params() -> None:
+    """The registered choice parameters reject values outside their enumerations."""
+    info = get_effect(EFFECT_ID)
+    with pytest.raises(ValueError):
+        resolve_params(info.params, {"transform": "shear"})
+    with pytest.raises(ValueError):
+        resolve_params(info.params, {"blend": "overlay"})
+
+
+def test_resolve_params_clamps_numeric_bounds() -> None:
+    """decay, amount and iterations are clamped to their contract bounds."""
+    info = get_effect(EFFECT_ID)
+    resolved = resolve_params(info.params, {"decay": 5.0, "amount": -4.0, "iterations": 99})
+    assert resolved["decay"] == 0.99
+    assert resolved["amount"] == 0.0
+    assert resolved["iterations"] == 8
+    assert resolve_params(info.params, {"iterations": 0})["iterations"] == 1
+
+
+def test_effect_does_not_mutate_the_input() -> None:
+    """Running the effect leaves the source array untouched."""
+    img = _image()
+    before = img.copy()
+    _run(img, _params(transform="displace"), iterations=8)
+    assert np.array_equal(img, before)
+
+
+@pytest.mark.parametrize("shape", [(1, 1), (1, 5), (5, 1), (37, 23)])
+def test_outputs_are_float32_in_range_at_small_shapes(shape: tuple[int, int]) -> None:
+    """Even tiny or degenerate images produce a float32 buffer inside [0, 1]."""
+    out = _run(_image(shape=shape), _params(transform="rotate"))
+    assert out.shape == (*shape, 3)
+    assert out.dtype == np.float32
+    assert np.isfinite(out).all()
+    assert float(out.min()) >= 0.0
+    assert float(out.max()) <= 1.0

CODER NOTES AND DEVIATIONS (L13, attempt 1)
- E1 : le contrat ne fixe pas les libellés ParamSpec ; le codeur réutilise Strength/Scale/
  Ratio du catalogue i18n GELÉ (test_i18n exige que tout libellé soit une clé du catalogue et
  en.json est hors owns) au lieu de Decay/Transform/Blend. À juger : conforme au contrat
  (les clés i18n ne sont pas normatives) et nécessaire pour passer les tests existants.
- 5 transformations composables (bilinéaire dont, bords clampés), 3 blends, normalisation par
  frame, 200 itérations bornées [0,1].
