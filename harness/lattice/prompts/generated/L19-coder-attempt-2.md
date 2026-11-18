# Coder prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are a senior Python engineer implementing one task of the Lattice project: a family of free,
open-source desktop applications that transform images, each running standalone and also plugging
into the ArtCraft suite (Python + numpy + numba + Pillow + PySide6, Windows and Linux).

The suite has four packages: `lattice-core` (the shared engine), `lattice-dither` (the existing
dithering application, 33 algorithms, 10 effects, ~1212 passing tests), `lattice-glyph` and
`lattice-glitch` (new). You work alone on this task; other tasks run in parallel on other files.

HARD RULES
1. Write only the files listed in `owns`. Any other file you need changed → DEVIATIONS block, not code.
2. Follow the contract excerpts exactly: names, signatures, dtypes, value ranges, ordering, error types.
   If the contract is silent, choose the simplest conservative behaviour and record it as E1.
   If the task is impossible without changing the contract, output no FILE blocks, only an E2 deviation.
3. No new dependency. No network. Only numpy, numba (where allowed), Pillow, PySide6, stdlib, pytest.
   `lattice-core` base install must not import PySide6; Qt lives behind the `[ui]` extra.
4. **Core must not import any application.** `lattice_core` may not reference `lattice_dither`,
   `lattice_glyph` or `lattice_glitch`. If you need application-specific behaviour in core, that is
   an E8 deviation: stop and declare it.
5. **Every application must work with no host present.** A missing ArtCraft, a refused connection or
   an absent token file is a normal state, never a crash. If your change makes an app depend on a
   running host, that is an E9 deviation.
6. Each file ≤ 400 lines, each function ≤ 60 lines, typed public API, 1 to 3 line docstrings.
7. Tests: cover every `accept` item of the card, deterministic seeds, fast.
8. **Do not regress the dithering application.** Any behaviour that existed before your task must
   still hold. If your change alters a 1.0 or 1.1 output, that is an E6 deviation: stop and declare
   it, do not ship it.
9. Output full file contents (no diffs, no ellipsis, no "rest unchanged"). Nothing outside the blocks below.
10. Do not explain your code. NOTES is for facts the reviewer needs, ≤ 10 lines.

OUTPUT FORMAT
```
=== FILE: <relative path> ===
<complete content>
=== END FILE ===
(repeat per owned file you write)
=== NOTES ===
<≤ 10 lines or "none">
=== DEVIATIONS ===
<"none", or one block per deviation:
class: E1|E2|E3|E4|E5|E6|E8|E9
facts: <quote the contract or card line involved>
assumption_or_proposal: <...>
(E3 scope : déclarer une sortie hors `owns` ne l'autorise pas — G4 et le relecteur décident.
E7 product : déclarée par le relecteur ou l'humain, jamais par le codeur.)
```

CONTRACT EXCERPTS (version 0.1.0)

## §5 Pipeline

Inherits Lattice Dither §13 (pre-dither conditioning) and its render order, with step 8 replaced by
the renderer call. The normative order becomes:

1. If `max_side`: area-downscale so `max(H, W) <= max_side`. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = `pre_blur / 3`).
6. Compute grid geometry from `renderer.cell_aspect()` and `pixel_size`, with the normative
   rule (H11, decided 2026-11-16): let `a = cell_aspect()`; if `a >= 1`, `cell_w = pixel_size`
   and `cell_h = max(1, floor(pixel_size / a + 0.5))`; else `cell_h = pixel_size` and
   `cell_w = max(1, floor(pixel_size * a + 0.5))`. The grid holds as many whole cells as fit in
   the step-5 image. Glyph font sizes derive from `cell_h` (no `size` option in §9).
7. Downscale to the grid.
8. `resolve_palette` on the image from step 7.
9. Algorithm (params through `resolve_params`) → `index`.
10. Derive `coverage` and `samples` per §3.
11. `renderer.render(grid, palette, style)`.
12. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.

Steps 3, 4 and 5 must be no-ops at their defaults. Step 11 replaces the 1.0 `apply_palette` +
`upscale_nearest` pair; `PixelRenderer` reproduces that pair exactly.

**Continuous mode (S1, amended at H11, decided 2026-11-16).** The pipeline may run without
quantisation: `algorithm: null` and `palette: null` are legal. In that mode **steps 6 to 11 are
skipped outright**: the step-5 image goes straight to step 12 (post-effects); no `CellGrid` is
built and no renderer is called. Lattice Glitch is an effect-graph app that consumes the core
(seed, masks, presets, bridge, CLI) without depending on the CellRenderer quantisation chain.

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

CURRENT CONTENT OF YOUR FILES

--- lattice_core/seed.py ---
"""Deterministic per-module seeding for the random operators of a render (§18)."""

from __future__ import annotations

import numpy as np

from lattice_core.registry import get_effect, resolve_params
from lattice_core.types import Image

_MASK64 = (1 << 64) - 1
_PHI = 0x9E3779B97F4A7C15
_G1 = 0xBF58476D1CE4E5B9
_G2 = 0x94D049BB133111EB


def _mix(value: int) -> int:
    """Return a splitmix64 mixing of value, kept inside the unsigned 64-bit range."""
    mixed = (value + _PHI) & _MASK64
    mixed = ((mixed ^ (mixed >> 30)) * _G1) & _MASK64
    mixed = ((mixed ^ (mixed >> 27)) * _G2) & _MASK64
    return (mixed ^ (mixed >> 31)) & _MASK64


def module_seed(seed: int, module: int) -> int:
    """Return the deterministic per-module stream seed derived from the global seed."""
    return _mix(_mix(int(seed)) ^ _mix(int(module) + 1))


class SeedController:
    """One global seed plus per-module streams, with optional per-module locks.

    ``rng(module)`` returns a deterministic generator for one module. A locked
    module keeps its stream when the seed is rerolled, so its output never
    changes with the global seed; every unlocked module follows the new seed.
    """

    def __init__(self, seed: int = 0, locked: tuple[int, ...] = ()) -> None:
        self._base: int = int(seed)
        self._fixed: dict[int, int] = {}
        for module in locked:
            self.lock(module)

    @property
    def seed(self) -> int:
        """The global seed driving the whole render."""
        return self._base

    def module_seed_for(self, module: int) -> int:
        """Return the stream seed of one module, fixed when the module is locked."""
        return self._fixed.get(module, module_seed(self._base, module))

    def rng(self, module: int) -> np.random.Generator:
        """Return the deterministic random generator of one module."""
        return np.random.default_rng(self.module_seed_for(module))

    def lock(self, module: int) -> None:
        """Freeze the current stream of module so a reroll does not change it."""
        if module not in self._fixed:
            self._fixed[module] = module_seed(self._base, module)

    def unlock(self, module: int) -> None:
        """Let module follow the global seed again on the next reroll."""
        self._fixed.pop(module, None)

    def locked(self) -> frozenset[int]:
        """Return the set of module indices whose streams are frozen."""
        return frozenset(self._fixed)

    def reroll(self, seed: int | None = None) -> int:
        """Reroll the global seed; locked modules keep their prior streams."""
        self._base = _mix(self._base + 1) if seed is None else int(seed)
        return self._base


def render_effects(img: Image, effects: list[str], controller: SeedController,
                   *, params: dict[str, dict] | None = None,
                   module_start: int = 0) -> list[Image]:
    """Apply the named effects in order with per-module rngs, returning each stage.

    ``params`` optionally overrides an effect's parameters by effect id; every
    stage is clipped to [0, 1] like the interactive renderer does.
    """
    overrides = params or {}
    out: Image = img
    stages: list[Image] = []
    for offset, effect_id in enumerate(effects, start=module_start):
        info = get_effect(effect_id)
        params = resolve_params(info.params, overrides.get(effect_id, {}))
        rng = controller.rng(offset)
        out = np.ascontiguousarray(
            np.clip(info.fn(out, params, rng), 0.0, 1.0), np.float32
        )
        stages.append(out)
    return stages


--- lattice_core/mask.py ---
"""Greyscale effect masks: PNG round-trip, path/base64 references and composition (§18)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_core.types import Image

MAX_EMBED_BYTES = 64 * 1024
"""Reference is embedded as base64 below this PNG size; larger masks must use a path."""


@dataclass(frozen=True)
class MaskRef:
    """Serialisable reference to one greyscale mask: a path or embedded base64 data.

    ``data`` holds the base64 PNG payload when the mask is small enough to embed
    (under ``MAX_EMBED_BYTES``); ``path`` points at an external PNG for larger
    masks. Exactly one of the two is set, mirroring the §16 preset `masks` entry.
    """

    id: str
    width: int
    height: int
    path: str | None = None
    data: str | None = None

    @classmethod
    def from_mask(cls, mask: Image, ref_id: str, *, path: str | None = None) -> MaskRef:
        """Build a reference for mask, embedding when possible and requiring a path otherwise."""
        plane = _plane(mask)
        payload = to_png(plane)
        if len(payload) < MAX_EMBED_BYTES:
            data = base64.b64encode(payload).decode("ascii")
            return cls(ref_id, plane.shape[1], plane.shape[0], data=data)
        if path is None:
            raise ValueError(
                f"mask of {len(payload)} bytes needs a path (over {MAX_EMBED_BYTES} - 1 bytes)"
            )
        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))

    @classmethod
    def from_path(cls, path: str | Path, ref_id: str) -> MaskRef:
        """Load the dimensions of an exported PNG mask without decoding its values."""
        plane = import_png(path)
        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))

    @property
    def embedded(self) -> bool:
        """True when the mask is embedded as base64 data rather than referenced by path."""
        return self.data is not None

    def to_dict(self) -> dict[str, str | int | None]:
        """Return the JSON dict of the reference; exactly one of path/data is present."""
        item: dict[str, str | int | None] = {
            "id": self.id, "width": self.width, "height": self.height,
        }
        item["data" if self.embedded else "path"] = self.data if self.embedded else self.path
        return item

    @classmethod
    def from_dict(cls, item: dict) -> MaskRef:
        """Rebuild a reference from its JSON dict, rejecting an entry with both keys."""
        ref = cls(str(item["id"]), _int(item, "width"), _int(item, "height"),
                  path=_str_or_none(item.get("path")),
                  data=_str_or_none(item.get("data")))
        if not ref.path and not ref.data:
            raise ValueError("mask reference needs a path or embedded data")
        if ref.path and ref.data:
            raise ValueError("mask reference cannot carry both a path and embedded data")
        return ref


def _int(item: dict, key: str) -> int:
    value = item[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"mask reference key {key!r} must be an integer")
    return value


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _plane(mask: Image) -> np.ndarray:
    """Return the (H, W) float32 mask plane, accepting an (H, W, 1) channel image."""
    data = np.asarray(mask, dtype=np.float32)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2:
        raise ValueError(f"mask must be a greyscale plane, got shape {mask.shape}")
    return data


def to_png(mask: Image) -> bytes:
    """Encode a greyscale mask as 8-bit PNG bytes with exact rounding."""
    plane = np.clip(_plane(mask), 0.0, 1.0)
    buffer = io.BytesIO()
    PILImage.fromarray((plane * 255.0).round().astype(np.uint8), mode="L").save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def from_png(data: bytes) -> Image:
    """Decode 8-bit PNG bytes back to a float32 greyscale mask in [0, 1]."""
    with PILImage.open(io.BytesIO(data)) as pil:
        pil = pil.convert("L")
        values = np.asarray(pil, dtype=np.float32) / np.float32(255.0)
    return np.ascontiguousarray(values, dtype=np.float32)


def from_base64(text: str) -> Image:
    """Decode a base64 PNG payload back to a float32 greyscale mask."""
    return from_png(base64.b64decode(text))


def export_png(mask: Image, path: str | Path) -> Path:
    """Write a mask as an 8-bit greyscale PNG, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(to_png(mask))
    return target


def import_png(path: str | Path) -> Image:
    """Read an 8-bit greyscale PNG mask from disk into [0, 1]."""
    return from_png(Path(path).read_bytes())


def load_ref(ref: MaskRef | dict) -> Image:
    """Resolve a MaskRef (or its dict) into the greyscale mask it references."""
    item = ref.to_dict() if isinstance(ref, MaskRef) else dict(ref)
    parsed = MaskRef.from_dict(item)
    if parsed.data is not None:
        return from_base64(parsed.data)
    if parsed.path is None:
        raise ValueError("mask reference carries no data or path")
    return import_png(parsed.path)


def _weights(mask: Image, shape: tuple[int, int]) -> np.ndarray:
    """Return the (H, W, 1) clip-mask weights, raising ValueError on a shape mismatch."""
    plane = np.clip(_plane(mask), 0.0, 1.0)
    if plane.shape != shape:
        raise ValueError(f"mask must be {shape}, got {plane.shape}")
    return plane[:, :, None]


def apply(source: Image, effect: Image, *, mask: Image) -> Image:
    """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.

    The mask is keyword-only and shared with the effects; a shape mismatch raises
    ValueError. A mask of all zeros returns the source unchanged for any effect.
    """
    weight = _weights(mask, source.shape[:2])
    one = np.float32(1.0)
    out = (one - weight) * source + weight * effect
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)


--- tests/test_seed.py ---
"""Tests for the §18 seed system: determinism, per-module lock, reroll and serialisation."""

from __future__ import annotations

import numpy as np

import lattice_core.effects  # noqa: F401 — enregistre les effets (registre peuplé à l'import)
from lattice_core.pipeline import EffectInstance, PipelineSpec, render
from lattice_core.preset import Preset, from_json, from_pipeline_spec, to_json, to_pipeline_spec
from lattice_core.seed import SeedController, module_seed, render_effects

_JPEG = {"quality": 40, "corruptions": 5}


def test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline(
    rng: np.random.Generator,
) -> None:
    """Accept: the same seed produces identical output across two multi-effect runs."""
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    spec = PipelineSpec(seed=2026)
    spec.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    first = render(img, spec)
    second = render(img, spec)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, np.clip(img, 0.0, 1.0).astype(np.uint8))


def test_different_seed_changes_the_pipeline_output(rng: np.random.Generator) -> None:
    """The seed genuinely drives the pipeline: a new seed re-randomises the render."""
    img = np.clip(rng.random((48, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    base = PipelineSpec(seed=11)
    base.post_effects = [EffectInstance("jpeg_glitch", _JPEG),
                         EffectInstance("rgb_shift", {})]
    rerolled = PipelineSpec(seed=12)
    rerolled.post_effects = list(base.post_effects)
    assert not np.array_equal(render(img, base), render(img, rerolled))


def test_controller_is_deterministic_for_a_fixed_seed(rng: np.random.Generator) -> None:
    """Running render_effects with the same controller twice gives identical stages."""
    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=99)
    first = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
                           params={"jpeg_glitch": _JPEG})
    second = render_effects(img, ["jpeg_glitch", "gaussian_blur"], controller,
                            params={"jpeg_glitch": _JPEG})
    for a, b in zip(first, second, strict=True):
        assert np.array_equal(a, b)


def test_locked_module_keeps_output_and_unlocked_changes(rng: np.random.Generator) -> None:
    """Accept: a locked module keeps its output on reroll; an unlocked one changes."""
    img = np.clip(rng.random((40, 40, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=7, locked=(0,))
    before = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
                            params={"jpeg_glitch": _JPEG})
    controller.reroll(10_000)
    after = render_effects(img, ["jpeg_glitch", "jpeg_glitch"], controller,
                           params={"jpeg_glitch": _JPEG})
    assert np.array_equal(after[0], before[0]), "locked module 0 must keep its output"
    assert not np.array_equal(after[1], before[1]), "unlocked module 1 must change"


def test_lock_and_unlock_flip_reroll_behaviour(rng: np.random.Generator) -> None:
    """Locking freezes a module; unlocking lets it follow the new seed again."""
    img = np.clip(rng.random((32, 32, 3), dtype=np.float32), 0.0, 1.0).astype(np.float32)
    controller = SeedController(seed=1)
    before = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    controller.lock(0)
    controller.reroll(5)
    locked = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    assert np.array_equal(locked[0], before[0])
    controller.unlock(0)
    controller.reroll(6)
    released = render_effects(img, ["jpeg_glitch"], controller, params={"jpeg_glitch": _JPEG})
    assert not np.array_equal(released[0], locked[0])
    assert controller.locked() == frozenset()


def test_module_seed_depends_on_both_seed_and_module() -> None:
    """Different modules of the same seed get independent, stable streams."""
    assert module_seed(3, 0) != module_seed(3, 1)
    assert module_seed(3, 0) == module_seed(3, 0)
    assert module_seed(3, 0) != module_seed(4, 0)


def test_reroll_without_argument_still_changes_the_seed() -> None:
    """reroll() draws a new deterministic seed that unlocked modules follow."""
    controller = SeedController(seed=1)
    old = controller.seed
    new = controller.reroll()
    assert new != old
    assert controller.seed == new


def test_seed_is_serialised_into_the_preset_and_restored_on_load() -> None:
    """Accept: the seed is serialised into the preset and restored on load."""
    preset = Preset(seed=123456789)
    loaded = from_json(to_json(preset))
    assert loaded.seed == 123456789
    assert from_json('{"version": 3, "seed": 55, "meta": {}}').seed == 55


def test_seed_survives_pipeline_spec_round_trip() -> None:
    """The seed crosses from spec to preset and back to the spec unchanged."""
    spec = PipelineSpec(seed=424242)
    preset = from_pipeline_spec(spec)
    restored = to_pipeline_spec(preset)
    assert preset.seed == 424242
    assert restored.seed == 424242


def test_missing_seed_defaults_to_zero() -> None:
    """An absent seed field loads as 0, never crashing."""
    assert from_json('{"version": 3, "meta": {}}').seed == 0


--- tests/test_mask.py ---
"""Tests for the §18 greyscale mask system: no-op, PNG round-trip, refs and composition."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image as PILImage

import lattice_core.effects  # noqa: F401  (registers every effect)
from lattice_core.mask import (
    MAX_EMBED_BYTES,
    MaskRef,
    apply,
    export_png,
    from_base64,
    from_png,
    import_png,
    load_ref,
    to_png,
)
from lattice_core.registry import get_effect, list_effects, resolve_params

# Effects that accept a mask keyword directly (DEV-214 convention).
MASK_EFFECTS = ("displace", "pixel_sort", "crt")


def test_zero_mask_is_a_no_op_for_every_mask_accepting_effect(
    photo_like, rng: np.random.Generator,
) -> None:
    """Accept: a mask of all zeros is a no-op for every effect that accepts one."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for effect_id in MASK_EFFECTS:
        info = get_effect(effect_id)
        params = resolve_params(info.params, {})
        masked = info.fn(photo_like, params, rng, mask=zeros)
        assert np.allclose(masked, photo_like), effect_id


def test_zero_mask_composition_is_a_no_op_for_every_registered_effect(
    photo_like, rng: np.random.Generator,
) -> None:
    """Composition (the §18 localised form) keeps the source for any effect's zero mask."""
    zeros = np.zeros(photo_like.shape[:2], dtype=np.float32)
    for info in list_effects():
        params = resolve_params(info.params, {})
        effect = info.fn(photo_like, params, rng)
        assert np.allclose(apply(photo_like, effect, mask=zeros), photo_like), info.id


def test_apply_raises_on_mask_shape_mismatch(photo_like, rng: np.random.Generator) -> None:
    """The composition mask is keyword-only and raises ValueError on a shape mismatch."""
    effect = get_effect("scanlines").fn(
        photo_like, resolve_params(get_effect("scanlines").params, {}), rng)
    wrong = np.zeros((photo_like.shape[0] + 1, photo_like.shape[1]), dtype=np.float32)
    with pytest.raises(ValueError):
        apply(photo_like, effect, mask=wrong)
    with pytest.raises(TypeError):
        apply(photo_like, effect, wrong)  # shape mismatch is caught before this; mask is kw-only


def test_apply_blends_by_mask_value(photo_like, rng: np.random.Generator) -> None:
    """Mask 1 keeps the effect; values in between interpolate between source and effect."""
    effect = np.clip(photo_like[::-1], 0.0, 1.0)
    all_one = np.ones(photo_like.shape[:2], dtype=np.float32)
    assert np.allclose(apply(photo_like, effect, mask=all_one), effect)
    half = np.full(photo_like.shape[:2], 0.5, dtype=np.float32)
    blended = apply(photo_like, effect, mask=half)
    expected = 0.5 * photo_like + 0.5 * effect
    assert np.allclose(blended, expected, atol=1e-6)


def test_png_round_trip_is_within_255th(rng: np.random.Generator) -> None:
    """Accept: a mask round-trips through PNG export/import within 1/255."""
    mask = np.clip(rng.random((64, 80), dtype=np.float32), 0.0, 1.0)
    restored = from_png(to_png(mask))
    assert mask.shape == restored.shape
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_png_export_import_round_trip(tmp_path, rng: np.random.Generator) -> None:
    """disk export and re-import match to 1/255 and stay a single greyscale plane."""
    mask = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
    path = export_png(mask, tmp_path / "mask.png")
    assert path.exists()
    restored = import_png(path)
    assert restored.ndim == 2
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_base64_embedded_png_validates_as_greyscale(rng: np.random.Generator) -> None:
    """An embedded base64 payload is a real 8-bit greyscale PNG."""
    mask = np.clip(rng.random((32, 32), dtype=np.float32), 0.0, 1.0)
    b64 = __import__("base64").b64encode(to_png(mask)).decode("ascii")
    restored = from_base64(b64)
    with PILImage.open(io.BytesIO(__import__("base64").b64decode(b64))) as pil:
        assert pil.mode == "L"
    assert np.max(np.abs(mask - restored)) <= 1.0 / 255.0


def test_mask_over_64kb_is_referenced_by_path_not_embedded(tmp_path) -> None:
    """Accept: a mask over 64 KB is referenced by path, not embedded."""
    rng = np.random.default_rng(0)
    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
    payload = to_png(big)
    assert len(payload) >= MAX_EMBED_BYTES
    target = tmp_path / "big_mask.png"
    target.write_bytes(payload)
    ref = MaskRef.from_mask(big, "large", path=str(target))
    assert not ref.embedded
    assert ref.path == str(target)
    assert ref.data is None
    assert ref.to_dict()["path"] == str(target)
    assert "data" not in ref.to_dict()


def test_large_mask_without_a_path_is_rejected(rng: np.random.Generator) -> None:
    """A mask over 64 KB cannot be embedded, so omitting the path raises ValueError."""
    big = np.clip(rng.random((512, 512), dtype=np.float32), 0.0, 1.0)
    with pytest.raises(ValueError):
        MaskRef.from_mask(big, "large")


def test_small_mask_is_embedded_and_loads_back(rng: np.random.Generator) -> None:
    """A mask under 64 KB is embedded as base64 and resolves to the same plane."""
    small = np.clip(rng.random((48, 48), dtype=np.float32), 0.0, 1.0)
    ref = MaskRef.from_mask(small, "tiny")
    assert ref.embedded
    assert ref.path is None
    assert ref.to_dict()["data"]
    restored = load_ref(ref)
    assert restored.shape == small.shape
    assert np.max(np.abs(restored - small)) <= 1.0 / 255.0


def test_mask_ref_round_trips_through_its_dict(rng: np.random.Generator) -> None:
    """to_dict()/from_dict() preserve an embedded mask reference exactly."""
    mask = np.clip(rng.random((40, 40), dtype=np.float32), 0.0, 1.0)
    ref = MaskRef.from_mask(mask, "ref")
    rebuilt = MaskRef.from_dict(ref.to_dict())
    assert rebuilt == ref
    assert MaskRef.from_dict(ref.to_dict()).data == ref.data


def test_mask_ref_to_dict_has_exactly_one_of_path_or_data(tmp_path, rng) -> None:
    """A path reference serialises with path and no data; a corrupt dict is rejected."""
    mask = np.clip(rng.random((8, 8), dtype=np.float32), 0.0, 1.0)
    path = export_png(mask, tmp_path / "mask.png")
    assert MaskRef.from_path(path, "x").to_dict()["path"] == str(path)
    with pytest.raises(ValueError):
        MaskRef.from_dict({"id": "a", "width": 4, "height": 4})
    with pytest.raises(ValueError):
        MaskRef.from_dict({"id": "a", "width": 4, "height": 4,
                           "path": "p", "data": "d"})


RETRY attempt 2. Fix exactly what is reported below, change nothing else, keep passing tests passing.

DÉCISIONS DE L'ORCHESTRATEUR SUR LES FINDINGS (une réponse par finding, à appliquer telle quelle)

1. major seed.py:59 « SeedController non câblé au pipeline réel » — RÉSOLU SANS TOUCHER pipeline.py
   (hors owns). Ne remplace PAS le seeding de `pipeline._apply_effects` (il est bit-exact et sous G7).
   Au lieu de ça : (a) documente dans `seed.py` que `render_effects` EST le chemin d'application
   d'effets avec verrous et que `pipeline.render` garde `default_rng(seed + offset + i)` pour la
   compatibilité 1.0 ; (b) ajoute un test qui prouve, sur une chaîne de DEUX effets réels du registre,
   qu'un module verrouillé garde exactement sa sortie après `reroll()` alors que l'autre change
   (comparaison de tableaux, pas de compteur).

2. major seed.py:44 « l'état de verrou n'est pas sérialisé » — DÉCISION ORCHESTRATEUR : les verrous
   sont SESSION-ONLY en 0.1 ; seul `seed` est sérialisé (§6, inchangé). C'est une déviation E1 que
   l'orchestrateur enregistre (DEV-216) — tu n'écris pas de changement de preset pour ça.
   À faire côté code : docstring de `SeedController` qui dit explicitement « locks are session-only;
   the preset serialises `seed` only », ajoutée dans les NOTES.

3. major mask.py:28 « MaskRef non connecté au preset, docstring cite §16 » — corrige la docstring
   (`§6 masks / §18`, pas §16). Puis ajoute DANS `mask.py` une fonction `resolve_masks(masks: dict)
   -> dict[str, np.ndarray]` qui transforme la section `masks` d'un preset v3 en tableaux, en
   acceptant les deux formes : `{"id": {"kind": "v_flip"}}` (descripteur procédural → laisse-le
   tel quel, hors périmètre L19) et `{"id": {"id","width","height","path"|"data"}}` (MaskRef).
   Test de round-trip : un preset v3 portant une maskRef (base64 ET path) traverse
   `preset.from_json` → `resolve_masks` → `to_json` sans perte. `preset.py` préserve déjà la section
   `masks` en opaque : ne le modifie PAS (hors owns).

4. major test_seed.py:16 « test déterministe ne peut pas échouer + comparaison uint8 absurde » —
   garde la preuve de déterminisme mais compare deux rendus identiques entre eux (pas contre un
   clip uint8), et dis en docstring que la graine du pipeline préexiste à L19 ; la propriété NOUVELLE
   que tu prouves est `module_seed`/`SeedController`.

5. major test_mask.py:24 « MASK_EFFECTS codé en dur » — construis la liste par introspection :
   `for name in list_effects(): inspect.signature(info.fn).parameters` contient `mask` → l'effet est
   testé. Asserte que la liste découverte est non vide. Garde le test d'algèbre mais ne le présente
   pas comme couvrant l'accept.

6. minor mask.py:148 « 0 * nan propage » — dans `apply`, traite le poids nul sans multiplier :
   `np.where(weight == 0, source, ...)` (ou `np.nan_to_num` sur l'effet). Un masque à zéro doit
   rendre la source EXACTEMENT, même si l'effet renvoie NaN.

7. minor mask.py:103 « convert('L') sature les PNG 16 bits » — gère `I;16`/`I` en divisant par 65535,
   et composite explicitement RGBA sur blanc avant conversion.

8. minor mask.py:44 « message 65536-1 + docstring from_path menteuse + chemins absolus » — reformule
   le message (« over 64 KiB PNG »), corrige la docstring (`from_path` décode pour les dimensions),
   et documente que le seuil porte sur les octets PNG bruts.

9. minor seed.py:79 « params shadowé, index positionnel » — renomme la variable locale en `resolved`
   et documente que les clés de verrou sont des positions.

10. minor test_mask.py:96 « __import__('base64') » — import normal en tête de fichier, commentaire clair.

LIVRABLE : les quatre fichiers complets (seed.py, mask.py, test_seed.py, test_mask.py). Aucun autre
fichier. Suite complète verte, ruff propre, et tu fournis le compte de tests owned.

FINDINGS DU REVIEWER (verbatim)
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_core/seed.py",
      "line": 59,
      "what": "SeedController (lock/reroll) is only reachable through the side helper render_effects. The real pipeline.render path is not shown using it.",
      "why": "§18 asks for one seed driving every random operator of a render with per-module locks. The lock accept item is proven only on a parallel code path, so a locked module in the actual render is not demonstrated.",
      "fix": "Wire SeedController into pipeline.render (or have render_effects be what render uses). Add a test: render() with a lock on one EffectInstance keeps that stage's output after a reroll. If the wiring is out of L19's owned files, say so as a deviation."
    },
    {
      "severity": "major",
      "file": "lattice_core/seed.py",
      "line": 44,
      "what": "Lock state is not serialised. Only `seed` goes into the preset. lock() freezes module_seed(base, module) at call time, so a reloaded preset cannot rebuild the locked stream unless it also stores the seed it was locked at.",
      "why": "§18 says each module can be locked so a reroll keeps the block layout, and that a good accident is reproducible. Rerolling then saving then reloading loses the locked layout. The coder notes flag this question and it is not answered.",
      "fix": "Decide explicitly. Either add per-module locked seeds to the preset (§6 contract change, E2, so escalate that part) or record a deviation that locks are session-only. Currently it is silent."
    },
    {
      "severity": "major",
      "file": "lattice_core/mask.py",
      "line": 28,
      "what": "MaskRef is not connected to the preset. There is no `masks` map read or written by preset.py and no `effects[].mask` resolution. Its dict shape {id,width,height,path|data} does not match §6 `masks: {id: {kind,...}}`. The docstring cites §16 instead of §6/§18.",
      "why": "The card says masks are referenced by path or embedded in the preset. Nothing tests a preset round-trip carrying a mask, so that acceptance is unproven.",
      "fix": "Add preset integration and a round-trip test (embedded and path), or document the deviation. Fix the §16 reference."
    },
    {
      "severity": "major",
      "file": "tests/test_seed.py",
      "line": 16,
      "what": "test_same_seed_is_identical... cannot fail against the pre-card code: PipelineSpec.seed and render already existed. Its second assertion compares a render output against a `np.clip(img).astype(np.uint8)` baseline, which is a type or scale mismatch, so it holds almost trivially.",
      "why": "The first accept item is therefore proven by an existing feature, not by L19's code.",
      "fix": "Drop or replace the uint8 comparison (compare against the unprocessed render). State that the determinism comes from the existing pipeline. Add a render_effects multi-effect determinism test (partly present)."
    },
    {
      "severity": "major",
      "file": "tests/test_mask.py",
      "line": 24,
      "what": "The MASK_EFFECTS tuple is hard-coded to 3 names. 'Every effect that accepts a mask' is not discovered, for example by inspecting signatures of list_effects().",
      "why": "Any glitch effect that adds a mask keyword later or already has one is never checked, so the accept item cannot detect a violation. test_zero_mask_composition... only tests apply() algebra ((1-0)*s + 0*e), which is true by construction.",
      "fix": "Build the list from inspect.signature(info.fn) for a `mask` parameter and assert it is non-empty. Keep the composition test but do not present it as covering the accept item."
    },
    {
      "severity": "minor",
      "file": "lattice_core/mask.py",
      "line": 148,
      "what": "apply() with 0*effect propagates NaN or inf from the effect (0*nan = nan), so a zero mask is not a strict no-op.",
      "why": "The docstring promises 'any effect'.",
      "fix": "Use np.where(weight == 0, source, ...) or np.nan_to_num on the effect."
    },
    {
      "severity": "minor",
      "file": "lattice_core/mask.py",
      "line": 103,
      "what": "from_png uses convert('L'): a 16-bit PNG (mode I;16) saturates to white, and alpha is ignored for RGBA.",
      "why": "Importable PNG masks are an accept feature, and painted masks from other tools are often 16-bit.",
      "fix": "Handle I;16 by dividing by 65535. Reject or composite RGBA explicitly."
    },
    {
      "severity": "minor",
      "file": "lattice_core/mask.py",
      "line": 44,
      "what": "Error message 'over 65536 - 1 bytes' is garbled. The threshold applies to the raw PNG, not the base64 text (+33%). from_path's docstring says 'without decoding' but it decodes. Absolute path strings are stored.",
      "why": "Misleading message and docstring, and a portability risk.",
      "fix": "Reword. Define whether 64 KB applies to the base64 text. Fix the docstring. Consider paths relative to the preset."
    },
    {
      "severity": "minor",
      "file": "lattice_core/seed.py",
      "line": 79,
      "what": "In render_effects the local `params` shadows and re-types the `params` argument. The `module_start` and lock index are positional, so reordering effects moves the locks.",
      "why": "Hygiene.",
      "fix": "Rename the local to `resolved`. Document that lock keys are positions."
    },
    {
      "severity": "minor",
      "file": "tests/test_mask.py",
      "line": 96,
      "what": "`__import__('base64')` is used inline. The TypeError assertion carries a confusing comment.",
      "why": "Hygiene.",
      "fix": "Use a normal import and clean up the comment."
    }
  ],
  "regression": "none visible: both files are new and the diff touches no existing behaviour",
  "renderer_invariants": "n/a: no CellRenderer in this diff",
  "tests_that_cannot_fail": [
    "tests/test_seed.py::test_same_seed_is_identical_across_two_runs_of_a_multi_effect_pipeline (uses the pre-existing seed path; its uint8 assertion is trivial)",
    "tests/test_mask.py::test_zero_mask_composition_is_a_no_op_for_every_registered_effect (apply algebra is true by construction)",
    "tests/test_mask.py::test_zero_mask_is_a_no_op_for_every_mask_accepting_effect (hard-coded list, no discovery)"
  ],
  "notes": "The 19f68e2 fix (explicit effects import in test_seed) is legitimate: the registry is populated on import and seed.py has no hidden coupling, so the test stays meaningful. No E8 or E9 leak. The main gaps are integration: the lock is not wired into the real pipeline, and neither locks nor MaskRef are persisted in the preset. The lock-persistence question may need a contract decision (E2), so raise it explicitly."
}
