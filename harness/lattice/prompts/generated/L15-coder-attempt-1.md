# Coder prompt — L15 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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
CONTRACT EXCERPTS (version 0.1.0)

## §14 Pixel sort

- Three thresholds: `black`, `brightness`, `white`. A run starts when a pixel passes `brightness`
  and continues while it stays inside the `black`..`white` band.
- Direction: `rows`, `columns`, `diagonal`.
- Sort key: `luma`, `hue`, `saturation`, `r`, `g`, `b`.
- `mask` acts as an interval map: white pixels are sorted, black pixels are not.
- Runs are sorted with a stable sort so the result is deterministic.

PUBLIC SIGNATURES OF MODULES YOU MAY IMPORT
--- lattice_core/registry.py ---
class AlgorithmInfo:
class EffectInfo:
def register_algorithmid: str, name: str, family: str, params: tuple[ParamSpec, ...]=()  # Return a decorator that registers an algorithm under id.
def register_effectid: str, name: str, params: tuple[ParamSpec, ...]=()  # Return a decorator that registers an effect under id.
def get_algorithmid: str  # Return the algorithm registered under id, or raise KeyError.
def list_algorithms  # Return every registered algorithm, sorted by family then name.
def get_effectid: str  # Return the effect registered under id, or raise KeyError.
def list_effects  # Return every registered effect, sorted by name.
def resolve_paramsspecs: tuple[ParamSpec, ...], given: dict  # Fill defaults, clamp numbers to their bounds, cast ints and validate choices.

--- lattice_core/effects/halftone.py ---
def platesimg: Image, black_pullout: float  # Return the C, M, Y and K ink amounts of every pixel.
def halftone_cmykimg: Image, params: dict, rng: np.random.Generator  # Screen the four CMYK plates at the print angles and recombine them.

--- lattice_core/effects/tone.py ---
def gaussian_blurimg: Image, params: dict, rng: np.random.Generator  # Blur the image with a gaussian kernel whose sigma is radius / 3.
def sharpenimg: Image, params: dict, rng: np.random.Generator  # Sharpen the image with an unsharp mask of the given amount and radius.
def glowimg: Image, params: dict, rng: np.random.Generator  # Add a screen-blended bloom built from the bright pass of the image.
def noiseimg: Image, params: dict, rng: np.random.Generator  # Add gaussian noise of standard deviation amount / 2, shared or per channel.
def posterizeimg: Image, params: dict, rng: np.random.Generator  # Quantise every channel to at most `levels` evenly spaced values in [0, 1].

TASK CARD
### L15 · Pixel sort
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/effects/pixel_sort.py`, `tests/test_pixel_sort.py`
- context: §14
- spec: implement §14. Three thresholds (`black`, `brightness`, `white`), direction (`rows`,
  `columns`, `diagonal`), sort key (`luma`, `hue`, `saturation`, `r`, `g`, `b`), mask as interval
  map. Stable sort.
- accept:
  - a fully white image with `brightness = 0` sorts every row.
  - a fully black image with `black = 0` sorts nothing.
  - the sort is stable: equal keys keep their relative order.
  - a mask of all black sorts nothing; all white equals no mask.
  - `columns` transposes the result of `rows` on a square image.
  - output shape equals input shape.

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/effects/pixel_sort.py` n'existe PAS (à créer). Convention des effets du core :
les modules de `lattice_core/effects/` (ex. halftone.py, tone.py, glitch.py) s'enregistrent
via `register_effect(id, name, params)` et exposent `fn(img, params)` où img est un array
float32 (H, W, 3) dans [0, 1] — lisez-en un AVANT de coder. `tests/test_pixel_sort.py`
n'existe pas. Un effet doit être déterministe (seed via `params["seed"]` si besoin) et ne pas
muter son entrée. Attention : un tri stable exige un `np.argsort(kind="stable")` (ou équivalent)
— les runs (définis par la bande black..white) sont triés individuellement.