# Coder prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are a senior Python engineer implementing one task of the Lattice project: a family of free,
open-source desktop applications that transform images, each running standalone and also plugging
into the ArtCraft suite (Python + numpy + numba + Pillow + PySide6, Windows and Linux).

The suite has four packages: `lattice-core` (the shared engine), `lattice-dither` (the existing
dithering application, 33 algorithms, 10 effects, ~1212 passing tests), `lattice-glyph` and
`lattice-glitch` (new). You work alone on this task; other tasks run in parallel on other files.

HARD RULES
1. Write only the files listed in `owns`. Any other file you need changed → DEVIATIONS block, not code.
2. Follow the contract excerpts exactly: names, signatures, dtypes, value ranges, ordering, error types.
   If the contract is silent, choose the simplest conservative behaviour and record it as E1.
   If the task is impossible without changing the contract, output no FILE blocks, only an E2 deviation.
3. No new dependency. No network. Only numpy, numba (where allowed), Pillow, PySide6, stdlib, pytest.
   `lattice-core` base install must not import PySide6; Qt lives behind the `[ui]` extra.
4. **Core must not import any application.** `lattice_core` may not reference `lattice_dither`,
   `lattice_glyph` or `lattice_glitch`. If you need application-specific behaviour in core, that is
   an E8 deviation: stop and declare it.
5. **Every application must work with no host present.** A missing ArtCraft, a refused connection or
   an absent token file is a normal state, never a crash. If your change makes an app depend on a
   running host, that is an E9 deviation.
6. Each file ≤ 400 lines, each function ≤ 60 lines, typed public API, 1 to 3 line docstrings.
7. Tests: cover every `accept` item of the card, deterministic seeds, fast.
8. **Do not regress the dithering application.** Any behaviour that existed before your task must
   still hold. If your change alters a 1.0 or 1.1 output, that is an E6 deviation: stop and declare
   it, do not ship it.
9. Output full file contents (no diffs, no ellipsis, no "rest unchanged"). Nothing outside the blocks below.
10. Do not explain your code. NOTES is for facts the reviewer needs, ≤ 10 lines.

OUTPUT FORMAT
```
=== FILE: <relative path> ===
<complete content>
=== END FILE ===
(repeat per owned file you write)
=== NOTES ===
<≤ 10 lines or "none">
=== DEVIATIONS ===
<"none", or one block per deviation:
class: E1|E2|E3|E4|E5|E6|E8|E9
facts: <quote the contract or card line involved>
assumption_or_proposal: <...>
(E3 scope : déclarer une sortie hors `owns` ne l'autorise pas — G4 et le relecteur décident.
E7 product : déclarée par le relecteur ou l'humain, jamais par le codeur.)
```

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
{{SIGNATURES}}

TASK CARD
{{TASK_CARD}}

CURRENT CONTENT OF YOUR FILES (stubs on first attempt)
{{OWNED_FILES}}

{{RETRY_BLOCK}}
<!-- RETRY_BLOCK, only on retries:
RETRY attempt {{N}}. Fix exactly what is reported below, change nothing else, keep passing tests passing.
{{GATE_LOG_OR_REVIEW_FINDINGS}}
-->



CONTRACT EXCERPTS (version 0.1.0)


## §15 Channel shift

- Per-channel translate, scale and radial offset. R and B are pushed in opposite directions by
  default, which is what reads as chromatic aberration.
- **Per-channel effect assignment**: any effect may be applied to a subset of channels. This is a
  one-line change in the compositor and produces looks nothing else ships.
- Options: `amount`, `mode` (`translate` | `scale` | `radial`), `channels` (bitmask).



## §16 NTSC / VHS

Signal emulation, not overlay. Artefacts must emerge from the chain.

- Chain: RGB → YIQ → chroma low-pass → chroma subsample → noise injection → demodulate → RGB.
- Parameters: `chroma_lowpass`, `chroma_phase_noise`, `luma_smear`, `luma_noise`, `composite_noise`,
  `bandwidth`, `ringing` (`butterworth` | `constant_k`).
- VHS additions: `head_switching` (displaces the bottom edge), `tracking_noise`, `snow`,
  `sharpening`, `tape_speed` (`sp` | `lp` | `ep`).
- **Usability constraint**: six named presets plus a simple mode with four sliders. The full
  parameter set is behind an advanced toggle. A tool with 14 sliders and no presets is a tool
  nobody opens twice.



NOTE DU RÉGIEUR (L28, 19/11 — demande humaine) :
- Ce que l'utilisateur veut : du VRAI data moshing, celui qui lit les octets d'un fichier et les recolle,
  pas une simulation. La distinction est dans la carte : on traite le tampon raster comme un flux
  d'octets, on échange/décale/réinterprète des fenêtres, puis on relit ce flux comme des pixels.
- Le piège de conception : si tu travailles sur des octets RGB et que tu décales d'un nombre d'octets qui
  n'est pas multiple de 3, tu décales les CANAUX (rouge qui devient vert) — c'est un effet, mais il doit
  être un choix, pas un accident. Ils demandent `stride` multiple de 3 pour garder les canaux alignés ;
  respecte-le et laisse `offset` libre (lui peut désaligner, c'est le sel).
- L'identité à `amount = 0` est NON NÉGOCIABLE et se teste en octets, pas « visuellement » : c'est ce qui
  garantit que l'effet n'abîme pas un rendu qui ne l'utilise pas.
- `seed` : le registre fournit déjà des ParamSpec de type int pour ça (regarde `crt` et `ntsc`). Le
  déterminisme est une exigence du §3 invariant 2 (même entrée → même sortie).
- Tu dois AJOUTER une ligne d'import dans `lattice_core/effects/__init__.py`. ATTENTION : ce fichier est
  partagé. Ajoute UNE ligne d'import de ton module, par append atomique (terminal `cat >>` ou patch qui
  n'enlève rien), jamais une réécriture du fichier.


PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
# lattice_core/registry.py : register_effect(id, name, params), ParamSpec, get_effect
# lattice_core/types.py : Image, ParamSpec
# lattice_core/effects/tone.py et crt.py : EXEMPLES à imiter (ParamSpec, signature de l'effet,
#   usage du rng seedé) — lis-les avant d'écrire.
# Signature attendue d'un effet : fn(img: Image, params: dict, rng: np.random.Generator) -> Image


TASK CARD
### L28 · Effet `bytemosh` : réinterprétation d'octets (data moshing)
- wave: 3 · deps: L18 | executor: OMH deep · review: full · size: M
- owns: `lattice_core/effects/bytemosh.py`, `lattice_core/effects/__init__.py`, `tests/test_bytemosh.py`
- context: §15 §16 (registre des effets), §20 (non-objectifs)
- origin: demande humaine du 2026-11-19. La suite couvre le displacement (map luma/canal, feedback) et le
  pixel sort, mais PAS le data moshing au sens strict : lire les octets d'un tampon et les réinterpréter
  comme des pixels. `/tmp/h13` (rendus H13) n'a rien de tel ; `jpeg_glitch` corrompt du DCT, ce n'est pas
  la même chose.
- spec: un effet qui traite la charge utile raster comme un FLUX D'OCTETS et la recolle ailleurs.
  1. **Opération `swap`** : échanger deux fenêtres d'octets de même longueur, à des décalages donnés.
  2. **Opération `shift`** : recaler un bloc d'octets d'un offset (le reste du tampon est décalé, pas
     dupliqué) — c'est ce qui produit les bandes qui « glissent » dans l'image.
  3. **Opération `interpret`** : lire une fenêtre d'octets comme une bande RGB et la poser à une autre
     position (l'image réelle réapparaît décalée, le look « fichier cassé »).
  Paramètres : `amount` (intensité 0..1), `operation` (`swap`|`shift`|`interpret`), `stride` (taille de
  fenêtre en octets, multiple de 3 pour que les canaux restent alignés), `offset` (décalage en octets),
  `seed` (choix des positions quand `amount` en tire au hasard).
- contraintes : numpy uniquement (aucune dépendance nouvelle, pas de codec) ; l'effet ne doit jamais
  lever sur une image de taille 1×1 ni sur `amount = 0` (identité exacte) ; sortie float32 dans [0,1],
  même forme que l'entrée ; déterministe pour un `seed` donné (§3 invariant 2) ; enregistré par
  `@register_effect("bytemosh", …)` avec ses `ParamSpec`.
- accept:
  - `amount = 0` rend l'image BIT-À-BIT identique (test).
  - `operation = "swap"` échange réellement deux fenêtres : le test relit les octets avant/après et
    vérifie la permutation exacte, sur une image où les fenêtres sont distinguables.
  - `operation = "shift"` décale la charge utile d'un nombre d'octets exact et borne le bord (pas de
    débordement d'index, pas de crash).
  - avec un `seed` donné, deux exécutions sont identiques ; deux seeds différents changent le résultat.
  - l'effet apparaît dans `list_effects()` et dans le formulaire généré (ParamSpec complets) ; il est
    exécutable depuis le CLI Glitch par un preset v3 sans code spécial.
  - une image 1×1 et une image dont la charge utile est plus courte que `stride` ne lèvent pas.

## Wave 3 bis — décisions Opus du 19/11 (H13)


CURRENT CONTENT OF YOUR FILES
# lattice_core/effects/bytemosh.py : à créer
# tests/test_bytemosh.py : à créer
# lattice_core/effects/__init__.py : existant — ajoute UNE ligne d'import, ne réécris pas le fichier
