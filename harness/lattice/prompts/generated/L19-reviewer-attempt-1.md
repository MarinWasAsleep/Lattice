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

### L19 · Seed system and masks
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/seed.py`, `lattice_core/mask.py`, `tests/test_seed.py`,
  `tests/test_mask.py`
- context: §18
- spec: implement §18. One seed drives every random operator; per-module lock; reroll. Masks:
  greyscale, paintable, importable/exportable PNG, referenced by path or embedded base64 under
  64 KB.
- accept:
  - the same seed produces identical output across two runs of a multi-effect pipeline.
  - a locked module keeps its output when the seed is rerolled; an unlocked one changes.
  - a mask of all zeros is a no-op for every effect that accepts one.
  - a mask round-trips through PNG export/import within 1/255.
  - a mask over 64 KB is referenced by path, not embedded.
  - the seed is serialised into the preset and restored on load.

GATE RESULTS (L19, attempt 1 — deepseek-v4-flash-0731, code livré puis interrompu par la
coupure du budget nous AVANT son rapport final ; l'orchestrateur a vérifié le disque : fichiers
présents/complets, aucun import app)
- Owned tests : **22 passed** (0,40 s). Suite complète : **1915 passed, 1 skipped**.
- seed.py (~93 L) : SeedController splitmix64 — streams par module depuis la graine globale,
  locks par module. mask.py (~164 L) : blending 0→1, ValueError sur shape mismatch des masques.
- Le rapport du codeur (notes/E1) est PERDU (coupure) — le relecteur doit évaluer lui-même :
  labels ParamSpec (§18 ne spécifie rien ?), transport/contour du schéma masque (DEV-214 :
  keyword-only + ValueError), sérialisation du seed dans le preset, masque path-vs-base64 < 64 Ko.

DIFF (arbre de travail vs HEAD — seed.py, mask.py, tests)
diff --git a/lattice_core/mask.py b/lattice_core/mask.py
new file mode 100644
index 0000000..89bb54f
--- /dev/null
+++ b/lattice_core/mask.py
@@ -0,0 +1,165 @@
+"""Greyscale effect masks: PNG round-trip, path/base64 references and composition (§18)."""
+
+from __future__ import annotations
+
+import base64
+import io
+from dataclasses import dataclass
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core.types import Image
+
+MAX_EMBED_BYTES = 64 * 1024
+"""Reference is embedded as base64 below this PNG size; larger masks must use a path."""
+
+
+@dataclass(frozen=True)
+class MaskRef:
+    """Serialisable reference to one greyscale mask: a path or embedded base64 data.
+
+    ``data`` holds the base64 PNG payload when the mask is small enough to embed
+    (under ``MAX_EMBED_BYTES``); ``path`` points at an external PNG for larger
+    masks. Exactly one of the two is set, mirroring the §16 preset `masks` entry.
+    """
+
+    id: str
+    width: int
+    height: int
+    path: str | None = None
+    data: str | None = None
+
+    @classmethod
+    def from_mask(cls, mask: Image, ref_id: str, *, path: str | None = None) -> "MaskRef":
+        """Build a reference for mask, embedding when possible and requiring a path otherwise."""
+        plane = _plane(mask)
+        payload = to_png(plane)
+        if len(payload) < MAX_EMBED_BYTES:
+            data = base64.b64encode(payload).decode("ascii")
+            return cls(ref_id, plane.shape[1], plane.shape[0], data=data)
+        if path is None:
+            raise ValueError(
+                f"mask of {len(payload)} bytes needs a path (over {MAX_EMBED_BYTES} - 1 bytes)"
+            )
+        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))
+
+    @classmethod
+    def from_path(cls, path: str | Path, ref_id: str) -> "MaskRef":
+        """Load the dimensions of an exported PNG mask without decoding its values."""
+        plane = import_png(path)
+        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))
+
+    @property
+    def embedded(self) -> bool:
+        """True when the mask is embedded as base64 data rather than referenced by path."""
+        return self.data is not None
+
+    def to_dict(self) -> dict[str, str | int | None]:
+        """Return the JSON dict of the reference; exactly one of path/data is present."""
+        item: dict[str, str | int | None] = {
+            "id": self.id, "width": self.width, "height": self.height,
+        }
+        item["data" if self.embedded else "path"] = self.data if self.embedded else self.path
+        return item
+
+    @classmethod
+    def from_dict(cls, item: dict) -> "MaskRef":
+        """Rebuild a reference from its JSON dict, rejecting an entry with both keys."""
+        ref = cls(str(item["id"]), _int(item, "width"), _int(item, "height"),
+                  path=_str_or_none(item.get("path")),
+                  data=_str_or_none(item.get("data")))
+        if not ref.path and not ref.data:
+            raise ValueError("mask reference needs a path or embedded data")
+        if ref.path and ref.data:
+            raise ValueError("mask reference cannot carry both a path and embedded data")
+        return ref
+
+
+def _int(item: dict, key: str) -> int:
+    value = item[key]
+    if isinstance(value, bool) or not isinstance(value, int):
+        raise ValueError(f"mask reference key {key!r} must be an integer")
+    return value
+
+
+def _str_or_none(value: object) -> str | None:
+    return None if value is None else str(value)
+
+
+def _plane(mask: Image) -> np.ndarray:
+    """Return the (H, W) float32 mask plane, accepting an (H, W, 1) channel image."""
+    data = np.asarray(mask, dtype=np.float32)
+    if data.ndim == 3 and data.shape[2] == 1:
+        data = data[:, :, 0]
+    if data.ndim != 2:
+        raise ValueError(f"mask must be a greyscale plane, got shape {mask.shape}")
+    return data
+
+
+def to_png(mask: Image) -> bytes:
+    """Encode a greyscale mask as 8-bit PNG bytes with exact rounding."""
+    plane = np.clip(_plane(mask), 0.0, 1.0)
+    buffer = io.BytesIO()
+    PILImage.fromarray((plane * 255.0).round().astype(np.uint8), mode="L").save(
+        buffer, format="PNG"
+    )
+    return buffer.getvalue()
+
+
+def from_png(data: bytes) -> Image:
+    """Decode 8-bit PNG bytes back to a float32 greyscale mask in [0, 1]."""
+    with PILImage.open(io.BytesIO(data)) as pil:
+        pil = pil.convert("L")
+        values = np.asarray(pil, dtype=np.float32) / np.float32(255.0)
+    return np.ascontiguousarray(values, dtype=np.float32)
+
+
+def from_base64(text: str) -> Image:
+    """Decode a base64 PNG payload back to a float32 greyscale mask."""
+    return from_png(base64.b64decode(text))
+
+
+def export_png(mask: Image, path: str | Path) -> Path:
+    """Write a mask as an 8-bit greyscale PNG, creating parent directories."""
+    target = Path(path)
+    target.parent.mkdir(parents=True, exist_ok=True)
+    target.write_bytes(to_png(mask))
+    return target
+
+
+def import_png(path: str | Path) -> Image:
+    """Read an 8-bit greyscale PNG mask from disk into [0, 1]."""
+    return from_png(Path(path).read_bytes())
+
+
+def load_ref(ref: MaskRef | dict) -> Image:
+    """Resolve a MaskRef (or its dict) into the greyscale mask it references."""
+    item = ref.to_dict() if isinstance(ref, MaskRef) else dict(ref)
+    parsed = MaskRef.from_dict(item)
+    if parsed.data is not None:
+        return from_base64(parsed.data)
+    if parsed.path is None:
+        raise ValueError("mask reference carries no data or path")
+    return import_png(parsed.path)
+
+
+def _weights(mask: Image, shape: tuple[int, int]) -> np.ndarray:
+    """Return the (H, W, 1) clip-mask weights, raising ValueError on a shape mismatch."""
+    plane = np.clip(_plane(mask), 0.0, 1.0)
+    if plane.shape != shape:
+        raise ValueError(f"mask must be {shape}, got {plane.shape}")
+    return plane[:, :, None]
+
+
+def apply(source: Image, effect: Image, *, mask: Image) -> Image:
+    """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.
+
+    The mask is keyword-only and shared with the effects; a shape mismatch raises
+    ValueError. A mask of all zeros returns the source unchanged for any effect.
+    """
+    weight = _weights(mask, source.shape[:2])
+    one = np.float32(1.0)
+    out = (one - weight) * source + weight * effect
+    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)
\ No newline at end of file
diff --git a/lattice_core/seed.py b/lattice_core/seed.py
new file mode 100644
index 0000000..b177da4
--- /dev/null
+++ b/lattice_core/seed.py
@@ -0,0 +1,94 @@
+"""Deterministic per-module seeding for the random operators of a render (§18)."""
+
+from __future__ import annotations
+
+import numpy as np
+
+from lattice_core.registry import get_effect, resolve_params
+from lattice_core.types import Image
+
+_MASK64 = (1 << 64) - 1
+_PHI = 0x9E3779B97F4A7C15
+_G1 = 0xBF58476D1CE4E5B9
+_G2 = 0x94D049BB133111EB
+
+
+def _mix(value: int) -> int:
+    """Return a splitmix64 mixing of value, kept inside the unsigned 64-bit range."""
+    mixed = (value + _PHI) & _MASK64
+    mixed = ((mixed ^ (mixed >> 30)) * _G1) & _MASK64
+    mixed = ((mixed ^ (mixed >> 27)) * _G2) & _MASK64
+    return (mixed ^ (mixed >> 31)) & _MASK64
+
+
+def module_seed(seed: int, module: int) -> int:
+    """Return the deterministic per-module stream seed derived from the global seed."""
+    return _mix(_mix(int(seed)) ^ _mix(int(module) + 1))
+
+
+class SeedController:
+    """One global seed plus per-module streams, with optional per-module locks.
+
+    ``rng(module)`` returns a deterministic generator for one module. A locked
+    module keeps its stream when the seed is rerolled, so its output never
+    changes with the global seed; every unlocked module follows the new seed.
+    """
+
+    def __init__(self, seed: int = 0, locked: tuple[int, ...] = ()) -> None:
+        self._base: int = int(seed)
+        self._fixed: dict[int, int] = {}
+        for module in locked:
+            self.lock(module)
+
+    @property
+    def seed(self) -> int:
+        """The global seed driving the whole render."""
+        return self._base
+
+    def module_seed_for(self, module: int) -> int:
+        """Return the stream seed of one module, fixed when the module is locked."""
+        return self._fixed.get(module, module_seed(self._base, module))
+
+    def rng(self, module: int) -> np.random.Generator:
+        """Return the deterministic random generator of one module."""
+        return np.random.default_rng(self.module_seed_for(module))
+
+    def lock(self, module: int) -> None:
+        """Freeze the current stream of module so a reroll does not change it."""
+        if module not in self._fixed:
+            self._fixed[module] = module_seed(self._base, module)
+
+    def unlock(self, module: int) -> None:
+        """Let module follow the global seed again on the next reroll."""
+        self._fixed.pop(module, None)
+
+    def locked(self) -> frozenset[int]:
+        """Return the set of module indices whose streams are frozen."""
+        return frozenset(self._fixed)
+
+    def reroll(self, seed: int | None = None) -> int:
+        """Reroll the global seed; locked modules keep their prior streams."""
+        self._base = _mix(self._base + 1) if seed is None else int(seed)
+        return self._base
+
+
+def render_effects(img: Image, effects: list[str], controller: SeedController,
+                   *, params: dict[str, dict] | None = None,
+                   module_start: int = 0) -> list[Image]:
+    """Apply the named effects in order with per-module rngs, returning each stage.
+
+    ``params`` optionally overrides an effect's parameters by effect id; every
+    stage is clipped to [0, 1] like the interactive renderer does.
+    """
+    overrides = params or {}
+    out: Image = img
+    stages: list[Image] = []
+    for offset, effect_id in enumerate(effects, start=module_start):
+        info = get_effect(effect_id)
+        params = resolve_params(info.params, overrides.get(effect_id, {}))
+        rng = controller.rng(offset)
+        out = np.ascontiguousarray(
+            np.clip(info.fn(out, params, rng), 0.0, 1.0), np.float32
+        )
+        stages.append(out)
+    return stages
\ No newline at end of file
diff --git a/tests/test_mask.py b/tests/test_mask.py
new file mode 100644
index 0000000..cddb3d4
--- /dev/null
+++ b/tests/test_mask.py
@@ -0,0 +1,155 @@
+"""Tests for the §18 greyscale mask system: no-op, PNG round-trip, refs and composition."""
+
+from __future__ import annotations
+
+import io
+
+import numpy as np
+import pytest
+from PIL import Image as PILImage
+
+import lattice_core.effects  # noqa: F401  (registers every effect)
+from lattice_core.mask import (
+    MAX_EMBED_BYTES,
+    MaskRef,
+    apply,
+    export_png,
+    from_base64,
+    from_png,
+    import_png,
+    load_ref,
+    to_png,
+)
+from lattice_core.registry import get_effect, list_effects, resolve_params
+
+# Effects that accept a mask keyword directly (DEV-214 convention).
+MASK_EFFECTS = ("displace", "pixel_sort", "crt")
+
+
+def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(
+    photo_like, rng: np.random.Generator,
+) -> None:
+    """Accept: a mask of all zeros is a no-op for every effect that accepts one."""
+    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
+    for effect_id in MASK_EFFECTS:
+        info = get_effect(effect_id)
+        params = resolve_params(info.params, {})
+        masked = info.fn(photo_like, params, rng, mask=zeros)
+        assert np.allclose(masked, photo_like), effect_id
+
+
+def test_zero_mask_composition_is_a_no_op_for_every_registered_effect(
+    photo_like, rng: np.random.Generator,
+) -> None:
+    """Composition (the §18 localised form) keeps the source for any effect's zero mask."""
+    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
+    for info in list_effects():
+        params = resolve_params(info.params, {})
+        effect = info.fn(photo_like, params, rng)
+        assert np.allclose(apply(photo_like, effect, mask=zeros), photo_like), info.id
+
+
+def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generator) -> None:
+    """The composition mask is keyword-only and raises ValueError on a shape mismatch."""
+    effect = get_effect("scanlines").fn(
+        photo_like, resolve_params(get_effect("scanlines").params, {}), rng)
+    wrong = np.zeros((photo_like.shape[0] + 1, photo_like.shape[1]), dtype=np.float32)
+    with pytest.raises(ValueError):
+        apply(photo_like, effect, mask=wrong)
+    with pytest.raises(TypeError):
+        apply(photo_like, effect, wrong)  # shape mismatch is caught before this; mask is kw-only
+
+
+def test_apply_blends_by_mask_value(photo_like, rng: np.random.Generator) -> None:
+    """Mask 1 keeps the effect; values in between interpolate between source and effect."""
+    effect = np.clip(photo_like[::-1], 0.0, 1.0)
+    all_one = np.ones(photo_like.shape[:2], dtype=np.float32)
+    assert np.allclose(apply(photo_like, effect, mask=all_one), effect)
+    half = np.full(photo_like.shape[:2], 0.5, dtype=np.float32)
+    blended = apply(photo_like, effect, mask=half)
+    expected = 0.5 * photo_like + 0.5 * effect
+    assert np.allclose(blended, expected, atol=1e-6)
+
+
+def test_png_round_trip_is_within_255th(rng: np.random.Generator) -> None:
+    """Accept: a mask round-trips through PNG export/import within 1/255."""
+    mask = np.clip(rng.random((64, 80), dtype=np.float32), 0.0, 1.0)
+    restored = from_png(to_png(mask))
+    assert mask.shape == restored.shape
+    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0
+
+
+def test_png_export_import_round_trip(tmp_path, rng: np.random.Generator) -> None:
+    """disk export and re-import match to 1/255 and stay a single greyscale plane."""
+    mask = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
+    path = export_png(mask, tmp_path / "mask.png")
+    assert path.exists()
+    restored = import_png(path)
+    assert restored.ndim == 2
+    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0
+
+
+def test_base64_embedded_png_validates_as_greyscale(rng: np.random.Generator) -> None:
+    """An embedded base64 payload is a real 8-bit greyscale PNG."""
+    mask = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
+    b64 = __import__("base64").b64encode(to_png(mask)).decode("ascii")
+    restored = from_base64(b64)
+    with PILImage.open(io.BytesIO(__import__("base64").b64decode(b64))) as pil:
+        assert pil.mode == "L"
+    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0
+
+
+def test_mask_over_64kb_is_referenced_by_path_not_embedded(tmp_path) -> None:
+    """Accept: a mask over 64 KB is referenced by path, not embedded."""
+    rng = np.random.default_rng(0)
+    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
+    payload = to_png(big)
+    assert len(payload) >= MAX_EMBED_BYTES
+    target = tmp_path / "big_mask.png"
+    target.write_bytes(payload)
+    ref = MaskRef.from_mask(big, "large", path=str(target))
+    assert not ref.embedded
+    assert ref.path == str(target)
+    assert ref.data is None
+    assert ref.to_dict()["path"] == str(target)
+    assert "data" not in ref.to_dict()
+
+
+def test_large_mask_without_a_path_is_rejected(rng: np.random.Generator) -> None:
+    """A mask over 64 KB cannot be embedded, so omitting the path raises ValueError."""
+    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
+    with pytest.raises(ValueError):
+        MaskRef.from_mask(big, "large")
+
+
+def test_small_mask_is_embedded_and_loads_back(rng: np.random.Generator) -> None:
+    """A mask under 64 KB is embedded as base64 and resolves to the same plane."""
+    small = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
+    ref = MaskRef.from_mask(small, "tiny")
+    assert ref.embedded
+    assert ref.path is None
+    assert ref.to_dict()["data"]
+    restored = load_ref(ref)
+    assert restored.shape == small.shape
+    assert np.max(np.abs(restored - small)) <= 1.0 / 255.0
+
+
+def test_mask_ref_round_trips_through_its_dict(rng: np.random.Generator) -> None:
+    """to_dict()/from_dict() preserve an embedded mask reference exactly."""
+    mask = np.clip(rng.random((40, 40), dtype=np.float32), 0.0, 1.0)
+    ref = MaskRef.from_mask(mask, "ref")
+    rebuilt = MaskRef.from_dict(ref.to_dict())
+    assert rebuilt == ref
+    assert MaskRef.from_dict(ref.to_dict()).data == ref.data
+
+
+def test_mask_ref_to_dict_has_exactly_one_of_path_or_data(tmp_path, rng) -> None:
+    """A path reference serialises with path and no data; a corrupt dict is rejected."""
+    mask = np.clip(rng.random((8, 8), dtype=np.float32), 0.0, 1.0)
+    path = export_png(mask, tmp_path / "mask.png")
+    assert MaskRef.from_path(path, "x").to_dict()["path"] == str(path)
+    with pytest.raises(ValueError):
+        MaskRef.from_dict({"id": "a", "width": 4, "height": 4})
+    with pytest.raises(ValueError):
+        MaskRef.from_dict({"id": "a", "width": 4, "height": 4,
+                           "path": "p", "data": "d"})
\ No newline at end of file
diff --git a/tests/test_seed.py b/tests/test_seed.py
new file mode 100644
index 0000000..73694cc
--- /dev/null
+++ b/tests/test_seed.py
@@ -0,0 +1,116 @@
+"""Tests for the §18 seed system: determinism, per-module lock, reroll and serialisation."""
+
+from __future__ import annotations
+
+import numpy as np
+import pytest
+
+from lattice_core.registry import get_effect
+from lattice_core.preset import Preset, from_json, from_pipeline_spec, to_json, to_pipeline_spec
+from lattice_core.pipeline import EffectInstance, PipelineSpec, render
+from lattice_core.seed import SeedController, module_seed, render_effects
+
+_JPEG = {"quality": 40, "corruptions": 5}
+
+
+def test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline(
+    rng: np.random.Generator,
+) -> None:
+    """Accept: the same seed produces identical output across two multi-effect runs."""
+    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    spec = PipelineSpec(seed=2026)
+    spec.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
+                         EffectInstance("rgb_shift", {})]
+    first = render(img, spec)
+    second = render(img, spec)
+    assert np.array_equal(first, second)
+    assert not np.array_equal(first, np.clip(img, 0.0, 1.0).astype(np.uint8))
+
+
+def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) -> None:
+    """The seed genuinely drives the pipeline: a new seed re-randomises the render."""
+    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    base = PipelineSpec(seed=11)
+    base.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
+                         EffectInstance("rgb_shift", {})]
+    rerolled = PipelineSpec(seed=12)
+    rerolled.post_effects = list(base.post_effects)
+    assert not np.array_equal(render(img, base), render(img, rerolled))
+
+
+def test_controller_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
+    """Running render_effects with the same controller twice gives identical stages."""
+    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    controller = SeedController(seed=99)
+    first = render_effects(img, ["jpeg_glitch", "ntsc"], controller, params={"jpeg_glitch": _JPEG})
+    second = render_effects(img, ["jpeg_glitch", "ntsc"], controller,
+                            params={"jpeg_glitch": _JPEG})
+    for a, b in zip(first, second, strict=True):
+        assert np.array_equal(a, b)
+
+
+def test_locked_module_keeps_output_and_unlocked_changes(rng: np.random.Generator) -> None:
+    """Accept: a locked module keeps its output on reroll; an unlocked one changes."""
+    img = np.clip(rng.random((40, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    controller = SeedController(seed=7, locked=(0,))
+    before = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
+                            params={"jpeg_glitch": _JPEG})
+    controller.reroll(10_000)
+    after = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
+                           params={"jpeg_glitch": _JPEG})
+    assert np.array_equal(after[0], before[0]), "locked module 0 must keep its output"
+    assert not np.array_equal(after[1], before[1]), "unlocked module 1 must change"
+
+
+def test_lock_and_unlock_flip_reroll_behaviour(rng: np.random.Generator) -> None:
+    """Locking freezes a module; unlocking lets it follow the new seed again."""
+    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    controller = SeedController(seed=1)
+    before = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
+    controller.lock(0)
+    controller.reroll(5)
+    locked = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
+    assert np.array_equal(locked[0], before[0])
+    controller.unlock(0)
+    controller.reroll(6)
+    released = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
+    assert not np.array_equal(released[0], locked[0])
+    assert controller.locked() == frozenset()
+
+
+def test_module_seed_depends_on_both_seed_and_module() -> None:
+    """Different modules of the same seed get independent, stable streams."""
+    assert module_seed(3, 0) != module_seed(3, 1)
+    assert module_seed(3, 0) == module_seed(3, 0)
+    assert module_seed(3, 0) != module_seed(4, 0)
+
+
+def test_reroll_without_argument_still_changes_the_seed() -> None:
+    """reroll() draws a new deterministic seed that unlocked modules follow."""
+    controller = SeedController(seed=1)
+    old = controller.seed
+    new = controller.reroll()
+    assert new != old
+    assert controller.seed == new
+
+
+def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
+    """Accept: the seed is serialised into the preset and restored on load."""
+    preset = Preset(seed=123456789)
+    loaded = from_json(to_json(preset))
+    assert loaded.seed == 123456789
+    assert from_json('{"version": 3, "seed": 55, "meta": {}}').seed == 55
+
+
+def test_seed_survives_pipeline_spec_round_trip() -> None:
+    """The seed crosses from spec to preset and back to the spec unchanged."""
+    spec = PipelineSpec(seed=424242)
+    preset = from_pipeline_spec(spec)
+    restored = to_pipeline_spec(preset)
+    assert preset.seed == 424242
+    assert restored.seed == 424242
+
+
+def test_missing_seed_defaults_to_zero() -> None:
+    """An absent seed field loads as 0, never crashing."""
+    assert from_json('{"version": 3, "meta": {}}').seed == 0
\ No newline at end of file
