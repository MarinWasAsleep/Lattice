# Project state — harness 1.1 (updated by the orchestrator only)

contract_version: 1.1.0-draft
base_contract: 1.0.0 (harness/CONTRACT.md, §1 to §11, frozen)
max_concurrency: 4
last_update: 2026-11-12

## Environment (inherited from 1.0, unchanged)

- python: 3.15.2 · numpy 2.5.4 · numba 0.68.1 · Pillow 13.0.0 · PySide6 6.12.0 · pytest 9.2.0 · ruff 0.17.4
- venv: `.venv` at the project root. No new dependency in 1.1.
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
| T23 | 5 | todo | 0 | 0 | | SVG export |
| T24 | 5 | todo | 0 | 0 | | print export |
| T25 | 5 | todo | 0 | 0 | | animation + video |
| T26 | 6 | todo | 0 | 0 | | algorithm gallery |
| T27 | 6 | todo | 0 | 0 | | undo, shortcuts, drag and drop |
| T28 | 6 | todo | 0 | 0 | | i18n + French catalogue |
| T29 | 6 | todo | 0 | 0 | | performance, large images |
| T30 | 7 | todo | 0 | 0 | | Pixel Snapper + descreen |
| T31 | 7 | todo | 0 | 0 | | bridge v2 |
| T32 | 7 | todo | 0 | 0 | | integration + acceptance |

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
  is file-based or pasted hex, never network in the core.
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

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H5 | after T17 | pending — read and freeze CONTRACT 1.1 |
| H6 | after wave 4 | pending — judge output on three real images |
| H7 | after wave 5 | pending — run the CLI and the print export |
| H8 | after wave 6 | pending — use it for a week |
| H9 | T32 | pending — acceptance in PhotoCraft |

## Next

- NEXT: wave 4 is complete. T23 (SVG export) and T24 (print export) open wave 5.
- DEV-101 is resolved, so no deviation blocks a task. DEV-104 and DEV-105 stay open as accepted
  readings of §14 and §15.1 and need no action before wave 5.
- H5 (read and freeze CONTRACT 1.1) is still pending and should be taken before wave 5.
- H6 (judge output on three real images) can now be taken: T17 to T21 are in, so conditioning,
  colour metrics, strength, both halftones and the palette library are usable from the GUI.
- H7 (run the CLI and the print export) is half ready: the CLI is in, the print export is T24.
