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
— les runs (définis par la bande black..white) sont triés individuellement.--- RETRY attempt 2 ---

Les fichiers owns existent (état attempt 1 : 27 tests, suite 1759 verte). Fix exactly what is
reported below; change nothing else; keep passing tests passing.

```json
{
  "verdict": "FIX",
  "findings": [
    {
      "severity": "major",
      "file": "lattice_core/effects/pixel_sort.py",
      "line": 160,
      "what": "Mask transported via undocumented params[\"mask\"] side-channel (read line 157, outside ParamSpec); a shape-mismatched mask is silently dropped (mask=None) instead of erroring.",
      "why": "resolve_params rejects unknown keys, so the mask can never arrive through normal parameter resolution; the only way in is post-hoc injection (as the test helper _apply_mask does). Lines 160-161 silently discard a wrong-sized mask -> a caller asking for a mask gets a fully-unmasked result with no signal. Sibling effect L14 (displace.py _mask_weights) transports the mask as keyword-only and raises ValueError on size mismatch. Two effects in the same package now have incompatible mask APIs; the compositor (L20) must special-case one, or one silently loses its mask. Contract §14 is silent (E1), but silent-drop on mismatch is a latent wrong-result defect, not a documented convention.",
      "fix": "Accept mask as keyword-only mirroring displace.py and raise ValueError on shape mismatch instead of setting mask=None. If the params-dict channel is kept, validate/raise on mismatch and register an E1 deviation recording the transport choice so L20 reconciles it with displace."
    },
    {
      "severity": "minor",
      "file": "tests/test_pixel_sort.py",
      "line": 72,
      "what": "test_fully_white_brightness_zero_sorts_every_row and test_fully_black_black_zero_sorts_nothing are tautological.",
      "why": "Both images are constant (all-ones / all-zeros), so any reordering - including a no-op implementation - yields the identical image and out == img holds. Neither can detect a missing sort. The accepts are actually proven by test_brightness_zero_sorts_every_row_ascending and test_pixels_below_brightness_are_not_sorted.",
      "fix": "Replace the all-white/all-black assertions with an image having a non-trivial ordering under the tested key, or drop them as redundant."
    },
    {
      "severity": "minor",
      "file": "tests/test_pixel_sort.py",
      "line": 245,
      "what": "test_effect_is_deterministic and test_diagonal_is_deterministic assert determinism that holds trivially because rng is never used.",
      "why": "The effect ignores its rng argument (stable sort is deterministic by construction), so these tests pass regardless of seed and cannot fail.",
      "fix": "Note pixel_sort is intentionally rng-free, or exercise determinism across differing rng values to make the claim meaningful."
    },
    {
      "severity": "minor",
      "file": "lattice_core/effects/pixel_sort.py",
      "line": 169,
      "what": "No trailing newline at end of file (also test_pixel_sort.py).",
      "why": "Hygiene: both new files end without a final newline.",
      "fix": "Append a trailing newline to both files."
    }
  ],
  "regression": "none",
  "renderer_invariants": "N/A — pixel_sort is an effect, not a CellRenderer. Effect-level analogues hold and are tested: output shape preserved, no input mutation, deterministic.",
  "tests_that_cannot_fail": [
    "test_fully_white_brightness_zero_sorts_every_row",
    "test_fully_black_black_zero_sorts_nothing",
    "test_effect_is_deterministic",
    "test_diagonal_is_deterministic"
  ],
  "notes": "columns(A) == rows(A^T).T is mathematically correct; the literal reading columns(A) == rows(A).T is false (counterexample A=[[2,1],[0,3]] gives columns [[0,1],[2,3]] vs rows.T [[1,0],[2,3]]), so the coder's interpretation honors the contract intent. All six accept items genuinely implemented (27 owned tests pass). i18n label reuse matches the accepted DEV-212 precedent. The mask transport (E1) should be recorded as a deviation and reconciled with L14's displace convention before L20."
}

INSTRUCTIONS DE L'ORCHESTRATEUR :
1. **Major mask** : alignez le transport du masque sur le motif de L14 (displace.py) — masque
   en keyword-only (mirror displace), et raise ValueError sur shape mismatch au lieu de
   mask=None silencieux. Ne gardez PAS le canal params['mask'] comme chemin normal si
   resolve_params le rejette ; si vous le gardez, validez + raise. Consignez E1 (transport).
2. Tests tautologiques (all-white/all-black) : remplacez par une image à ordre non trivial
   sous la clé testée, ou supprimez-les (les accepts sont couverts par les tests ascendants).
3. Determinism rng-unused : soit notez pixel_sort intentionnellement rng-free, soit exercez
   le déterminisme sur rng différents.
4. Trailing newline sur les deux fichiers.
5. La convention masque (keyword-only, ValueError) doit MATCHER displace.py pour que L20
   (compositor) n'ait pas à spécial-case r un des deux effets.
