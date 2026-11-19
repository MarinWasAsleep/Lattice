Lis ces sept images, en citant les chemins absolus quand tu en parles :

- /home/mar1/Lattice/docs/bytemosh/00_source.png — la source
- /home/mar1/Lattice/docs/bytemosh/01_swap.png — échange de deux fenêtres de 100 lignes
- /home/mar1/Lattice/docs/bytemosh/02_shift.png — rotation du flux d'octets
- /home/mar1/Lattice/docs/bytemosh/03_interpret.png — une fenêtre recopiée ailleurs
- /home/mar1/Lattice/docs/bytemosh/04_drift_03.png — dérive à 0,3
- /home/mar1/Lattice/docs/bytemosh/05_drift_10.png — dérive à 1,0
- /home/mar1/Lattice/docs/bytemosh/06_swap_simple.png — un seul échange de 150 lignes

## Le contexte

On a livré dans la suite Lattice (apps de traitement d'image : Dither, Glitch, Glyph) un effet
nommé `bytemosh`. Son principe : le tampon raster RGB est traité comme un FLUX D'OCTETS, on
réarrange des fenêtres d'octets, puis on relit ce flux comme des pixels. Quatre opérations :

- `swap` échange deux fenêtres de longueur `stride`
- `shift` fait une rotation circulaire de tout le flux
- `interpret` recopie une fenêtre à un autre endroit du tampon
- `drift` décale chaque ligne d'un cran de plus que la ligne du dessus, en pente irrégulière

Paramètres : `amount` (0..1), `operation`, `stride` (octets, multiple de 3 pour garder les
canaux alignés), `offset` (octets, l'ancrage), `seed`.

La source a été fabriquée exprès (dégradé vertical, anneau jaune, rectangle vert, texte blanc)
pour que les déplacements de lignes soient visibles à l'œil.

Deux choses qu'on assume : (1) ce n'est pas du data moshing au sens strict — le vrai moshing
exige un codec vidéo et la suppression des I-frames, or le contrat interdit la vidéo en entrée ;
(2) `amount = 0` rend l'image bit-à-bit identique, c'est verrouillé par des tests.

## Ce que je te demande

Une critique d'artiste, tranchée, pas une liste d'options neutres.

1. **Est-ce que ça « mosh » ?** Pour chaque opération, dis franchement si l'image ressemble à un
   fichier graphique réellement abîmé ou à un filtre appliqué. Note sur 10. Distingue ce qui est
   conventionnel dans le genre de ce qui est authentique.
2. **Le défaut principal.** S'il n'en fallait qu'un, lequel ? Sois précis : quelle opération, quel
   réglage, quel symptôme visible.
3. **Voies d'amélioration concrètes.** Par ordre de rendement décroissant. Pour chacune : ce que
   ça changerait à l'image, et à quel point c'est du travail (une ligne / une carte de quelques
   heures / une refonte). Cite des références du genre si tu en as (databending glitch art,
   Aesthetics of Data Moshing, Rosa Menkman, Kim Asendorf, Jonas Lund...).
4. **Ce qu'il faudrait ajouter que personne n'a fait.** Si tu vois un geste qui manque à la
   gamme — pas un réglage, un effet.
5. **Verdict.** Est-ce que ces images méritent de figurer dans la doc publique du projet ? Lesquelles,
   lesquelles jeter.

Tu peux lire le code si ça t'aide : /home/mar1/Lattice/lattice_core/effects/bytemosh.py et
/home/mar1/Lattice/docs/bytemosh/README.md.

Écris en français, direct, sans ménagement. Si tu penses que ça ne mosh pas, dis-le.
