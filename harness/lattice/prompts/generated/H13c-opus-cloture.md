Lis ces planches de frames, en citant les chemins absolus :

- /home/mar1/Lattice/harness/lattice/docs/h13/new/planches/glitch_01_vhs_soft_frames.png
- /home/mar1/Lattice/harness/lattice/docs/h13/new/planches/glitch_02_channel_rift_frames.png
- /home/mar1/Lattice/harness/lattice/docs/h13/new/planches/glitch_03_sort_echo_frames.png
- /home/mar1/Lattice/harness/lattice/docs/h13/new/planches/glitch_04_crt_finish_frames.png

La source est /home/mar1/Lattice/docs/bytemosh/00_source.png (dégradé vertical + rayures de 12 px,
anneau jaune, rectangle vert, texte blanc). Chaque planche montre 4 frames d'une boucle de 8
(frame 0, 2, 5, 7), côte à côte, pour que tu puisses juger le MOUVEMENT et pas seulement l'image fixe.

## Le contexte de ce que tu avais demandé

À ton premier verdict H13 tu avais refusé de clore « Lattice Glitch vivant » en posant quatre
conditions. Voici où elles sont :

1. **La géométrie CRT** — tu avais relevé : « ~60 lignes du bas recopient la dernière rangée »,
   « ~50 colonnes étirées », « aucun coin noir ». CORRIGÉ : `_curve` a maintenant une zone de
   validité, tout échantillon hors de l'image source devient noir au lieu d'écraser le bord.
   Mesuré sur le GIF de crt_finish : coins bas-gauche et bas-droit à 0,0,0 ; les 10 dernières
   lignes ne sont plus identiques entre elles (variance 11 à 14 au lieu de 0) ; colonnes de bord
   noires.
2. **Aucun GIF n'utilisait l'axe `param`** — tu avais raison, le CLI ne l'exposait même pas (bug
   corrigé). Les 4 GIF sont maintenant rendus avec `--axis param` : crt.curvature 0,05→0,35,
   ntsc.snow 0,02→0,30, channel_shift.amount 2→24, feedback.decay 0,3→0,9.
3. **Le raccord de boucle dupliquait une frame** — tu avais écrit « la même image affichée deux
   fois de suite ». CORRIGÉ : `t = index / count` au lieu de `index / (count - 1)`. Mesuré sur
   les 4 GIF : frame 0 ≠ frame 7, et 5 images distinctes sur 8 (la symétrie aller-retour d'une
   courbe sinusoïdale, c'est l'attendu).
4. **La source était floue (photo de bougé)** — REMPLACÉE par une source nette fabriquée exprès,
   où chaque déplacement de ligne est visible.

## Ce que je te demande

Un verdict sur la clôture de H13, « Lattice Glitch est-il vivant, ou est-ce encore un filtre ? »

1. Pour chaque planche : est-ce que ça bouge de façon vivante, ou est-ce un filtre appliqué à une
   image fixe ? Note /10. Précise ce qui est conventionnel dans le genre et ce qui est authentique.
2. La boucle est-elle propre (pas d'à-coup au raccord) ?
3. Le CRT : la silhouette de tube est-elle enfin crédible ? Reste-t-il un artefact de bord ?
4. **Verdict explicite** : H13 est-il CLOS, ou faut-il encore une carte ? Si tu refuses de clore,
   donne les conditions précises, mesurables, et dis lesquelles sont des cartes de fond.
5. Si tu vois des défauts, sois précis : quel preset, quel réglage, quel symptôme visible.

Tu peux lire le code si ça t'aide (/home/mar1/Lattice/lattice_core/effects/crt.py,
animation.py). Écris en français, direct, sans ménagement.
