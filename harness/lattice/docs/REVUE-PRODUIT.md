# Revue produit — verdicts Opus (Claude opus-5-5, effort medium)

Deux analyses produit commandées le 2026-11-16, exécutées par Claude Opus
(médian, ~1,4 $ chacune) : une sur l'application Lattice Dither livrée, une sur
la suite dans son ensemble (contrat 0.1 + cartes + marché). Verdicts bruts dans
`docs/analyses/app-verdict.json` et `docs/analyses/suite-verdict.json`.

Méthode : trois passes Claude Opus (opus-5-5, effort medium, ~3,4 $ au total).
L'analyse « app » s'est appuyée sur le code UI réel (main_window, panels,
export, presets) ; une passe de confirmation visuelle a ensuite porté les 5
captures d'écran réelles (verdict : `docs/analyses/visio-verdict.json`) —
elle confirme l'essentiel, aggrave plusieurs constats et corrige quelques
points. L'analyse « suite » s'est appuyée sur le contrat 0.1, les cartes
L1-L23 et la recherche marché (verdict : `docs/analyses/suite-verdict.json`).

## Protocole des checkpoints de jugement (H11-H13)

Le jugement humain reste la décision ; l'analyse ne l'est plus. Aux checkpoints
où l'humain doit juger, l'orchestrateur commande une analyse à **Claude Opus
(medium)** via le gabarit `prompts/ANALYSTE-PRODUIT.md` :

1. **Objet** : contrat (H11 — gel du §3/du contrat 0.1) ou interface (H12/H13 —
   captures d'écran réelles, parcours scriptés, code UI).
2. **Livrable** : un verdict JSON (synthese, findings avec preuves, manques,
   superflus) **plus un bloc `questions_pour_le_decideur` obligatoire** —
   2 à 5 questions, chacune avec options, recommandation et conséquence.
3. **Humain** : ne lit que les questions et tranche. Il n'analyse rien de zéro ;
   s'il veut creuser, il relance l'analyste, pas sa propre analyse.
4. **Trace** : verdicts bruts dans `docs/analyses/` (app-verdict,
   visio-verdict, suite-verdict), synthèse dans REVUE-PRODUIT.md, décisions
   dans STATE.md.

C'est exactement le pattern déjà appliqué pour ces trois passes : l'analyse a
été entièrement déléguée (3,4 $), l'humain n'a eu qu'à arbitrer.

## Verdict app (résumé)

Le moteur est solide (1212 tests) ; l'application est « organisée comme le
contrat, pas comme le parcours de l'artiste ». L'objectif officiel du 1.1
(« un bon résultat en moins d'une minute ») n'est pas atteint.

- **Désormais 3 bloquants** (les deux premiers sont des défauts de résultat
  silencieux, confirmés par le code ; le troisième est venu des captures) :
  1) export avancé (SVG/impression/GIF/vidéo) sur l'aperçu plafonné à 1024 px
  au lieu d'un rendu pleine résolution — nuance visuelle : la barre n'expose
  que « Exporter en PNG » (le bon chemin) ; 2) « GIF animé »/« Vidéo »
  produisent un fichier d'une seule image dans la GUI ; 3) l'indicateur
  « Préréglage 1/12 : 01_gameboy.json » **ment dans les cinq états** (affiché
  sans image, sur un rendu Floyd-Steinberg N&B, et figé après changement
  d'algorithme et de palette) — c'est le piège le plus visible pour H12.
- **Aggravations visuelles** : la galerie occupe ~500 px de large (pas 240) —
  le canevas n'a que ~35 % de la fenêtre, vide au démarrage ; la barre
  d'outils déborde à 1280 px (« Préparer la source » et « Retirer la trame »
  hors champ : piège pour le scan) ; la galerie est figée (vignettes
  identiques, jamais sur l'image/palette courante, aucun surlignage de
  l'algorithme actif) ; le bouton « Ajouter ▾ » des effets est placé sous la
  liste « Après tramage » alors qu'il vise « Avant » — l'écran contredit le
  comportement ; les boutons PhotoCraft restent actifs malgré
  « PhotoCraft : déconnecté » ; zone « Couleurs » vide pour une palette EGA
  de 16 couleurs.
- **Corrections apportées par les captures** : le groupe « Extraire de
  l'image » est bien grisé quand la source est « Intégrée » (moins confus que
  le code ne le laissait croire) ; les pièges d'export restent établis par le
  code seul (non visibles sur les captures, le menu Fichier n'étant pas
  ouvert).
- **8 majeurs**, tous d'interface : état vide sans consigne, presets ◀/▶ à
  l'aveugle avec noms de fichiers techniques, barre de 19 actions plates,
  panneau Algorithme surchargé (la force noyée), galerie en doublon, bouton
  « Ajouter » d'effet visant la liste *avant* tramage, noms de palettes bruts
  (`cga_0_high`, `kmeans`), incohérence « Préréglage 1/12 » au démarrage.
- **Aucun constat ne touche le moteur** : 2-3 cartes d'ergonomie suffisent
  (priorités 1-9 du fichier visio-verdict.json — la n°1 est désormais
  l'indicateur de preset ; la passe visuelle exécute 10 tours, 0,71 $).

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

## Décisions prises avant H11 (2026-11-16, humain sur recommandations Opus)

S1, S2, S3, S4 et S5 sont **tranchés et appliqués au contrat** (voir `DEVIATIONS.md` AMD-002..006,
et CONTRACT.md §5 / §3 / §6 / §2). La carte **L-UI** est créée dans TASKS.md (vague 0, après L5).
Reste ouvert : le **périmètre marché** (glyphes/glitch comme paris assumés vs intégrer
séparations/animation — la décision éclairée par la recherche ciblée attendue avant H12).

## Cartes d'ergonomie dérivées (app) — 3 cartes au fil de l'eau

- C-EXP : export unique pleine résolution ; GIF/vidéo masqués ou branchés sur
  une vraie séquence (bloquants 1 et 2).
- C-LOOK : état vide guidant + appliquer réellement le preset 1 au démarrage +
  panneau « Looks » (vignettes sur l'image courante, noms par look) + presets
  migrés en v3 avec meta.name.
- C-ORDRE : hiérarchie de la barre d'outils, panneau Algorithme en
  Essentiel/Préparation/Avancé, effet par défaut « après », noms de palettes
  lisibles, langue dans l'UI.
