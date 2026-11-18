# Reviewer prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are reviewing one task of the Lattice project: a family of free, open-source image-transformation
applications sharing one engine, each running standalone and also plugging into the ArtCraft suite.
You see the task card, the contract sections it must satisfy, the git diff, the gate results and the
coder's notes. You do not see the rest of the repository, and you do not need to.

The dithering application is frozen and shipped (harness 1.1 feature-complete: 18 cards T17-T34,
~1212 test cases at wave-7 close; its human checkpoints H6-H9 are the 1.1 harness's business),
with a public release. Your job is to decide whether this diff can join it.

WHAT TO CHECK, IN THIS ORDER
1. **Contract conformance.** Names, signatures, dtypes, ranges, ordering, error types. A deviation
   from the contract is a blocker even if the tests pass.
2. **Regression.** Does anything that worked before behave differently? Gate G7 (core regression)
   exists for this. A regression is an E6 deviation and a blocker unless the card explicitly asks
   for the change.
3. **The abstraction holds.** Gate G8 checks that every registered `CellRenderer` satisfies §3. Read
   the invariant list and check the diff against each one, not just the gate result. A renderer that
   mutates its input, or whose output size is off by one, is a blocker.
4. **No abstraction leak.** Does `lattice_core` reference an application? Does an application import
   from another application? That is an E8 deviation and a blocker.
5. **No host coupling.** Does the application still work with no ArtCraft running? A missing token
   file, a refused connection or an absent host must be a normal state. That is an E9 deviation and a
   blocker.
6. **Test quality.** Do the tests actually fail on the old code? A test that passes before and after
   the change proves nothing. Look for assertions that restate the implementation, tests that would
   pass with the feature removed, and missing edge cases named in `accept`.
7. **Correctness of the maths.** For renderer and effect cards, check the formulas against the
   contract, not against intuition. Off-by-one in a kernel, a missing normalisation, a wrong colour
   space, a mask applied in the wrong order.
8. **Product quality** (cards L10, L12, L20, L21 only). Is the control discoverable? Does the default
   surprise? Does the message say what to do next? A task can pass every test and still be an E7.
9. **Hygiene.** File length, function length, typing, docstrings, no dead code, no commented-out
   blocks, no debug prints.

SEVERITY
- **blocker**: wrong result, contract violation, regression, crash, data loss, abstraction leak,
  host coupling.
- **major**: missing acceptance item, test that cannot fail, wrong default, misleading message.
- **minor**: style, naming, a docstring that lies.

VERDICT
- `PASS` — no blocker, no major. Minors are listed but do not block.
- `FIX` — at least one blocker or major. The coder gets one more cycle with your findings.
- `ESCALATE` — the task cannot be done as specified, or the fix needs a contract change. Name the
  deviation class (E2, E4, E6, E7, E8, E9).

OUTPUT FORMAT, nothing else:
```json
{
  "verdict": "PASS | FIX | ESCALATE",
  "findings": [
    {"severity": "blocker|major|minor", "file": "...", "line": 0,
     "what": "...", "why": "...", "fix": "..."}
  ],
  "regression": "none | <what changed vs the frozen behaviour>",
  "renderer_invariants": "all six hold | <which one fails and how>",
  "tests_that_cannot_fail": ["..."],
  "notes": "<≤ 5 lines>"
}
```

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

TASK CARD
{{TASK_CARD}}

GATE RESULTS
{{GATE_SUMMARY}}

DIFF
{{DIFF}}

CODER NOTES AND DEVIATIONS
{{CODER_BLOCKS}}

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


CONTRACT EXCERPTS (version 1.1)
## §19 Vector export

New module `dithercraft/export/svg.py`.

```python
def export_svg(rgb8: RGB8, path: Path, *, cell: int = 1, background: str | None = None) -> None
```

- One `<path>` element per distinct colour, `fill` set to the hex code, `shape-rendering="crispEdges"`.
- Cells of the same colour are merged into horizontal runs before being emitted. The file size
  follows the number of runs, not the number of colours: flat artwork produces few runs, a dithered
  render produces about one run per pixel.
- `cell` multiplies the coordinate system (a 1-pixel cell becomes `cell` units), so the SVG scales
  cleanly.
- The document has `width`/`height` in pixels and a `viewBox` in cell units.
- Budget: 2048×2048, 16 colours, **on a dithered render**, under 50 MB and under 5 s. The reference
  content is the worst case, a Floyd-Steinberg render, because that is what the tool produces by
  default and a budget measured on flat artwork would not protect the real output. Measured: 46.45 MB
  in 2.66 s. Flat artwork stays far below (0.49 MB in 0.30 s) and is not the reference.


CONTRACT EXCERPTS (version 1.1)
## §20 Print export

New module `dithercraft/export/print.py`.

```python
def export_print(
    rgb8: RGB8,
    path: Path,
    *,
    dpi: int = 300,
    bleed_mm: float = 0.0,
    crop_marks: bool = False,
    separations: bool = False,
) -> list[Path]
```

- Writes a PNG at `dpi` (metadata only; pixel dimensions unchanged) with an optional bleed border
  filled with the edge colour, and optional crop marks drawn outside the trim area.
- `separations = True` additionally writes one greyscale PNG per ink (`<stem>_C.png`, `_M`, `_Y`,
  `_K`) computed from the CMYK conversion, and returns every path written. The plates cover the trim
  only: the bleed is a replication of the edge and the margin holds marks, so neither carries ink.
  A plate is 255 where its ink is at full strength, so an ink the image does not use is an all-zero
  plate, which reads as black in a greyscale viewer.
- Returns the list of files created, in write order.


CONTRACT EXCERPTS (version 1.1)
## §21 Animation and video

New module `dithercraft/core/animation.py` and `dithercraft/export/video.py`.

```python
def render_sequence(frames: list[Image], spec: PipelineSpec, *, stable: bool = True) -> list[RGB8]
def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None
def export_video(frames: list[RGB8], path: Path, *, fps: int = 12) -> bool
```

- `stable = True` is the temporal-stability mode: ordered matrices are anchored to the canvas (not
  to the frame), the palette is resolved once on the first frame and reused, and the error of frame
  n is not carried into frame n+1 (carrying is explicitly out of scope for 1.1).
- `export_gif` uses Pillow only.
- `export_video` returns `False` and writes nothing when no ffmpeg binary can be found; it never
  raises for a missing ffmpeg. It returns `True` on success.
- The ffmpeg binary comes from the `imageio-ffmpeg` dependency, which ships one inside the wheel, so
  `pip install -r requirements.txt` is enough and no system step is needed. A system ffmpeg is the
  fallback when the dependency is absent. This is the one dependency 1.1 adds; the 1.0 rule "no new
  dependency" is amended here, by human decision, and the PyInstaller bundle ships the binary too.
- No other new dependency. ffmpeg is still invoked as a subprocess, never linked.


CONTRACT EXCERPTS (version 1.1)
## §22 Ergonomics

### §22.1 Algorithm gallery

New module `dithercraft/ui/gallery.py`. A grid of thumbnails, one per registered algorithm,
rendered at 96×96 from a fixed test image (the same synthetic image as `tools/contact_sheet.py`),
with the algorithm name underneath and a search box filtering by name and family. Thumbnails are
cached in `%LOCALAPPDATA%/LatticeDither/thumbs/` keyed by `(algorithm_id, params_hash, palette_hash)`
and regenerated when the key changes.

### §22.2 Undo, shortcuts, drag and drop, recent files

New module `dithercraft/ui/commands.py`: an undo stack over `PipelineSpec` (immutable snapshots,
depth 50). `MainWindow` gains:

- `Ctrl+Z` / `Ctrl+Shift+Z` (and `Ctrl+Y`) for undo/redo.
- Drag and drop of image files onto the window opens the first one.
- A `File > Recent` menu with the last 10 images, persisted in `QSettings`.
- `Ctrl+O`, `Ctrl+S`, `Ctrl+E` (export), `Ctrl+Shift+S` (send to PhotoCraft), `F5` (re-render),
  `Space` (toggle before/after), `Left`/`Right` (previous/next preset, already present).

### §22.3 Localisation

New package `dithercraft/i18n/` with `en.json` and `fr.json`, and:

```python
def tr(key: str, **kwargs) -> str
def set_language(code: str) -> None   # "en" | "fr"
def current_language() -> str
```

- Every user-visible string in `ui/` goes through `tr()`. No literal UI string outside the JSON
  files. Tests assert on `tr()` output, never on a literal.
- The French file uses **tramage** for dithering, **palette** unchanged, **algorithme**,
  **avant/après**, **force**, **densité**.
- Language is chosen from `QSettings`, defaulting to the system locale, falling back to `en`.

REVUE-PRODUIT (extrait — bloquants 1-2 visés par la carte)
- **Désormais 3 bloquants** (les deux premiers sont des défauts de résultat
  silencieux, confirmés par le code ; le troisième est venu des captures) :
  1) export avancé (SVG/impression/GIF/vidéo) sur l'aperçu plafonné à 1024 px
  au lieu d'un rendu pleine résolution — nuance visuelle : la barre n'expose
  que « Exporter en PNG » (le bon chemin) ; 2) « GIF animé »/« Vidéo »
  produisent un fichier d'une seule image dans la GUI ; 3) l'indicateur
  « Préréglage 1/12 : 01_gameboy.json » **ment dans les cinq états** (affiché
  sans image, sur un rendu Floyd-Steinberg N&B, et figé après changement
  d'algorithme et de palette) — c'est le piège le plus visible pour H12.
- **Aggravations visuelles** : la galerie occupe ~500 px de large (pas 240) —
  le canevas n'a que ~35 % de la fenêtre, vide au démarrage ; la barre
  d'outils déborde à 1280 px (« Préparer la source » et « Retirer la trame »
  hors champ : piège pour le scan) ; la galerie est figée (vignettes
  identiques, jamais sur l'image/palette courante, aucun surlignage de
  l'algorithme actif) ; le bouton « Ajouter ▾ » des effets est placé sous la
  liste « Après tramage » alors qu'il vise « Avant » — l'écran contredit le
  comportement ; les boutons PhotoCraft restent actifs malgré
  « PhotoCraft : déconnecté » ; zone « Couleurs » vide pour une palette EGA
  de 16 couleurs.

TASK CARD
### L-UI2 · Recâblage de Lattice Dither sur `lattice_core/ui` (doublons supprimés)
- wave: 2 · deps: L-UI, L11 · executor: OMH deep-work · review: strict · size: L
- owns: `lattice_dither/ui/**`, `tests/test_ui_*.py`, `lattice_core/ui/**`
- context: §2 (`ui/`), 1.1 §19-§22 (fenêtre, export, raccourcis), REVUE-PRODUIT (bloquants 1-2)
- motivation (décision humaine du 2026-11-18) : `lattice_dither/ui/` fait 4026 lignes et n'importe
  AUCUN widget de `lattice_core/ui`. Le canvas a été dupliqué à l'identique lors de L-UI, mais le
  worker et le dialogue d'export ont divergé : le core n'a ni `request_send`/`request_get`/
  `check_version` (pont PhotoCraft interactif), ni `PaletteExtraction` (extraction de palette sur
  thread), ni les pages d'export impression/GIF/vidéo. Tant que Dither garde sa copie, la suite
  n'a pas UNE ui partagée mais deux, et chaque correctif doit être fait deux fois — c'est
  exactement le défaut structurel S5 relevé par la revue produit.
- spec: recâbler Dither sur les widgets du core sans changer un pixel de rendu ni un raccourci.
  1. Ce qui manque au core d'abord : généraliser `RenderWorker` pour couvrir les verbes pont
     (`request_send`, `request_get`, `check_version`) et extraire `PaletteExtraction` dans
     `lattice_core/ui/worker.py` — le bridge du core (`lattice_core/ui/bridge.py`) porte déjà le
     `ConnectionProbe`, ne pas le redupliquer.
  2. Le dialogue d'export du core doit couvrir les quatre formats de Dither (PNG, SVG, impression,
     GIF/vidéo séquence) ; les pages spécifiques restent dans l'app SEULEMENT si elles dépendent
     d'un format que le core n'a pas à connaître.
  3. Ensuite seulement : `lattice_dither/ui/` réimporte les widgets du core ; les fichiers devenus
     vides sont SUPPRIMÉS (pas de coquilles de ré-export qui laisseraient deux chemins d'import).
  4. Aucune régression de comportement : G6 (parité CLI/GUI de Dither) et G7 (témoins bit-à-bit)
     doivent rester verts, et la batterie 1.1 de Dither (raccourcis §22.2, undo, récents, drag & drop)
     doit passer sans qu'un seul test soit modifié — sauf import.
- accept:
  - `lattice_dither/ui/` n'importe plus aucun widget propre : `PreviewCanvas`, `RenderWorker`,
    `PaletteExtraction`, `ExportDialog`, `LookGallery` et `PresetIndicator` viennent du core.
  - pas un seul fichier de `lattice_dither/ui/` ne duplique un widget existant dans
    `lattice_core/ui/` (vérifié par un test qui compare les `__all__` et les noms de classes).
  - les 11 fichiers `tests/test_ui_*.py` passent ; `tests/test_ui_shared.py` reste vert ; le compte
    total de tests ne baisse pas.
  - G6 et G7 verts : un même preset rend des octets identiques en CLI et GUI, et les trois témoins
    sont bit-à-bit.
  - le worker du core expose `request_send`, `request_get`, `check_version` et `PaletteExtraction`,
    couverts par des tests, et `lattice_core` n'importe toujours aucune application (E8).
  - `lattice_core/ui` s'installe et s'importe sans Dither : `pip install -e .[ui]` seul suffit.


GATE RESULTS
GATES (orchestrateur, rejoués après l'attempt 2) :
- G2 pytest : 285 passed (tests/test_ui_*.py) (orchestrateur).
- G3 ruff (owns) : All checks passed.
- G1 : lattice_dither/ui/export_dialog.py SUPPRIMÉ (vérifié) ; commands.py recâblé sur le dialogue core ; test Ctrl+E adapté (E1 DEV-221, pas de contournement).
- E2E : Ctrl+E → SVG 1400×900 (> plafond preview 1024) — le bloquant REVUE n°1 est livré.
RE-REVUE PASS 1 (verdict FIX) — VÉRIFIE finding par finding que le correctif du retry est réel ; le codeur
affirme avoir appliqué dans l'ordre du JSON. Juge le diff CUMULATIF (HEAD -> arbre), pas la prose :
- [BLOCKER] lattice_dither/ui/export_dialog.py:69 — Généraliser lattice_core/ui/export_dialog.py : 4 formats (PNG, SVG, impression, GIF/vidéo séquence) avec frames, writers génériques côté core (Pillow only), writer vidéo et tr() injectables 
- [MAJOR] tests/test_ui_no_duplicates.py:39 — Dialogue déplacé dans le core : retirer DECLARED_APP_EXPORT, ajouter ExportDialog (+ ExportError) à SHARED_WIDGETS.
- [MINOR] lattice_core/ui/worker.py:103 — Assumer et documenter la normalisation app-agnostique, ou paramétrer le nom d'application.
- [MINOR] lattice_core/ui/worker.py:46 — Injecter le libellé du raccourci au constructeur, comme layer_name ; défaut app-agnostique.

DIFF (cumulatif HEAD -> arbre)
diff --git a/lattice_core/ui/__init__.py b/lattice_core/ui/__init__.py
index 8fc76bc..906f910 100644
--- a/lattice_core/ui/__init__.py
+++ b/lattice_core/ui/__init__.py
@@ -19,6 +19,7 @@ from lattice_core.ui.worker import (
     MAX_SOURCE_SIDE,
     PREVIEW_MAX_SIDE,
     PREVIEW_STAGES,
+    PaletteExtraction,
     PreviewResult,
     RenderResult,
     RenderWorker,
@@ -41,6 +42,7 @@ __all__ = [
     "Mode",
     "PREVIEW_MAX_SIDE",
     "PREVIEW_STAGES",
+    "PaletteExtraction",
     "PresetIndicator",
     "PreviewCanvas",
     "PreviewResult",
diff --git a/lattice_core/ui/export_dialog.py b/lattice_core/ui/export_dialog.py
index 0556682..f8a2ea4 100644
--- a/lattice_core/ui/export_dialog.py
+++ b/lattice_core/ui/export_dialog.py
@@ -1,24 +1,28 @@
-"""Shared full-resolution export dialog (PNG/SVG/GIF).
+"""Shared full-resolution export dialog: PNG, SVG, print and GIF/video sequence.
 
 The Dither product review blocker was that the advanced export ran on the
 1024 px preview proxy. This dialog fixes that contract: it owns the render. It
 is handed the source image and the pipeline spec, renders the pipeline at FULL
-resolution (no ``max_side``) on export, and only then writes the file, so the
-file always matches the pipeline output size. The render callable can be
-injected for worker-thread rendering in an application shell.
+resolution (no ``max_side``) on export, and only then writes the file. The
+render callable, the frame sequence, the video writer (ffmpeg lives outside
+core) and ``tr`` are injectable, so every application reuses this one dialog
+and core never imports an application.
 """
 
 from __future__ import annotations
 
 from collections.abc import Callable
 from pathlib import Path
+from typing import Protocol
 
 import numpy as np
 from PySide6.QtCore import QSettings
 from PySide6.QtWidgets import (
+    QCheckBox,
     QComboBox,
     QDialog,
     QDialogButtonBox,
+    QDoubleSpinBox,
     QFileDialog,
     QFormLayout,
     QHBoxLayout,
@@ -26,6 +30,7 @@ from PySide6.QtWidgets import (
     QLineEdit,
     QPushButton,
     QSpinBox,
+    QStackedWidget,
     QVBoxLayout,
     QWidget,
 )
@@ -33,30 +38,69 @@ from PySide6.QtWidgets import (
 from lattice_core import color
 from lattice_core.pipeline import PipelineSpec, render
 from lattice_core.types import RGB8, Image
+from lattice_core.ui.export_writers import write_gif, write_print
 from lattice_core.ui.svg import write_svg
 
 EXPORT_DIR_KEY = "export_dir"
 REPORT_SEPARATOR = "\n"
-FORMATS: tuple[str, ...] = ("png", "svg", "gif")
-FORMAT_LABELS = {"png": "PNG", "svg": "SVG", "gif": "GIF"}
-FORMAT_SUFFIX = {"png": ".png", "svg": ".svg", "gif": ".gif"}
+FORMATS: tuple[str, ...] = ("png", "svg", "print", "gif", "video")
+ANIMATED_FORMATS: tuple[str, ...] = ("gif", "video")
+FORMAT_LABELS = {
+    "png": "PNG",
+    "svg": "SVG",
+    "print": "Print PNG",
+    "gif": "Animated GIF",
+    "video": "Video",
+}
+FORMAT_SUFFIX = {"png": ".png", "svg": ".svg", "print": ".png", "gif": ".gif", "video": ".mp4"}
 FORMAT_FILTER = {
     "png": "PNG images (*.png);;All files (*)",
     "svg": "SVG images (*.svg);;All files (*)",
-    "gif": "GIF images (*.gif);;All files (*)",
+    "print": "PNG images (*.png);;All files (*)",
+    "gif": "Animated GIF (*.gif);;All files (*)",
+    "video": "Video (*.mp4 *.mkv *.webm);;All files (*)",
 }
 DEFAULT_CELL = 1
-MAX_CELL = 64
+DEFAULT_DPI = 300
+DEFAULT_BLEED_MM = 0.0
+DEFAULT_FPS = 12
+DEFAULT_LOOP = 0
 DEFAULT_PATH_NAME = "export"
+MAX_CELL = 64
+MAX_DPI = 1200
+MAX_BLEED_MM = 50.0
+MAX_FPS = 60
+MAX_LOOP = 100
 RENDER = Callable[[PipelineSpec], RGB8]
 
 
+class VideoWriter(Protocol):
+    """Writes a frame sequence through an external encoder, like the app's export_video."""
+
+    def __call__(self, frames: list[RGB8], path: Path, *, fps: int = 12) -> bool:
+        """Write frames to path at fps; return False, never raise, when unavailable."""
+        ...
+
+
+class Translate(Protocol):
+    """Translates one UI key and formats it with kwargs, like an application's tr."""
+
+    def __call__(self, key: str, **kwargs: object) -> str:
+        """Return the translated, formatted text of key."""
+        ...
+
+
+def _default_tr(key: str, **kwargs: object) -> str:
+    """Return key formatted with kwargs: the app-agnostic fallback translation."""
+    return key.format(**kwargs)
+
+
 class ExportError(Exception):
     """An export that could not be written: no output path, or a render failure."""
 
 
 class ExportDialog(QDialog):
-    """Dialog that renders the pipeline at full resolution and writes it as PNG, SVG or GIF."""
+    """Dialog rendering the pipeline at full resolution as PNG, SVG, print, GIF or video."""
 
     def __init__(
         self,
@@ -66,12 +110,19 @@ class ExportDialog(QDialog):
         *,
         render_full: RENDER | None = None,
         settings: QSettings | None = None,
+        frames: list[RGB8] | None = None,
+        video_writer: VideoWriter | None = None,
+        tr: Translate | None = None,
     ) -> None:
+        """Build the dialog; frames, the video writer and tr are injected by the app."""
         super().__init__(parent)
-        self.setWindowTitle("Export")
+        self._tr = tr if tr is not None else _default_tr
+        self.setWindowTitle(self._tr("Export"))
         self.source = np.ascontiguousarray(source, dtype=np.float32)
         self.spec = spec
+        self.frames = list(frames) if frames else []
         self._render_full = render_full if render_full is not None else self._default_render
+        self._video_writer = video_writer
         self.written: list[Path] = []
         self._settings = settings or QSettings()
         self._build()
@@ -82,12 +133,17 @@ class ExportDialog(QDialog):
         self.format_box = QComboBox(self)
         self.format_box.setObjectName("export_format")
         for key in FORMATS:
-            self.format_box.addItem(FORMAT_LABELS[key], key)
-        self.stack = QWidget(self)
-        self._build_svg_page(self.stack)
+            self.format_box.addItem(self._tr(FORMAT_LABELS[key]), key)
+        self.stack = QStackedWidget(self)
+        self.stack.setObjectName("export_options")
+        self.stack.addWidget(QWidget(self.stack))  # the PNG page carries no option
+        self._build_svg_page()
+        self._build_print_page()
+        self._build_gif_page()
+        self._build_video_page()
         self.path_edit = QLineEdit(self)
         self.path_edit.setObjectName("export_path")
-        browse = QPushButton("Browse…", self)
+        browse = QPushButton(self._tr("Browse…"), self)
         browse.setObjectName("export_browse")
         browse.clicked.connect(self._on_browse)
         row = QHBoxLayout()
@@ -99,8 +155,8 @@ class ExportDialog(QDialog):
         self.buttons = QDialogButtonBox(
             QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close, self
         )
-        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Export")
-        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Close")
+        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(self._tr("Export"))
+        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(self._tr("Close"))
         self.buttons.accepted.connect(self._on_export)
         self.buttons.rejected.connect(self.reject)
         layout = QVBoxLayout(self)
@@ -109,22 +165,76 @@ class ExportDialog(QDialog):
         layout.addLayout(row)
         layout.addWidget(self.report)
         layout.addWidget(self.buttons)
+        self.format_box.currentIndexChanged.connect(self._on_format_changed)
 
-    def _build_svg_page(self, page: QWidget) -> None:
+    def _build_svg_page(self) -> None:
         """Create the SVG page: cell size and background colour."""
+        page = QWidget(self.stack)
         self.cell = QSpinBox(page)
         self.cell.setObjectName("export_cell")
         self.cell.setRange(1, MAX_CELL)
         self.cell.setValue(DEFAULT_CELL)
         self.background_edit = QLineEdit(page)
         self.background_edit.setObjectName("export_background")
-        self.background_edit.setPlaceholderText("#RRGGBB, empty for transparent")
+        self.background_edit.setPlaceholderText(self._tr("#RRGGBB, empty for transparent"))
         form = QFormLayout(page)
-        form.addRow("Cell size", self.cell)
-        form.addRow("Background", self.background_edit)
+        form.addRow(self._tr("Cell size"), self.cell)
+        form.addRow(self._tr("Background"), self.background_edit)
+        self.stack.addWidget(page)
+
+    def _build_print_page(self) -> None:
+        """Create the print page: resolution, bleed, crop marks and separations."""
+        page = QWidget(self.stack)
+        self.dpi = QSpinBox(page)
+        self.dpi.setObjectName("export_dpi")
+        self.dpi.setRange(1, MAX_DPI)
+        self.dpi.setValue(DEFAULT_DPI)
+        self.bleed = QDoubleSpinBox(page)
+        self.bleed.setObjectName("export_bleed")
+        self.bleed.setRange(0.0, MAX_BLEED_MM)
+        self.bleed.setDecimals(1)
+        self.bleed.setValue(DEFAULT_BLEED_MM)
+        self.crop_marks = QCheckBox(self._tr("Crop marks"), page)
+        self.crop_marks.setObjectName("export_crop_marks")
+        self.separations = QCheckBox(self._tr("Separations"), page)
+        self.separations.setObjectName("export_separations")
+        form = QFormLayout(page)
+        form.addRow(self._tr("Resolution"), self.dpi)
+        form.addRow(self._tr("Bleed (mm)"), self.bleed)
+        form.addRow(self.crop_marks)
+        form.addRow(self.separations)
+        self.stack.addWidget(page)
+
+    def _build_gif_page(self) -> None:
+        """Create the GIF page: frame rate and loop count."""
+        page = QWidget(self.stack)
+        self.gif_fps = QSpinBox(page)
+        self.gif_fps.setObjectName("export_gif_fps")
+        self.gif_fps.setRange(1, MAX_FPS)
+        self.gif_fps.setValue(DEFAULT_FPS)
+        self.gif_loop = QSpinBox(page)
+        self.gif_loop.setObjectName("export_gif_loop")
+        self.gif_loop.setRange(0, MAX_LOOP)
+        self.gif_loop.setValue(DEFAULT_LOOP)
+        self.gif_loop.setSpecialValueText(self._tr("forever"))
+        form = QFormLayout(page)
+        form.addRow(self._tr("Frame rate"), self.gif_fps)
+        form.addRow(self._tr("Loop"), self.gif_loop)
+        self.stack.addWidget(page)
+
+    def _build_video_page(self) -> None:
+        """Create the video page: frame rate."""
+        page = QWidget(self.stack)
+        self.video_fps = QSpinBox(page)
+        self.video_fps.setObjectName("export_video_fps")
+        self.video_fps.setRange(1, MAX_FPS)
+        self.video_fps.setValue(DEFAULT_FPS)
+        form = QFormLayout(page)
+        form.addRow(self._tr("Frame rate"), self.video_fps)
+        self.stack.addWidget(page)
 
     def format(self) -> str:
-        """Return the selected format key: png, svg or gif."""
+        """Return the selected format key: png, svg, print, gif or video."""
         return str(self.format_box.currentData())
 
     def export_directory(self) -> Path:
@@ -136,7 +246,7 @@ class ExportDialog(QDialog):
         """Return the output path typed in the dialog, with the format's suffix."""
         text = self.path_edit.text().strip()
         if not text:
-            raise ExportError("Choose an output file first.")
+            raise ExportError(self._tr("Choose an output file first."))
         path = Path(text)
         return path if path.suffix else path.with_suffix(FORMAT_SUFFIX[self.format()])
 
@@ -152,21 +262,53 @@ class ExportDialog(QDialog):
         """Render at full resolution, write the file and return the paths written."""
         target = self.target_path()
         target.parent.mkdir(parents=True, exist_ok=True)
-        self.report.setText("Rendering at full resolution…")
-        image = self._render_full(self.spec)
-        written = self._write(image, target)
+        frames = self._frames_for_export()
+        written = self._write(frames, target)
         self.written = written
         self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
-        self.report.setText(REPORT_SEPARATOR.join(f"Exported {path.name}" for path in written))
+        lines = [self._tr("Exported {name}", name=path.name) for path in written]
+        self.report.setText(REPORT_SEPARATOR.join(lines))
         return written
 
-    def _write(self, image: RGB8, target: Path) -> list[Path]:
+    def _frames_for_export(self) -> list[RGB8]:
+        """Return the injected sequence for animated formats, else one full render."""
+        if self.frames and self.format() in ANIMATED_FORMATS:
+            return self.frames
+        self.report.setText(self._tr("Rendering at full resolution…"))
+        return [self._render_full(self.spec)]
+
+    def _write(self, frames: list[RGB8], target: Path) -> list[Path]:
         """Write the selected format to target and return every file created."""
         kind = self.format()
+        image = frames[0]
         if kind == "svg":
             write_svg(image, target, cell=self.cell.value(), background=self.background())
+        elif kind == "print":
+            return write_print(
+                image,
+                target,
+                dpi=self.dpi.value(),
+                bleed_mm=self.bleed.value(),
+                crop_marks=self.crop_marks.isChecked(),
+                separations=self.separations.isChecked(),
+            )
+        elif kind == "gif":
+            write_gif(frames, target, fps=self.gif_fps.value(), loop=self.gif_loop.value())
+        elif kind == "video":
+            return self._write_video(frames, target)
         else:
-            color.to_pil(image).save(target, format="PNG" if kind == "png" else "GIF")
+            color.to_pil(image).save(target, format="PNG")
+        return [target]
+
+    def _write_video(self, frames: list[RGB8], target: Path) -> list[Path]:
+        """Write through the injected video writer; a missing encoder is an error."""
+        if self._video_writer is None:
+            raise ExportError(self._tr("No video writer available."))
+        if not self._video_writer(frames, target, fps=self.video_fps.value()):
+            reason = self._tr("No ffmpeg available.")
+            raise ExportError(
+                self._tr("Cannot write {path}: {error}", path=target.name, error=reason)
+            )
         return [target]
 
     def _on_export(self) -> None:
@@ -176,11 +318,17 @@ class ExportDialog(QDialog):
         except (ExportError, OSError, ValueError) as exc:
             self.report.setText(str(exc))
 
+    def _on_format_changed(self, index: int) -> None:
+        """Show the options of the selected format and retarget the path suffix."""
+        self.stack.setCurrentIndex(index)
+        text = self.path_edit.text().strip() or DEFAULT_PATH_NAME
+        self.path_edit.setText(str(Path(text).with_suffix(FORMAT_SUFFIX[self.format()])))
+
     def _on_browse(self) -> None:
         """Ask for an output path with the selected format's filter."""
         current = self.path_edit.text().strip() or str(self.export_directory())
         path, _ = QFileDialog.getSaveFileName(
-            self, "Export", current, FORMAT_FILTER[self.format()]
+            self, self._tr("Export"), current, self._tr(FORMAT_FILTER[self.format()])
         )
         if path:
             self.path_edit.setText(path)
@@ -197,9 +345,22 @@ def run_export_dialog(
     parent: QWidget | None = None,
     *,
     render_full: RENDER | None = None,
+    settings: QSettings | None = None,
+    frames: list[RGB8] | None = None,
+    video_writer: VideoWriter | None = None,
+    tr: Translate | None = None,
 ) -> list[Path]:
     """Show the export dialog for source and spec and return every file written."""
-    dialog = ExportDialog(source, spec, parent, render_full=render_full)
+    dialog = ExportDialog(
+        source,
+        spec,
+        parent,
+        render_full=render_full,
+        settings=settings,
+        frames=frames,
+        video_writer=video_writer,
+        tr=tr,
+    )
     dialog.exec()
     return dialog.written
 
diff --git a/lattice_core/ui/export_writers.py b/lattice_core/ui/export_writers.py
new file mode 100644
index 0000000..3dca082
--- /dev/null
+++ b/lattice_core/ui/export_writers.py
@@ -0,0 +1,136 @@
+"""Generic export writers for the shared dialog: print PNG and animated GIF.
+
+Pillow and numpy only, no application import and no external binary: the video
+writer stays injectable because ffmpeg lives outside core (CONTRACT §20, §21).
+The print layout is the contract one: the trim, an edge-replicated bleed and a
+transparent margin holding the crop marks; separations are CMYK plates at full
+black pullout, written as single-channel PNGs where 255 means full ink.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core.effects.halftone import plates
+from lattice_core.types import RGB8
+
+MM_PER_INCH = 25.4
+MARK_MM = 3.0
+MARK_THICKNESS_MM = 0.25
+SEPARATION_PULLOUT = 1.0
+INKS = ("C", "M", "Y", "K")
+
+
+def _mm_to_px(mm: float, dpi: int) -> int:
+    """Convert a length in millimetres to whole pixels at dpi."""
+    return int(round(mm / MM_PER_INCH * dpi))
+
+
+def _mark(canvas: np.ndarray, top: int, left: int, height: int, width: int) -> None:
+    """Paint one black crop mark onto the RGBA canvas."""
+    canvas[top : top + height, left : left + width] = (0, 0, 0, 255)
+
+
+def _draw_marks(canvas: np.ndarray, margin: int, bleed: int, dpi: int) -> None:
+    """Draw the eight crop marks in the margin, aligned with the trim edges."""
+    height, width = canvas.shape[:2]
+    thick = max(1, _mm_to_px(MARK_THICKNESS_MM, dpi))
+    top, left = margin + bleed, margin + bleed
+    bottom, right = height - margin - bleed, width - margin - bleed
+    for y in (top, bottom):
+        _mark(canvas, y, 0, thick, margin)
+        _mark(canvas, y, width - margin, thick, margin)
+    for x in (left, right):
+        _mark(canvas, 0, x, margin, thick)
+        _mark(canvas, height - margin, x, margin, thick)
+
+
+def _canvas(array: np.ndarray, bleed: int, margin: int, dpi: int) -> np.ndarray:
+    """Return the printable canvas: trim, then bleed, then the transparent margin."""
+    work = array
+    if bleed:
+        work = np.pad(work, ((bleed, bleed), (bleed, bleed), (0, 0)), mode="edge")
+    if not margin:
+        return work
+    height, width = work.shape[:2]
+    canvas = np.zeros((height + 2 * margin, width + 2 * margin, 4), dtype=np.uint8)
+    canvas[margin : margin + height, margin : margin + width, :3] = work
+    canvas[margin : margin + height, margin : margin + width, 3] = 255
+    _draw_marks(canvas, margin, bleed, dpi)
+    return canvas
+
+
+def _save(canvas: np.ndarray, path: Path, dpi: int) -> None:
+    """Write the canvas as a PNG carrying dpi in its metadata."""
+    mode = "RGBA" if canvas.shape[2] == 4 else "RGB"
+    PILImage.fromarray(canvas, mode=mode).save(path, format="PNG", dpi=(dpi, dpi))
+
+
+def _save_plate(plate: np.ndarray, path: Path, dpi: int) -> None:
+    """Write one ink plate as a single-channel PNG where 255 is full ink."""
+    data = np.clip(np.asarray(plate, dtype=np.float32) * 255.0, 0.0, 255.0).astype(np.uint8)
+    PILImage.fromarray(data, mode="L").save(path, format="PNG", dpi=(dpi, dpi))
+
+
+def write_print(
+    rgb8: RGB8,
+    path: Path,
+    *,
+    dpi: int = 300,
+    bleed_mm: float = 0.0,
+    crop_marks: bool = False,
+    separations: bool = False,
+) -> list[Path]:
+    """Write rgb8 as a print-ready PNG and return every file created, in write order."""
+    array = np.asarray(rgb8)
+    if array.ndim != 3 or array.shape[2] != 3:
+        raise ValueError(f"expected an (H, W, 3) image, got shape {array.shape}")
+    if int(dpi) < 1:
+        raise ValueError(f"dpi must be >= 1, got {dpi}")
+    if float(bleed_mm) < 0.0:
+        raise ValueError(f"bleed_mm must be >= 0, got {bleed_mm}")
+    if array.shape[0] == 0 or array.shape[1] == 0:
+        raise ValueError("cannot export an empty image")
+    target = Path(path)
+    bleed = _mm_to_px(float(bleed_mm), int(dpi))
+    margin = _mm_to_px(MARK_MM, int(dpi)) if crop_marks else 0
+    canvas = _canvas(array, bleed, margin, int(dpi))
+    _save(canvas, target, int(dpi))
+    written = [target]
+    if separations:
+        work = np.ascontiguousarray(array, dtype=np.float32) / 255.0
+        for ink, plate in zip(INKS, plates(work, SEPARATION_PULLOUT), strict=True):
+            plate_path = target.with_name(f"{target.stem}_{ink}.png")
+            _save_plate(plate, plate_path, int(dpi))
+            written.append(plate_path)
+    return written
+
+
+def _check_sequence(frames: list[RGB8], fps: int) -> int:
+    """Validate the sequence and return the frame duration in milliseconds."""
+    if not frames:
+        raise ValueError("cannot export an empty sequence")
+    if int(fps) < 1:
+        raise ValueError(f"fps must be >= 1, got {fps}")
+    return int(round(1000.0 / int(fps)))
+
+
+def write_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
+    """Write frames to path as an animated GIF, using Pillow only."""
+    duration = _check_sequence(frames, fps)
+    images = [PILImage.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB") for frame in frames]
+    images[0].save(
+        Path(path),
+        format="GIF",
+        save_all=True,
+        append_images=images[1:],
+        duration=duration,
+        loop=int(loop),
+        optimize=False,
+    )
+
+
+__all__ = ["write_gif", "write_print"]
diff --git a/lattice_core/ui/worker.py b/lattice_core/ui/worker.py
index e545948..fb8031b 100644
--- a/lattice_core/ui/worker.py
+++ b/lattice_core/ui/worker.py
@@ -1,10 +1,12 @@
-"""Shared render worker: progressive previews and full-resolution renders.
+"""Shared render worker: progressive previews, full-resolution renders and bridge calls.
 
 Previews are rendered from cached proxies, coarse first (``PREVIEW_STAGES``), so
 a large source never reaches the pipeline at full resolution. The full render
-happens only on export. Sources above ``MAX_SOURCE_SIDE`` are refused instead of
-exhausting memory. The worker is app-agnostic: it renders pipeline specs and
-emits signals; it never talks to a host.
+happens only on export or send. Sources above ``MAX_SOURCE_SIDE`` are refused
+instead of exhausting memory. With ``bridge=True`` the worker also talks to
+PhotoCraft (send/get/version) and probes the connection on a timer; the default
+worker renders only, so an application that does not use the bridge is
+unaffected. The worker never touches a widget and never imports an application.
 """
 
 from __future__ import annotations
@@ -14,11 +16,21 @@ import time
 from dataclasses import dataclass
 
 import numpy as np
-from PySide6.QtCore import QObject, QTimer, Signal, Slot
+from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
 
 from lattice_core import color
+from lattice_core.bridge import DEFAULT_LAYER_NAME
+from lattice_core.bridge.photocraft import (
+    BridgeError,
+    PhotoCraftClient,
+    installed_photocraft_version,
+    version_status,
+)
+from lattice_core.palettes.extract import extract_palette
+from lattice_core.palettes.io import hex_list
 from lattice_core.pipeline import PipelineSpec, render
 from lattice_core.types import RGB8, Image
+from lattice_core.ui.bridge import ConnectionProbe
 
 LOGGER = logging.getLogger(__name__)
 
@@ -27,6 +39,12 @@ PREVIEW_STAGES: tuple[int, ...] = (256, 1024)
 PREVIEW_MAX_SIDE = PREVIEW_STAGES[-1]
 MAX_SOURCE_SIDE = 8000
 PROXY_STRIP_ROWS = 256
+CONNECTION_INTERVAL_MS = 3000
+LAYER_NAME = DEFAULT_LAYER_NAME
+UNTESTED = "untested"
+UNKNOWN = "unknown"
+NO_CLIENT_MESSAGE = "PhotoCraft is not reachable. Start it from the {shortcut} shortcut."
+SHORTCUT_NAME = "PhotoCraft"
 
 
 @dataclass(frozen=True)
@@ -73,7 +91,10 @@ def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
 
 
 def oversize_message(shape: tuple[int, ...]) -> str | None:
-    """Return the refusal message for a source of this (height, width), or None."""
+    """Return the refusal message for a source of this (height, width), or None.
+
+    Wording is app-agnostic by design (L-UI2): the shared worker names no app.
+    """
     if len(shape) < 2:
         return None
     height, width = int(shape[0]), int(shape[1])
@@ -85,30 +106,94 @@ def oversize_message(shape: tuple[int, ...]) -> str | None:
     )
 
 
+class PaletteExtraction(QObject):
+    """Runs one palette extraction on a helper thread and reports it by signal."""
+
+    finished = Signal(object)
+    failed = Signal(str)
+
+    def __init__(self, image: Image, k: int, method: str) -> None:
+        super().__init__()
+        self._args = (image, k, method)
+        self._thread = QThread()
+        self.moveToThread(self._thread)
+        self._thread.started.connect(self.run)
+        self.finished.connect(self._thread.quit)
+        self.failed.connect(self._thread.quit)
+        self._thread.finished.connect(self.deleteLater)
+        _ACTIVE_EXTRACTIONS.add(self)
+        self._thread.finished.connect(lambda: _ACTIVE_EXTRACTIONS.discard(self))
+
+    def start(self) -> None:
+        """Start the helper thread; this object stays alive until it finishes."""
+        self._thread.start()
+
+    @Slot()
+    def run(self) -> None:
+        """Emit the extracted colours, or the error message."""
+        try:
+            self.finished.emit(hex_list(extract_palette(*self._args)))
+        except ValueError as exc:
+            self.failed.emit(str(exc))
+
+
+_ACTIVE_EXTRACTIONS: set[PaletteExtraction] = set()
+
+
 class RenderWorker(QObject):
-    """Renders debounced, staged previews and full-resolution exports of one source."""
+    """Renders previews and full-resolution images; with bridge=True talks to PhotoCraft."""
 
     preview_ready = Signal(object)
     export_ready = Signal(object)
+    image_ready = Signal(object)
+    send_finished = Signal(int)
     failed = Signal(str)
     progress = Signal(str)
-
-    def __init__(self, parent: QObject | None = None) -> None:
+    connection_state = Signal(str)
+    version_status_ready = Signal(str, object)
+
+    def __init__(
+        self,
+        parent: QObject | None = None,
+        *,
+        bridge: bool = False,
+        layer_name: str = LAYER_NAME,
+        shortcut_name: str = SHORTCUT_NAME,
+    ) -> None:
         super().__init__(parent)
+        self._bridge = bridge
+        self._layer_name = layer_name
+        self._no_client_message = NO_CLIENT_MESSAGE.format(shortcut=shortcut_name)
+        self.probe: ConnectionProbe | None = ConnectionProbe(parent=self) if bridge else None
+        if self.probe is not None:
+            self.probe.state_changed.connect(self.connection_state)
         self._source: Image | None = None
         self._proxies: dict[int, tuple[Image, RGB8]] = {}
         self._spec: PipelineSpec | None = None
         self._job = 0
         self._pending_job = 0
         self._debounce: QTimer | None = None
+        self._connection: QTimer | None = None
 
     @Slot()
     def start(self) -> None:
-        """Create the debounce timer inside whatever thread owns this worker."""
+        """Create the timers inside the worker thread; with bridge=True run startup checks."""
         self._debounce = QTimer(self)
         self._debounce.setSingleShot(True)
         self._debounce.setInterval(DEBOUNCE_MS)
         self._debounce.timeout.connect(self._render_preview)
+        if self._bridge:
+            self._connection = QTimer(self)
+            self._connection.setInterval(CONNECTION_INTERVAL_MS)
+            self._connection.timeout.connect(self.check_connection)
+            self._connection.start()
+            self.check_connection()
+            self.check_version()
+
+    def stop_probing(self) -> None:
+        """Stop the connection probe; called from the GUI thread before shutdown."""
+        if self.probe is not None:
+            self.probe.stop()
 
     @Slot(object)
     def set_source(self, image: Image | None) -> None:
@@ -141,6 +226,57 @@ class RenderWorker(QObject):
         if result is not None:
             self.export_ready.emit(result)
 
+    @Slot(object)
+    def request_send(self, spec: PipelineSpec) -> None:
+        """Render spec at full resolution and place it as a new PhotoCraft layer."""
+        self.progress.emit("Rendering for PhotoCraft…")
+        result = self._render_full(spec)
+        if result is None:
+            return
+        client = self._client()
+        if client is None:
+            return
+        self.progress.emit("Sending the render to PhotoCraft…")
+        try:
+            layer = client.place_as_layer(color.to_pil(result.image), self._layer_name)
+        except BridgeError as exc:
+            self.failed.emit(f"Cannot send the render to PhotoCraft: {exc}")
+            return
+        self.send_finished.emit(int(layer))
+
+    @Slot()
+    def request_get(self) -> None:
+        """Fetch the visible PhotoCraft document and emit it as a float32 image."""
+        client = self._client()
+        if client is None:
+            return
+        self.progress.emit("Fetching the image from PhotoCraft…")
+        try:
+            image = client.render_document()
+        except BridgeError as exc:
+            self.failed.emit(f"Cannot get the image from PhotoCraft: {exc}")
+            return
+        self.image_ready.emit(color.to_float(image))
+
+    @Slot()
+    def check_connection(self) -> None:
+        """Refresh the PhotoCraft connection state with one discover() call."""
+        if self.probe is not None:
+            self.probe.check()
+
+    @Slot()
+    def check_version(self) -> None:
+        """Emit the §8.6 version status, with the installed version when untested."""
+        try:
+            status = version_status()
+        except Exception:  # noqa: BLE001 - a version probe must never break the worker
+            LOGGER.exception("version_status failed")
+            status = UNKNOWN
+        installed = None
+        if status == UNTESTED:
+            installed = installed_photocraft_version()
+        self.version_status_ready.emit(status, installed)
+
     def _proxy_for(self, max_side: int) -> tuple[Image, RGB8]:
         """Return the cached (float32 proxy, uint8 proxy) of the source at max_side."""
         cached = self._proxies.get(max_side)
@@ -193,3 +329,10 @@ class RenderWorker(QObject):
             self.failed.emit(f"Render failed: {exc}")
             return None
         return RenderResult(self._job, rgb8, time.perf_counter() - started)
+
+    def _client(self) -> PhotoCraftClient | None:
+        """Return a connected PhotoCraft client, or emit a failure and return None."""
+        client = PhotoCraftClient.discover()
+        if client is None:
+            self.failed.emit(self._no_client_message)
+        return client
diff --git a/lattice_dither/ui/canvas.py b/lattice_dither/ui/canvas.py
deleted file mode 100644
index e60e0fc..0000000
--- a/lattice_dither/ui/canvas.py
+++ /dev/null
@@ -1,244 +0,0 @@
-"""Preview canvas with nearest-neighbour display and before/after/split modes."""
-
-from __future__ import annotations
-
-from typing import Literal
-
-import numpy as np
-from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
-from PySide6.QtGui import (
-    QColor,
-    QImage,
-    QMouseEvent,
-    QPainter,
-    QPen,
-    QPixmap,
-    QTransform,
-    QWheelEvent,
-)
-from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget
-
-from lattice_core.types import RGB8
-
-Mode = Literal["after", "before", "split"]
-
-MODES: tuple[str, ...] = ("after", "before", "split")
-MIN_ZOOM = 0.01
-MAX_ZOOM = 32.0
-WHEEL_STEP = 1.25
-FIT_MARGIN = 2.0
-
-
-def _as_rgb8(rgb8: RGB8) -> RGB8:
-    """Validate an RGB8 array and return it as a contiguous uint8 (H, W, 3) array."""
-    array = np.asarray(rgb8)
-    if array.ndim != 3 or array.shape[2] != 3:
-        raise ValueError(f"expected an (H, W, 3) array, got shape {array.shape}")
-    if array.dtype != np.uint8:
-        if array.dtype.kind not in "iu":
-            raise ValueError(f"expected a uint8 array, got dtype {array.dtype}")
-        array = np.clip(array, 0, 255).astype(np.uint8)
-    return np.ascontiguousarray(array)
-
-
-def _pixels(image: QImage) -> np.ndarray:
-    """Return a writable (height, bytesPerLine) uint8 view of the image pixels."""
-    height = image.height()
-    return np.frombuffer(image.bits(), dtype=np.uint8).reshape(height, image.bytesPerLine())
-
-
-class PreviewCanvas(QGraphicsView):
-    """Zoomable, pannable preview of the rendered image with a split view."""
-
-    zoom_changed = Signal(float)
-
-    def __init__(self, parent: QWidget | None = None) -> None:
-        super().__init__(parent)
-        self._scene = QGraphicsScene(self)
-        self.setScene(self._scene)
-        self._item = QGraphicsPixmapItem()
-        self._item.setTransformationMode(Qt.TransformationMode.FastTransformation)
-        self._scene.addItem(self._item)
-        self._after: RGB8 | None = None
-        self._before: RGB8 | None = None
-        self._buffer: QImage | None = None
-        self._mode: Mode = "after"
-        self._zoom = 1.0
-        self._fitted = True
-        self._panning = False
-        self._pan_origin = QPoint()
-        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
-        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
-        self.setDragMode(QGraphicsView.DragMode.NoDrag)
-        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
-        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
-        self.setBackgroundBrush(QColor(32, 32, 34))
-        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
-        self.setFrameShape(QGraphicsView.Shape.NoFrame)
-
-    def set_image(self, rgb8: RGB8) -> None:
-        """Set the rendered (after) image and refresh the display."""
-        previous = None if self._after is None else self._after.shape
-        self._after = _as_rgb8(rgb8)
-        self._refresh()
-        if previous is None or (self._fitted and self._after.shape != previous):
-            self.zoom_fit()
-
-    def set_original(self, rgb8: RGB8 | None) -> None:
-        """Set the source (before) image, or None to clear it."""
-        self._before = None if rgb8 is None else _as_rgb8(rgb8)
-        self._refresh()
-
-    def set_mode(self, mode: Mode) -> None:
-        """Switch the preview between the after, before and split views."""
-        if mode not in MODES:
-            raise ValueError(f"unknown mode {mode!r}")
-        self._mode = mode
-        self._refresh()
-        self.viewport().update()
-
-    def mode(self) -> Mode:
-        """Return the active preview mode."""
-        return self._mode
-
-    def qimage(self) -> QImage | None:
-        """Return the QImage buffer the canvas displays, or None when it is empty."""
-        return self._buffer
-
-    def zoom(self) -> float:
-        """Return the current zoom factor (1.0 is one image pixel per screen pixel)."""
-        return self._zoom
-
-    def set_zoom(self, f: float) -> None:
-        """Set the zoom factor, clamped to the supported range."""
-        factor = float(min(max(float(f), MIN_ZOOM), MAX_ZOOM))
-        self._zoom = factor
-        self._fitted = False
-        self.setTransform(QTransform().scale(factor, factor))
-        self.zoom_changed.emit(factor)
-
-    def zoom_fit(self) -> None:
-        """Scale the image so that it fits entirely inside the viewport."""
-        rect = self._scene.sceneRect()
-        if rect.isEmpty():
-            return
-        viewport = self.viewport().size()
-        scale_x = (viewport.width() - FIT_MARGIN) / rect.width()
-        scale_y = (viewport.height() - FIT_MARGIN) / rect.height()
-        self.set_zoom(min(scale_x, scale_y))
-        self._fitted = True
-
-    def _refresh(self) -> None:
-        """Rebuild the displayed pixmap from the current images and mode."""
-        after = self._after
-        if after is None:
-            self._item.setPixmap(QPixmap())
-            self._scene.setSceneRect(QRectF())
-            return
-        self._compose(after)
-        pixmap = QPixmap.fromImage(self._buffer)
-        self._item.setPixmap(pixmap)
-        self._scene.setSceneRect(QRectF(pixmap.rect()))
-
-    def _compose(self, after: RGB8) -> None:
-        """Write the image matching the current mode into the display buffer."""
-        before = self._before
-        paired = before is not None and before.shape == after.shape
-        if paired and self._mode == "before":
-            self._blit(before)
-            return
-        self._blit(after)
-        if paired and self._mode == "split":
-            self._blit_left(before)
-
-    def _blit(self, rgb8: RGB8) -> None:
-        """Copy rgb8 into the display buffer, reallocating it only when the shape changes."""
-        height, width = rgb8.shape[:2]
-        buffer = self._buffer
-        if buffer is None or buffer.width() != width or buffer.height() != height:
-            buffer = QImage(width, height, QImage.Format.Format_RGB888)
-            self._buffer = buffer
-        view = _pixels(buffer)
-        view[:, : width * 3] = rgb8.reshape(height, width * 3)
-        if view.shape[1] > width * 3:
-            view[:, width * 3 :] = 0
-
-    def _blit_left(self, rgb8: RGB8) -> None:
-        """Copy the left half of rgb8 into the display buffer."""
-        buffer = self._buffer
-        if buffer is None:
-            return
-        height, width = rgb8.shape[:2]
-        half = (width // 2) * 3
-        _pixels(buffer)[:, :half] = rgb8.reshape(height, width * 3)[:, :half]
-
-    def wheelEvent(self, event: QWheelEvent) -> None:
-        """Zoom around the cursor with the mouse wheel."""
-        delta = event.angleDelta().y()
-        if delta == 0:
-            event.ignore()
-            return
-        factor = WHEEL_STEP if delta > 0 else 1.0 / WHEEL_STEP
-        self.zoom_around(event.position(), self._zoom * factor)
-        event.accept()
-
-    def zoom_around(self, position: QPointF, f: float) -> None:
-        """Set the zoom factor while keeping the scene point under position fixed."""
-        anchor = self.mapToScene(position.toPoint())
-        self.set_zoom(f)
-        offset = self.mapFromScene(anchor) - position.toPoint()
-        horizontal = self.horizontalScrollBar()
-        vertical = self.verticalScrollBar()
-        horizontal.setValue(horizontal.value() + offset.x())
-        vertical.setValue(vertical.value() + offset.y())
-
-    def mousePressEvent(self, event: QMouseEvent) -> None:
-        """Start panning on a left or middle button press."""
-        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
-            self._panning = True
-            self._pan_origin = event.position().toPoint()
-            self.setCursor(Qt.CursorShape.ClosedHandCursor)
-            event.accept()
-            return
-        super().mousePressEvent(event)
-
-    def mouseMoveEvent(self, event: QMouseEvent) -> None:
-        """Scroll the view while a pan drag is active."""
-        if self._panning:
-            position = event.position().toPoint()
-            delta = position - self._pan_origin
-            self._pan_origin = position
-            horizontal = self.horizontalScrollBar()
-            vertical = self.verticalScrollBar()
-            horizontal.setValue(horizontal.value() - delta.x())
-            vertical.setValue(vertical.value() - delta.y())
-            event.accept()
-            return
-        super().mouseMoveEvent(event)
-
-    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
-        """Finish panning when the drag button is released."""
-        if self._panning and event.button() in (
-            Qt.MouseButton.LeftButton,
-            Qt.MouseButton.MiddleButton,
-        ):
-            self._panning = False
-            self.unsetCursor()
-            event.accept()
-            return
-        super().mouseReleaseEvent(event)
-
-    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
-        """Draw the divider line of the split view."""
-        super().drawForeground(painter, rect)
-        after = self._after
-        before = self._before
-        if self._mode != "split" or after is None or before is None:
-            return
-        if before.shape != after.shape:
-            return
-        x = float(after.shape[1] // 2)
-        painter.save()
-        painter.setPen(QPen(QColor(255, 255, 255, 180), 0))
-        painter.drawLine(QPointF(x, 0.0), QPointF(x, float(after.shape[0])))
-        painter.restore()
diff --git a/lattice_dither/ui/commands.py b/lattice_dither/ui/commands.py
index aae6c91..1f38e69 100644
--- a/lattice_dither/ui/commands.py
+++ b/lattice_dither/ui/commands.py
@@ -24,8 +24,9 @@ from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence
 
 from lattice_core import color
 from lattice_core.pipeline import PipelineSpec
+from lattice_core.ui.export_dialog import run_export_dialog
+from lattice_dither.export.video import export_video
 from lattice_dither.i18n import tr
-from lattice_dither.ui.export_dialog import run_export_dialog
 
 if TYPE_CHECKING:
     from lattice_dither.ui.main_window import MainWindow
@@ -267,12 +268,20 @@ class CommandController(QObject):
         self.open_path(Path(path))
 
     def export_dialog(self) -> None:
-        """Open the export dialog on the last rendered preview."""
-        image = self.window._last_image
-        if image is None:
+        """Open the shared core dialog, which renders the pipeline at full resolution."""
+        source = self.window.prepared_source
+        if source is None:
             self.window._error(tr("Load an image before exporting."))
             return
-        run_export_dialog(image, self.window)
+        self.window._rebuild_spec()
+        run_export_dialog(
+            source,
+            copy.deepcopy(self.window.spec),
+            self.window,
+            settings=self.window._settings,
+            video_writer=export_video,
+            tr=tr,
+        )
 
     def rerender(self) -> None:
         """Render the current pipeline again, reporting when there is no source."""
diff --git a/lattice_dither/ui/export_dialog.py b/lattice_dither/ui/export_dialog.py
deleted file mode 100644
index 4acceeb..0000000
--- a/lattice_dither/ui/export_dialog.py
+++ /dev/null
@@ -1,282 +0,0 @@
-"""Export dialog: one window for the four export formats (CONTRACT §19 to §21).
-
-The dialog renders nothing: it is handed the finished uint8 RGB image, and for the
-animated formats the rendered frame sequence, and writes it with the export functions of
-``lattice_dither.export``. The last directory used is remembered in ``QSettings`` under
-``export_dir``, the same key the main window uses for its PNG export.
-
-The defaults are the contract defaults: ``cell=1``, ``dpi=300``, ``bleed_mm=0``,
-``crop_marks=False``, ``separations=False`` and ``fps=12``.
-"""
-
-from __future__ import annotations
-
-from pathlib import Path
-
-from PySide6.QtCore import QSettings
-from PySide6.QtWidgets import (
-    QCheckBox,
-    QComboBox,
-    QDialog,
-    QDialogButtonBox,
-    QDoubleSpinBox,
-    QFileDialog,
-    QFormLayout,
-    QHBoxLayout,
-    QLabel,
-    QLineEdit,
-    QPushButton,
-    QSpinBox,
-    QStackedWidget,
-    QVBoxLayout,
-    QWidget,
-)
-
-from lattice_core.types import RGB8
-from lattice_dither.export.print import export_print
-from lattice_dither.export.svg import export_svg
-from lattice_dither.export.video import export_gif, export_video
-from lattice_dither.i18n import tr
-
-SETTINGS_NAME = "LatticeDither"
-EXPORT_DIR_KEY = "export_dir"
-REPORT_SEPARATOR = "\n"
-FORMATS: tuple[str, ...] = ("svg", "print", "gif", "video")
-FORMAT_LABELS = {"svg": "SVG", "print": "Print PNG", "gif": "Animated GIF", "video": "Video"}
-FORMAT_SUFFIX = {"svg": ".svg", "print": ".png", "gif": ".gif", "video": ".mp4"}
-FORMAT_FILTER = {
-    "svg": "SVG images (*.svg);;All files (*)",
-    "print": "PNG images (*.png);;All files (*)",
-    "gif": "Animated GIF (*.gif);;All files (*)",
-    "video": "Video (*.mp4 *.mkv *.webm);;All files (*)",
-}
-DEFAULT_CELL = 1
-DEFAULT_DPI = 300
-DEFAULT_BLEED_MM = 0.0
-DEFAULT_FPS = 12
-DEFAULT_LOOP = 0
-MAX_CELL = 64
-MAX_DPI = 1200
-MAX_BLEED_MM = 50.0
-MAX_FPS = 60
-MAX_LOOP = 100
-
-
-class ExportError(Exception):
-    """An export that could not be written: no output path, or no ffmpeg."""
-
-
-class ExportDialog(QDialog):
-    """Dialog exporting one render as SVG, print PNG, animated GIF or video."""
-
-    def __init__(
-        self,
-        image: RGB8,
-        parent: QWidget | None = None,
-        *,
-        frames: list[RGB8] | None = None,
-        settings: QSettings | None = None,
-    ) -> None:
-        """Build the dialog for image, using frames for the animated formats."""
-        super().__init__(parent)
-        self.setWindowTitle(tr("Export"))
-        self.image = image
-        self.frames = list(frames) if frames else [image]
-        self.written: list[Path] = []
-        self._settings = settings or QSettings(SETTINGS_NAME, SETTINGS_NAME)
-        self._build()
-        self._load_defaults()
-
-    def _build(self) -> None:
-        """Create the format selector, the option pages, the path row and the buttons."""
-        self.format_box = QComboBox(self)
-        self.format_box.setObjectName("export_format")
-        for key in FORMATS:
-            self.format_box.addItem(tr(FORMAT_LABELS[key]), key)
-        self.stack = QStackedWidget(self)
-        self.stack.setObjectName("export_options")
-        self._build_svg_page()
-        self._build_print_page()
-        self._build_gif_page()
-        self._build_video_page()
-        self.path_edit = QLineEdit(self)
-        self.path_edit.setObjectName("export_path")
-        browse = QPushButton(tr("Browse…"), self)
-        browse.setObjectName("export_browse")
-        browse.clicked.connect(self._on_browse)
-        row = QHBoxLayout()
-        row.addWidget(self.path_edit)
-        row.addWidget(browse)
-        self.report = QLabel(self)
-        self.report.setObjectName("export_report")
-        self.report.setWordWrap(True)
-        self.buttons = QDialogButtonBox(
-            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close, self
-        )
-        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Export"))
-        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
-        self.buttons.accepted.connect(self._on_export)
-        self.buttons.rejected.connect(self.reject)
-        layout = QVBoxLayout(self)
-        layout.addWidget(self.format_box)
-        layout.addWidget(self.stack)
-        layout.addLayout(row)
-        layout.addWidget(self.report)
-        layout.addWidget(self.buttons)
-        self.format_box.currentIndexChanged.connect(self._on_format_changed)
-
-    def _build_svg_page(self) -> None:
-        """Create the SVG page: cell size and background colour."""
-        page = QWidget(self.stack)
-        self.cell = QSpinBox(page)
-        self.cell.setObjectName("export_cell")
-        self.cell.setRange(1, MAX_CELL)
-        self.cell.setValue(DEFAULT_CELL)
-        self.background_edit = QLineEdit(page)
-        self.background_edit.setObjectName("export_background")
-        self.background_edit.setPlaceholderText(tr("#RRGGBB, empty for transparent"))
-        form = QFormLayout(page)
-        form.addRow(tr("Cell size"), self.cell)
-        form.addRow(tr("Background"), self.background_edit)
-        self.stack.addWidget(page)
-
-    def _build_print_page(self) -> None:
-        """Create the print page: resolution, bleed, crop marks and separations."""
-        page = QWidget(self.stack)
-        self.dpi = QSpinBox(page)
-        self.dpi.setObjectName("export_dpi")
-        self.dpi.setRange(1, MAX_DPI)
-        self.dpi.setValue(DEFAULT_DPI)
-        self.bleed = QDoubleSpinBox(page)
-        self.bleed.setObjectName("export_bleed")
-        self.bleed.setRange(0.0, MAX_BLEED_MM)
-        self.bleed.setDecimals(1)
-        self.bleed.setValue(DEFAULT_BLEED_MM)
-        self.crop_marks = QCheckBox(tr("Crop marks"), page)
-        self.crop_marks.setObjectName("export_crop_marks")
-        self.separations = QCheckBox(tr("Separations"), page)
-        self.separations.setObjectName("export_separations")
-        form = QFormLayout(page)
-        form.addRow(tr("Resolution"), self.dpi)
-        form.addRow(tr("Bleed (mm)"), self.bleed)
-        form.addRow(self.crop_marks)
-        form.addRow(self.separations)
-        self.stack.addWidget(page)
-
-    def _build_gif_page(self) -> None:
-        """Create the GIF page: frame rate and loop count."""
-        page = QWidget(self.stack)
-        self.gif_fps = QSpinBox(page)
-        self.gif_fps.setObjectName("export_gif_fps")
-        self.gif_fps.setRange(1, MAX_FPS)
-        self.gif_fps.setValue(DEFAULT_FPS)
-        self.gif_loop = QSpinBox(page)
-        self.gif_loop.setObjectName("export_gif_loop")
-        self.gif_loop.setRange(0, MAX_LOOP)
-        self.gif_loop.setValue(DEFAULT_LOOP)
-        self.gif_loop.setSpecialValueText(tr("forever"))
-        form = QFormLayout(page)
-        form.addRow(tr("Frame rate"), self.gif_fps)
-        form.addRow(tr("Loop"), self.gif_loop)
-        self.stack.addWidget(page)
-
-    def _build_video_page(self) -> None:
-        """Create the video page: frame rate."""
-        page = QWidget(self.stack)
-        self.video_fps = QSpinBox(page)
-        self.video_fps.setObjectName("export_video_fps")
-        self.video_fps.setRange(1, MAX_FPS)
-        self.video_fps.setValue(DEFAULT_FPS)
-        form = QFormLayout(page)
-        form.addRow(tr("Frame rate"), self.video_fps)
-        self.stack.addWidget(page)
-
-    def format(self) -> str:
-        """Return the selected format key: svg, print, gif or video."""
-        return str(self.format_box.currentData())
-
-    def export_directory(self) -> Path:
-        """Return the remembered export directory, or the home directory."""
-        stored = self._settings.value(EXPORT_DIR_KEY)
-        return Path(stored) if stored else Path.home()
-
-    def target_path(self) -> Path:
-        """Return the output path typed in the dialog, with the format's suffix."""
-        text = self.path_edit.text().strip()
-        if not text:
-            raise ExportError(tr("Choose an output file first."))
-        path = Path(text)
-        return path if path.suffix else path.with_suffix(FORMAT_SUFFIX[self.format()])
-
-    def background(self) -> str | None:
-        """Return the SVG background colour, or None when the field is empty."""
-        return self.background_edit.text().strip() or None
-
-    def export_now(self) -> list[Path]:
-        """Export the image with the current options and return the files written."""
-        target = self.target_path()
-        target.parent.mkdir(parents=True, exist_ok=True)
-        written = self._write(target)
-        self.written = written
-        self._settings.setValue(EXPORT_DIR_KEY, str(target.parent))
-        lines = [tr("Exported {name}", name=path.name) for path in written]
-        self.report.setText(REPORT_SEPARATOR.join(lines))
-        return written
-
-    def _write(self, target: Path) -> list[Path]:
-        """Write the selected format to target and return every file created."""
-        kind = self.format()
-        if kind == "svg":
-            export_svg(self.image, target, cell=self.cell.value(), background=self.background())
-            return [target]
-        if kind == "print":
-            return export_print(
-                self.image,
-                target,
-                dpi=self.dpi.value(),
-                bleed_mm=self.bleed.value(),
-                crop_marks=self.crop_marks.isChecked(),
-                separations=self.separations.isChecked(),
-            )
-        if kind == "gif":
-            export_gif(self.frames, target, fps=self.gif_fps.value(), loop=self.gif_loop.value())
-            return [target]
-        if not export_video(self.frames, target, fps=self.video_fps.value()):
-            reason = tr("No ffmpeg available.")
-            raise ExportError(tr("Cannot write {path}: {error}", path=target.name, error=reason))
-        return [target]
-
-    def _on_export(self) -> None:
-        """Export with the current options and report the outcome in the dialog."""
-        try:
-            self.export_now()
-        except (ExportError, OSError, ValueError) as exc:
-            self.report.setText(str(exc))
-
-    def _on_format_changed(self, index: int) -> None:
-        """Show the options of the selected format and retarget the path suffix."""
-        self.stack.setCurrentIndex(index)
-        text = self.path_edit.text().strip() or "export"
-        self.path_edit.setText(str(Path(text).with_suffix(FORMAT_SUFFIX[self.format()])))
-
-    def _on_browse(self) -> None:
-        """Ask for an output path with the selected format's filter."""
-        current = self.path_edit.text().strip() or str(self.export_directory())
-        filters = tr(FORMAT_FILTER[self.format()])
-        path, _ = QFileDialog.getSaveFileName(self, tr("Export"), current, filters)
-        if path:
-            self.path_edit.setText(path)
-
-    def _load_defaults(self) -> None:
-        """Point the path field at the remembered directory and the format's suffix."""
-        suffix = FORMAT_SUFFIX[self.format()]
-        self.path_edit.setText(str(self.export_directory() / f"export{suffix}"))
-
-
-def run_export_dialog(
-    image: RGB8, parent: QWidget | None = None, *, frames: list[RGB8] | None = None
-) -> list[Path]:
-    """Show the export dialog for image and return every file written."""
-    dialog = ExportDialog(image, parent, frames=frames)
-    dialog.exec()
-    return dialog.written
diff --git a/lattice_dither/ui/main_window.py b/lattice_dither/ui/main_window.py
index 07869d9..53b31f3 100644
--- a/lattice_dither/ui/main_window.py
+++ b/lattice_dither/ui/main_window.py
@@ -37,16 +37,16 @@ from lattice_core.bridge.photocraft import TESTED_PHOTOCRAFT_VERSION
 from lattice_core.pipeline import PipelineSpec
 from lattice_core.presets import is_within, shipped_preset_dir, user_preset_dir
 from lattice_core.types import RGB8, Image
+from lattice_core.ui.canvas import PreviewCanvas
+from lattice_core.ui.worker import PreviewResult, RenderResult, RenderWorker
 from lattice_dither.i18n import tr
 from lattice_dither.preprocess import descreen, detect_grid, snap_to_grid
 from lattice_dither.ui.algorithm_panel import AlgorithmPanel
-from lattice_dither.ui.canvas import PreviewCanvas
 from lattice_dither.ui.commands import CommandController
 from lattice_dither.ui.effects_panel import EffectsPanel
 from lattice_dither.ui.gallery import AlgorithmGallery
 from lattice_dither.ui.palette_panel import PalettePanel
 from lattice_dither.ui.preset_browser import PresetController
-from lattice_dither.ui.worker import PreviewResult, RenderResult, RenderWorker
 
 LOGGER = logging.getLogger(__name__)
 
@@ -239,7 +239,7 @@ class MainWindow(QMainWindow):
     def _start_worker(self) -> None:
         """Create the render worker in its own thread and connect every signal."""
         self.thread = QThread(self)
-        self.worker = RenderWorker()
+        self.worker = RenderWorker(bridge=True, shortcut_name="PhotoCraft (Lattice Dither)")
         self.worker.moveToThread(self.thread)
         self.thread.started.connect(self.worker.start)
         self.thread.finished.connect(self.worker.deleteLater)
diff --git a/lattice_dither/ui/palette_panel.py b/lattice_dither/ui/palette_panel.py
index 5511911..d616838 100644
--- a/lattice_dither/ui/palette_panel.py
+++ b/lattice_dither/ui/palette_panel.py
@@ -38,8 +38,8 @@ from lattice_core.palettes.io import (
 from lattice_core.palettes.library import get_library, library_names
 from lattice_core.pipeline import PipelineSpec
 from lattice_core.types import Image
+from lattice_core.ui.worker import PaletteExtraction
 from lattice_dither.i18n import tr
-from lattice_dither.ui.worker import PaletteExtraction
 
 LOGGER = logging.getLogger(__name__)
 
diff --git a/lattice_dither/ui/worker.py b/lattice_dither/ui/worker.py
deleted file mode 100644
index 708dfce..0000000
--- a/lattice_dither/ui/worker.py
+++ /dev/null
@@ -1,356 +0,0 @@
-"""Render worker: progressive previews, full-resolution renders and bridge calls.
-
-Previews are rendered from cached proxies, coarse first (``PREVIEW_STAGES``), so a large
-source never reaches the pipeline at full resolution. The full render happens only on
-export or send. Sources above ``MAX_SOURCE_SIDE`` are refused instead of exhausting memory.
-"""
-
-from __future__ import annotations
-
-import logging
-import threading
-import time
-from dataclasses import dataclass
-
-import numpy as np
-from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
-
-from lattice_core import color
-from lattice_core.bridge.photocraft import (
-    BridgeError,
-    PhotoCraftClient,
-    installed_photocraft_version,
-    version_status,
-)
-from lattice_core.palettes.extract import extract_palette
-from lattice_core.palettes.io import hex_list
-from lattice_core.pipeline import PipelineSpec, render
-from lattice_core.types import RGB8, Image
-
-LOGGER = logging.getLogger(__name__)
-
-DEBOUNCE_MS = 120
-PREVIEW_STAGES: tuple[int, ...] = (256, 1024)
-PREVIEW_MAX_SIDE = PREVIEW_STAGES[-1]
-MAX_SOURCE_SIDE = 8000
-PROXY_STRIP_ROWS = 256
-CONNECTION_INTERVAL_MS = 3000
-PROBE_JOIN_MS = 250
-LAYER_NAME = "Lattice Dither"
-CONNECTED = "connected"
-DISCONNECTED = "disconnected"
-UNTESTED = "untested"
-UNKNOWN = "unknown"
-NO_CLIENT_MESSAGE = (
-    "PhotoCraft is not reachable. Start it from the PhotoCraft (Lattice Dither) shortcut."
-)
-
-
-@dataclass(frozen=True)
-class RenderResult:
-    """One finished full-resolution render: its job, the image and its duration."""
-
-    job: int
-    image: RGB8
-    seconds: float
-
-
-@dataclass(frozen=True)
-class PreviewResult:
-    """One finished preview stage: its job, the render, the source proxy and its duration."""
-
-    job: int
-    image: RGB8
-    original: RGB8
-    seconds: float
-    max_side: int = PREVIEW_MAX_SIDE
-
-
-def proxy_factor(image: Image, max_side: int) -> int:
-    """Return the integer area-downscale factor that brings image under max_side."""
-    longest = max(image.shape[:2])
-    return max(1, -(-longest // max(1, int(max_side))))
-
-
-def _downscale_strips(image: Image, factor: int) -> Image:
-    """Area-downscale image by factor in row strips, so peak memory stays near the output."""
-    if factor <= 1:
-        return np.ascontiguousarray(image, dtype=np.float32)
-    rows = max(factor, (PROXY_STRIP_ROWS // factor) * factor)
-    parts = [
-        color.downscale(image[start : start + rows], factor)
-        for start in range(0, image.shape[0], rows)
-    ]
-    return np.ascontiguousarray(np.concatenate(parts, axis=0))
-
-
-def preview_proxy(image: Image, max_side: int = PREVIEW_MAX_SIDE) -> RGB8:
-    """Return the uint8 proxy of image, shaped like the preview render at max_side."""
-    return color.to_rgb8(_downscale_strips(image, proxy_factor(image, max_side)))
-
-
-def oversize_message(shape: tuple[int, ...]) -> str | None:
-    """Return the refusal message for a source of this (height, width), or None."""
-    if len(shape) < 2:
-        return None
-    height, width = int(shape[0]), int(shape[1])
-    if max(height, width) <= MAX_SOURCE_SIDE:
-        return None
-    return (
-        f"Image is {width}×{height} px, above the {MAX_SOURCE_SIDE} px limit; "
-        "downscale it before opening it in Lattice Dither."
-    )
-
-
-class ConnectionProbe(QObject):
-    """Runs discover() on a helper thread so a slow probe never delays a render."""
-
-    state_changed = Signal(str)
-
-    def __init__(self, parent: QObject | None = None) -> None:
-        super().__init__(parent)
-        self._lock = threading.Lock()
-        self._thread: threading.Thread | None = None
-        self._stopped = False
-
-    def check(self) -> None:
-        """Start one discover() probe unless the previous one is still running."""
-        with self._lock:
-            if self._stopped or (self._thread is not None and self._thread.is_alive()):
-                return
-            self._thread = threading.Thread(
-                target=self._run, name="photocraft-probe", daemon=True
-            )
-            self._thread.start()
-
-    def stop(self) -> None:
-        """Stop emitting probe results and wait briefly for the running probe."""
-        with self._lock:
-            self._stopped = True
-            thread = self._thread
-        if thread is not None:
-            thread.join(PROBE_JOIN_MS / 1000.0)
-
-    def _run(self) -> None:
-        """Probe PhotoCraft and emit the resulting connection state."""
-        try:
-            client = PhotoCraftClient.discover()
-        except Exception:  # noqa: BLE001 - a probe must never raise
-            LOGGER.exception("PhotoCraft discovery failed")
-            client = None
-        if not self._stopped:
-            self.state_changed.emit(CONNECTED if client is not None else DISCONNECTED)
-
-
-class PaletteExtraction(QObject):
-    """Runs one palette extraction on a helper thread and reports it by signal."""
-
-    finished = Signal(object)
-    failed = Signal(str)
-
-    def __init__(self, image: Image, k: int, method: str) -> None:
-        super().__init__()
-        self._args = (image, k, method)
-        self._thread = QThread()
-        self.moveToThread(self._thread)
-        self._thread.started.connect(self.run)
-        self.finished.connect(self._thread.quit)
-        self.failed.connect(self._thread.quit)
-        self._thread.finished.connect(self.deleteLater)
-        _ACTIVE_EXTRACTIONS.add(self)
-        self._thread.finished.connect(lambda: _ACTIVE_EXTRACTIONS.discard(self))
-
-    def start(self) -> None:
-        """Start the helper thread; this object stays alive until it finishes."""
-        self._thread.start()
-
-    @Slot()
-    def run(self) -> None:
-        """Emit the extracted colours, or the error message."""
-        try:
-            self.finished.emit(hex_list(extract_palette(*self._args)))
-        except ValueError as exc:
-            self.failed.emit(str(exc))
-
-
-_ACTIVE_EXTRACTIONS: set[PaletteExtraction] = set()
-
-
-class RenderWorker(QObject):
-    """Renders previews and full-resolution images and talks to PhotoCraft."""
-
-    preview_ready = Signal(object)
-    export_ready = Signal(object)
-    image_ready = Signal(object)
-    send_finished = Signal(int)
-    failed = Signal(str)
-    progress = Signal(str)
-    connection_state = Signal(str)
-    version_status_ready = Signal(str, object)
-
-    def __init__(self, parent: QObject | None = None) -> None:
-        super().__init__(parent)
-        self.probe = ConnectionProbe(self)
-        self.probe.state_changed.connect(self.connection_state)
-        self._source: Image | None = None
-        self._proxies: dict[int, tuple[Image, RGB8]] = {}
-        self._spec: PipelineSpec | None = None
-        self._job = 0
-        self._pending_job = 0
-        self._debounce: QTimer | None = None
-        self._connection: QTimer | None = None
-
-    @Slot()
-    def start(self) -> None:
-        """Create the timers inside the worker thread and run the startup checks."""
-        self._debounce = QTimer(self)
-        self._debounce.setSingleShot(True)
-        self._debounce.setInterval(DEBOUNCE_MS)
-        self._debounce.timeout.connect(self._render_preview)
-        self._connection = QTimer(self)
-        self._connection.setInterval(CONNECTION_INTERVAL_MS)
-        self._connection.timeout.connect(self.check_connection)
-        self._connection.start()
-        self.check_connection()
-        self.check_version()
-
-    def stop_probing(self) -> None:
-        """Stop the connection probe; called from the GUI thread before shutdown."""
-        self.probe.stop()
-
-    @Slot(object)
-    def set_source(self, image: Image | None) -> None:
-        """Adopt image as the pipeline source, refusing sources above MAX_SOURCE_SIDE."""
-        if image is not None:
-            message = oversize_message(np.shape(image))
-            if message is not None:
-                self.failed.emit(message)
-                return
-        self._proxies.clear()
-        self._source = None if image is None else np.ascontiguousarray(image, dtype=np.float32)
-
-    @Slot(object)
-    def request_preview(self, spec: PipelineSpec) -> None:
-        """Store spec and restart the debounce timer; only the last spec is rendered."""
-        self._spec = spec
-        self._job += 1
-        self._pending_job = self._job
-        if self._debounce is not None:
-            self._debounce.start()
-
-    @Slot(object)
-    def request_export(self, spec: PipelineSpec) -> None:
-        """Render spec at full resolution and emit the result for saving."""
-        result = self._render_full(spec)
-        if result is not None:
-            self.export_ready.emit(result)
-
-    @Slot(object)
-    def request_send(self, spec: PipelineSpec) -> None:
-        """Render spec at full resolution and place it as a new PhotoCraft layer."""
-        self.progress.emit("Rendering for PhotoCraft…")
-        result = self._render_full(spec)
-        if result is None:
-            return
-        client = self._client()
-        if client is None:
-            return
-        self.progress.emit("Sending the render to PhotoCraft…")
-        try:
-            layer = client.place_as_layer(color.to_pil(result.image), LAYER_NAME)
-        except BridgeError as exc:
-            self.failed.emit(f"Cannot send the render to PhotoCraft: {exc}")
-            return
-        self.send_finished.emit(int(layer))
-
-    @Slot()
-    def request_get(self) -> None:
-        """Fetch the visible PhotoCraft document and emit it as a float32 image."""
-        client = self._client()
-        if client is None:
-            return
-        self.progress.emit("Fetching the image from PhotoCraft…")
-        try:
-            image = client.render_document()
-        except BridgeError as exc:
-            self.failed.emit(f"Cannot get the image from PhotoCraft: {exc}")
-            return
-        self.image_ready.emit(color.to_float(image))
-
-    @Slot()
-    def check_connection(self) -> None:
-        """Refresh the PhotoCraft connection state with one discover() call."""
-        self.probe.check()
-
-    @Slot()
-    def check_version(self) -> None:
-        """Emit the §8.6 version status, with the installed version when untested."""
-        try:
-            status = version_status()
-        except Exception:  # noqa: BLE001 - a version probe must never break the worker
-            LOGGER.exception("version_status failed")
-            status = UNKNOWN
-        installed = None
-        if status == UNTESTED:
-            installed = installed_photocraft_version()
-        self.version_status_ready.emit(status, installed)
-
-    def _proxy_for(self, max_side: int) -> tuple[Image, RGB8]:
-        """Return the cached (float32 proxy, uint8 proxy) of the source at max_side."""
-        cached = self._proxies.get(max_side)
-        if cached is None:
-            source = self._source
-            if source is None:
-                raise ValueError("no source image")
-            proxy = _downscale_strips(source, proxy_factor(source, max_side))
-            cached = (proxy, color.to_rgb8(proxy))
-            self._proxies[max_side] = cached
-        return cached
-
-    def _render_preview(self) -> None:
-        """Render the latest spec through the preview stages, dropping superseded jobs."""
-        spec, source = self._spec, self._source
-        if spec is None or source is None:
-            return
-        job = self._pending_job
-        if job != self._job:
-            LOGGER.debug("dropping superseded preview job %d", job)
-            return
-        previous: tuple[int, int] | None = None
-        for max_side in PREVIEW_STAGES:
-            if job != self._job:
-                LOGGER.debug("dropping superseded preview job %d", job)
-                return
-            started = time.perf_counter()
-            try:
-                proxy, original = self._proxy_for(max_side)
-                rgb8 = render(proxy, spec)
-            except Exception as exc:  # noqa: BLE001 - report any render failure to the user
-                self.failed.emit(f"Render failed: {exc}")
-                return
-            if rgb8.shape == previous:
-                continue
-            previous = rgb8.shape
-            seconds = time.perf_counter() - started
-            self.preview_ready.emit(PreviewResult(job, rgb8, original, seconds, max_side))
-
-    def _render_full(self, spec: PipelineSpec) -> RenderResult | None:
-        """Render spec at full resolution, emitting failed and returning None on error."""
-        source = self._source
-        if source is None:
-            self.failed.emit("Load an image before rendering.")
-            return None
-        started = time.perf_counter()
-        try:
-            rgb8 = render(source, spec)
-        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
-            self.failed.emit(f"Render failed: {exc}")
-            return None
-        return RenderResult(self._job, rgb8, time.perf_counter() - started)
-
-    def _client(self) -> PhotoCraftClient | None:
-        """Return a connected PhotoCraft client, or emit a failure and return None."""
-        client = PhotoCraftClient.discover()
-        if client is None:
-            self.failed.emit(NO_CLIENT_MESSAGE)
-        return client


CODER NOTES AND DEVIATIONS (attempt 2, transcript)
(vide)