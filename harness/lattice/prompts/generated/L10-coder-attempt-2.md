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

CONTRACT EXCERPTS (version 0.1.0)

## §2 Packages and repositories

Four repositories, four distributions:

```
lattice-core      import lattice_core      no UI dependency in the base install
lattice-dither    import lattice_dither    depends on lattice-core>=0.1,<0.2
lattice-glyph     import lattice_glyph     depends on lattice-core>=0.1,<0.2
lattice-glitch    import lattice_glitch    depends on lattice-core>=0.1,<0.2
```

**What L1 actually moves** (current tree at HEAD `b4b0aea`, portage Linux approuvé): `core/{color,pipeline,presets,types,registry}.py`,
the `palettes/` package, `dither/` (from `algorithms/`), `effects/`, `bridge/`. The application keeps
`ui/`, `export/`, `preprocess/`, `i18n/` and its own `cli.py` (the 1.1 verbs are app-specific; the shared CLI
frame is created with the application shells). `core/animation.py` is moved into `lattice_core` by
card L-LOOP (N-image loop, decided 2026-11-16); full video is out of scope for the suite (H11
coherence pass). There is no `core/palette.py` in the current tree:
palettes are a package. `image.py`, `cell.py` and `renderers/` are created by the cards (L2+).

- `lattice-core` base install depends on **numpy, numba, Pillow only**. PySide6 is an optional
  extra: `lattice-core[ui]`. A CLI-only user must never download Qt.
- Applications depend on core, never the reverse. Core must not import any application.
- Core is published to PyPI. Applications pin a compatible range, not an exact version.
- Local development uses editable installs of all four in one virtual environment.

`lattice_core` module layout:

```
lattice_core/
  image.py        buffer, load, save, resize, crop
  color.py        metrics, nearest_index, adjust
  palette.py      Palette model, extraction, import/export
  cell.py         CellGrid, RenderStyle, CellRenderer, registry
  renderers/      pixel.py, glyph_ramp.py, glyph_shape.py, bitmask.py, text.py
  dither/         the 33 algorithms, moved from Lattice Dither unchanged
  effects/        the 10 Lattice Dither effects plus the glitch effects
  pipeline.py     PipelineSpec, render
  preset.py       preset v3 read/write
  bridge/         ArtCraftClient, photocraft.py, designcraft.py
  cli.py          shared argument parsing and exit codes   (frame built with the app shells, L12/L20)
  ui/             shared widgets, imported only under the [ui] extra.
                  Owned by card L-UI (after L5, before L12/L20, decided 2026-11-16): preview
                  canvas + worker with before/after split, Looks grid (thumbnails on the
                  current image), one full-resolution export dialog, bridge status dot, empty
                  state. L-UI fixes the two blocker findings of the Dither product review
                  (export resolution, preset indicator) first.
```

## §9 Glyph renderers

Four renderers, one per mechanism.

**`glyph_ramp`** — one monospace character per cell. `luma` (S2, decided 2026-11-16) indexes an
ordered ramp, darkest first, independently of the palette: a black/white palette still uses the
full ramp. Options: `ramp` (string), `font` (path), `fg`/`bg` (colour or `transparent`),
`mode` (`mono` | `fg_colour` | `bg_colour` | `palette`), `offset` (float, shifts the
luma-to-glyph mapping), `invert` (bool). There is no `size` option (H11, decided 2026-11-16):
the glyph font size is derived from `cell_h` (§5 step 6), so each glyph covers its cell exactly.

- The ramp contract is explicit: **darkest character first, lightest last**. A ramp that violates
  it is not detected, it is documented.
- `offset` is animatable and is the cheapest way to make a still image shimmer.
- Aspect correction uses `cell_aspect()`; the default font ratio is 1/2 (width/height).

**`glyph_shape`** — one monospace character per cell, chosen by shape rather than by density.

- For each glyph, place `k = 6` sampling circles inside the cell (top/middle/bottom × left/right).
  For each circle, sample many points and compute the fraction inside the glyph's ink. That is the
  glyph's shape vector.
- **Normalise each component by the maximum across the alphabet.** Without this every vector
  clusters in the bottom-left and every cell maps to the same few characters.
- Per cell, compute the same vector from `samples` and take the nearest neighbour.
- Shape vectors are precomputed per (font, size) and cached at module level.
- Budget: 1024×1024, 64 glyphs, under 200 ms after warm-up. If missed, a precomputed lookup table
  over quantised vectors is allowed.

**`bitmask`** — sub-cell dots. One code path, four geometries:

| Geometry | Sub-grid | Codepoints |
|---|---|---|
| `braille` | 2×4 | U+2800 + bitmask |
| `sextant` | 2×3 | U+1FB00..U+1FB3B |
| `quadrant` | 2×2 | U+2596..U+259F |
| `half_block` | 1×2 | U+2580, U+2584, U+2588 |

Threshold `samples` into on/off sub-dots. Options: `threshold` (0..1), `fg`/`bg`. The sub-dot
decision belongs to the algorithm, run at subgrid resolution (S3): there is no `dither` option
(removed; H11 coherence pass).

**`pixel`** — one solid square per cell. This is Lattice Dither's current behaviour, expressed through
the abstraction. It must reproduce the 1.0 output byte for byte.

TASK CARD

### L10 · Glyph set browser and non-Latin ramps
- wave: 1 · deps: L6 · executor: OMH capable · review: light · size: M
- owns: `lattice_core/ui/glyph_browser.py`, `lattice_core/data/ramps.json`,
  `tests/test_ramps.py`
- context: §9
- spec: a browsable catalogue of glyph sets with a **live preview of the actual ramp rendered in the
  current font**, which almost nobody ships. Categories: classic ASCII, numbers, symbols, blocks,
  geometric, braille, playing cards, and non-Latin ramps (Japanese, Korean, Chinese, Russian,
  German, French, Spanish). `ramps.json` holds the data; the browser renders it.
- accept:
  - `ramps.json` validates against a schema test and every ramp is non-empty and darkest-first.
  - the browser renders a preview for every set without raising.
  - at least 8 categories and at least 6 non-Latin ramps are present.
  - selecting a set updates the preview within 100 ms.

SITUATION — attempt 1 de cette carte, mais le code existe déjà et n'a aucun test
Une session précédente interrompue a laissé `lattice_core/ui/glyph_browser.py` (413 lignes) et
`lattice_core/data/ramps.json` (269 lignes, déjà conforme au schéma décrit ci-dessous). Ni l'un ni
l'autre n'a été relu, et **`tests/test_ramps.py` n'existe pas**. Ton travail : livrer les deux
fichiers + écrire `tests/test_ramps.py` couvrant les cinq items d'accept.

État vérifié par l'orchestrateur, que tu dois corriger :
- `glyph_browser.py:203` dépasse 100 colonnes (ruff E501) — c'est le SEUL défaut de lint.
- règle 6 du prompt : ≤ 400 lignes par fichier. 413 > 400 : découpe (helpers ou constantes déplacés
  dans le même module restent dans le même fichier — si tu ne peux pas descendre sous 400 sans
  changer de comportement, dis-le en NOTES et propose).
- le module est sous `lattice_core/ui/` : il n'est importé que sous l'extra `[ui]`. Aucun import
  applicatif (E8). Les tests Qt tournent en `QT_QPA_PLATFORM=offscreen` (convention du dépôt).
- `ramps.json` est sous `lattice_core/data/` : vérifie que le chargement par chemin fonctionne quand
  le paquet est installé (chemin relatif à `__file__`, pas au cwd) et que le fichier est déclaré
  comme donnée de paquet (il est dans le paquet, `importlib.resources` ou `Path(__file__).parent`).

CONTENU ACTUEL DE `lattice_core/data/ramps.json`

{
  "schema": "lattice.ramps/1",
  "categories": [
    {
      "id": "classic_ascii",
      "name": "Classic ASCII",
      "ladder": "$@B%8&WM#*+=-:;,.·' ",
      "ramps": [
        {
          "id": "classic_10",
          "name": "Classic 10",
          "script": "latin",
          "ramp": "@%#*+=-:. "
        },
        {
          "id": "classic_dense",
          "name": "Dense ASCII",
          "script": "latin",
          "ramp": "$@B%8&WM#"
        },
        {
          "id": "classic_light",
          "name": "Light ASCII",
          "script": "latin",
          "ramp": "=-:,. "
        }
      ]
    },
    {
      "id": "numbers",
      "name": "Numbers",
      "ladder": "8069453271 ",
      "ramps": [
        {
          "id": "numbers_ten",
          "name": "Digits, ten steps",
          "script": "latin",
          "ramp": "8069453271 "
        },
        {
          "id": "numbers_five",
          "name": "Digits, five steps",
          "script": "latin",
          "ramp": "80631 "
        },
        {
          "id": "numbers_three",
          "name": "Digits, three steps",
          "script": "latin",
          "ramp": "801 "
        }
      ]
    },
    {
      "id": "symbols",
      "name": "Symbols",
      "ladder": "@&%$#*+=~-:;,.· ",
      "ramps": [
        {
          "id": "symbols_ladder",
          "name": "Symbol ladder",
          "script": "latin",
          "ramp": "@&%$#*+=~-:,. "
        },
        {
          "id": "symbols_short",
          "name": "Symbol short",
          "script": "latin",
          "ramp": "@%#+=-,. "
        },
        {
          "id": "symbols_light",
          "name": "Symbol light",
          "script": "latin",
          "ramp": "~-;,. "
        }
      ]
    },
    {
      "id": "blocks",
      "name": "Blocks",
      "ladder": "█▉▊▓▋▒▌▍▎░▏· ",
      "ramps": [
        {
          "id": "blocks_shades",
          "name": "Block shades",
          "script": "latin",
          "ramp": "█▓▒░ "
        },
        {
          "id": "blocks_eighths",
          "name": "Block eighths",
          "script": "latin",
          "ramp": "█▉▊▋▌▍▎▏ "
        },
        {
          "id": "blocks_dots",
          "name": "Blocks and dots",
          "script": "latin",
          "ramp": "█▌░· "
        }
      ]
    },
    {
      "id": "geometric",
      "name": "Geometric",
      "ladder": "●◉◍◎○◆◇□△▽· ",
      "ramps": [
        {
          "id": "geometric_circles",
          "name": "Filled circles",
          "script": "latin",
          "ramp": "●◉◍◎○ "
        },
        {
          "id": "geometric_shapes",
          "name": "Outline shapes",
          "script": "latin",
          "ramp": "◆◇□△▽ "
        },
        {
          "id": "geometric_dots",
          "name": "Dots",
          "script": "latin",
          "ramp": "●· "
        }
      ]
    },
    {
      "id": "braille",
      "name": "Braille",
      "ladder": "⣿⣷⣯⣟⡿⢿⣻⣽⣾⣶⣦⣤⣠⣀ ",
      "ramps": [
        {
          "id": "braille_full",
          "name": "Braille, full descent",
          "script": "braille",
          "ramp": "⣿⣷⣯⣟⡿⢿⣻⣽⣾⣶⣦⣤⣀ "
        },
        {
          "id": "braille_four",
          "name": "Braille, four steps",
          "script": "braille",
          "ramp": "⣿⣶⣤⣀ "
        },
        {
          "id": "braille_light",
          "name": "Braille, light",
          "script": "braille",
          "ramp": "⣤⣀ "
        }
      ]
    },
    {
      "id": "playing_cards",
      "name": "Playing cards",
      "ladder": "♠♣♥♦♤♧♡♢ ",
      "ramps": [
        {
          "id": "card_suits",
          "name": "Card suits, filled",
          "script": "latin",
          "ramp": "♠♣♥♦ "
        },
        {
          "id": "card_suits_outline",
          "name": "Card suits, outline",
          "script": "latin",
          "ramp": "♤♧♡♢ "
        }
      ]
    },
    {
      "id": "japanese",
      "name": "Japanese",
      "ladder": "鬱曜語書日中口一 ",
      "ramps": [
        {
          "id": "kanji_density",
          "name": "Kanji, by stroke count",
          "script": "japanese",
          "ramp": "鬱曜書日口一 "
        },
        {
          "id": "kanji_light",
          "name": "Kanji, light",
          "script": "japanese",
          "ramp": "日中口一 "
        }
      ]
    },
    {
      "id": "korean",
      "name": "Korean",
      "ladder": "한국어문자 ",
      "ramps": [
        {
          "id": "hangul_syllables",
          "name": "Hangul syllables",
          "script": "korean",
          "ramp": "한국어문자 "
        }
      ]
    },
    {
      "id": "chinese",
      "name": "Chinese",
      "ladder": "鬱龍書國中一 ",
      "ramps": [
        {
          "id": "hanzi_density",
          "name": "Hanzi, by stroke count",
          "script": "chinese",
          "ramp": "鬱龍書國中一 "
        },
        {
          "id": "hanzi_light",
          "name": "Hanzi, light",
          "script": "chinese",
          "ramp": "國中一 "
        }
      ]
    },
    {
      "id": "russian",
      "name": "Russian",
      "ladder": "ЩЖШМДФБ ",
      "ramps": [
        {
          "id": "cyrillic_dense",
          "name": "Cyrillic, dense",
          "script": "russian",
          "ramp": "ЩЖШМДФБ "
        },
        {
          "id": "cyrillic_light",
          "name": "Cyrillic, light",
          "script": "russian",
          "ramp": "МДФБ "
        }
      ]
    },
    {
      "id": "accented_latin",
      "name": "Accented Latin",
      "ladder": "ÄÖÜẞÉÈÊÀÇÑÁÍÓÚß ",
      "ramps": [
        {
          "id": "german_umlauts",
          "name": "German umlauts",
          "script": "german",
          "ramp": "ÄÖÜẞ "
        },
        {
          "id": "french_accents",
          "name": "French accents",
          "script": "french",
          "ramp": "ÉÈÊÀÇ "
        },
        {
          "id": "spanish_accents",
          "name": "Spanish accents",
          "script": "spanish",
          "ramp": "ÑÁÍÓÚ "
        }
      ]
    }
  ]
}


CONTENU ACTUEL DE `lattice_core/ui/glyph_browser.py`

"""Browsable catalogue of glyph ramps, previewed in the current font (§9, card L10).

The data lives in ``lattice_core/data/ramps.json``: each category documents one master
ladder, darkest glyph first, and every ramp is an ordered subsequence of that ladder — so
"darkest first" is documented data, never detected per font (§9). This module is part of
``lattice_core.ui`` and therefore needs the ``[ui]`` extra; the rest of the core never
imports PySide6.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NoReturn

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lattice_core import color
from lattice_core.cell import CellGrid, RenderStyle, get_renderer
from lattice_core.renderers import glyph_ramp  # noqa: F401  (self-registers "glyph_ramp")
from lattice_core.types import RGB8

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "ramps.json"
SCHEMA = "lattice.ramps/1"
MIN_CATEGORIES = 8
MIN_NON_LATIN_RAMPS = 6
NON_LATIN_SCRIPTS = frozenset(
    {"japanese", "korean", "chinese", "russian", "german", "french", "spanish"}
)
SCRIPTS = frozenset({"latin", "braille"}) | NON_LATIN_SCRIPTS
PREVIEW_CELL = (18, 36)
DEFAULT_FG = "#111114"
DEFAULT_BG = "#ffffff"
HINT_TEXT = "Pick a category, then a set: the preview draws that ramp darkest to lightest."
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_BW: np.ndarray = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)


@dataclass(frozen=True)
class GlyphRamp:
    """One named ramp of the catalogue, darkest glyph first."""

    id: str
    name: str
    script: str
    ramp: str
    category_id: str


@dataclass(frozen=True)
class GlyphCategory:
    """One catalogue category: its documented ladder and the ramps cut from it."""

    id: str
    name: str
    ladder: str
    ramps: tuple[GlyphRamp, ...]


@dataclass(frozen=True)
class Catalogue:
    """The whole ramps catalogue, in display order."""

    categories: tuple[GlyphCategory, ...]

    def ramps(self) -> tuple[GlyphRamp, ...]:
        """Return every ramp of the catalogue, category by category."""
        return tuple(ramp for category in self.categories for ramp in category.ramps)

    def get(self, ramp_id: str) -> GlyphRamp:
        """Return the ramp registered under ramp_id, or raise KeyError naming it."""
        for ramp in self.ramps():
            if ramp.id == ramp_id:
                return ramp
        raise KeyError(f"unknown glyph ramp: {ramp_id!r}")

    def category(self, category_id: str) -> GlyphCategory:
        """Return the category registered under category_id, or raise KeyError naming it."""
        for category in self.categories:
            if category.id == category_id:
                return category
        raise KeyError(f"unknown glyph category: {category_id!r}")


def _fail(where: str, message: str) -> NoReturn:
    """Raise ValueError naming the offending path of the catalogue document."""
    raise ValueError(f"ramps.json: {where}: {message}")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    """Return value as an object, or raise ValueError naming where it is not one."""
    if not isinstance(value, Mapping):
        _fail(where, "expected an object")
    return value


def _text(node: Mapping[str, object], key: str, where: str) -> str:
    """Return node[key] as a non-empty string, or raise ValueError naming it."""
    value = node.get(key)
    if not isinstance(value, str) or not value:
        _fail(f"{where}.{key}", "expected a non-empty string")
    return value


def _identifier(node: Mapping[str, object], where: str) -> str:
    """Return node["id"] as a lowercase slug, or raise ValueError naming it."""
    value = _text(node, "id", where)
    if not _IDENTIFIER.match(value):
        _fail(f"{where}.id", f"expected a lowercase slug, got {value!r}")
    return value


def _unique(values: list[str], where: str) -> None:
    """Raise ValueError when values holds a duplicate, naming the repeated one."""
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail(where, f"duplicate id {value!r}")
        seen.add(value)


def _ordered(ramp: str, ladder: str, where: str) -> None:
    """Raise ValueError unless ramp is an ordered subsequence of ladder (§9: darkest first)."""
    at = 0
    for glyph in ramp:
        at = ladder.find(glyph, at)
        if at < 0:
            _fail(f"{where}.ramp", f"{glyph!r} is out of ladder order or absent from the ladder")
        at += 1


def _ramp_entry(data: object, category_id: str, where: str) -> GlyphRamp:
    """Validate one ramp object and return it."""
    node = _mapping(data, where)
    identifier = _identifier(node, where)
    name = _text(node, "name", where)
    script = _text(node, "script", where)
    if script not in SCRIPTS:
        _fail(f"{where}.script", f"expected one of {sorted(SCRIPTS)}, got {script!r}")
    ramp = _text(node, "ramp", where)
    if len(ramp) < 2:
        _fail(f"{where}.ramp", "expected at least two glyphs")
    if len(set(ramp)) != len(ramp):
        _fail(f"{where}.ramp", "contains a repeated glyph")
    return GlyphRamp(identifier, name, script, ramp, category_id)


def _category_entry(data: object, where: str) -> GlyphCategory:
    """Validate one category object, its ladder and every ramp cut from it."""
    node = _mapping(data, where)
    identifier = _identifier(node, where)
    name = _text(node, "name", where)
    ladder = _text(node, "ladder", where)
    if len(set(ladder)) != len(ladder):
        _fail(f"{where}.ladder", "contains a repeated glyph")
    raw = node.get("ramps")
    if not isinstance(raw, list) or not raw:
        _fail(f"{where}.ramps", "expected a non-empty list")
    ramps = tuple(
        _ramp_entry(item, identifier, f"{where}.ramps[{at}]") for at, item in enumerate(raw)
    )
    for ramp in ramps:
        _ordered(ramp.ramp, ladder, where)
    return GlyphCategory(identifier, name, ladder, ramps)


def validate_catalogue(data: object) -> Catalogue:
    """Validate one ramps document against the schema and return it as typed objects.

    Raises ValueError naming the offending path. Every ramp must be an ordered subsequence
    of its category ladder, which is the data-level form of the "darkest first" contract.
    """
    root = _mapping(data, "$")
    if root.get("schema") != SCHEMA:
        _fail("$.schema", f"expected {SCHEMA!r}")
    raw = root.get("categories")
    if not isinstance(raw, list):
        _fail("$.categories", "expected a list")
    categories = tuple(
        _category_entry(item, f"$.categories[{at}]") for at, item in enumerate(raw)
    )
    if len(categories) < MIN_CATEGORIES:
        _fail("$.categories", f"expected at least {MIN_CATEGORIES} categories")
    _unique([category.id for category in categories], "$.categories[].id")
    ramps = [ramp for category in categories for ramp in category.ramps]
    _unique([ramp.id for ramp in ramps], "$.categories[].ramps[].id")
    non_latin = sum(1 for ramp in ramps if ramp.script in NON_LATIN_SCRIPTS)
    if non_latin < MIN_NON_LATIN_RAMPS:
        _fail("$.categories[].ramps[].script", f"expected at least {MIN_NON_LATIN_RAMPS} non-Latin ramps")
    return Catalogue(categories)


@cache
def _load(path: str) -> Catalogue:
    """Load and validate the catalogue at path; cached per path."""
    with Path(path).open(encoding="utf-8") as handle:
        return validate_catalogue(json.load(handle))


def load_catalogue(path: Path | str | None = None) -> Catalogue:
    """Return the shipped catalogue, or the one at path, validated on first use."""
    return _load(str(DATA_FILE if path is None else Path(path).expanduser().resolve()))


def render_ramp_preview(
    ramp: str,
    *,
    font: str | None = None,
    cell: tuple[int, int] = PREVIEW_CELL,
    fg: str = DEFAULT_FG,
    bg: str = DEFAULT_BG,
) -> RGB8:
    """Return the ramp drawn left to right in font, darkest glyph first.

    Uses the real ``glyph_ramp`` renderer on a one-row grid, so the preview and a render of
    the same ramp differ only by the gradient behind the glyphs.
    """
    count, (cell_w, cell_h) = len(ramp), (int(cell[0]), int(cell[1]))
    positions = (np.arange(count, dtype=np.float32) + 0.5) / np.float32(count)
    luma = color.srgb_to_linear(positions)[None, :]
    grid = CellGrid(
        cols=count,
        rows=1,
        cell_w=cell_w,
        cell_h=cell_h,
        index=np.zeros((1, count), dtype=np.int32),
        coverage=np.zeros((1, count), dtype=np.float32),
        luma=np.ascontiguousarray(luma, dtype=np.float32),
        samples=np.zeros((1, count, 1), dtype=np.float32),
    )
    style = RenderStyle({"ramp": ramp, "font": font, "fg": fg, "bg": bg, "mode": "mono"})
    image = get_renderer("glyph_ramp").render(grid, _BW, style)
    return color.to_rgb8(np.asarray(image, dtype=np.float32) / 255.0)


def _pixmap(rgb8: RGB8) -> QPixmap:
    """Return a QPixmap copy of a uint8 RGB array."""
    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
    buffer = data.tobytes()
    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


def _item(text: str, data: str) -> QListWidgetItem:
    """Return a list item showing text and carrying data as its user role."""
    item = QListWidgetItem(text)
    item.setData(Qt.ItemDataRole.UserRole, data)
    return item


def _list_widget(parent: QWidget, name: str) -> QListWidget:
    """Return one of the browser's two lists, named for tests and styling."""
    widget = QListWidget(parent)
    widget.setObjectName(name)
    widget.setAlternatingRowColors(True)
    return widget


class GlyphBrowser(QWidget):
    """Category list, set list and a live preview of every ramp in the current font."""

    ramp_chosen = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        catalogue: Catalogue | None = None,
        font: str | None = None,
        cell: tuple[int, int] = PREVIEW_CELL,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("glyph_browser")
        self._catalogue = load_catalogue() if catalogue is None else catalogue
        self._font = font
        self._cell = (int(cell[0]), int(cell[1]))
        self._current: GlyphRamp | None = None
        self._preview: RGB8 | None = None
        self.category_list = _list_widget(self, "glyph_category_list")
        self.category_list.setMaximumWidth(190)
        self.set_list = _list_widget(self, "glyph_set_list")
        self.name_label = QLabel("", self)
        self.name_label.setObjectName("glyph_set_name")
        self.preview_label = QLabel(self)
        self.preview_label.setObjectName("glyph_preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(self._cell[1])
        self.ramp_label = QLabel("", self)
        self.ramp_label.setObjectName("glyph_ramp_text")
        self.ramp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_label = QLabel(HINT_TEXT, self)
        self.hint_label.setObjectName("glyph_hint")
        self.hint_label.setWordWrap(True)
        self._build_layout()
        self._populate()

    def catalogue(self) -> Catalogue:
        """Return the catalogue this browser displays."""
        return self._catalogue

    def current_ramp(self) -> GlyphRamp | None:
        """Return the ramp currently previewed, or None before the first selection."""
        return self._current

    def preview_rgb8(self) -> RGB8 | None:
        """Return the pixels of the current preview, or None before the first selection."""
        return None if self._preview is None else self._preview.copy()

    def select_ramp(self, ramp_id: str) -> None:
        """Show ramp_id, selecting its category and its set, and repaint the preview."""
        self._catalogue.get(ramp_id)  # KeyError naming an unknown id
        for row, category in enumerate(self._catalogue.categories):
            ids = [ramp.id for ramp in category.ramps]
            if ramp_id in ids:
                if self.category_list.currentRow() != row:
                    self.category_list.setCurrentRow(row)
                self.set_list.setCurrentRow(ids.index(ramp_id))
                return

    def set_font(self, font: str | None) -> None:
        """Preview every ramp in font, or in the bundled font when font is None."""
        self._font = font
        if self._current is not None:
            self._show(self._current)

    def _build_layout(self) -> None:
        """Lay out the two lists beside the name, preview and ramp text."""
        lists = QVBoxLayout()
        lists.setSpacing(4)
        lists.addWidget(QLabel("Categories", self))
        lists.addWidget(self.category_list, 1)
        lists.addWidget(QLabel("Sets", self))
        lists.addWidget(self.set_list, 1)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.name_label)
        right.addWidget(self.preview_label)
        right.addWidget(self.ramp_label)
        right.addWidget(self.hint_label)
        right.addStretch(1)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)
        outer.addLayout(lists, 1)
        outer.addLayout(right, 2)

    def _populate(self) -> None:
        """Fill the category list and select the first set of the first category."""
        for category in self._catalogue.categories:
            self.category_list.addItem(_item(category.name, category.id))
        self.category_list.currentRowChanged.connect(self._on_category_changed)
        self.set_list.currentRowChanged.connect(self._on_set_changed)
        if self._catalogue.categories:
            self.category_list.setCurrentRow(0)

    def _on_category_changed(self, row: int) -> None:
        """Refill the set list with the ramps of the selected category."""
        self.set_list.blockSignals(True)
        self.set_list.clear()
        if 0 <= row < len(self._catalogue.categories):
            for ramp in self._catalogue.categories[row].ramps:
                self.set_list.addItem(_item(ramp.name, ramp.id))
        self.set_list.blockSignals(False)
        if self.set_list.count():
            self.set_list.setCurrentRow(0)

    def _on_set_changed(self, row: int) -> None:
        """Preview the newly selected set and announce it."""
        if not 0 <= row < self.set_list.count():
            return
        ramp = self._catalogue.get(str(self.set_list.item(row).data(Qt.ItemDataRole.UserRole)))
        self._show(ramp)
        self.ramp_chosen.emit(ramp.id)

    def _show(self, ramp: GlyphRamp) -> None:
        """Render ramp in the current font and update every label of the preview pane."""
        self._preview = render_ramp_preview(ramp.ramp, font=self._font, cell=self._cell)
        self._current = ramp
        self.preview_label.setPixmap(_pixmap(self._preview))
        self.name_label.setText(ramp.name)
        self.ramp_label.setText(f"{ramp.ramp!r}")


__all__ = [
    "Catalogue",
    "DATA_FILE",
    "GlyphBrowser",
    "GlyphCategory",
    "GlyphRamp",
    "MIN_CATEGORIES",
    "MIN_NON_LATIN_RAMPS",
    "NON_LATIN_SCRIPTS",
    "PREVIEW_CELL",
    "SCHEMA",
    "load_catalogue",
    "render_ramp_preview",
    "validate_catalogue",
]

