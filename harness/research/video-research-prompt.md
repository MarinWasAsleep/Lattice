# Prompt de recherche — marché vidéo (à réutiliser plus tard)

Ce prompt reproduit, pour la vidéo, la méthode qui a produit `docs/market-research.md`
et le cadrage de la suite de plugins. À coller tel quel dans une nouvelle session.

---

## Le prompt

Tu travailles sur une suite de plugins libres et gratuits pour la suite **ArtCraft**
(apps Rust open source : PhotoCraft, VectorCraft, FilmCraft, EffectCraft, LightCraft,
DesignCraft, PdfCraft, AniCraft, TextureCraft, FigCraft, GridCraft, CADCraft, DeckCraft,
WordCraft, SoundCraft, MaterialCraft).

Le premier plugin, **Lattice Dither**, existe déjà et sert de patron. Sa forme est :

- `core/` — transformations pures en numpy, sans hôte, sans UI, testables seules
- `bridge/` — adaptateur du serveur de contrôle de l'hôte (TCP loopback, JSON par ligne,
  jeton d'authentification, HMAC-SHA256)
- `ui/` — PySide6
- un CLI headless qui produit exactement les mêmes octets que la GUI
- des presets JSON portables

Le pont fait deux choses : lire le document visible de l'hôte (aplati, en PNG) et pousser
le résultat en un nouveau calque. Rien de plus.

### Étape 1 — Cartographier l'hôte avant de chercher des concurrents

Ne devine pas la surface d'API. Interroge-la :

```
"C:\Program Files\ArtCraft\FilmCraft\filmcraft-cli.exe" --help
"C:\Program Files\ArtCraft\FilmCraft\filmcraft-cli.exe" commands
"C:\Program Files\ArtCraft\EffectCraft\effectcraft-cli.exe" --help
"C:\Program Files\ArtCraft\EffectCraft\effectcraft-cli.exe" commands
```

Réponds à : combien de commandes, quelles familles, qu'est-ce qui existe déjà pour le
traitement image par image, y a-t-il un registre de plugins, un serveur de contrôle, un
serveur MCP, un mode batch, un mode droplet. Cherche explicitement les trous : est-ce que
l'hôte sait déjà faire un tramage temporel, un datamosh, un CRT, un rendu par glyphes.

Le résultat de cette étape conditionne tout le reste : un plugin n'a de valeur que si
l'hôte ne sait pas déjà faire la chose.

### Étape 2 — Cartographier les outils existants, par famille de technique

Pour chaque famille, trouve 12 à 18 outils réels, pas une liste de 40 noms. Pour chacun :
nom, URL, plateforme, prix, licence, **le mécanisme réel** (pas le argumentaire marketing),
et une ou deux idées d'UX.

Familles à couvrir :

1. **Glitch vidéo et datamosh** — ffglitch, Moshup, datamosh.app, Mosh-Pro, Glitché,
   pipelines ffmpeg, Glitch Machine (Studio AAA)
2. **Tri de pixels et déplacement animés** — implémentations d'Asendorf, plugins AE,
   shaders Shadertoy
3. **CRT, VHS, NTSC** — NTSC-rs, ntscQT, CRT Royale, packs de shaders, émulation de signal
4. **Tramage temporel et tramage en mouvement** — Dither Boy, DitherMaster, DitherEffect,
   Dithertron, tout outil qui gère la cohérence entre images
5. **ASCII et glyphes en vidéo** — ASCII Magic, Chafa, renderers temps réel, LED walls
6. **Halftone et print en vidéo** — séparations animées, riso animé
7. **Pixel art et réduction animée** — Pyxelate, Retro Diffusion, demake tools
8. **Suites d'effets temps réel** — TouchDesigner, Notch, Resolume, Mosh-Pro, Max/MSP

### Étape 3 — Séparer le mécanisme du discours

Pour chaque outil, réponds à : est-ce un déplacement, un décalage de canal, un artefact
de bloc DCT, une boucle de rétroaction, une surcouche de scanlines, un filtre par image
sans mémoire ? Cette distinction vaut plus que la fiche produit.

Puis réponds à : qu'est-ce qui rend un outil de glitch « vivant » plutôt qu'un filtre
à usage unique ? Cherche les boucles de rétroaction, la cohérence temporelle, les contrôles
de graine et de randomisation, et la façon dont chaque outil gère vidéo contre images fixes.

### Étape 4 — Conclure

Termine par deux sections :

- **Ce qui manque** — des trous concrets qu'un nouvel entrant peut occuper, pas des
  généralités.
- **Verdict de module** — cette famille mérite-t-elle une app dédiée dans la suite,
  et pourquoi. Sois prêt à répondre « non ».

### Règles

- Vérifie les prix et les licences. Marque « non vérifié » plutôt que d'inventer.
- La licence compte : les meilleures couvertures algorithmiques sont en copyleft
  (didder, ditherzam, Dithertron, GIMP, G'MIC). Les cibles réutilisables sont
  libdither (MIT), histerdither (MIT), pyxelate (MIT), Dithermark (MIT),
  @thi.ng/pixel-dither (Apache-2.0).
- Écris en anglais, sans préambule.
- Ne propose pas de fonctionnalité que l'hôte sait déjà faire.

---

## Ce qu'il faudra vérifier en premier

- FilmCraft et EffectCraft exposent-ils un serveur de contrôle avec jeton, comme
  PhotoCraft ? Sans ça, le pont du patron Lattice Dither ne se transpose pas.
- Le pont actuel lit un PNG aplati. En vidéo, cela veut dire une image à la fois :
  est-ce assez rapide, et faut-il un mode « rends la séquence entière » côté CLI ?
- La cohérence temporelle est le vrai sujet. Un tramage recalculé par image scintille.
  Cherche comment les autres verrouillent la palette et ancrent la matrice à la scène.
