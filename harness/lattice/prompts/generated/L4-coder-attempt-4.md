# Coder prompt — L4 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

## §7 Bridge

One client, one adapter per host. The bridge is never fatal: every application works standalone.

```python
class ArtCraftClient:
    @staticmethod
    def discover(host: Literal["photocraft", "designcraft"], port: int | None = None) -> ArtCraftClient | None
    def ping(self) -> bool
    def render_document(self) -> Image.Image
    def place_as_layer(self, img: Image.Image, name: str) -> int
```

- **PhotoCraft** (port 47600, token file): `document.inspect`, `app.save`, `app.open`,
  `layer.copyToDocument`, `file.close`. This is the existing Lattice Dither implementation, moved.
- **DesignCraft**: `file.place` with `{path, frame?}` when a frame is selected, otherwise
  `{path, x, y, width}` to create one. `place_as_layer` returns the placed object id.
- Discovery reads the token file, opens one authenticated connection, and calls `engine.commands`
  as the liveness probe. A missing token, a refused connection or a failed probe returns `None`.
- Every call is bounded by a timeout. A bridge failure surfaces as a typed error, never a crash.
- The exchange directory is per-application, under the platform app-data directory
  (QStandardPaths: `%LOCALAPPDATA%/<App>` on Windows, `~/.local/share/<App>` on Linux), and files
  older than one hour are discarded on each call.

## §8 CLI

Every application exposes the same four verbs:

```
<app> render  --preset P --in IMG --out IMG
<app> batch   --preset P --in DIR --out DIR [--recursive]
<app> presets list|show|validate
<app> bridge  status|pull|push
```

- `render` and the GUI must produce **byte-identical** output for the same preset and image (G9).
- Exit codes: 0 success, 1 usage error, 2 render error, 3 bridge error.
- `--json` on any verb prints a machine-readable result on stdout and nothing else.
- No verb may require a display. `import lattice_core.ui` must not happen on the CLI path.

## §9 Glyph renderers

Four renderers, one per mechanism.

**`glyph_ramp`** — one monospace character per cell. `luma` (S2, decided 2026-11-16) indexes an
ordered ramp, darkest first, independently of the palette: a black/white palette still uses the
full ramp. Options: `ramp` (string), `font` (path), `fg`/`bg` (colour or `transparent`),
`mode` (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset` (float, shifts the
luma-to-glyph mapping), `invert` (bool). There is no `size` option (H11, decided 2026-11-16):
the glyph font size is derived from `cell_h` (§5 step 6), so each glyph covers its cell exactly.

- The ramp contract is explicit: **darkest character first, lightest last**. A ramp that violates
  it is not detected, it is documented.
- `offset` is animatable and is the cheapest way to make a still image shimmer.
- Aspect correction uses `cell_aspect()`; the default font ratio is 1/2 (width/height).

**`glyph_shape`** — one monospace character per cell, chosen by shape rather than by density.

- For each glyph, place `k = 6` sampling circles inside the cell (top/middle/bottom × left/right).
  For each circle, sample many points and compute the fraction inside the glyph's ink. That is the
  glyph's shape vector.
- **Normalise each component by the maximum across the alphabet.** Without this every vector
  clusters in the bottom-left and every cell maps to the same few characters.
- Per cell, compute the same vector from `samples` and take the nearest neighbour.
- Shape vectors are precomputed per (font, size) and cached at module level.
- Budget: 1024×1024, 64 glyphs, under 200 ms after warm-up. If missed, a precomputed lookup table
  over quantised vectors is allowed.

**`bitmask`** — sub-cell dots. One code path, four geometries:

| Geometry | Sub-grid | Codepoints |
|---|---|---|
| `braille` | 2×4 | U+2800 + bitmask |
| `sextant` | 2×3 | U+1FB00..U+1FB3B |
| `quadrant` | 2×2 | U+2596..U+259F |
| `half_block` | 1×2 | U+2580, U+2584, U+2588 |

Threshold `samples` into on/off sub-dots. Options: `threshold` (0..1), `fg`/`bg`. The sub-dot
decision belongs to the algorithm, run at subgrid resolution (S3): there is no `dither` option
(removed; H11 coherence pass).

**`pixel`** — one solid square per cell. This is Lattice Dither's current behaviour, expressed through
the abstraction. It must reproduce the 1.0 output byte for byte.

## §10 Text-halftone

`text` renderer. A flowing paragraph in a real font, not a character grid.

- Lay out the paragraph with real font metrics: kerning, line distance, word wrapping.
- Modulate per-glyph **weight, size and opacity** by the underlying `luma` (S2, decided
  2026-11-16): ink density must not collapse on a neutral palette.
- Cells may vary in size. `cell_aspect()` returns the nominal aspect; the renderer may vary a cell
  by ±50% and must still fill the output rectangle exactly.
- Options: `text` (string), `font`, `size`, `line_distance`, `kerning`, `size_mode`
  (`fixed` | `variable`), `weight_mode` (`fixed` | `variable`), `fg`/`bg`.
- `size_mode: fixed` keeps every glyph the same size and modulates only opacity. `variable` is the
  mode that makes the output look like art rather than ASCII.

## §11 Vector export

Every renderer can emit SVG.

- `pixel` → one `<rect>` per cell, merged into runs where adjacent cells share a colour.
- `glyph_ramp`, `glyph_shape`, `bitmask`, `text` → export driven by the renderer's `layout()`
  when it is available (H11): one `<text>` element per glyph, with `font-family`,
  `font-size` and `fill` set. The output is **editable typography**, not traced paths.
- Budget: 2048×2048 source, 16 colours, output under 8 MB. Beyond that, merge cells into rectangles
  and record a warning.
- SVG output must open in Inkscape, Illustrator and a browser without repair.

**Text export (P3, decided 2026-11-16).** `glyph_ramp`, `glyph_shape` and `bitmask` also emit
text — from `layout()` when available (H11): `.txt` (UTF-8, space-separated cells, `\n` line
breaks), `.ansi` (24-bit colour, SGR escapes; terminal-safe ordering), `.html` (a coloured `<pre>`
block in a standalone page). Shared CLI verb: `render --format png|svg|txt|ansi|html`. The ANSI
exporter must not leak escape codes into the text path; HTML output escapes text content.

## §12 Feedback buffer

The mechanism that makes a glitch tool an instrument rather than a filter.

```
f(n) = decay * T(f(n-1)) + input
```

- `decay` in `[0, 0.99]`. Values at or above 1 are rejected at validation.
- `T` is one of: `translate`, `rotate`, `scale`, `displace`, `identity`. Composable.
- The buffer is normalised per frame so it cannot diverge.
- Stability test: 200 iterations on a fixed input, no NaN, no value outside `[0, 1]`, and the mean
  converges.
- Options: `decay`, `transform`, `amount`, `iterations` (1..8), `blend` (`add` | `max` | `screen`).

## §13 Displacement

- Map source: a still image, an image sequence, a noise field, or the feedback buffer.
- Map modes: `luma`, `r`, `g`, `b`, `hue`.
- `dst(x, y) = src(x + k * (mapR - 0.5), y + k * (mapG - 0.5))`, with `k` in pixels.
- `iterations` repeats the displacement with decay, producing a smear without a feedback loop.
- `mask` restricts the effect spatially (§18).
- Sampling is bilinear; edges clamp.

## §14 Pixel sort

- Three thresholds: `black`, `brightness`, `white`. A run starts when a pixel passes `brightness`
  and continues while it stays inside the `black`..`white` band.
- Direction: `rows`, `columns`, `diagonal`.
- Sort key: `luma`, `hue`, `saturation`, `r`, `g`, `b`.
- `mask` acts as an interval map: white pixels are sorted, black pixels are not.
- Runs are sorted with a stable sort so the result is deterministic.

## §15 Channel shift

- Per-channel translate, scale and radial offset. R and B are pushed in opposite directions by
  default, which is what reads as chromatic aberration.
- **Per-channel effect assignment**: any effect may be applied to a subset of channels. This is a
  one-line change in the compositor and produces looks nothing else ships.
- Options: `amount`, `mode` (`translate` | `scale` | `radial`), `channels` (bitmask).

## §16 NTSC / VHS

Signal emulation, not overlay. Artefacts must emerge from the chain.

- Chain: RGB → YIQ → chroma low-pass → chroma subsample → noise injection → demodulate → RGB.
- Parameters: `chroma_lowpass`, `chroma_phase_noise`, `luma_smear`, `luma_noise`, `composite_noise`,
  `bandwidth`, `ringing` (`butterworth` | `constant_k`).
- VHS additions: `head_switching` (displaces the bottom edge), `tracking_noise`, `snow`,
  `sharpening`, `tape_speed` (`sp` | `lp` | `ep`).
- **Usability constraint**: six named presets plus a simple mode with four sliders. The full
  parameter set is behind an advanced toggle. A tool with 14 sliders and no presets is a tool
  nobody opens twice.

## §17 CRT / scanlines

The finishing layer. Static by nature, and that is fine.

- Scanline beam profile, phosphor mask (`slot` | `aperture_grille` | `shadow_mask`), bloom,
  curvature, vignette.
- **The mask scales in device pixels, not image pixels.** A CRT effect that does not know its
  output resolution is a lie.
- Options: `scanline_intensity`, `mask`, `mask_scale`, `bloom`, `curvature`, `vignette`.

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

## §19 Gates

G1 to G4 are inherited from the DitherCraft harness: ruff clean, pytest green, `check_contract`
passes, a task writes only the files it owns.

The dithering application already owns **G5 (v1 preset compatibility)** and **G6 (CLI/GUI parity)**
from the 1.1 harness — those two numbers mean something different there. To keep every gate number
unique across the project's history, this harness numbers its own gates from **G7** (gate registry
in `harness/README.md`; the next new gate is G10):

- **G7 core regression.** After L1, Lattice Dither renders its three witness presets byte-identically
  to the baselines committed at HEAD (`tests/data/baseline/`).
- **G8 renderer contract.** Every registered `CellRenderer` satisfies §3, verified by iterating
  `list_renderers()` so any future renderer is covered automatically.
- **G9 CLI/GUI parity.** For the same preset and image, the CLI and the GUI produce identical
  bytes, in every application (generalises the 1.1 G6).

## §20 Non-goals

Explicitly out of scope for this contract. Adding any of these requires a new contract version.

- Full video and timeline editing. A shared **N-image loop** (GIF/APNG, card L-LOOP) is in
  scope: variation of seed, offset or feedback iterations across N frames; no timeline, no video.
- Physical-media output (LEGO, beads, cross-stitch, embroidery).
- Print separations (CMYK plates, riso, spot inks, trapping, dot gain). **Assumed bet,
  documented, no promise** (P2, decided 2026-11-16): separations and full animation are
  explicitly out and not foreshadowed in any contract version yet.
- Network access in the core. Palette import is file-based or pasted hex.
- Any dependency beyond numpy, numba, Pillow, and PySide6 under the `[ui]` extra.

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
--- lattice_core/presets.py ---
def shipped_preset_dir  # Return the read-only shipped preset directory that sits next to the package.
def user_preset_dir  # Return the user preset directory under %APPDATA%, without creating it.
def preset_search_dirs  # Return the preset search order: the shipped directory first, then the user one.
def list_presetsdirectories: Sequence[Path] | None=None  # List the presets of the search directories, shipped first, a user file winning a tie.
def resolve_presetname: str, directories: Sequence[Path] | None=None  # Return the file a preset name resolves to, the user tier winning over the shipped one.
def is_withinpath: str | Path, directory: str | Path  # Return True when path is directory itself or lies inside it.
def to_jsonspec: PipelineSpec  # Serialise spec to indented JSON at the current preset version, keys in field order.
def from_jsontext: str  # Parse JSON into a PipelineSpec, validating the version, ids and metric.
def save_presetpath: str | Path, spec: PipelineSpec  # Write spec as UTF-8 JSON to path, creating parent directories.
def load_presetpath: str | Path  # Read a UTF-8 JSON preset file and parse it into a PipelineSpec.
--- lattice_core/pipeline.py ---
class PresetMeta:
class EffectInstance:
class PaletteSpec:
class PipelineSpec:
def resolve_palettespec: PaletteSpec, img: Image  # Return the float32 palette described by spec, extracting from img when needed.
def rendersrc: Image, spec: PipelineSpec, *, max_side: int | None=None, renderer: str | None=None, style: RenderStyle | None=None  # Render src through the twelve normative pipeline steps and return uint8 RGB.
def prepare_imagesrc: Image, spec: PipelineSpec, *, max_side: int | None=None, renderer: str | None=None  # Return src after steps 1 to 5, the image palette resolution reads.
def render_with_palettesrc: Image, spec: PipelineSpec, palette: Palette, *, max_side: int | None=None, renderer: str | None=None, style: RenderStyle | None=None  # Render src with an already resolved palette through the twelve pipeline steps.
--- lattice_core/types.py ---
class ParamSpec:

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

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/preset.py` n'existe PAS (à créer). `lattice_core/presets.py` existe (io v2 :
to_json/from_json, PRESET_VERSION=2, resolve_preset, shipped/user dirs — lisez-le ; il reste
possédé par L1 et ne doit PAS être déplacé : le format v3 vit dans le nouveau preset.py).
`tests/test_preset.py` et `tests/data/presets/` n'existent pas (à créer). `PipelineSpec`
(L2b) porte désormais `renderer`/`renderer_style` — la carte se coordonne avec eux (H11/AMD-008).--- RETRY attempt 2 ---

Les fichiers owns existent (état attempt 1, hy4-flash-free : 1372 tests verts) — lisez-les avant de modifier. Fix exactly what is reported below, change nothing else, keep passing tests passing.

VERDICT DE LA REVUE (relecture strict, pass 1, Sonnet thinking high) : FIX

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_core/preset.py",
      "line": 283,
      "what": "The card says a missing renderer falls back to the app default and records a warning. This is not implemented. When the `renderer` key is absent, `_section(..., _default_renderer())` fills in `pixel` with no warning, whatever the app is. `_resolve_renderer` only acts on a renderer that is named but not in `APP_RENDERERS[app]`.",
      "why": "`{\"version\":3,\"app\":\"glyph\"}` loads with renderer `pixel` and no warning, and `from_json(..., app=\"glyph\")` does the same because `pixel` is in the glyph table. It should become `glyph_ramp` with a warning. `Preset(app=\"glyph\")` also defaults to `pixel`. This accept item is neither implemented nor tested. All 36 tests pass anyway.",
      "fix": "Detect that `renderer` or `renderer.name` is absent in `_from_v3` and `_from_legacy`. In that case set `APP_DEFAULT_RENDERER[app]`, where app is `preset.app` or the `app=` context, and append a warning. Add tests for a v3 preset with no `renderer`, in the glyph, dither and unknown-app cases."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 14,
      "what": "`APP_RENDERERS` is a hardcoded table of renderer names per app. It duplicates the renderer registry (`lattice_core.renderers.list_renderers()`) and is invented, since the contract excerpt is silent on it (the coder's E1).",
      "why": "The table can drift from the registry. Renderer availability in a context should come from the registry, or from a context argument the host passes in, not from a copy kept in core.",
      "fix": "Derive availability from `list_renderers()` intersected with a per-app allow-list, or let the caller pass `available=`. Confirm the table against §6 at the human checkpoint."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 262,
      "what": "Legacy `extra` only excludes `_LEGACY_TOP`. `_preset_dict` then runs `data.update(preset.extra)` after the v3 keys. A v1/v2 file containing `pipeline`, `app`, `effects` and so on would overwrite the converted section on save. A hand-built `Preset.extra` containing `version` would do the same.",
      "why": "Silent corruption of the saved preset in a rare edge case.",
      "fix": "Exclude `_V3_TOP` from `extra` in `_from_legacy`, or write `extra` first and the typed sections after it."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 191,
      "what": "Validation is loose. `_version` and `_as_int` accept `True`, `3.7` and `\"3\"` through `int()`. A non-dict entry in `effects` raises `TypeError` from `dict(entry)`, not `ValueError`. The section error message does not name the section.",
      "why": "A malformed preset gives an inconsistent error type and a vague message.",
      "fix": "Reject bool and float explicitly. Validate each effect entry with `_as_dict`. Name the section in the error."
    },
    {
      "severity": "minor",
      "file": "tests/test_preset.py",
      "line": 38,
      "what": "`test_every_preset_loads...` globs `ROOT/presets`. If that directory were empty or missing, the parametrisation would shrink and still pass. The `version 4` test uses `match=\"4\"`, which is weak.",
      "why": "The shipped-preset accept item could be passed vacuously. A message such as `\"... 14\"` would also match.",
      "fix": "Assert that at least one shipped preset is collected. Use `match=r\"\\b4\\b\"`."
    }
  ],
  "regression": "none (new module; no existing file changed apart from the orchestrator's DEV-209 packaging test)",
  "renderer_invariants": "all six hold (no renderer touched)",
  "tests_that_cannot_fail": [
    "test_core_preset_module_does_not_import_applications (a substring check; it only fails on a literal package name)",
    "test_every_preset_loads_and_reports_its_version (can pass vacuously if the presets/ glob is empty)"
  ],
  "notes": "Not checked against §6, which was not in the excerpts. Main gap: the 'missing renderer → app default + warning' accept item. E8 and E9 are clean. The `PipelineSpec` bridge matches the L2b fields (renderer, renderer_style); `max_side` is a render argument, not a spec field, so dropping it from the bridge is correct. The E1 choices (to_json always writes v3, `locked_colours`, the source mapping) are reasonable and should be validated at H11."
}
```

NOTE DE L'ORCHESTRATEUR : la relecture n'avait pas reçu §6 (erreur d'assemblage du prompt) et
l'a signalé — le contrat §6 est dans ce prompt (CONTRACT EXCERPTS ci-dessus) : vérifiez chaque
accept contre §6, pas seulement contre les findings.
--- RETRY attempt 3 (cycle borné, DEV-210 : budget de revue 2/2 épuisé) ---

Les fichiers owns existent (état attempt 2 : owned 65 tests verts, base 1372 verte isolée).
Fix exactly what is reported below, change nothing else, keep passing tests passing.

EXCERPT SUPPLEMENTAIRE — §5 Pipeline (le contexte de la carte était §6 seul ; le mode continu
y vit, S1) :

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
VERDICTS DES PASS 1 ET 2 DE LA REVUE (verbatim, blocs ci-dessous) — le pass 2 dit
expressément : « The coder should also drop the APP_RENDERERS table » ; votre prompt
contient maintenant §5 ET §6 : vérifiez chaque accept contre les deux, y compris les nulls
du mode continu (§5 S1) et la disponibilité des renderers via le REGISTRE (list_renderers),
pas une table dupliquée.
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_core/preset.py",
      "line": 330,
      "what": "The fallback test uses the hard-coded APP_RENDERERS table instead of the renderer registry. The table omits renderers that the contract names (braille, sextant, quadrant). For an unknown app it is empty, so even `pixel` gets a spurious 'unavailable' warning.",
      "why": "§6 says the fallback applies 'if the named renderer is absent'. Absent means not registered. A glyph v3 preset naming `braille` is silently downgraded to `glyph_ramp` and the real name is lost on re-save. `{app:'widget', renderer:{name:'pixel'}}` warns for no reason. The core also hard-codes the names of the three apps, which is an E8-style leak.",
      "fix": "Default `available` to the set returned by `list_renderers()`, resolved lazily at call time. Keep per-app default names only as a minimal map, with `pixel` as the universal fallback. Drop the per-app availability table. Add tests for an unknown app with `pixel`, and for a registered non-table renderer."
    },
    {
      "severity": "major",
      "file": "lattice_core/preset.py",
      "line": 268,
      "what": "In `_from_legacy`, a v1/v2 preset with no `renderer` key gets the context app's default renderer plus a warning. With `app='glyph'` it becomes `glyph_ramp`. Every legacy file that lacks a renderer also loads with a spurious warning.",
      "why": "§6 says versions 1 and 2 map to `app: 'dither'`, `renderer: 'pixel'`, deterministically. Absence of the key is the normal state for v1, not a fallback case. The test `test_legacy_preset_without_renderer_gets_default_and_warning` enshrines the wrong behaviour.",
      "fix": "For legacy presets, set the renderer to `pixel` with no warning when the key is absent. Apply the availability fallback only when a name is present but unavailable. Fix the test."
    },
    {
      "severity": "major",
      "file": "lattice_core/preset.py",
      "line": 232,
      "what": "Continuous mode (§5 S1, `algorithm: null` and `palette: null`) is lost on load. `_section(None, defaults)` turns a null palette into the default palette. `_legacy_pipeline` ignores a None `algorithm_id` and keeps `floyd_steinberg`, so `from_pipeline_spec` of an algorithm-less spec silently re-enables quantisation. In v3, `pipeline.algorithm: null` survives only because the merge overwrites the default.",
      "why": "The contract makes null algorithm and null palette legal, and Glitch depends on them. The bridge changes the pipeline's meaning and breaks round-trip fidelity.",
      "fix": "Keep an explicit `palette: null` and `algorithm: null` through `_from_v3`, `_legacy_pipeline`, `_spec_palette` and `to_pipeline_spec`. Test the PipelineSpec → Preset → PipelineSpec round trip with algorithm_id=None and palette=None."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 29,
      "what": "`_PIPELINE_KEYS` omits `max_side`. The v3 `max_side` is never copied to the spec. Effect `mask`, `masks`, `fonts` and `output` are not bridged either.",
      "why": "§5 step 1 uses `max_side`, so setting it in a preset has no effect through `to_pipeline_spec`. This is possible silent data loss if PipelineSpec has the field.",
      "fix": "Map `max_side` if PipelineSpec carries it. Otherwise document that the bridge is partial."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 244,
      "what": "`_legacy_palette` stores the v2 `locked` list under a non-contract key `locked_colours`. Unknown legacy palette sub-keys are dropped.",
      "why": "v3 `palette.locked` is a bool, so the mapping is ad hoc. A newer-app palette sub-key does not survive a legacy load/save.",
      "fix": "Document the mapping, or set `locked` to bool(list) and keep the list under a documented key."
    },
    {
      "severity": "minor",
      "file": "tests/test_preset.py",
      "line": 280,
      "what": "`test_core_preset_module_does_not_import_applications` is a string-grep test that the implementation can never fail. It misses the real leak, which is the hard-coded app and renderer tables.",
      "why": "It gives false assurance on rule 4 (E8).",
      "fix": "Remove it, or replace it with a check on imports."
    }
  ],
  "regression": "none (new module; no frozen behaviour touched)",
  "renderer_invariants": "all six hold (no renderer code in this card)",
  "tests_that_cannot_fail": [
    "test_core_preset_module_does_not_import_applications",
    "test_shipped_presets_are_discovered (it only checks that a glob is non-empty)"
  ],
  "notes": "The six accept items pass as written. The defects are in fallback semantics (registry vs table, legacy defaults) and in continuous-mode nulls. The coder should also drop the APP_RENDERERS table. The hy4-flash-free output is solid on the base format: validation, extra preservation and byte stability are good."
}
--- RETRY attempt 4 (CYCLE TEST-ONLY, autorisé par l'humain — arbitrage du 17/11) ---

Le code de l'attempt 3 a été jugé correct par la relecture (aucun défaut de code : « the fix is
test-only »). Ne modifiez le comportement QUE si un test l'exige. Ce qui reste :

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "tests/test_preset.py",
      "line": 126,
      "what": "The accept item \"loading a glyph preset in a dither context returns a warning and a pixel renderer\" is not tested. The only glyph-in-dither test asserts the opposite: glyph_ramp is kept and warnings == [].",
      "why": "An explicit acceptance criterion has no test. The one test that touches it exercises a different semantic: availability = whole registry, so any app keeps any registered renderer. Nothing proves the implemented fallback path matches the card.",
      "fix": "Add a test that loads glyph_v3.json with app='dither' and available={'pixel'} (the dither host's own renderer set). Assert renderer.name == 'pixel' and exactly one warning that names 'glyph_ramp'. Keep the registry-default test, but state in its docstring that the app host must pass `available` to get the card's behaviour."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 124,
      "what": "In from_json, `preset = ...; return preset` is a needless temporary. The nested conditional for `context` is hard to read.",
      "why": "Hygiene only.",
      "fix": "Return directly from each branch and compute `context` with an if/else."
    },
    {
      "severity": "minor",
      "file": "lattice_core/preset.py",
      "line": 270,
      "what": "In _from_legacy, legacy files that carry v3 section keys (pipeline, effects, app, masks and so on) are silently dropped. They are excluded from `extra` via `_V3_TOP`.",
      "why": "This contradicts the contract's preservation of unknown keys. The data loss is silent, although the test deliberately protects the typed sections from overwrite.",
      "fix": "Either document the drop in the docstring or stash the colliding keys under a namespaced `extra` key."
    }
  ],
  "regression": "none (new module; PipelineSpec bridge is additive; no frozen behaviour touched)",
  "renderer_invariants": "all six hold (this card adds no renderer; the preset only reads the registry through list_renderers)",
  "tests_that_cannot_fail": [
    "test_shipped_presets_are_discovered: the second assert (`_all_files()`) is implied by the first"
  ],
  "notes": "The dither-context accept item conflicts with the pass-2 decision to remove the per-app renderer table. The `available` parameter can satisfy both, but only if a test pins it, so the fix is test-only. If the human wants the default call from_json(glyph, app='dither') to warn with no `available`, an app-to-renderer table is needed again. That is a contract/card clarification, so escalate. No E8/E9 issue: the AST import test is real and no host access is present. Maths: none, since this card has no renderer or effect maths."
}
```

INSTRUCTIONS DE L'ORCHESTRATEUR :
1. Ajoutez le test d'accept manquant : « loading a glyph preset in a dither context returns a
   warning and a pixel renderer » — via le paramètre `available=` (la sémantique du registre
   décidée au pass 2 reste en vigueur ; un renderer nommé mais non disponible → fallback pixel
   + warning). Figez le comportement dans test_preset.py.
2. Corrigez les 2 minors cosmétiques (temporaire inutile dans from_json ; _from_legacy qui
   ignore silencieusement des clés v3 → avertissement ou documenté).
3. Rien d'autre. Full suite base (isolation) verte.
