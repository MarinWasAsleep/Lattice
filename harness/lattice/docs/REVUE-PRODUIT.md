# Revue produit — verdicts Opus (Claude opus-5-5, effort medium)

Deux analyses produit commandées le 2026-11-16, exécutées par Claude Opus
(médian, ~1,4 $ chacune) : une sur l'application Lattice Dither livrée, une sur
la suite dans son ensemble (contrat 0.1 + cartes + marché). Verdicts bruts dans
`docs/analyses/app-verdict.json` et `docs/analyses/suite-verdict.json`.

Méthode : l'analyse « app » s'est appuyée sur le code UI réel (main_window,
panels, export, presets) — les captures d'écran n'ayant pas été attachées, une
passe de confirmation visuelle est en cours (verdict attendu :
`docs/analyses/visio-verdict.json`). L'analyse « suite » s'est appuyée sur le
contrat 0.1, les cartes L1-L23 et la recherche marché.

## Verdict app (résumé)

Le moteur est solide (1212 tests) ; l'application est « organisée comme le
contrat, pas comme le parcours de l'artiste ». L'objectif officiel du 1.1
(« un bon résultat en moins d'une minute ») n'est pas atteint.

- **2 bloquants** (défauts de résultat silencieux) : export avancé
  (SVG/impression/GIF/vidéo) sur l'aperçu plafonné à 1024 px au lieu d'un
  rendu pleine résolution ; « GIF animé »/« Vidéo » produisent un fichier
  d'une seule image dans la GUI (l'animation n'existe que côté CLI).
- **8 majeurs**, tous d'interface : état vide sans consigne, presets ◀/▶ à
  l'aveugle avec noms de fichiers techniques, barre de 19 actions plates,
  panneau Algorithme surchargé (la force noyée), galerie en doublon, bouton
  « Ajouter » d'effet visant la liste *avant* tramage, noms de palettes bruts
  (`cga_0_high`, `kmeans`), incohérence « Préréglage 1/12 » au démarrage.
- **Aucun constat ne touche le moteur** : 2-3 cartes d'ergonomie suffisent
  (voir priorités 1-5 du fichier JSON).

## Verdict suite (résumé)

La thèse tient pour Dither et la moitié de Glyph ; **elle ne décrit pas
Glitch**, et cinq défauts sont structurels — ils seront figés par L2
(CellRenderer) et L4 (preset v3) si on ne les tranche pas avant H11 :

| # | Objet figé | Défaut | Conséquence |
|---|---|---|---|
| S1 | pipeline §5 | impose grille + palette + algorithme, pas de « aucun » | pixel sort / VHS postérisent d'abord la photo |
| S2 | coverage §3 | dérivée de la luminance de la palette quantifiée | palette N&B → rampe de 70 glyphes n'en utilise que 2 ; texte-halftone binaire |
| S3 | pipeline | tramage à la résolution de la cellule, pas du sous-point | braille/sextants privés des 33 algorithmes |
| S4 | preset v3 §6 | effets sans avant/après, palette sans source d'extraction, pas de champ masque, polices par chemin (non portables), pas de taille de sortie | perte d'information vs l'existant ; §17 sans appui |
| S5 | UX partagée | aucune carte ne possède l'aperçu/le navigateur de presets/l'export/l'état du pont dans le core | L12/L20 réécrivent chacune une UI en héritant des défauts connus de Dither |

- **Marché vs périmètre** : aucune section glyphes/glitch dans la recherche
  marché (glyphes = priorité 2 n°20, glitch = une ligne de catalogue) ; les
  deux besoins les mieux documentés (vrai halftone/séparations §7.3, P1 n°8 ;
  stabilité temporelle/animation §7.5, P1) sont exclus par §20. À assumer
  explicitement, pas à subir.
- **Manques de parcours perçus** : Glyph sans sortie texte brut/ANSI/HTML
  (copier-coller) ; Glitch sans dimension temporelle = ne peut pas prouver
  H13 (« vivant, pas un filtre »).
- **Points forts transférables** : pont non bloquant, seed sérialisé, presets
  JSON lisibles, CLI headless, registres qui génèrent l'UI, discipline des
  gates (G7 bit-à-bit, G8 sur le registre).

## Décisions à prendre avant H11 (gel du contrat)

Le contrat 0.1 est un brouillon jusqu'à H11. Chaque ligne ci-dessous est une
décision explicite : amender le contrat, ou accepter la contrainte.

1. S1 — autoriser un algorithme « aucun » (ou un mode « brut ») dans le
   pipeline : les effets glitch traitent une image, pas une postérisation.
2. S2 — redéfinir `coverage` : soit depuis l'image source (avant quantification),
   soit par échelle de luminance de l'image ; à trancher avec le §3 avant L2.
3. S3 — tramer au niveau du sous-point pour les renderers bitmask/texte, ou
   documenter la limitation.
4. S4 — compléter le preset v3 (étapes avant/après, source d'extraction,
   masque, tailles de sortie, polices par nom+fallback) avant L4.
5. S5 — donner une carte « UI partagée » (widgets de preview/navigateur
   presets/export/pont) dans le core [ui], avant L12/L20.
6. Périmètre — assumer publiquement que glyphes/glitch sont paris, et différer
   ou intégrer les besoins P1 (séparations, animation) comme cartes hors contrats.

## Cartes d'ergonomie dérivées (app) — 3 cartes au fil de l'eau

- C-EXP : export unique pleine résolution ; GIF/vidéo masqués ou branchés sur
  une vraie séquence (bloquants 1 et 2).
- C-LOOK : état vide guidant + appliquer réellement le preset 1 au démarrage +
  panneau « Looks » (vignettes sur l'image courante, noms par look) + presets
  migrés en v3 avec meta.name.
- C-ORDRE : hiérarchie de la barre d'outils, panneau Algorithme en
  Essentiel/Préparation/Avancé, effet par défaut « après », noms de palettes
  lisibles, langue dans l'UI.
