# DitherCraft task cards — harness 1.1

Card fields: `wave`, `deps` (must be done), `executor`, `review` (strict | full | light), `size`
(S ≤ 150 lines, M ≤ 400, L ≤ 800 across files), `owns` (only files the task may write),
`context` (CONTRACT sections to inject verbatim), `spec`, `accept` (each item becomes a test or a
review check).

Contract sections §1 to §11 refer to `harness/CONTRACT.md` (1.0.0). §12 to §25 refer to
`harness/v1.1/CONTRACT.md` (1.1.0).

Max concurrency: 4. Two tasks may run together only if their `owns` sets are disjoint. The only
shared files in 1.1 are `ui/main_window.py` (T27, T32) and `ui/palette_panel.py` (T21, T32); both
pairs sit in different waves and are never concurrent.

---

## T17 · Spec v2, preset v2, conditioning
- wave: 4 (critical path, do first) · deps: none · executor: DeepSeek · review: strict · size: L
- owns: dithercraft/core/types.py, dithercraft/core/pipeline.py, dithercraft/core/presets.py,
  tests/test_pipeline.py, tests/test_presets.py, tests/test_preset_compat.py
- context: §3 §7 §12 §13 §18 §25
- spec: implement §13 and §18 exactly. `PipelineSpec` gains `saturation`, `pre_blur`, `auto_levels`,
  `color_metric`; `PaletteSpec` gains `locked` and `order`; `PresetMeta` is added and carried by
  `PipelineSpec.meta`. `adjust` gains the `saturation` argument with the default 0.0 so every
  existing caller keeps working. The render order becomes the eleven steps of §13; steps 3, 4 and 5
  are new and must be no-ops at their defaults. `to_json` writes version 2 and `meta`; `from_json`
  accepts 1 and 2 and raises `ValueError` naming any other version. `tests/test_preset_compat.py`
  holds the three witness presets (`01_gameboy`, `05_ega_riemersma`, `07_grey16_stucki`) as
  committed PNG baselines rendered **before** this task starts; the test re-renders and compares
  bytes. Generate the baselines with the 1.0 code and commit them under `tests/data/baseline/`.
- accept:
  - a v1 preset loads, `version` reads 1, and the render is byte-identical to its baseline (G5).
  - a v2 preset round-trips through `to_json`/`from_json` with equality.
  - `version: 3` raises `ValueError` naming 3.
  - `saturation=0`, `pre_blur=0`, `auto_levels=False`, `color_metric="srgb"` reproduce the 1.0
    output exactly on all three witnesses.
  - `saturation=1` on a grey image changes nothing; on a coloured image it increases the channel
    spread; `saturation=-1` makes every pixel grey within 1e-6.
  - `auto_levels` maps a 0.2..0.8 ramp to 0..1 within 1/255.
  - `pre_blur` preserves the mean within 1e-3 and is a no-op at 0.
  - `PaletteSpec.order` that is not a permutation raises `ValueError` at `resolve_palette`.
  - `locked` with more than `extract_k` entries raises `ValueError`.

## T18 · Colour matching metrics
- wave: 4 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/core/color.py, tests/test_color.py
- context: §5 §12
- spec: implement §12. One numba kernel per metric, or one kernel with a metric code; palette
  converted once per call. `nearest_index` keeps `metric="srgb"` as the default so nothing else
  changes. `lab2000` may use a 33³ trilinear LUT if the exact path misses the budget; the LUT is
  built lazily and cached at module level.
- accept:
  - `srgb` output is byte-identical to the 1.0 implementation on 20 random images and 5 palettes.
  - on `pal_bw`, a mid-grey pixel picks the same index under all four metrics.
  - `oklab` and `lab2000` disagree with `srgb` on at least 5 % of pixels of a saturated test image
    with `pico8` (proves the metric is actually applied).
  - `lab2000` matches a reference CIEDE2000 implementation within 1e-6 on 100 colour pairs
    (reference values hard-coded in the test from the published test data).
  - `perf` test: 1024×1024, K=16, each metric under 150 ms after warm-up (informative, not a gate).
  - the LUT path, if used, stays within ΔE 0.5 of the exact path on 1000 sampled pixels.

## T19 · Dither strength across every algorithm
- wave: 4 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/algorithms/error_diffusion.py, dithercraft/algorithms/ordered.py,
  dithercraft/algorithms/misc.py, dithercraft/algorithms/halftone.py,
  dithercraft/algorithms/ostromoukhov.py, dithercraft/algorithms/yliluoma.py,
  dithercraft/algorithms/dot_diffusion.py, dithercraft/algorithms/dbs.py,
  tests/test_strength.py
- context: §4 §14
- spec: implement §14. Every registered algorithm gets `strength` in its `params` tuple, float 0..1,
  default 1.0, with the family semantics of §14. Algorithms that already have `strength` keep their
  existing behaviour at 1.0. Do not change any other parameter, default or algorithm output at
  `strength=1`.
- accept:
  - **the invariant, for every registered algorithm**: `strength=0` equals
    `nearest_index(img, palette, metric)` exactly, on three test images and two palettes. The test
    iterates `list_algorithms()` so a future algorithm is covered automatically.
  - `strength=1` output is byte-identical to the pre-task output for every algorithm (baseline
    captured before the change).
  - `strength=0.5` output differs from both 0 and 1 on at least one algorithm per family.
  - `resolve_params` clamps `strength` to [0, 1].

## T20 · Halftone v2 and CMYK halftone
- wave: 4 · deps: T17 · executor: DeepSeek · review: full · size: L
- owns: dithercraft/algorithms/halftone.py, dithercraft/effects/halftone.py,
  dithercraft/effects/__init__.py, tests/test_halftone.py, tests/test_effects_halftone.py
- context: §4 §15
- spec: implement §15.1 in `algorithms/halftone.py` (new params `dot_shape`, `oversample`,
  `per_channel`; `angle` range widened to 0..180) and §15.2 as a new post-effect module
  `effects/halftone.py` registered as `halftone_cmyk`. `effects/__init__.py` imports it. The CMYK
  effect works in RGB space: convert to CMYK, screen each plate at its fixed angle, recombine.
  `lpi` maps to a cell size through the 300 DPI reference of §15.2.
- accept:
  - every `dot_shape` produces a different output on the same input; all six are accepted and an
    unknown shape raises `ValueError`.
  - `per_channel=True` on a saturated red image produces non-zero coverage in more than one channel.
  - `oversample` 1 vs 4 differ, and 4 is smoother (lower variance inside a cell).
  - `halftone_cmyk` on pure white produces no ink; on pure black produces K coverage only when
    `black_pullout=1`, and C+M+Y coverage when `black_pullout=0`.
  - `halftone_cmyk` output is float32 in [0, 1] with the input shape, for 1×1 and 37×23 inputs.
  - `ink_colors=True` output is not greyscale on a coloured input.

## T21 · Palette authoring and library
- wave: 4 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/palettes/library.py, dithercraft/palettes/data/*.hex,
  dithercraft/palettes/io.py, dithercraft/ui/palette_panel.py, tools/fetch_palettes.py,
  tests/test_palette_library.py, tests/test_ui_palette.py
- context: §6 §16
- spec: implement §16. Ship at least 12 library palettes whose licence permits redistribution, each
  file starting with `# source:` and `# licence:` comment lines; only palettes with a verifiable
  permissive licence (CC0, public domain, or explicitly free to redistribute) may be shipped — when
  in doubt, leave it out and say so in NOTES. `from_hex_text` accepts pasted hex lists.
  `tools/fetch_palettes.py` is standalone, uses `urllib`, is never imported by the app, and is
  documented as manual. The palette panel gains lock toggles on swatches, drag-to-reorder, and a
  library picker.
- accept:
  - every shipped `.hex` parses, has 2..256 colours, and its header names a source and a licence.
  - `library_names()` is sorted and stable; `get_library` on an unknown name raises `KeyError`.
  - `from_hex_text` handles `#RRGGBB`, `RRGGBB`, commas, newlines, tabs and surrounding prose.
  - locked swatches survive extraction unchanged; reordering changes `order` but not the rendered
    image (assert on a render before and after).
  - the panel round-trips a spec with `locked` and `order` set.
  - `tools/fetch_palettes.py --help` runs without network access.

## T22 · CLI and batch
- wave: 5 · deps: T17 · executor: DeepSeek · review: strict · size: M
- owns: dithercraft/cli.py, tests/test_cli.py, tests/test_cli_parity.py
- context: §7 §17 §25
- spec: implement §17. `render`, `batch` and `info` subcommands, argparse, no third-party CLI
  library. `render` and `batch` call `core.pipeline.render` with the same arguments the GUI uses.
  `tests/test_cli_parity.py` renders the same preset and image through the CLI and through
  `pipeline.render` and compares bytes (G6).
- accept:
  - `render` on a 3-preset × 2-image matrix produces byte-identical files to the direct
    `pipeline.render` call (G6).
  - `batch` with `--jobs 4` produces the same bytes as `--jobs 1`.
  - exit codes 0/1/2/3 as specified; a missing input file gives 2 and a one-line message, never a
    traceback.
  - `--json` output parses and contains `ok`, `files`, `errors`.
  - `batch` skips up-to-date outputs and rewrites them with `--force`.
  - `info` prints the algorithm, palette and effect chain of a preset without rendering.

## T23 · SVG export
- wave: 5 · deps: T17 · executor: DeepSeek · review: full · size: S
- owns: dithercraft/export/__init__.py, dithercraft/export/svg.py, tests/test_export_svg.py
- context: §19
- spec: implement §19. Horizontal run merging before emitting paths. No XML library beyond
  `xml.etree.ElementTree` or plain string building; the output must be valid XML.
- accept:
  - a 2-colour 8×8 image produces exactly 2 `<path>` elements.
  - the SVG parses with `ElementTree`, has `width`, `height` and `viewBox`.
  - `cell=4` multiplies every coordinate by 4.
  - 2048×2048 with 16 colours stays under 8 MB and finishes under 5 s.
  - rendering the SVG back to a raster at 1:1 reproduces the input indices (checked by parsing the
    rectangles, not by rasterising).

## T24 · Print export
- wave: 5 · deps: T17, T23 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/export/print.py, tests/test_export_print.py
- context: §20
- spec: implement §20. Bleed is filled with the edge colour; crop marks are drawn outside the trim
  area in black on a transparent margin. Separations are greyscale PNGs derived from the CMYK
  conversion, one per ink, named `<stem>_C.png` etc.
- accept:
  - `bleed_mm=0, crop_marks=False, separations=False` writes exactly one file and returns it.
  - `separations=True` writes five files and returns them in write order.
  - the four separation images have the input shape and are single-channel.
  - a pure-cyan input gives a non-empty C plate and empty M, Y, K plates.
  - `dpi` is written into the PNG metadata and does not change pixel dimensions.

## T25 · Animation and video
- wave: 5 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/core/animation.py, dithercraft/export/video.py, tests/test_animation.py
- context: §21
- spec: implement §21. `stable=True` anchors ordered matrices to the canvas and resolves the palette
  once on the first frame. `export_gif` uses Pillow. `export_video` shells out to ffmpeg only when
  `shutil.which("ffmpeg")` finds it, and returns `False` otherwise without raising.
- accept:
  - `render_sequence` on 5 identical frames with `stable=True` gives 5 identical outputs.
  - with `stable=False` and a `random` algorithm, consecutive frames differ.
  - the palette is resolved once: a monkeypatched `resolve_palette` is called exactly once for a
    5-frame sequence.
  - `export_gif` writes a file Pillow can reopen with the right frame count and duration.
  - `export_video` returns `False` and writes nothing when ffmpeg is absent (monkeypatched
    `shutil.which`), and never raises.

## T26 · Algorithm gallery
- wave: 6 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/gallery.py, tests/test_ui_gallery.py
- context: §22.1
- spec: implement §22.1. Thumbnails render off the GUI thread through the existing worker pattern;
  the grid shows a placeholder until a thumbnail is ready. Cache key is
  `(algorithm_id, params_hash, palette_hash)`; a stale key regenerates. Search filters by name and
  family, case-insensitive, accent-insensitive.
- accept:
  - the gallery builds offscreen with a monkeypatched registry of 3 algorithms and shows 3 cells.
  - the search box filters to the matching cell and back to all when cleared.
  - a second build with the same key reads from the cache (assert the renderer is called once).
  - a changed palette hash invalidates the cache.
  - no widget is touched from the worker thread (review check).

## T27 · Undo, shortcuts, drag and drop, recent files
- wave: 6 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/commands.py, dithercraft/ui/main_window.py, tests/test_ui_commands.py
- context: §22.2
- spec: implement §22.2. The undo stack stores immutable `PipelineSpec` snapshots, depth 50, and
  coalesces rapid slider changes within 400 ms into one entry. Recent files live in `QSettings`,
  capped at 10, missing entries pruned on load.
- accept:
  - undo/redo round-trips a spec through 5 changes and back.
  - the stack never exceeds 50 entries.
  - a burst of 10 changes within 400 ms produces one undo entry.
  - dropping a PNG on the window opens it; dropping a non-image is ignored with a status message.
  - recent files survive a window rebuild and drop entries whose file no longer exists.
  - every shortcut in §22.2 is bound and triggers its action (assert on the action, not the key).

## T28 · Localisation infrastructure and French catalogue
- wave: 6 · deps: none · executor: DeepSeek · review: strict · size: M
- owns: dithercraft/i18n/__init__.py, dithercraft/i18n/en.json, dithercraft/i18n/fr.json,
  dithercraft/ui/app.py, dithercraft/ui/param_form.py, tests/test_i18n.py
- context: §22.3
- spec: implement §22.3. `tr()` looks up the current language, falls back to English, then to the
  key itself, and formats with `**kwargs`. `set_language` rejects unknown codes with `ValueError`.
  Convert `ui/app.py` and `ui/param_form.py` fully; the remaining UI files are converted by T32.
  The French catalogue uses **tramage**, not « dithering ».
- accept:
  - `en.json` and `fr.json` have exactly the same key set (test compares the sets).
  - every value is a non-empty string; no key is left in English inside `fr.json` for the words
    listed in §22.3 (test checks a fixed list of terms).
  - `tr()` on a missing key returns the key; `tr("x", n=3)` formats `{n}`.
  - `set_language("de")` raises `ValueError`; `set_language("fr")` then `tr()` returns French.
  - `ui/app.py` and `ui/param_form.py` contain no literal user-visible string (test greps for
    `setText("`, `setWindowTitle("`, `setPlaceholderText("` with a literal argument).

## T29 · Performance and large images
- wave: 6 · deps: T17 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/worker.py, dithercraft/ui/canvas.py, tests/test_ui_worker.py
- context: §7 §9
- spec: progressive preview: render a 256 px proxy first, show it, then the 1024 px proxy, then the
  full render on demand. The worker keeps the "last one wins" rule. The canvas must not allocate a
  new QImage when the shape is unchanged. Images above 8000 px on either side are refused with a
  clear message rather than exhausting memory.
- accept:
  - a 6000×4000 image renders a preview without exceeding the memory budget (assert peak
    allocation stays under 12× the proxy size, measured with `tracemalloc`).
  - the 256 px proxy arrives before the 1024 px one (assert on the emission order).
  - 10 rapid spec changes still render only the last one.
  - an 9000 px image is refused with a message and no crash.
  - the canvas reuses its buffer when the shape is unchanged (assert on object identity).

## T30 · Pixel Snapper and descreen
- wave: 7 · deps: T17 · executor: DeepSeek · review: full · size: L
- owns: dithercraft/preprocess/__init__.py, dithercraft/preprocess/grid.py,
  dithercraft/preprocess/descreen.py, tests/test_preprocess.py
- context: §23
- spec: implement §23. `detect_grid` uses autocorrelation of the edge magnitude; confidence is the
  normalised peak height. `snap_to_grid` is nearest-neighbour onto the detected lattice.
  `descreen` notches the dominant off-centre FFT peaks and applies a light median. Both are pure
  numpy.
- accept:
  - on a synthetically upscaled 4× pixel-art image, `detect_grid` returns (4, 4, 0, 0) with
    confidence > 0.8, and `snap_to_grid` recovers the original exactly.
  - on a smooth photo, confidence is < 0.5 and the caller leaves the image untouched.
  - on a rotated halftone screen, `descreen` reduces the peak energy at the screen frequency by at
    least 80 % while keeping the mean within 2 %.
  - `descreen(strength=0)` is the identity.
  - 1×1 and 37×23 inputs do not raise.

## T31 · Bridge v2
- wave: 7 · deps: T17 · executor: DeepSeek · review: strict · size: M
- owns: dithercraft/bridge/photocraft.py, tests/test_bridge.py
- context: §8 §24
- spec: implement §24 as additions only. Every 1.0 test keeps passing unchanged. The preview-layer
  handle is per-client and cleared on `commit_preview_layer` and on disconnect. Timeouts per §24.
- accept:
  - all 1.0 bridge tests pass without modification.
  - `preview_layer` twice then `update_preview_layer` produces one layer, not three (assert on the
    recorded request sequence).
  - `commit_preview_layer` renames the layer and a following `preview_layer` creates a new one.
  - `documents()` returns the `ui.inspect` list; `render_document(1)` pulls the second document.
  - a disconnect clears the preview handle.
  - the 5 s / 60 s timeouts are applied (assert on the socket timeout argument).

## T32 · Integration and acceptance
- wave: 7 · deps: T17 to T31 · executor: DeepSeek · review: strict · size: L
- owns: dithercraft/ui/main_window.py, dithercraft/ui/algorithm_panel.py,
  dithercraft/ui/effects_panel.py, dithercraft/ui/palette_panel.py,
  tests/test_ui_integration.py, tests/manual/CHECKLIST.md
- context: §7 §9 §12 §13 §14 §15 §16 §17 §19 §20 §21 §22 §23 §24
- spec: wire everything. The algorithm panel exposes `color_metric`, `strength`, the halftone
  parameters and the conditioning strip; the palette panel exposes the library, lock and order; the
  effects panel lists `halftone_cmyk`; the toolbar gains Export SVG, Export print, Export animation,
  and a "Prepare source" toggle backed by T30. Convert the remaining UI strings through `tr()`.
  `tests/manual/CHECKLIST.md` is the H9 recipe.
- accept:
  - every new parameter is reachable from the UI and round-trips through a preset.
  - no literal user-visible string remains in `ui/*.py` (test greps as in T28).
  - the full pipeline runs from a preset loaded from disk to a PNG on disk, offscreen, in under 5 s
    for a 1024×1024 image.
  - G5 and G6 pass.
  - the checklist covers: three source types (photo, existing pixel art, scan), every export path,
    the CLI, both languages, undo/redo, and the PhotoCraft round trip.
