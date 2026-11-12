# Project state — Lattice harness 0.1 (updated by the orchestrator only)

contract_version: 0.1.0-draft
base_contracts: DitherCraft 1.0.0 (§1–§11) and 1.1.0 (§12–§25), frozen, in force for the dithering app
max_concurrency: 4
last_update: 2026-11-12

## Environment

- python: 3.15.2 · numpy 2.5.4 · numba 0.68.1 · Pillow 13.0.0 · PySide6 6.12.0 · pytest 9.2.0 · ruff 0.17.4
- venv: `.venv` at the Lattice root. All four packages installed editable in it.
- Hosts: PhotoCraft 0.22.0, DesignCraft, PdfCraft — installed under `C:\Program Files\ArtCraft\`.
- Baseline before L1: 622 tests green, ruff clean, `check_contract` OK, commit `5f3a7f4`.

## Decisions log

- 2026-11-12: the suite is named **Lattice**. The dithering application is renamed **Lattice Dither**
  (package `lattice_dither`, distribution `lattice-dither`); the rename is done, not deferred.
- 2026-11-12: the suite is a set of **plugins for ArtCraft**, not a competitor. ArtCraft is the
  host: PhotoCraft (raster), DesignCraft (layout), PdfCraft (PDF production).
- 2026-11-12: **one repository per application, plus a published `lattice-core`.** Applications pin
  a compatible range, never an exact version.
- 2026-11-12: the core is **extracted from Lattice Dither**, not rewritten. Lattice Dither becomes the
  first consumer, which proves the abstraction instead of theorising it.
- 2026-11-12: the architectural bet is the **`CellRenderer`** abstraction (§3). Dithering decides
  which palette entry a cell gets; the renderer decides how to draw it. This is what lets 33
  algorithms serve three applications.
- 2026-11-12: **fixed images only.** Video is out of scope. The research prompt for a future video
  pass is archived at `harness/research/video-research-prompt.md`.
- 2026-11-12: **no physical media** (LEGO, beads, cross-stitch) and **no print separations** in this
  contract. Both are validated markets; both are deferred.
- 2026-11-12: licence is **MIT OR Apache-2.0**, matching ArtCraft. This is what makes libdither,
  histerdither, pyxelate and Pixel Art Fixer reusable.
- 2026-11-12: every application works **standalone and bridged**. The bridge is never fatal.
- 2026-11-12: three new gates — G5 core regression, G6 renderer contract, G7 CLI/GUI parity.
- 2026-11-12: **repositories split.** `MarinWasAsleep/Lattice` is the private working repository and
  tracks everything, harness included. `MarinWasAsleep/lattice-dither` is the public product
  repository: code, README, `docs/` and presets, with no harness. See AMD-001.

## Task table

| Task | Wave | Status | g | r | Commit | Notes |
|---|---|---|---|---|---|---|
| L1 | 0 | todo | 0 | 0 | | extract lattice-core; critical path, alone |
| L2 | 0 | todo | 0 | 0 | | CellRenderer + PixelRenderer |
| L3 | 0 | todo | 0 | 0 | | colour metrics + palette |
| L4 | 0 | todo | 0 | 0 | | preset v3 |
| L5 | 0 | todo | 0 | 0 | | bridge generalisation |
| L6 | 1 | todo | 0 | 0 | | glyph ramp |
| L7 | 1 | todo | 0 | 0 | | shape-matched glyphs |
| L8 | 1 | todo | 0 | 0 | | bitmasks |
| L9 | 1 | todo | 0 | 0 | | text-halftone |
| L10 | 1 | todo | 0 | 0 | | glyph browser + non-Latin ramps |
| L11 | 1 | todo | 0 | 0 | | SVG export |
| L12 | 1 | todo | 0 | 0 | | GlyphCraft shell |
| L13 | 2 | todo | 0 | 0 | | feedback buffer |
| L14 | 2 | todo | 0 | 0 | | displacement |
| L15 | 2 | todo | 0 | 0 | | pixel sort |
| L16 | 2 | todo | 0 | 0 | | channel shift |
| L17 | 2 | todo | 0 | 0 | | NTSC / VHS |
| L18 | 2 | todo | 0 | 0 | | CRT / scanlines |
| L19 | 2 | todo | 0 | 0 | | seed + masks |
| L20 | 2 | todo | 0 | 0 | | GlitchCraft shell |
| L21 | 3 | todo | 0 | 0 | | preset interchange + gallery |
| L22 | 3 | todo | 0 | 0 | | acceptance in PhotoCraft and DesignCraft |

`g` = gate retries used (max 3), `r` = review cycles used (max 2).

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H1 | after L1 | pending — verify Lattice Dither is intact and `lattice-core` installs alone |
| H2 | after L2 | pending — read and freeze the `CellRenderer` protocol |
| H3 | after wave 1 | pending — judge GlyphCraft on three real images |
| H4 | after wave 2 | pending — verify GlitchCraft is alive, not a filter |
| H5 | L22 | pending — acceptance in PhotoCraft then DesignCraft |

## Next

- NEXT: L1 alone. Nothing else may start until it is done and H1 is passed.
