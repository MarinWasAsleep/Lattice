# Coder prompt — L17 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

PUBLIC SIGNATURES (lecture seule — ne pas écrire)
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

--- lattice_core/effects/tone.py ---
def gaussian_blurimg: Image, params: dict, rng: np.random.Generator  # Blur the image with a gaussian kernel whose sigma is radius / 3.
def sharpenimg: Image, params: dict, rng: np.random.Generator  # Sharpen the image with an unsharp mask of the given amount and radius.
def glowimg: Image, params: dict, rng: np.random.Generator  # Add a screen-blended bloom built from the bright pass of the image.
def noiseimg: Image, params: dict, rng: np.random.Generator  # Add gaussian noise of standard deviation amount / 2, shared or per channel.
def posterizeimg: Image, params: dict, rng: np.random.Generator  # Quantise every channel to at most `levels` evenly spaced values in [0, 1].

--- lattice_core/color.py ---
def to_floatimg: PILImage.Image  # Convert any Pillow image to float32 RGB in [0, 1], compositing alpha over white.
def to_rgb8img: Image  # Convert a float32 image in [0, 1] to uint8, rounding half up and clipping.
def to_pilrgb8: RGB8  # Wrap a uint8 RGB array in a Pillow image.
def luminanceimg: Image  # Return the sRGB luminance of every pixel as a float32 (H, W) array.
def nearest_indeximg: Image, palette: Palette, metric: str='srgb'  # Return the index of the closest palette colour for every pixel, under metric.
def metric_codemetric: str | int  # Return the kernel code of a colour metric name, or pass an int code through.
def to_working_spaceimg: Image, metric: str | int  # Convert an sRGB image or palette to the space the metric compares in.
def srgb_to_oklabimg: Image  # Convert sRGB values in [0, 1] to Oklab (Ottosson's matrices, no axis scaling).
def srgb_to_labimg: Image  # Convert sRGB values in [0, 1] to CIELAB under the D65 white point.
def apply_paletteidx: Indices, palette: Palette  # Map palette indices back to float32 colours.
def adjustimg: Image, brightness: float, contrast: float, gamma: float, saturation: float=0.0  # Apply gamma, contrast around 0.5, brightness and saturation, clipping to [0, 1].
def srgb_to_linearimg: Image  # Decode sRGB-encoded values in [0, 1] to linear light with the exact transfer function.
def linear_to_srgbimg: Image  # Encode linear-light values in [0, 1] back to sRGB with the exact transfer function.
def auto_levelsimg: Image, low: float=0.5, high: float=99.5  # Stretch each channel between its low and high percentiles, clipping to [0, 1].
def gaussian_blurimg: Image, sigma: float  # Blur img with a separable Gaussian of the given sigma; sigma <= 0 is a no-op.
def downscaleimg: Image, factor: int  # Average factor x factor blocks, replicating the edge when the size is not divisible.
def upscale_nearestimg: Image, factor: int, shape: tuple[int, int]  # Repeat every pixel factor times, then crop to shape.
def nearest_index_pxr: float, g: float, b: float, palette: np.ndarray, metric: int=0  # Return the index of the palette colour closest to (r, g, b); numba kernel.

TASK CARD
### L17 · NTSC / VHS
- wave: 2 · deps: L2 · executor: OMH deep · review: strict · size: L
- owns: `lattice_core/effects/ntsc.py`, `tests/test_ntsc.py`
- context: §16
- spec: implement §16. Chain: RGB → YIQ → chroma low-pass → chroma subsample → noise → demodulate
  → RGB. Parameters as listed. VHS additions: `head_switching`, `tracking_noise`, `snow`,
  `sharpening`, `tape_speed`. **Six named presets plus a simple mode with four sliders**; the full
  set behind an advanced toggle.
- accept:
  - all parameters at their neutral values return the input within 1/255.
  - `head_switching` displaces only the bottom band, and the band height is a parameter.
  - `chroma_lowpass` reduces chroma variance while leaving luma variance within 5 %.
  - each of the six presets produces a distinct output on the same input.
  - the simple mode exposes exactly four parameters.
  - output shape equals input shape.

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/effects/ntsc.py` n'existe PAS (à créer). Convention des effets du core : les
modules de `lattice_core/effects/` (ex. tone.py, pixel_sort.py, channel_shift.py) s'enregistrent
via `register_effect(id, name, params)` et exposent `fn(img, params)` où img est un array
float32 (H, W, 3) dans [0, 1] — lisez-en un AVANT de coder. `tests/test_ntsc.py` n'existe pas.
Un effet doit être déterministe (seed via params["seed"]) et ne pas muter son entrée. La chaîne
RGB→YIQ→chroma low-pass→chroma subsample→noise→demodulate→RGB doit émuler un SIGNAL (pas un
overlay) : l'implémentation en numpy pur est attendue. Les libellés ParamSpec doivent réutiliser
les clés du catalogue i18n (lattice_dither/i18n/en.json — test_i18n, DEV-212). 6 presets nommés
+ mode simple à 4 sliders + toggle advanced.

CONTRAT DE RÉCEPTION (tests déterministes) : paramètres neutres → entrée à 1/255 près ;
head_switching ne déplace que la bande du bas (hauteur = paramètre) ; chroma_lowpass réduit la
variance chroma, luma variance à 5 % près ; 6 presets → 6 sorties distinctes sur même entrée ;
mode simple expose exactement 4 paramètres ; shape identique.