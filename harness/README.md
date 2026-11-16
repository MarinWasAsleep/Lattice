# Harness Lattice — index des trois générations

Ce dossier porte le **protocole d'agents** qui construit les applications Lattice : un orchestrateur
qui ne code jamais, des codeurs routés par la chaîne OMH, un relecteur, et un humain aux
checkpoints. Tout se joue sur des fichiers (`CONTRACT.md`, `TASKS.md`, `STATE.md`, `DEVIATIONS.md`,
`prompts/`) — ce README est la porte d'entrée unifiée : **à lire en premier**.

## Les trois générations

| Dossier | Statut | Périmètre | Cartes | Gates | Checkpoints |
|---|---|---|---|---|---|
| `v1.0/` | **terminé** | L'app de tramage (alors nommée DitherCraft), v1 | 18 (T00-T16, T07 en A/B) | G1-G4 | H0-H4 |
| `v1.1/` | **feature-complete** | L'app de tramage, v1.1 (qualité, workflow, ergonomie) | 18 (T17-T34) | +G5, G6 | H5-H9 — H6/H7/H8/H9 encore ouverts (humain) |
| `lattice/` | **en cours (0.1)** | La suite : `lattice-core` + Lattice Dither, GlyphCraft, GlitchCraft | 22 (L1-L22, 4 vagues) — tout « todo », NEXT : L1 seul | +G7, G8, G9 | H10-H14 |

`docs/graph.html` (+ `graph.png`) : le graph « par quel agent » — boucle d'agents + cartes par vague.
`lattice/DEMARRAGE.md` : transfert vers Windows et ordre de lancement.

## Noms (piège historique)

- L'app s'appelait **DitherCraft** pendant les harness 1.0/1.1 ; elle a été renommée **Lattice
  Dither** (package `lattice_dither/`) le 2026-11-12 (AMD-001). Les documents 1.0/1.1 parlent encore
  de « dithercraft/ » : lisez `lattice_dither/`.
- « Lattice » sans suffixe = la **suite** (le plan 0.1), pas l'app.

## Rôles et exécuteurs (le vocabulaire unifié)

| Rôle | Qui | Fait | Ne fait jamais |
|---|---|---|---|
| Orchestrateur | Hermes (session TUI) ou un agent équivalent | planifie ≤ 4 cartes (owns disjoints), génère les prompts, court les gates, tient `STATE.md`, applique DEVIATIONS | écrire du code produit |
| Codeur | sous-agent via la chaîne OMH, catégorie = champ `executor` de la carte | une carte à la fois, fichiers `owns` seulement ; sort `FILE` + `NOTES` + `DEVIATIONS` | le reste du dépôt |
| Relecteur | catégorie OMH `review` | verdict PASS / FIX / ESCALATE, contrats avant tests | écrire du code |
| Humain | toi | checkpoints, décisions de déviation, gel du contrat | — |

Les générations 1.0/1.1 nommaient les modèles dans les cartes : **DeepSeek** (codeur), **Sonnet**
(orchestrateur et relecteur). Depuis le 0.1, cartes et gabarits ne nomment plus aucun modèle : le
routage vit dans la chaîne OMH (`omh_delegate_route`), catégorie par difficulté — `ultrabrain`
(L1, L7), `architect` (L2), `deep` (L3, L9, L17), `deep-work` (L12, L20), `capable` (le reste),
`quick` (L16).

## Registre des gates (numérotation globale unique)

Règle : **un numéro de gate n'est jamais réutilisé** dans l'histoire du projet. Le prochain gate
sera G10.

| Gate | Génération | Nom | Vérifie |
|---|---|---|---|
| G1 | 1.0 | ruff | lint propre |
| G2 | 1.0 | pytest | suite verte |
| G3 | 1.0 | check_contract | le code respecte le contrat |
| G4 | 1.0 | propriété des fichiers | une carte n'écrit que ses `owns` |
| G5 | 1.1 | compat presets v1 | les presets v1 se chargent et rendent à l'identique |
| G6 | 1.1 | parité CLI/GUI (dither) | CLI et GUI rendent des octets identiques |
| G7 | 0.1 | régression du core | après L1, Lattice Dither rend ses presets témoins au bit près (baselines `tests/data/baseline/`) |
| G8 | 0.1 | contrat des renderers | chaque `CellRenderer` du registre satisfait §3 |
| G9 | 0.1 | parité CLI/GUI (multi-apps) | dans chaque app, CLI et GUI rendent des octets identiques (généralise G6) |

Vérification des compteurs (33 algorithmes, 10 effets, ~1212 tests) : G2 au premier run sur la
machine de build — la doc ne fait pas foi, le registre si.

## Registre des checkpoints (numérotation continue)

1.0 : H0 (env) → H1 (geler le contrat 1.0) → H2 (ergonomie) → H3 (packaging) → H4 (recette).
1.1 : H5 (geler le contrat 1.1) → H6 (juger la sortie) → H7 (CLI + export) → H8 (une semaine d'usage)
→ H9 (recette PhotoCraft) — **H6 à H9 sont encore ouverts** et appartiennent au harness 1.1.
0.1 : H10 (après L1 : core intact) → H11 (après L2 : geler le contrat 0.1.0) → H12 (après vague 1 :
juger GlyphCraft) → H13 (après vague 2 : GlitchCraft vivant) → H14 (L22 : recette PhotoCraft puis
DesignCraft).

## Budgets et déviations

- Budgets par tâche : **3 retries de gates, 2 cycles de revue**, puis déviation.
- Classes de déviation : E1 (ambiguïté), E2 (défaut de contrat), E3 (scope — déclarée par G4/
  relecteur, une déclaration n'autorise rien), E4 (blocage technique), E5 (environnement), E6
  (régression, 1.1+), E7 (produit, relecteur/humain), E8 (fuite d'abstraction core→app, 0.1), E9
  (couplage hôte, 0.1 : chaque app marche seule). Protocole complet : `v1.0/DEVIATIONS.md` +
  `lattice/DEVIATIONS.md`.
- `STATE.md` n'est mis à jour que par l'orchestrateur, avec preuve (gates verts, commit). La carte
  L22 remet son résumé d'acceptation à l'orchestrateur, qui le reporte.

## Conventions de travail

- Build sur la **machine Windows** de l'utilisateur (Python 3.13.18, venv `.venv`, hôtes ArtCraft
  pour les cartes pont et l'acceptation). La machine Linux (Hermes) prépare et pousse.
- Livraison : commit + **push direct sur master** ; l'utilisateur tire sur Windows.
- Chemin critique de la suite : **L1 → L2 → L12/L20 → L21 → L22**. Toujours prioriser L1 puis L2.
- Concurrence max 4, deux cartes ensemble seulement si `owns` disjoints ; L1 démarre seul.
- Contrat 0.1.0 : brouillon jusqu'à H11 (gel). Tout changement passe par `DEVIATIONS.md`, jamais
  directement dans le code.
