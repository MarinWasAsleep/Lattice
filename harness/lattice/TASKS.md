# Lattice task cards — harness 0.1

Card fields: `wave`, `deps` (must be done), `executor`, `review` (strict | full | light), `size`
(S ≤ 150 lines, M ≤ 400, L ≤ 800 across files), `owns` (only files the task may write),
`context` (CONTRACT sections to inject verbatim), `spec`, `accept` (each item becomes a test or a
review check).

Contract sections refer to `harness/lattice/CONTRACT.md` (0.1.0). Sections §1 to §11 of
`harness/v1.0/CONTRACT.md` and §12 to §25 of `harness/v1.1/CONTRACT.md` remain in force for the
dithering application and are cited as `1.0 §n` and `1.1 §n`.

Max concurrency: 4. Two tasks may run together only if their `owns` sets are disjoint.

Routage des exécuteurs (0.1) : `executor` = catégorie de la chaîne OMH
(`omh_delegate_route`) qui désigne le modèle du codeur — `ultrabrain` (performance ou
décision critique), `architect` (contrat), `deep`, `deep-work` (coquilles d'applications),
`capable`, `quick`. Le relecteur est la catégorie `review` sur toutes les cartes ;
l'orchestrateur ne code jamais.

---

## Wave 0 — the shared core

### L1 · Extract `lattice-core` from Lattice Dither
- wave: 0 (critical path, do first, alone) · deps: none · executor: OMH ultrabrain · review: strict · size: L
- owns: `pyproject.toml`, `lattice_core/**`, `lattice_dither/**`, `tests/**`, `tools/**`
- context: §1 §2 §5 §19
- spec: create the `lattice_core` package and move into it, **without changing behaviour**. Arbre
  réel au HEAD `d66c4ca` (2026-11-16) :
  - `lattice_dither/core/{color,pipeline,presets,types,registry}.py` → `lattice_core/`
  - `lattice_dither/palettes/` (le paquet entier : `builtin.py`, `extract.py`, `io.py`,
    `library.py`, `data/`) → `lattice_core/palettes/`
  - `lattice_dither/algorithms/**` → `lattice_core/dither/` (les 33 algorithmes, `_strength.py` et
    `ostromoukhov_table.py` compris)
  - `lattice_dither/effects/**` → `lattice_core/effects/`
  - `lattice_dither/bridge/**` → `lattice_core/bridge/`
  Restent dans `lattice_dither` : `ui/`, `export/`, `preprocess/`, `i18n/`, `core/animation.py`
  (animation/vidéo = fonction de l'app, hors périmètre de la suite), `cli.py` (verbes 1.1
  spécifiques à l'app ; le cadre CLI partagé de §8 sera créé avec les coquilles L12/L20),
  `__init__.py`, `__main__.py` et la colle d'application. Il n'existe pas de `core/palette.py` :
  les palettes sont un package. Rename imports mechanically; do not refactor logic. Les baselines
  témoins existent déjà (`tests/data/baseline/` : `01_gameboy.png`, `05_ega_riemersma.png`,
  `07_grey16_stucki.png`, `source.png`, générées à la clôture du 1.1) : au démarrage, re-rendre
  les trois presets témoins (`01_gameboy`, `05_ega_riemersma`, `07_grey16_stucki`) au HEAD et
  vérifier la conformité bit-à-bit avant de toucher au code — recommitter un PNG seulement s'il
  diffère du HEAD. `pyproject.toml` devient la distribution `lattice-core` avec
  `[project.optional-dependencies] ui = ["PySide6"]` ; la base d'installation ne doit pas tirer Qt.
- accept:
  - `pip install -e .` in a clean venv installs numpy, numba and Pillow only; `import
    lattice_core` works and `import PySide6` is not attempted.
  - the three witness presets render byte-identically to their baselines (G7).
  - the full existing test suite passes unchanged, except for import paths.
  - `ruff check .` is clean.
  - `lattice_core` imports no module from `lattice_dither`, and contains no application module
    (`ui`, `export`, `preprocess`, `i18n`, `cli`, `animation`) — both checked by tests that walk
    the package.

### L2 · `CellRenderer` contract and `PixelRenderer`
- wave: 0 · deps: L1 · executor: OMH architect · review: strict · size: M
- owns: `lattice_core/cell.py`, `lattice_core/renderers/__init__.py`,
  `lattice_core/renderers/pixel.py`, `tests/test_cell.py`
- context: §3 §5
- spec: implement §3 exactly: `CellGrid`, `RenderStyle`, the `CellRenderer` protocol, the registry
  (`register_renderer`, `get_renderer`, `list_renderers`), and the `coverage` derivation. Implement
  `PixelRenderer` so that it reproduces the 1.0 `apply_palette` + `upscale_nearest` pair exactly.
  Wire step 11 of §5 into `pipeline.render` behind the registry, with `pixel` as the default so
  every existing caller keeps working.
- accept:
  - the six invariants of §3 are each a test.
  - `PixelRenderer` output is byte-identical to the 1.0 path on 20 random images and 5 palettes.
  - `list_renderers()` returns `["pixel"]` at this point.
  - `get_renderer("nope")` raises `KeyError` naming the missing renderer.
  - `coverage` is 0.0 on a single-colour palette and monotonic in palette luminance otherwise.
  - registering a duplicate name raises `ValueError`.

### L3 · Colour metrics and palette model
- wave: 0 · deps: L1 · executor: OMH deep · review: full · size: M
- owns: `lattice_core/color.py`, `lattice_core/palette.py`, `tests/test_color.py`,
  `tests/test_palette.py`
- context: §4, 1.1 §12, 1.1 §16
- spec: port the 1.1 colour metrics (`srgb`, `linear`, `oklab`, `lab2000`) into `lattice_core`.
  Add `Palette.lum_min` / `lum_max` computed once at construction in linear light. Palette import
  accepts hex lists, GPL files, PNG images and Lospec-style text; no network. `Palette.order` is a
  permutation or `None`.
- accept:
  - `srgb` output is byte-identical to the 1.0 implementation on 20 random images and 5 palettes.
  - `oklab` and `lab2000` disagree with `srgb` on at least 5 % of pixels of a saturated test image.
  - `lum_min`/`lum_max` are correct on a two-colour palette within 1e-6.
  - a GPL file, a PNG and a hex list of the same palette produce equal `Palette` objects.
  - a non-permutation `order` raises `ValueError` naming the offending index.
  - no import of `urllib`, `requests` or `socket` anywhere in `palette.py`.

### L4 · Preset format v3
- wave: 0 · deps: L1 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/preset.py`, `tests/test_preset.py`, `tests/data/presets/**`
- context: §6
- spec: implement §6. `from_json` accepts 1, 2 and 3; 1 and 2 map to `app: "dither"`,
  `renderer: "pixel"`. Unknown top-level keys and unknown `style` keys are preserved on round-trip.
  An `app` mismatch is not an error; a missing renderer falls back to the app default and records a
  warning. `to_json` writes sorted keys, two-space indent, one trailing newline.
- accept:
  - every preset in `presets/` loads and reports the right `version`.
  - a v3 preset round-trips through `to_json`/`from_json` with equality.
  - a preset carrying an unknown key `"future": {"x": 1}` survives a load/save unchanged.
  - `version: 4` raises `ValueError` naming 4.
  - loading a `glyph` preset in a `dither` context returns a warning and a `pixel` renderer.
  - `to_json` output is byte-stable across two calls.

### L5 · Bridge generalisation
- wave: 0 · deps: L1 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/bridge/**`, `tests/test_bridge.py`, `tests/test_bridge_smoke.py`
- context: §7
- spec: implement §7. `ArtCraftClient` with `discover`, `ping`, `render_document`,
  `place_as_layer`. Move the existing PhotoCraft code into `bridge/photocraft.py` unchanged. Add
  `bridge/designcraft.py` using `file.place` with `{path, frame?}` when a frame is selected and
  `{path, x, y, width}` otherwise. Discover the exact DesignCraft parameter surface with
  `designcraft-cli describe file.place` and record it as an amendment in `DEVIATIONS.md`; do not
  invent parameters. Every call is bounded by a timeout; failure returns a typed error, never a
  crash.
- accept:
  - `discover("photocraft")` returns `None` when the token file is absent, and a working client
    when PhotoCraft is running.
  - `discover("designcraft")` behaves the same way against a running DesignCraft.
  - `render_document` returns an image whose size matches `document.inspect`.
  - `place_as_layer` returns an integer id and the layer is visible in the host.
  - a bridge failure raises `BridgeError` and leaves no temporary file behind.
  - exchange files older than one hour are discarded on the next call.

---

## Wave 1 — glyphs

### L6 · Glyph ramp renderer
- wave: 1 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/glyph_ramp.py`, `tests/test_glyph_ramp.py`
- context: §3 §9
- spec: implement `glyph_ramp` per §9. Options: `ramp`, `font`, `size`, `fg`, `bg`, `mode`
  (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset`, `invert`. The ramp contract is
  darkest-first and is documented, not detected. `offset` shifts the luminance-to-glyph mapping and
  is animatable. Aspect correction uses `cell_aspect()`; default font ratio 1/2.
- accept:
  - a 10-character ramp on a black-to-white gradient produces 10 distinct glyphs in order.
  - `offset` shifts the mapping by exactly one glyph per 1/len(ramp) of coverage.
  - `invert` reverses the ramp.
  - `mode: "palette"` gives each glyph the palette colour of its cell.
  - `mode: "bg_colour"` puts the colour in the background and the glyph in `fg`.
  - output size is exactly `(cols * cell_w, rows * cell_h)`.
  - a missing font file raises `ValueError` naming the path.

### L7 · Shape-matched glyph renderer
- wave: 1 · deps: L6 · executor: OMH ultrabrain · review: strict · size: L
- owns: `lattice_core/renderers/glyph_shape.py`, `tests/test_glyph_shape.py`
- context: §3 §9
- spec: implement `glyph_shape` per §9. Six sampling circles per cell (top/middle/bottom ×
  left/right). For each glyph, compute the fraction of sampled points inside its ink. **Normalise
  each component by the maximum across the alphabet** — without this every vector clusters and
  every cell maps to the same few characters. Per cell, compute the same vector from `samples` and
  take the nearest neighbour. Cache shape vectors per (font, size) at module level.
- accept:
  - on a synthetic image of a diagonal edge, `glyph_shape` picks different glyphs on either side of
    the edge, and the chosen glyphs differ from `glyph_ramp` on at least 20 % of cells.
  - normalisation is verified: without it, a test asserts that more than 80 % of cells collapse to
    fewer than 3 distinct glyphs; with it, at least 8 distinct glyphs appear on a gradient.
  - the cache is hit on the second call (asserted by a counter).
  - budget: 1024×1024, 64 glyphs, under 200 ms after warm-up.
  - `p` and `q` are distinguished on a test image that differs only by vertical ink position.

### L8 · Bitmask renderers
- wave: 1 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/bitmask.py`, `tests/test_bitmask.py`
- context: §3 §9
- spec: implement `bitmask` per §9. One code path, four geometries: `braille` (2×4, U+2800+mask),
  `sextant` (2×3, U+1FB00..U+1FB3B), `quadrant` (2×2, U+2596..U+259F), `half_block` (1×2, U+2580/
  U+2584/U+2588). Threshold `samples` into sub-dots. Options: `threshold`, `fg`, `bg`, `dither`.
- accept:
  - a fully black cell produces the full codepoint for each geometry; a fully white cell produces
    the empty or background codepoint.
  - the four geometries produce the documented sub-cell counts (8, 6, 4, 2).
  - `threshold` at 0.5 on a half-black cell produces a half-filled codepoint.
  - `dither: true` changes the sub-dot pattern on a mid-grey cell and is deterministic.
  - every emitted codepoint is a valid Unicode scalar in the documented range.

### L9 · Text-halftone renderer
- wave: 1 · deps: L2 · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §3 §10
- spec: implement `text` per §10. Lay out a flowing paragraph with real font metrics: kerning, line
  distance, word wrapping. Modulate per-glyph weight, size and opacity by `coverage`. Cells may vary
  in size by ±50 % and must still fill the output rectangle exactly. Options: `text`, `font`,
  `size`, `line_distance`, `kerning`, `size_mode` (`fixed` | `variable`), `weight_mode`
  (`fixed` | `variable`), `fg`, `bg`.
- accept:
  - `size_mode: "fixed"` produces glyphs of identical size; `"variable"` produces at least 5
    distinct sizes on a gradient.
  - the output rectangle is filled exactly, with no gap and no overflow, for both modes.
  - a 200-word paragraph wraps without clipping and without a single glyph outside the canvas.
  - the same text and seed produce identical output across two calls.
  - an empty `text` raises `ValueError` naming the option.

### L10 · Glyph set browser and non-Latin ramps
- wave: 1 · deps: L6 · executor: OMH capable · review: light · size: M
- owns: `lattice_core/ui/glyph_browser.py`, `lattice_core/data/ramps.json`,
  `tests/test_ramps.py`
- context: §9
- spec: a browsable catalogue of glyph sets with a **live preview of the actual ramp rendered in the
  current font**, which almost nobody ships. Categories: classic ASCII, numbers, symbols, blocks,
  geometric, braille, playing cards, and non-Latin ramps (Japanese, Korean, Chinese, Russian,
  German, French, Spanish). `ramps.json` holds the data; the browser renders it.
- accept:
  - `ramps.json` validates against a schema test and every ramp is non-empty and darkest-first.
  - the browser renders a preview for every set without raising.
  - at least 8 categories and at least 6 non-Latin ramps are present.
  - selecting a set updates the preview within 100 ms.

### L11 · SVG export
- wave: 1 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/svg.py`, `tests/test_svg.py`
- context: §11
- spec: implement §11. `pixel` → `<rect>` per cell, merged into runs. `glyph_ramp`, `glyph_shape`,
  `bitmask` → one `<text>` per glyph with `font-family`, `font-size`, `fill`. `text` → one `<text>`
  per glyph preserving layout. Budget: 2048×2048, 16 colours, under 8 MB, else merge and warn.
- accept:
  - the output parses as XML and has the right root namespace.
  - a 64×64 pixel render produces fewer `<rect>` elements than cells (runs are merged).
  - a glyph render produces exactly `cols * rows` `<text>` elements.
  - the 8 MB budget triggers a merge and a warning on a large render.
  - the file opens in a browser without repair (checked by parsing, not by launching a browser).

### L12 · Lattice Glyph application shell
- wave: 1 · deps: L6, L8, L9, L11 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glyph/**`, `tests/test_glyph_app.py`
- context: §1 §2 §7 §8 §9 §10 §11
- spec: the `lattice-glyph` distribution. PySide6 window with a renderer selector, a live preview, a
  palette panel, a preset browser, and the four CLI verbs of §8. Bridge to PhotoCraft and
  DesignCraft. Works standalone on a dropped file. No new dependency.
- accept:
  - the app launches, opens an image, renders, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - `bridge status` reports the host state without crashing when no host runs.
  - the app runs with `lattice-core` installed without the `[ui]` extra only for the CLI path.
  - every renderer in the registry is selectable in the UI.

---

## Wave 2 — glitch

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

### L14 · Displacement
- wave: 2 · deps: L13 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/displace.py`, `tests/test_displace.py`
- context: §13
- spec: implement §13. Map source: still, sequence, noise field, or the feedback buffer. Modes:
  `luma`, `r`, `g`, `b`, `hue`. `dst(x, y) = src(x + k*(mapR-0.5), y + k*(mapG-0.5))`.
  `iterations` repeats with decay. `mask` restricts spatially. Bilinear sampling, clamped edges.
- accept:
  - a flat grey map leaves the image unchanged.
  - a horizontal ramp map shifts pixels by exactly `k/2` at the extremes.
  - `iterations = 3` produces a visibly longer smear than `iterations = 1` (measured by edge
    spread).
  - a mask of all zeros leaves the image unchanged; all ones equals no mask.
  - output shape equals input shape for every mode.

### L15 · Pixel sort
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/pixel_sort.py`, `tests/test_pixel_sort.py`
- context: §14
- spec: implement §14. Three thresholds (`black`, `brightness`, `white`), direction (`rows`,
  `columns`, `diagonal`), sort key (`luma`, `hue`, `saturation`, `r`, `g`, `b`), mask as interval
  map. Stable sort.
- accept:
  - a fully white image with `brightness = 0` sorts every row.
  - a fully black image with `black = 0` sorts nothing.
  - the sort is stable: equal keys keep their relative order.
  - a mask of all black sorts nothing; all white equals no mask.
  - `columns` transposes the result of `rows` on a square image.
  - output shape equals input shape.

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

### L20 · Lattice Glitch application shell
- wave: 2 · deps: L13, L14, L15, L16, L17, L18, L19 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glitch/**`, `tests/test_glitch_app.py`
- context: §1 §2 §7 §8 §12 §13 §14 §15 §16 §17 §18
- spec: the `lattice-glitch` distribution. PySide6 window with an effect stack, a live preview, a
  seed control with reroll and per-module lock, a mask painter, a preset browser, and the four CLI
  verbs of §8. Bridge to PhotoCraft and DesignCraft. Works standalone.
- accept:
  - the app launches, opens an image, stacks two effects, reorders them, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - reroll changes the output; locking a module keeps that module's contribution.
  - the mask painter produces a mask that the renderer honours.
  - the app runs with `lattice-core` without the `[ui]` extra only for the CLI path.

---

## Wave 3 — integration

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

### L22 · Acceptance in PhotoCraft and DesignCraft
- wave: 3 · deps: L21 · executor: OMH capable · review: strict · size: M
- owns: `tools/acceptance.py`
- context: §7 §19
- spec: an end-to-end acceptance script. For each of the three applications: pull the visible
  document from a running PhotoCraft, render, push as a layer, verify the layer exists and its
  pixels match. Then place the same render into a DesignCraft document via `file.place` and verify
  the placed object. The script prints a JSON summary (run date, host versions, per-app results) ;
  the orchestrator records it in `STATE.md` — the card does not write `STATE.md` directly.
- accept:
  - the script runs green against a live PhotoCraft and a live DesignCraft.
  - the pushed layer's pixels match the render within 1/255.
  - the placed DesignCraft object exists and its bounds match the requested width.
  - the script exits non-zero and names the failing host when a host is absent.
  - the JSON summary carries the run date and the host versions (orchestrator reports it in `STATE.md`).