Lis ces trois images, en citant les chemins absolus :

- /tmp/starters/source.png — la source (portrait photographique, 720×900)
- /tmp/starters/planche_dither.png — les 4 starters Dither côte à côte, chacun étiqueté
- /tmp/starters/planche_glyph.png — les 4 starters Glyph côte à côte, chacun étiqueté

## Le contexte

Lattice est une suite de traitement d'image en trois apps : **Dither** (tramage vers une
palette), **Glitch** (effets continus), **Glyph** (l'image redessinée en caractères). Chaque
app livre 4 « starters » : des presets prêts à l'emploi que l'utilisateur charge pour partir
d'un résultat correct plutôt que d'un réglage vide.

Les 4 starters Glitch ont déjà été jugés par toi (H13). **Les 8 starters Dither et Glyph n'ont
jamais été regardés par personne** — c'est la passe de polissage.

- `dither_01_gameboy_fs` : Floyd-Steinberg, pixel 2, palette Game Boy intégrée
- `dither_02_pico8_bayer8` : Bayer 8×8 ordonné, palette PICO-8
- `dither_03_ega_riemersma` : Riemersma (diffusion par courbe de Hilbert), palette EGA
- `dither_04_grey16_atkinson` : Atkinson, 16 niveaux de gris
- `glyph_01_ascii_gameboy` : rampe ASCII `@%#*+=-:. `, palette Game Boy, pixel 8
- `glyph_02_braille_grey8` : braille (8 points par caractère), 8 gris
- `glyph_03_quadrant_pico8` : quadrants Unicode (2×2 par caractère), palette PICO-8
- `glyph_04_shape_ega` : glyphes de forme, palette EGA

## Ce que je te demande

Un verdict de produit, tranché. Ce sont les images que l'utilisateur voit en premier quand il
ouvre l'app — elles doivent donner envie.

1. **Note /10 pour chacun des huit**, avec une phrase de justification. Sois précis sur le
   symptôme visible, pas sur le principe.
2. **Le palmarès** : les deux meilleurs de chaque famille, et les deux à refaire.
3. **Y a-t-il un starter qui trahit son nom ?** Par exemple un « gameboy » qui n'a pas l'air
   Game Boy, ou un braille qui n'est pas lisible comme du braille.
4. **La source est-elle la bonne ?** Un portrait photographique est-il le bon véhicule pour
   juger un tramage et du glyphe, ou faudrait-il une autre image (paysage, objet, texte) ?
5. **Un défaut de famille** : y a-t-il quelque chose qui cloche dans les quatre Dither, ou dans
   les quatre Glyph, et qui ne vient pas d'un réglage mais de la façon dont le preset est bâti ?
6. **Laquelle de ces huit images mettrais-tu en vignette de la galerie ?**

Tu peux lire les presets si ça t'aide : /home/mar1/Lattice/presets/starter/*.json

Écris en français, direct, sans ménagement. Si un starter est mauvais, dis-le.
