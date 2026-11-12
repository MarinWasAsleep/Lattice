# DitherCraft : harness 1.1 — de l'outil qui marche à l'outil qu'on utilise

Le harness 1.0 a construit un produit complet et correct : 33 algorithmes, 9 effets, 11 palettes,
aperçu temps réel, presets, pont PhotoCraft, 622 tests. Il répondait à la question « est-ce que ça
marche ». Le harness 1.1 répond à une autre question : **est-ce que ça vaut le coup de l'ouvrir
plutôt qu'un autre outil, dans le plus de situations possible.**

Ce dossier est la suite. Il ne remplace pas le 1.0 : le contrat 1.0 reste en vigueur pour les
sections §1 à §11, et ce dossier n'ajoute que ce qui manque.

## Ce qui change par rapport au 1.0

| Axe | 1.0 | 1.1 |
|---|---|---|
| Objectif | Couvrir le contrat | Gagner en qualité de sortie, en couverture de workflow, en plaisir d'usage |
| Critère de réussite | Les gates passent | Un utilisateur qui n'a jamais vu l'outil obtient un bon résultat en moins d'une minute, et un utilisateur avancé peut l'automatiser |
| Revue | Proportionnée au risque | Idem, plus une revue « produit » sur les cartes d'ergonomie |
| Nombre de cartes | 18 | 16 (T17 à T32) |
| Vagues | 4 | 4 (vagues 4 à 7) |

## Les quatre questions auxquelles le 1.1 répond

1. **La sortie est-elle bonne ?** Aujourd'hui la correspondance couleur est en distance RVB naïve,
   ce qui rend les tramages boueux sur les petites palettes. Le halftone est faux (une tuile de
   seuil, pas un écran). Il n'y a aucun réglage de force. → Cartes T17 à T21.
2. **Est-ce que ça s'insère dans un vrai flux de travail ?** Aujourd'hui : une image à la fois, à la
   main, en GUI seulement. Pas de CLI, pas de lot, pas de vectoriel, pas d'impression, pas
   d'animation. → Cartes T22 à T25.
3. **Est-ce agréable ?** Pas de galerie pour choisir un algorithme, pas d'annulation, pas de
   glisser-déposer, interface anglaise. → Cartes T26 à T29.
4. **Est-ce robuste sur de vraies sources ?** Un document PhotoCraft redimensionné ou compressé
   arrive avec de l'anti-aliasing et du bruit JPEG, et le tramage amplifie les deux. → Cartes T30
   à T32.

## Fichiers

| Fichier | Lu par | Rôle |
|---|---|---|
| `CONTRACT.md` | codeur (extraits), relecteur (extraits), orchestrateur | Contrat 1.1.0 **gelé** en **delta** : §12 à §25. §1 à §11 du 1.0 restent en vigueur. |
| `TASKS.md` | orchestrateur | Les 18 cartes T17 à T34 : dépendances, vagues, fichiers possédés, critères d'acceptation. |
| `STATE.md` | orchestrateur, toi | Registre vivant. |
| `DEVIATIONS.md` | orchestrateur, relecteur, toi | Protocole (inchangé) + registre 1.1. |
| `prompts/` | orchestrateur, codeur, relecteur | Gabarits, adaptés au 1.1. |

## Graphe de dépendances

```
T17 (spec v2 + presets v2 + conditionnement)   ← chemin critique, tout en dépend
 ├─ VAGUE 4, en parallèle (fichiers disjoints) :
 │   T18 métrique couleur      T19 force de tramage
 │   T20 halftone v2           T21 authoring de palette
 ├─ VAGUE 5, en parallèle :
 │   T22 CLI + lot             T23 export SVG
 │   T24 export impression     T25 animation + vidéo
 ├─ VAGUE 6, en parallèle :
 │   T26 galerie d'algorithmes T27 annulation + raccourcis + glisser-déposer
 │   T28 localisation FR       T29 performance et grandes images
 └─ VAGUE 7, séquentielle :
     T30 Pixel Snapper + dé-tramage → T31 pont v2 → T32 intégration et recette
```

- **Chemin critique** : T17 → T18/T19/T20 → T32. Priorise toujours T17.
- **Seules** : T17 (tout en dépend), T32 (câblage global).
- **Concurrence** : 4 maximum, comme en 1.0.
- T28 (localisation) ne dépend de rien : elle peut tourner à n'importe quel moment et sert de
  remplissage quand une vague est bloquée.

## Gates

G1 à G4 inchangés (ruff, pytest, check_contract, propriété des fichiers). Deux gates nouveaux :

- **G5 compatibilité des presets** : tout preset de `presets/` écrit en version 1 se charge encore
  et produit la même image qu'avant le 1.1 (comparaison pixel à pixel sur 3 presets témoins).
  C'est le gate qui empêche le 1.1 de casser ce que le 1.0 a livré.
- **G6 parité CLI / GUI** : pour un même preset et une même image, `dithercraft.cli render` et le
  rendu GUI donnent des octets identiques. C'est le gate qui empêche les deux chemins de diverger.

## Points de contrôle humains

| Id | Quand | Ce que tu fais |
|---|---|---|
| H5 | Après T17 | Relire le contrat 1.1 et le geler. C'est la décision la plus rentable du projet, comme H1. |
| H6 | Après la vague 4 | Ouvrir l'outil sur trois images réelles (une photo, un pixel art existant, un scan) et juger la sortie. |
| H7 | Après la vague 5 | Passer une vraie image par la CLI et par l'export impression. |
| H8 | Après la vague 6 | Utiliser l'outil une semaine sans y penser. Noter tout ce qui agace. |
| H9 | T32 | Recette complète dans PhotoCraft. |

## Risques

| Id  | Risque                                                                             | Parade                                                                                                                                                    |
| --- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R8  | La métrique OKLab/LAB2000 coûte trop cher en calcul et casse l'aperçu temps réel   | T18 impose un budget : 1024×1024, K=16, sous 150 ms après warm-up. Sinon repli sur une LUT 3D précalculée.                                                |
| R9  | Le halftone CMJN ne rentre pas dans le contrat « algorithme → indices »            | T20 le traite comme un **effet** de post-traitement, pas comme un algorithme. Décision prise dans le contrat §15, pas laissée au codeur.                  |
| R10 | L'export SVG explose en taille sur les grandes images                              | T23 impose un plafond : 2048×2048, 16 couleurs, fichier sous 8 Mo, sinon fusion des cellules par rectangle.                                               |
| R11 | La vidéo dépend de ffmpeg, absent chez l'utilisateur                               | T25 : GIF via Pillow toujours disponible, MP4 seulement si ffmpeg est trouvé, message clair sinon. Aucune dépendance ajoutée.                             |
| R12 | La localisation FR casse les tests qui cherchent des chaînes anglaises             | T28 : les tests passent par la fonction `tr()`, jamais par une chaîne littérale. Revue stricte sur ce point.                                              |
| R13 | L'annulation (T27) et l'intégration (T32) se marchent dessus dans `main_window.py` | Elles sont dans deux vagues différentes et ne sont jamais concurrentes.                                                                                   |
| R14 | Le Pixel Snapper invente une grille sur une photo qui n'en a pas                   | T30 : si la confiance de détection est sous un seuil, ne rien faire et le dire. Un pré-traitement qui abîme une photo est pire que pas de pré-traitement. |

## Comment démarrer

1. Lire `CONTRACT.md` §12 à §24. Si une décision ne te va pas, c'est maintenant qu'il faut la
   changer, pas après H5.
2. Lancer l'orchestrateur avec `prompts/ORCHESTRATOR.md`, section KICKOFF.
3. T17 d'abord, seule. Puis la vague 4 en parallèle.

## Ce que le 1.1 ne fait pas, volontairement

- Pas de nouvelle dépendance. Ni scipy, ni opencv, ni scikit-image, ni ffmpeg obligatoire.
- Pas de réseau dans le cœur. L'import de palettes se fait par fichier ou par copier-coller de
  codes hexadécimaux ; un script séparé, lancé à la main, peut remplir la bibliothèque.
- Pas de renommage du projet. Décision reportée, elle n'a aucun impact sur le code.
- Pas de refonte de l'architecture. Le 1.0 est sain ; le 1.1 l'étend.
