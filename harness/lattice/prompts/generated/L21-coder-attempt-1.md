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

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
{{SIGNATURES}}

TASK CARD
{{TASK_CARD}}

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)
{{OWNED_FILES}}

{{RETRY_BLOCK}}
<!-- RETRY_BLOCK, only on retries:
RETRY attempt {{N}}. Fix exactly what is reported below, change nothing else, keep passing tests passing.
{{GATE_LOG_OR_REVIEW_FINDINGS}}
-->



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


NOTE DU RÉGIEUR (wave 2, épreuve A/B — ce prompt part sur qwen4:free) :
le jeu de démarrage (≥ 12 presets v3) se crée SOUS presets/ (ou un sous-dossier neuf de presets/) —
NE TOUCHE PAS à lattice_glyph/presets (6 presets livrés, carte faite) ni lattice_glitch/presets (8, faits).
Les presets existants de presets/ (v1 dither) restent intacts ; lis-les comme référence, n'écris que du
nouveau. La galerie consomme les registres (import lattice_core... explicite dans le test).

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
# --- lattice_core/registry ---
  class AlgorithmInfo:
      """Registration record of one dithering algorithm."""
  class EffectInfo:
      """Registration record of one image effect."""
  def register_algorithm(
      def decorator(fn: AlgorithmFn) -> AlgorithmFn:
  def register_effect(
      def decorator(fn: EffectFn) -> EffectFn:
  def get_algorithm(id: str) -> AlgorithmInfo:
      """Return the algorithm registered under id, or raise KeyError."""
  def list_algorithms() -> list[AlgorithmInfo]:
      """Return every registered algorithm, sorted by family then name."""
  def get_effect(id: str) -> EffectInfo:
      """Return the effect registered under id, or raise KeyError."""
  def list_effects() -> list[EffectInfo]:
      """Return every registered effect, sorted by name."""
  def resolve_params(specs: tuple[ParamSpec, ...], given: dict) -> dict:
      """Fill defaults, clamp numbers to their bounds, cast ints and validate choices."""
# --- lattice_core/pipeline ---
  class PresetMeta:
      """Human-readable description of a preset, carried through the JSON format."""
  class EffectInstance:
      """One configured effect in a pipeline, with its parameters and enabled flag."""
  class PaletteSpec:
      """Description of the palette a pipeline renders with."""
  class PipelineSpec:
      """Complete, serialisable description of one render."""
  def resolve_palette(spec: PaletteSpec, img: Image) -> Palette:
      """Return the float32 palette described by spec, extracting from img when needed."""
  def render(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
  def prepare_image(src: Image, spec: PipelineSpec, *, max_side: int | None = None,
  def render_with_palette(src: Image, spec: PipelineSpec, palette: Palette,
# --- lattice_core/preset ---
  class Preset:
      """A v3 preset: typed sections, preserved unknown keys and load warnings."""
  def to_json(preset: Preset) -> str:
      """Serialise preset as sorted, two-space-indented v3 JSON with one trailing newline."""
  def from_json(
  def save_preset(path: str | Path, preset: Preset) -> None:
      """Write preset as UTF-8 v3 JSON, creating parent directories."""
  def load_preset(
  def to_pipeline_spec(preset: Preset) -> PipelineSpec:
      """Return PipelineSpec carrying renderer/style and continuous-mode nulls (§5 S1)."""
  def from_pipeline_spec(spec: PipelineSpec) -> Preset:
      """Build a v3 preset from a PipelineSpec, keeping renderer and renderer_style."""
# --- lattice_core/palettes/builtin ---
  def get_builtin(name: str) -> Palette:
      """Return a copy of the built-in palette registered under name."""
  def builtin_names() -> list[str]:
      """Return the sorted names of every built-in palette."""
# --- lattice_core/ui/looks ---
  class Look:
      """One named pipeline variant shown in the Looks grid."""
  def render_look_thumbnail(look: Look, source: Image, size: int = THUMB_SIZE) -> RGB8:
      """Render look on the source proxy and return a size×size thumbnail."""
  class LookThumbnailWorker(QObject):
      """Renders look thumbnails on a helper thread and reports them by signal."""
      def build(self, look_id: str, spec: PipelineSpec, source: Image) -> None:
      """Render one thumbnail and emit it; this slot never touches a widget."""
  class LookCell(QWidget):
      """One gallery cell: a thumbnail above the look name."""
      def has_thumbnail(self) -> bool:
      """Return True once a rendered thumbnail has replaced the placeholder."""
      def show_placeholder(self) -> None:
      """Show the neutral placeholder instead of a thumbnail."""
      def set_thumbnail(self, rgb8: RGB8) -> None:
      """Show rgb8 as this cell's thumbnail; call it from the GUI thread only."""
      def mousePressEvent(self, event: QMouseEvent) -> None:
      """Report the look of the cell when it is clicked."""
  class LookGallery(QWidget):
      """Grid of look thumbnails rendered on the current image."""
      def cells(self) -> list[LookCell]:
      """Return every cell of the gallery, in the order the looks were set."""
      def looks(self) -> list[Look]:
      """Return the looks of the gallery, in display order."""
      def set_looks(self, looks: Sequence[Look]) -> None:
      """Replace the gallery with looks, in order, and re-queue every thumbnail."""
      def set_source(self, image: Image | None) -> None:
      """Set the current image; every thumbnail is re-rendered on it."""
      def shutdown(self) -> None:
      """Stop the helper thread and release its worker; safe to call more than once."""
      def closeEvent(self, event: QCloseEvent) -> None:
      """Stop the helper thread before the widget goes away."""
# --- lattice_glyph/presets ---
  class PresetEntry:
      """One preset file found in a search directory."""
  class PresetReport:
      """The outcome of validating one preset: its entry, its problems and its warnings."""
  def app_data_dir() -> Path:
      """Return this application's data directory: %LOCALAPPDATA% on Windows, XDG elsewhere."""
  def user_preset_dir() -> Path:
      """Return the user preset directory of this app, without creating it."""
  def search_dirs() -> tuple[Path, Path]:
      """Return the preset search order: the shipped tier first, the user tier second."""
  def available(directories: Sequence[Path] | None = None) -> list[PresetEntry]:
      """Return every preset of the search directories, a user file winning a name tie."""
  def default_spec() -> PipelineSpec:
      """Return the pipeline of a fresh Glyph document: glyph ramp, gameboy, 8 px cells."""
  def to_preset(spec: PipelineSpec, name: str = "") -> Preset:
      """Return the v3 preset of spec, its renderer kept, tagged ``app: glyph``."""
  def spec_of(preset: Preset) -> PipelineSpec:
      """Return the PipelineSpec of a parsed preset, its renderer and style included."""
  def read_preset(path: str | Path) -> Preset:
      """Read and parse one preset in this application's context."""
  def describe(preset: Preset) -> dict:
      """Return a JSON-serialisable summary of a preset, without rendering it."""
  def validate(path: str | Path) -> PresetReport:
      """Parse one preset and report every problem instead of raising it."""
  def validate_all(directories: Sequence[Path] | None = None) -> list[PresetReport]:
      """Validate every preset of the search directories, shipped tier first."""
  def save_preset(path: str | Path, preset: Preset) -> Path:
      """Write preset as UTF-8 v3 JSON, creating the parent directories, and return the path."""
  def save_spec(path: str | Path, spec: PipelineSpec) -> Path:
      """Write the v3 preset of spec to path."""

TASK CARD
### L21 · Preset interchange and gallery
- wave: 3 · deps: L12, L20 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/gallery.py`, `lattice_core/ui/gallery.py`, `tests/test_gallery.py`,
  `presets/**`
- context: §6 §11
- spec: a gallery showing every algorithm and renderer on one reference image, side by side — the
  documentation pattern that makes a 30-algorithm tool legible. Presets circulate between the three
  applications: a preset written by one loads in the others with a warning and a fallback renderer.
  Ship a starter set of at least 12 presets across the three apps.
- accept:
  - a preset written by `glyph` loads in `glitch` with a warning and renders.
  - a preset written by `dither` loads in `glyph` and renders with `pixel`.
  - the gallery renders every registered algorithm and renderer without raising.
  - at least 12 starter presets exist and all validate.
  - the gallery output is a single PNG under 4 MB.


CURRENT CONTENT OF YOUR FILES (disk state — integrate never replace; files marked 'à créer' do not exist yet)


# === lattice_core/gallery.py : à créer (n'existe pas encore) ===

# === lattice_core/ui/gallery.py : à créer (n'existe pas encore) ===

# === tests/test_gallery.py : à créer (n'existe pas encore) ===

# === presets/ : RÉPERTOIRE (12 fichiers) — à lire dans le repo, ne pas coller ici ===
#   presets/01_gameboy.json
#   presets/02_pico8_bayer.json
#   presets/03_blue_noise_cga.json
#   presets/04_halftone_print.json
#   presets/05_ega_riemersma.json
#   presets/06_glitch_scanlines.json
#   presets/07_grey16_stucki.json
#   presets/08_ostromoukhov_ega.json
#   presets/09_yliluoma2_pico8.json
#   presets/10_yliluoma1_grey16.json
#   presets/11_dot_diffusion_cga.json
#   presets/12_dbs_rgb8.json