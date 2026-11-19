# bytemosh — data bending sur le flux d'octets

L'effet `bytemosh` traite le tampon raster d'une image **comme un flux d'octets**, le
réarrange, puis relit ce flux comme des pixels. C'est du *databending* : la corruption est
réelle (les octets changent de place), pas une simulation de bruit.

Ce n'est pas du *data moshing* au sens strict du terme — celui-ci suppose un codec vidéo,
avec suppression des I-frames pour que la lecture réutilise les vecteurs de mouvement.
Lattice n'accepte pas de vidéo en entrée (§20 du contrat).

## Les quatre opérations

| Opération | Ce qu'elle fait | Rendement |
|---|---|---|
| `swap` | échange deux fenêtres d'octets de même longueur | le plus lisible |
| `shift` | rotation circulaire de tout le flux | translate l'image, propre |
| `interpret` | recopie une fenêtre ailleurs dans le tampon | recopie de blocs |
| `drift` | décale chaque ligne un cran de plus, en pente irrégulière | cisaille, dérive |

## Paramètres

| Paramètre | Rôle |
|---|---|
| `amount` | intensité, 0 → 1. À 0 l'image est **bit-à-bit identique**. |
| `operation` | `swap`, `shift`, `interpret` ou `drift` |
| `stride` | longueur de la fenêtre en octets (multiple de 3 pour garder les canaux alignés) |
| `offset` | décalage d'ancrage en octets |
| `seed` | choix des positions aléatoires — même seed, même image |

`offset` mérite une attention : un décalage **multiple de 3** décale l'image
horizontalement en gardant les couleurs justes ; un décalage **non multiple de 3** décale
les canaux RVB les uns par rapport aux autres et fait apparaître des couleurs qui ne sont
pas dans la source. Les deux sont utiles, mais ce n'est pas le même effet.

## Exemples

La source est un dégradé vertical avec un anneau jaune, un rectangle vert et du texte
blanc — les formes droites rendent les déplacements lisibles.

- `00_source.png` — la source, pour comparer
- `01_swap.png` — deux échanges de 100 lignes : les blocs changent de place et la source
  reste reconnaissable
- `02_shift.png` — translation du flux
- `03_interpret.png` — une fenêtre de 50 lignes recopiée ailleurs, en escalier
- `04_drift_03.png` / `05_drift_10.png` — la dérive à intensité 0,3 puis 1,0
- `06_swap_simple.png` — un seul échange de 150 lignes, le cas le plus propre

## Recette

```
lattice-glitch render --preset mon_preset.json --in source.png --out image.png
```

```json
{
  "version": 3,
  "app": "glitch",
  "seed": 7,
  "pipeline": {"algorithm": null, "palette": null, "pixel_size": 1},
  "palette": null,
  "effects": [
    {"name": "bytemosh", "enabled": true, "stage": "post", "mask": null,
     "params": {"amount": 0.25, "operation": "swap", "stride": 216000,
                "offset": 21, "seed": 5}}
  ]
}
```

Le bloc `pipeline` n'est pas décoratif : sans lui, le convertisseur retombe sur les
valeurs par défaut de Dither (Floyd-Steinberg + palette noir et blanc) et Glitch refuse de
rendre. `algorithm` et `palette` doivent être `null` pour un rendu continu.

En boucle animée, l'axe `param` fait respirer l'amplitude :

```
lattice-glitch loop --preset mon_preset.json --in source.png --out boucle.gif \
  --frames 8 --axis param --param bytemosh.amount --from 0 --to 1 --curve sin
```

`--curve sin` fait un aller-retour (0 → 1 → presque 0, sans répéter la première image) ;
`--curve linear` fait un triangle. La course de retour produit des images miroir : avec
8 frames, on obtient 5 images distinctes, et c'est l'effet attendu d'une boucle A→B→A.

## Piège de réglage

Une fenêtre trop petite ne se voit pas : sur une image de 720 px de large, une ligne fait
2160 octets. Avec `stride` sous ~10 000 (soit 5 lignes), on obtient de la poussière, pas
un déplacement. Le paramètre n'est pas cassé — la fenêtre est juste plus petite que ce que
l'œil peut lire.

Pour vérifier qu'un paramètre agit vraiment, comparer deux rendus au `md5sum` plutôt qu'à
l'œil : deux réglages différents doivent produire deux fichiers différents.
