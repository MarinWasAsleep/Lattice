# DÉMARRAGE — transférer et lancer le harness Lattice 0.1 sur Windows

Tout le travail de préparation (graph des agents, routage des cartes, prompt L1) vit dans ce dépôt.
La machine de build est **Windows** (Python 3.15.2, venv `.venv`, numpy 2.5.4, numba 0.68.1,
Pillow 13.0.0, PySide6 6.12.0, pytest 9.2.0, ruff 0.17.4 — voir `harness/lattice/STATE.md`).
Sur la machine Linux, on ne fait que préparer et pousser.

Le graph de référence : ouvrir `harness/lattice/docs/graph.html` (export PNG : `docs/graph.png`).
Il répond à « **par quel agent ?** » : la vue ① est la boucle (orchestrateur → codeur → gates →
relecteur → humain), la vue ② est la répartition des 22 cartes par vague et par catégorie d'agent.

## 1 · Transfert

```powershell
cd C:\path\to\projects
git clone https://github.com/MarinWasAsleep/Lattice.git
cd Lattice
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest ruff
```

État attendu avant de lancer quoi que ce soit :

- `python -m pytest` → **622 tests verts** (état `5f3a7f4`)
- `ruff check .` → propre
- `python tools\check_contract.py` → OK
- Les hôtes ArtCraft (PhotoCraft 0.22.0, DesignCraft, PdfCraft) ne sont nécessaires que pour les
  cartes pont et l'acceptation (L5, L22) et les vérifications visuelles H3-H4. Le reste tourne sans eux.

## 2 · Qui fait quoi (rôles)

| Rôle | Qui | Ce qu'il fait | Ne fait jamais |
|---|---|---|---|
| Orchestrateur | Hermes (session TUI) | planifie (≤4 en parallèle, owns disjoints), génère les prompts, court les gates, tient `STATE.md`, applique le protocole de déviation | de code produit |
| Codeur | sous-agent routé via la chaîne OMH (`omh_delegate_route`, catégorie du champ `executor` des cartes) | une carte à la fois ; sort `FILE` + `NOTES` + `DEVIATIONS` | rien hors ses fichiers `owns` |
| Relecteur | catégorie OMH `review` | verdict `PASS` / `FIX` / `ESCALATE` (JSON), contrats avant tests | écrire du code |
| Humain (toi) | toi | checkpoints H1-H5, décisions de déviation E1-E9, gèle le contrat après H2 | — |

Catégories des cartes (legende du graph) : ultrabrain (L1, L7) · architect (L2) · deep (L3, L9, L17) ·
deep-work (L12, L20) · capable (le reste) · quick (L16). Toutes les relectures passent par `review`.

## 3 · Ordre de lancement

1. **KICKOFF** — donne à l'orchestrateur (Hermes) le prompt `harness/lattice/prompts/ORCHESTRATOR.md`
   avec l'EVENT `kickoff`. Il vérifie le contrat et génère le prompt codeur de L1. L1 démarre **seul**.
2. **L1** — remets le prompt déjà généré `harness/lattice/prompts/generated/L1-coder-attempt-1.md`
   à l'exécuteur (sous-agent routé `ultrabrain`). Le prompt impose de committer les baselines PNG
   (`tests/data/baseline/`) **avant** de toucher au code : c'est la condition du gate G5.
3. **Gates** (orchestrateur, terminal) : G1 ruff · G2 pytest · G3 check_contract · G4 fichiers `owns` ;
   +G5 régression du core (baselines au bit près) · G6 renderers · G7 parité CLI/GUI.
   Échec → retry ≤ 3, sinon déviation.
4. **Relecture** (catégorie `review`) : verdict PASS/FIX/ESCALATE, retry ≤ 2.
5. **H1 (toi)** : vérifier que Lattice Dither est intact et que `lattice-core` s'installe seul
   (`pip install -e .` sans Qt : numpy + numba + Pillow uniquement, `import lattice_core` OK).
6. Vague 0 en parallèle (L2-L5, ≤ 4 cartes) → **H2** : relire et **geler** le protocole `CellRenderer` §3.
7. Vagues 1 (glyphes) et 2 (glitch), indépendantes → **H3** (ouvrir GlyphCraft, juger) puis **H4**.
8. Vague 3 séquentielle : L21 → L22 (recette PhotoCraft puis DesignCraft) → **H5**.

## 4 · Règles qui ne se négocient pas

- `STATE.md` n'est mis à jour que par l'orchestrateur, avec preuve (gates verts, commit).
- Deux cartes ne tournent en parallèle que si leurs ensembles `owns` sont disjoints (max 4).
- Chemin critique : **L1 → L2 → L12/L20 → L21 → L22**. Toujours prioriser L1 puis L2.
- Déviations E1-E9 : si un codeur déclare une E8 (fuite core→app) ou E9 (dépendance à un hôte),
  ne jamais accepter un contournement — remonter à l'humain.
- Le contrat 0.1.0 est un brouillon jusqu'à H2. Tout changement de contrat se fait par
  `DEVIATIONS.md`, jamais dans le code.

## 5 · Après chaque carte

L'orchestrateur met `STATE.md` à jour (table des tâches + journal), enregistre le commit, et pousse
(`git push origin master`). La machine Linux (ou n'importe quelle session Hermes) peut ensuite
reprendre le fil avec `STATE.md` → prochaine carte prête.
