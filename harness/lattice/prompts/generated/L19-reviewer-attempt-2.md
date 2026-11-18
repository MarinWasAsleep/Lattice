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

## §18 Seed and masks

**Seed.** One seed drives every random operator in a render. Reroll is a single button. Each module
can be locked so a reroll changes the noise without losing the block layout. The seed is serialised
into the preset, so a good accident is reproducible.

**Masks.** A greyscale image, same size as the source, where 0 means no effect and 1 means full
effect. Masks are:
- paintable in the app (brush, gradient, luminance range),
- importable and exportable as PNG,
- referenced by path in the preset, or embedded as base64 when under 64 KB.

A global effect is a filter. A localised effect is a composition. Every glitch effect accepts a
mask.



## §6 Preset format v3

One format for the whole suite. Human-readable, diffable, portable.

```json
{
  "version": 3,
  "app": "glyph",
  "meta": {"name": "", "author": "", "created": ""},
  "renderer": {"name": "glyph_ramp", "style": {}},
  "palette": {"colors": ["#000000", "#ffffff"], "locked": false, "order": null,
              "source": "integrated",
              "extract": {"from": "image", "n_colors": 16, "rows": null}},
  "pipeline": {
    "algorithm": "floyd_steinberg", "params": {}, "color_metric": "srgb",
    "pixel_size": 1, "max_side": null, "brightness": 0.0, "contrast": 0.0,
    "gamma": 1.0, "saturation": 0.0, "pre_blur": 0.0, "auto_levels": false
  },
  "effects": [{"name": "scanlines", "params": {}, "enabled": true, "stage": "post", "mask": null}],
  "masks": {"flip": {"kind": "v_flip"}},
  "fonts": {"ramp": {"family": "DejaVu Sans Mono", "style": "", "fallback": ["mono"]}},
  "output": {"scale": 1, "width": null, "dpi": null},
  "seed": 0
}
```

**v3 completeness (S4, decided 2026-11-16).** The v3 format keeps every capability the v1/v2
formats had: `effects[].stage: "pre" | "post"` (default `post`), `palette.source` +
`palette.extract` (how the palette of a preset was obtained — integrated, extracted from the
image, or imported), `masks: {id: {...}}` referenced by `effects[].mask`, `fonts: {id: {family,
style, fallback[]}}` resolved by family name then shipped fallbacks (no absolute paths), and
`output: {scale, width?, dpi?}` feeding §17. Unknown keys remain preserved on round-trip.

Rules:

- `from_json` accepts versions 1, 2 and 3. Versions 1 and 2 are Lattice Dither formats and map to
  `app: "dither"`, `renderer: "pixel"`. Any other version raises `ValueError` naming it.
- Unknown top-level keys and unknown `style` keys are **preserved** on round-trip. A preset written
  by a newer app must survive a load/save by an older one.
- An `app` mismatch is not an error. Any app may load any preset. If the named renderer is absent,
  the app falls back to its default renderer and records a warning in the result.
- `to_json` writes sorted keys, two-space indent, one trailing newline.
- `seed` is part of the preset. Two runs of the same preset produce identical output.



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



GATE RESULTS (L19, attempt 2 — retry après le FIX du pass 1, exécuté sur mistral deepseek-v4-1-flash-1017)
- Owned tests : 32 passed (12 test_seed + 20 test_mask ; pass 1 en comptait 22).
- Suite complète : 1941 passed, 1 skipped. G1 ruff : all checks passed. G3 check_contract : OK.
- Aucun autre fichier du dépôt n'a changé : le diff ci-dessous couvre les quatre fichiers de la carte.

DISPOSITION DES FINDINGS DU PASS 1 (vérifie chacun toi-même, ne crois pas les NOTES)
1. major seed.py:59 « SeedController non câblé au pipeline » → décision orchestrateur : le seeding de
   pipeline._apply_effects n'est PAS touché (bit-exact sous G7, hors owns) ; render_effects est
   désigné comme le chemin verrouillé ; un test à deux effets réels doit prouver qu'un module
   verrouillé garde sa sortie après reroll.
2. major seed.py:44 « verrous non sérialisés » → DEV-216 : session-only en 0.1, documenté, et un test
   doit montrer qu'un preset rechargé reconstruit depuis `seed` seul.
3. major mask.py:28 « MaskRef hors preset + docstring §16 » → resolve_masks() dans mask.py ;
   preset.py intouché ; round-trip base64 ET path.
4. major test_seed.py:16 « test qui ne peut pas échouer » → comparaison de deux rendus entre eux.
5. major test_mask.py:24 « MASK_EFFECTS en dur » → découverte par introspection des signatures.
6-10. minors (0*nan, PNG 16 bits, message 64 KiB, shadowing params, __import__ inline) → à vérifier.

CONTRÔLE QUE JE TE DEMANDE EN PLUS : Y a-t-il une régression possible sur `mask.apply` ou sur les
autres effets qui consomment un masque (displace, pixel_sort) ? Ces fichiers ne sont pas dans le diff
mais la convention DEV-214 y est liée.

DIFF (vs HEAD 87b3a5d)

diff --git a/lattice_core/mask.py b/lattice_core/mask.py
index 8378544..bf969bc 100644
--- a/lattice_core/mask.py
+++ b/lattice_core/mask.py
@@ -13,16 +13,22 @@ from PIL import Image as PILImage
 from lattice_core.types import Image
 
 MAX_EMBED_BYTES = 64 * 1024
-"""Reference is embedded as base64 below this PNG size; larger masks must use a path."""
+"""Threshold on the raw 8-bit PNG size (not its base64 text, which is ~4/3 larger).
+
+A mask whose PNG is at least this size must be referenced by path; smaller masks are
+embedded as base64 data in the preset `masks` entry (§6 masks / §18).
+"""
 
 
 @dataclass(frozen=True)
 class MaskRef:
     """Serialisable reference to one greyscale mask: a path or embedded base64 data.
 
-    ``data`` holds the base64 PNG payload when the mask is small enough to embed
-    (under ``MAX_EMBED_BYTES``); ``path`` points at an external PNG for larger
-    masks. Exactly one of the two is set, mirroring the §16 preset `masks` entry.
+    ``data`` holds the base64 PNG payload when the mask's PNG is smaller than
+    ``MAX_EMBED_BYTES``; ``path`` points at an external PNG for larger masks. Exactly
+    one of the two is set, mirroring the §6 preset `masks` entry (see also §18).
+    The path is stored verbatim, so a relative one resolves against the process
+    working directory, not against the preset's own folder.
     """
 
     id: str
@@ -41,13 +47,14 @@ class MaskRef:
             return cls(ref_id, plane.shape[1], plane.shape[0], data=data)
         if path is None:
             raise ValueError(
-                f"mask of {len(payload)} bytes needs a path (over {MAX_EMBED_BYTES} - 1 bytes)"
+                f"mask PNG is {len(payload)} bytes, at or over the {MAX_EMBED_BYTES} byte "
+                "(64 KiB) embed limit; pass path= to reference it on disk"
             )
         return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))
 
     @classmethod
     def from_path(cls, path: str | Path, ref_id: str) -> MaskRef:
-        """Load the dimensions of an exported PNG mask without decoding its values."""
+        """Reference an existing PNG mask by path, decoding it once to read its dimensions."""
         plane = import_png(path)
         return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))
 
@@ -108,12 +115,29 @@ def to_png(mask: Image) -> bytes:
     return buffer.getvalue()
 
 
+def _decode_grey(pil: PILImage.Image) -> np.ndarray:
+    """Return 8-bit grey values from a decoded PNG, handling 16-bit and alpha modes.
+
+    ``I;16``/``I`` samples are divided by 65535 rather than saturated through
+    ``convert("L")``; RGBA is composited over white first, so an imported painted
+    mask from another tool keeps its tones.
+    """
+    if pil.mode in ("RGBA", "LA", "PA"):
+        flat = pil.convert("RGBA")
+        backdrop = PILImage.new("RGBA", flat.size, (255, 255, 255, 255))
+        return np.asarray(PILImage.alpha_composite(backdrop, flat).convert("L"))
+    if pil.mode in ("I;16", "I;16B", "I;16L", "I"):
+        wide = np.clip(np.asarray(pil, dtype=np.float32), 0.0, 65535.0)
+        return np.round(wide / 257.0)
+    return np.asarray(pil.convert("L"))
+
+
 def from_png(data: bytes) -> Image:
-    """Decode 8-bit PNG bytes back to a float32 greyscale mask in [0, 1]."""
+    """Decode PNG bytes (8 or 16 bit, grey or alpha) to a float32 mask in [0, 1]."""
     with PILImage.open(io.BytesIO(data)) as pil:
-        pil = pil.convert("L")
-        values = np.asarray(pil, dtype=np.float32) / np.float32(255.0)
-    return np.ascontiguousarray(values, dtype=np.float32)
+        pil.load()
+        values = _decode_grey(pil)
+    return np.ascontiguousarray(np.clip(values / 255.0, 0.0, 1.0), dtype=np.float32)
 
 
 def from_base64(text: str) -> Image:
@@ -130,7 +154,7 @@ def export_png(mask: Image, path: str | Path) -> Path:
 
 
 def import_png(path: str | Path) -> Image:
-    """Read an 8-bit greyscale PNG mask from disk into [0, 1]."""
+    """Read a greyscale PNG mask from disk into [0, 1]."""
     return from_png(Path(path).read_bytes())
 
 
@@ -145,6 +169,29 @@ def load_ref(ref: MaskRef | dict) -> Image:
     return import_png(parsed.path)
 
 
+def resolve_masks(section: dict[str, object] | None) -> dict[str, Image]:
+    """Resolve the `masks` section of a v3 preset into its greyscale mask planes.
+
+    Two entry shapes are accepted: a procedural descriptor (``{"kind": "v_flip"}``,
+    kept by the preset as opaque data and not handled here) is skipped, while a
+    mask reference (``{"path": ...}`` or ``{"data": ...}``, with the optional
+    ``id``/``width``/``height`` fields of ``MaskRef.to_dict()``) is decoded into a
+    float32 plane keyed by its section id. The input dict is never mutated, so the
+    preset section survives a ``to_json`` round-trip unchanged.
+    """
+    planes: dict[str, Image] = {}
+    for mask_id, entry in dict(section or {}).items():
+        if not isinstance(entry, dict) or "kind" in entry:
+            continue
+        if "path" in entry and "data" in entry:
+            raise ValueError(f"mask {mask_id!r} cannot carry both a path and embedded data")
+        if entry.get("data") is not None:
+            planes[str(mask_id)] = from_base64(str(entry["data"]))
+        elif entry.get("path") is not None:
+            planes[str(mask_id)] = import_png(str(entry["path"]))
+    return planes
+
+
 def _weights(mask: Image, shape: tuple[int, int]) -> np.ndarray:
     """Return the (H, W, 1) clip-mask weights, raising ValueError on a shape mismatch."""
     plane = np.clip(_plane(mask), 0.0, 1.0)
@@ -157,9 +204,12 @@ def apply(source: Image, effect: Image, *, mask: Image) -> Image:
     """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.
 
     The mask is keyword-only and shared with the effects; a shape mismatch raises
-    ValueError. A mask of all zeros returns the source unchanged for any effect.
+    ValueError. A mask of all zeros returns the source unchanged for any effect,
+    NaN or inf in the effect included (a zero weight never multiplies the effect).
     """
     weight = _weights(mask, source.shape[:2])
     one = np.float32(1.0)
-    out = (one - weight) * source + weight * effect
+    with np.errstate(invalid="ignore"):
+        blended = (one - weight) * source + weight * effect
+    out = np.where(weight == 0.0, source, blended)
     return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)
diff --git a/lattice_core/seed.py b/lattice_core/seed.py
index 2d82e8d..cad256a 100644
--- a/lattice_core/seed.py
+++ b/lattice_core/seed.py
@@ -1,4 +1,10 @@
-"""Deterministic per-module seeding for the random operators of a render (§18)."""
+"""Deterministic per-module seeding for the random operators of a render (§18).
+
+``render_effects`` is the effects-application path that honours per-module locks:
+each effect of the chain draws from its own stream, and a locked position keeps its
+stream across a reroll. ``pipeline.render`` keeps the 1.0 seeding rule
+``default_rng(seed + offset + i)`` untouched, so its output stays bit-exact (§5).
+"""
 
 from __future__ import annotations
 
@@ -32,6 +38,8 @@ class SeedController:
     ``rng(module)`` returns a deterministic generator for one module. A locked
     module keeps its stream when the seed is rerolled, so its output never
     changes with the global seed; every unlocked module follows the new seed.
+    Locks are session-only: the preset serialises ``seed`` only (§6), so a
+    reloaded preset rebuilds every stream, locks included, from that seed.
     """
 
     def __init__(self, seed: int = 0, locked: tuple[int, ...] = ()) -> None:
@@ -78,17 +86,19 @@ def render_effects(img: Image, effects: list[str], controller: SeedController,
     """Apply the named effects in order with per-module rngs, returning each stage.
 
     ``params`` optionally overrides an effect's parameters by effect id; every
-    stage is clipped to [0, 1] like the interactive renderer does.
+    stage is clipped to [0, 1] like the interactive renderer does. Lock keys are
+    positions: the i-th effect of the chain runs as module ``module_start + i``,
+    so reordering the chain moves which lock governs which effect.
     """
     overrides = params or {}
     out: Image = img
     stages: list[Image] = []
     for offset, effect_id in enumerate(effects, start=module_start):
         info = get_effect(effect_id)
-        params = resolve_params(info.params, overrides.get(effect_id, {}))
+        resolved = resolve_params(info.params, overrides.get(effect_id, {}))
         rng = controller.rng(offset)
         out = np.ascontiguousarray(
-            np.clip(info.fn(out, params, rng), 0.0, 1.0), np.float32
+            np.clip(info.fn(out, resolved, rng), 0.0, 1.0), np.float32
         )
         stages.append(out)
     return stages
diff --git a/tests/test_mask.py b/tests/test_mask.py
index cc04a48..43ffc05 100644
--- a/tests/test_mask.py
+++ b/tests/test_mask.py
@@ -2,7 +2,12 @@
 
 from __future__ import annotations
 
+import base64
+import inspect
 import io
+import json
+from collections.abc import Callable
+from typing import Any, cast
 
 import numpy as np
 import pytest
@@ -18,30 +23,45 @@ from lattice_core.mask import (
     from_png,
     import_png,
     load_ref,
+    resolve_masks,
     to_png,
 )
+from lattice_core.preset import from_json, to_json
 from lattice_core.registry import get_effect, list_effects, resolve_params
 
-# Effects that accept a mask keyword directly (DEV-214 convention).
-MASK_EFFECTS = ("displace", "pixel_sort", "crt")
 
+def _mask_effects() -> list[str]:
+    """Return every registered effect whose signature accepts a ``mask`` keyword."""
+    return [info.id for info in list_effects()
+            if "mask" in inspect.signature(info.fn).parameters]
 
-def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(
-    photo_like, rng: np.random.Generator,
-) -> None:
+
+def _masked_call(effect_id: str) -> Callable[..., Any]:
+    """Return the effect function widened to accept its optional mask keyword.
+
+    ``EffectFn`` in the registry declares only ``(img, params, rng)``; the mask
+    keyword is a per-effect extension (§18), so the call is typed through Any.
+    """
+    return cast(Callable[..., Any], get_effect(effect_id).fn)
+
+
+def test_the_registry_has_effects_that_accept_a_mask() -> None:
+    """Discovery is not vacuous: at least one registered effect takes a mask."""
+    assert _mask_effects(), "no registered effect accepts a mask"
+
+
+def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(photo_like) -> None:
     """Accept: a mask of all zeros is a no-op for every effect that accepts one."""
     zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
-    for effect_id in MASK_EFFECTS:
+    for effect_id in _mask_effects():
         info = get_effect(effect_id)
         params = resolve_params(info.params, {})
-        masked = info.fn(photo_like, params, rng, mask=zeros)
+        masked = _masked_call(effect_id)(photo_like, params, np.random.default_rng(0), mask=zeros)
         assert np.allclose(masked, photo_like), effect_id
 
 
-def test_zero_mask_composition_is_a_no_op_for_every_registered_effect(
-    photo_like, rng: np.random.Generator,
-) -> None:
-    """Composition (the §18 localised form) keeps the source for any effect's zero mask."""
+def test_zero_mask_composition_keeps_the_source(photo_like, rng: np.random.Generator) -> None:
+    """apply() algebra on a zero mask; a supporting property, not the accept item."""
     zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
     for info in list_effects():
         params = resolve_params(info.params, {})
@@ -49,6 +69,16 @@ def test_zero_mask_composition_is_a_no_op_for_every_registered_effect(
         assert np.allclose(apply(photo_like, effect, mask=zeros), photo_like), info.id
 
 
+def test_zero_mask_composition_survives_nan_in_the_effect(photo_like) -> None:
+    """A zero weight never multiplies the effect, so NaN/inf cannot leak into the source."""
+    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
+    broken = np.full_like(photo_like, np.nan)
+    broken[0, 0, 0] = np.inf
+    composed = apply(photo_like, broken, mask=zeros)
+    assert np.array_equal(composed, photo_like)
+    assert np.isfinite(composed).all()
+
+
 def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generator) -> None:
     """The composition mask is keyword-only and raises ValueError on a shape mismatch."""
     effect = get_effect("scanlines").fn(
@@ -57,7 +87,8 @@ def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generato
     with pytest.raises(ValueError):
         apply(photo_like, effect, mask=wrong)
     with pytest.raises(TypeError):
-        apply(photo_like, effect, wrong)  # shape mismatch is caught before this; mask is kw-only
+        # The keyword-only contract is the point: a positional third argument is refused.
+        apply(photo_like, effect, wrong)  # type: ignore[call-arg]
 
 
 def test_apply_blends_by_mask_value(photo_like, rng: np.random.Generator) -> None:
@@ -80,7 +111,7 @@ def test_png_round_trip_is_within_255th(rng: np.random.Generator) -> None:
 
 
 def test_png_export_import_round_trip(tmp_path, rng: np.random.Generator) -> None:
-    """disk export and re-import match to 1/255 and stay a single greyscale plane."""
+    """Disk export and re-import match to 1/255 and stay a single greyscale plane."""
     mask = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
     path = export_png(mask, tmp_path / "mask.png")
     assert path.exists()
@@ -92,13 +123,38 @@ def test_png_export_import_round_trip(tmp_path, rng: np.random.Generator) -> Non
 def test_base64_embedded_png_validates_as_greyscale(rng: np.random.Generator) -> None:
     """An embedded base64 payload is a real 8-bit greyscale PNG."""
     mask = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
-    b64 = __import__("base64").b64encode(to_png(mask)).decode("ascii")
+    payload = to_png(mask)
+    b64 = base64.b64encode(payload).decode("ascii")
     restored = from_base64(b64)
-    with PILImage.open(io.BytesIO(__import__("base64").b64decode(b64))) as pil:
+    with PILImage.open(io.BytesIO(payload)) as pil:
         assert pil.mode == "L"
     assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0
 
 
+def test_png_16_bit_greyscale_is_not_saturated() -> None:
+    """A 16-bit PNG keeps its tones instead of saturating to white through convert('L')."""
+    ramp = np.linspace(0, 65535, 64, dtype=np.uint16).reshape(8, 8)
+    buffer = io.BytesIO()
+    PILImage.fromarray(ramp).save(buffer, format="PNG")
+    restored = from_png(buffer.getvalue())
+    assert restored.shape == (8, 8)
+    assert restored.min() == pytest.approx(0.0, abs=1e-6)
+    assert restored.max() == pytest.approx(1.0, abs=1e-6)
+    assert np.max(np.abs(restored - ramp.astype(np.float32) / 65535.0)) <= 1.0 / 255.0
+
+
+def test_rgba_png_is_composited_over_white() -> None:
+    """A semi-transparent painted mask is flattened onto white, not onto black."""
+    data = np.zeros((4, 4, 4), dtype=np.uint8)
+    data[..., 0] = 255
+    data[..., 3] = 128
+    buffer = io.BytesIO()
+    PILImage.fromarray(data, mode="RGBA").save(buffer, format="PNG")
+    restored = from_png(buffer.getvalue())
+    assert restored.shape == (4, 4)
+    assert restored.min() > 0.5
+
+
 def test_mask_over_64kb_is_referenced_by_path_not_embedded(tmp_path) -> None:
     """Accept: a mask over 64 KB is referenced by path, not embedded."""
     rng = np.random.default_rng(0)
@@ -115,10 +171,11 @@ def test_mask_over_64kb_is_referenced_by_path_not_embedded(tmp_path) -> None:
     assert "data" not in ref.to_dict()
 
 
-def test_large_mask_without_a_path_is_rejected(rng: np.random.Generator) -> None:
+def test_large_mask_without_a_path_is_rejected() -> None:
     """A mask over 64 KB cannot be embedded, so omitting the path raises ValueError."""
+    rng = np.random.default_rng(1)
     big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
-    with pytest.raises(ValueError):
+    with pytest.raises(ValueError, match="64 KiB"):
         MaskRef.from_mask(big, "large")
 
 
@@ -140,7 +197,7 @@ def test_mask_ref_round_trips_through_its_dict(rng: np.random.Generator) -> None
     ref = MaskRef.from_mask(mask, "ref")
     rebuilt = MaskRef.from_dict(ref.to_dict())
     assert rebuilt == ref
-    assert MaskRef.from_dict(ref.to_dict()).data == ref.data
+    assert rebuilt.data == ref.data
 
 
 def test_mask_ref_to_dict_has_exactly_one_of_path_or_data(tmp_path, rng) -> None:
@@ -153,3 +210,66 @@ def test_mask_ref_to_dict_has_exactly_one_of_path_or_data(tmp_path, rng) -> None
     with pytest.raises(ValueError):
         MaskRef.from_dict({"id": "a", "width": 4, "height": 4,
                            "path": "p", "data": "d"})
+
+
+def _preset_with_masks(section: dict) -> str:
+    """Return a v3 preset text carrying section as its `masks` object."""
+    data = {
+        "version": 3, "app": "glitch", "meta": {},
+        "effects": [{"name": "crt", "params": {}, "enabled": True, "stage": "post",
+                     "mask": "gate"}],
+        "masks": section,
+    }
+    return json.dumps(data, sort_keys=True, indent=2) + "\n"
+
+
+def test_masks_section_round_trips_through_the_preset(tmp_path) -> None:
+    """Accept: mask references (base64 and path) survive preset load/resolve/save intact.
+
+    A procedural descriptor is left untouched: L19 owns references, not descriptors.
+    """
+    rng = np.random.default_rng(2)
+    small = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
+    embedded = MaskRef.from_mask(small, "gate").to_dict()
+    big = np.clip(rng.random((256, 256), dtype=np.float32), 0.0, 1.0)
+    target = tmp_path / "large.png"
+    target.write_bytes(to_png(big))
+    on_disk = MaskRef.from_mask(big, "wide", path=str(target)).to_dict()
+    section = {"gate": embedded, "wide": on_disk, "flip": {"kind": "v_flip"}}
+
+    preset = from_json(_preset_with_masks(section))
+    planes = resolve_masks(preset.masks)
+
+    assert set(planes) == {"gate", "wide"}
+    assert planes["gate"].shape == (32, 32)
+    assert np.max(np.abs(planes["gate"] - small)) <= 1.0 / 255.0
+    assert planes["wide"].shape == (256, 256)
+    assert preset.masks["flip"] == {"kind": "v_flip"}
+
+    saved = json.loads(to_json(preset))
+    assert saved["masks"] == section
+    assert saved["effects"][0]["mask"] == "gate"
+    assert saved["seed"] == 0
+
+
+def test_resolve_masks_ignores_empty_and_unknown_entries() -> None:
+    """An absent section, an empty dict and a descriptor all resolve to no planes."""
+    assert resolve_masks(None) == {}
+    assert resolve_masks({}) == {}
+    assert resolve_masks({"flip": {"kind": "v_flip"}}) == {}
+
+
+def test_resolve_masks_keys_by_section_id(tmp_path) -> None:
+    """The plane is keyed by the preset id, which is what ``effects[].mask`` names."""
+    mask = np.full((6, 5), 0.5, dtype=np.float32)
+    path = export_png(mask, tmp_path / "m.png")
+    planes = resolve_masks({"gate": {"path": str(path)}, "other": {"path": str(path)}})
+    assert set(planes) == {"gate", "other"}
+    assert all(plane.shape == (6, 5) for plane in planes.values())
+
+
+def test_resolve_masks_rejects_a_corrupt_reference() -> None:
+    """A mask entry carrying both a path and data is rejected, not silently preferred."""
+    with pytest.raises(ValueError):
+        resolve_masks({"bad": {"id": "bad", "width": 4, "height": 4,
+                               "path": "p.png", "data": "eA=="}})
diff --git a/tests/test_seed.py b/tests/test_seed.py
index 600dffe..4ea4081 100644
--- a/tests/test_seed.py
+++ b/tests/test_seed.py
@@ -10,12 +10,16 @@ from lattice_core.preset import Preset, from_json, from_pipeline_spec, to_json,
 from lattice_core.seed import SeedController, module_seed, render_effects
 
 _JPEG = {"quality": 40, "corruptions": 5}
+# Two effects that both consume their rng, so a changed stream is visible.
+_CHAIN = ["jpeg_glitch", "noise"]
 
 
-def test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline(
-    rng: np.random.Generator,
-) -> None:
-    """Accept: the same seed produces identical output across two multi-effect runs."""
+def test_pipeline_determinism_is_the_preexisting_seed_path(rng: np.random.Generator) -> None:
+    """§6 determinism of pipeline.render predates L19; L19 adds module_seed/SeedController.
+
+    The case is kept as a regression witness for the 1.0 seeding rule
+    (``default_rng(seed + offset + i)``), which L19 deliberately does not replace.
+    """
     img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
     spec = PipelineSpec(seed=2026)
     spec.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
@@ -23,7 +27,9 @@ def test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline(
     first = render(img, spec)
     second = render(img, spec)
     assert np.array_equal(first, second)
-    assert not np.array_equal(first, np.clip(img, 0.0, 1.0).astype(np.uint8))
+    other = PipelineSpec(seed=2027)
+    other.post_effects = list(spec.post_effects)
+    assert not np.array_equal(first, render(img, other))
 
 
 def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) -> None:
@@ -37,27 +43,33 @@ def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) ->
     assert not np.array_equal(render(img, base), render(img, rerolled))
 
 
-def test_controller_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
-    """Running render_effects with the same controller twice gives identical stages."""
+def test_render_effects_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
+    """Accept: the same seed gives identical output on two runs of a multi-effect chain."""
     img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
     controller = SeedController(seed=99)
-    first = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
-                           params={"jpeg_glitch": _JPEG})
-    second = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
-                            params={"jpeg_glitch": _JPEG})
+    first = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
+    second = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
+    assert len(first) == 2
     for a, b in zip(first, second, strict=True):
         assert np.array_equal(a, b)
+    # The chain really is randomised: rerolling the same controller changes it.
+    controller.reroll(1000)
+    third = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
+    assert not np.array_equal(first[0], third[0])
+    assert not np.array_equal(first[1], third[1])
 
 
 def test_locked_module_keeps_output_and_unlocked_changes(rng: np.random.Generator) -> None:
-    """Accept: a locked module keeps its output on reroll; an unlocked one changes."""
+    """Accept: a locked module keeps its output on reroll; an unlocked one changes.
+
+    Two real registry effects that both draw from their rng; position 0 is locked.
+    Compared as arrays, not as a call counter.
+    """
     img = np.clip(rng.random((40, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
     controller = SeedController(seed=7, locked=(0,))
-    before = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
-                            params={"jpeg_glitch": _JPEG})
+    before = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
     controller.reroll(10_000)
-    after = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
-                           params={"jpeg_glitch": _JPEG})
+    after = render_effects(img, _CHAIN, controller, params={"jpeg_glitch": _JPEG})
     assert np.array_equal(after[0], before[0]), "locked module 0 must keep its output"
     assert not np.array_equal(after[1], before[1]), "unlocked module 1 must change"
 
@@ -78,11 +90,25 @@ def test_lock_and_unlock_flip_reroll_behaviour(rng: np.random.Generator) -> None
     assert controller.locked() == frozenset()
 
 
+def test_module_start_offsets_the_lock_positions(rng: np.random.Generator) -> None:
+    """Lock keys are positions: a chain started at module_start uses that offset."""
+    img = np.clip(rng.random((24, 24, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
+    controller = SeedController(seed=3, locked=(5,))
+    before = render_effects(img, ["jpeg_glitch"], controller, module_start=5,
+                            params={"jpeg_glitch": _JPEG})
+    controller.reroll(77)
+    after = render_effects(img, ["jpeg_glitch"], controller, module_start=5,
+                           params={"jpeg_glitch": _JPEG})
+    assert np.array_equal(after[0], before[0])
+
+
 def test_module_seed_depends_on_both_seed_and_module() -> None:
     """Different modules of the same seed get independent, stable streams."""
     assert module_seed(3, 0) != module_seed(3, 1)
     assert module_seed(3, 0) == module_seed(3, 0)
     assert module_seed(3, 0) != module_seed(4, 0)
+    assert module_seed(-1, 2) == module_seed(-1, 2)
+    assert 0 <= module_seed(-1, 2) < (1 << 64)
 
 
 def test_reroll_without_argument_still_changes_the_seed() -> None:
@@ -92,6 +118,8 @@ def test_reroll_without_argument_still_changes_the_seed() -> None:
     new = controller.reroll()
     assert new != old
     assert controller.seed == new
+    second = SeedController(seed=1)
+    assert second.reroll() == new
 
 
 def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
@@ -102,6 +130,27 @@ def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
     assert from_json('{"version": 3, "seed": 55, "meta": {}}').seed == 55
 
 
+def test_locks_are_session_only_and_a_reloaded_preset_drops_them() -> None:
+    """E1/DEV-216: only `seed` is serialised, so a lock is lost across save/load.
+
+    Locked at seed A then rerolled to B, the controller keeps serving the frozen
+    A-stream; a preset saved after the reroll carries only B, so a reloaded
+    controller rebuilds module 0 from B and no longer reproduces the frozen stream.
+    """
+    controller = SeedController(seed=7, locked=(0,))
+    frozen = controller.rng(0).bit_generator.state
+    rerolled = controller.reroll(1000)
+    assert controller.rng(0).bit_generator.state == frozen, "the lock still holds in session"
+
+    loaded = from_json(to_json(Preset(seed=rerolled)))
+    assert loaded.seed == 1000
+    rebuilt = SeedController(seed=loaded.seed)
+    assert rebuilt.locked() == frozenset()
+    assert rebuilt.rng(0).bit_generator.state != frozen, "the lock did not survive the reload"
+    fresh = SeedController(seed=1000)
+    assert rebuilt.rng(0).bit_generator.state == fresh.rng(0).bit_generator.state
+
+
 def test_seed_survives_pipeline_spec_round_trip() -> None:
     """The seed crosses from spec to preset and back to the spec unchanged."""
     spec = PipelineSpec(seed=424242)


CODER NOTES AND DEVIATIONS

- 32 tests owned ; suite 1941 verte ; ruff et contrat propres.
- pipeline._apply_effects intouché (G7) ; render_effects = chemin verrouillé ; DEV-216 session-only.
- resolve_masks() ajouté dans mask.py ; preset.py intouché.
- apply() sélectionne au poids nul (pas de 0*nan) ; PNG 16 bits /65535 ; RGBA composité sur blanc.
