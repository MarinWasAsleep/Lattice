Tu es l'analyste produit senior de la suite Lattice. Tu as rendu le verdict H13 ce matin, et
l'humain t'a délégué la décision. Les cartes que tu avais demandées sont livrées : juge-les.

## Ce que tu avais dit (rappel de ton propre verdict)

> « OUI SOUS CONDITIONS. Aujourd'hui, Glitch est un très bon éditeur de pile d'effets, mais il
> n'est pas encore vivant. Pour qu'il le devienne, il ne faut pas de timeline. Il faut trois
> choses : brancher la boucle dans l'application, faire respecter les verrous de seed par l'axe
> `seed`, et corriger le bord du CRT. »

Tu avais posé 5 questions, toutes tranchées en option 1 :
- Q1 : `render_loop` reçoit une fonction de rendu injectable, Glitch passe `document.render_rgb8`,
  verbe CLI `loop`, entrée GIF/APNG à l'export
- Q2 : les modules verrouillés gardent leur flux sur toutes les frames
- Q3 : 4e axe `param` (un paramètre de A à B et retour, boucle sans raccord)
- Q4 : le bug CRT passe avant le gel H13
- Q5 : une planche de 4 GIF sur source nette, image 0 == PNG, vérifiée à l'œil

## Ce qui a été livré

**L24 — bug CRT.** Le masque de phosphores est maintenant appliqué APRÈS la courbure (les rayures
vivent en espace écran). Mesures sur le rendu réel du preset `crt_finish` : écart rouge/bleu des
8 premières colonnes +43,3 → +15,3 ; des 8 dernières −26,5 → +1,3 ; variance spatiale des colonnes
de bord 24,1 → 33,0 et 19,6 → 31,0.

**L25 — boucle branchée par injection.** `render_loop(..., render_fn)` ; Glitch passe
`document.render_rgb8` + son RenderContext. Verbe CLI `loop` (sans Qt), entrée GIF/APNG à l'export.
Preuve : frame 0 d'une boucle == PNG du même preset, écart **0** (identité octet).

**L26 — verrous sur l'axe seed.** Les 36 tests du codeur passaient alors que le cas le plus courant
ne variait pas ; défaut corrigé. Mesure sur deux effets `noise` : sans verrou **3/3 frames
distinctes**, tout verrouillé 1/3 (figé, voulu).

**L27 — 4e axe `param`.** `axis="param"` + `param="<effet>.<clé>"`, `from_value`, `to_value`,
`curve="sin"|"linear"`. Sin = période complète, frame[0] == frame[count-1]. Mesure sur
`channel_shift.amount` 0→40 : écart **236/255 sur 1,2 million de pixels** entre frame 0 et frame 1.
Le même preset en axe `seed` reste figé (1/6) : c'est ce que Q3 devait résoudre.

## Les pièces à juger

Quatre boucles de 8 frames, 720×900, à partir des quatre presets livrés, sur la même photo :

1. `/home/mar1/Lattice/harness/lattice/docs/h13/glitch_01_vhs_soft.gif` — VHS soft (NTSC + scanlines)
2. `/home/mar1/Lattice/harness/lattice/docs/h13/glitch_02_channel_rift.gif` — Channel rift
3. `/home/mar1/Lattice/harness/lattice/docs/h13/glitch_03_sort_echo.gif` — Sort echo (pixel sort + feedback)
4. `/home/mar1/Lattice/harness/lattice/docs/h13/glitch_04_crt_finish.gif` — CRT finish (celui que tu avais vu cassé)

Et, si tu ne peux pas lire l'animation, **quatre planches de frames** (4 moments de chaque boucle
côte à côte : frames 0, 2, 5, 7) — ce sont de vrais PNG, ouvre-les :

- `.../h13/planches/glitch_01_vhs_soft_frames.png`
- `.../h13/planches/glitch_02_channel_rift_frames.png`
- `.../h13/planches/glitch_03_sort_echo_frames.png`
- `.../h13/planches/glitch_04_crt_finish_frames.png`

Mesures objectives des planches (écart max vs frame 0, /255) : VHS 125/192/222, Channel rift
151/196/221, Sort echo 154/148/144, CRT 118/156/173. Les 4 GIF ont 8 frames toutes distinctes.

Code modifié, si tu veux vérifier (lecture seule) : `lattice_core/animation.py`, `lattice_core/effects/crt.py`,
`lattice_glitch/document.py`, `lattice_glitch/export_actions.py`, `lattice_glitch/cli.py`.
Le contrat a reçu un amendement : `§20` liste maintenant 4 axes (seed, offset, iterations, param),
toujours sans timeline et sans vidéo.

## Ce que je te demande

1. **Le bug CRT est-il réellement corrigé ?** Regarde la planche 04 : les bandes rouge et bleue de
   bord ont-elles disparu, et le rendu est-il devenu ce qu'un écran CRT doit être ?
2. **Glitch est-il vivant, maintenant ?** Verdict net. Si non, dis précisément ce qui manque encore —
   pas une liste de souhaits, ce qui empêche la démonstration.
3. **Le mouvement est-il le bon ?** Un effet qui bouge n'est pas forcément un effet qui vit : regarde
   les planches et dis si ce que tu vois est du glitch crédible ou du bruit gratuit. Nomme les presets
   qui, selon toi, ne méritent pas d'être dans la vitrine.
4. **Les 4 GIF sont-ils une preuve suffisante pour clore H13 ?** Ou faut-il autre chose (une source
   nette, un preset supplémentaire, une durée, un raccord) ?
5. **2 à 4 questions à trancher par l'utilisateur** si quelque chose reste ouvert, avec options et
   recommandation.

## Règles

- Français, franc, sans flatterie. Si c'est raté, dis-le : un verdict complaisant coûte plus cher
  qu'un verdict dur.
- Ce que tu n'as pas pu observer, dis-le (« établi par les mesures », « non observable »).
- Lecture seule : ne modifie rien, ne lance aucun build.
