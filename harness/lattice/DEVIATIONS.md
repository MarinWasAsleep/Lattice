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

### DEV-205
- class: E1 (règle gelée vs test antérieur) + E3 (correction hors owns) | task: L2b | contract:
  0.1.0 | status: accepted
- raised by: coder (attempt 1) | date: 2026-11-16
- facts: la règle H11 §5-6 (gelée) donne pour a=0.5/pixel_size=1 → (cell_w, cell_h) = (1, 1),
  mais `tests/test_cell.py:233` (livré L2, pré-gel) assertait (1, 2) via l'arrondi
  half-to-even. `test_cell.py` n'est pas dans les owns de L2b (G4).
- decision: accepted | by: orchestrateur | date: 2026-11-16 — test aligné sur la règle gelée :
  pixel_size=2 → (1, 2) sous H11 (floor(2·0.5+0.5)=1), intention du test (aspect 0,5 → cellule
  1×2) conservée, commentaire ajouté. Révision à la relecture L2b pass 2 : PASS.
- impact: aucun plan ni contrat ; évite une DEV par carte future.

### DEV-206
- class: E1 (×2) | task: L5 | contract: 0.1.0 | status: accepted
- raised by: coder | date: 2026-11-16
- facts:
  1. Racine app-data Linux ajoutée — le code ne connaissait que `%LOCALAPPDATA%` ; §7 l'exigeait
     (Windows inchangé, sortie 1.0/1.1 inchangée).
  2. `ArtCraftClient.discover` lève `ValueError` sur un nom d'hôte hors `HOSTS` au lieu de
     renvoyer `None` — un nom d'hôte faux est un bug d'appel, pas une absence d'hôte.
- decision: accepted | by: orchestrateur (après relecture : seul finding majeur = AMD non
  enregistrée, résolue par AMD-009 ; le code est sain)
- impact: aucun ; 3 minors de relecture notés pour les cartes pont futures (fallback
  fichier→base64 couplé à la chaîne d'erreur de l'hôte, `_decode` sans retry candidat,
  monkeypatch `sys.platform` dans le test).

### DEV-207
- class: E1 | task: L3 | contract: 0.1.0 | status: accepted
- raised by: coder | date: 2026-11-16
- facts: le contrat ne borne pas le nombre de couleurs importées d'un PNG — le code impose
  2..256 couleurs distinctes (cohérent avec `palettes/io` MIN/MAX), ordre = première apparition
  (déterministe) ; `Palette.order` conservé `list[int] | None`, validé à la construction.
- decision: accepted | by: orchestrateur (review L3 PASS, 2 minors distincts consignés : bornes
  propagées aux vues par `__array_finalize__` ; `order` non entier stocké après coercition →
  IndexError au lieu de ValueError — à traiter à la prochaine carte qui touche palette.py)
- impact: aucun.

## Amendments (registre)

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

### AMD-008 — gel 0.1.0, décisions H11 (B/A/A/A/A), 2026-11-16
- task: none (checkpoint H11) | contract: 0.1.0 | date: 2026-11-16
- section: §2, §3, §5, §9, §10, §11 + TASKS (carte L2b)
- discovered: analyse H11 (Opus — `prompts/generated/H11-analyse-result.json`) : S2/S3 ajoutés
  à §3 sans être propagés à §9/§10/L6/L8/L9 (rampe sur `coverage`, `dither` dans bitmask),
  invariant 2 contredit le cache de §9, §11 sans accès aux glyphes choisis (le protocole ne
  renvoie que des pixels), mode continu inapplicable tel qu'écrit (index int32 de pixels source
  avec palette nulle), `pipeline.py` orphelin après L2 (DEV-203 « à ré-examiner à H11 »), règle
  de géométrie des cellules absente (aspect > 1 s'effondre en 1×1).
- contract change (décisions humaines du 2026-11-16, Q1=B Q2=A Q3=A Q4=A Q5=A) :
  - Q1 : le gel 0.1.0 est différé à cette passe d'amendements — l'humain relit le diff, puis
    `contract_version: 0.1.0` sans nouvelle analyse H11.
  - Q2 : capacité optionnelle `layout()` ajoutée à §3 (glyphes positionnés) ; `render()` en est
    la rastérisation ; §11 (SVG/txt/ansi/html) consomme `layout()` quand elle existe.
  - Q3 : nouvelle carte **L2b** « pipeline §3/§5 complet » (architect, strict, M), deps L2,
    owns `pipeline.py` + `cell.py` + `tests/test_pipeline.py` ; L4/L6/L8/L9/L11 passent en deps L2b.
  - Q4 : règle normative §5-6 — `a = cell_aspect()` ; a >= 1 : cell_w = pixel_size, cell_h =
    max(1, floor(pixel_size/a + 0.5)) ; sinon l'inverse. `size` retiré de §9 (police glyphe
    dérivée de cell_h).
  - Q5 : mode continu reformulé — `algorithm: null`/`palette: null` → étapes 6-11 sautées,
    image de l'étape 5 → étape 12, aucun CellGrid.
  - Cohérence : §9 glyph_ramp indexé par `luma` (S2, palette N&B = rampe complète) ; §9 bitmask
    sans `dither` (S3) ; §10 modulation par `luma` ; invariant 2 amendé (caches déterministes
    autorisés, jamais de changement de sortie) ; `consumes()` élargi à coverage/subindex ;
    frames flottantes officialisées (§3 render_frame, rés. du blocker L2) ; §2 rédactionnel
    (animation.py).
- status: applied (diff à relire par l'humain avant le gel)

### AMD-009 — pont DesignCraft : surface réelle observée (L5), 2026-11-16
- task: L5 | contract: 0.1.0 | date: 2026-11-16
- section: §7
- discovered (observé sur DesignCraft 0.20.1 Flatpak, `designcraft-cli describe file.place`) :
  1. Surface `file.place` : `{path?|base64?, name?, frame?: id, spread?, x?, y?, width?,
     height?, pdfPage?, …}` — « places an image into `frame` when given; otherwise any
     explicit x/y/spread/width creates a new frame ». Aucun paramètre inventé.
  2. Le canal DesignCraft n'a **pas d'authentification** : `auth` répond `unknown method`.
     La découverte = connexion + `engine.commands` (pas de token file, contrairement à §7).
  3. Sous Flatpak, l'hôte ne lit que xdg-documents/xdg-pictures : `file.place` avec un `path`
     du répertoire d'échange échoue (`No such file or directory`) → repli sur `base64`
     (paramètre documenté) ; `file.exportBatch` sans `dir` renvoie le PNG en base64 — plus
     aucun fichier d'échange nécessaire.
  4. PhotoCraft Flatpak exige `--automation-read-root`/`--automation-write-root` pointant sur
     le répertoire d'échange ; sans document ouvert, `place_as_layer` lève `BridgeError`
     (« no document open ») — comportement normal, pas un crash.
- contract change: à plier dans §7 au prochain checkpoint — « reads the token file, opens one
  authenticated connection » ne s'applique qu'à PhotoCraft ; DesignCraft = connexion directe
  sans auth, surface documentée ci-dessus.
- status: applied (orchestrateur — résolution de la major de la relecture L5)

