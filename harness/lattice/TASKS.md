# Lattice task cards — harness 0.1

Card fields: `wave`, `deps` (must be done), `executor`, `review` (strict | full | light), `size`
(S ≤ 150 lines, M ≤ 400, L ≤ 800 across files), `owns` (only files the task may write),
`context` (CONTRACT sections to inject verbatim), `spec`, `accept` (each item becomes a test or a
review check).

Contract sections refer to `harness/lattice/CONTRACT.md` (1.0.0). Sections §1 to §11 of
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
  réel au HEAD `b4b0aea` (2026-11-16 — portage Linux approuvé, suite 1212 verte sur Mint) :
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
  `07_grey16_stucki.png`, `source.png` — 07 régénérée au portage Linux, gamma par table committée,
  voir décision 2026-11-16) : au démarrage, re-rendre les trois presets témoins (`01_gameboy`,
  `05_ega_riemersma`, `07_grey16_stucki`) au HEAD et vérifier la conformité bit-à-bit avant de toucher
  au code — recommitter un PNG seulement s'il diffère du HEAD. `pyproject.toml` devient la distribution
  `lattice-core` avec `[project.optional-dependencies] ui = ["PySide6"]` ; la base d'installation ne
  doit pas tirer Qt.
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
  `lattice_core/renderers/pixel.py`, `tests/test_cell.py` + `lattice_core/pipeline.py`
  (ajout DEV-203 : l'étape 11 de §5 et la dérivation coverage/luma/samples de §3 vivent
  dans `pipeline.render` — la carte ne peut pas les implémenter sans ce fichier)
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

### L2b · Pipeline §3/§5 complet — mode continu, sous-points, géométrie (H11)
- wave: 0 · deps: L2 · executor: OMH architect · review: strict · size: M
- owns: `lattice_core/pipeline.py`, `lattice_core/cell.py`, `tests/test_pipeline.py`
- context: §3 §5 (amendements H11 décidés 2026-11-16 : règle de géométrie §5-6, mode continu
  reformulé, pochoir `sample_points()`, `render_frame`, `layout()`, invariant 2 amendé)
- spec: compléter le pipeline et les types selon les amendements H11 :
  1. `PipelineSpec` gagne `renderer: str = "pixel"` et `renderer_style: dict = {}` ;
     `render` et `render_with_palette` les propagent (fin du `DEFAULT_RENDERER` hardcodé).
  2. Mode continu (§5) : `algorithm: null` et `palette: null` → étapes 6-11 sautées, l'image
     de l'étape 5 va directement aux post-effets (étape 12) ; aucun CellGrid construit, aucun
     renderer appelé. Bit-exact par construction.
  3. Sous-points (S3) : quand `renderer.subgrid() != (1, 1)`, l'algorithme tourne à la
     résolution (rows·sy, cols·sx) et `grid.subindex: (rows, cols, sx·sy) int32` est rempli.
  4. Pochoir `samples` : `renderer.sample_points()` (optionnel, H11) ; défaut = grille uniforme
     de k points, position appliquée dans la dérivation de `samples`.
  5. Règle de géométrie §5-6 (H11/Q4) : `a = cell_aspect()` ; si a >= 1 : cell_w = pixel_size
     et cell_h = max(1, floor(pixel_size / a + 0.5)) ; sinon l'inverse. L'aspect > 1 ne
     s'effondre plus en 1×1 (remplace l'arrondi half-to-even).
  6. `_render_frame` : si `render_frame` est implémenté, vérifier la forme
     (rows·cell_h, cols·cell_w, 3) — erreur typée sinon. `prepare_image` reçoit le renderer
     (géométrie correcte pour autre chose que pixel).
  7. `RenderStyle.__post_init__` stocke une copie des options (le mapping mutable du caller
     ne doit pas pouvoir contourner l'invariant 6).
  8. Docstrings §5 : « twelve normative pipeline steps ».
- accept:
  - en mode continu, `render` == étape 5 → étape 12 (bit-à-bit, avec et sans post-effect) ;
    aucun appel de renderer (vérifié par un spy) et aucun CellGrid construit.
  - `pixel` reste bit-identique 1.0 : 20 images aléatoires × 5 palettes flottantes, la suite
    existante (1257) reste verte, témoins bit-à-bit.
  - `subgrid (2, 3)` (stub) : `subindex` a la forme (rows, cols, 6) et la couverture des
    sous-points est monotone à la résolution du sous-point.
  - `sample_points()` : le nombre de points demandé est respecté ; sans la méthode, grille
    uniforme de k points.
  - renderer inconnu dans la spec → `KeyError` nommant le renderer ; style non JSON → `ValueError`.
  - stubs d'aspect 0.5 et 2.0 : la grille préserve l'aspect de la source, cell_w/cell_h
    conformes à la règle §5-6.
  - `render_frame` qui renvoie une mauvaise forme → erreur typée, pas de crash.
  - muter le dict du caller après construction de `RenderStyle` ne change pas le style.

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

### L-UI · Shared widgets, extracted from Lattice Dither (S5)
- wave: 0 · deps: L1 · executor: OMH capable · review: full · size: L
- owns: `lattice_core/ui/**`, `tests/test_ui_shared.py`, moves from `lattice_dither/ui/**`
- context: §2 (`lattice_core/ui/`), REVUE-PRODUIT (bloquants 1-2 de l'analyse Dither, S5)
- spec: implement §2 `ui/` as code, decided 2026-11-16. Extract from Lattice Dither the shared
  widgets into `lattice_core/ui/`: preview canvas + progress worker + before/after split,
  Looks grid (thumbnails rendered on the current image), one full-resolution export dialog
  (PNG/SVG/GIF — never the 1024 px preview proxy), bridge status dot, empty state. Fix first
  the two blocker findings of the Dither product review: (a) exported images must render at
  full resolution, (b) the preset indicator must be honest (applies the real preset, updates
  on change, absent when no image is loaded). Both apps (L12/L20) consume these widgets;
  they must not reimplement a canvas or an export dialog.
- accept:
  - `lattice_core/ui` imports no application module; apps import it under the `[ui]` extra.
  - the export dialog renders the pipeline at full resolution (not the preview proxy) and
    the resulting file matches the pipeline output size.
  - the preset indicator shows the actually-applied preset, updates after any pipeline
    change, and is hidden without an image.
  - canvas + worker + split, Looks grid, bridge status dot and empty state exist as widgets
    with tests (offscreen), each consumed by a smoke test.
  - no test regression: the full suite still passes (1216 baseline).

---

## Wave 1 — glyphs

### L6 · Glyph ramp renderer
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/glyph_ramp.py`, `tests/test_glyph_ramp.py` +
  `lattice_core/renderers/__init__.py` (enregistrement : ajout DEV-208 — append atomique d'une
  ligne d'import via terminal, JAMAIS write_file sur ce fichier, ne toucher qu'à VOTRE ligne)
- context: §3 §9
- spec: implement `glyph_ramp` per §9. Options: `ramp`, `font`, `fg`, `bg`, `mode`
  (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset`, `invert` — **pas de `size`** :
  la taille de police est dérivée de `cell_h` (H11/Q4, §5-6). La rampe est indexée par `luma`
  (S2, indépendante de la palette). The ramp contract is darkest-first and is documented, not
  detected. `offset` shifts the luma-to-glyph mapping and is animatable. Aspect correction uses
  `cell_aspect()`; default font ratio 1/2.
- accept:
  - a 10-character ramp on a black-to-white gradient produces 10 distinct glyphs in order.
  - une palette N&B ne réduit pas la rampe : les 10 caractères restent distincts (S2/H11).
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
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/renderers/bitmask.py`, `tests/test_bitmask.py` +
  `lattice_core/renderers/__init__.py` (enregistrement : ajout DEV-208 — append atomique d'une
  ligne d'import via terminal, JAMAIS write_file sur ce fichier, ne toucher qu'à VOTRE ligne)
- context: §3 §9
- spec: implement `bitmask` per §9. One code path, four geometries: `braille` (2×4, U+2800+mask),
  `sextant` (2×3, U+1FB00..U+1FB3B), `quadrant` (2×2, U+2596..U+259F), `half_block` (1×2, U+2580/
  U+2584/U+2588). Threshold `samples` into sub-dots. Options: `threshold`, `fg`, `bg` — pas de
  `dither` (S3/H11 : la décision du sous-point appartient à l'algorithme, résolu au subgrid).
- accept:
  - a fully black cell produces the full codepoint for each geometry; a fully white cell produces
    the empty or background codepoint.
  - the four geometries produce the documented sub-cell counts (8, 6, 4, 2).
  - `threshold` at 0.5 on a half-black cell produces a half-filled codepoint.
  - sur une cellule gris moyen, le motif des sous-points suit l'algorithme à la résolution du
    subgrid et est déterministe (S3 : pas d'option `dither`).
  - every emitted codepoint is a valid Unicode scalar in the documented range.

### L9 · Text-halftone renderer
- wave: 1 · deps: L2b · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §3 §10
- spec: implement `text` per §10. Lay out a flowing paragraph with real font metrics: kerning, line
  distance, word wrapping. Modulate per-glyph weight, size and opacity by `luma` (S2/H11 —
  l'encre ne doit pas s'effondrer sur une palette neutre). Cells may vary
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

### L11 · SVG export · text export
- wave: 1 · deps: L2b · executor: OMH capable · review: full · size: M
- owns: `lattice_core/svg.py`, `lattice_core/textout.py`, `tests/test_svg.py`, `tests/test_textout.py`
- context: §11 (incl. text export — P3, decided 2026-11-16)
- spec: implement §11, **depuis `layout()` quand le renderer l'implémente (H11/Q2)**.
  `pixel` → `<rect>` per cell, merged into runs. `glyph_ramp`, `glyph_shape`,
  `bitmask` → one `<text>` per glyph avec `font-family`, `font-size`, `fill` — via `layout()`.
  `text` → one `<text>` per glyph preserving layout. Budget: 2048×2048, 16 colours, under 8 MB,
  else merge and warn.
  **Text export**: `render --format txt|ansi|html` for `glyph_ramp`, `glyph_shape`, `bitmask` —
  from `layout()` (H11) : `.txt` UTF-8, `.ansi` 24-bit SGR, `.html` `<pre>`; HTML escapes text,
  ANSI never leaks into the text path.
- accept:
  - the output parses as XML and has the right root namespace.
  - a 64×64 pixel render produces fewer `<rect>` elements than cells (runs are merged).
  - a glyph render produces exactly `cols * rows` `<text>` elements.
  - the 8 MB budget triggers a merge and a warning on a large render.
  - the file opens in a browser without repair (checked by parsing, not by launching a browser).
  - `txt` output has `cols * rows` tokens and `rows` lines; `ansi` contains SGR 24-bit sequences
    only; `html` renders the same grid and escapes `<`/`&` in glyph text.

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

### L-LOOP · N-image loop (GIF/APNG)
- wave: 2 · deps: L20 · executor: OMH capable · review: light · size: S
- owns: `lattice_core/animation.py`, `tests/test_animation_loop.py`
- context: §12 §20 (P4, decided 2026-11-16)
- spec: move `core/animation.py` from Lattice Dither into `lattice_core/animation.py` and
  generalise it into a shared N-image loop: render N frames by varying seed, offset, or
  feedback iterations, emit GIF and APNG. Consumed by the Glitch CLI
  (`render --frames N --format gif|apng`) and by the L20 shell's export. No timeline, no
  video (§20). Lattice Dither's CLI keeps its exports as-is.
- accept:
  - N frames vary only the declared axis (seed/offset/itérations) and are identical otherwise.
  - GIF and APNG open with Pillow and have exactly N frames.
  - `animation.py` sits in lattice_core and imports no application module.
  - the Dither 1.1 exports (video path untouched) still pass their existing tests.

### L28 · Effet `bytemosh` : réinterprétation d'octets (data moshing)
- wave: 3 · deps: L18 | executor: OMH deep · review: full · size: M
- owns: `lattice_core/effects/bytemosh.py`, `lattice_core/effects/__init__.py`, `tests/test_bytemosh.py`
- context: §15 §16 (registre des effets), §20 (non-objectifs)
- origin: demande humaine du 2026-11-19. La suite couvre le displacement (map luma/canal, feedback) et le
  pixel sort, mais PAS le data moshing au sens strict : lire les octets d'un tampon et les réinterpréter
  comme des pixels. `/tmp/h13` (rendus H13) n'a rien de tel ; `jpeg_glitch` corrompt du DCT, ce n'est pas
  la même chose.
- spec: un effet qui traite la charge utile raster comme un FLUX D'OCTETS et la recolle ailleurs.
  1. **Opération `swap`** : échanger deux fenêtres d'octets de même longueur, à des décalages donnés.
  2. **Opération `shift`** : recaler un bloc d'octets d'un offset (le reste du tampon est décalé, pas
     dupliqué) — c'est ce qui produit les bandes qui « glissent » dans l'image.
  3. **Opération `interpret`** : lire une fenêtre d'octets comme une bande RGB et la poser à une autre
     position (l'image réelle réapparaît décalée, le look « fichier cassé »).
  Paramètres : `amount` (intensité 0..1), `operation` (`swap`|`shift`|`interpret`), `stride` (taille de
  fenêtre en octets, multiple de 3 pour que les canaux restent alignés), `offset` (décalage en octets),
  `seed` (choix des positions quand `amount` en tire au hasard).
- contraintes : numpy uniquement (aucune dépendance nouvelle, pas de codec) ; l'effet ne doit jamais
  lever sur une image de taille 1×1 ni sur `amount = 0` (identité exacte) ; sortie float32 dans [0,1],
  même forme que l'entrée ; déterministe pour un `seed` donné (§3 invariant 2) ; enregistré par
  `@register_effect("bytemosh", …)` avec ses `ParamSpec`.
- accept:
  - `amount = 0` rend l'image BIT-À-BIT identique (test).
  - `operation = "swap"` échange réellement deux fenêtres : le test relit les octets avant/après et
    vérifie la permutation exacte, sur une image où les fenêtres sont distinguables.
  - `operation = "shift"` décale la charge utile d'un nombre d'octets exact et borne le bord (pas de
    débordement d'index, pas de crash).
  - avec un `seed` donné, deux exécutions sont identiques ; deux seeds différents changent le résultat.
  - l'effet apparaît dans `list_effects()` et dans le formulaire généré (ParamSpec complets) ; il est
    exécutable depuis le CLI Glitch par un preset v3 sans code spécial.
  - une image 1×1 et une image dont la charge utile est plus courte que `stride` ne lèvent pas.

## Wave 3 bis — décisions Opus du 19/11 (H13)

### L24 · CRT : les colonnes de bord étirées en aplats par la courbure (H13, M1)
- wave: 3 · deps: L18 | executor: OMH capable · review: light · size: S
- owns: `lattice_core/effects/crt.py`, `tests/test_crt.py`
- context: §17
- origin: verdict Opus H13 du 2026-11-19 (constat M1, prouvé sur image réelle). La grille de phosphores
  est appliquée AVANT la courbure (`crt.py:178-185`) ; la courbure échantillonne hors image et clampe au
  bord (`_sample`, `crt.py:131-133`) ; or la colonne 0 du masque est rouge et la dernière bleue
  (`crt.py:69-73`) — elles sont donc étirées en bandes pleines sur toute la hauteur. Visible sur le
  preset livré `lattice_glitch/presets/08_crt_finish.json` (curvature 0.2).
- spec: corriger l'ORDRE, pas le masque : appliquer le masque de phosphores APRÈS la courbure, de sorte
  que le masque s'applique à l'écran courbé (physiquement juste) et qu'aucune colonne du masque ne soit
  étirée. Le rendu sans courbure ni vignette doit rester BIT-À-BIT identique (G7 : c'est le chemin gelé
  des presets existants). Si un échantillonnage hors bord doit changer, il retourne du noir, jamais la
  couleur du bord.
- accept:
  - avec `curvature: 0.2` + le masque du preset 08, aucune colonne de bord n'est un aplat monochrome :
    la variance par colonne sur les 8 premières et 8 dernières colonnes dépasse 1 % de la plage.
  - `curvature: 0` + masque : sortie bit-à-bit identique à HEAD (test de non-régression G7).
  - les 14 tests CRT existants restent verts.

### L25 · Boucle animée branchée dans Lattice Glitch (H13, B1+B2)
- wave: 3 · deps: L20, L-LOOP | executor: OMH deep · review: full · size: M
- owns: `lattice_core/animation.py`, `lattice_glitch/cli.py`, `lattice_glitch/export_actions.py`,
  `tests/test_animation_loop.py`, `tests/test_glitch_app.py`
- context: §8 §20
- origin: verdict Opus H13 du 2026-11-19 (B1, B2 ; question Q1 réponse 1). `render_loop` n'est appelé
  nulle part dans `lattice_glitch/` ; l'export n'offre que PNG (`export_actions.py:61`) et le CLI que
  `png` (`cli.py:286`). De plus `render_loop` passe par `pipeline.render_with_palette` (règle de seed
  1.0, `seed + offset + i`) qui ignore masques et verrous : l'image 0 d'une boucle ne serait pas le PNG
  affiché.
- spec: `render_loop` accepte une fonction de rendu INJECTABLE (image → RGB8) ; Glitch lui passe
  `document.render_rgb8` avec son RenderContext (masques, flux, verrous). Nouveau verbe CLI
  `loop --preset P --in IMG --out F.gif|.png --frames N [--axis seed|offset|iterations]`, et entrée
  GIF/APNG dans le dialogue d'export. `pipeline` n'est pas modifié (pas de régression G7).
- accept:
  - l'image 0 d'une boucle Glitch est OCTET-IDENTIQUE au PNG du même preset (preuve que le chemin est
    le même).
  - un GIF et un APNG s'ouvrent avec Pillow et comptent exactement N frames.
  - un preset à masque : le masque reste appliqué sur les N frames.
  - CLI sans Qt (import ininterrompu sous bloqueur PySide6).
  - les 22 tests L-LOOP restent verts.

### L26 · L'axe `seed` respecte les verrous (H13, B3)
- wave: 3 · deps: L25 | executor: OMH deep · review: full · size: S
- owns: `lattice_core/animation.py`, `tests/test_animation_loop.py`
- context: §18 §8
- origin: verdict Opus H13 du 2026-11-19 (B3, Q2 réponse 1). `replace(spec, seed=seed+step*i)`
  (`animation.py:110`) change TOUS les modules : les verrous sont ignorés, on obtient un scintillement,
  pas un mouvement.
- spec: en mode seed, les modules VERROUILLÉS gardent leur stream (contribution identique sur toutes les
  frames) ; seuls les modules libres varient. Le verrou reste session-only côté cœur (DEV-216) ; c'est
  l'API de la boucle qui accepte un ensemble de flux figés par module.
- accept:
  - deux frames consécutives : la contribution d'un module verrouillé est identique (bit-à-bit sur le
    rendu de ce module seul), celle d'un module libre diffère.
  - sans verrou, comportement actuel inchangé (non-régression).
  - les 22 tests L-LOOP + ceux de L25 restent verts.

### L27 · Quatrième axe `param` (boucle paramétrique, H13, Q3)
- wave: 3 · deps: L26 | executor: OMH deep · review: full · size: M
- owns: `lattice_core/animation.py`, `tests/test_animation_loop.py`
- context: §20 (amendement), §12-§17
- origin: verdict Opus H13 du 2026-11-19 (Q3 réponse 1). Channel rift, Sort echo et CRT finish sont
  DÉTERMINISTES : en mode seed, 3 starters sur 4 produisent N images identiques. Le seul moyen de les
  animer sans timeline est de faire aller un paramètre numérique de A à B et retour.
- spec: 4e axe `param` : `--param <effet>.<clé> --from A --to B --curve sin|linear`, une seule valeur par
  boucle, ALLER-RETOUR (image N == image 0) pour que la boucle soit sans raccord. Amendement §20 :
  la liste des axes gagne `param`, toujours sans timeline et sans vidéo.
- accept:
  - sur channel_shift, les N frames diffèrent deux à deux et la dernière égale la première.
  - la courbe linéaire va strictement de A à B.
  - un preset déterministe produit N images DIFFÉRENTES (aujourd'hui : identiques).
  - les tests de L25/L26 restent verts.

### DEV-229 — H13 : décisions Opus appliquées (Q1-Q5)
- class: E7 (produit) + AMD §20 | status: applied | date: 2026-11-19
- decision (Opus, délégué par l'humain) : Q1 = 1 (rendu injectable, verbe CLI loop, export GIF/APNG) ;
  Q2 = 1 (les verrous figent le module sur toutes les frames) ; Q3 = 1 (4e axe `param`, aller-retour,
  un seul paramètre) ; Q4 = 1 (le bug CRT passe AVANT le gel H13) ; Q5 = 1 (planche de 4 GIF sur source
  nette, image 0 == PNG, vérifiée à l'œil).
- verdict : OUI SOUS CONDITIONS — le moteur pour animer existe, il n'est pas raccordé. 3 cartes (L25-L27)
  + le correctif CRT (L24).

---

### L-UI2 · Recâblage de Lattice Dither sur `lattice_core/ui` (doublons supprimés)
- wave: 2 · deps: L-UI, L11 · executor: OMH deep-work · review: strict · size: L
- owns: `lattice_dither/ui/**`, `tests/test_ui_*.py`, `lattice_core/ui/**`
- context: §2 (`ui/`), 1.1 §19-§22 (fenêtre, export, raccourcis), REVUE-PRODUIT (bloquants 1-2)
- motivation (décision humaine du 2026-11-18) : `lattice_dither/ui/` fait 4026 lignes et n'importe
  AUCUN widget de `lattice_core/ui`. Le canvas a été dupliqué à l'identique lors de L-UI, mais le
  worker et le dialogue d'export ont divergé : le core n'a ni `request_send`/`request_get`/
  `check_version` (pont PhotoCraft interactif), ni `PaletteExtraction` (extraction de palette sur
  thread), ni les pages d'export impression/GIF/vidéo. Tant que Dither garde sa copie, la suite
  n'a pas UNE ui partagée mais deux, et chaque correctif doit être fait deux fois — c'est
  exactement le défaut structurel S5 relevé par la revue produit.
- spec: recâbler Dither sur les widgets du core sans changer un pixel de rendu ni un raccourci.
  1. Ce qui manque au core d'abord : généraliser `RenderWorker` pour couvrir les verbes pont
     (`request_send`, `request_get`, `check_version`) et extraire `PaletteExtraction` dans
     `lattice_core/ui/worker.py` — le bridge du core (`lattice_core/ui/bridge.py`) porte déjà le
     `ConnectionProbe`, ne pas le redupliquer.
  2. Le dialogue d'export du core doit couvrir les quatre formats de Dither (PNG, SVG, impression,
     GIF/vidéo séquence) ; les pages spécifiques restent dans l'app SEULEMENT si elles dépendent
     d'un format que le core n'a pas à connaître.
  3. Ensuite seulement : `lattice_dither/ui/` réimporte les widgets du core ; les fichiers devenus
     vides sont SUPPRIMÉS (pas de coquilles de ré-export qui laisseraient deux chemins d'import).
  4. Aucune régression de comportement : G6 (parité CLI/GUI de Dither) et G7 (témoins bit-à-bit)
     doivent rester verts, et la batterie 1.1 de Dither (raccourcis §22.2, undo, récents, drag & drop)
     doit passer sans qu'un seul test soit modifié — sauf import.
- accept:
  - `lattice_dither/ui/` n'importe plus aucun widget propre : `PreviewCanvas`, `RenderWorker`,
    `PaletteExtraction`, `ExportDialog`, `LookGallery` et `PresetIndicator` viennent du core.
  - pas un seul fichier de `lattice_dither/ui/` ne duplique un widget existant dans
    `lattice_core/ui/` (vérifié par un test qui compare les `__all__` et les noms de classes).
  - les 11 fichiers `tests/test_ui_*.py` passent ; `tests/test_ui_shared.py` reste vert ; le compte
    total de tests ne baisse pas.
  - G6 et G7 verts : un même preset rend des octets identiques en CLI et GUI, et les trois témoins
    sont bit-à-bit.
  - le worker du core expose `request_send`, `request_get`, `check_version` et `PaletteExtraction`,
    couverts par des tests, et `lattice_core` n'importe toujours aucune application (E8).
  - `lattice_core/ui` s'installe et s'importe sans Dither : `pip install -e .[ui]` seul suffit.

### L9b · Renderer `text` : répétition du paragraphe pour remplir la toile (H12)
- wave: 2 · deps: L9 | executor: OMH capable · review: strict · size: M
- owns: `lattice_core/renderers/text.py`, `tests/test_text.py`
- context: §10
- origin: décision humaine H12 du 2026-11-18 (DEV-218). Le renderer pose son paragraphe UNE fois
  (`_flow` boucle sur `while idx < len(chars)`) : mesuré 496 caractères sur 12 960 cellules
  disponibles, soit 3 % de la hauteur de la toile à `pixel_size 10`. §10 exige que les cellules
  « must still fill the output rectangle exactly ».
- spec: boucler le texte jusqu'à ce que toutes les cellules soient couvertes. Option `repeat`
  (`fill` | `once`), défaut `fill` ; `once` conserve le comportement actuel pour qui veut un
  paragraphe unique. Ne change pas la modulation par `luma`, ni la césure, ni `size_mode`.
- accept:
  - sur un paragraphe court (une phrase) et un canevas large, la fraction de cellules portant de
    l'encre dépasse 90 % en mode `fill`.
  - `repeat: once` reproduit exactement le comportement d'avant (test de non-régression).
  - le texte bouclé respecte la césure et ne produit aucun glyphe hors du canevas (les tests de L9
    restent verts).
  - la luma du rendu d'un portrait sur fond neutre passe sous 0,90 et son contraste dépasse 0,20
    (aujourd'hui : 0,995 / 0,011).

### L9c · `glyph_ramp` en mode `palette`/`bg_colour` : fond respecté, encre relative, rampe bornée (H12)
- wave: 2 · deps: L6 | executor: OMH deep · review: strict · size: L
- owns: `lattice_core/renderers/glyph_ramp.py`, `tests/test_glyph_ramp.py`
- context: §9
- origin: décisions humaines H12 du 2026-11-18 (3 questions sur 4). Trois défauts prouvés :
  (a) en mode `palette`, le papier vient du ton le plus sombre de la palette et le `bg` déclaré est
  ignoré — un preset qui demande `#ffffff` rend 80 % de noir ; (b) en mode `bg_colour`, une encre
  fixe ne peut pas fonctionner : le fond porte le ton, donc la rampe double l'information et le
  glyphe se bat contre le fond ou s'efface ; (c) les ombres restent muettes parce que la rampe
  envoie l'espace (densité nulle) dans les zones sombres.
- spec:
  1. **Fond respecté** : en mode `palette`, le papier est `bg` du style. Le ton le plus sombre de
     la palette devient le comportement de `bg: "auto"` (valeur explicite), jamais le défaut.
  2. **Encre relative** (modes `palette` et `bg_colour`) : trier la palette par luma une fois, prendre
     le rang du fond de la cellule, et choisir l'encre 2 crans au-dessus si le fond est sombre,
     2 crans en dessous s'il est clair. L'encre n'est plus une couleur fixe dans ces deux modes.
  3. **Rampe bornée en `bg_colour`** : le glyphe ne suit plus la luma absolue mais l'écart entre le
     ton de la cellule et le fond ; espace et `@` exclus de la rampe dans ce mode (densité moyenne).
- accept:
  - un preset `mode: palette` avec `bg: #ffffff` produit un rendu dont la luma dépasse 0,60
    (aujourd'hui 0,036).
  - en `bg_colour` sur un portrait, le contraste dépasse 0,30 ET les ombres portent des glyphes
    visibles — décision humaine 18/11/2026 (E2 amendé, suite au rejet du span³) : ≥ 5 glyphes distincts
    dans les 20 % de cellules les plus sombres à 8 px, ≥ 4 à 12 px (taille de référence H12).
  - `bg: "auto"` reproduit exactement l'ancien comportement du mode `palette` (non-régression).
  - les six invariants §3 tiennent et G8 reste vert sur tout le registre.
  - la taille de cellule n'est pas modifiée comme correctif : à 12 px le rendu doit déjà tenir.

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

### L23 · Packaging multi-plateforme et installation
- wave: 3 · deps: L12, L20 · executor: OMH capable · review: light · size: S
- owns: `scripts/**`, `tools/**`
- context: §1 §2
- spec: chaque app de la suite se lance en développement sur Windows ET Linux, et se distribue sur
  les deux. Scripts de build et d'installation par plateforme : binaire PyInstaller par OS, entrée de
  menu (`.desktop` sur Linux, raccourcis PowerShell sur Windows), mêmes numéros de version. Aucune
  nouvelle dépendance d'exécution. Les hôtes ArtCraft restent une intégration détectée au runtime (E9).
- accept:
  - sur un venv vierge de chaque plateforme, l'installation des paquets puis `python -m <app>` ouvrent
    la fenêtre avec une image chargée.
  - le script de build produit un binaire par plateforme qui lance l'app sans Python installé.
  - l'entrée de menu (`.desktop` / raccourcis) lance l'app ; un échec d'installation échoue avec une
    ligne nommée dans les logs.
  - la release d'une app embarque les deux binaires construits à partir de la même version de code.
## Wave 4 — post-H13, données brutes et finition 1.0

### L28 · `bytemosh` : corruption de données brutes
- wave: 4 · deps: — · executor: qwen4 · review: Opus (visuelle) · size: M · **done**
- owns: `lattice_core/effects/bytemosh.py`, `tests/test_bytemosh.py`, `docs/bytemosh/**`
- context: demande humaine (« un truc pour faire du pixel displacement ou du data moshing ? »)
- spec: quatre opérations — `swap`, `shift` (indel), `interpret`, `drift` — pilotées par
  `amount`/`operation`/`stride`/`offset`/`seed`. `amount=0` bit-identique, déterministe par seed.
- accept: notes Opus finales — shift 8,5/10, interpret 8/10, swap 7/10, drift 7/10.
- notes: deux défauts trouvés par mesure puis par Opus — bornes `ParamSpec` silencieuses
  (`stride` 3072 = 1,4 ligne, `offset` ±65536) relevées à ±4 000 000 (DEV-234) ; `shift` inopérant
  à `offset=0` et `drift` ignorant `stride`/`offset`, rayures arc-en-ciel dues à un pas non multiple
  de 3 (DEV-235, DEV-236).

### L29 · Documentation de `bytemosh` et axe `param` au CLI
- wave: 4 · deps: L28 · size: S · **done**

### L30 · `shift` en indel : le décalage propage à partir de la coupure
- wave: 4 · deps: L28 · size: S · **done**
- spec: `data[p:] = np.roll(data[p:], d)` — une translation propre ne damage rien, Opus l'avait
  notée 1/10 ; un indel abîme à partir de P et seulement là.

### L31 · `feedback` : origine et direction
- wave: 4 · deps: — · size: M · **done**
- owns: `lattice_core/effects/feedback.py`, `tests/test_feedback.py`
- spec: `origin` (centre, 4 coins, 4 bords) et `direction` (−180..180), `iterations` 8→16.
- notes: **axe Y inversé trouvé par Opus** — `cap 90` montait au lieu de descendre, convention
  mathématique au lieu d'écran ; `sy = ys - amount*sin(angle)` (DEV-237).

### L32/L33 · Polissage post-H13 de `sort_echo` et du CRT
- wave: 4 · deps: L24 · review: Opus · **done**
- notes: `sort_echo` 3/10 → 5-6/10 (cause mesurée : `white=1.0` faisait courir les runs 543 px sur
  720 ; `white 0.92` + `brightness 0.45`) ; CRT gagne `roll` (phase du balayage) au lieu d'animer
  `curvature` — « aucun tube ne fait ça » (DEV-241). Rejetés sur mesure : bande 0.30-0.70, clés
  `saturation` et `hue`.

### L34 · Passe visuelle des huit starters dither et glyph
- wave: 4 · deps: — · review: Opus · **done**
- notes: trois accusations d'Opus confirmées sur mesure — `dither_01` à 99,8 % sur deux couleurs,
  `glyph_01` en `mono` noir/blanc avec un masque orphelin, renderers bitmask n'utilisant la palette
  que pour décider quels points s'allument. `glyph_04` passé en mode continu : le tramage en amont
  détruisait les échantillons (DEV-242, DEV-243).

### L36 · Galerie d'algorithmes promue dans le core
- wave: 4 · deps: — · size: M · **done**
- owns: `lattice_core/ui/algorithm_gallery.py`, `lattice_dither/ui/gallery.py`
- spec: la vraie galerie (440 l.) monte dans le core, le prototype mort (300 l.) disparaît, l'app se
  réduit à une **fabrique** de 30 l. (`test_ui_no_duplicates` interdit un nom de classe présent dans
  deux paquets) ; `app_dir_name` et `set_translator` injectés (DEV-244).

### L37 · `cli.py` et `actions.py` partagés
- wave: 4 · deps: L36 · size: L · **done**
- owns: `lattice_core/cli_shared.py`, `lattice_core/ui/actions.py`, les deux `cli.py`/`actions.py` d'app
- spec: les onze verbes communs vivent une seule fois ; un `CliBackend` déclare ce qui reste propre à
  l'app, `extra_verbs` enregistre `loop` côté Glitch seul. Tailles : cli 419+370 → 144+72 (+417),
  actions 136+114 → 57+58 (+172).
- notes: sept pièges corrigés, tous trouvés par les tests — dont Glyph qui rend un **spec** là où
  Glitch rend un **preset**, et `discover_host` qui doit se résoudre à l'appel, pas à l'installation
  du backend (DEV-245).

### L38 · 1.0.0 : versions alignées, binaires reconstruits, coexistence des trois shells
- wave: 4 · deps: L37 · size: L · **done**
- owns: `pyproject.toml` ×4, `__init__.py` ×4, `build/manifests/**`, `scripts/packaging/*.spec`,
  `tests/test_three_shells.py`
- spec: un seul numéro partout, annoncé par chaque surface ; six binaires reconstruits et installés ;
  `.desktop` validés ; un test qui démarre les trois apps dans un même processus.
- accept: `lattice-dither 1.0.0`, `lattice-glyph 1.0.0`, `lattice-glitch 1.0.0` depuis les binaires
  installés ; `VERSION CHECK OK` ; tag `v1.0.0`.
- notes: **trois bugs trouvés en testant les binaires livrés, aucun visible dans la suite** — Dither
  ne pouvait ouvrir aucun de ses quatre starters (v3 contre chargeur v1/v2, DEV-246) ; Glyph et
  Glitch mouraient sur `ModuleNotFoundError` (import dynamique de `entry.py` non suivi par
  PyInstaller) ; `grey16_atkinson` annonçait 16 gris et en rendait 243 (post-effet `sharpen` sur le
  grain du tramage, DEV-247). Voir aussi DEV-248 (`--version`).
