# DitherCraft task cards

Card fields: `wave`, `deps` (must be done), `executor`, `review` (strict | full | light), `size`
(S ≤ 150 lines, M ≤ 400, L ≤ 800 across files), `owns` (only files the task may write),
`context` (CONTRACT sections to inject verbatim), `spec`, `accept` (each item becomes a test or a review check).

Max concurrency: 4. Two tasks may run together only if their `owns` sets are disjoint (always true by design,
except T10 and T14 which share `ui/main_window.py` and are never concurrent).

---

## T00 · Environment and protocol probe
- wave: 0 · deps: none · executor: Sonnet + human (H0) · review: none (human validates) · size: S
- owns: requirements.txt, harness/STATE.md (env section), harness/CONTRACT.md (§8 TBD only)
- spec:
  1. Check whether numba and PySide6 install on the system Python (3.15.2) inside a fresh `.venv`.
     If either fails, ask the human to approve Python 3.13 via the `py` launcher, then retry.
  2. Pin exact installed versions in `requirements.txt`. `git init`, `.gitignore` (.venv, __pycache__, *.pyc, .ruff_cache).
  3. Probe the running desktop app read-only: read `instance.json`, connect to its port, call `methods`
     with candidate token transports (field in request, first-line handshake) until one succeeds. Record TBD-1.
  4. Human sets the automation read root of the desktop app to `%LOCALAPPDATA%\DitherCraft\exchange`
     (via UI preferences or documented flag). Record TBD-2.
  5. On a throwaway document in the app: `doc.place` a test PNG, try `engine.execute` with `layer.rasterize.layer`
     and a rename. Record TBD-3, TBD-4. Undo afterwards.
- accept: `.venv\Scripts\python -c "import numpy, numba, PIL, PySide6"` succeeds; four TBD entries filled
  with verified facts or "not possible"; CONTRACT version stays draft.

## T01 · Scaffold and core
- wave: 0 · deps: T00 · executor: DeepSeek · review: strict · size: L
- owns: pyproject.toml, every file in CONTRACT §2 marked T01, stub versions of every other `.py` file in §2,
  tests/conftest.py, tests/test_registry.py, tests/test_color.py
- context: §1 §2 §3 §4 §5 §10 §11
- spec: implement §3, §4, §5 and `tools/check_contract.py` exactly. Stubs contain only a module docstring
  naming the owner task (e.g. `"""Owned by T02. Error diffusion algorithms."""`) so later imports succeed.
  `algorithms/__init__.py` imports error_diffusion, ordered, misc, halftone. `effects/__init__.py` imports tone, glitch.
  `conftest.py` provides fixtures `rng` (default_rng(0)), `gradient` (64x64 horizontal grey ramp Image),
  `photo_like` (seeded smooth random 96x64 Image), `pal_bw`, `pal_4` (black, red, green, white).
- accept:
  - resolve_params: defaults filled, clamping, int cast, ValueError on unknown key and bad choice.
  - duplicate registration raises ValueError; list_algorithms order is family then name.
  - to_float on RGBA (0,0,0,0) pixel gives white; to_rgb8(to_float(x)) round-trips uint8 exactly.
  - nearest_index on pal_bw: values < 0.5 → 0, > 0.5 → 1; chunking gives same result as unchunked on 300x300.
  - downscale/upscale_nearest round trip keeps shape for non-divisible sizes (e.g. 37x23, factor 4).
  - adjust(0, 0, 1) is identity within 1e-6.
  - check_contract.py exits 0 with empty registries and with one dummy algorithm registered in a test.

## T02 · Error diffusion algorithms
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/algorithms/error_diffusion.py, tests/test_error_diffusion.py
- context: §3 §4 §5 §10
- spec: one generic numba kernel `_diffuse(img, palette, offsets, weights, serpentine, strength) -> Indices`
  driven by data tables. Error is computed per RGB channel against the chosen palette color, on a float32 working copy.
  Serpentine: odd rows run right to left with dx mirrored. Params for all: `serpentine` (bool, True),
  `strength` (float 0..1, 1.0). Register (id, divisor, entries as (dx, dy, weight)):
  - floyd_steinberg /16: (1,0,7) (-1,1,3) (0,1,5) (1,1,1)
  - false_floyd_steinberg /8: (1,0,3) (0,1,3) (1,1,2)
  - jarvis_judice_ninke /48: (1,0,7) (2,0,5) (-2,1,3) (-1,1,5) (0,1,7) (1,1,5) (2,1,3) (-2,2,1) (-1,2,3) (0,2,5) (1,2,3) (2,2,1)
  - stucki /42: (1,0,8) (2,0,4) (-2,1,2) (-1,1,4) (0,1,8) (1,1,4) (2,1,2) (-2,2,1) (-1,2,2) (0,2,4) (1,2,2) (2,2,1)
  - burkes /32: (1,0,8) (2,0,4) (-2,1,2) (-1,1,4) (0,1,8) (1,1,4) (2,1,2)
  - sierra /32: (1,0,5) (2,0,3) (-2,1,2) (-1,1,4) (0,1,5) (1,1,4) (2,1,2) (-1,2,2) (0,2,3) (1,2,2)
  - sierra_two_row /16: (1,0,4) (2,0,3) (-2,1,1) (-1,1,2) (0,1,3) (1,1,2) (2,1,1)
  - sierra_lite /4: (1,0,2) (-1,1,1) (0,1,1)
  - atkinson /8: (1,0,1) (2,0,1) (-1,1,1) (0,1,1) (1,1,1) (0,2,1)   (weights sum to 6/8 on purpose)
  - stevenson_arce /200: (2,0,32) (-3,1,12) (-1,1,26) (1,1,30) (3,1,16) (-2,2,12) (0,2,26) (2,2,12) (-3,3,5) (-1,3,12) (1,3,12) (3,3,5)
  Do not add other kernels.
- accept:
  - weight sums: all 1.0 except atkinson 0.75 (test reads the tables).
  - black image → all index of black; white → all index of white (pal_bw).
  - 64x64 grey 0.5 with pal_bw: white fraction in [0.48, 0.52] for each kernel ([0.45, 0.55] for atkinson).
  - serpentine True and False give different outputs on `gradient`; strength 0 equals nearest_index.
  - `perf` test: floyd_steinberg on 1024x1024, K=16 under 0.5 s after warm-up (informative).

## T03 · Ordered dithering
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/algorithms/ordered.py, tools/gen_blue_noise.py, data/blue_noise_64.npy, tests/test_ordered.py
- context: §3 §4 §5 §10
- spec: threshold matrix M (n x n) of ranks 0..n²-1 normalized to t = (rank + 0.5) / n², tiled over the image.
  Color rule: `amplitude = spread / max(1, round(K ** (1/3)) - 1)`; `value = img + (t - 0.5) * amplitude`
  on all channels; then `nearest_index`. Pure numpy, no numba.
  Params: `spread` (float 0..2, 1.0), `matrix_scale` (int 1..8, 1: each matrix cell repeated scale x scale).
  Register: bayer_2, bayer_4, bayer_8, bayer_16 (recursive Bayer construction); cluster_dot_4, cluster_dot_8
  (ranks by distance to cell center, ties broken by angle `atan2`, ascending); blue_noise (loads
  `data/blue_noise_64.npy`, cached at module level); lines_horizontal, lines_vertical, lines_diagonal
  (t from `y mod 4`, `x mod 4`, `(x + y) mod 4`).
  `tools/gen_blue_noise.py`: void-and-cluster (Ulichney), Gaussian sigma 1.5, toroidal, seed 0, writes a
  64x64 int32 rank array; must finish under 120 s. The `.npy` is committed; runtime never regenerates it.
- accept:
  - every matrix is a permutation of 0..n²-1; bayer_2 equals [[0,2],[3,1]].
  - 64x64 grey 0.5, pal_bw, bayer_4: white fraction exactly 0.5.
  - blue_noise file shape (64, 64), permutation of 0..4095.
  - matrix_scale 2 on bayer_2 equals bayer_2 with each cell repeated 2x2.

## T04 · Misc and halftone algorithms
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/algorithms/misc.py, dithercraft/algorithms/halftone.py, tests/test_misc.py, tests/test_halftone.py
- context: §3 §4 §5 §10
- spec (misc.py, family "other"):
  - threshold: param `level` (float 0..1, 0.5). Binary between darkest and lightest palette colors
    (by luminance): luminance < level → darkest index, else lightest.
  - random: white noise added as in T03 with uniform t; params `spread`, `seed`.
  - riemersma: Hilbert curve traversal (curve order covering max(H, W), skip out-of-bounds cells),
    error history of `history` (int 4..64, 16) entries with weights `ratio ** (i / (history - 1))`,
    `ratio` (float 0.01..0.5, 1/16), normalized to sum 1. numba allowed.
- spec (halftone.py, family "halftone"): binary between darkest and lightest palette colors.
  Cells of `cell_size` (int 3..64, 8) on a grid rotated by `angle` (float 0..90, 45). Per cell, mean luminance L.
  A pixel is dark when its spot function value < (1 - L). Register halftone_dots (spot = normalized distance to
  cell center, round), halftone_squares (Chebyshev distance), halftone_lines (distance to the cell's center line).
  Vectorized numpy.
- accept: threshold monotonic in level; riemersma 64x64 grey 0.5 pal_bw white fraction in [0.45, 0.55];
  random deterministic with same seed, different with another; halftone on black gives all dark, on white all light;
  halftone_dots angle 0 vs 45 differ; dark fraction grows as luminance decreases (3 levels).

## T05 · Built-in palettes and palette IO
- wave: 1 · deps: T01 · executor: DeepSeek · review: light · size: S
- owns: dithercraft/palettes/builtin.py, dithercraft/palettes/io.py, tests/test_palettes_io.py
- context: §3 §6 §10
- spec: BUILTIN contains exactly these entries (hex given; do not invent others):
  - bw: 000000 FFFFFF
  - gameboy: 0F380F 306230 8BAC0F 9BBC0F
  - cga_0_high: 000000 55FF55 FF5555 FFFF55
  - cga_1_high: 000000 55FFFF FF55FF FFFFFF
  - ega: 000000 0000AA 00AA00 00AAAA AA0000 AA00AA AA5500 AAAAAA 555555 5555FF 55FF55 55FFFF FF5555 FF55FF FFFF55 FFFFFF
  - pico8: 000000 1D2B53 7E2553 008751 AB5236 5F574F C2C3C7 FFF1E8 FF004D FFA300 FFEC27 00E436 29ADFF 83769C FF77A8 FFCCAA
  - grey_4, grey_8, grey_16: evenly spaced greys from black to white (generated)
  - rgb_8: the 8 corners of the RGB cube
  - cmyk_5: FFFFFF 00FFFF FF00FF FFFF00 000000
- accept: counts (2, 4, 4, 4, 16, 16, 4, 8, 16, 8, 5); .hex and .gpl round trip exactly; parser tolerates `#`,
  blank lines, comments, CRLF; malformed line → ValueError mentioning the line number.

## T06 · Palette extraction
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: S
- owns: dithercraft/palettes/extract.py, tests/test_extract.py
- context: §3 §5 §6 §10
- spec: as §6. median_cut: recursive split on the channel with largest range, at the median, until k boxes; color = box mean.
- accept: image made of exactly 4 flat colors, k=4 → those 4 colors within 1/255 (both methods); single-color image
  → K=2; output sorted by luminance; same seed gives same result; 2000x2000 image under 2 s.

## T07A · Tone effects
- wave: 1 · deps: T01 · executor: DeepSeek · review: light · size: M
- owns: dithercraft/effects/tone.py, tests/test_effects_tone.py
- context: §3 §4 §10
- spec: private helper `_gaussian_blur(img, sigma)` (separable, numpy only, kernel radius ceil(3 sigma), edge replicate).
  Register: gaussian_blur (`radius` 0..50 → sigma = radius / 3), sharpen (unsharp: `amount` 0..3 = 1.0, `radius` 0.5..10 = 1.5),
  glow (`threshold` 0..1 = 0.7, `radius` 1..50 = 10, `intensity` 0..3 = 1.0; bright-pass, blur, screen blend),
  noise (`amount` 0..1 = 0.1, `monochrome` bool True, gaussian), posterize (`levels` int 2..32 = 4).
- accept: radius 0 blur is identity; blur preserves mean of a random image within 1e-3; glow never darkens any pixel;
  posterize output has ≤ levels unique values per channel; all outputs float32 in [0, 1].

## T07B · Glitch effects
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/effects/glitch.py, tests/test_effects_glitch.py
- context: §3 §4 §10
- spec: register chromatic_aberration (`amount` px 0..50 = 4, radial: R scaled outward, B inward from center,
  bilinear sampling), rgb_shift (`r_x`, `r_y`, `b_x`, `b_y` int -100..100, wrap off, edge replicate),
  jpeg_glitch (`quality` int 1..95 = 20, `corruptions` int 0..50 = 5: encode with Pillow, overwrite random bytes after
  the SOS marker using rng, decode; on decode failure retry with half the corruptions; at 0, return the clean JPEG
  round trip; never raise), scanlines (`spacing` int 2..16 = 3, `thickness` int 1..8 = 1, `darkness` 0..1 = 0.5).
- accept: amount 0 / zero shifts / darkness 0 are identities (jpeg excepted); jpeg_glitch never raises across
  50 seeds; output shapes equal input including 1x1; same rng seed gives identical output.

## T08 · PhotoCraft bridge
- wave: 1 · deps: T00, T01 · executor: DeepSeek · review: strict · size: M
- owns: dithercraft/bridge/photocraft.py, tests/test_bridge.py, tools/smoke_photocraft.py
- context: §8 (including §8.6) §10
- spec: as §8, using the TBD facts recorded by T00. JSON lines over TCP, UTF-8, read until newline,
  ids incrementing. pid liveness check with `ctypes` (`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` +
  `GetExitCodeProcess` == STILL_ACTIVE, then `CloseHandle`). **Never call `os.kill` on Windows: it terminates
  the process.** No psutil. Every failure path raises BridgeError with a readable message.
- accept (fake desktop server in test, requires auth as first request): discover returns None for missing or empty token
  file, closed port, refused auth (instance.json is never read); every connection sends `auth` first; render_document follows §8.3 (relative `/` path,
  reads then deletes the PNG); place_as_layer follows §8.4 step order exactly (assert the recorded request sequence);
  a failure at step 3 still closes the helper and reactivates the target; error response → BridgeError with the
  server message; old exchange files are cleaned (EXCHANGE_DIR monkeypatched to tmp_path); timeout → BridgeError.
- accept (§8.6): installed_photocraft_version parses "photocraft-cli 0.22.0 (5000240c6, 2026-11-09)" to "0.22.0"
  (subprocess monkeypatched), returns None on missing file, non-zero exit, timeout, unparsable output; version_status
  covers the three cases. smoke_photocraft.py imports cleanly and its `--help` runs without touching the app (review
  checks the step order and that cleanup runs in a `finally`).
- deps note: §8 verified on the user's instance by P00 (2026-11-10); no remaining PROBE tags.

## T09 · Pipeline and presets
- wave: 1 (highest priority, critical path) · deps: T01 · executor: DeepSeek · review: strict · size: M
- owns: dithercraft/core/pipeline.py, dithercraft/core/presets.py, tests/test_pipeline.py, tests/test_presets.py
- context: §3 §4 §5 §6 §7 §10
- spec: as §7. Tests must not depend on T02 to T07B: register test-only algorithms and effects (ids prefixed
  `test_`) by monkeypatching the registry dicts in fixtures; do not edit registry.py.
  `resolve_palette` for "builtin" imports palettes.builtin lazily; if T05 is not done, tests use "custom" palettes only.
- accept: output dtype/shape for pixel_size 1, 3, 7 on 37x23; max_side reduces shape; disabled effects skipped;
  effect order matters (two non-commuting test effects); same spec same output; JSON round trip equality;
  unknown algorithm id in JSON → ValueError naming it; missing keys → defaults.

## T10 · UI shell and preview canvas
- wave: 1 · deps: T01 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/app.py, dithercraft/ui/main_window.py, dithercraft/ui/canvas.py, dithercraft/ui/param_form.py,
  tests/test_ui_canvas.py, tests/test_ui_param_form.py
- context: §3 §9 §10
- spec: `app.main()` creates QApplication, Fusion style, dark palette, MainWindow. MainWindow: toolbar actions
  (§9) created but connected to placeholder slots that log; right QDockWidget with QTabWidget holding three
  placeholder QLabel tabs named Algorithm, Palette, Effects; status bar. PreviewCanvas and ParamForm per §9.
  Tests use `QT_QPA_PLATFORM=offscreen`.
- accept: window builds offscreen; set_image accepts 1x1 and 4000x3000; split mode shows both halves;
  zoom 400 % keeps pixels sharp (transformation mode Fast); ParamForm builds one widget per kind, values()
  returns defaults, set_values does not emit changed, clamps out-of-range values.

## T11 · Algorithm panel
- wave: 2 · deps: T09, T10 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/algorithm_panel.py, tests/test_ui_algorithm.py
- context: §3 §4 §7 §9 §10 + public signatures of ui/param_form.py
- spec: uses ParamForm from T10. AlgorithmPanel: algorithm combo grouped by family (separators), ParamForm rebuilt on
  change, pixel_size spinbox, brightness/contrast/gamma sliders, Reset button. Implements panel interface.
- accept: load_from then apply_to round-trips a spec; changed not emitted during load_from; switching algorithm
  resets params to defaults; works with a monkeypatched registry of two fake algorithms.

## T12 · Effects panel
- wave: 2 · deps: T09, T10 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/effects_panel.py, tests/test_ui_effects.py
- context: §3 §4 §7 §9 §10 + public signatures of ui/param_form.py
- spec: uses ParamForm from T10. Two QListWidgets (Before dither, After dither) with internal drag-and-drop reorder, item checkbox =
  enabled, Add (menu from list_effects), Remove, Duplicate; selecting an item shows its ParamForm below.
- accept: reorder reflected in apply_to; disabling keeps the item; round trip of a spec with 3 pre and 2 post effects.

## T13 · Palette panel
- wave: 2 · deps: T05, T06, T09, T10 · executor: DeepSeek · review: full · size: M
- owns: dithercraft/ui/palette_panel.py, tests/test_ui_palette.py
- context: §3 §6 §7 §9 §10
- spec: source radio (Built-in, Extracted, Custom); built-in combo with swatch preview; extract controls (k, method,
  Extract button that needs `set_source_image(img)`, then switches to Custom with the extracted colors);
  swatch grid (click = QColorDialog, right click = remove, + = add, max 256); Import / Export (.hex, .gpl).
- accept: round trip of each source type; extraction result appears as custom colors; K < 2 prevented.

## T14 · Integration and live preview
- wave: 3 · deps: T02 to T13 · executor: DeepSeek · review: strict · size: L
- owns: dithercraft/ui/main_window.py, dithercraft/ui/worker.py, tests/test_ui_integration.py
- context: §7 §8.5 §8.6 §9 §10 + public signatures of all ui/*.py and bridge/photocraft.py
- spec: replace placeholders with the 3 panels; MainWindow owns the PipelineSpec; any panel `changed` →
  rebuild spec → worker. Worker per §9. Actions: Open image (PIL), Get from PhotoCraft, Send to PhotoCraft
  (full-res render then place_as_layer, progress in status bar), Export PNG, Load/Save preset (`presets/` default dir).
  Connection indicator refreshed every 3 s via `discover()` in the worker, never in GUI thread. Errors → QMessageBox.
  Remember last preset dir and window geometry with QSettings. At startup, call `version_status()` in the worker
  and apply the §8.6 UI rule (non-blocking status-bar warning when "untested").
- accept: offscreen test: load image, change algorithm, preview updated within 2 s; stale jobs dropped (10 rapid
  changes → last spec rendered); Send with a fake bridge places one PNG; no widget access from worker (review check); with version_status monkeypatched to "untested" the warning appears
  once, with "unknown" nothing appears.

## T15 · Packaging and shortcuts
- wave: 3 · deps: T14 · executor: DeepSeek · review: light · human: H3 before running the script · size: S
- owns: DitherCraft.pyw, tools/make_icon.py, assets/dithercraft.ico, scripts/install_shortcuts.ps1
- spec: `.pyw` adds project root to sys.path and calls `dithercraft.ui.app.main()`. Icon: 256 px Bayer pattern
  generated by Pillow. PowerShell script (UTF-8 BOM, `-Encoding utf8`) creates Desktop and Start Menu shortcuts
  via WScript.Shell targeting `.venv\Scripts\pythonw.exe "<root>\DitherCraft.pyw"`, idempotent, `-Uninstall` switch.
  Do not create a PhotoCraft shortcut: "PhotoCraft (DitherCraft)" already exists on the Desktop (P00). The script only
  checks it exists and warns if missing.
- accept: script dry-run mode (`-WhatIf`) prints the two target paths; nothing written outside the two shortcut locations.

## T16 · Acceptance in PhotoCraft
- wave: 3 · deps: T15 · executor: human (H4) + Sonnet triage · size: n/a
- owns: tests/manual/CHECKLIST.md, bug reports appended to DEVIATIONS.md (class E4)
- checklist: launch from shortcut; connection indicator green with PhotoCraft open, red when closed; Get from
  PhotoCraft on a 4000 px photo; every algorithm visibly works; live preview stays fluid; extract palette;
  stack 3 effects and reorder; save and reload preset; Send creates a new layer above, original untouched;
  Export PNG; accents in file paths (e.g. `C:\Users\marin\Images\été.png`).
- Each failure becomes a new task card T16-x (S size, DeepSeek, review full), generated by the orchestrator.
