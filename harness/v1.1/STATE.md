# Project state — harness 1.1 (updated by the orchestrator only)

contract_version: 1.1.0 (frozen at H5, 2026-11-12)
base_contract: 1.0.0 (harness/CONTRACT.md, §1 to §11, frozen)
max_concurrency: 4
last_update: 2026-11-12

## Environment (inherited from 1.0, unchanged)

- python: 3.15.2 · numpy 2.5.4 · numba 0.68.1 · Pillow 13.0.0 · PySide6 6.12.0 · pytest 9.2.0 · ruff 0.17.4
- venv: `.venv` at the project root. No new dependency in 1.1.
- ffmpeg: provided by the `imageio-ffmpeg==0.8.1` dependency, which ships ffmpeg 9.0.2 (essentials
  build) inside its wheel. A system ffmpeg on `PATH` is the fallback. The video export returns
  `False` when neither is available.
- Baseline before 1.1: 622 tests green, ruff clean, check_contract OK, commit `5e3c2dd`.

## Task table

| Task | Wave | Status | g | r | Commit | Notes |
|---|---|---|---|---|---|---|
| T17 | 4 | done | 0 | 0 | 502ea80 | spec v2, preset v2, conditioning; G5 green |
| T18 | 4 | done | 0 | 0 | 3f5fbad | colour metrics; DEV-102 wired |
| T19 | 4 | done | 0 | 0 | d7c0624 | strength on all 33 algorithms |
| T20 | 4 | done | 0 | 0 | 3faf7fb | halftone v2 + CMYK effect |
| T21 | 4 | done | 0 | 0 | 87badc4 | library, hex import, lock, reorder; DEV-101 resolved |
| T22 | 5 | done | 0 | 0 | 452da4e | CLI + batch; G6 green |
| T23 | 5 | done | 0 | 0 | | SVG export; DEV-106 on the size budget |
| T24 | 5 | done | 0 | 0 | | print export, bleed, crop marks, separations |
| T25 | 5 | done | 0 | 0 | | animation + video; DEV-107 adds imageio-ffmpeg |
| T26 | 6 | done | 0 | 0 | afc9dbc | algorithm gallery, off-thread thumbnails |
| T27 | 6 | done | 0 | 0 | ad4ddc1 | undo, shortcuts, drag and drop, recent files |
| T28 | 6 | done | 0 | 0 | 28232e5 | i18n + French catalogue, 160 keys |
| T29 | 6 | done | 0 | 0 | 76fc68f | progressive preview, 8000 px guard |
| T30 | 7 | todo | 0 | 0 | | Pixel Snapper + descreen |
| T31 | 7 | todo | 0 | 0 | | bridge v2 |
| T32 | 7 | todo | 0 | 0 | | integration + acceptance |
| T33 | 6 | done | 0 | 0 | 939d0b5 | export dialog + CLI subcommands |
| T34 | 6 | done | 0 | 0 | 1182a55 | preset search order, two tiers |

`g` = gate retries used (max 3), `r` = review cycles used (max 2).

## Decisions log

- 2026-11-11: harness 1.1 opened. Scope chosen from the market research in
  `docs/market-research.md`: output quality first, then workflow coverage, then ergonomics, then
  robustness on real sources.
- 2026-11-11: the 1.0 contract stays frozen and in force for §1 to §11. 1.1 is a delta, not a
  rewrite, so no 1.0 task is reopened.
- 2026-11-11: CMYK halftone is an **effect**, not an algorithm, because it produces ink coverage
  rather than palette indices. Recorded in §15.2 so no coder has to invent it.
- 2026-11-11: no new dependency in 1.1. ffmpeg is optional and detected at runtime; palette import
  is file-based or pasted hex, never network in the core. **Amended on 2026-11-12 by DEV-107:**
  `imageio-ffmpeg` is now a dependency, so ffmpeg ships with the project instead of being an
  undeclared system step. The palette rule is unchanged.
- 2026-11-11: two new gates, G5 (v1 preset compatibility) and G6 (CLI/GUI parity), because 1.1
  touches the pipeline and adds a second render path. Both are gates, not informative tests.
- 2026-11-11: the project name is not changed in 1.1. Decision deferred by the user; it has no code
  impact.
- 2026-11-12: **the harness 1.1 is executed before the Lattice harness 0.1**, by human decision. The
  Lattice contract inherits §12 and §13, so those sections must exist in code before `lattice-core`
  is extracted. Lattice's L1 to L22 wait.
- 2026-11-12: the environment was rebuilt from scratch (`.venv`, Python 3.13.18, the pinned
  requirements). The baseline was **620 passed, 2 failed**, not the 622 the harness claimed. Both
  failures were test-harness defects, not product defects: the fake PhotoCraft server's accept loop
  died after 20 ms because `socket.timeout` is an `OSError`, and the smoke test decoded the child's
  locale-encoded stdout as UTF-8. Fixed in `f8ab012`; the baseline is now genuinely 622.
- 2026-11-12: the three witness baselines were rendered from the committed `source.png`, not from
  the float image `tools/contact_sheet.py` produces. Rendering from the float image made the
  baselines unreproducible from the repository alone.
- 2026-11-12: T17's `owns` was extended to `core/color.py` and `tests/test_ui_algorithm.py`
  (AMD-102). Three deviations opened: DEV-101 (`locked` has no colour source), DEV-102
  (`color_metric` has no path to the algorithms), DEV-103 (the positive saturation formula is
  undefined).
- 2026-11-12: **DEV-102 is resolved.** The pipeline converts the image and the palette to the
  metric's working space once, then injects the metric code into `params["_color_metric"]` after
  `resolve_params`. The reserved key cannot collide with a `ParamSpec` id, and the algorithm
  signature stays `fn(img, palette, params)`. Algorithms read it through `metric_of(params)`.
- 2026-11-12: CIEDE2000 was verified exact against all 34 Sharma et al. reference pairs (worst
  error 4.95e-05). Measured cost for a 1024² image at K=16: srgb 191 ms, linear 223 ms, oklab
  291 ms, lab2000 1498 ms. All four miss the 150 ms budget of §12; the perf test is informative,
  not a gate, and the 33³ LUT that would fix it is deferred to T29.
- 2026-11-12: T19's `owns` was extended to `algorithms/_strength.py` and the four algorithm test
  files (AMD-103). The `strength=1` invariant is checked against digests captured from a worktree
  at `3f5fbad`, not against a re-derivation, so the test proves the output did not move.
- 2026-11-12: the per-family `strength` semantics of §14 cannot all be satisfied literally. A
  halftone spot threshold scaled to 0.5 yields two colours, not K, so `strength=0` would not equal
  `nearest_index`. Halftone, yliluoma and dbs therefore blend in colour space toward the
  nearest-colour map (DEV-104).
- 2026-11-12: T20 keeps one default `dot_shape` per algorithm (`round`, `square`, `line`) instead of
  the single `"round"` the §15.1 block shows. With a shared default the three algorithms would
  render identically at their defaults, and the witness preset `04_halftone_print` would change
  (DEV-105).
- 2026-11-12: `effects/halftone.py` imports `coverage` and `spot_function` from
  `algorithms/halftone.py` rather than duplicating the six spot functions. The dependency runs one
  way only, effects on algorithms, so there is no import cycle.
- 2026-11-12: the §15.1 accept item "4 is smoother (lower variance inside a cell)" is measured on
  the coverage map, not on the binary index map. A one-bit output cannot be smoother than one bit
  per pixel; what oversampling actually smooths is the coverage, whose variance drops for all six
  shapes on both a flat and a gradient image.
- 2026-11-12: T22's `owns` was extended to nothing: the card's three files were enough. `batch`
  always writes PNG whatever the input extension, because a JPEG output would be lossy and G6
  compares bytes. `--ext` filters the inputs only.
- 2026-11-12: argparse exits 2 on a usage error, but §17 reserves 2 for an input error and gives 1
  to usage. The parser is subclassed so `error` exits 1, and `main` returns the code rather than
  letting `SystemExit` escape, which also makes the exit codes testable in-process.
- 2026-11-12: T21 shipped twelve library palettes: `vga16`, `tango`, `web_safe` (public domain or
  factual) and `solarized_dark`, `solarized_light`, `nord`, `gruvbox_dark`, `dracula`,
  `catppuccin_mocha`, `one_dark`, `tokyo_night`, `rose_pine` (MIT). The artist pixel-art palettes
  and the console palettes were left out: their licence is not stated, or their values are emulator
  approximations rather than published data. `palettes/data/NOTICE.md` records the MIT text and the
  exclusions.
- 2026-11-12: the library hex values were transcribed from each project's published palette. The
  tests check the structure of every file, not the exact colours; a maintainer should diff them
  against upstream before a release.
- 2026-11-12: T21's sixth accept item, "locked swatches survive extraction unchanged", was **not**
  implemented at first. DEV-101 was open: the contract never said which palette a `locked` index
  pointed into. The panel stored, serialised, round-tripped and displayed the lock, so the field was
  usable as soon as the decision landed; only the seeding was missing.
- 2026-11-12: **DEV-101 is resolved.** `PaletteSpec.locked` is a `list[str]` of `#RRGGBB` colours,
  seeded at the front of the extraction result. Indices into the UI palette were rejected because
  the render would then depend on hidden UI state, so the same preset would render differently
  depending on what was on screen before, and the lock would silently do nothing in the CLI.
  Indices into `PaletteSpec.colors` were rejected as coherent but useless, since `colors` is empty
  or stale in the extracted workflow. §16 was amended in place with no version bump: no shipped
  preset used `locked`, so there is nothing to migrate. `extract_k - len(locked)` colours are
  extracted, never fewer than `MIN_K`; `len(locked) == extract_k` skips extraction entirely;
  duplicate locked colours collapse to one slot. The panel now keys the lock on the colour, so
  removing one of two identical swatches keeps the colour locked and recolouring a locked swatch
  moves the lock to the new colour.
- 2026-11-12: reordering permutes `PaletteSpec.order` and leaves the colours in natural order, so
  the rendered image is byte-identical before and after. The panel resets `order` when the palette
  changes size, because a permutation of the old size would fail `_validate_order`.
- 2026-11-12: T23 emits a run as `M x y h w v cell` and relies on the fill rule to close the
  subpath, so a rectangle costs nine bytes instead of the twelve a `z` and a return leg would add.
  The `viewBox` uses the same multiplied space as the coordinates, which is the only reading that
  satisfies both "`cell` multiplies every coordinate" and "`width`/`height` in pixels".
- 2026-11-12: **DEV-106 is opened.** §19's 8 MB budget for 2048×2048 at 16 colours is met on flat
  artwork (0.49 MB) but not on a dithered render (46.45 MB), because the size follows the number of
  runs, not the number of colours. The budget test is measured on flat content and the contract
  needs to name its reference content.
- 2026-11-12: T24 builds the canvas in three concentric areas, trim then bleed then a 3 mm
  transparent margin, and draws the crop marks in the margin only, so they never touch the bleed or
  the trim. The main PNG is RGB without crop marks and RGBA with them, because the margin is
  transparent. The bleed is `np.pad(mode="edge")`, which is the literal reading of "filled with the
  edge colour".
- 2026-11-12: the separations reuse `effects.halftone.plates` at full black pullout rather than
  duplicating the CMYK formula, so the codebase keeps one definition of the conversion. Full pullout
  is the textbook one: a neutral grey lands entirely on the K plate, which is what a printer expects
  from a separation. A plate is written with 255 meaning full ink, so "empty" is an all-zero array.
- 2026-11-12: `dpi` is stored through Pillow's `dpi=` argument and reads back as 299.9994 at 300 dpi,
  because PNG stores pixels per metre as an integer. The tests compare with a tolerance rather than
  for equality.
- 2026-11-12: T25 needed the palette resolved outside `render`, so `render` was split into
  `_prepare` (steps 1 to 5) and `_finish` (steps 6 to 11) and two public wrappers were added,
  `prepare_image` and `render_with_palette`. `render`'s signature is unchanged, as §7 pins it, and
  G5 and G6 prove the output did not move.
- 2026-11-12: §21 lists three properties for `stable=True`: ordered matrices anchored to the canvas,
  the palette resolved once, and no error carried between frames. The first and the third are
  structural in 1.1 and hold in both modes, because the ordered matrices are indexed by pixel
  coordinates and every frame is rendered from scratch. `stable` therefore controls the palette
  only: once for the sequence, or once per frame. The seed belongs to the spec, not to the frame, so
  two identical frames still render identically with `stable=False`; the card's "consecutive frames
  differ" is met with moving frames, which is the literal reading.
- 2026-11-12: Pillow's GIF writer merges consecutive identical frames into one with a longer
  duration, so the frame-count test uses distinct frames. GIF stores the delay in centiseconds, so
  12 fps lands on 80 ms rather than 83; the tests pin both 10 fps (exact) and 12 fps (rounded).
- 2026-11-12: ffmpeg 9.0.2 (Gyan full build) was installed through winget, so both paths of
  `export_video` are now exercised. The success path is checked with `ffprobe`: h264, the frame
  dimensions and the requested rate all come back as written. The two tests skip themselves when
  ffmpeg or ffprobe is missing, so the suite stays green on a machine without them.
- 2026-11-12: **DEV-107 is resolved, by human decision.** `imageio-ffmpeg==0.8.1` becomes a project
  dependency, so `pip install -r requirements.txt` is the whole install and the video export no
  longer depends on an undeclared system step. The wheel is 38.9 MB and carries ffmpeg 9.0.2
  (essentials build, 105 MB unpacked). `export_video` resolves through
  `imageio_ffmpeg.get_ffmpeg_exe()` and falls back to `shutil.which`, so a system ffmpeg still
  works. The PyInstaller script gained `--hidden-import` and `--collect-data` for the package,
  because the import is lazy and static analysis would miss it. PhotoCraft stays an integration:
  it is a separate application, detected at runtime, never a dependency.
- 2026-11-12: **DEV-108 is resolved, by human decision.** The separation plates cover the trim only,
  without the bleed and without the crop-mark margin, so they are smaller than the print PNG. The
  reading is recorded rather than implemented because the print export targets digital art, where it
  is a convenience for a poster or a zine, not a prepress workflow. A consequence worth knowing: a
  render whose palette has no colour with green below its maximum produces an all-zero M plate,
  which is correct and reads as black in a greyscale viewer.
- 2026-11-12: **H5 review opened four decisions, all taken by the human.** §19's budget is measured
  on a dithered render and rises to 50 MB, because a budget measured on flat artwork would not
  protect the output the default pipeline produces. §14's colour-space blend becomes the normative
  definition of `strength` for halftone, yliluoma and dbs, so the `strength = 0` invariant holds for
  all 33 algorithms. §13's multiplicative saturation is written in for the whole range [-1, 1], and
  §15.1's per-algorithm `dot_shape` defaults are written in. DEV-103, DEV-104, DEV-105 and DEV-106
  are resolved, so no deviation is open.
- 2026-11-12: the H5 review also found two clauses with no card behind them. The four exports were
  reachable from neither `ui/` nor `cli.py`; T32 was to add the toolbar buttons but nothing specified
  the dialog or the CLI side, so T33 now owns the export surface. §18's two-tier preset search order
  was not implemented at all, so T34 owns it. §18 and §22.1 also still named `DitherCraft` for the data
  directories; they now name `LatticeDither`, matching the code, with the bridge keeping its legacy
  fallback.
- 2026-11-12: **H5 is done and CONTRACT 1.1.0 is frozen.** The version drops the `-draft` suffix and
  the document is normative as it stands. From here a change is a version bump, not an edit: PATCH
  for a clarification, MINOR for an addition, MAJOR only with human approval. The header's section
  range was corrected to §12 to §25, since §25 (the gates) is part of this document.
- 2026-11-12: **wave 6 is complete**, run as two parallel batches because two cards shared a file.
  Batch A was T28, T29, T33 and T34; batch B was T26 and T27, which needed T29's worker and T34's
  `main_window.py` in place first. T27 and T34 both own `main_window.py`, so they could not overlap.
- 2026-11-12: T28 keys the catalogue on the English source string, gettext style, so a missing key
  falls back to readable text rather than a dotted id. The catalogue is deliberately wider than the
  two files the card converts (160 keys), because T32 does not own the JSON and could not add keys.
  The grep test runs four detectors with positive and negative controls; six mutations were applied
  and caught.
- 2026-11-12: T29 renders each preview stage from a cached proxy rather than from the source, so a
  large image never reaches the pipeline at full resolution: a 6000×4000 preview peaks at 45.5 MB
  instead of 296 MB. The card's "12× the proxy size" is undefined; the proxy's float32 working
  footprint is used, and a second assertion (`peak < source.nbytes / 4`) proves independence from
  source size. The stricter uint8 reading is unreachable, because one float32 pass in
  `pipeline._prepare` already peaks at 24 MB.
- 2026-11-12: T33's `export-anim` takes a directory of frames or a single image, and the output
  suffix picks the writer. A missing ffmpeg exits 3, not 2: the input was fine, the export did not
  happen. Out-of-range options exit 1, matching §17's usage/input split.
- 2026-11-12: T34 redirects any save target inside the shipped tier to the user tier, so the shipped
  directory is unreachable for writes in every case. A path the user explicitly picks outside both
  tiers is honoured, which is the 1.0 behaviour. The user directory is created when the save dialog
  opens, so a fresh install opens inside it.
- 2026-11-12: T26 holds its thumbnail worker in a module-level set until the thread finishes,
  mirroring `_ACTIVE_EXTRACTIONS` in `worker.py`. Dropping the last reference before the thread
  stopped caused an intermittent access violation in `shutdown()`, one run in eight.
- 2026-11-12: T27 binds `Ctrl+E` to T33's dialog and exports the last rendered preview rather than
  starting a fresh full-resolution render, which would freeze the UI. For sources at or below
  1024 px the preview is full resolution. `Left`/`Right` stay on the preset event filter: binding
  them as action shortcuts would double-step and steal the arrows from a focused spin box.
- 2026-11-12: the i18n JSON is data, not a module, so the frozen exe would have raised
  `FileNotFoundError` at startup. `scripts/build_exe.ps1` now collects `lattice_dither.i18n`. The
  `.spec` is a build artifact and is gitignored, so the script is the durable fix.

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H5 | after T17 | done — CONTRACT 1.1.0 frozen on 2026-11-12 |
| H6 | after wave 4 | pending — judge output on three real images |
| H7 | after wave 5 | pending — run the CLI and the print export |
| H8 | after wave 6 | in progress — DEV-109 found and fixed |
| H9 | T32 | pending — acceptance in PhotoCraft |

## Next

- NEXT: wave 6 is complete. Wave 7 opens with T30 (Pixel Snapper and descreen), then T31 (bridge v2),
  then T32 (integration and acceptance).
- No deviation is open. DEV-101 and DEV-103 to DEV-108 are all resolved, so nothing blocks a task.
- H6 (judge output on three real images) can now be taken: T17 to T21 are in, so conditioning,
  colour metrics, strength, both halftones and the palette library are usable from the GUI.
- H7 (run the CLI and the print export) is ready and now reachable by a user: T33 added the export
  dialog and the three CLI subcommands, so the SVG, print, GIF and video exports no longer need
  Python.
- H8 (use it for a week) can start now that wave 6 is in: the gallery, undo, shortcuts, drag and
  drop, recent files, both languages and the export surface are all wired.
- T32 must convert the remaining `ui/` files through `tr()` and add `export_dialog.py`, `gallery.py`
  and `commands.py` to its literal-string check. The catalogue already holds every key those three
  files use.
- T32 must also expose `color_metric` in the algorithm panel. H8 confirmed it is absent from `ui/`
  entirely: `strength` reaches the user through the generic param form because it is an algorithm
  parameter, but `color_metric` is a `PipelineSpec` field with no control, so the four metrics are
  unreachable from the GUI.
- H8 is in progress. Its first pass found DEV-109 (dead F5 and Space, swallowed drops), fixed in
  `5075027` and confirmed working by the human. The gallery is still unwired, so it cannot be
  judged until T32.
