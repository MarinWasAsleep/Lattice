# Lattice — harness 0.1 : d'un outil à une suite

Lattice Dither est un produit fini : 33 algorithmes, 9 effets, 11 palettes, aperçu temps réel,
presets JSON, pont PhotoCraft, 622 tests. Il répond à « est-ce que ça marche ». Lattice répond à
une autre question : **est-ce qu'une même mécanique peut produire plusieurs outils qui se sentent
différents, s'installent séparément, et se branchent tous sur ArtCraft.**

Ce dossier est le plan de la suite. Il ne remplace pas le harness 1.0 ni le 1.1 de Lattice Dither :
ceux-ci restent en vigueur pour l'app de tramage, qui devient le premier consommateur du core.

## La thèse

Tout outil de cette famille fait la même chose :

```
échantillonner une cellule → quantifier vers une palette → tramer → rendre la cellule
```

Seul le dernier étage change. Un pixel carré, un glyphe de rampe, un glyphe apparié par forme, un
bitmask braille, un paragraphe de texte, une tuile. Lattice Dither possède déjà les trois premiers
étages, testés. **Le coût marginal d'un nouveau studio est donc un renderer plus un catalogue**,
pas un nouveau moteur.

C'est l'abstraction `CellRenderer` (§3 du contrat). C'est le pari architectural du projet, et c'est
le même pari que Studio AAA a fait commercialement avec Dither Boy, Script Slayer et Flareware.

## Ce que Lattice n'est pas

- Pas un concurrent d'ArtCraft. C'est un **écosystème de plugins** pour ArtCraft.
- Pas un outil payant. MIT/Apache-2.0, gratuit pour tous, pour toujours.
- Pas une suite d'effets jetables. Chaque app doit être le meilleur outil libre de sa catégorie,
  pas le douzième.

## Les quatre questions auxquelles le harness 0.1 répond

1. **Le core peut-il être partagé sans casser Lattice Dither ?** Le code existe et il est couvert.
   L'extraction doit produire des rendus identiques au bit près, sinon on a perdu l'acquis.
   → Cartes L1 à L5.
2. **Les glyphes peuvent-ils dépasser le gadget ?** Le segment est saturé : Script Slayer est offert
   dans Dither Boy, Chafa et img2txt sont libres et excellents, ASCII Magic livre 100+ styles.
   La seule voie est ce que personne n'a combiné : appariement par forme avec vraie police, taille
   variable, rampes non-latines, texte-halftone, sortie vectorielle éditable. → Cartes L6 à L12.
3. **Le glitch peut-il être un instrument plutôt qu'un filtre ?** Le mécanisme qui rend un outil
   vivant est le tampon de rétroaction. Tout le reste s'y branche. L'anti-patron à éviter est le
   slider d'intensité unique. → Cartes L13 à L20.
4. **La suite se comporte-t-elle comme une suite ?** Presets qui circulent d'une app à l'autre,
   pont qui marche sur PhotoCraft et DesignCraft, installation indépendante. → Cartes L21 à L22.

## Fichiers

| Fichier | Lu par | Rôle |
|---|---|---|
| `CONTRACT.md` | codeur (extraits), relecteur (extraits), orchestrateur | Contrat 0.1.0 : §1 à §20. Remplace le contrat Lattice Dither pour tout ce qui est partagé ; §1 à §11 du 1.0 restent en vigueur pour l'app de tramage. |
| `TASKS.md` | orchestrateur | Les 22 cartes L1 à L22 : dépendances, vagues, fichiers possédés, critères d'acceptation. |
| `STATE.md` | orchestrateur, toi | Registre vivant. |
| `DEVIATIONS.md` | orchestrateur, relecteur, toi | Protocole et registre. |
| `prompts/` | orchestrateur, codeur, relecteur | Gabarits adaptés à la suite. |

## Graphe de dépendances

```
L1 (extraire lattice-core)  ← chemin critique, tout en dépend
 ├─ VAGUE 0, en parallèle après L1 :
 │   L2 CellRenderer + PixelRenderer   L3 métrique + palette
 │   L4 preset v3                      L5 pont généralisé
 ├─ VAGUE 1, glyphes (après L2) :
 │   L6 rampe de glyphes → L7 appariement par forme
 │   L8 bitmasks (braille/sextant/quadrant/demi-bloc)
 │   L9 texte-halftone
 │   L10 navigateur de jeux + rampes non-latines
 │   L11 export vectoriel
 │   L12 coquille GlyphCraft + pont
 ├─ VAGUE 2, glitch (après L2, indépendante de la vague 1) :
 │   L13 tampon de rétroaction → L14 déplacement → L15 tri de pixels
 │   L16 décalage de canal      L17 NTSC/VHS      L18 CRT/scanlines
 │   L19 graine + masques       L20 coquille GlitchCraft + pont
 └─ VAGUE 3, séquentielle :
     L21 échange de presets + galerie → L22 recette dans PhotoCraft et DesignCraft
```

- **Chemin critique** : L1 → L2 → L12/L20 → L22. Priorise toujours L1 puis L2.
- **Seules** : L1 (tout en dépend), L2 (les renderers en dépendent), L22 (câblage global).
- **Concurrence** : 4 maximum. Deux cartes ne tournent ensemble que si leurs ensembles `owns` sont
  disjoints.
- Les vagues 1 et 2 sont indépendantes : si les glyphes bloquent, le glitch avance.

## Gates

G1 à G4 sont repris du harness 1.0 (ruff, pytest, check_contract, propriété des fichiers). Trois
gates nouveaux, propres à la suite :

- **G5 régression du core** : après L1, Lattice Dither rend ses trois presets témoins exactement comme
  avant l'extraction, au bit près. C'est le gate qui empêche la suite de casser le produit existant.
- **G6 contrat des renderers** : chaque `CellRenderer` enregistré satisfait le protocole §3 sur une
  grille de test commune, vérifié en itérant le registre pour que tout renderer futur soit couvert
  d'office.
- **G7 parité CLI / GUI** : pour un même preset et une même image, le rendu CLI et le rendu GUI
  donnent des octets identiques, dans chaque app.

## Points de contrôle humains

| Id | Quand | Ce que tu fais |
|---|---|---|
| H1 | Après L1 | Vérifier que Lattice Dither est intact et que le paquet `lattice-core` s'installe seul. |
| H2 | Après L2 | Relire le protocole `CellRenderer` et le geler. C'est la décision la plus rentable du projet. |
| H3 | Après la vague 1 | Ouvrir GlyphCraft sur trois images réelles et juger. Si les glyphes ne convainquent pas, ne pas continuer. |
| H4 | Après la vague 2 | Ouvrir GlitchCraft et vérifier qu'il est vivant, pas un filtre. |
| H5 | L22 | Recette complète dans PhotoCraft puis DesignCraft. |

## Risques

| Id | Risque | Parade |
|---|---|---|
| R1 | L'extraction du core casse Lattice Dither | L1 impose des baselines PNG rendues **avant** de commencer, et G5 compare au bit près. |
| R2 | L'abstraction `CellRenderer` ne couvre pas le texte-halftone, qui n'est pas une grille | L9 est autorisée à produire une grille de cellules de tailles variables ; le protocole §3 le prévoit dès le départ. |
| R3 | L'appariement par forme est trop lent pour l'aperçu | L7 impose un budget : 1024×1024, 64 glyphes, sous 200 ms après pré-calcul des vecteurs de forme. Sinon table de correspondance précalculée. |
| R4 | Le tampon de rétroaction diverge ou explose en mémoire | L13 impose un decay < 1 strict et une normalisation par image ; test de stabilité sur 200 itérations. |
| R5 | NTSC/VHS demande trop de réglages pour rester utilisable | L17 impose un jeu de 6 presets nommés et un mode simple de 4 curseurs. |
| R6 | Les presets v3 divergent entre apps | L4 définit le format une fois ; L21 teste l'aller-retour entre les trois apps. |
| R7 | DesignCraft n'a pas la même surface de contrôle que PhotoCraft | L5 découvre la surface réelle avec `describe` et l'inscrit en amendement du contrat, sans rien inventer. |
| R8 | Le périmètre glitch complet est trop gros pour une v1 | Les cartes L13 à L18 sont indépendantes et livrables séparément ; L20 peut sortir avec un sous-ensemble. |

## Comment démarrer

1. Lire `CONTRACT.md` §1 à §20. Si une décision ne te va pas, c'est maintenant qu'il faut la
   changer, pas après H2.
2. Lancer l'orchestrateur avec `prompts/ORCHESTRATOR.md`, section KICKOFF.
3. L1 d'abord, seule. Puis la vague 0 en parallèle.

## Ce que le harness 0.1 ne fait pas, volontairement

- **Pas de vidéo.** Décision explicite. Le prompt de recherche vidéo est archivé dans
  `harness/research/video-research-prompt.md` pour plus tard.
- **Pas de matières physiques** (LEGO, perles, point de croix). Le rapport de recherche montre que
  c'est un vrai marché, mais ce n'est pas le sujet maintenant.
- **Pas de séparations d'impression** (CMJN, riso, encres spot). Le rapport montre que c'est le
  produit le plus défendable à terme ; il est hors périmètre ici.
- **Pas de nouvelle dépendance lourde.** numpy, numba, Pillow, PySide6. Rien d'autre.
- **Pas de réseau dans le core.** L'import de palettes se fait par fichier ou copier-coller.
