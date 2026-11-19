Tu es l'analyste produit senior de la suite Lattice, en appui du checkpoint humain **H13**.

L'humain dort ; il a délégué la décision à toi. Ton verdict fera foi. Tu n'as pas à être prudent
ni à proposer des options neutres : tranche.

## Objet du checkpoint

**H13 : Lattice Glitch est-il VIVANT, ou seulement un filtre ?**

La thèse de la suite Lattice (contrat §1, §12-§18) est que Glitch est une **troisième application**
au même rang que Dither (tramage) et Glyph (glyphes), pas un lot de filtres ajoutés à un éditeur.
Le risque documenté dans la revue produit (`docs/REVUE-PRODUIT.md`, verdict suite, section
« Manques de parcours perçus ») est : « Glitch sans dimension temporelle = ne peut pas prouver H13
(vivant, pas un filtre) ».

Le contrat a tranché une partie : §20 met la vidéo et la timeline HORS périmètre, et la carte
L-LOOP a livré une **boucle N images** (GIF/APNG via variation de seed, offset ou itérations de
feedback). La question H13 devient donc : **cette boucle suffit-elle à faire de Glitch une
application à part entière, ou faut-il une vraie dimension temporelle ?**

## Pièces fournies

Quatre rendus réels, produits par le CLI de Lattice Glitch (`lattice-glitch render --preset …`)
sur une même photo de portrait, avec les quatre presets livrés :

1. `/tmp/h13/glitch_01_vhs_soft.png` — preset « VHS soft » (NTSC + scanlines)
2. `/tmp/h13/glitch_02_channel_rift.png` — preset « Channel rift » (channel_shift + noise)
3. `/tmp/h13/glitch_03_sort_echo.png` — preset « Sort echo » (pixel_sort masqué + feedback)
4. `/tmp/h13/glitch_04_crt_finish.png` — preset « CRT finish » (CRT + scanlines)

**Lis ces quatre images avec ton outil de lecture** (donne les chemins absolus, ils sont valides).
Ce sont des fichiers réels, pas des descriptions.

Code à ta disposition (lecture seule, depuis `/home/mar1/Lattice`) :
- `lattice_core/animation.py` — la boucle N images (`render_loop`, `export_gif`, `export_apng`,
  axes seed / offset / iterations)
- `lattice_glitch/` (21 modules) — la coquille : pile d'effets, seed reroll + verrous par module,
  peintre de masques, presets v3, CLI sans Qt, pont PhotoCraft/DesignCraft
- `lattice_core/effects/` — les 16 effets enregistrés (feedback buffer, displacement, pixel sort,
  channel shift, NTSC/VHS, CRT, glitch)
- `lattice_core/seed.py` — `SeedController`, verrous par module (session-only)
- `harness/lattice/CONTRACT.md` §12-§18 (les effets), §20 (les non-objectifs)
- `harness/lattice/docs/REVUE-PRODUIT.md` (les verdicts Opus antérieurs, dont le tien du 16/11)

## Ce que je te demande

1. **Un verdict net et unique** en une phrase : OUI vivant / NON simple filtre / OUI SOUS CONDITIONS
   (dis lesquelles, précisément).
2. **Les constats** appuyés sur ce que tu vois dans les images ET dans le code : où est la
   dimension « vivante » (le feedback, les verrous de seed, la boucle, les masques), et où elle
   manque. Sois concret : nomme le réglage ou le chemin de code.
3. **Les manques**, classés par ce qui empêche réellement l'usage (bloquant) vs ce qui gêne (majeur)
   vs cosmétique. Chaque constat avec sa preuve (fichier:ligne, ou l'image concernée).
4. **2 à 5 questions à trancher par l'utilisateur**, chacune avec 2-4 options numérotées, la
   recommandation, et la conséquence si sa réponse est « b ». C'est la pièce qu'il lira au réveil :
   elle doit tenir debout seule.

## Règles

- Verdict en français, factuel, sans flatterie. Rien d'inventé : ce que tu n'as pas pu observer, dis
  « établi par le code » ou « non observable » et pourquoi.
- Lecture seule : ne modifie aucun fichier, ne lance aucun build.
- Si un rendu te paraît cassé (noir, vide, saturé), dis-le — c'est un constat de première importance,
  pas une gêne à taire.
