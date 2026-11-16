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

### DEV-203
- class: E1 (ambiguïté de carte) + E3 (scope) | task: L2 | contract: 0.1.0 | status: accepted
- raised by: orchestrator | date: 2026-11-16
- facts: la carte L2 liste `owns` sans `lattice_core/pipeline.py`, mais sa spec exige de
  câbler l'étape 11 de §5 dans `pipeline.render` ("Wire step 11 of §5 into `pipeline.render`
  behind the registry") et §3 pose la dérivation de `coverage`/`luma`/`samples` aux étapes
  6-10 du pipeline. Sans `pipeline.py` dans owns, G4 échoue mécaniquement (écriture hors
  owns) et aucun appelant existant ne peut passer par le registre, alors que les `accept`
  exigent "every existing caller keeps working" et les tests pixel/coverage.
- assumption / proposal: ajouter `lattice_core/pipeline.py` aux `owns` de L2. C'est le seul
  fichier manquant ; `pipeline.py` n'est possédé par aucune autre carte du plan (L1 l'a
  déplacé, L-UI et les coquilles touchent leurs propres paquets).
- decision: accepted | by: orchestrator | date: 2026-11-16
- impact: owns de L2 élargi d'un fichier, aucun autre effet de plan ni de contrat ; à
  ré-examiner à H11 (gel §3/§5).

### DEV-204
- class: E1 (×2) | task: L2 | contract: 0.1.0 | status: accepted
- raised by: coder (attempt 1) | date: 2026-11-16
- facts:
  1. Le contrat ne dit pas quoi mettre dans `samples` pour `pixel` (k=1) → le codeur met la
     luma de la cellule source (`luma[:, :, None]`), comportement conservateur le plus simple.
     Cohérent avec §3 : échantillon 1 point = luminance moyenne de la cellule.
  2. `RenderStyle.options` est passé vide (`{}`) par le pipeline — `PipelineSpec` n'a pas
     encore de champ renderer/style ; la sélection d'un renderer autre que `pixel` et le style
     sont prévus pour les cartes suivantes (voir finding minor « renderer hardcodé » de la
     revue — adressé dans le retry attempt 2).
- decision: accepted | by: orchestrateur (après revue FIX : ni l'un ni l'autre n'est un
  blocker ; le 2 est adressé dans l'attempt 2 qui câble le champ renderer)
- impact: aucun sur le contrat ; le 1 reste le comportement `pixel` (il ne consomme que
  `index`), le 2 est résorbé par le retry.

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

### AMD-002 .. AMD-006 — structural amendments, decided 2026-11-16 (human, on Opus recommendations)
- task: none (pre-H11 freeze) | contract: 0.1.0 | date: 2026-11-16
- sections: §5 (S1), §3 (S2, S3), §6 (S4), §2 (S5)
- discovered: REVUE-PRODUIT.md — five structural defects that L2/L4 would freeze (see S1-S5).
- contract change (all applied to CONTRACT.md):
  - S1 §5: continuous mode — `algorithm: null` / `palette: null` legal, renderer `pixel` 1×1,
    Glitch is an effect-graph app.
  - S2 §3: `grid.luma` (source luminance before quantisation) + renderer `consumes()`; full
    glyph ramps with b/w palettes; new L2 test "luma independent of the palette".
  - S3 §3: renderer `subgrid = (sx, sy)` (braille 2×4, sextant 2×3); pipeline dithers at
    sub-point resolution, `grid.subindex`; `dither: bool` removed.
  - S4 §6: v3 completeness — `effects[].stage pre|post`, `palette.source/extract`, `masks`,
    `fonts {family, fallback}`, `output {scale, width?, dpi?}`.
  - S5 §2: card L-UI owns `lattice_core/ui/` (canvas+worker+split, Looks grid, full-resolution
    export, bridge dot, empty state) after L5, before L12/L20; fixes the two Dither blockers.

### AMD-007 — market scope, decided 2026-11-16 (human, on Opus recommendations)
- task: none (pre-H11 freeze) | contract: 0.1.0 | date: 2026-11-16
- sections: §11, §20, §2
- discovered: REVUE-PRODUIT — the suite builds the two least-documented products (glyphs,
  glitch) while excluding the two best-documented needs (separations, animation).
- contract change (all applied to CONTRACT.md + TASKS.md):
  - P1: a targeted glyph/glitch market research is launched in the background, added to
    `docs/market-research.md` before H12.
  - P2: separations and full animation stay excluded as an **assumed, documented bet** — no
    promise in any contract version (§20).
  - P3: §11 text export — `txt`/`ansi`/`html` + `render --format txt|ansi|html`; card L11.
  - P4: §20 N-image loop — card L-LOOP (GIF/APNG, `core/animation.py` moved to lattice_core).
