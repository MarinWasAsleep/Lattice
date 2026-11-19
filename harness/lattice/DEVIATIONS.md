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

### DEV-208
- class: E1 (enregistrement des renderers de la vague 1) + E3 (owns élargis) | task: L6, L8 |
  contract: 0.1.0 | status: accepted
- raised by: orchestrateur | date: 2026-11-17
- facts: `lattice_core/renderers/__init__.py` est possédé par L2 (done) et n'enregistre que
  `pixel`. L6 (glyph_ramp) et L8 (bitmask) doivent enregistrer leurs renderers pour G8
  (`list_renderers()` couvre tout) et le `renderer=` de PipelineSpec (L2b) — mais aucun owns
  ne couvre `__init__.py` après L2 (même gouffre que DEV-203). Deux cartes modifiant le même
  fichier en parallèle = conflit last-writer-wins avec write_file.
- decision: accepted | by: orchestrateur | date: 2026-11-17 — owns de L6 et L8 élargis à
  `renderers/__init__.py`, avec règle d'append atomique : chaque carte ajoute UNIQUEMENT sa
  ligne d'import via terminal (`cat >>`), jamais write_file sur ce fichier, jamais les lignes
  de l'autre. Chaque module renderer s'auto-enregistre à l'import (register_renderer en bout
  de module), comme le motif pixel.
- impact: owns élargis de 2 cartes ; règle d'écriture documentée pour G4 ; ré-examiné à la
  relecture L6/L8.

### DEV-209
- class: E1 (test périmé par amendement) + E3 (correction hors owns) | task: L4/L-UI | contract:
  0.1.0 | status: accepted
- raised by: orchestrateur | date: 2026-11-17
- facts: `tests/test_core_packaging.py` (livré L1) interdisait `ui` dans lattice_core et
  PySide6 partout. AMD-008 (H11, S5) a créé `lattice_core/ui/` (widgets partagés, extra [ui])
  possédé par L-UI — les 2 assertions sont devenues fausses : la carte L4 (36 tests) provoquait
  2 échecs de suite causés par les modules ui/ de L-UI en cours de création.
- decision: accepted | by: orchestrateur | date: 2026-11-17 — test aligné sur le contrat :
  `ui` retiré d'APPLICATION_MODULES (le paquet ui de core n'est pas un module d'app) ; le
  contrôle no-PySide6 ne scanne plus le sous-arbre `lattice_core/ui/` (légal sous [ui]).
- impact: aucun plan ; G4 : le fichier n'est dans les owns d'aucune carte (mécanique de gates).

### DEV-210
- class: E2 (budget de revue épuisé) + E1 (contexte de carte partiel) | task: L4 | contract:
  0.1.0 | status: open (décision orchestrateur : 3e cycle borné, PASS exigé sinon ESCALATE
  → humain)
- raised by: orchestrateur | date: 2026-11-17
- facts: L4 a consommé les 2 cycles de revue (pass 1 FIX, pass 2 FIX). Les 3 majors du pass 2 :
  1) la table APP_RENDERERS duplique le registre (le pass 1 l'avait déjà signale — le retry a
  gardé la table comme défaut) ; 2) _from_legacy : le défaut d'app s'applique avec warning
  même quand aucun renderer n'est présent dans un preset v1/v2 ? (sémantique du repli) ;
  3) **mode continu perdu au chargement** : _section(None, defaults) transforme algorithm/
  palette nulls des presets v3 en défauts — le mode continu §5 S1 ne survit pas au load.
  Le contexte de la carte était §6 seul ; §5 (mode continu) n'a jamais été dans les extraits
  du codeur (erreur de carte ou de contexte — le reviewer l'a attrape cote contrat).
- decision: orchestrateur | date: 2026-11-17 — 3e cycle borné (attempt 3) sur hy4-flash-free
  avec §5+§6 dans le prompt, consigne explicite (registre, pas de table), findings pass 1+2
  verbatim. Si le PASS n'est pas obtenu a ce cycle : ESCALATE vers l'humain (mode continu
  bloquant pour la chaine Glitch). r reste à 2 dans la table (compteur officiel).
- suite (2026-11-17) : attempt 3 propre (71 tests, mode continu nulls préservé, table
  supprimée) ; relecture pass 3 (Sonnet) : **FIX test-only** — aucun défaut de code, l'unique
  major est un item d'accept (repli dither-context) non testé (conflit résolu par `available=`,
  un test suffit) + 2 minors cosmétiques. **ESCALATE humain : arbitrage rendu — 4e cycle
  TEST-ONLY autorisé** (17/11) → attempt 4 : test d'accept ajouté, AUCUN changement de
  comportement requis (le code était correct), 72 tests owned, isolation 1448. **Relecture
  pass 4 : PASS (Sonnet)** — L4 done, 4 minors notés (tension sémantique registre-vs-letra
  de l'accept documentée, couplage d'environnement des tests, APP_DEFAULT_RENDERER hardcodé
  les noms d'app, clés v3 collant en legacy). **DEV-210 résolue.**
- impact: 1 cycle supplémentaire pour L4 ; rien d'autre.

### DEV-211
- class: E1 (test périmé par l'arrivée des renderers) + E3 (correction hors owns) | task: L6/L8
  | contract: 0.1.0 | status: accepted
- raised by: codeurs L6/L8 + orchestrateur | date: 2026-11-17
- facts: `tests/test_cell.py::test_list_renderers_returns_pixel` (livré L2) asserte
  `list_renderers() == ["pixel"]` — l'accept L2 disait « at this point ». Les renderers de la
  vague 1 (glyph_ramp L6, braille/sextant/quadrant/half_block L8) l'ont rendu faux ; le fichier
  n'est dans les owns d'aucune carte.
- decision: accepted | by: orchestrateur | date: 2026-11-17 — assertion structurelle : pixel
  présent, unicité des noms, sous-ensemble attendu des renderers de vague 1 présent (les
  invariants par renderer restent la propriété de G8).
- impact: aucun plan ; test_cell.py déjà aligné par l'orchestrateur (DEV-205).

### DEV-212
- class: E1 (wording) | task: L13 | contract: 0.1.0 | status: accepted
- raised by: codeur L13 (hy4) | date: 2026-11-17
- facts: labels ParamSpec de l'effet feedback (decay→Strength, transform→Scale, blend→Ratio)
  réutilisent les clés du catalogue i18n GELÉ — test_i18n asserte que chaque label est une clé
  de lattice_dither/i18n/en.json (hors owns), qui ne contient ni Decay ni Transform ni Blend.
- decision: accepted | by: relecteur (mistral-large-4) + orchestrateur — seuls ids/kinds/
  ranges sont normatifs ; réutiliser les clés du catalogue est la seule option conforme.
- impact: si une carte future owns en.json, ajouter des clés dédiées (Decay etc.).

### DEV-213
- class: E3 (test ajouté hors findings de relecture) | task: L6 | contract: 0.1.0
  | status: accepted
- raised by: relecteur pass 2 (v4-pro) | date: 2026-11-17
- facts: le terme de hauteur `_font_size` (cell_h/height_ratio) n'est exercé par AUCUN test —
  le mutant de mutation `font_size_from_cell_w_only` survit (à l'aspect 0.5 fixe du pipeline,
  by_width lie toujours). Minor réel, aucun accept violé, terme = défense en profondeur.
- decision: accepted | by: orchestrateur — ajout d'un cas épinglé `_font_size(4, 4, None) == 3`
  (by_h ~3.33 lie vs by_w ~4.60 ; un calcul largeur-seule donnerait 5) dans
  test_glyph_font_size_derives_from_the_cell : tue le mutant, fige le terme hauteur.
- impact: 49→50 assertions-owned (même test), code glyph_ramp.py inchangé.

### DEV-214
- class: E3 (convention inter-ers) | task: L14, L15 | contract: 0.1.0 | status: accepted
- raised by: relecteur L15 pass 1 (v4-pro) | date: 2026-11-17
- facts: deux effets (displace L14, pixel_sort L15) transportaient le masque différemment —
  displace keyword-only + ValueError, pixel_sort params['mask'] + drop silencieux ; L20
  (compositor) aurait dû spécial-caser l'un d'eux, ou un effet perdait son masque en silence.
- decision: accepted | by: orchestrateur + relecteurs — **convention : le masque passe en
  keyword-only (`*, mask=...`) et lève ValueError sur shape mismatch (message identique
  `mask must be {shape}, got {data.shape}`) chez TOUS les effets qui utilisent un masque**
  (displace, pixel_sort, et toute carte future §18). Le canal params est interdit pour les
  arrays (resolve_params les rejette).
- impact: L14+ L15 alignés ; les cartes §18 à venir (L19, …) et L20 suivent cette convention.

### DEV-215
- class: E1 (compromis de domaine) | task: L7 | contract: 0.1.0 | status: accepted
- raised by: codeur L7 (attempt 2) + relecture Sonnet | date: 2026-11-17
- facts: l'encre de cellule est comparée en domaine coverage ; `_circle_weights` intègre une
  couverture géométrique exacte alors que les samples restent des luminances ponctuelles —
  les deux sont des surfaces en [0,1], donc commensurables (compromis demandé par le finding).
  p/q : au plus petit stencil (cell_h 4/8) les vecteurs diffèrent mais le plus-proche voisin
  est le même — limite du stencil §9 à 6 disques, pas du code (dès cell_h ≥ 10, p/q séparés).
- decision: accepted | by: orchestrateur + relecture (PASS) — le test asserte la différence de
  vecteur partout et de glyphe dès cell_h ≥ 10 ; limitation documentée dans la docstring.
- impact: aucune action ; sert de référence si L10 (glyph browser) ou H12 signalent p/q.

### AMD-011 — glyph_shape : la normalisation ne s'applique qu'aux vecteurs de l'alphabet (L7), 2026-11-17
- task: L7 | contract: 0.1.0 | date: 2026-11-17
- section: §9 (glyph_shape)
- discovered: la lecture littérale de « Normalise each component by the maximum across the
  alphabet » (diviser AUSSI le vecteur de cellule) est INSATISFAISABLE : mesuré, elle écrase
  tout (1–4 glyphes distincts, top-3 = 1,00), violant l'autre clause de l'accept « ≥ 8
  distincts ». La relecture (Sonnet, pass 1) confirme : c'est un amendement de contrat
  (E2/E4), pas un fix.
- contract change: §9 PATCH (clarification, 2026-11-17) : « The per-component normalisation is
  applied to the alphabet shape vectors only (using the per-component maximum across the
  alphabet); the per-cell vector stays in raw disk-coverage fractions so the range of the cell
  retains its meaning. » Ratification humaine déléguée à l'arbitrage visuel de H12 comme
  AMD-010 (réversible).
- status: applied (PATCH §9) — arbitrage visuel final à H12

### AMD-010 — rampes de glyphes : indexation perceptuelle de la luma (L6), 2026-11-17
- task: L6 | contract: 0.1.0 | date: 2026-11-17
- section: §9 (glyph_ramp)
- discovered: L6 a ré-encodé la luma (linéaire, S2) en sRGB avant l'indexation de la rampe —
  sinon un dégradé N&B réel s'écrase dans le tiers sombre (gris 50 % sRGB = 0,214 linéaire) et
  l'accept « 10 glyphes distincts » échoue sur un dégradé perçu. La relecture (Sonnet) a
  demandé un arbitrage : §9 amendé dit « luma indexes an ordered ramp » sans préciser la
  fonction de transfert.
- contract change: §9 PATCH (clarification, 2026-11-17) : « the ramp is indexed by the
  sRGB-perceptual encoding of `grid.luma` (monotonic re-encoding of the linear value; darkest
  first is preserved) ». Décision humaine demandée, délégation à l'arbitrage visuel de H12
  (jugement des rampes sur images réelles) — réversible en une ligne.
- status: applied (PATCH §9) — arbitrage visuel final à H12

### DEV-216
- class: E1 (silence du contrat sur la persistance des verrous) | task: L19 | contract: 0.1.0
  | status: accepted
- raised by: relecteur pass 1 (Sonnet) | date: 2026-11-18
- facts: `SeedController.lock()` fige le flux d'un module à l'instant de l'appel ; §6 ne sérialise
  que `seed`, donc un preset sauvegardé après verrouillage puis rechargé perd la disposition
  verrouillée (le relecteur relève que §18 promet « a good accident is reproducible »). Second
  point : `SeedController`/`render_effects` n'est pas le chemin de `pipeline.render`, qui garde
  `default_rng(seed + offset + i)` (bit-exact, sous G7).
- assumption / proposal: (1) les verrous sont **session-only** en 0.1 — un preset transporte la
  graine, pas l'état de verrouillage ; (2) `pipeline.py` n'est pas modifié : son seeding est
  bit-exact et sous G7, et il n'est pas dans les `owns` de L19 — `render_effects` est le chemin
  documenté pour les effets verrouillés.
- decision: accepted | by: orchestrateur | date: 2026-11-18 — le contrat §6 reste inchangé ; si H13
  montre le besoin de presets verrouillés, ce sera un MINOR de contrat (clé `masks`/`locks`) avec
  sa propre carte, pas un ajout silencieux.
- impact: aucun code hors L19 ; à reconsidérer à H13 (Lattice Glitch vit de ces accidents).

### DEV-217
- class: E2 (budget de revue épuisé) + E3 (correctif borné test-only) | task: L9 | contract: 0.1.0
  | status: open (décision orchestrateur : 3e cycle borné, PASS exigé sinon ESCALATE humain)
- raised by: orchestrateur | date: 2026-11-18
- facts: L9 a consommé ses 2 cycles de revue (pass 1 FIX : clamp de `_place` rendant l'accept 3
  intestable, `weight_mode` silencieux ; pass 2 FIX : 1 major + 4 minors, DONT AUCUN ne porte sur le
  code produit — le major est que le helper de test `_ink_bbox` mesure l'encre avec
  `font.getbbox(char, anchor='ls')` en IGNORANT `glyph.stroke`, alors que le mode `variable` épaissit
  le trait de `round(ink * max(1, size // 8))` px ; l'accept « aucun glyphe hors du canevas » ne peut
  donc pas détecter un débordement dû au trait. Mesure indépendante de l'orchestrateur, en utilisant
  `_mask` (qui inclut le padding de trait) : 0 glyphe hors canevas sur 1008 glyphes × 6 combinaisons
  (cellules 8×16, 6×12, 3×5 × size_mode fixed/variable), dépassement max 0,0 px. Le code est donc
  correct ; c'est la preuve qui manque.
- assumption / proposal: 3e cycle borné TEST-ONLY (attempt 4), sur hy4-flash-free, avec interdiction
  de modifier le comportement de rendu. Si le PASS n'est pas obtenu : ESCALATE humain. `r` reste à 2
  dans la table (compteur officiel).
- decision: orchestrateur | date: 2026-11-18
- impact: un cycle supplémentaire pour L9 ; rien d'autre.
- suite (2026-11-18) : **cycle 3 rendu, verdict ESCALATE** — et il avait raison. Le relecteur
  n'ayant pas pu exécuter, il a conclu sur lecture que `_fit()` ignore le trait ; l'orchestrateur a
  alors mesuré, et **sa mesure antérieure (0,0 px) était complaisante** : ses textes de test
  commençaient par des caractères fins ou des espaces, donc aucun glyphe dense ne touchait x=0.
  Reproduction avec des cas hostiles, masque réellement rastérisé (trait inclus) :
  **défaut A** — texte « lattice text halftone » ×40 en `variable` sur cellules 8×16 : 13 glyphes
  dehors, jusqu'à 2 px (le trait dépasse la bbox de police que `_fit` mesure) ;
  **défaut B, plus grave** — « @ » × 400 (aucune espace) sur 320×160 : 400 glyphes dehors, le
  dernier à x=399 pour un canevas de 320 px, parce que `_fit()` réduit la police jusqu'à size 1 puis
  **abandonne** et que `_flow()` ne coupe jamais un mot. Violation directe de l'accept 3 (un mot
  long, un chemin ou une URL suffisent en usage réel).
  Le relecteur a classé B en major sans le voir (il n'a pas de cas sans espace) : l'orchestrateur
  l'élève en **blocker** et dégèle `text.py` pour l'attempt 5, borné à ces deux corrections
  (`_fit` mesure trait inclus ; `_flow` casse un mot trop long) plus une assertion de test à zéro
  débordement au lieu de la tolérance `max(1, size//8)`.


### DEV-218 — renderer `text` : le paragraphe n'est pas répété pour remplir la toile (L9/H12)
- class: E7 (produit) + E2 (défaut de contrat) | task: L9 (régression découverte à H12) | contract: 0.1.0
  | status: open
- raised by: analyse produit H12 (Sonnet puis Opus, 2026-11-18) | date: 2026-11-18
- facts: `_Paragraph._flow` (`lattice_core/renderers/text.py:271`) boucle sur `while idx < len(chars)` :
  il pose le texte UNE fois et s'arrête. Mesure orchestrateur : avec 496 caractères et
  `pixel_size 10`, le texte occupe **3 % de la hauteur du canevas** (26 px sur 900) pour
  **12 960 cellules disponibles** ; à `pixel_size 24`, 16 %. Le rendu sort donc quasi blanc
  (luma 0,995–1,000, contraste 0,011–0,042) et les images de H12 ne sont pas des texte-halftones.
  §10 dit : « Lay out the paragraph with real font metrics … Cells may vary in size … and must still
  fill the output rectangle exactly ». « Fill the output rectangle exactly » est donc violé : le
  renderer remplit le CADRE de son flux, mais laisse la toile vide quand le texte est court.
  Les 64 tests de L9 ne l'ont pas vu : ils vérifient la géométrie (aucun glyphe hors canevas,
  tailles distinctes, césure) et jamais que la toile est COUVERTE.
- assumption / proposal: boucler le texte jusqu'à remplir toutes les cellules (répétition du
  paragraphe), avec un mode `repeat: once` en option pour qui veut un paragraphe unique. Ajouter un
  test d'accept « la toile est couverte » : la fraction de cellules portant de l'encre doit dépasser
  un seuil (ex. 90 %) sur un texte court et un canevas large.
- decision: à trancher à H12 (question 3 du formulaire).
- impact: carte de correction à créer (L9b), et la vitrine de Glyph ne peut pas montrer `text` avant.

### DEV-219 — L9c attempt 1 : l'encre relative n'est appliquée qu'en `bg_colour`, `palette` est laissé inchangé
- class: E1 (interprétation d'une décision humaine) + E7 (produit) | task: L9c | contract: 0.1.0
  | status: open
- raised by: orchestrateur (vérification par exécution) | date: 2026-11-18
- facts: la décision H12 n°2 dit « l'encre devient relative à ±2 crans du fond **dans les modes
  `palette` et `bg_colour`** ». Le codeur ne l'applique qu'en `bg_colour` et laisse `palette` avec
  l'encre = couleur de palette de la cellule, au motif que l'accept 3 exige que `bg:"auto"` reproduise
  exactement l'ancien comportement. **Les deux exigences ne sont pas incompatibles** :
  `bg:"auto"` + ancienne encre est une variante ; `bg:"auto"` + encre relative est la nouvelle.
  Mesures orchestrateur : en mode `palette` + `bg:#ffffff`, luma sRGB 0,986 et **contraste 0,055** —
  l'image est blanche, donc l'accept 1 (« luma > 0,60 ») est satisfait par la lettre, pas par le fond.
  Second écart : l'accept 2 demande ≥ 5 glyphes distincts dans les 20 % de cellules les plus sombres ;
  le codeur annonce 5, la mesure de l'orchestrateur en trouve **4** (`- . : =`).
- assumption / proposal: (1) appliquer l'encre relative aussi en mode `palette` (le fond étant `bg`
  ou le ton le plus sombre si `auto`) ; (2) recaler l'accept 1 sur une mesure qui discrimine : luma
  compris entre 0,40 et 0,75 ET contraste > 0,25 (un rendu blanc ne doit pas passer) ;
  (3) faire vérifier l'accept 2 par le relecteur avec le protocole exact de l'orchestrateur.
- decision: orchestrateur — renvoi au codeur en attempt 2 avec ces trois points, sans consommer de
  cycle de revue (la carte n'a pas encore été relue).
- impact: un seul fichier (`glyph_ramp.py`) et son test ; les 2077 tests restent verts entre-temps.

### DEV-220 — L9c attempt 4 : normalisation linéaire vs seuil « ≥ 5 glyphes d'ombre » (arbitrage humain)
- class: E2 (résolu par décision humaine) + E1 ×2 + E3 | task: L9c | contract: 0.1.0 | status: applied
- raised by: codeur attempt 4 (xfail strict) — vérifié par l'orchestrateur (mesures + gates) | date: 2026-11-18
- facts: la relecture attempt 3 a rejeté le `span³` de l'attempt 3 (exposant calibré sur une image,
  dégénéré sur palettes sombres : ×37 à luma max 0,3, ×1000 à 0,1) et imposé la plage linéaire
  `gap / (max−min)`. Avec la plage linéaire, sur A_portrait (pico8, floyd_steinberg) à 12 px
  (taille de référence H12) : contraste sRGB 0,3259 > 0,30 ✓ mais **4 glyphes distincts dans les
  20 % les plus sombres (`- . : =`) < 5** ; à 8 px : 0,3269 et 5 ✓. Le cube (×1,37 sur pico8) était
  la seule voie vers 5 à 12 px ; la plage linéaire (×1,11) ne la franchit pas.
- decision (HUMAIN, 2026-11-18, H12 bis) : le contraste > 0,30 est le critère produit (tenu à 0,33) ;
  le seuil de comptage s'assouplit à **≥ 4 glyphes à 12 px**, le pin **≥ 5 reste à 8 px**. Accept de
  la carte amendé dans TASKS.md ; test désxfailé avec seuils paramétrés par cas ; aucun exposant,
  aucun seuil baissé en silence (le xfail strict avait porté les mesures avant l'arbitrage).
- E1 (ÉCART 1, formalisé) : `bg:"auto"` sélectionne le papier (ton le plus sombre) et conserve les
  glyphes absolus ; l'encre relative (±2 crans) est mandatée par spec 2 dans les DEUX modes, donc
  les pixels changent légitimement — la non-régression compare papier + glyphes, pas les pixels entiers.
- E1 (plafond 400 l) : tests/test_glyph_ramp.py à 463 l (restaurations mandatées du finding 6 —
  14 docstrings + commentaires de justification — + 2 nouveaux tests + pins littéraux). Convention
  du dépôt : les fichiers de test ne sont plafonnés que de fait (948 l au HEAD pour test_text.py).
- E3 (fixture hors owns) : tests/data/A_portrait.jpg (140 Ko, sha256 f57037fdb035…, identique à la
  source H12) — pré-autorisé par la disposition 5 du retry ; photo réelle, remplaçable par l'humain
  par une image sous licence. Les générations déterministes honnêtes mesuraient 0,22/0,25 de contraste
  (< 0,30) : les accorder pour passer aurait reproduit le gaming de span³ — rejetées.
- impact: glyph_ramp.py (400 l) + tests (463 l) + TASKS.md (accept) ; suite 66 cas verts sur la carte.

### DEV-221 — L-UI2 attempt 2 : pin Ctrl+E recâblé (test périmé par la carte)
- class: E1 | task: L-UI2 | contract: 0.1.0 | status: applied
- raised by: relecture attempt 1 (blocker export ; test_ui_commands.py:554 pinnait le handoff preview)
- decision: la carte recâble Ctrl+E sur le dialogue du core en PLEINE résolution (bloquant REVUE n°1, résolu).
  Le test périmé est adapté (il épingle source+spec+injections et refuse `_last_image`), précédent DEV-209.
  Aucun contournement silencieux ; vérifié en E2E : Ctrl+E → SVG 1400×900.

### DEV-222 — Dépassements de plafond 400 l (L9b et L20, tests et source)
- class: E1 | task: L9b, L20 | contract: 0.1.0 | status: applied
- facts: text.py 419 l (restauration de style ordonnée par le relecteur + ajouts L9b — aucun périmètre de
  restauration ne tient sous 400) ; tests/test_glitch_app.py 459 l (5 accepts + 6 findings demandés, sans
  assertions tautologiques) ; precedent DEV-202 (E1 acceptés) et convention tests non plafonnés (948 l au HEAD).
- decision: waivers enregistrés ; source des paquets respecte ≤ 400 (window.py 392, max), fonctions ≤ 60.

### DEV-223 — L20 attempt 2 : sérialisation des streams verrouillés (G9) + format de preset du shell
- class: E1 ×2 | task: L20 | contract: 0.1.0 | status: applied
- facts: §8 exige CLI/GUI octets identiques pour le même preset ; §18 core = verrous session-only (DEV-216,
  seed seul sérialisé). Le shell Glitch étend SON format de preset : chaque slot verrouillé écrit son stream
  (module_seed_for(i)) dans effects[].seed, relu au chargement vers RenderContext.streams ; unlock purge.
- decision: pas de changement du contrat core (SeedController inchangé, session-only conservé) ; l'extension
  est au format du shell, enregistrée pour ré-examen au gel (§18) — test verrou → reroll → sauvegarde →
  parité CLI/GUI puis rechargement → parité + stream figé conservé.

### DEV-224 — L-LOOP : sémantique des axes + APNG + doublon temporaire (E1 ×3)
- class: E1 ×3 | task: L-LOOP | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: contrat silencieux sur les axes de variation et l'APNG (carte P4).
- decision: axes — `seed` = spec.seed + step*i ; `offset` = np.roll horizontal de step*i px ;
  `iterations` = premier effet feedback activé, saturé à 8 (§12) ; `step` paramètre ajouté ; count=0 → [].
  APNG : duration ms, loop, disposal=2. Pas de vidéo ni timeline (§20). Doublon temporaire
  lattice_core/animation.py / lattice_dither/core/animation.py assumé (exports 1.1 gelés intacts) ;
  carte de déduplication à venir. PASS 1er cycle (relecture qwen4), test_core_packaging aligné (DEV-226).

### DEV-225 — L21 : interchange au niveau core (E1 ×4)
- class: E1 ×4 | task: L21 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: §6 « app mismatch is not an error » + « availability from the registry at call time » ;
  glitch document est continuous-only.
- decision: load_for_app/render_for_app dans le core (contexte app + warning + fallback), testé via
  les VRAIS lecteurs d'app (lattice_glyph.document.render_rgb8, glitch read_preset) ; available= est la
  surface de renderers par app, jamais de table dupliquée ; les starters taggés dither sont v3 (validés
  par le chargeur v3 + registres) — la tier v1 native de Dither reste intacte (hors owns). PASS 1er cycle.

### DEV-226 — test_core_packaging aligné sur L-LOOP (animation légitime dans le core)
- class: E1 | task: L-LOOP | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: le gate L1 interdisait `animation` dans lattice_core (APPLICATION_MODULES) ; la carte L-LOOP
  déplace justement le module N-image loop dans le core (aucun import applicatif, accept de la carte).
- decision: 'animation' retiré de l'ensemble (précédents DEV-205/209 — test aligné au niveau gate) ;
  la copie app reste pour les exports 1.1 ; rejoué : batterie complète 2167 passed / 1 skipped.

### DEV-227 — L22 : recette d'acceptance contre les hôtes Flatpak (vérifiée en réel)
- class: E1 (procédure) | task: L22 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: les deux hôtes sont des Flatpak. PhotoCraft exige `--automation-read-root`/`--automation-write-root`
  pointant un répertoire DU BAC À SABLE (`~/.var/app/ai.storyteller.photocraft/data/...`), un `XDG_DATA_HOME`
  cohérent côté client, et son `control.token` recopié dans `<XDG_DATA_HOME>/LatticeDither/`. DesignCraft
  n'ouvre son canal JSON que sur le drapeau **`--control 7979`** (absent de `--help` : documenté dans
  `share/doc/designcraft/README.md` de l'app installée) et sans token. Un `export XDG_DATA_HOME` oublié dans
  la session masque les apps Flatpak utilisateur (`flatpak list` vide) — `env -u XDG_DATA_HOME`.
- decision: recette consignée dans `tools/acceptance.py` (docstring) et STATE ; l'hôte absent sort 3 et
  nomme l'hôte. Vérifié : PhotoCraft 0.23.1 (3 apps, écart 0.000000), DesignCraft 0.20.1 (width 160).

### DEV-228 — L23 : packaging prouvé sur Linux, Windows déclaré non exécuté (E1 ×2)
- class: E1 ×2 | task: L23 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: Windows non testable sur cette machine (`pwsh` absent) ; aucun asset .ico pour Glyph/Glitch.
- decision: scripts Windows adaptés/complétés mais NON exécutés (E1) — aucun .exe ni raccourci Windows produit.
  Icônes : `applications-graphics` sur Linux, défaut sur Windows ; Dither garde la sienne.
- preuves Linux (exécutées par le codeur puis REVÉRIFIÉES par l'orchestrateur) : 6 binaires PyInstaller onefile
  dans `dist/` (156–231 Mo) ; `./dist/lattice-glyph-cli --help` exit 0 sans Python du venv ;
  `QT_QPA_PLATFORM=offscreen ./dist/LatticeGlitch` affiche « window shown » exit 0 ; 3 `.desktop` validés par
  `desktop-file-validate` ; 6 lanceurs dans ~/.local/bin ; **aucun raccourci sur le Bureau** (règle utilisateur) ;
  `check_versions.py` → VERSION CHECK OK (4 × 0.1.0, empreinte c03cd3baf14d31a8) ; venv vierge uv --offline
  9/9 smoke OK. Bug réel trouvé pendant la validation : le binaire Glyph plantait sans
  `lattice_core/data/ramps.json` — les 3 specs embarquent désormais `lattice_core/data` et `palettes/data`.
- correctif orchestrateur : B023 dans `tools/smoke_install.py` (fermeture de boucle) → ruff 0.

### DEV-230 — L24 : le masque de phosphores passe après la courbure (H13/M1 corrigé)
- class: E7 (produit) | task: L24 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: masque appliqué avant `_curve()` + `_sample()` clampant au bord -> colonne 0 (rouge) et dernière
  (bleue) étirées en bandes pleines dès curvature > 0. Prouvé sur `/tmp/h13/glitch_04_crt_finish.png`.
- fix: masque appliqué APRÈS la courbure (les rayures vivent en espace écran) ; couleurs du masque et
  `_sample()` inchangés ; TDD (tests écrits avant, dont la non-régression bit-identique à curvature 0).
- preuves orchestrateur : 46 passed (test_crt + témoins G7), ruff 0 ; mesure des bords sur le rendu réel —
  écart R−B bord gauche +43,3 -> +15,3, bord droit −26,5 -> +1,3 ; std spatiale des colonnes de bord
  24,1 -> 33,0 et 19,6 -> 31,0 (les aplats redeviennent des rayures).

### DEV-231 — L25 : boucle branchée dans Glitch par injection (H13/B1+B2 résolu)
- class: E7 (produit) | task: L25 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: `render_loop` acceptait seulement le chemin `pipeline.render_with_palette` (seed 1.0), qui ignore
  masques et verrous : frame 0 d'une boucle Glitch != PNG affiché (B2). Aucune sortie animée dans l'app
  (B1). Le codeur a été INTERROMPU par un timeout modèle (29 min) ; son travail était complet sur disque.
- fix: `render_loop(..., render_fn)` injectable ; Glitch passe `document.render_rgb8` + RenderContext ;
  verbe CLI `loop` (--preset --in --out --frames --axis) et entrées GIF/APNG au dialogue d'export.
  `pipeline.py` NON modifié.
- preuves orchestrateur (rejouées, pas sur parole) : frame 0 == PNG du preset, **écart 0** (identité
  byte) ; APNG et GIF à 4 frames sur l'axe `offset` ; 91 tests verts (loop+glitch+crt+témoins G7), ruff 0.
- constat mesuré au passage (confirmant Opus M2) : sur VHS soft, l'axe `seed` donne 4 frames IDENTIQUES
  (`channel_shift`/`pixel_sort`/`crt` sont déterministes) ; Pillow fusionne alors les frames. C'est
  exactement ce que L27 (axe `param`) doit lever.

### DEV-232 — L26 : l'axe seed respecte les verrous + TROU corrigé (sans verrou, rien ne variait)
- class: E7 (produit) | task: L26 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: le codeur a livré `locked_streams` + `StreamedSpec` (streams par frame), mais deux trous que la
  MESURE a révélés (ses 36 tests étaient verts) : (1) `render_loop` n'attachait des streams QUE si
  `locked_streams` était non vide -> le cas le plus courant (aucun verrou) rendait N frames IDENTIQUES,
  le `context.streams` du preset écrasant tout ; (2) `lattice_glitch/document._module_rng` lisait
  seulement `context.streams`, donc les streams de frame n'arrivaient jamais au rendu.
- fix (orchestrateur, dans les owns de L26/L25) : streams de frame attachés dès que le spec a des effets
  (`locked_streams or {}`) ; `_module_rng(position, context, controller, spec)` fait primer les streams du
  spec quand ils existent ; le shell Glitch transmet désormais `locked_streams` depuis
  `controller.locked()` (sinon les verrous de session étaient ignorés par la boucle).
- preuve mesurée (noise ×2, portrait) : sans verrou 1/3 -> **3/3 frames distinctes** ; tout verrouillé
  -> 1/3 (figé, voulu) ; un module verrouillé -> varie, ce module constant. APNG 4 frames réelles,
  frame 0 == PNG (identité byte), 156 tests verts (loop+glitch+crt+témoins+effets), ruff 0.

### DEV-234 — L28 · `bytemosh` : bornes de `stride`/`offset` (E3, orchestrateur)
- classes: E3
- context: L28, effet `bytemosh` (data moshing). Le codeur a livré 62 tests verts.
- facts: les `ParamSpec` d'origine bornaient `stride` à 3072 et `offset` à ±65536. Sur une
  image de 720 px, une ligne fait 2160 octets : toute fenêtre « large » était ramenée par
  `resolve_params` à 3072 octets, soit 1,4 ligne. Deux rendus avec `stride` 108000 et
  324000 sortaient **identiques au MD5** — la preuve que le paramètre était neutralisé.
- decision: plafonds relevés à 4 000 000 (stride et offset), sémantique inchangée.
- evidence: après correction, les MD5 divergent (`e83d870a…` vs `a12f43c0…`) ; jugement
  visuel indépendant (Claude Sonnet) : swap 7/10, interpret 6/10, blocs entiers échangés
  lisibles et couleurs préservées (offset multiple de 3 = décalage en pixels).
- lesson: une borne de `ParamSpec` est un plafond SILENCIEUX. Un paramètre qui « ne fait
  rien » se diagnostique en comparant deux sorties au MD5, pas à l'œil.
- status: applied

### DEV-233 — L27 : 4e axe `param` (faire bouger les effets déterministes) — DECISION AMD §20
- class: AMD §20 (amendement de contrat) + E1 ×2 | task: L27 | contract: 0.1.0 | status: applied | date: 2026-11-19
- facts: `channel_shift`, `rgb_shift`, `pixel_sort` et `crt` ne consomment pas le rng — mesuré : VHS soft en
  axe `seed` = 1/5 frames distinctes. Sans un axe de paramètre, 3 starters sur 4 restent figés en boucle.
- AMD §20 (validé par Opus, question Q3 = option 1) : la liste des axes gagne **`param`** — UN paramètre
  numérique d'un effet, de A à B et retour, boucle sans raccord. Toujours SANS timeline et SANS vidéo.
- implementation: `axis="param"` + `param="<effet>.<clé>"`, `from_value`, `to_value`, `curve="sin"|"linear"` ;
  sin = période complète `A + (B-A)*(1-cos(2πi/count))/2` (H13b Q2 : `count` pas, la dernière frame s'arrête
  un pas avant le début, donc PAS de doublon `frame[0] == frame[count-1]`) ; linear =
  triangle aller-retour. Keyword-only, ignorés sur les autres axes (callers inchangés).
- preuve orchestrateur (mesurée, pas sur parole) : channel_shift.amount 0→40 sur le portrait — frame 0 vs
  frame 1 **écart 236/255 sur 1,2 M pixels** ; frame[0] == frame[5] était l'ancien critère, CORRIGÉ par
  H13b Q2 (le doublon au raccord se voyait comme un à-coup) : 8 frames, frame[0] != frame[7] ;
  axe seed sur le même preset = 1/6, axe param = 3/6 distinctes (la symétrie aller-retour rend 1==4 et 2==3,
  c'est l'attendu de la courbe). 65 tests verts (loop+glitch), ruff 0.
- E1 : fichier de tests à 496 l (> 400, précédent DEV-222) ; formule de la courbe `linear` non spécifiée
  par le contrat -> triangle aller-retour retenu, cohérent avec la boucle sans raccord.

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

### DEV-235 — L29 · le CLI n'exposait pas l'axe `param` (E3, orchestrateur)
- classes: E3
- context: rédaction de la doc publique de `bytemosh`. La recette `loop --axis param` écrite
  dans le README a été EXÉCUTÉE avant publication : `invalid choice: 'param'`.
- facts: `lattice_core.animation.AXES` contenait `param` depuis L27, mais `lattice_glitch/cli.py`
  et `lattice_glitch/export_actions.py` portaient chacun un tuple en dur `("seed", "offset",
  "iterations")` avec le commentaire « mirrors lattice_core.animation.AXES ». L'axe était donc
  atteignable seulement depuis les tests. Le CLI n'avait pas non plus `--param/--from/--to/--curve`.
- decision: la liste vit dans `lattice_core/axes.py` (module sans Qt ni image), importée par les
  trois appelants ; le CLI gagne `--param`, `--from`, `--to`, `--curve`, et refuse
  `--axis param` sans `--param` en erreur d'usage (exit 1).
- evidence: `loop --axis param --param bytemosh.amount --from 0 --to 1 --frames 8` écrit un GIF
  de 8 frames, écarts consécutifs 252-255/255, frame[0] != frame[7]. Deux tests neufs :
  `test_cli_loop_exposes_every_axis_the_core_accepts`, `test_cli_loop_rejects_param_without_the_parameter_name`.
- lesson: un commentaire « mirrors X » est un aveu de duplication, pas une garantie. Quand deux
  listes doivent rester égales, la seconde doit LIRE la première.
- status: applied

### DEV-236 — L30 · `bytemosh` : la propagation (critique Opus sur les rendus)
- classes: E1 ×2 (sémantique des opérations) | task: L30 | status: applied | date: 2026-11-19
- context: jugement visuel des images de doc par Claude Opus en thinking high, trois passes avec
  les images régénérées entre chaque. Notes de départ : swap 3/10, shift 1/10, interpret 5/10,
  drift 2-5/10. Diagnostic central : « rien ne se propage, l'image guérit à la ligne suivante ».
- facts: deux bugs réels confirmés par la mesure — `round(amount * 0) = 0` rendait `shift`
  inopérant au `offset` par défaut, et `_drift` recevait `stride`/`offset` sans jamais s'en servir.
  Troisième défaut, relevé sur les images : `_drift` tournait chaque ligne SUR ELLE-MÊME, donc sur
  un dégradé vertical la rotation était invisible et le fond restait intact — précisément la couture
  qui prouve un fichier mal relu manquait.
- decision: `shift` devient un indel sur la queue du flux (`data[p:] = roll(data[p:], d)`) à des
  positions seedées ; `_indel` est extrait comme primitive ; `drift` tire ses positions sur tout le
  flux (trier des tirages, pas un pas depuis le début — un pas de `width//4` ramenait les dix
  événements dans la première rangée et empilait dix roulements en une seule translation) ; `offset`
  rebranché dans `drift` (un curseur mort est un bug) ; pas multiples de 3 pour ne pas tourner les
  canaux au hasard.
- evidence: notes Opus après correctif — shift **8,5/10**, interpret **8/10**, swap **7/10**,
  drift **7/10** et **6,5/10**. Le diagnostic « rien ne se propage » ne tient plus pour shift et
  drift. Docstring de `_drift` alignée sur ce que le code fait réellement (la version précédente
  annonçait un reshape à largeur fausse que le code ne faisait pas).
- reste (carte, pas retouche) : `drift` n'a pas de pente continue — une vraie largeur de rangée
  fausse (`width + k*3`) donnerait la diagonale ; `amount` discrimine peu entre 0,3 et 1,0 ; les
  positions de `swap`/`interpret` ne sont pas alignées sur 3, ce qui retourne les canaux 2 fois
  sur 3 (assumé et documenté, c'est le vocabulaire du databending).
- status: applied

### DEV-237 — L31 · `feedback` : origine et direction (demande humaine)
- classes: E1 (deux options neuves) | task: L31 | status: applied | date: 2026-11-19
- context: demande de l'utilisateur — « je veux choisir l'origine, choisir la direction » sur
  l'effet derrière son preset préféré (`07_feedback_echo`). Jusque-là l'écho partait toujours
  du centre et ne pouvait glisser que vers la droite.
- facts: `_apply_transform` codait `sx, sy = xs - amount, ys` pour `translate` (un seul axe
  possible) et `(width-1)/2, (height-1)/2` en dur pour `rotate`/`scale` (pivot fixe). Les
  transformations étaient déjà composables, donc deux options suffisent à couvrir la gamme.
- decision: deux ParamSpec, `origin` (choice : center, 4 coins, 4 bords) et `direction`
  (float −180..180, degrés). `origin` déplace le pivot de rotate/scale et le bord de départ de
  translate ; `direction` donne un cap à translate et une dérive biaisée à displace.
  `iterations` passe de 8 à 16 (plafond relevé : la boucle normalise, aucune divergence).
- evidence: mesure du centre de gravité d'une tache lumineuse — cap 0 → x +10, cap 180 → x −10,
  cap 90 → y +10 (bas de l'écran), cap −90 → y −10 ; symétrie miroir vérifiée. Pivot : sur une
  rampe horizontale, un zoom centré laisse le milieu à 0,513 alors qu'un pivot en haut-gauche
  le porte à 0,847 ; en rotation à 30°, le coin haut-gauche reste exactement à sa valeur source
  avec ce pivot et vaut 0,317 avec le pivot central. 89 tests dans `test_feedback.py`.
- bug attrapé par le juge visuel : `sy = ys + amount*sin(θ)` suivait la convention mathématique
  (Y vers le haut), donc « cap 90 » faisait monter l'écho alors que l'utilisateur demandait le
  bas. Signe inversé sur translate et displace ; revérifié sur rendu réel : droite / bas / haut
  conformes.
- status: applied
