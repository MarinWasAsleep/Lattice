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
mode simple expose exactement 4 paramètres ; shape identique.--- RETRY attempt 2 ---

Les fichiers owns existent (état attempt 1 : 23 tests, suite 1759 verte). Fix exactly what is
reported below; change nothing else; keep passing tests passing. Carte STRICT (relecture Sonnet).

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "blocker",
      "file": "lattice_core/effects/ntsc.py",
      "line": 166,
      "what": "`_bandwidth_filter` convolves along axis 0, which is vertical. It blurs scan lines into each other instead of limiting the horizontal signal bandwidth.",
      "why": "Bandwidth in an NTSC/VHS chain is a horizontal (along-the-line) property. A vertical blur is a wrong result and looks nothing like tape. The `tape_speed`, `bandwidth` and `ringing` parameters all go through this path. No test would catch it.",
      "fix": "Filter along axis=1. Add a test that a vertical step edge is smeared horizontally by `bandwidth < 1` and that a horizontal edge is left unchanged."
    },
    {
      "severity": "major",
      "file": "lattice_core/effects/ntsc.py",
      "line": 164,
      "what": "`ringing` selects a Gaussian (\"butterworth\") or a box (\"constant_k\"). Both kernels are non-negative, so neither can produce overshoot or Gibbs ringing. The comment and docstring claim they do.",
      "why": "The parameter does not do what its name says, and the \"butterworth\" label is wrong for a Gaussian. For a card meant to be a signal emulation, this is a misleading control.",
      "fix": "Use a kernel with negative lobes: a windowed-sinc or an actual Butterworth/constant-k frequency response. Test that the edge response overshoots. Otherwise rename the parameter and correct the docstrings."
    },
    {
      "severity": "major",
      "file": "lattice_core/effects/ntsc.py",
      "line": 187,
      "what": "In `_head_switching`, `shift = round(amount * width)` is applied with `np.roll`. At `amount = 1.0`, which is the slider maximum, the roll equals the width and is the identity.",
      "why": "The maximum setting does nothing, and displacement is non-monotone in `amount`: 0.5 and 1.0 are the two extremes of a wrapped cycle. Tests only use 0.6 and 0.8. The default `band_height` of 0.25 is also far from a real head-switching band of a few lines.",
      "fix": "Cap the shift, for example `amount * width * 0.5`, so it stays below the width. Consider a skew that grows within the band and a small default band. Add an `amount=1.0` test that the band differs from the base."
    },
    {
      "severity": "major",
      "file": "lattice_core/effects/ntsc.py",
      "line": 34,
      "what": "The \"advanced toggle\" required by the card is not implemented. `SIMPLE_PARAMS` is only a duplicated tuple of ParamSpecs that nothing consumes. There is no mode or advanced flag, and nothing applies the presets (`preset()` is untested and unused).",
      "why": "Acceptance item \"simple mode exposes exactly four parameters, full set behind an advanced toggle\" is met only in the trivial sense of `len(SIMPLE_PARAMS) == 4`. The corresponding test cannot fail against the real requirement.",
      "fix": "Express the simple/advanced split in the registry metadata, for example an `advanced: bool` flag on ParamSpec or a `simple_ids` attribute on the effect. Derive `SIMPLE_PARAMS` from `_PARAMS` rather than duplicating it. Test the registry-level exposure and `preset()`, including its KeyError."
    },
    {
      "severity": "major",
      "file": "lattice_core/effects/ntsc.py",
      "line": 28,
      "what": "The ParamSpec labels reuse unrelated i18n keys: snow=\"Contrast\", sharpening=\"Darkness\", chroma_lowpass=\"Level\", band_height=\"Level\", ringing=\"Ratio\", tape_speed=\"Scale\", luma_smear=\"Spacing\", tracking_noise=\"Threshold\".",
      "why": "The user sees controls whose names do not match what they do, and two controls share the same label. This is a misleading message. The frozen-catalogue workaround (DEV-212) cannot justify it, and a lattice_core test importing `lattice_dither.i18n` is also a core-to-app coupling.",
      "fix": "Add proper NTSC keys to the catalogue through a registered deviation or contract change. If the catalogue is truly frozen, escalate (E4/E7) rather than ship false labels. Drop the `lattice_dither` import from the core test."
    },
    {
      "severity": "major",
      "file": "tests/test_ntsc.py",
      "line": 1,
      "what": "Most stages have no isolated test: `bandwidth`, `ringing`, `tape_speed`, `luma_noise`, `composite_noise`, `chroma_phase_noise`, `tracking_noise`, `snow` and `sharpening` are only exercised inside the aggressive/preset runs. The preset-distinctness test uses `np.array_equal`, so any tiny difference passes.",
      "why": "A stage that does nothing, or does the wrong thing as the bandwidth axis bug does, passes all the tests. The preset test would pass even if the presets were nearly identical.",
      "fix": "Add one test per parameter that checks the specific effect (axis, variance or edge response), and that the parameter is a no-op at neutral. Make the preset test use a minimum mean-absolute-difference threshold."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/ntsc.py",
      "line": 215,
      "what": "`_snow` adds independent per-channel gaussian noise on RGB after demodulation. It is an overlay, not a signal-domain effect, and it produces coloured speckle rather than monochrome snow. `sharpening` is also done post-demod on RGB.",
      "why": "The card insists on signal emulation, not overlay. The same applies to sharpening, which is a luma operation in a real VCR.",
      "fix": "Inject snow into Y (and optionally I/Q) before demodulation, and sharpen Y only."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/ntsc.py",
      "line": 27,
      "what": "The `seed` ParamSpec is never read: noise comes only from the `rng` argument. The YIQ comment claims the matrices are \"normalised to [0, 1]\", but I and Q are signed.",
      "why": "A dead parameter and a docstring that lies. The `bandwidth` blur also jumps to radius 1 as soon as `bw < 0.999`, so it is discontinuous near neutral.",
      "fix": "Remove `seed` or document that it is unused. Correct the comment. Make the kernel radius continuous in `bw`."
    },
    {
      "severity": "minor",
      "file": "tests/test_ntsc.py",
      "line": 6,
      "what": "The comment says `__init__.py` does not import the effect yet, but it now does. `noqa: E402` is unneeded.",
      "why": "Stale comment.",
      "fix": "Remove the comment and the unneeded noqa."
    }
  ],
  "regression": "none (effects/__init__ only adds the ntsc import; full suite 1759 passed per gate)",
  "renderer_invariants": "all six hold (effect card; no renderer touched or changed)",
  "tests_that_cannot_fail": [
    "test_simple_mode_exposes_exactly_four_parameters (asserts the length of a constant tuple, not the exposed UI)",
    "test_simple_params_carry_i18n_catalogue_labels (asserts that labels exist in the catalogue, which enshrines the misleading labels)",
    "test_each_preset_produces_a_distinct_output_on_the_same_input (array_equal threshold is trivially met)",
    "test_extreme_params_never_raise (the NEUTRAL half adds nothing beyond the identity test)"
  ],
  "notes": "Verdict is based on reading the diff only; I did not run the code. §16 itself was not provided, so conformance of the parameter list and presets could not be checked. The vertical bandwidth filter and the head_switching wrap at 1.0 are real maths defects that the current tests cannot catch. The i18n label workaround needs a registered deviation, or an escalation if the catalogue cannot change."
}

INSTRUCTIONS DE L'ORCHESTRATEUR :
1. **Blocker** : `_bandwidth_filter` doit borner la BANDE HORIZONTALE (convoluer le long de
   l'axe des lignes de balayage), PAS l'axe vertical. Corriger l'axe.
2. **ringing** : un vrai « ringing » (Butterworth / constant-k) exige un noyau qui sonne
   (lobes négatifs ou réponse en fréquence à sous-dépassement), pas un flou gaussien/box.
   Implémentez une réponse de filtre qui produit du ringing (ex. noyau à lobes opposés ou
   filtrage fréquentiel), sinon renommez/neurotisez la sémantique.
3. **head_switching** : le déplacement de la bande du bas ne doit pas replier (np.roll à
   amount=1.0 = largeur entière) ; clamp/fenêtre pour ne déplacer que la bande voulue.
4. **Toggle advanced** : la carte exige un mode simple (4 sliders) ET l'ensemble complet
   derrière un toggle advanced. Exposez BOTH (simple = 4 paramètres mappés sur les vrais
   paramètres ; advanced = les 14). Ne pas se contenter d'un tuple dupliqué.
5. **Libellés i18n** : les réutilisations sémantiquement fausses (snow→Contrast,
   sharpening→Darkness, chroma_lowpass→Level…) sont refusées — soit trouvez une clé du
   catalogue qui VEUT DIRE le paramètre, soit déclarez le paramètre sans label trompeur
   (et signalez E1). Le relecteur refuse d'ancrer des labels mensongers.
6. **Tests** : isolez chaque étage (bandwidth, ringing, tape_speed, luma_noise,
   composite_noise, chroma_phase_noise, head_switching, snow) avec un test déterministe qui
   prouve l'effet (pas seulement le round-trip neutre).
7. **snow** : doit être dans le domaine signal (bruit injecté dans la chaîne, pas un overlay
   RGB post-démod) — ou justifiez autrement (E1).
8. **seed** : le ParamSpec seed doit être lu (utilisez-le pour le rng au lieu d'ignorer
   l'argument). §16 est inclus dans les extraits ci-dessus.
--- RETRY attempt 3 (retry du FIX Sonnet pass 2) ---

Les fichiers owns existent (état attempt 2 : 61 tests, suite 1855 verte). Fix exactly what is
reported below; change nothing else; keep passing tests passing.

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_core/effects/ntsc.py",
      "line": 98,
      "what": "_generator always builds default_rng(int(params['seed'])) and discards the rng argument. 'seed' is a ParamSpec with default 0, so resolve_params always supplies it and the `seed is None` fallback is dead code.",
      "why": "§5 gives effect i `default_rng(seed + i)` and post-effect j `default_rng(seed + 1000 + j)`. With this code the pipeline seed never reaches NTSC. Two NTSC instances at different positions get identical noise. Changing the global seed leaves the output unchanged unless the user also edits the effect's own seed. test_seed_parameter_drives_the_noise_not_the_rng_argument asserts this behaviour, so the tests now lock the deviation in.",
      "fix": "Derive the generator from both inputs, e.g. default_rng([int(params['seed']), int(rng.integers(0, 2**32))]). Or treat the param as an offset on the pipeline rng and keep rng as the source. Update the test so that a different rng gives different noise and the same (seed, rng) gives identical noise. If §16 really mandates a standalone seed, state in the notes that §5 is overridden and escalate as E2."
    },
    {
      "severity": "major",
      "file": "tests/test_ntsc.py",
      "line": 234,
      "what": "test_each_noise_and_chroma_stage_is_a_noop_at_neutral compares _apply(img, {param: 0.0}) with _apply(img). Every ZERO_STAGES parameter is already 0.0 in NEUTRAL, so both calls are the same call.",
      "why": "The test cannot fail. Adding a bogus always-on noise term to a stage at amount 0 would still pass, because both sides are equally wrong. The coder's notes claim a no-op check per stage that this test does not provide.",
      "fix": "Compare against an independent reference. Either assert the stage output equals the input to the stage (call the private function with amount=0 and check `is`/array_equal), or compare against the identity chain with the stage removed. Alternatively add a mutation-style check: a tiny positive amount (1e-6) must differ from the zero case by less than the tolerance."
    },
    {
      "severity": "minor",
      "file": "tests/test_ntsc.py",
      "line": 258,
      "what": "The last assertion of test_tape_speed_narrows_the_bandwidth_in_order, `_apply(img, {'tape_speed': 'sp'}) == _apply(img)`, is also a tautology, because 'sp' is the default.",
      "why": "It proves nothing about sp multiplying the bandwidth by 1.0.",
      "fix": "Drop it, or compare sp against an explicit bandwidth=1.0 identity (np.allclose to the input)."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/ntsc.py",
      "line": 34,
      "what": "Several labels are misleading or ambiguous in the UI: 'Matrix' for ringing, 'Resolution' for tape_speed, 'Angle' for chroma_phase_noise, 'Scale' for band_height, 'Ratio' for head_switching. The comment also names lattice_dither/i18n/en.json from inside lattice_core.",
      "why": "The controls become unreadable next to each other, and the core's comments point at an application's catalogue (close to E8 in spirit, though no import exists). LABEL_NOTES documents the mapping but the end user never sees it.",
      "fix": "Open a card that owns the catalogue so NTSC-specific keys can be added. Until then, drop the lattice_dither path from the comment. Use more descriptive labels from the neutral vocabulary where one exists, or label with the human-readable name of the parameter."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/ntsc.py",
      "line": 197,
      "what": "'constant_k' is implemented as a brick-wall filter, which is not a constant-k filter. In _subsample, `height` is unpacked and never used.",
      "why": "The name and the docstring tell different stories. The unused variable is a hygiene lapse.",
      "fix": "Add a docstring note that 'constant_k' means the sharp-cutoff variant, or rename the choice if §16 allows it. Replace `height, width` with `_, width`."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/ntsc.py",
      "line": 355,
      "what": "All stochastic stages draw from one shared generator in sequence.",
      "why": "Enabling a stage that consumes random numbers (phase noise, for example) shifts the noise realisation of every later stage. A preset therefore changes more than its own stage when the user tweaks one slider.",
      "fix": "Spawn one child generator per stage, e.g. default_rng([seed, stage_index]). This also makes the stage independent of the order in which they run."
    }
  ],
  "regression": "none visible in this diff. Only effects/__init__.py and the new files change, and G7 was green (1855 passed). I could not read effects/__init__.py to confirm the registration line.",
  "renderer_invariants": "not applicable: this is an effect card with no CellRenderer in the diff. The effect does not mutate its input (copy plus a test) and output shape equals input shape. Per-seed determinism holds, but the pipeline seed is ignored (see finding 1).",
  "tests_that_cannot_fail": [
    "test_each_noise_and_chroma_stage_is_a_noop_at_neutral (both sides are the same neutral call)",
    "test_tape_speed_narrows_the_bandwidth_in_order, last assertion (sp is the default)"
  ],
  "notes": "Maths and the accept items hold: bandwidth runs along the scan lines, the ringing kernels differ, head switching is capped and bottom-only, simple mode has exactly four parameters, and neutral is the identity within 1/255. I did not run the code; this review is from the diff and the gate output.\nThe main defect is that the pipeline's seed derivation is bypassed (§5). I could not see §16, so if it explicitly mandates a standalone seed parameter, the issue becomes a contract question to settle (E2) and not a coder error.\nThe remaining findings are small; one more cycle should clear all of them."
}
INSTRUCTIONS DE L'ORCHESTRATEUR :
1. **Major seed/rng** : `_generator` ne doit PAS ignorer l'argument rng. Décidez une précédence
   CLAIRE et documentée : si params['seed'] est fourni, il prime (default_rng(seed)) ; sinon
   utilisez l'argument rng du pipeline. Testez les deux chemins.
2. **Major test no-op** : `_apply(img, {param: 0.0})` vs `_apply(img)` — le test ne prouve pas
   le no-op (les défauts incluent déjà 0.0 ?). Renforcez : prouvez que changer le paramètre
   depuis son neutrophile change la sortie (test de vivacité par paramètre déjà là ? le rendre
   discriminant) et que le neutre est bien neutre.
3. **Minors** : dernière assertion tape_speed (== _apply) faible → assertion sur la largeur de
   bande mesurée ; labels trompeurs ('Matrix' pour ringing, 'Resolution' pour tape_speed,
   'Angle'…) → choisir des clés i18n qui VEULENT DIRE le paramètre (ou LABEL_NOTES honnête) ;
   `constant_k` = brick-wall ≠ constant-k → soit renommer la sémantique (et le docstring) soit
   implémenter approx constant-k (E1 si non résoluble) ; générateur partagé entre étages
   stochastiques → streams séparés par étage (dériver du seed) pour l'indépendance.
4. §16 est inclus dans les extraits ci-dessus.
