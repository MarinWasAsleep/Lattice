# DÉMARRAGE — installer l'environnement et lancer le harness sur cette machine

Le build de la suite Lattice vit maintenant sur **cette machine** (Linux Mint). Le repo vivant est
`~/Lattice`, l'index de référence est `harness/README.md` (à lire en premier), le graph « par quel
agent » est `harness/lattice/docs/graph.html` (+ PNG). La suite ArtCraft existe aussi sous Linux :
le pont s'exécute contre les hôtes Linux (cartes L5, L22), et Windows reste une cible de
publication (carte L23).

## 1 · Environnement (fait le 2026-11-16)

```bash
cd ~/Lattice
uv venv --python 3.13 .venv
uv pip install -r requirements.txt --python .venv/bin/python
```

État vérifié à cette installation : **1212 tests verts**, `ruff check .` propre,
`python tools/check_contract.py` OK — commit `b4b0aea` (portage Linux). Le gamma est appliqué par
table committée (`core/gamma_table.py`) : les rendus sont bit-identiques Windows ET Linux.

Les hôtes ArtCraft (PhotoCraft 0.22.0, DesignCraft) ne sont nécessaires que pour les cartes pont et
l'acceptation (L5, L22) et les vérifications visuelles H12-H13. Le reste tourne sans eux.

## 2 · Qui fait quoi (rôles unifiés)

| Rôle | Qui | Fait | Ne fait jamais |
|---|---|---|---|
| Orchestrateur | Hermes (cette session) | planifie ≤ 4 cartes (owns disjoints), génère les prompts, court les gates, tient `STATE.md`, applique DEVIATIONS | de code produit |
| Codeur | sous-agent routé par la chaîne OMH (catégorie = champ `executor` de la carte) | une carte à la fois, fichiers `owns` seulement | hors `owns` |
| Relecteur | catégorie OMH `review` | verdict PASS / FIX / ESCALATE, contrats avant tests | écrire du code |
| Humain (toi) | toi | checkpoints H10-H14, décisions de déviation E1-E9 | — |

Correspondance historique (DeepSeek/Sonnet) et registres : `harness/README.md`.

## 3 · Ordre de lancement

1. **KICKOFF** — donne à l'orchestrateur le prompt `harness/lattice/prompts/ORCHESTRATOR.md` avec
   l'EVENT `kickoff`. Il vérifie le contrat et génère le prompt codeur de L1. L1 démarre **seul**.
2. **L1** — remets le prompt déjà généré `harness/lattice/prompts/generated/L1-coder-attempt-1.md`
   à l'exécuteur (routé `ultrabrain`). Le prompt impose de re-rendre les baselines témoins au HEAD
   et de vérifier la conformité bit-à-bit avant de toucher au code (condition du gate G7).
3. **Gates** (orchestrateur, terminal) : G1 ruff · G2 pytest · G3 check_contract · G4 fichiers `owns` ;
   +G7 régression du core (baselines au bit près) · G8 contrats des renderers · G9 parité CLI/GUI.
   Échec → retry ≤ 3, sinon déviation.
4. **Relecture** (catégorie `review`) : verdict PASS/FIX/ESCALATE, retry ≤ 2.
5. **H10 (toi)** : vérifier que Lattice Dither est intact et que `lattice-core` s'installe seul
   (`uv pip install -e .` sans Qt : numpy + numba + Pillow uniquement, `import lattice_core` OK).
6. Vague 0 en parallèle (L2-L5, ≤ 4 cartes) → **H11** : relire et **geler** le protocole `CellRenderer` §3.
7. Vagues 1 (Lattice Glyph) et 2 (Lattice Glitch), indépendantes → **H12** puis **H13**.
8. Vague 3 séquentielle : L21 → L22 (recette PhotoCraft puis DesignCraft, hôtes Linux) → **H14**,
   puis L23 (packaging Windows + Linux).

## 4 · Règles qui ne se négocient pas

- `STATE.md` n'est mis à jour que par l'orchestrateur, avec preuve (gates verts, commit). La carte
  L22 remet son résumé JSON à l'orchestrateur, qui le reporte.
- Deux cartes ne tournent en parallèle que si leurs ensembles `owns` sont disjoints (max 4).
- Chemin critique : **L1 → L2 → L12/L20 → L21 → L22**. Toujours prioriser L1 puis L2.
- Déviations E1-E9 : une E8 (fuite core→app) ou E9 (dépendance à un hôte) ne se contourne jamais —
  remonter à l'humain.
- Le contrat 0.1.0 est un brouillon jusqu'à H11. Tout changement passe par `DEVIATIONS.md`, jamais
  dans le code.
- Les rendus sont bit-identiques Windows/Linux (tables committées). Si le gate G7 échoue sur une
  plateforme, c'est une vraie régression, pas une différence d'arrondi.

## 5 · Après chaque carte

L'orchestrateur met `STATE.md` à jour (table + journal), enregistre le commit et pousse
(`git push origin master`). N'importe quelle session Hermes reprend ensuite le fil avec `STATE.md`
→ prochaine carte prête.
