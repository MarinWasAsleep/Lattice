# Marché du dithering — état des lieux et pistes pour PhotoCraft

Recherche menée en novembre 2026 en anglais, français, allemand, espagnol, portugais, russe,
japonais, chinois et coréen. Chaque fiche vient d'une source primaire (page éditeur, dépôt, store) ;
ce qui n'a pas pu être vérifié est marqué **non vérifié**.

---

## 1. La référence : Dither Boy (Studio AAA)

Le produit que tu as cité comme étalon.

- **Éditeur** : Studio AAA (Jack McArdle & Danny Void), studio britannique.
- **Prix** : £60 tarif, £49 en promo. Achat unique, mises à jour incluses, pas d'abonnement.
- **Plateforme** : application autonome Windows + macOS. Pas un plugin.
- **Algorithmes** : 63, présentés comme « entièrement éditables, animables », familles error
  diffusion / bitmap / halftone / modulation, dont des algorithmes maison.
- **Pipeline** : effets empilables et réordonnables (Epsilon Glow, JPEG Glitch, Chromatic
  Aberration, Blur/Sharpen). Halftone CMJN depuis la 6.0. « Shape Shifter » (6.6.6) ajoute le
  dithering à formes personnalisées, les fichiers projet et les codes de thème partageables.
- **Couleur** : palettes intégrées, extraction automatique depuis l'image, palettes utilisateur
  partageables, édition couleur par couleur.
- **Animation** : timeline intégrée, lecture vidéo live, « Temporal Variation » = neuf motifs de
  bruit animé inspirés des écrans cathodiques.
- **Sorties** : PNG, JPG, SVG vectoriel, MP4, vecteurs noirs pour impression et broderie.
- **Positionnement** : « transformer un algorithme de compression en effet granulaire, éditable,
  malléable ». Pas d'IA, pas d'abonnement, branding d'époque.

**Le reste du catalogue Studio AAA** (utile pour comprendre le modèle économique) : Flareware £40,
Script Slayer gratuit (rendu ASCII, 48 jeux de glyphes, intégré à Dither Boy), Glitch Machine £45
(After Effects), CRT Scanlines £25, plus 78 packs de ressources. Chaque outil payant est alimenté
par des presets et palettes gratuits : c'est le moteur de rétention.

---

## 2. Concurrence commerciale

### Applications autonomes

| Produit | Éditeur | Prix | Points forts |
| --- | --- | --- | --- |
| **Dither Boy** | Studio AAA | £49 | 63 algos, pipeline d'effets, timeline vidéo, export SVG |
| **DitherMaster Studio** | Grave Hammer Games | $16.99 | 30+ algos, 40+ étapes réordonnables, **CLI**, plusieurs images ouvertes, vidéo, « The Archive » de presets copiables |
| **Ditherdragon** | winterveil | $19.95 | 11 méthodes, 53 palettes + import Lospec, détection de matière, preset « Repair AI pixel art » |
| **DIITHER** | A. Gorayeb | $3.99 | Minimal, sliders contraste/médianes/hautes lumières, GIF animé |

### Plugins Photoshop

| Produit | Éditeur | Prix | Points forts |
| --- | --- | --- | --- |
| **Dither Pusher 2** | bangingjoints / aescripts | $39 | 45 algos (28 error diffusion, 6 ordered, 50 motifs), palettes **Lospec**, export de tracés vectoriels vers Illustrator, rendu par lot sur tous les calques |
| **DITHERTONE Pro** | Doron Supply | $65 | 63 moteurs (30 dither, 8 halftone, 25 ASCII), **LPI**, plaques CMJN aux angles presse, DTF, 78 presets, 52 palettes |
| **Retratone** | Texturelabs | $45–79 | Halftone d'encre réelle, encres qui se superposent, 100 presets |
| **Halftone+** | Seso | $35 | 13 styles, séparation 4/6/8 canaux, chaque effet sur son propre calque |
| **Dither FX** | DanielMevit | gratuit, AGPL-3.0 | 35 algos en JavaScript dans un panneau UXP, temps réel |

### Plugins After Effects / Resolve / Premiere

| Produit | Éditeur | Prix | Points forts |
| --- | --- | --- | --- |
| **DITHERON 3** | EZSCAPE | $79 | 67–80+ algos, 7 modes, 40 palettes, moteur de glow, 300 emplacements de looks, GPU, AE + Resolve + FCP avec une licence |
| **RetroDither** | BGRA Entertainment | $49.99 | 12 méthodes, 20 palettes, **palette depuis n'importe quel calque image ou vidéo**, serpentine |
| **Dither Decay** | MEGAKRUNCH | $39 | 8 looks, entrée par presets |
| **DITHER A3SD PRO** | WEFLARESTUDIO | $29 | 60 motifs, 50 palettes, **53 formes de tuiles** (Pac-Man, Space Invaders…), seed animable |
| **PixDither** | Wunkolo | $20 | 20+ palettes dont PICO-8 et C64 |

### Autres hôtes

- **Affinity** : Visual.af Filter Gallery, effet Dithering gratuit (Bayer 2×2/4×4/8×8, mode
  « couleurs d'origine », 5 presets, curseur de comparaison avant/après). Le dithering natif
  d'Affinity Photo est un filtre hérité sans Bayer ordonné.
- **Illustrator** : Phantasm (Astute Graphics), halftone vivant non destructif, gain de point,
  séparations. **Shpigford/dither** (gratuit, open source) : chaque cellule devient une forme
  vectorielle groupée par couleur, 9 motifs, cœur JS partagé web + plugin.
- **Figma** : DitherFX (34 algos, palier gratuit à 5), vga dithercore.exe, Dither Studio, Dither it!.
- **Canva** : **aucun dithering**. Le plus gros public design du monde n'a pas la primitive.
- **Unity / Godot / Unreal** : shaders de post-traitement, dont le *surface-stable fractal
  dithering* (Rune Skovbo Johansen) porté partout — les points collent aux surfaces 3D.

---

## 3. Outils web

Les plus intéressants, tous gratuits et traités côté client :

- **Dithertron** (8bitworkshop, GPL-3.0) — 60+ cibles matérielles réelles (C64, NES, ZX Spectrum,
  MSX, Game Boy…), palettes par bloc avec **recuit simulé**, sélecteur de fonction d'erreur
  couleur, curseur « Gray », export binaire natif. La référence pour le respect des contraintes
  matérielles.
- **Dithermark** (MIT) — la plus grosse liste d'algorithmes du web : Yliluoma 1 et 2, Hue-Lightness
  Bayer, R2 Sequence, XOR/ADD, et le système de suffixes (R2)/(R)/(S) qui multiplie les rendus
  sans multiplier l'interface.
- **Ditherer** (gyng, MIT) — **chaîne d'étapes empilables** avec presets nommés par *look*
  (« Ditherpunk Blue Noise », « Gameboy Screen », « Amber Terminal »), image et vidéo.
- **DitherEffect** — 84 styles / 39 algos, timeline à keyframes, **réaction audio**, lot de 100
  images, export print avec DPI, fond perdu et plaques d'encre séparées.
- **Dither it!** (MIT) — FS, Atkinson, Bayer 4×4, GIF animé, curseur avant/après, page de
  ressources qui crédite les algorithmes.
- **Ditherlicious** — un seul algorithme (Stucki), cinq modes de conversion N&B nommés
  (luminosité, moyenne, filtre rouge/vert/bleu). Le minimalisme assumé.
- **halftone-fx.com** — halftone + dithering, formes de marques personnalisées, aperçu partagé
  par une ligne déplaçable, export PNG/SVG/WebM.
- **Bitgrain** — se positionne comme outil d'**impression** qui ditherise : fond perdu, traits de
  coupe, séparations riso/CMJN, PDF print. Annonce aussi une intégration agent (Claude).
- **DITHR** (MIT) — pensé pour l'**e-ink** : éditeur à calques + synchronisation directe vers les
  dalles Waveshare / Good Display.
- **Pixelaro** (Brésil) — **Pixel Snapper** : détection de grille, suppression d'anti-aliasing et
  de bruit JPEG, correspondance OKLab, préservation des contours. Plus export Minecraft map-art.
- **Turbo Dither** — facteur de diffusion 0–2 exposé, mode peinture manuelle après dithering,
  webcam live.

---

## 4. Open source, CLI et bibliothèques

Le point clé ici est la **licence**, parce qu'elle décide de ce qu'on peut réutiliser.

| Projet | Licence | Intérêt |
| --- | --- | --- |
| **libdither** (robertkist) | **MIT** | Le meilleur candidat de réutilisation : DBS, dot diffusion, Riemersma, Ostromoukhov, Zhou Fang, Kacker-Allebach, et modes de comparaison couleur **LAB76/94/2000, sRGB, linéaire, HSV, luminance, Tetrapal**. C99 sans dépendance. |
| **Ditherista** | MIT | GUI au-dessus de libdither, 90+ méthodes. |
| **histerdither** | MIT | Python/PIL, dithering vers palette arbitraire, Yliluoma. |
| **pyxelate** | MIT | Python, downscale + palette + palette transfer. |
| **DitherPunk.jl** | MIT | Galerie de tous les algorithmes sur la même image de test — le meilleur modèle de doc. |
| **@thi.ng/pixel-dither** | Apache-2.0 | Format de noyau documenté (offset/weight/shift). |
| **didder** | GPL-3.0 | CLI de référence : **matrices ordonnées et noyaux d'erreur en JSON**, donc extensibles par l'utilisateur. |
| **ditherzam** | GPL-3.0 | Le plus proche cousin de Lattice Dither : Python + PySide6 + Numba + Pillow, 77 styles, pipeline d'effets réordonnable, verrouillage/réordonnancement de palettes, masques peints après dither, 2 519 tests. |
| **Dither Guy** | GPL-3.0 | Python, « inspiré par Dither Boy », image + vidéo, dossier `presets/`. |
| **Dithertron** | GPL-3.0 | Voir plus haut. |
| **libimagequant / pngquant** | GPL-3.0 **ou licence commerciale payante** | Meilleur générateur de palette, mais double licence. |
| **GEGL `gegl:dither`** | LGPL-3.0 | 11 méthodes, **niveaux par canal** (R/G/B/A indépendants) — c'est ainsi qu'on obtient du RGB332 ou du RGB565 authentique. |
| **GIMP Newsprint** | GPL-3.0 | Le meilleur modèle de halftone : angle et période **par canal**, CMJN + RVB, 5 formes de point, extraction du noir, suréchantillonnage anti-aliasing. |
| **ImageMagick** | Apache-like | **Cartes de seuil nommées** (`o4x4`, `h8x8o`, `c6x6w`…) et cartes XML fournies par l'utilisateur. |
| **G'MIC** | CeCILL | `halftone` avec taille de point clair et foncé séparées, 6 formes, douceur. |
| **tramage** (MichailSemoglou) | à vérifier | Error diffusion **en Oklab** contrainte à une palette, avec papier de recherche. Python. |

---

## 5. Éditeurs pixel-art et leur écosystème

- **Aseprite** ($19.99) — les matrices de dithering sont un **type d'extension installable**
  (PNG + manifeste `package.json`). Extensions : Dithering Brushes (Exokem, CC BY-NC-SA) avec
  **curseur de densité 0–100 %** et aperçu dans les couleurs avant/plan ; DitherForge ($2.99) avec
  **bandes + biais + direction** ; Dithering Generator (densités de début/fin, 8 bruits dont Bayer,
  blue noise, halftone, lignes).
- **Krita** — dithering Bayer dans l'outil dégradé avec « Dither steps » ; le plugin `krita-dither`
  est mort depuis 2010. **SZK Pixel Art Suite** (payant) : docker de dithering avec éditeur de
  motif et **navigation aux flèches qui met à jour le motif en direct**.
- **GIMP** — quatre options seulement (aucun, Floyd-Steinberg, FS « reduced color bleeding »,
  Positioned). Le « Positioned » est **stable en animation** parce que le motif est ancré au canevas.
- **GrafX2** (français, GPL) — dithering à trois niveaux + curseur « Mix » aléatoire, et modes de
  contrainte machine (ZX Spectrum, CPC, C64, Apple II, Game Boy Color).
- **PhotoFiltre** (français) — « Monochrome » vs « Monochrome tramé » dans la conversion en
  couleurs indexées, et hébergement des filtres 8BF Photoshop.
- **Piskel** (Apache-2.0) — outil de dithering en **pinceau**, pas en filtre.
- **Pixelorama** (MIT) — dithering comme propriété d'un dégradé.

---

## 6. Japonais, chinois, coréen

- **NeSprite** (hiyameshi8bit, ¥800) — conversion en dots avec curseur de dithering, barre de
  palette éditable avec import `.pal`, versions CLI, vidéo et After Effects. Le plus proche
  équivalent japonais de Dither Boy.
- **画像減色ツール** (raky.net, gratuit) — 7 modes de dithering nommés, **mode pixel art qui
  préserve les couleurs d'accent** (les reflets des yeux), **transfert de palette** depuis une
  image de référence, sortie grille de point de croix.
- **RetroImageConverter** (cyross, open source) — presets nommés **par machine** (PC-9801, MSX,
  X68000…), tuilage comme alternative au dithering, correction du rapport de points.
- **GB Dot Converter** (Deepblizzard) — valide la sortie contre les **contraintes matérielles**
  (nombre de tuiles uniques, limites de la Game Boy), export JSON vers GB Paint.
- **レトロピクセルコンバーターII** et **HALFTONE MAKER** (AMIX) — empilement CRT (scanlines,
  bloom, vignettage) et halftone CMJN avec les angles presse expliqués dans l'interface.
- **图像抖动处理工具** (yikeaigc, chinois) — 12 algorithmes, **traitement par lot avec ZIP**,
  « interlaced scan » qui casse les traînées directionnelles, palettes ambre et e-ink.
- **d1tools** (chinois) — bibliothèque de palettes **Lospec** intégrée, clustered-dot.
- **OmniGIF** (chinois) — 11 algorithmes, **cadence des frames et boucle** dans le même panneau.
- **Wdot** (coréen) — choix de la **métrique de distance couleur** (RVB / Oklab / CIEDE2000) et
  « dot mode » qui aligne le downscale sur la grille de pixels existante.
- **ROBERIN** (coréen) — comparaison par **balayage horizontal** au même endroit, histogramme de
  cellules par couleur, aperçu qui ne change que la palette.

---

## 7. Ce que personne ne fait

1. **Personne ne fait le pont vers un éditeur.** Tous les plugins dithérisent *dans* l'hôte ; tous
   les standalone obligent à exporter puis réimporter. Les seules exceptions trouvées : le
   copier-coller de Dither Boy, l'éditeur Playdate qui écrit directement dans le dossier du projet,
   et un template PSD communautaire qui convertit les calques en direct. **Le pont
   « lire le document visible → ditheriser → renvoyer comme nouveau calque » n'existe nulle part
   ailleurs.** C'est le seul vrai fossé défensif du projet.
2. **La science des couleurs est ignorée.** Presque tout le monde compare en distance RVB naïve.
   Seuls libdither, Wdot, Dithertron et epaper-dithering font mieux. Un simple menu
   « correspondance couleur : sRGB / linéaire / OKLab / LAB2000 » mettrait Lattice Dither devant tous
   les outils gratuits.
3. **Le halftone est faux presque partout.** En dehors de GIMP Newsprint, d'AliveColors et de
   DITHERTONE, « halftone » veut dire une tuile de seuil 4×4. Un vrai halftone à angles d'écran est
   un différenciateur qui coûte une après-midi de maths.
4. **L'opération inverse n'est pas revendiquée.** Sattva Descreen vend le dé-tramage par Fourier
   comme plugin payant ; ArtLogic expose un « anti-dither » dans un SDK. Aucun outil de dithering ne
   propose « dé-ditheriser puis re-ditheriser » — pourtant c'est la demande naturelle dès qu'on
   travaille sur des scans ou de l'art déjà tramé.
5. **La stabilité temporelle est un angle mort.** Seul GIMP documente un mode stable en animation.
   Personne ne verrouille la palette entre les frames ni ne propage l'erreur d'une frame à l'autre.
6. **Les presets ne sont pas portables.** didder a des matrices JSON, Aseprite des PNG + manifeste,
   ditherzam des « Looks ». Aucun format commun, et aucun outil web n'exporte un preset en fichier.
7. **Presque personne ne livre de CLI.** DitherMaster Studio et le DitherCraft Rust en ont une ;
   Didder et ImageMagick sont CLI d'abord. Pour une application Python, un mode headless est quasi
   gratuit et ouvre le batch, la CI et l'usage par agent.
8. **Aucune localisation.** PhotoFiltre et GrafX2 sont natifs français mais franco-only ; tout le
   reste est anglais avec des pages traduites à la machine. Une interface française qui dit
   « tramage » et pas « dithering » est un coin à enfoncer.

---

## 8. À réadapter dans PhotoCraft, par ordre de rentabilité

### Priorité 0 — peu de code, gros effet

1. **Curseur de densité / force (0–100 %)** sur chaque algorithme. Exokem, yikeaigc, GrafX2. C'est
   l'interaction la plus « Dither Boy » trouvée dans toute la recherche.
2. **Métrique de correspondance couleur** : sRGB / linéaire / OKLab / LAB2000. Wdot, libdither.
3. **Bande de conditionnement avant dithering** : pré-flou, contraste, luminosité, saturation.
   IMG online, DIITHER. Le plus gros gain visuel pour le moins de code.
4. **Curseur de comparaison avant/après** déplaçable. halftone-fx, Visual.af, Dither it!.
5. **Verrouillage et réordonnancement des pastilles de palette**, plus import Lospec. ditherzam,
   Dither Pusher.
6. **Presets nommés par look** (« Gameboy Screen », « Amber Terminal ») plutôt que par algorithme.
   Ditherer, DitherMaster Archive.
7. **Dégradé de densité + bandes + biais** pour le dithering ordonné. DitherForge, sodedromme.

### Priorité 1 — différenciateurs

8. **Vrai halftone** : angle et période par canal, CMJN, formes de point, LPI. GIMP Newsprint,
   DITHERTONE, HALFTONE MAKER.
9. **Validation des contraintes matérielles** : budget de tuiles, résolution, limites de palette.
   GB Dot Converter, Dithertron.
10. **Presets nommés par machine** (PC-9801, MSX, Apple II, C64, ZX Spectrum). RetroImageConverter.
11. **Pré-passe « Pixel Snapper »** : détection de grille, suppression d'anti-aliasing et de bruit
    JPEG avant dithering. Pixelaro. **Indispensable pour le pont PhotoCraft**, où le document
    récupéré peut avoir été redimensionné ou compressé.
12. **Dé-tramage / re-tramage** (opération inverse). Sattva, ArtLogic.
13. **Stabilité temporelle** : matrices ancrées au canevas, palette verrouillée entre frames.
    GIMP « Positioned ».
14. **Export SVG / vectoriel**. Dither Boy, Shpigford/dither, DITHERTONE.
15. **Formes de tuiles personnalisées**. Dither Boy « Shape Shifter », A3SD (53 formes).
16. **Dithering qui suit les contours** (Edge Dither) et **surface-stable fractal dithering**.

### Priorité 2 — plus tard

17. Vidéo et timeline.
18. CLI + format de preset JSON documenté, comme standard ouvert.
19. Export print : fond perdu, traits de coupe, séparations.
20. Rendu ASCII / glyphes (Script Slayer, DITHERTONE 25 moteurs ASCII).
21. Interface française avec le vocabulaire « tramage ».

---

## 9. Le nom « DitherCraft » était déjà pris — renommé en Lattice Dither

Trois usages vivants, vérifiés :

1. **`github.com/shahil-sk/dithercraft`** — « An open-source, clean-room reimplementation of
   Dither Boy, built in pure Rust ». 63 algorithmes, 9 motifs de bruit temporel, cœur JPEG Glitch,
   5 thèmes, export SVG vectoriel, CLI, licence MIT ou Apache-2.0. Dernier push octobre 2026,
   0 étoile. C'est fonctionnellement le même produit, sous le même nom.
2. **Unity Asset Store** — « DitherCraft: Retro Pixel Dithering Post-Processing » (Cheddar Sparks).
3. **Gumroad** — « DitherCraft FX », pack d'effets gratuit pour DaVinci Resolve (Editors Den).

Rien n'est en conflit de marque déposée à ce stade (aucune des trois n'est déposée), mais la
recherche par nom renvoyait déjà un concurrent direct en Rust.

**Décision : renommé.** L'application s'appelle désormais **Lattice Dither**, premier consommateur
de la suite Lattice. Le dépôt de travail est `MarinWasAsleep/Lattice` (privé) et le dépôt produit
est `MarinWasAsleep/lattice-dither` (public). Le nom `DitherCraft` n'est plus utilisé nulle part
dans le produit ; il ne subsiste que dans les trois usages tiers ci-dessus et dans les comptes
rendus historiques du harness 1.0 et 1.1.
