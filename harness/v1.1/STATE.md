# Project state — harness 1.1 (updated by the orchestrator only)

contract_version: 1.1.0-draft
base_contract: 1.0.0 (harness/CONTRACT.md, §1 to §11, frozen)
max_concurrency: 4
last_update: 2026-11-11

## Environment (inherited from 1.0, unchanged)

- python: 3.15.2 · numpy 2.5.4 · numba 0.68.1 · Pillow 13.0.0 · PySide6 6.12.0 · pytest 9.2.0 · ruff 0.17.4
- venv: `.venv` at the project root. No new dependency in 1.1.
- Baseline before 1.1: 622 tests green, ruff clean, check_contract OK, commit `5e3c2dd`.

## Task table

| Task | Wave | Status | g | r | Commit | Notes |
|---|---|---|---|---|---|---|
| T17 | 4 | done | 0 | 0 | 502ea80 | spec v2, preset v2, conditioning; G5 green |
| T18 | 4 | todo | 0 | 0 | | colour metrics |
| T19 | 4 | todo | 0 | 0 | | strength invariant |
| T20 | 4 | todo | 0 | 0 | | halftone v2 + CMYK effect |
| T21 | 4 | todo | 0 | 0 | | palette authoring + library |
| T22 | 5 | todo | 0 | 0 | | CLI + batch |
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

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H5 | after T17 | pending — read and freeze CONTRACT 1.1 |
| H6 | after wave 4 | pending — judge output on three real images |
| H7 | after wave 5 | pending — run the CLI and the print export |
| H8 | after wave 6 | pending — use it for a week |
| H9 | T32 | pending — acceptance in PhotoCraft |

## Next

- NEXT: T18 (colour metrics) and T19 (strength) can run in parallel: their `owns` sets are disjoint
  (`core/color.py` + `tests/test_color.py` against the eight algorithm modules +
  `tests/test_strength.py`). T20 and T21 follow, also disjoint. Max concurrency 4.
- T18 and T19 must resolve DEV-102: `color_metric` is inert until it reaches the kernels.
- H5 (read and freeze CONTRACT 1.1) is still pending and should be taken before wave 5.
