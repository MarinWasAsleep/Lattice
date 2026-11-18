# Project state — Lattice harness 0.1 (updated by the orchestrator only)

> La carte L22 transmet son résumé d'acceptation (JSON, via `tools/acceptance.py`) ; l'orchestrateur
> le reporte dans STATE.md — la carte n'écrit pas STATE.md directement.

contract_version: 0.1.0
base_contracts: DitherCraft 1.0.0 (§1–§11) and 1.1.0 (§12–§25), frozen, in force for the dithering app
max_concurrency: 4
last_update: 2026-11-18

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
- 2026-11-16: **rotation des backends (décision utilisateur)** — toutes les
  tâches de codage (cartes ET relectures) tournent par ordre de dispatch sur **nous → mistral →
  opencode-go → nous → …**. Modèles **prouvés par probes** : standard = deepseek-v4.1-flash
  hébergé par chacun (`deepseek/deepseek-v4-flash-0731` chez nous — préfixe vendor obligatoire,
  `deepseek-v4-1-flash-1017` chez mistral, `deepseek-v4.1-flash` chez opencode-go) ; lourdes =
  le fort de chaque backend (`deepseek/deepseek-v4-pro` chez nous — probe vert, `mistral-large-4`
  chez mistral — listé par l'API ; `kimi-k3.1-pro` chez opencode-go — probe vert mais **SORTI de
  la rotation le 17/11** : 2,00/10,00 $ par M + plafond 15 $/mois ; le lourd opencode-go devient
  **`hy4-flash-free` — 0 $, illimité, promo limited-time** → couche MASSE (codage
  mécanique/volumineux), épreuve à la prochaine carte routée opencode-go, décision humaine du
  2026-11-17, tiering 3 étages : masse = hy4-flash-free / standard = deepseek-v4.1-flash
  (nous/mistral) / critique = **Sonnet thinking high ×3 (CLI claude, décision 17/11 : remplace
  Opus)**, mistral-large-4, v4-pro). Providers Hermes :
  custom:mistral (MISTRAL_API_KEY), custom:opencode-go (**opencode.ai/zen/go/v1,
  OPENCODE_GO_API_KEY — abonnement Go ; header `x-opencode-session` requis par le backend,
  envoyé nativement par Hermes ≥ 0.21.6 — corrigé le soir : la doc du matin disait
  inference/go/openai/v1 + OPENCODE_API_KEY, config réellement établie au soir avec probes
  de bout en bout : deepseek-v4.1-flash et kimi-k3.1-pro → « pong » verts via route OMH)**.
  L1 a tourné sur nous ; **prochain dispatch : mistral (L2)**.
  L'orchestrateur pose la route OMH (omh_delegate_route, provider + model exacts ci-dessus) avant
  chaque dispatch.
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
  H10 done 2026-11-16 (humain) — app relancée depuis le menu.
- 2026-11-16: **L2 done — commit `7394b8b`**. Review pass 2 : **PASS (Opus, effort medium)** —
  verdict archivé `prompts/generated/L2-reviewer-result-2.json` ; les 5 findings du pass 1
  (dont le blocker E6) résolus, vérification indépendante orchestrateur à 0/25 octets (palettes
  flottantes + post-effects, module pipeline HEAD rejoué). 7 minors non bloquants, à traiter aux
  cartes suivantes : `prepare_image` calcule toujours la géométrie pixel (renderer param absent),
  `_cell_geometry` arrondit half-to-even (aspect perdu si aspect > 1 et pixel_size petit),
  `_render_frame` duck-type sans contrôle de shape, formule Rec.709 dupliquée, docstrings §5
  (11 vs 12 étapes), `RenderStyle` stocke le mapping mutable du caller, `noqa: F401` redondant +
  reload interdit. G2 : 1257 tests (1216 + 41). **Retry attempt 2 dispatché puis exécuté sur
  deepseek-v4-1-flash-1017** (modèle standard éco, règle de routage humain). Route lourde suivie :
  Opus ×3 complet (review pass 1, review pass 2, prochain = analyse H11) → prochain creneau lourd
  = mistral-large-4.

- 2026-11-16: **H11 done (humain)** — l'humain gèle le contrat **0.1.0** avec les amendements
  AMD-008 : Q1=B (amender puis geler, diff relu), Q2=A (`layout()` §3), Q3=A (carte L2b),
  Q4=A (règle de géométrie §5-6, `size` retiré de §9), Q5=A (mode continu = étapes 6-11 sautées).
  Le contrat 0.1.0-draft devient **0.1.0** — plus aucun changement sans PATCH/MINOR vérifié.
- 2026-11-16: **Vague 0 — relectures : L3 PASS (mistral-large-4), L5 résolu côté doc
  (deepseek-v4-pro → AMD-009, code sain)** — L3 : 6 accept vérifiés par exécution, 2 minors
  consignés pour la prochaine carte qui touchera palette.py (bornes de Palette propagées aux
  vues par `__array_finalize__` — résultats périmés sur slice ; `order` non entier stocké après
  coercition → IndexError au lieu de ValueError). L5 : 52 tests, 3 minors notés (fallback
  base64 couplé à la chaîne d'erreur, `_decode` sans retry, monkeypatch sys.platform). L2b :
  retry attempt 2 en cours (2 blockers maths). Commits de la vague une fois L2b posé.
- 2026-11-16: **Vague 0 close — L3 `dcf187f`, L5 `e187968`, L2b `3fe662a`** — 1336 tests verts
  (1216 base +41 L2 +17 L3 +52 L5 +49 L2b... ) vérifié à la batterie : ruff, check_contract,
  G4 par carte, G7 témoins bit-à-bit, G8 ["pixel"]. Relectures : L3 PASS (mistral-large-4),
  L5 gestionnaire AMD-009 (deepseek-v4-pro), L2b FIX→retry→PASS (Opus, 2 cycles). DEV-205/206/207
  enregistrés. 5 minors L2b consignés (msg erreur palette size, ordre des erreurs _validate_order,
  RenderStyle options dict mutable après construction, ordre row-major des sous-points non
  documenté, fn non typé) — à traiter aux cartes pipeline/props (L4, L7).

## Task table

| Task | Wave | Status | g | r | Commit | Notes |
|---|---|---|---|---|---|---|
| L1 | 0 | done | 1 | 1 | 696964d | extract lattice-core; critical path — gates G1-G7 verts, review PASS, DEV-202 (E1 ×5 acceptés) |
| L2 | 0 | done | 1 | 2 | 7394b8b | CellRenderer + PixelRenderer; gates G1-G4+G7-G9 verts (1257 tests), review Opus PASS (pass 1 FIX → retry), DEV-203 (owns pipeline.py), DEV-204 (2 × E1) |
| L2b | 0 | done | 0 | 2 | 3fe662a | pipeline §3/§5 complet (H11) — retry (2 blockers maths), review Opus PASS, DEV-205 (test aligné) |
| L3 | 0 | done | 0 | 1 | dcf187f | colour metrics + palette — review PASS mistral-large-4, DEV-207 |
| L4 | 0 | done | 0 | 4 | 11778ec | preset v3 — épreuve masse hy4-flash-free CONCLUE (4 cycles, PASS Sonnet), DEV-210, 4 minors notés |
| L5 | 0 | done | 0 | 1 | e187968 | bridge generalisation — review: code sain, AMD-009 (surface DesignCraft), DEV-206 |
| L-UI | 0 | done | 0 | 1 | a78009f | widgets partagés — PASS mistral-large-4, bloquants REVUE-PRODUIT vérifiés par exécution, E8/PySide6 propres |
| L6 | 1 | done | 0 | 2 | 45c42a2 | glyph ramp — retry invariant 2 + AMD-010 (rampe perceptuelle), PASS v4-pro, 49 tests, DEV-212/213 |
| L7 | 1 | done | 0 | 2 | d032847 | shape-matched glyphs — retry (AMD-011, comparateur densité, consomme samples), PASS Sonnet pass 2, DEV-215 |
| L8 | 1 | done | 0 | 2 | f60129c | bitmask — retry Unicode row-major (v4-pro blocker), PASS v4-pro, 48 tests, invariants §3 tenus |
| L9 | 1 | done | 0 | 4 | a75cfd1 | text-halftone — 5 tentatives : clamp intestable, `_fit` sans trait, mot insécable débordant → `_ink_box` sur encre réelle + césure ; **PASS Sonnet pass 5** ; 64 tests ; 3 minors (canevas trop petit non épinglé, docstring seed/paper perdue, `_flow` 45 l noms à 1 lettre) |
| L10 | 1 | done | 0 | 3 | 7f2312f | glyph browser + ramps.json — pass 1 FIX (5 défauts de code), pass 2 FIX test-only (2 majors), pass 3 **PASS** ; 30 tests ; E1 sur le buffer QImage (UB, non testable déterministiquement) |
| L11 | 1 | done | 0 | 1 | 4d03c55 | SVG + export texte (txt/ansi/html) depuis `layout()` — PASS Sonnet pass 1 ; 51 tests ; 3 E1 acceptées (blanc → `·`, dégradation en blocs, `text` refuse l'export texte) ; 5 minors (privés importés entre modules, rects de bord hors grille quand le pas ne divise pas, `·` aussi en ansi/html, `_token` ne gère pas l'espace interne, 2 tests de budget mous) |
| L12 | 1 | done | 0 | 2 | a86ae86 | coquille Lattice Glyph — pass 1 FIX (4 majors : preset amputé de 6 champs, `format_of` menteur, frappe invalide, pont dupliqué) → pass 2 **PASS** ; 2064 tests ; 7 minors (pont : `failed` modal, patch de test inopérant, suffixe → exit 2 au lieu de 1) |
| L13 | 2 | done | 0 | 1 | 11fe38a | feedback buffer — 2e carte hy4-flash-free : PASS strict du 1er essai (mistral-large-4, vérifié par exécution) → TIER MASSE ACTÉ |
| L14 | 2 | done | 0 | 1 | 0b0881d | displacement — PASS mistral-large-4 (5 accepts re-vérifiés par exécution, mutation-killed) ; monoplan pilote 2 axes (lecture §13) |
| L15 | 2 | done | 0 | 2 | f19f5cc | pixel sort — retry (mask aligné L14, tests non-tautologiques), PASS v4-pro pass 2, DEV-214 |
| L16 | 2 | done | 0 | 1 | c896465 | channel shift — 3e carte hy4 : PASS mistral-large-4, 0 finding, vérifié par exécution |
| L17 | 2 | done | 2 | 2 | 87b3a5d | NTSC / VHS — PASS Sonnet pass 3 (50 tests owned) ; 4 minors : labels i18n (carte catalogue future), LABEL_NOTES mort, constant_k = brick-wall, tracking_noise jusqu'à 25 % de largeur |
| L18 | 2 | done | 0 | 1 | (commit L18) | CRT / scanlines — PASS mistral-large-4 : pixels d'appareil vérifiés en direct, DEV-214 exact, 35 tests |
| L19 | 2 | done | 0 | 2 | 75a083d | seed + masks — pass 1 FIX (5 majors d'intégration) → retry (32 tests) → **PASS** Sonnet pass 2 ; DEV-216 verrous session-only ; 4 minors (render_effects non appelé par pipeline.render, resolve_masks muet sur une entrée vide, PNG P+tRNS, test seed hérité de 4 lignes) |
| L9b | 2 | done | 0 | 2 | fadb506 | renderer `text` : répétition fill/once (H12, DEV-218) — 89 tests, PASS 2e cycle, DEV-222 |
| L9c | 2 | done | 0 | 4 | cb3154c | `glyph_ramp` fond+encre relative+rampe bornée (plage linéaire) — accept amendé (E2 humain), 66 tests, PASS 4e cycle, DEV-220/222 |
| L-UI2 | 2 | done | 0 | 2 | a384f06 | Dither recâblé sur l'UI du core — ExportDialog 4 formats + Ctrl+E pleine résolution (REVUE bloquant 1), doublons supprimés ; 285 tests, PASS 2e cycle, DEV-221/222 |
| L20 | 2 | done | 0 | 2 | fdc07d3 | coquille lattice-glitch (21 modules, pyproject, CLI sans Qt) — G9 prouvé, crash export corrigé, NTSC simple+presets ; 8 tests, PASS 2e cycle, DEV-222/223 |
| L21 | 3 | todo | 0 | 0 | | preset interchange + gallery |
| L22 | 3 | todo | 0 | 0 | | acceptance in PhotoCraft and DesignCraft |
| L23 | 3 | todo | 0 | 0 | | packaging multi-plateforme + installation |

`g` = gate retries used (max 3), `r` = review cycles used (max 2).

## Human checkpoints

| Id | When | Status |
|---|---|---|
| H10 | after L1 | ✅ done 2026-11-16 — app lancée par l'humain (`.venv/bin/python -m lattice_dither`, intacte) ; `lattice_core` s'installe seul en venv vierge (sans PySide6) |
| H11 | after L2 | ✅ done 2026-11-16 — analyse Opus (H11-analyse-result.json), décisions B/A/A/A/A, amendements AMD-008 appliqués puis **contrat gelé en 0.1.0** |
| H12 | after wave 1 | ✅ **done 2026-11-18** — analyses Sonnet + Opus high (4 passes) ; **4 décisions humaines** : (1) mode `palette` respecte `bg`, (2) plafond corrigé par le fond de case portant le ton, (3) renderer `text` répète son paragraphe, (4) corriger les deux puis vitrine = `text`. Cartes **L9b** et **L9c** créées. AMD-010 ratifié, AMD-011 sous réserve de test |
| H13 | after wave 2 | pending — analyse Sonnet (thinking high) (Lattice Glitch vivant, pas un filtre ?) → toi : trancher |
| H14 | L22 | pending — acceptance in PhotoCraft then DesignCraft |

La numérotation des checkpoints continue à travers les générations : 1.0 H0-H4, 1.1 H5-H9,
0.1 H10-H14 (registre : `harness/README.md`).

- 2026-11-17: **GLM chez Mistral découvert** — `zai-glm-5-3-flash` (0,15/0,50 $, 1M ctx,
  orientation agents) et `zai-glm-5-3` (1,40/4,40 $) servis par Mistral (tiers Z.ai, même
  clé/compte), probe GLM-flash vert (latence ~2 min à froid à surveiller). Pas de « GLM 3.5 »
  au catalogue. Décision humaine : **pas en rotation avant la vague 1** (épreuve L4 proposée,
  différée). La clé mistral n'est pas dans le `.env` du profil (Hermes l'a dans son env —
  non localisée, fonctionnement confirmé par les dispatches).

- 2026-11-17: **L4 review pass 1 : FIX (Sonnet thinking high — 1er usage)** — la major :
  l'accept « missing renderer falls back to the app default and records a warning » n'est pas
  implémenté (le repli ne se résout pas au défaut d'app) ; 4 minors (table APP_RENDERERS
  dupliquée vs registre, ordre extra vs clés v3, validation lâche int(True/3.7/"3"),
  paramétrisation fragile du test). Erreur d'orchestration détectée par le reviewer : §6
  manquait des extraits de son prompt (corrigé pour le retry). **L4 retry attempt 2 dispatché,
  toujours sur hy4-flash-free** (épreuve masse en cours, même modèle — verdict juste).
  **DEV-209** : test de packaging L1 aligné sur S5 (ui retiré d'APPLICATION_MODULES,
  no-PySide6 restreint à la base) — suite 1372 verte.
- 2026-11-17: **L4 en cycle 3 (DEV-210)** — review pass 2 : FIX (Sonnet) — 3 majors : table
  APP_RENDERERS toujours dupliquée (exigence pass 1 répétée : « drop the table »),
  sémantique du repli legacy, et surtout **mode continu perdu au chargement** (algorithm/
  palette null → défauts ; §5 S1 ne survit pas au load — contexte de carte §6 seul, §5 jamais
  fourni au codeur). Budget revue 2/2 épuisé → déviation E2/E1, 3e cycle borné (PASS exigé,
  sinon ESCALATE humain — le mode continu est bloquant pour la chaîne Glitch). Suite : owned
  65 verts, base isolée 1372 verte. L-UI/L6/L8 toujours en vol.
- 2026-11-17: **Vague 1 lancée + L4/L-UI (4 voies)** — L4 = épreuve de la couche masse sur
  hy4-flash-free (opencode-go), L-UI (nous), L6 (mistral), L8 (nous) — tous standard éco sauf
  L4 (gratuit). **DEV-208** : owns de L6/L8 élargis à renderers/__init__.py (append atomique
  via terminal, jamais write_file — règle documentée pour G4). Prompts :
  prompts/generated/{L4,L-UI,L6,L8}-coder-attempt-1.md. Relectures à venir sur le tier
  critique (Sonnet thinking high → mistral-large-4 → v4-pro).

- 2026-11-17: **Vague 1 — relectures : L8 FIX (v4-pro, blocker Unicode trouvé)** — la table
  sextant était en column-major (54/60 glyphes d'export transposés ; PNG correct) ; l'E1
  (4 motifs inexprimables) vrai mais mal implémenté, test auto-bénissant. Retry L8 sur nous
  (row-major, test dérivé des noms Unicode, skip < 13.0, palette dégénérée → tout-papier).
  L6 retry (mistral) et L13 (hy4) en vol ; relecture L-UI (mistral-large-4) en vol. AMD-010
  (rampe perceptuelle) posé — arbitrage visuel à H12. L4 done (épreuve masse concluante).

## Next

- **Vague 1 CLOSE (18/11 au soir, swarm qwen4-max:free — décision utilisateur)** : L9b, L9c, L-UI2, L20
  done (commits fadb506/cb3154c/a384f06/fdc07d3), reviews PASS, **2124 passed / 1 skipped**, ruff 0,
  contract OK. Table de routage actée : **hy4-flash-free = masse ; qwen4:free = édition/refactoring +
  reviews de routine ; Sonnet CLI = goût seulement**.
- **Vague 2 à lancer (épreuve A/B)** : **L21 (gallery/interchange, qwen4)** et **L-LOOP (animation→core,
  hy4-flash-free)** — même protocole de relecture, compteurs comparés au passage (essais/findings/vitesse).
  Ensuite L-UI2 minors → carte de suivi i18n (2 clés du dialogue core), puis L22 (acceptance, H14) et L23.
- 2026-11-18: **H12 DONE — 4 décisions humaines prises** (analyse Sonnet + 4 passes Opus high, toutes
  sur pièces). (1) Le mode `palette` de `glyph_ramp` **respecte `bg`** : la palette ne colore que
  l'encre, le plus sombre de la palette devient `bg: "auto"` explicite et jamais le défaut. (2) Le
  plafond d'encre de 15 % se corrige par **la case qui prend la couleur du fond et la lettre qui
  apporte la texture** — décision d'Opus, confirmée par mesure (contraste 0,055 → 0,31). (3) Le
  renderer `text` **répète son paragraphe** jusqu'à remplir la toile (DEV-218 : aujourd'hui 3 % de
  la hauteur, 496 caractères sur 12 960 cellules). (4) Corriger les deux défauts, puis **`text` en
  vitrine** ; `bg_colour` corrigé devient la deuxième image couleur. Cartes **L9b** (text, réplétion,
  capable/strict/M) et **L9c** (`glyph_ramp`, fond + encre relative ±2 crans + rampe bornée,
  deep/strict/L) créées avec leurs accept chiffrés. **AMD-010 ratifié** ; **AMD-011 sous réserve**
  d'un test sur dégradé et capture de texte. Ce que les analyses ont établi au passage :
  `glyph_shape` reste pauvre sur portrait et capture (F4, hypothèse AMD-011 non prouvée) et le
  braille est le seul renderer lisible en l'état.
- 2026-11-18: **L12 done — commit `a86ae86`, PASS Sonnet pass 2. LA VAGUE 1 EST CLOSE** (L6, L7, L8,
  L9, L10, L11, L12 tous done). La coquille `lattice-glyph` : 18 fichiers, 390 l pour `window.py`,
  consomme `lattice_core/ui` sans réimplémenter un canvas ni un dialogue d'export (défaut S5 évité),
  G9 tenu par **un seul chemin de rendu** (`render_rgb8`), CLI sans Qt (vérifié sous bloqueur
  d'import), et les 8 renderers du registre sélectionnables. Le pass 1 avait trouvé 4 majors dont un
  **grave et prouvé par exécution** : `spec_from_panels` construisait un `PipelineSpec` neuf et
  perdait 6 réglages du preset (brightness, contrast, gamma, saturation, pre_blur, auto_levels) dès
  la première édition de panneau — corrigé par `deepcopy` + surcharge ciblée, revérifié à zéro perte.
  `format_of` refusait silencieusement `.jpg` en écrivant un PNG déguisé : il lève maintenant
  `DocumentError` en nommant le suffixe. 7 minors consignés, dont **trois à traiter avant H14** :
  `failed` reste branché sur une modale (un hôte qui disparaît entre découverte et appel ouvre un
  dialogue, E9 incomplètement fermé), le `monkeypatch` de `hosts.discover` est inopérant côté GUI,
  et un suffixe inconnu renvoie le code 2 au lieu du 1 que §8 prescrit.
- 2026-11-18: **Prochaine étape : H12** (checkpoint humain — juger Lattice Glyph sur trois images
  réelles). Analyse produit déléguée à Sonnet thinking high (`ANALYSTE-PRODUIT.md`) : captures,
  parcours, comparaison des rampes ; verdict + questions à trancher. AMD-010 (encodage perceptuel de
  la luma) et AMD-011 (normalisation `glyph_shape`) attendent la ratification humaine à ce
  checkpoint. **Décision de dispatch actée le 18/11** : les cartes restantes partent en
  `delegate_task` (visibles dans le dock TUI, transcript par `/agents`), plus en `hermes -z`.
- 2026-11-18: **L9 done — commit `a75cfd1`, PASS Sonnet pass 5** (5 tentatives, la carte la plus
  coûteuse du lot, et la plus instructive). Trois défauts réels trouvés en cascade : (a) l'accept
  « aucun glyphe hors du canevas » était **intestable** parce que `_place()` clampait les boîtes ;
  (b) `_fit()` mesurait la bbox de POLICE sans le trait §10, donc l'encre réelle dépassait de
  `stroke` px ; (c) **plus grave**, `_flow()` ne coupait jamais un mot et `_fit()` abandonnait à
  size 1 — un mot insécable (« @ » ×400) débordait de 81 px sur 320. Correctif final : `_ink_box()`
  dérive la bbox des pixels d'encre non nuls du masque trait inclus, `_flow()` casse les mots trop
  longs, `_fit()` mesure la même bbox et reste borné à 8 passes. **L'orchestrateur s'est trompé en
  cours de route** : sa première mesure (0,0 px) était complaisante (textes commençant par des
  caractères fins), la deuxième comptait le padding du masque comme de l'encre (1,0 px fictif
  partout). En mesurant les pixels non nuls : 0 débordement sur toutes les tailles réalistes ;
  seule une cellule 3×5 sur un canevas 120×50 px avec 1400 caractères déborde encore, et Sonnet
  arbitre que c'est une **limite physique acceptable** (le renderer doit remplir le rectangle ; une
  erreur typée serait un changement de contrat). 3 minors : ce cas non épinglé, docstring `seed`/
  `paper` perdue, `_flow` à 45 lignes avec des noms d'une lettre.
- 2026-11-18: **L11 done — commit `4d03c55`, PASS Sonnet pass 1** (1 seul cycle). `svg.py` (395 l) et
  `textout.py` (149 l) implémentent §11 depuis `layout()` : `pixel` en `<rect>` fusionnés (mesuré
  par l'orchestrateur : 2756 rects pour 4096 cellules sur du bruit 4 couleurs), glyphes en un
  `<text>` par glyphe (256/256 vérifié), budget 8 MB avec dégradation en rectangles à l'opacité de
  `coverage` puis en blocs coalescés, chaque étape rapportée. Export texte `txt`/`ansi`/`html`, ANSI
  jamais dans le chemin texte. Indépendance vérifiée après import : ni PySide6 ni `lattice_dither`
  dans `sys.modules`. **Les 3 E1 sont acceptées par la relecture** : `·` pour une cellule blanche
  (un espace disparaîtrait au split), dégradation en blocs (c'est ce que §11 prescrit), et `text`
  qui REFUSE l'export texte — §11 ne liste que glyph_ramp/glyph_shape/bitmask (52 placements pour
  4608 cellules : il n'y a pas de grille à imprimer). 5 minors consignés, dont deux tests de budget
  mous et des rects de bord qui peuvent dépasser la grille quand le pas ne la divise pas.
- 2026-11-18: **L10 done — commit `7f2312f`, PASS Sonnet pass 3** (3 cycles de revue consommés).
  Le WIP repris cachait cinq vrais défauts, corrigés : `render_ramp_preview` renvoyait HxWx4 quand
  `fg`/`bg` valait `transparent` (réinterprété en RGB888 → couleurs et stride faux) ; `select_ramp`
  ne repeignait pas quand la ligne était déjà courante ; `_ordered` citait `ramps[0]` au lieu de
  `ramps[1]` ; `_pixmap` gardait un `bytes` temporaire comme buffer de QImage ; `_load` fusionné dans
  un `load_catalogue` mémoïsé. Le pass 2 a jugé le code bon et attaqué les TESTS : le balayage ne
  prouvait pas le mappage cellule↔glyphe et le test des 100 ms ne mesurait qu'un cache chaud. Le
  pass 3 valide les deux preuves (colonne i byte-égale au rendu du glyphe seul ; `clear_glyph_caches`
  + `misses >= len(ramp)` rendent un run chaud impossible). **E1 acceptée** (arbitrage Sonnet) sur le
  buffer QImage : lire un tampon libéré est un comportement indéfini, aucun test Python déterministe
  ne peut l'attraper ; le codeur a écrit un garde de contenu et l'a déclaré au lieu de le maquiller.
  `ramps.json` (12 catégories, 30 rampes) est embarqué dans la wheel via `[tool.setuptools.package-data]`
  — ligne hors owns appliquée par l'orchestrateur après vérification par construction + venv vierge.
  3 minors de tests consignés (garde QImage faible, rampes non-latines non vérifiées contre un
  aperçu plat, constante d'encre 0x11 codée en dur).
- 2026-11-18: **L19 done — commit `75a083d`, PASS Sonnet pass 2** (2 cycles de revue, budget plein).
  Le retry de mistral a rendu 4 fichiers complets (32 tests owned, suite **1941 verte**, ruff et
  contrat propres) : `render_effects` est le chemin verrouillé documenté — `pipeline._apply_effects`
  reste `default_rng(seed + offset + i)`, bit-exact sous G7, non touché (DEV-216) ; `resolve_masks()`
  relie la section `masks` d'un preset aux `MaskRef` (base64 et path) sans modifier `preset.py` ;
  `mask.apply` sélectionne au poids nul au lieu de propager `0*nan` ; les PNG 16 bits (`I;16`) sont
  divisés par 65535 et le RGBA composité sur blanc (avant : saturation à blanc / alpha perdu).
  4 minors consignés : `pipeline.render` n'appelle pas `render_effects` (les verrous ne sont donc pas
  atteignables depuis une app — à câbler quand L20 possédera le pipeline applicatif) ; `resolve_masks`
  ignore silencieusement une entrée sans `path` ni `data` ; PNG `P` avec tRNS non compositeur ;
  un test de déterminisme ne teste que le chemin de graine préexistant. Vérification float64 vs
  float32 de `from_png` faite par l'orchestrateur : **0 ulp d'écart sur les 256 octets**.
- 2026-11-18: **reprise — L17 done, commit `87b3a5d`**. `git stash apply` du WIP 17/11 : `effects/__init__.py`
  réintègre `ntsc`, `.probe_crt.py` (sonde jetable) supprimé, ruff ramené à 0. **Relecture pass 3
  (Sonnet thinking high, cycle 3 sous E2/D EV-210) : PASS** — les findings pass 1/2 sont vérifiés
  corrigés (bandwidth sur l'axe des lignes, ringing à lobes négatifs, head_switching clampé,
  `seed` + `rng` pilotent ensemble le bruit, un générateur enfant par étage). 4 minors notés :
  labels ParamSpec réutilisant le catalogue i18n gelé (→ carte future sur le propriétaire du
  catalogue), `LABEL_NOTES` jamais lu par le code, `constant_k` est en fait un brick-wall,
  `tracking_noise` déplace jusqu'à 25 % de la largeur par ligne (presets VHS à surveiller à H13).
  Gates : ruff 0, contract OK, **1904 passed / 1 skipped**.
- 2026-11-18: **L19 review pass 1 : FIX (Sonnet)** — 5 majors, tous d'intégration, pas de maths :
  `SeedController` n'est câblé qu'au chemin `render_effects` et pas à `pipeline.render`; les verrous
  ne sont pas sérialisés ; `MaskRef` n'est relié ni à `preset.masks` ni à `effects[].mask`; deux
  tests ne peuvent pas échouer (comparaison uint8 triviale ; liste d'effets codée en dur). Décision
  orchestrateur : les verrous restent **session-only** en 0.1 (DEV-216, E1) — §6 continue de ne
  sérialiser que `seed` ; le câblage pipeline est refusé (hors owns, seeding bit-exact sous G7).
- **CLÔTURE DE SESSION 17/11 (point stable vérifié)** : arbre propre, HEAD `7c10e9c` poussé,
  **1854 passed / 1 skipped**, ruff clean, `tools/check_contract.py` → contract OK.
  L19 (seed + masks) livré et commité (code vérifié, relecture non faite — à reprendre).
  **WIP dans `git stash@{0}`** : L9 text-halftone, L10 glyph browser, L17 attempt 3 (non
  aboutis). Reprise : `git stash pop` puis relancer leurs reviews. Les enfants en vol ont été
  interrompus proprement (limite nous + arrêt demandé).
- Ensuite : L11 (SVG/text export, débloqué par L9), L12 coquille Glyph, L20 coquille Glitch,
  vague 3 (L21-L23), checkpoints H12/H13 (arbitrages AMD-010/AMD-011).

- 2026-11-19 (00h10, clôture de vague orchestrateur) : **VAGUE 1 CLOSE en swarm qwen4-max:free** — L9b
  `fadb506`, L9c `cb3154c`, L-UI2 `a384f06`, L20 `fdc07d3`. 4 cartes livrées, 4 reviews PASS (2e cycle
  sauf L9c 4e — le span³ avait été rejeté pour cause de knob, plage linéaire imposée). **E2 L9c tranché
  par l'humain** : le contraste > 0,30 reste le critère, comptage ≥ 4 glyphes à 12 px / ≥ 5 à 8 px
  (DEV-220) — la 5e nuance n'était atteinte que par le cube. DEV-221 (pin Ctrl+E recâblé), DEV-222
  (waivers 400 l), DEV-223 (streams verrouillés sérialisés au format du shell, cœur session-only).
  Batterie complète rejouée par l'orchestrateur : **2124 passed / 1 skipped** (2077 au HEAD → +47),
  ruff global 0, check_contract OK, G7 témoins intacts (aucun code de rendu touché par la vague).
  Minors consignés pour les cartes qui toucheront ces lignes : text.py:370 (encre des glyphes de queue du
  dernier pass `_fit`, approximation bornée) ; test_glyph_ramp.py (compacité E302 délibérée) ; i18n
  fr/en : 2 clés du dialogue core (rendu pleine résolution, no-video-writer) ; export_writers.py vs
  `export/` app : motif S5 à faire déléguer par une carte de suivi ; glitch : docstring seed_panel périmé,
  controller._fixed vs _fixed_streams (cycle déverrouiller/re-verrouiller), combo ntsc non resynchronisé.
  **Prochaine vague : L21 (qwen4) + L-LOOP (hy4) en épreuve A/B.**