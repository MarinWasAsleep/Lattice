# Project state — Lattice harness 0.1 (updated by the orchestrator only)

> La carte L22 transmet son résumé d'acceptation (JSON, via `tools/acceptance.py`) ; l'orchestrateur
> le reporte dans STATE.md — la carte n'écrit pas STATE.md directement.

contract_version: 0.1.0
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
| L6 | 1 | in_progress | 0 | 0 | | glyph ramp — mistral/deepseek-v4-1-flash-1017, DEV-208 (append __init__) |
| L7 | 1 | todo | 0 | 0 | | shape-matched glyphs |
| L8 | 1 | done | 0 | 2 | f60129c | bitmask — retry Unicode row-major (v4-pro blocker), PASS v4-pro, 48 tests, invariants §3 tenus |
| L9 | 1 | todo | 0 | 0 | | text-halftone |
| L10 | 1 | todo | 0 | 0 | | glyph browser + non-Latin ramps |
| L11 | 1 | todo | 0 | 0 | | SVG export |
| L12 | 1 | todo | 0 | 0 | | Lattice Glyph shell |
| L13 | 2 | done | 0 | 1 | 11fe38a | feedback buffer — 2e carte hy4-flash-free : PASS strict du 1er essai (mistral-large-4, vérifié par exécution) → TIER MASSE ACTÉ |
| L14 | 2 | in_progress | 0 | 0 | | displacement — image: mistral (standard) |
| L15 | 2 | in_progress | 0 | 0 | | pixel sort — nous (standard) |
| L16 | 2 | in_progress | 0 | 0 | | channel shift — 3e carte masse : hy4-flash-free (tier acté) |
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
| H10 | after L1 | ✅ done 2026-11-16 — app lancée par l'humain (`.venv/bin/python -m lattice_dither`, intacte) ; `lattice_core` s'installe seul en venv vierge (sans PySide6) |
| H11 | after L2 | ✅ done 2026-11-16 — analyse Opus (H11-analyse-result.json), décisions B/A/A/A/A, amendements AMD-008 appliqués puis **contrat gelé en 0.1.0** |
| H12 | after wave 1 | pending — analyse Sonnet (thinking high) de Lattice Glyph sur trois images réelles (captures/parcours) → toi : trancher |
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

- **Épreuve masse CONCLUE** : hy4-flash-free acté sur le tier masse (L4 PASS après 4 cycles
  avec code final jugé correct ; L13 PASS strict au 1er essai, vérifié par exécution). Les
  cartes opencode-go tournent désormais sur hy4 en routine (L16 = 3e).
- **En vol** : L14 (mistral), L15 (nous), L16 (hy4), relecture L6 (v4-pro). À chaque verdict :
  gates → relecture (tier critique, rotation Sonnet → mistral-large-4 → v4-pro) → commit.
- Ensuite : L7 (deps L6 ✓), L9, L10, L11, L12 (coquille Glyph, chemin critique) ; vague 2
  déjà entamée par L13. L-UI done débloque les coquilles UI de L12/L20.
