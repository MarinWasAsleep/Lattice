# Project state — Lattice harness 0.1 (updated by the orchestrator only)

> La carte L22 transmet son résumé d'acceptation (JSON, via `tools/acceptance.py`) ; l'orchestrateur
> le reporte dans STATE.md — la carte n'écrit pas STATE.md directement.

contract_version: 0.1.0-draft
base_contracts: DitherCraft 1.0.0 (§1–§11) and 1.1.0 (§12–§25), frozen, in force for the dithering app
max_concurrency: 4
last_update: 2026-11-16

## Environment

- python: 3.13.14 (géré par `uv` — cpython-3.13.14-linux-x86_64) · numpy 2.5.4 · numba 0.68.1 · Pillow 13.0.0 · PySide6 6.12.0 · pytest 9.2.0 · ruff 0.17.4
- machine de build : **Linux Mint (cette machine)**, repo vivant dans `~/Lattice`. Windows reste
  une cible de publication (carte L23).
- venv: `.venv` at the repo root. Editable installs au fil des cartes.
- Hosts: **installés en Flatpak (user) sur cette machine** : PhotoCraft 0.23.1
  (`ai.storyteller.photocraft`), DesignCraft 0.20.1, PdfCraft 0.21.1, ArtCraft Launcher 0.19.2.
  Le pont y accède par `flatpak run` ; le token file vit sous `~/.var/app/ai.storyteller.photocraft/…`
  (à confirmer à la carte L5). Le port 47600 n'est ouvert que lorsque l'hôte tourne. Le 1.1 a tourné
  sans hôte réel : H9 §8 (recette) est maintenant exécutable si besoin.
- Baseline before L1: harness 1.1 feature-complete, portage Linux approuvé, HEAD `b4b0aea`
  (2026-11-16) — **1212 test cases green sur Mint (G2 Linux effectué), ruff clean, `check_contract`
  OK**. Le gamma est appliqué par table committée : les rendus sont bit-identiques cross-plateforme
  (décision ci-dessous). Les checkpoints humains H6-H9 de l'app appartiennent au harness 1.1.

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
- 2026-11-12: three new gates for the suite — numbered **G7** (core regression), **G8** (renderer
  contract) and **G9** (CLI/GUI parity, generalising the 1.1 G6) so every gate number stays unique
  across the project's history (registry: `harness/README.md`). Originally drafted as G5-G7, renamed
  on 2026-11-16 during the harness unification.
- 2026-11-12: **repositories split.** `MarinWasAsleep/Lattice` is the private working repository and
  tracks everything, harness included. `MarinWasAsleep/lattice-dither` is the public product
  repository: code, README, `docs/` and presets, with no harness. See AMD-001.
- 2026-11-16: harness unification (see `harness/README.md`) — gates of this harness renumbered
  G7-G9, checkpoints renamed H10-H14 (continuing the 1.0 H0-H4 / 1.1 H5-H9 sequence), baseline
  pinned to HEAD `b4b0aea`, card L1 realigned on the actual tree, Python pinned via uv 3.13.14,
  `STATE.md` stays orchestrator-only (L22 hands its acceptance summary to the orchestrator).
- 2026-11-16: **portage Linux approuvé par l'utilisateur** — le build continue sur cette machine
  (Mint), le repo vivant est `~/Lattice`. ArtCraft étant disponible sous Linux, le pont n'est pas
  Windows-only : les cartes L5 et L22 s'exécutent contre les hôtes Linux. Le gamma de l'application
  passe de `np.power` (libm — dernier bit dépendant de la plateforme) à une courbe 8 bits committée
  (`lattice_dither/core/gamma_table.py`, 73 gammas × 256 niveaux, générée par
  `tools/gen_gamma_table.py`) : rendu bit-à-bit identique Windows/Linux (E6 approuvé par l'humain).
  Baseline témoin `07_grey16_stucki` régénérée ; `01_gameboy`/`05_ega_riemersma` inchangés
  (gamma 1.0). Suite : **1212 verts sur Mint**. Nouvelle carte L23 (packaging Win/Linux).
- 2026-11-16: **L1 done — commit `696964d`**, gates G1-G7 verts côté orchestrateur (G2 : 1216 test
  cases passed, dont 4 nouveaux tests de packaging AST ; G3 ruff propre ; G4 `check_contract` OK ;
  G5/G7 témoins bit-à-bit), **review PASS** (39 paires renommées vérifiées au niveau tokens :
  0 changement non-import ; `shipped_preset_dir` parents[2]→parents[1] même cible ; split
  `bridge/_client.py` préserve le monkeypatching runtime). Corrigé par l'orchestrateur :
  `tools/fetch_palettes.py` (chemin résiduel `lattice_dither/palettes` → `lattice_core/palettes`).
  **DEV-202** enregistré : 5 × E1 acceptés (table gamma générée > 400 l, kernels JIT > 60 l,
  fichiers UI pré-existants > 400 l, baselines 01/05 octets ≠ mais pixels identiques, install
  vérifiée en offline). Vérification H10 rejouée par l'orchestrateur : venv uv vierge + `pip install
  -e .` → `lattice_core` importe, PySide6 non importé, requires = numpy/numba/Pillow (+ extra ui).
  H10 passe en attente de l'humain (app à relancer depuis le menu).

## Task table

| Task | Wave | Status | g | r | Commit | Notes |
|---|---|---|---|---|---|---|
| L1 | 0 | done | 1 | 1 | 696964d | extract lattice-core; critical path — gates G1-G7 verts, review PASS, DEV-202 (E1 ×5 acceptés) |
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
| L12 | 1 | todo | 0 | 0 | | Lattice Glyph shell |
| L13 | 2 | todo | 0 | 0 | | feedback buffer |
| L14 | 2 | todo | 0 | 0 | | displacement |
| L15 | 2 | todo | 0 | 0 | | pixel sort |
| L16 | 2 | todo | 0 | 0 | | channel shift |
| L17 | 2 | todo | 0 | 0 | | NTSC / VHS |
| L18 | 2 | todo | 0 | 0 | | CRT / scanlines |
| L19 | 2 | todo | 0 | 0 | | seed + masks |
| L20 | 2 | todo | 0 | 0 | | Lattice Glitch shell |
| L21 | 3 | todo | 0 | 0 | | preset interchange + gallery |
| L22 | 3 | todo | 0 | 0 | | acceptance in PhotoCraft and DesignCraft |
| L23 | 3 | todo | 0 | 0 | | packaging multi-plateforme + installation |

`g` = gate retries used (max 3), `r` = review cycles used (max 2).

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H10 | after L1 | pending (humain) — dossiers prêts 2026-11-16 : app intacte + lattice-core installable seul |
| H11 | after L2 | pending — analyse Opus du contrat (gabarit ANALYSTE-PRODUIT) → toi : trancher le gel |
| H12 | after wave 1 | pending — analyse Opus de Lattice Glyph sur trois images réelles (captures/parcours) → toi : trancher |
| H13 | after wave 2 | pending — analyse Opus (Lattice Glitch vivant, pas un filtre ?) → toi : trancher |
| H14 | L22 | pending — acceptance in PhotoCraft then DesignCraft |

La numérotation des checkpoints continue à travers les générations : 1.0 H0-H4, 1.1 H5-H9,
0.1 H10-H14 (registre : `harness/README.md`).

## Next

- NEXT: L1 alone. Nothing else may start until it is done and H10 is passed.
