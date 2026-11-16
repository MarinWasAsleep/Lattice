# Deviation protocol and register — Lattice harness 0.1

The protocol is **unchanged** from `harness/v1.0/DEVIATIONS.md` (DitherCraft 1.0): same five classes E1
to E5, same retry budget (3 gate retries, 2 review cycles), same impact rule. Read that file; it is
not repeated here.

Classes E6 (regression) and E7 (product) from `harness/v1.1/DEVIATIONS.md` also apply, unchanged.

Two additions for the suite:

- **E8 Abstraction leak.** A change that makes an application import from another application, or
  that puts application-specific logic into `lattice_core`. Caught by the L1 test that walks the
  package, or by the reviewer. Never acceptable: core must not know that Lattice Glyph exists. The
  resolution is either to move the code into the application, or to generalise it behind a
  documented core interface.
- **E9 Host coupling.** A change that makes an application unusable without ArtCraft: a hard
  dependency on a running host, a crash when the bridge is absent, or a UI that only makes sense
  when bridged. Every application must open a file and render it with no host present. Declared by
  the reviewer or caught at H12, H13 or H14.

## Register

Format: one block per deviation, newest at the bottom. Status: open | accepted | rejected | resolved.

The DitherCraft registers (DEV-001 to DEV-008 in 1.0, DEV-101 onward in 1.1) are closed and stay in
their own files. Nothing is carried over.

```
### DEV-201
- class: E8 | task: Lxx | contract: 0.1.0 | status: open
- raised by: reviewer | date: 2026-11-xx
- facts: <what leaked, quote the import or the file>
- assumption / proposal: <move it, or generalise it behind a core interface>
- decision: <filled by decider> | by: <reviewer / orchestrator / human>
- impact: <tasks affected, contract version bump>

### DEV-202
- class: E1 (×5) | task: L1 | contract: 0.1.0 | status: accepted
- raised by: coder, then reviewer | date: 2026-11-16
- facts:
  1. `lattice_core/gamma_table.py` = 1329 lines (> 400) — generated data table (header
     "generated, do not edit"), governs bit-exact G7 rendering; moved as-is rather than split
     (splitting generated data would risk E6). Size identical to HEAD (R100).
  2. Kernels numba `_search` (dbs.py, 142 l) and `_yliluoma2` (yliluoma.py, 68 l) exceed the
     60-line function cap — JIT kernels; splitting them is a logic refactor forbidden by the
     card ("rename imports mechanically; do not refactor logic").
  3. `ui/main_window.py` (516), `ui/palette_panel.py` (563), `ui/gallery.py` (440) already
     exceeded 400 lines at HEAD; app modules, not moved, only import-rewritten.
  4. Witness baselines 01/05 differ from the committed PNGs at the byte level but have
     identical pixels (Pillow encoder, pre-existing at HEAD); `git diff HEAD -- tests/data/baseline`
     is empty — no data touched.
  5. `pip install -e .` with network resolution was not run by the coder; verified in
     equivalent form (editable --no-deps + exact numpy/numba/Pillow restored from uv cache,
     clean venv, PySide6 not imported).
- decision: accepted | by: orchestrator | after review PASS (reviewer verified: no logic change,
  byte-identical renames, correct shipped_preset_dir, monkeypatching preserved, no residual imports)
- impact: none — all five are constraints of the card, none alters behaviour or packaging.
```

## Amendments

Facts discovered during a task that the contract could not have known, recorded here rather than
invented in code. The orchestrator folds them into the contract at the next checkpoint.

```
### AMD-xxx
- task: Lxx | contract: 0.1.0 | date: 2026-11-xx
- section: §n
- discovered: <the real surface, quoted from the host's own `describe` output>
- contract change: <the sentence to add or replace>
```

### AMD-001
- task: none (human decision) | contract: 0.1.0 | date: 2026-11-12
- section: §1, §2, §20
- discovered: the name `DitherCraft` is already in use by three live products, one of them a
  direct Rust competitor (`github.com/shahil-sk/dithercraft`). Recorded in
  `docs/market-research.md` §9.
- contract change: §1 table row becomes `| Lattice Dither | lattice-dither | palette dithering |`;
  the §20 non-goal "Renaming DitherCraft" is removed. The application is renamed Lattice Dither,
  package `lattice_dither`, distribution `lattice-dither`, executable `LatticeDither.exe`.
