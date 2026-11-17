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

CONTRACT EXCERPTS (version 0.1.0)
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

### L4 · Preset format v3
- wave: 0 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/preset.py`, `tests/test_preset.py`, `tests/data/presets/**`
- context: §6
- spec: implement §6. `from_json` accepts 1, 2 and 3; 1 and 2 map to `app: "dither"`,
  `renderer: "pixel"`. Unknown top-level keys and unknown `style` keys are preserved on round-trip.
  An `app` mismatch is not an error; a missing renderer falls back to the app default and records a
  warning. `to_json` writes sorted keys, two-space indent, one trailing newline. Coordonne
  `renderer`/`renderer_style` avec les champs de `PipelineSpec` apportés par L2b (H11).
- accept:
  - every preset in `presets/` loads and reports the right `version`.
  - a v3 preset round-trips through `to_json`/`from_json` with equality.
  - a preset carrying an unknown key `"future": {"x": 1}` survives a load/save unchanged.
  - `version: 4` raises `ValueError` naming 4.
  - loading a `glyph` preset in a `dither` context returns a warning and a `pixel` renderer.
  - `to_json` output is byte-stable across two calls.

GATE RESULTS (L4, attempt 2 — retry après FIX du pass 1)
- G1 ruff: clean. Owned tests : **65 passed** (test_preset.py). Suite complète : 1463 passed
  + 12 échecs — TOUS dans les fichiers des cartes parallèles encore en vol (test_bitmask.py ×8,
  registre renderer test_cell.py ×1, test_ui_shared.py ×3), AUCUN dans test_preset.py.
  Contrôle d'isolation orchestrateur (base + owned, sans les fichiers parallèles) :
  **1400 passed / 1 skip — la base 1372 reste verte**. G3/G7/G8 rejoués en batterie complète
  quand L6/L8/L-UI atterrissent.
- Cadre : carte produite par **hy4-flash-free (opencode-go)** — épreuve de la couche masse.
  Pass 1 : FIX (1 major + 4 minors). Ce pass 2 juge la qualité du retry.

PASS 1 FINDINGS — DISPOSITION (attempt 2)
- major « missing renderer → app default + warning non implémenté » → implémenté : helper
  unique `_apply_renderer` dans `_from_v3` et `_from_legacy` (contexte app= ou preset.app),
  6 cas testés (glyph, dither, app inconnue, sans app, override de contexte, renderer sans name).
- minor « APP_RENDERERS duplique le registre » → `available=` ajouté à from_json/load_preset :
  l'hôte fournit la disponibilité réelle (table conservée par défaut, commentée E1).
- minor « extra écrase les clés v3 » → `_preset_dict` écrit extra en premier, `_from_legacy`
  exclut `_V3_TOP` : plus d'écrasement des sections typées.
- minor « validation lâche » → `_version`/`_as_int` rejettent bools/floats/strings ;
  `_section` nomme la section ; effets via `_as_dict` avec index.
- minor « paramétrisation fragile » → test non-vacuous sur presets/ + `match=r"\b4\b"`.
- Note orchestrateur (le pass 1 n'avait pas reçu §6) : les 6 accept sont maintenant vérifiés
  contre §6 — test couvrant 11 sections, stages, masques, fonts, output.

DIFF (arbre de travail vs HEAD — état complet de la carte, attempts 1+2)
diff --git a/lattice_core/preset.py b/lattice_core/preset.py
new file mode 100644
index 0000000..da371ed
--- /dev/null
+++ b/lattice_core/preset.py
@@ -0,0 +1,388 @@
+"""Preset format v3: one portable, diffable preset format shared by every Lattice app."""
+
+from __future__ import annotations
+
+import json
+from collections.abc import Iterable
+from dataclasses import asdict, dataclass, field
+from pathlib import Path
+from typing import Any, Literal
+
+from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec
+
+PRESET_VERSION = 3
+SUPPORTED_VERSIONS = (1, 2, 3)
+DEFAULT_APP = "dither"
+APP_DEFAULT_RENDERER: dict[str, str] = {
+    "dither": "pixel",
+    "glyph": "glyph_ramp",
+    "glitch": "pixel",
+}
+# E1: section 6 is silent on availability; hosts may override this with `available=`.
+APP_RENDERERS: dict[str, frozenset[str]] = {
+    "dither": frozenset({"pixel"}),
+    "glyph": frozenset({"glyph_ramp", "glyph_shape", "bitmask", "text", "pixel"}),
+    "glitch": frozenset({"pixel"}),
+}
+_LEGACY_TOP = frozenset({
+    "version", "pre_effects", "post_effects", "brightness", "contrast", "gamma",
+    "saturation", "pre_blur", "auto_levels", "color_metric", "pixel_size",
+    "algorithm_id", "algorithm_params", "palette", "seed", "meta", "renderer",
+    "renderer_style",
+})
+_V3_TOP = frozenset({
+    "version", "app", "meta", "renderer", "palette", "pipeline", "effects", "masks",
+    "fonts", "output", "seed",
+})
+_LEGACY_SOURCE = {"builtin": "integrated", "extracted": "image", "custom": "imported"}
+_V3_SOURCE: dict[str, Literal["builtin", "extracted", "custom"]] = {
+    "integrated": "builtin",
+    "image": "extracted",
+    "imported": "custom",
+}
+_PIPELINE_KEYS = ("color_metric", "pixel_size", "brightness", "contrast", "gamma",
+                  "saturation", "pre_blur", "auto_levels")
+
+
+def _default_meta() -> dict[str, Any]:
+    """Return the v3 meta defaults, including the creation date field."""
+    return {"name": "", "author": "", "created": ""}
+
+
+def _default_renderer(app: str = DEFAULT_APP) -> dict[str, Any]:
+    """Return the app default renderer name and its free-form style object."""
+    return {"name": APP_DEFAULT_RENDERER.get(app, "pixel"), "style": {}}
+
+
+def _default_palette() -> dict[str, Any]:
+    """Return the complete v3 palette object, including extraction settings."""
+    return {
+        "colors": ["#000000", "#ffffff"],
+        "locked": False,
+        "order": None,
+        "source": "integrated",
+        "extract": {"from": "image", "n_colors": 16, "rows": None},
+    }
+
+
+def _default_pipeline() -> dict[str, Any]:
+    """Return the v3 pipeline defaults from contract section 6."""
+    return {
+        "algorithm": "floyd_steinberg",
+        "params": {},
+        "color_metric": "srgb",
+        "pixel_size": 1,
+        "max_side": None,
+        "brightness": 0.0,
+        "contrast": 0.0,
+        "gamma": 1.0,
+        "saturation": 0.0,
+        "pre_blur": 0.0,
+        "auto_levels": False,
+    }
+
+
+def _default_output() -> dict[str, Any]:
+    """Return the default output size settings."""
+    return {"scale": 1, "width": None, "dpi": None}
+
+
+@dataclass
+class Preset:
+    """A v3 preset: typed sections, preserved unknown keys and load warnings."""
+
+    version: int = PRESET_VERSION
+    app: str = DEFAULT_APP
+    meta: dict[str, Any] = field(default_factory=_default_meta)
+    renderer: dict[str, Any] = field(default_factory=_default_renderer)
+    palette: dict[str, Any] = field(default_factory=_default_palette)
+    pipeline: dict[str, Any] = field(default_factory=_default_pipeline)
+    effects: list[dict[str, Any]] = field(default_factory=list)
+    masks: dict[str, Any] = field(default_factory=dict)
+    fonts: dict[str, Any] = field(default_factory=dict)
+    output: dict[str, Any] = field(default_factory=_default_output)
+    seed: int = 0
+    extra: dict[str, Any] = field(default_factory=dict)
+    warnings: list[str] = field(default_factory=list, compare=False, repr=False)
+
+    def __post_init__(self) -> None:
+        """Point an untouched default renderer at a non-dither app's default."""
+        if self.app != DEFAULT_APP and self.renderer == _default_renderer():
+            self.renderer = _default_renderer(self.app)
+
+
+def to_json(preset: Preset) -> str:
+    """Serialise preset as sorted, two-space-indented v3 JSON with one trailing newline."""
+    data = _preset_dict(preset)
+    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
+
+
+def from_json(
+    text: str, *, app: str | None = None, available: Iterable[str] | None = None,
+) -> Preset:
+    """Parse a v1, v2 or v3 preset; an explicit app context resolves absent renderers."""
+    try:
+        data = json.loads(text)
+    except json.JSONDecodeError as exc:
+        raise ValueError(f"invalid preset JSON: {exc}") from exc
+    if not isinstance(data, dict):
+        raise ValueError("preset JSON must be an object")
+    version = _version(data)
+    context = app if app is not None else (
+        str(data.get("app", DEFAULT_APP)) if version == PRESET_VERSION else DEFAULT_APP
+    )
+    if version == PRESET_VERSION:
+        preset = _from_v3(data, context, available)
+    else:
+        preset = _from_legacy(data, version, context, available)
+    return preset
+
+
+def save_preset(path: str | Path, preset: Preset) -> None:
+    """Write preset as UTF-8 v3 JSON, creating parent directories."""
+    target = Path(path)
+    target.parent.mkdir(parents=True, exist_ok=True)
+    target.write_text(to_json(preset), encoding="utf-8")
+
+
+def load_preset(
+    path: str | Path, *, app: str | None = None, available: Iterable[str] | None = None,
+) -> Preset:
+    """Read a JSON preset file and parse it with an optional app context."""
+    return from_json(Path(path).read_text(encoding="utf-8"), app=app, available=available)
+
+
+def to_pipeline_spec(preset: Preset) -> PipelineSpec:
+    """Return a PipelineSpec carrying the v3 renderer name and style (H11)."""
+    source = preset.pipeline
+    spec = PipelineSpec()
+    spec.algorithm_id = source.get("algorithm")
+    spec.algorithm_params = dict(_as_dict(source.get("params", {}), "params"))
+    for key in _PIPELINE_KEYS:
+        if key in source:
+            setattr(spec, key, source[key])
+    for entry in preset.effects:
+        effect = _effect_instance(entry)
+        (spec.pre_effects if entry.get("stage", "post") == "pre" else spec.post_effects).append(
+            effect)
+    spec.palette = _spec_palette(preset.palette)
+    spec.seed = preset.seed
+    spec.meta.name = str(preset.meta.get("name", ""))
+    spec.meta.author = str(preset.meta.get("author", ""))
+    spec.renderer = str(preset.renderer.get("name", "pixel"))
+    spec.renderer_style = dict(_as_dict(preset.renderer.get("style", {}), "style"))
+    return spec
+
+
+def from_pipeline_spec(spec: PipelineSpec) -> Preset:
+    """Build a v3 preset from a PipelineSpec, keeping renderer and renderer_style."""
+    # The spec itself declares the renderer available, so no context fallback applies.
+    return _from_legacy(
+        asdict(spec), int(spec.version), DEFAULT_APP, frozenset({str(spec.renderer)}),
+    )
+
+
+def _preset_dict(preset: Preset) -> dict[str, Any]:
+    """Return the JSON object of preset: typed v3 sections win over preserved keys."""
+    data: dict[str, Any] = dict(preset.extra)
+    data.update({
+        "version": PRESET_VERSION,
+        "app": preset.app,
+        "meta": dict(preset.meta),
+        "renderer": dict(preset.renderer),
+        "palette": dict(preset.palette),
+        "pipeline": dict(preset.pipeline),
+        "effects": [dict(entry) for entry in preset.effects],
+        "masks": dict(preset.masks),
+        "fonts": dict(preset.fonts),
+        "output": dict(preset.output),
+        "seed": preset.seed,
+    })
+    return data
+
+
+def _version(data: dict[str, Any]) -> int:
+    """Return the parsed version, rejecting bools, floats and strings by name."""
+    value = data.get("version", PRESET_VERSION)
+    if isinstance(value, bool) or not isinstance(value, int):
+        raise ValueError(f"unsupported preset version: {value!r}")
+    if value not in SUPPORTED_VERSIONS:
+        raise ValueError(f"unsupported preset version: {value}")
+    return value
+
+
+def _section(value: object, defaults: dict[str, Any], name: str) -> dict[str, Any]:
+    """Merge one named JSON section over fresh defaults, keeping keys the defaults lack."""
+    if value is None:
+        return dict(defaults)
+    if not isinstance(value, dict):
+        raise ValueError(f"preset section {name!r} must be an object")
+    merged = dict(defaults)
+    merged.update(value)
+    return merged
+
+
+def _as_int(value: object, key: str) -> int:
+    """Return an int or raise ValueError naming the key; bools and floats are rejected."""
+    if isinstance(value, bool) or not isinstance(value, int):
+        raise ValueError(f"preset key {key!r} must be an integer")
+    return value
+
+
+def _as_list(value: object, key: str) -> list:
+    """Return value as a list or raise ValueError naming the offending key."""
+    if not isinstance(value, list):
+        raise ValueError(f"preset key {key!r} must be a list")
+    return value
+
+
+def _as_dict(value: object, key: str) -> dict:
+    """Return value as a dict or raise ValueError naming the offending key."""
+    if not isinstance(value, dict):
+        raise ValueError(f"preset key {key!r} must be an object")
+    return value
+
+
+def _from_v3(
+    data: dict[str, Any], context: str, available: Iterable[str] | None,
+) -> Preset:
+    """Build a Preset from v3 JSON, merging defaults and preserving unknown keys."""
+    preset = Preset()
+    preset.app = str(data.get("app", DEFAULT_APP))
+    renderer = data.get("renderer")
+    named = isinstance(renderer, dict) and "name" in renderer
+    preset.renderer = _section(renderer, _default_renderer(context), "renderer")
+    preset.meta = _section(data.get("meta"), _default_meta(), "meta")
+    preset.palette = _section(data.get("palette"), _default_palette(), "palette")
+    preset.pipeline = _section(data.get("pipeline"), _default_pipeline(), "pipeline")
+    preset.output = _section(data.get("output"), _default_output(), "output")
+    preset.effects = [
+        dict(_as_dict(entry, f"effects[{index}]"))
+        for index, entry in enumerate(_as_list(data.get("effects", []), "effects"))
+    ]
+    preset.masks = _section(data.get("masks"), {}, "masks")
+    preset.fonts = _section(data.get("fonts"), {}, "fonts")
+    preset.seed = _as_int(data.get("seed", 0), "seed")
+    preset.extra = {key: value for key, value in data.items() if key not in _V3_TOP}
+    _apply_renderer(preset, context, named, available)
+    return preset
+
+
+def _from_legacy(
+    data: dict[str, Any], version: int, context: str = DEFAULT_APP,
+    available: Iterable[str] | None = None,
+) -> Preset:
+    """Map a Lattice Dither v1/v2 preset onto the v3 shape without losing data."""
+    preset = Preset(version=version, app=DEFAULT_APP)
+    preset.meta = _section(data.get("meta"), _default_meta(), "meta")
+    renderer = data.get("renderer")
+    named = isinstance(renderer, str) or (isinstance(renderer, dict) and "name" in renderer)
+    if isinstance(renderer, str):
+        preset.renderer["name"] = renderer
+    elif isinstance(renderer, dict):
+        preset.renderer.update(renderer)
+    if "renderer_style" in data:
+        preset.renderer["style"] = dict(_as_dict(data["renderer_style"], "renderer_style"))
+    preset.palette = _legacy_palette(data.get("palette"))
+    preset.pipeline = _legacy_pipeline(data)
+    preset.effects = (_legacy_effects(data.get("pre_effects"), "pre")
+                      + _legacy_effects(data.get("post_effects"), "post"))
+    preset.seed = _as_int(data.get("seed", 0), "seed")
+    preset.extra = {
+        key: value for key, value in data.items()
+        if key not in _LEGACY_TOP and key not in _V3_TOP
+    }
+    _apply_renderer(preset, context, named, available)
+    return preset
+
+
+def _legacy_palette(value: object) -> dict[str, Any]:
+    """Map a v2 PaletteSpec onto the v3 palette object, keeping v2-only settings."""
+    palette = _default_palette()
+    if value is None:
+        return palette
+    source = _as_dict(value, "palette")
+    palette["colors"] = [str(entry) for entry in _as_list(source.get("colors", []), "colors")]
+    palette["source"] = _LEGACY_SOURCE.get(str(source.get("source", "builtin")), "imported")
+    palette["extract"] = {
+        "from": "image",
+        "n_colors": _as_int(source.get("extract_k", 16), "extract_k"),
+        "rows": None,
+    }
+    for key in ("name", "extract_method", "locked", "order"):
+        if key in source:
+            palette[key if key != "locked" else "locked_colours"] = source[key]
+    return palette
+
+
+def _legacy_pipeline(data: dict[str, Any]) -> dict[str, Any]:
+    """Map the flat v2 pipeline fields onto the v3 pipeline object."""
+    pipeline = _default_pipeline()
+    if data.get("algorithm_id") is not None:
+        pipeline["algorithm"] = data["algorithm_id"]
+    pipeline["params"] = dict(_as_dict(data.get("algorithm_params", {}), "algorithm_params"))
+    for key in _PIPELINE_KEYS:
+        if key in data:
+            pipeline[key] = data[key]
+    return pipeline
+
+
+def _legacy_effects(value: object, stage: str) -> list[dict[str, Any]]:
+    """Map a v2 effect list onto v3 entries tagged with their stage."""
+    entries: list[dict[str, Any]] = []
+    for item in _as_list(value if value is not None else [], f"{stage}_effects"):
+        source = _as_dict(item, "effect")
+        entry = dict(source)
+        entry["name"] = source.get("effect_id", "")
+        entry.pop("effect_id", None)
+        entry.setdefault("params", {})
+        entry.setdefault("enabled", True)
+        entry.setdefault("mask", None)
+        entry["stage"] = stage
+        entries.append(entry)
+    return entries
+
+
+def _apply_renderer(
+    preset: Preset, app: str, named: bool, available: Iterable[str] | None,
+) -> None:
+    """Fall back to the app default, with a warning, when a renderer is absent or unavailable."""
+    table = frozenset(available) if available is not None else APP_RENDERERS.get(app, frozenset())
+    default = APP_DEFAULT_RENDERER.get(app, "pixel")
+    name = str(preset.renderer.get("name", ""))
+    if not named:
+        preset.renderer["name"] = default
+        preset.warnings.append(f"renderer absent in app {app!r}; using {default!r}")
+        return
+    if name in table:
+        return
+    preset.renderer["name"] = default
+    preset.warnings.append(f"renderer {name!r} unavailable in app {app!r}; using {default!r}")
+
+
+def _effect_instance(entry: dict[str, Any]) -> EffectInstance:
+    """Build an EffectInstance from one v3 effect entry."""
+    return EffectInstance(
+        effect_id=str(entry.get("name", "")),
+        params=dict(_as_dict(entry.get("params", {}), "params")),
+        enabled=bool(entry.get("enabled", True)),
+    )
+
+
+def _spec_palette(palette: dict[str, Any]) -> PaletteSpec:
+    """Build a PaletteSpec from a v3 palette object, reversing the v2 source mapping."""
+    spec = PaletteSpec()
+    spec.source = _V3_SOURCE.get(str(palette.get("source", "integrated")), "custom")
+    spec.colors = [str(entry) for entry in palette.get("colors", [])]
+    if palette.get("name") is not None:
+        spec.name = str(palette["name"])
+    extract = _as_dict(palette.get("extract", {}), "extract")
+    if extract.get("n_colors") is not None:
+        spec.extract_k = _as_int(extract["n_colors"], "n_colors")
+    if palette.get("extract_method") is not None:
+        spec.extract_method = str(palette["extract_method"])
+    if palette.get("locked_colours") is not None:
+        spec.locked = [str(entry) for entry in palette["locked_colours"]]
+    if palette.get("order") is not None:
+        spec.order = [_as_int(entry, "order") for entry in palette["order"]]
+    return spec
diff --git a/tests/data/presets/dither_v3.json b/tests/data/presets/dither_v3.json
new file mode 100644
index 0000000..675c584
--- /dev/null
+++ b/tests/data/presets/dither_v3.json
@@ -0,0 +1,31 @@
+{
+  "version": 3,
+  "app": "dither",
+  "meta": {"name": "Game Boy", "author": "Lattice", "created": "2026-11-16"},
+  "renderer": {"name": "pixel", "style": {}},
+  "palette": {
+    "colors": ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
+    "locked": false,
+    "order": null,
+    "source": "integrated",
+    "extract": {"from": "image", "n_colors": 16, "rows": null}
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "params": {},
+    "color_metric": "srgb",
+    "pixel_size": 2,
+    "max_side": null,
+    "brightness": 0.0,
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "saturation": 0.0,
+    "pre_blur": 0.0,
+    "auto_levels": false
+  },
+  "effects": [],
+  "masks": {},
+  "fonts": {},
+  "output": {"scale": 1, "width": null, "dpi": null},
+  "seed": 0
+}
diff --git a/tests/data/presets/future_keys_v3.json b/tests/data/presets/future_keys_v3.json
new file mode 100644
index 0000000..1fea8a6
--- /dev/null
+++ b/tests/data/presets/future_keys_v3.json
@@ -0,0 +1,35 @@
+{
+  "version": 3,
+  "app": "dither",
+  "meta": {"name": "Future preset", "author": "", "created": ""},
+  "renderer": {
+    "name": "pixel",
+    "style": {"scale": 2, "a_future_style_option": {"keep": true}}
+  },
+  "palette": {
+    "colors": ["#000000", "#ffffff"],
+    "locked": false,
+    "order": null,
+    "source": "integrated",
+    "extract": {"from": "image", "n_colors": 16, "rows": null}
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "params": {},
+    "color_metric": "srgb",
+    "pixel_size": 1,
+    "max_side": null,
+    "brightness": 0.0,
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "saturation": 0.0,
+    "pre_blur": 0.0,
+    "auto_levels": false
+  },
+  "effects": [],
+  "masks": {},
+  "fonts": {},
+  "output": {"scale": 1, "width": null, "dpi": null},
+  "seed": 5,
+  "future": {"x": 1}
+}
diff --git a/tests/data/presets/glyph_v3.json b/tests/data/presets/glyph_v3.json
new file mode 100644
index 0000000..7621610
--- /dev/null
+++ b/tests/data/presets/glyph_v3.json
@@ -0,0 +1,37 @@
+{
+  "version": 3,
+  "app": "glyph",
+  "meta": {"name": "Amber terminal", "author": "Marin", "created": "2026-11-16"},
+  "renderer": {
+    "name": "glyph_ramp",
+    "style": {"ramp": " .:-=+*#%@", "mode": "palette", "offset": 0.1, "invert": false}
+  },
+  "palette": {
+    "colors": ["#000000", "#ffffff"],
+    "locked": false,
+    "order": null,
+    "source": "integrated",
+    "extract": {"from": "image", "n_colors": 16, "rows": null}
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "params": {},
+    "color_metric": "srgb",
+    "pixel_size": 2,
+    "max_side": null,
+    "brightness": 0.0,
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "saturation": 0.0,
+    "pre_blur": 0.0,
+    "auto_levels": false
+  },
+  "effects": [
+    {"name": "scanlines", "params": {"intensity": 0.2}, "enabled": true, "stage": "pre", "mask": null},
+    {"name": "glow", "params": {}, "enabled": false, "stage": "post", "mask": "glow_mask"}
+  ],
+  "masks": {"glow_mask": {"kind": "v_flip"}},
+  "fonts": {"ramp": {"family": "DejaVu Sans Mono", "style": "", "fallback": ["mono"]}},
+  "output": {"scale": 2, "width": null, "dpi": 300},
+  "seed": 7
+}
diff --git a/tests/data/presets/legacy_v1.json b/tests/data/presets/legacy_v1.json
new file mode 100644
index 0000000..02e88a3
--- /dev/null
+++ b/tests/data/presets/legacy_v1.json
@@ -0,0 +1,19 @@
+{
+  "version": 1,
+  "pre_effects": [],
+  "brightness": 0.0,
+  "contrast": 0.0,
+  "gamma": 1.0,
+  "pixel_size": 2,
+  "algorithm_id": "floyd_steinberg",
+  "algorithm_params": {},
+  "palette": {
+    "source": "builtin",
+    "name": "gameboy",
+    "colors": [],
+    "extract_k": 8,
+    "extract_method": "kmeans"
+  },
+  "post_effects": [],
+  "seed": 0
+}
diff --git a/tests/data/presets/legacy_v2.json b/tests/data/presets/legacy_v2.json
new file mode 100644
index 0000000..9de0de9
--- /dev/null
+++ b/tests/data/presets/legacy_v2.json
@@ -0,0 +1,28 @@
+{
+  "version": 2,
+  "pre_effects": [{"effect_id": "scanlines", "params": {"intensity": 0.1}, "enabled": true}],
+  "brightness": 0.1,
+  "contrast": -0.2,
+  "gamma": 1.1,
+  "saturation": 0.3,
+  "pre_blur": 2.0,
+  "auto_levels": true,
+  "color_metric": "oklab",
+  "pixel_size": 3,
+  "algorithm_id": "floyd_steinberg",
+  "algorithm_params": {},
+  "palette": {
+    "source": "extracted",
+    "name": "bw",
+    "colors": ["#000000", "#ffffff"],
+    "extract_k": 6,
+    "extract_method": "median_cut",
+    "locked": ["#ffffff"],
+    "order": [1, 0]
+  },
+  "post_effects": [{"effect_id": "glow", "params": {}, "enabled": false}],
+  "seed": 42,
+  "meta": {"name": "Legacy", "author": "Marin", "description": "v2 source", "tags": ["old"]},
+  "renderer": "pixel",
+  "renderer_style": {"scale": 2}
+}
diff --git a/tests/test_preset.py b/tests/test_preset.py
new file mode 100644
index 0000000..ba05eed
--- /dev/null
+++ b/tests/test_preset.py
@@ -0,0 +1,289 @@
+"""Tests for the shared v3 preset format (card L4, contract section 6)."""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+import pytest
+
+from lattice_core import preset
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.preset import (
+    Preset,
+    from_json,
+    from_pipeline_spec,
+    load_preset,
+    save_preset,
+    to_json,
+    to_pipeline_spec,
+)
+
+ROOT = Path(__file__).resolve().parents[1]
+FIXTURES = ROOT / "tests" / "data" / "presets"
+
+
+def _all_files() -> list[Path]:
+    """Return the shipped and fixture presets in a stable order."""
+    return sorted((ROOT / "presets").glob("*.json")) + sorted(FIXTURES.glob("*.json"))
+
+
+def _fixture(name: str) -> str:
+    """Read one fixture preset as UTF-8 text."""
+    return (FIXTURES / name).read_text(encoding="utf-8")
+
+
+def test_shipped_presets_are_discovered() -> None:
+    """The shipped preset directory is not empty, so the glob test cannot pass vacuously."""
+    assert list((ROOT / "presets").glob("*.json"))
+    assert _all_files()
+
+
+@pytest.mark.parametrize("path", _all_files(), ids=lambda path: path.name)
+def test_every_preset_loads_and_reports_its_version(path: Path) -> None:
+    """Each shipped and fixture preset loads with the version written in its JSON."""
+    text = path.read_text(encoding="utf-8")
+    assert from_json(text).version == json.loads(text)["version"]
+
+
+@pytest.mark.parametrize("name", ["dither_v3.json", "glyph_v3.json"])
+def test_v3_round_trip_has_equal_presets(name: str) -> None:
+    """Two v3 presets survive to_json/from_json with dataclass equality."""
+    original = from_json(_fixture(name))
+    assert from_json(to_json(original)) == original
+
+
+def test_v3_round_trip_preserves_every_section_of_contract_six() -> None:
+    """All eleven v3 sections, stages, masks and fonts survive a load/save unchanged."""
+    saved = json.loads(to_json(from_json(_fixture("glyph_v3.json"))))
+    for key in ("version", "app", "meta", "renderer", "palette", "pipeline", "effects",
+                "masks", "fonts", "output", "seed"):
+        assert key in saved
+    assert [entry["stage"] for entry in saved["effects"]] == ["pre", "post"]
+    assert saved["masks"]["glow_mask"] == {"kind": "v_flip"}
+    assert saved["fonts"]["ramp"]["fallback"] == ["mono"]
+    assert saved["output"] == {"scale": 2, "width": None, "dpi": 300}
+    assert saved["seed"] == 7
+
+
+def test_unknown_top_level_and_style_keys_survive_a_load_save() -> None:
+    """A future top-level key and a future style option survive load/save unchanged."""
+    original = from_json(_fixture("future_keys_v3.json"))
+    saved = json.loads(to_json(original))
+    assert saved["future"] == {"x": 1}
+    assert saved["renderer"]["style"]["a_future_style_option"] == {"keep": True}
+    assert from_json(to_json(original)) == original
+
+
+def test_version_four_raises_value_error_naming_it() -> None:
+    """An unsupported version is rejected with the offending number in the message."""
+    with pytest.raises(ValueError, match=r"\b4\b"):
+        from_json('{"version": 4}')
+
+
+@pytest.mark.parametrize("value", [True, False, 3.7, "3", None])
+def test_non_integer_version_is_rejected(value: object) -> None:
+    """Bools, floats and strings never coerce into a supported version."""
+    with pytest.raises(ValueError, match="version"):
+        from_json(json.dumps({"version": value}))
+
+
+@pytest.mark.parametrize("value", [True, 2.5, "7", None])
+def test_non_integer_seed_is_rejected(value: object) -> None:
+    """Bools, floats and strings are rejected for the seed key by name."""
+    with pytest.raises(ValueError, match="seed"):
+        from_json(json.dumps({"version": 3, "seed": value}))
+
+
+@pytest.mark.parametrize(
+    "section", ["meta", "renderer", "palette", "pipeline", "output", "masks", "fonts"],
+)
+def test_non_object_section_error_names_the_section(section: str) -> None:
+    """A malformed section raises ValueError naming that section."""
+    with pytest.raises(ValueError, match=section):
+        from_json(json.dumps({"version": 3, section: []}))
+
+
+def test_non_object_effect_entry_raises_value_error_naming_it() -> None:
+    """A non-dict effect entry is a ValueError that names its index."""
+    with pytest.raises(ValueError, match=r"effects\[0\]"):
+        from_json(json.dumps({"version": 3, "effects": [1]}))
+
+
+def test_glyph_preset_in_dither_context_warns_and_falls_back() -> None:
+    """A glyph preset loads in dither context with a warning and the pixel renderer."""
+    text = _fixture("glyph_v3.json")
+    loaded = from_json(text, app="dither")
+    assert loaded.app == "glyph"
+    assert loaded.renderer["name"] == "pixel"
+    assert len(loaded.warnings) == 1
+    assert "glyph_ramp" in loaded.warnings[0]
+    assert "dither" in loaded.warnings[0]
+    assert from_json(text).renderer["name"] == "glyph_ramp"
+
+
+def test_available_context_can_keep_a_renderer_outside_the_app_table() -> None:
+    """A host-provided availability set decides fallback instead of the built-in table."""
+    loaded = from_json(_fixture("glyph_v3.json"), app="dither", available={"glyph_ramp"})
+    assert loaded.renderer["name"] == "glyph_ramp"
+    assert loaded.warnings == []
+
+
+@pytest.mark.parametrize(
+    ("text", "expected", "app"),
+    [
+        ('{"version": 3, "app": "glyph"}', "glyph_ramp", None),
+        ('{"version": 3, "app": "dither"}', "pixel", None),
+        ('{"version": 3, "app": "widget"}', "pixel", None),
+        ('{"version": 3}', "pixel", None),
+        ('{"version": 3, "app": "glyph"}', "pixel", "dither"),
+        ('{"version": 3, "renderer": {"style": {}}}', "pixel", "dither"),
+    ],
+)
+def test_absent_renderer_uses_app_default_with_warning(
+    text: str, expected: str, app: str | None,
+) -> None:
+    """A missing renderer name becomes the context app default and records one warning."""
+    loaded = from_json(text, app=app)
+    assert loaded.renderer["name"] == expected
+    assert len(loaded.warnings) == 1
+    assert "absent" in loaded.warnings[0]
+
+
+def test_legacy_preset_without_renderer_gets_default_and_warning() -> None:
+    """A v1 preset with no renderer key falls back to the dither default with a warning."""
+    loaded = from_json(_fixture("legacy_v1.json"))
+    assert loaded.renderer["name"] == "pixel"
+    assert len(loaded.warnings) == 1
+
+
+def test_available_renderer_in_context_has_no_warning() -> None:
+    """A preset naming a renderer the context supports loads without fallback."""
+    loaded = from_json(_fixture("dither_v3.json"), app="dither")
+    assert loaded.renderer["name"] == "pixel"
+    assert loaded.warnings == []
+
+
+def test_to_json_is_byte_stable_sorted_and_indented() -> None:
+    """Two serialisations are identical, with sorted keys, two-space indent and one LF."""
+    text = to_json(from_json(_fixture("dither_v3.json")))
+    assert text == to_json(from_json(_fixture("dither_v3.json")))
+    data = json.loads(text)
+    assert list(data) == sorted(data)
+    assert text == json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
+    assert text.endswith("\n") and not text.endswith("\n\n")
+
+
+def test_v1_preset_maps_to_dither_and_pixel() -> None:
+    """A v1 preset reports version 1 and takes the dither app and pixel renderer."""
+    loaded = from_json(_fixture("legacy_v1.json"))
+    assert (loaded.version, loaded.app, loaded.renderer["name"]) == (1, "dither", "pixel")
+    assert loaded.pipeline["algorithm"] == "floyd_steinberg"
+    assert loaded.palette["source"] == "integrated"
+    assert loaded.effects == []
+
+
+def test_v2_preset_keeps_stages_extraction_and_renderer_style() -> None:
+    """A v2 preset maps both effect stages, extraction settings and L2b renderer fields."""
+    loaded = from_json(_fixture("legacy_v2.json"))
+    assert (loaded.version, loaded.app) == (2, "dither")
+    assert loaded.renderer == {"name": "pixel", "style": {"scale": 2}}
+    assert [entry["stage"] for entry in loaded.effects] == ["pre", "post"]
+    assert loaded.palette["extract"]["n_colors"] == 6
+    assert loaded.palette["locked_colours"] == ["#ffffff"]
+    assert loaded.meta["tags"] == ["old"]
+
+
+def test_legacy_preset_serialises_as_current_v3() -> None:
+    """Saving a loaded legacy preset writes the one v3 format used across the suite."""
+    saved = json.loads(to_json(from_json(_fixture("legacy_v2.json"))))
+    assert saved["version"] == 3
+    assert saved["app"] == "dither"
+    assert saved["pipeline"]["color_metric"] == "oklab"
+    assert [entry["stage"] for entry in saved["effects"]] == ["pre", "post"]
+
+
+def test_legacy_extra_cannot_overwrite_a_v3_section() -> None:
+    """A legacy file carrying v3 keys must not corrupt the converted section on save."""
+    text = json.dumps({
+        "version": 1,
+        "algorithm_id": "atkinson",
+        "pipeline": {"algorithm": "evil"},
+        "app": "glyph",
+        "effects": ["evil"],
+    })
+    saved = json.loads(to_json(from_json(text)))
+    assert saved["pipeline"]["algorithm"] == "atkinson"
+    assert saved["app"] == "dither"
+    assert saved["effects"] == []
+
+
+def test_hand_built_extra_cannot_overwrite_a_typed_section() -> None:
+    """An extra key colliding with a typed section never wins on serialisation."""
+    saved = json.loads(to_json(Preset(extra={"version": 99, "seed": 12, "future": {"x": 1}})))
+    assert saved["version"] == 3
+    assert saved["seed"] == 0
+    assert saved["future"] == {"x": 1}
+
+
+def test_pipeline_spec_round_trip_carries_renderer_and_style() -> None:
+    """PipelineSpec renderer and renderer_style survive the v3 bridge in both directions."""
+    spec = PipelineSpec(
+        algorithm_id="floyd_steinberg", renderer="glyph_ramp",
+        renderer_style={"ramp": "@ .", "future": 1},
+    )
+    converted = from_pipeline_spec(spec)
+    assert converted.renderer == {"name": "glyph_ramp", "style": {"ramp": "@ .", "future": 1}}
+    rebuilt = to_pipeline_spec(converted)
+    assert rebuilt.renderer == spec.renderer
+    assert rebuilt.renderer_style == spec.renderer_style
+    assert rebuilt.algorithm_id == spec.algorithm_id
+
+
+def test_to_pipeline_spec_maps_effects_and_palette() -> None:
+    """The v3 bridge maps effects to their stages and the palette to a PaletteSpec."""
+    spec = to_pipeline_spec(from_json(_fixture("glyph_v3.json")))
+    assert [effect.effect_id for effect in spec.pre_effects] == ["scanlines"]
+    assert [effect.effect_id for effect in spec.post_effects] == ["glow"]
+    assert spec.palette is not None and spec.palette.source == "builtin"
+    assert spec.pixel_size == 2 and spec.seed == 7
+
+
+def test_missing_sections_take_defaults() -> None:
+    """A minimal v3 preset takes the documented defaults and keeps unknown keys."""
+    loaded = from_json('{"version": 3, "future": 1}')
+    assert loaded.renderer == {"name": "pixel", "style": {}}
+    assert loaded.pipeline["algorithm"] == "floyd_steinberg"
+    assert loaded.output == {"scale": 1, "width": None, "dpi": None}
+    assert loaded.extra == {"future": 1}
+
+
+def test_save_and_load_preset_helpers(tmp_path: Path) -> None:
+    """save_preset creates parents and load_preset reads back the same bytes."""
+    original = from_json(_fixture("glyph_v3.json"))
+    path = tmp_path / "nested" / "preset.json"
+    save_preset(path, original)
+    assert path.read_text(encoding="utf-8") == to_json(original)
+    assert load_preset(path) == original
+
+
+@pytest.mark.parametrize("text", ["{", "[]", "null"])
+def test_malformed_preset_json_raises_value_error(text: str) -> None:
+    """Malformed or non-object JSON is rejected with ValueError."""
+    with pytest.raises(ValueError):
+        from_json(text)
+
+
+def test_default_preset_is_a_v3_preset() -> None:
+    """A freshly built Preset is a complete v3 preset with no warnings."""
+    made = Preset()
+    assert made.version == 3 and made.app == "dither"
+    assert made.warnings == [] and made.extra == {}
+    assert from_json(to_json(made)) == made
+
+
+def test_core_preset_module_does_not_import_applications() -> None:
+    """The core preset module never references an application package (rule 4)."""
+    source = Path(preset.__file__).read_text(encoding="utf-8")
+    for name in ("lattice_dither", "lattice_glyph", "lattice_glitch"):
+        assert name not in source

CODER NOTES AND DEVIATIONS (L4, attempt 2, hy4-flash-free)
- `Preset(app="glyph")` construit directement `glyph_ramp` sans warning (le warning est un
  artefact de chargement, pas de construction) ; effet de bord noté : un renderer explicite
  pixel + app=glyph est aussi promu (non distinguable du défaut).
- `from_pipeline_spec` passe `available={spec.renderer}` pour préserver le pont L2b sans
  fallback inattendu. `APP_RENDERERS`/defaults = choix E1 à valider au point de contrôle humain.
- Aucun E8/E9, aucune écriture hors owns.
