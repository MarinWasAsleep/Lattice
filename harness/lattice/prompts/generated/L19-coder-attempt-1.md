# Coder prompt — L19 · attempt 1 (généré par l'orchestrateur, 2026-11-17, contrat 0.1.0 gelé)

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

## §18 Seed and masks

**Seed.** One seed drives every random operator in a render. Reroll is a single button. Each module
can be locked so a reroll changes the noise without losing the block layout. The seed is serialised
into the preset, so a good accident is reproducible.

**Masks.** A greyscale image, same size as the source, where 0 means no effect and 1 means full
effect. Masks are:
- paintable in the app (brush, gradient, luminance range),
- importable and exportable as PNG,
- referenced by path in the preset, or embedded as base64 when under 64 KB.

A global effect is a filter. A localised effect is a composition. Every glitch effect accepts a
mask.

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

--- lattice_core/preset.py ---
class Preset:
def to_jsonpreset: Preset  # Serialise preset as sorted, two-space-indented v3 JSON with one trailing newline.
def from_jsontext: str, *, app: str | None=None, available: Iterable[str] | None=None  # Parse a v1, v2 or v3 preset; an explicit app context resolves absent renderers.
def save_presetpath: str | Path, preset: Preset  # Write preset as UTF-8 v3 JSON, creating parent directories.
def load_presetpath: str | Path, *, app: str | None=None, available: Iterable[str] | None=None  # Read a JSON preset file and parse it with an optional app context.
def to_pipeline_specpreset: Preset  # Return PipelineSpec carrying renderer/style and continuous-mode nulls (§5 S1).
def from_pipeline_specspec: PipelineSpec  # Build a v3 preset from a PipelineSpec, keeping renderer and renderer_style.

TASK CARD
### L19 · Seed system and masks
- wave: 2 · deps: L2 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/seed.py`, `lattice_core/mask.py`, `tests/test_seed.py`,
  `tests/test_mask.py`
- context: §18
- spec: implement §18. One seed drives every random operator; per-module lock; reroll. Masks:
  greyscale, paintable, importable/exportable PNG, referenced by path or embedded base64 under
  64 KB.
- accept:
  - the same seed produces identical output across two runs of a multi-effect pipeline.
  - a locked module keeps its output when the seed is rerolled; an unlocked one changes.
  - a mask of all zeros is a no-op for every effect that accepts one.
  - a mask round-trips through PNG export/import within 1/255.
  - a mask over 64 KB is referenced by path, not embedded.
  - the seed is serialised into the preset and restored on load.

CURRENT CONTENT OF YOUR FILES (premier essai)
`lattice_core/seed.py` et `lattice_core/mask.py` n'existent PAS (à créer). `tests/test_seed.py`
et `tests/test_mask.py` n'existent pas. CONTEXT : les effets du core (effects/*) prennent
`fn(img, params, rng)` et, selon la CONVENTION DEV-214, un masque en keyword-only (', *,
mask=...') qui lève ValueError sur shape mismatch. Cette carte possède le SCHÉMA des masques
(mask.py) : elle doit rendre le masque joignable par le pipeline (le schéma EffectInstance a
beau ne pas avoir de champ masque — cf. L14/L15 — la réduire ici, ex. un champ mask référencé
par path ou base64 §18, et un champ seed). Le seed (§18) : une graine pilote chaque opérateur
aléatoire du pipeline ; per-module lock (un module verrouillé garde sa sortie au reroll d'une
graine) ; reroll. Les libellés ParamSpec doivent réutiliser les clés du catalogue i18n
(test_i18n / DEV-212). Contract : latence/ressource, un effet ne doit pas s'étonner d'un
mask None (comportement = pas de masque).

CONTRAT DE RÉCEPTION (tests déterministes) : même graine → sortie identique sur un pipeline
multi-effets à deux runnes ; module verrouillé garde sa sortie au reroll / déverrouillé change ;
masque tout-zéros = no-op pour chaque effet qui en accepte un ; round-trip PNG du masque à
1/255 près ; masque > 64 Ko référencé par path, pas embarqué ; seed sérialisé dans le preset et
restauré au chargement.