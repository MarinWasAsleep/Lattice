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

CONTRACT EXCERPTS (version 0.1.0)

## §1 Scope

Lattice is a family of free, open-source desktop applications that transform images, each of which
runs standalone and also plugs into the ArtCraft suite over its local control server.

Three applications are in scope:

| App | Package | Transform family |
|---|---|---|
| Lattice Dither | `lattice-dither` | palette dithering |
| Lattice Glyph | `lattice-glyph` | glyph, bitmask and text rendering |
| Lattice Glitch | `lattice-glitch` | feedback, displacement, sorting, signal degradation |

All three share one engine, `lattice-core`. All three target **fixed images only**. Video is out of
scope for this contract.

All packages run on **Windows and Linux** (the dither application already does; ArtCraft hosts exist
on both, so the bridge is testable on both). Card L23 covers packaging and install per platform.

Licence: MIT OR Apache-2.0, dual, for every package. No dependency may be added that is not compatible with both.



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



## §7 Bridge

One client, one adapter per host. The bridge is never fatal: every application works standalone.

```python
class ArtCraftClient:
    @staticmethod
    def discover(host: Literal["photocraft", "designcraft"], port: int | None = None) -> ArtCraftClient | None
    def ping(self) -> bool
    def render_document(self) -> Image.Image
    def place_as_layer(self, img: Image.Image, name: str) -> int
```

- **PhotoCraft** (port 47600, token file): `document.inspect`, `app.save`, `app.open`,
  `layer.copyToDocument`, `file.close`. This is the existing Lattice Dither implementation, moved.
- **DesignCraft**: `file.place` with `{path, frame?}` when a frame is selected, otherwise
  `{path, x, y, width}` to create one. `place_as_layer` returns the placed object id.
- Discovery reads the token file, opens one authenticated connection, and calls `engine.commands`
  as the liveness probe. A missing token, a refused connection or a failed probe returns `None`.
- Every call is bounded by a timeout. A bridge failure surfaces as a typed error, never a crash.
- The exchange directory is per-application, under the platform app-data directory
  (QStandardPaths: `%LOCALAPPDATA%/<App>` on Windows, `~/.local/share/<App>` on Linux), and files
  older than one hour are discarded on each call.



## §8 CLI

Every application exposes the same four verbs:

```
<app> render  --preset P --in IMG --out IMG
<app> batch   --preset P --in DIR --out DIR [--recursive]
<app> presets list|show|validate
<app> bridge  status|pull|push
```

- `render` and the GUI must produce **byte-identical** output for the same preset and image (G9).
- Exit codes: 0 success, 1 usage error, 2 render error, 3 bridge error.
- `--json` on any verb prints a machine-readable result on stdout and nothing else.
- No verb may require a display. `import lattice_core.ui` must not happen on the CLI path.



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



## §10 Text-halftone

`text` renderer. A flowing paragraph in a real font, not a character grid.

- Lay out the paragraph with real font metrics: kerning, line distance, word wrapping.
- Modulate per-glyph **weight, size and opacity** by the underlying `luma` (S2, decided
  2026-11-16): ink density must not collapse on a neutral palette.
- Cells may vary in size. `cell_aspect()` returns the nominal aspect; the renderer may vary a cell
  by ±50% and must still fill the output rectangle exactly.
- Options: `text` (string), `font`, `size`, `line_distance`, `kerning`, `size_mode`
  (`fixed` | `variable`), `weight_mode` (`fixed` | `variable`), `fg`/`bg`.
- `size_mode: fixed` keeps every glyph the same size and modulates only opacity. `variable` is the
  mode that makes the output look like art rather than ASCII.



## §11 Vector export

Every renderer can emit SVG.

- `pixel` → one `<rect>` per cell, merged into runs where adjacent cells share a colour.
- `glyph_ramp`, `glyph_shape`, `bitmask`, `text` → export driven by the renderer's `layout()`
  when it is available (H11): one `<text>` element per glyph, with `font-family`,
  `font-size` and `fill` set. The output is **editable typography**, not traced paths.
- Budget: 2048×2048 source, 16 colours, output under 8 MB. Beyond that, merge cells into rectangles
  and record a warning.
- SVG output must open in Inkscape, Illustrator and a browser without repair.

**Text export (P3, decided 2026-11-16).** `glyph_ramp`, `glyph_shape` and `bitmask` also emit
text — from `layout()` when available (H11): `.txt` (UTF-8, space-separated cells, `\n` line
breaks), `.ansi` (24-bit colour, SGR escapes; terminal-safe ordering), `.html` (a coloured `<pre>`
block in a standalone page). Shared CLI verb: `render --format png|svg|txt|ansi|html`. The ANSI
exporter must not leak escape codes into the text path; HTML output escapes text content.

TASK CARD

### L12 · Lattice Glyph application shell
- wave: 1 · deps: L6, L8, L9, L11 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glyph/**`, `tests/test_glyph_app.py`
- context: §1 §2 §7 §8 §9 §10 §11
- spec: the `lattice-glyph` distribution. PySide6 window with a renderer selector, a live preview, a
  palette panel, a preset browser, and the four CLI verbs of §8. Bridge to PhotoCraft and
  DesignCraft. Works standalone on a dropped file. No new dependency.
- accept:
  - the app launches, opens an image, renders, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - `bridge status` reports the host state without crashing when no host runs.
  - the app runs with `lattice-core` installed without the `[ui]` extra only for the CLI path.
  - every renderer in the registry is selectable in the UI.

GATE RESULTS (L12, attempt 1 — codeur deepseek-v4-1-flash-1017 sur mistral, TUÉ PAR TIMEOUT à 2700 s)
- CIRCONSTANCE : le codeur n'a jamais rendu son rapport (exit 124, sortie vide). Les 18 fichiers et le
  fichier de test étaient écrits sur disque avant qu'il ne se bloque. Aucun NOTES, aucune DEVIATION :
  ce que tu vois est le code nu. Une carte de cette taille (coquille d'application complète) sans
  justification est un risque en soi — sois plus dur que d'habitude sur les choix silencieux.
- `lattice_glyph/` : 18 fichiers, 2840 lignes. `tests/test_glyph_app.py` : 439 l, 9 tests.
- Suite complète : **2068 passed, 1 skipped** en 42 s. G1 ruff : all checks passed. G3 : OK.
- Un premier run a semblé bloquer (>400 s) : c'était de la CONTENTION CPU (le codeur tournait encore
  en parallèle), pas un test qui pend. Vérifié en relançant seul : 42 s.

CONTRÔLES QUE J'AI DÉJÀ FAITS MOI-MÊME — ne les refais pas, mais dis si je me suis trompé
1. Réutilisation de `lattice_core/ui` : `window.py`, `export_actions.py`, `rendering.py` importent
   `ExportDialog`, le canvas, le worker et `GlyphBrowser`. Aucun `QGraphicsView` ni `ExportDialog`
   n'est réimplémenté dans `lattice_glyph/` (grep exhaustif, 0 résultat).
2. G9 par fonction partagée : le CLI appelle `document.render_rgb8` → `_pipeline.render` ; la GUI
   appelle `rendering.render_full` → `render_rgb8`. Un seul chemin de rendu dans tout le paquet.
3. CLI sans Qt : `import lattice_glyph.cli` sous un bloqueur d'import de `PySide6` et de
   `lattice_core.ui` passe ; les deux sont absents de `sys.modules` après import.

CE QUE JE N'AI PAS VÉRIFIÉ ET QUE J'ATTENDS DE TOI
- §8 : les quatre verbes (`render`, `batch`, `presets list|show|validate`, `bridge status|pull|push`),
  les codes de sortie 0/1/2/3, `--json` imprimant un résultat machine et RIEN d'autre.
- La sélection des 8 renderers dans l'UI (accept L12 : « every renderer in the registry is
  selectable in the UI ») — vérifie que la liste est construite depuis `list_renderers()` et non
  codée en dur, sinon un renderer futur sera invisible.
- Le pont : `bridge status` doit rapporter l'état de l'hôte SANS planter quand aucun hôte ne tourne
  (E9). Vérifie que `discover()` renvoyant `None` est traité comme un état normal.
- La qualité des 9 tests : est-ce qu'ils échouent sur une app vide, ou sont-ils décoratifs ?
- Le mode continu (§5 S1) : Glyph quantifie toujours, mais si un preset v3 arrive avec
  `algorithm: null`, l'app doit-elle le refuser proprement ou le rendre ? Dis ce que tu observes.

DIFF (les 18 fichiers de `lattice_glyph/` + son test, créés de zéro)

diff --git a/lattice_glyph/__init__.py b/lattice_glyph/__init__.py
new file mode 100644
index 0000000..08f8883
--- /dev/null
+++ b/lattice_glyph/__init__.py
@@ -0,0 +1,7 @@
+"""Lattice Glyph: glyph, bitmask and text rendering for PhotoCraft and DesignCraft."""
+
+from __future__ import annotations
+
+APP_NAME = "Lattice Glyph"
+APP_ID = "glyph"
+__version__ = "0.1.0"
diff --git a/lattice_glyph/__main__.py b/lattice_glyph/__main__.py
new file mode 100644
index 0000000..21c3803
--- /dev/null
+++ b/lattice_glyph/__main__.py
@@ -0,0 +1,25 @@
+"""Entry point of Lattice Glyph: ``python -m lattice_glyph`` starts the window.
+
+With a verb on the command line it runs the CLI instead, so ``python -m lattice_glyph
+render …`` works before the distribution is installed; without one it opens the window.
+"""
+
+from __future__ import annotations
+
+import sys
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Run the CLI when a verb is given, the GUI otherwise, and return the exit code."""
+    arguments = list(sys.argv[1:] if argv is None else argv)
+    if arguments:
+        from lattice_glyph.cli import main as cli_main
+
+        return cli_main(arguments)
+    from lattice_glyph.app import main as app_main
+
+    return app_main([])
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/lattice_glyph/actions.py b/lattice_glyph/actions.py
new file mode 100644
index 0000000..4e47efc
--- /dev/null
+++ b/lattice_glyph/actions.py
@@ -0,0 +1,115 @@
+"""Actions and toolbar of the Glyph shell, built from one table so nothing is half-wired.
+
+Each entry pairs an object name with its label, its slot and its shortcut; the toolbar
+reads the same table, in the same order, so an action that exists is on the toolbar and an
+action on the toolbar has a real slot behind it.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+from pathlib import Path
+from typing import TYPE_CHECKING
+
+from PySide6.QtGui import QAction, QActionGroup, QKeySequence
+from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
+
+if TYPE_CHECKING:
+    from lattice_glyph.window import MainWindow
+
+Action = tuple[str, str, Callable[..., None]]
+MODES: tuple[tuple[str, str, str], ...] = (
+    ("mode_before", "Before", "before"),
+    ("mode_after", "After", "after"),
+    ("mode_split", "Split", "split"),
+)
+TOOLBAR_GROUPS: tuple[tuple[str, ...], ...] = (
+    ("open_image", "get_from_host", "send_to_host"),
+    ("export_image", "export_text"),
+    ("mode_before", "mode_after", "mode_split"),
+    ("zoom_fit", "zoom_100", "zoom_200", "zoom_400"),
+)
+MAIN_TOOLBAR = "main_toolbar"
+IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})
+
+
+def add_action(window: QMainWindow, key: str, text: str, slot: Callable[..., None],
+               shortcut: QKeySequence | None = None) -> QAction:
+    """Create one action on window, register it under key and connect it to slot."""
+    action = QAction(text, window)
+    action.setObjectName(key)
+    if shortcut is not None:
+        action.setShortcut(shortcut)
+    action.triggered.connect(slot)
+    window.addAction(action)
+    return action
+
+
+def build_actions(window: MainWindow) -> dict[str, QAction]:
+    """Create every action of the shell and return them keyed by object name."""
+    std = QKeySequence.StandardKey
+    actions: dict[str, QAction] = {}
+    table: tuple[tuple[str, str, Callable[..., None], QKeySequence | None], ...] = (
+        ("open_image", "Open image", window.open_dialog, std.Open),
+        ("get_from_host", "Get from host", window.get_from_host, None),
+        ("send_to_host", "Send to host", window.send_to_host, None),
+        ("export_image", "Export…", window.export_dialog, std.Save),
+        ("export_text", "Export text…", window.export_text, None),
+        ("zoom_fit", "Zoom Fit", window.canvas.zoom_fit, None),
+        ("zoom_100", "100 %", lambda: window.canvas.set_zoom(1.0), None),
+        ("zoom_200", "200 %", lambda: window.canvas.set_zoom(2.0), None),
+        ("zoom_400", "400 %", lambda: window.canvas.set_zoom(4.0), None),
+    )
+    for key, text, slot, shortcut in table:
+        actions[key] = add_action(window, key, text, slot, shortcut)
+    group = QActionGroup(window)
+    for key, text, mode in MODES:
+        action = add_action(window, key, text,
+                            lambda _checked=False, m=mode: window.set_mode(m))
+        action.setCheckable(True)
+        action.setChecked(mode == "after")
+        group.addAction(action)
+        actions[key] = action
+    window.mode_group = group
+    return actions
+
+
+def build_toolbar(window: QMainWindow, actions: dict[str, QAction]) -> QToolBar:
+    """Create the main toolbar, one separator between the groups of the table."""
+    toolbar = QToolBar("Main", window)
+    toolbar.setObjectName(MAIN_TOOLBAR)
+    toolbar.setMovable(False)
+    window.addToolBar(toolbar)
+    for index, keys in enumerate(TOOLBAR_GROUPS):
+        if index:
+            toolbar.addSeparator()
+        for key in keys:
+            toolbar.addAction(actions[key])
+    return toolbar
+
+
+def dropped_images(mime) -> list[Path]:
+    """Return the local image files carried by mime, in drop order."""
+    if not mime.hasUrls():
+        return []
+    paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
+    return [path for path in paths if path.suffix.lower() in IMAGE_SUFFIXES]
+
+
+def connect_shutdown(window: MainWindow) -> None:
+    """Stop the window's helper threads when the application quits."""
+    app = QApplication.instance()
+    if app is not None:
+        app.aboutToQuit.connect(window.shutdown)
+
+
+__all__ = [
+    "IMAGE_SUFFIXES",
+    "MAIN_TOOLBAR",
+    "TOOLBAR_GROUPS",
+    "add_action",
+    "build_actions",
+    "build_toolbar",
+    "connect_shutdown",
+    "dropped_images",
+]
diff --git a/lattice_glyph/app.py b/lattice_glyph/app.py
new file mode 100644
index 0000000..f82527f
--- /dev/null
+++ b/lattice_glyph/app.py
@@ -0,0 +1,75 @@
+"""QApplication bootstrap of Lattice Glyph: the Fusion dark theme and the window."""
+
+from __future__ import annotations
+
+import logging
+import sys
+
+from PySide6.QtGui import QColor, QPalette
+from PySide6.QtWidgets import QApplication
+
+from lattice_glyph import APP_NAME
+from lattice_glyph.actions import connect_shutdown
+from lattice_glyph.window import MainWindow
+
+LOGGER = logging.getLogger(__name__)
+
+BASE_COLOR = QColor(35, 35, 38)
+WINDOW_COLOR = QColor(53, 53, 56)
+TEXT_COLOR = QColor(220, 220, 220)
+DISABLED_COLOR = QColor(120, 120, 120)
+HIGHLIGHT_COLOR = QColor(64, 132, 214)
+
+
+def dark_palette() -> QPalette:
+    """Return the dark palette applied on top of the Fusion style."""
+    palette = QPalette()
+    palette.setColor(QPalette.ColorRole.Window, WINDOW_COLOR)
+    palette.setColor(QPalette.ColorRole.WindowText, TEXT_COLOR)
+    palette.setColor(QPalette.ColorRole.Base, BASE_COLOR)
+    palette.setColor(QPalette.ColorRole.AlternateBase, WINDOW_COLOR)
+    palette.setColor(QPalette.ColorRole.ToolTipBase, BASE_COLOR)
+    palette.setColor(QPalette.ColorRole.ToolTipText, TEXT_COLOR)
+    palette.setColor(QPalette.ColorRole.Text, TEXT_COLOR)
+    palette.setColor(QPalette.ColorRole.Button, WINDOW_COLOR)
+    palette.setColor(QPalette.ColorRole.ButtonText, TEXT_COLOR)
+    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
+    palette.setColor(QPalette.ColorRole.Link, HIGHLIGHT_COLOR)
+    palette.setColor(QPalette.ColorRole.Highlight, HIGHLIGHT_COLOR)
+    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
+    for role in (
+        QPalette.ColorRole.WindowText,
+        QPalette.ColorRole.Text,
+        QPalette.ColorRole.ButtonText,
+    ):
+        palette.setColor(QPalette.ColorGroup.Disabled, role, DISABLED_COLOR)
+    return palette
+
+
+def create_application(argv: list[str] | None = None) -> QApplication:
+    """Return the QApplication, creating it with the Fusion dark theme when needed."""
+    existing = QApplication.instance()
+    if isinstance(existing, QApplication):
+        app = existing
+    else:
+        app = QApplication(list(argv) if argv is not None else list(sys.argv))
+    app.setApplicationName(APP_NAME)
+    app.setApplicationDisplayName(APP_NAME)
+    app.setOrganizationName(APP_NAME)
+    app.setStyle("Fusion")
+    app.setPalette(dark_palette())
+    return app
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Start the Lattice Glyph GUI and return the Qt exit code."""
+    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
+    app = create_application(argv)
+    window = MainWindow()
+    connect_shutdown(window)
+    window.show()
+    LOGGER.info("Lattice Glyph window shown")
+    return app.exec()
+
+
+__all__ = ["create_application", "dark_palette", "main"]
diff --git a/lattice_glyph/bridge_actions.py b/lattice_glyph/bridge_actions.py
new file mode 100644
index 0000000..0e6c786
--- /dev/null
+++ b/lattice_glyph/bridge_actions.py
@@ -0,0 +1,96 @@
+"""Bridge work of the Glyph shell, run on a helper thread (§7).
+
+The window never talks to a host on the GUI thread: a slow connection would freeze the
+preview. ``BridgeWorker`` does exactly three things — pull the active document, place a
+render as a layer, or report why neither was possible — and a missing host is the normal
+``failed`` case, reported in the status bar, never an exception.
+"""
+
+from __future__ import annotations
+
+import logging
+
+from PySide6.QtCore import QObject, Signal, Slot
+
+from lattice_core import color
+from lattice_core.bridge import ArtCraftClient, BridgeError
+from lattice_core.types import RGB8, Image
+
+LOGGER = logging.getLogger(__name__)
+
+HOSTS = ("photocraft", "designcraft")
+DEFAULT_HOST = "photocraft"
+DEFAULT_NAME = "Lattice Glyph"
+NOT_RUNNING = "{host} is not running: Lattice Glyph works standalone"
+
+
+class BridgeWorker(QObject):
+    """Pulls documents from a host and pushes renders to it, off the GUI thread."""
+
+    pulled = Signal(object, str)
+    pushed = Signal(int)
+    failed = Signal(str)
+    progress = Signal(str)
+
+    @Slot(str)
+    def pull(self, host: str) -> None:
+        """Read the active document of host and emit it as a float32 image."""
+        self.progress.emit(f"Reading the {host} document…")
+        client = _discover(host)
+        if client is None:
+            self.failed.emit(NOT_RUNNING.format(host=host))
+            return
+        try:
+            image = color.to_float(client.render_document())
+        except (BridgeError, OSError, ValueError) as exc:
+            LOGGER.debug("bridge pull failed", exc_info=True)
+            self.failed.emit(f"{host}: {exc}")
+            return
+        finally:
+            client.disconnect()
+        self.pulled.emit(image, host)
+
+    @Slot(str, object, str)
+    def push(self, host: str, rgb8: RGB8, name: str) -> None:
+        """Place one rendered image in host as a layer and emit the object id."""
+        self.progress.emit(f"Placing the render in {host}…")
+        client = _discover(host)
+        if client is None:
+            self.failed.emit(NOT_RUNNING.format(host=host))
+            return
+        try:
+            object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
+        except (BridgeError, OSError, ValueError) as exc:
+            LOGGER.debug("bridge push failed", exc_info=True)
+            self.failed.emit(f"{host}: {exc}")
+            return
+        finally:
+            client.disconnect()
+        self.pushed.emit(int(object_id))
+
+
+def _discover(host: str) -> ArtCraftClient | None:
+    """Return a live client for host, or None for every way a host can be absent."""
+    if host not in HOSTS:
+        return None
+    try:
+        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
+    except (BridgeError, OSError, ValueError):
+        LOGGER.debug("host discovery failed", exc_info=True)
+        return None
+
+
+def pull_image(host: str = DEFAULT_HOST) -> Image | None:
+    """Synchronously read a host document, returning None when the host is absent."""
+    client = _discover(host)
+    if client is None:
+        return None
+    try:
+        return color.to_float(client.render_document())
+    except (BridgeError, OSError, ValueError):
+        return None
+    finally:
+        client.disconnect()
+
+
+__all__ = ["BridgeWorker", "DEFAULT_HOST", "HOSTS", "NOT_RUNNING", "pull_image"]
diff --git a/lattice_glyph/bridge_controller.py b/lattice_glyph/bridge_controller.py
new file mode 100644
index 0000000..bbbaf8d
--- /dev/null
+++ b/lattice_glyph/bridge_controller.py
@@ -0,0 +1,92 @@
+"""Bridge controller of the Glyph shell: host work on its own thread (§7, E9).
+
+The window never talks to a host on the GUI thread, and a host that is not running is a
+normal answer reported through ``failed``, never an exception. The controller is opt-in:
+without it, the shell is a complete standalone application.
+"""
+
+from __future__ import annotations
+
+import logging
+
+from PySide6.QtCore import QObject, QThread, Signal
+
+from lattice_core import color
+from lattice_core.bridge import ArtCraftClient, BridgeError
+from lattice_core.types import RGB8
+from lattice_glyph.bridge_actions import DEFAULT_HOST, BridgeWorker
+
+LOGGER = logging.getLogger(__name__)
+
+STOP_MS = 5000
+LAYER_NAME = "Lattice Glyph"
+
+
+class BridgeController(QObject):
+    """Owns the bridge thread and re-emits its results in the window's vocabulary."""
+
+    pulled = Signal(object, str)
+    pushed = Signal(int)
+    failed = Signal(str)
+    progress = Signal(str)
+    pull_request = Signal(str)
+    push_request = Signal(str, object, str)
+
+    def __init__(self, parent: QObject | None = None, host: str = DEFAULT_HOST) -> None:
+        """Create the helper thread and its worker, then start it."""
+        super().__init__(parent)
+        self.host = host
+        self.thread: QThread | None = QThread(None)
+        self.worker: BridgeWorker | None = BridgeWorker()
+        worker, thread = self.worker, self.thread
+        worker.moveToThread(thread)
+        thread.finished.connect(worker.deleteLater)
+        self.pull_request.connect(worker.pull)
+        self.push_request.connect(worker.push)
+        worker.pulled.connect(self.pulled)
+        worker.pushed.connect(self.pushed)
+        worker.failed.connect(self.failed)
+        worker.progress.connect(self.progress)
+        thread.start()
+
+    def pull(self) -> None:
+        """Ask the worker to read the active document of the host."""
+        self.pull_request.emit(self.host)
+
+    def push(self, rgb8: RGB8, name: str = LAYER_NAME) -> None:
+        """Ask the worker to place rgb8 in the host as a layer called name."""
+        self.push_request.emit(self.host, rgb8, name)
+
+    def stop(self) -> None:
+        """Stop the helper thread; safe to call more than once.
+
+        The worker is dropped only after its thread has stopped: PySide frees the C++ object
+        with the last Python reference, and a worker freed mid-slot is a crash.
+        """
+        thread = self.thread
+        if thread is None:
+            return
+        thread.quit()
+        if not thread.wait(STOP_MS):
+            LOGGER.warning("the bridge thread did not stop within %d ms", STOP_MS)
+            thread.wait()
+        self.thread = self.worker = None
+
+
+def fetch_image(host: str = DEFAULT_HOST):
+    """Synchronously read a host document, returning None when the host is absent."""
+    try:
+        client = ArtCraftClient.discover(host)  # type: ignore[arg-type]
+    except (BridgeError, OSError, ValueError):
+        return None
+    if client is None:
+        return None
+    try:
+        return color.to_float(client.render_document())
+    except (BridgeError, OSError, ValueError):
+        return None
+    finally:
+        client.disconnect()
+
+
+__all__ = ["BridgeController", "LAYER_NAME", "fetch_image"]
diff --git a/lattice_glyph/cli.py b/lattice_glyph/cli.py
new file mode 100644
index 0000000..61f95f9
--- /dev/null
+++ b/lattice_glyph/cli.py
@@ -0,0 +1,369 @@
+"""Command line of Lattice Glyph: the four verbs of §8 and their exit codes.
+
+``render`` and ``batch`` go through :mod:`lattice_glyph.document`, the module the GUI
+export uses, so their PNG bytes are identical by construction (G9). ``presets`` reads the
+v3 preset tiers and ``bridge`` talks to PhotoCraft or DesignCraft; an absent host is a
+normal answer reported as text, not a traceback (§7). No verb needs a display and this
+module never imports Qt: it only imports the core, whose base install has no PySide6.
+"""
+
+from __future__ import annotations
+
+import argparse
+import json
+import sys
+from pathlib import Path
+from typing import NoReturn
+
+import lattice_core.dither  # noqa: F401  (importing the package registers every algorithm)
+import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
+import lattice_core.renderers  # noqa: F401  (importing the package registers every renderer)
+from lattice_core import color
+from lattice_core.bridge import HOSTS, ArtCraftClient, BridgeError
+from lattice_core.pipeline import PipelineSpec
+from lattice_glyph import presets as preset_tools
+from lattice_glyph.document import (
+    FORMATS,
+    DocumentError,
+    Export,
+    format_of,
+    load_image,
+    render_rgb8,
+    target_path,
+    write_render,
+)
+
+EXIT_OK = 0
+EXIT_USAGE = 1
+EXIT_RENDER = 2
+EXIT_BRIDGE = 3
+DEFAULT_EXTENSIONS = "png,jpg,jpeg,bmp,tif,tiff,webp"
+PROG = "lattice-glyph"
+IMAGE_EXTENSIONS = frozenset(DEFAULT_EXTENSIONS.split(","))
+
+
+class UsageError(Exception):
+    """A command line the application cannot honour: a missing or unreadable preset."""
+
+
+class _Parser(argparse.ArgumentParser):
+    """Argument parser reporting usage errors with exit code 1, not argparse's 2."""
+
+    def error(self, message: str) -> NoReturn:
+        """Print the usage line and exit with the §8 usage code."""
+        self.print_usage(sys.stderr)
+        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")
+
+
+def _note(message: str) -> None:
+    """Print one human-readable line on stderr, leaving stdout to the machine result."""
+    print(message, file=sys.stderr)
+
+
+def _emit(args: argparse.Namespace, payload: dict) -> None:
+    """Print payload as JSON on stdout when --json is set; stdout stays empty otherwise."""
+    if getattr(args, "json", False):
+        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
+
+
+def _spec(preset: str) -> PipelineSpec:
+    """Load a preset file in this app's context, mapping any failure to a usage error."""
+    path = Path(preset)
+    if not path.is_file():
+        raise UsageError(f"preset not found: {path}")
+    try:
+        return preset_tools.spec_of(preset_tools.read_preset(path))
+    except (OSError, ValueError, KeyError) as exc:
+        raise UsageError(f"cannot read preset {path}: {exc}") from None
+
+
+def _failure(args: argparse.Namespace, message: str, code: int) -> int:
+    """Report one failure on stderr and in JSON and return the exit code of its class."""
+    _note(message)
+    _emit(args, {"ok": False, "errors": [message]})
+    return code
+
+
+def _cmd_render(args: argparse.Namespace) -> int:
+    """Render one image with one preset into one file, in the format it names."""
+    try:
+        spec = _spec(args.preset)
+        image = load_image(Path(args.source))
+        fmt = args.format or format_of(args.output)
+        export = write_render(image, spec, args.output, fmt)
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    for warning in export.warnings:
+        _note(f"warning: {warning}")
+    _note(f"wrote {export.path} ({export.fmt}, {export.size} bytes)")
+    _emit(args, _export_payload(export))
+    return EXIT_OK
+
+
+def _export_payload(export: Export) -> dict:
+    """Return the machine-readable description of one written file."""
+    return {"ok": True, "file": str(export.path), "format": export.fmt,
+            "bytes": export.size, "warnings": list(export.warnings), "errors": []}
+
+
+def _extensions(text: str) -> set[str]:
+    """Return the lower-case extensions listed in a comma-separated string."""
+    return {part.strip().lower().lstrip(".") for part in text.split(",") if part.strip()}
+
+
+def _batch_inputs(source: Path, extensions: set[str], recursive: bool) -> list[Path]:
+    """Return the image files of a directory, sorted, filtered by extension."""
+    if not source.is_dir():
+        raise UsageError(f"input directory not found: {source}")
+    found = source.rglob("*") if recursive else source.iterdir()
+    return sorted(
+        path for path in found
+        if path.is_file() and path.suffix.lower().lstrip(".") in extensions
+    )
+
+
+def _destination(target_dir: Path, item: Path, source: Path, fmt: str, recursive: bool) -> Path:
+    """Return where one batch item is written, mirroring the tree when recursive."""
+    relative = item.relative_to(source) if recursive else Path(item.name)
+    suffix = target_path(relative.name, fmt).suffix
+    return target_dir / relative.with_name(relative.stem + suffix)
+
+
+def _cmd_batch(args: argparse.Namespace) -> int:
+    """Render every image of a directory with one preset, keeping the file names."""
+    try:
+        spec = _spec(args.preset)
+        source = Path(args.source)
+        files = _batch_inputs(source, _extensions(args.ext), args.recursive)
+    except UsageError as exc:
+        _note(str(exc))
+        _emit(args, {"ok": False, "files": [], "errors": [str(exc)]})
+        return EXIT_USAGE
+    fmt = args.format or "png"
+    written: list[str] = []
+    errors: list[str] = []
+    for item in files:
+        destination = _destination(Path(args.output), item, source, fmt, args.recursive)
+        try:
+            export = write_render(load_image(item), spec, destination, fmt)
+        except DocumentError as exc:
+            _note(f"{item}: {exc}")
+            errors.append(f"{item}: {exc}")
+            continue
+        _note(f"wrote {export.path}")
+        written.append(str(export.path))
+    _emit(args, {"ok": not errors, "files": written, "errors": errors})
+    return EXIT_OK if not errors else EXIT_RENDER
+
+
+def _cmd_presets_list(args: argparse.Namespace) -> int:
+    """List the presets of the shipped tier and of the user tier."""
+    directories = [Path(entry) for entry in args.directory] or None
+    entries = preset_tools.available(directories)
+    payload = {"presets": [
+        {"name": entry.name, "path": str(entry.path), "read_only": entry.read_only}
+        for entry in entries
+    ]}
+    _emit(args, payload)
+    if not args.json:
+        for entry in entries:
+            tier = "shipped" if entry.read_only else "user"
+            print(f"{entry.name}\t{tier}\t{entry.path}")
+    return EXIT_OK
+
+
+def _cmd_presets_show(args: argparse.Namespace) -> int:
+    """Describe one preset: its renderer, its options, its palette and its pipeline."""
+    try:
+        preset = preset_tools.read_preset(Path(args.name))
+    except (OSError, ValueError, KeyError) as exc:
+        return _failure(args, f"cannot read preset {args.name}: {exc}", EXIT_USAGE)
+    description = preset_tools.describe(preset)
+    _emit(args, description)
+    if not args.json:
+        print(json.dumps(description, indent=2, ensure_ascii=False, sort_keys=True))
+    return EXIT_OK
+
+
+def _cmd_presets_validate(args: argparse.Namespace) -> int:
+    """Validate one preset file, or every preset of the tiers when no path is given."""
+    reports = [preset_tools.validate(Path(args.path))] if args.path \
+        else preset_tools.validate_all()
+    payload = {
+        "ok": all(report.ok for report in reports),
+        "presets": [
+            {"name": report.name, "ok": report.ok, "renderer": report.renderer,
+             "errors": report.errors, "warnings": report.warnings}
+            for report in reports
+        ],
+    }
+    _emit(args, payload)
+    if not args.json:
+        for report in reports:
+            print(f"{report.name}\t{'ok' if report.ok else 'invalid'}\t{report.renderer}")
+            for prose in report.errors + report.warnings:
+                print(f"  {prose}")
+    return EXIT_OK if payload["ok"] else EXIT_USAGE
+
+
+def discover_host(host: str) -> ArtCraftClient | None:
+    """Return a live client for host, or None for any host that is not running (§7)."""
+    try:
+        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
+    except (BridgeError, OSError, ValueError):
+        return None
+
+
+def host_report(hosts: tuple[str, ...] | list[str]) -> list[dict]:
+    """Probe every host and return one {host, connected} record per host."""
+    report: list[dict] = []
+    for host in hosts:
+        client = discover_host(host)
+        if client is not None:
+            client.disconnect()
+        report.append({"host": host, "connected": client is not None})
+    return report
+
+
+def _cmd_bridge_status(args: argparse.Namespace) -> int:
+    """Report the reachability of the ArtCraft hosts, with no host running being normal."""
+    hosts: list[str] = [args.host] if args.host else list(HOSTS)
+    report = host_report(hosts)
+    _emit(args, {"ok": True, "hosts": report})
+    if not args.json:
+        for entry in report:
+            print(f"{entry['host']}: {'connected' if entry['connected'] else 'not running'}")
+    return EXIT_OK
+
+
+def _cmd_bridge_pull(args: argparse.Namespace) -> int:
+    """Render the active document of a host with a preset and write the result."""
+    client = discover_host(args.host)
+    if client is None:
+        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
+    try:
+        image = color.to_float(client.render_document())
+        export = write_render(image, _spec(args.preset), args.output,
+                              args.format or format_of(args.output))
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    except (BridgeError, OSError) as exc:
+        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    _note(f"wrote {export.path} ({export.size} bytes)")
+    _emit(args, _export_payload(export))
+    return EXIT_OK
+
+
+def _cmd_bridge_push(args: argparse.Namespace) -> int:
+    """Render one image with a preset and place it in a host as a layer."""
+    client = discover_host(args.host)
+    if client is None:
+        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
+    try:
+        rgb8 = render_rgb8(load_image(Path(args.source)), _spec(args.preset))
+        object_id = client.place_as_layer(color.to_pil(rgb8), args.name)
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    except (BridgeError, OSError) as exc:
+        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    _note(f"placed object {object_id} in {args.host}")
+    _emit(args, {"ok": True, "host": args.host, "object_id": object_id, "errors": []})
+    return EXIT_OK
+
+
+def _add_render_options(parser: argparse.ArgumentParser, *, output_help: str) -> None:
+    """Add the preset, the output and the JSON flag shared by the render verbs."""
+    parser.add_argument("--preset", required=True, help="preset JSON file")
+    parser.add_argument("--out", dest="output", required=True, help=output_help)
+    parser.add_argument("--format", choices=FORMATS, default=None,
+                        help="png, svg, txt, ansi or html (default: from --out)")
+    parser.add_argument("--json", action="store_true", help="print a JSON result")
+
+
+def _build_parser() -> argparse.ArgumentParser:
+    """Return the argument parser carrying the four verbs of §8."""
+    parser = _Parser(prog=PROG, description="Lattice Glyph command line.")
+    verbs = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
+
+    render = verbs.add_parser("render", help="render one image with one preset")
+    _add_render_options(render, output_help="output file")
+    render.add_argument("--in", dest="source", required=True, help="input image")
+    render.set_defaults(handler=_cmd_render)
+
+    batch = verbs.add_parser("batch", help="render a directory with one preset")
+    _add_render_options(batch, output_help="output directory")
+    batch.add_argument("--in", dest="source", required=True, help="input directory")
+    batch.add_argument("--recursive", action="store_true", help="walk subdirectories")
+    batch.add_argument("--ext", default=DEFAULT_EXTENSIONS, help="input extensions")
+    batch.set_defaults(handler=_cmd_batch)
+
+    presets = verbs.add_parser("presets", help="list, show and validate presets")
+    preset_verbs = presets.add_subparsers(dest="preset_command", required=True,
+                                          parser_class=_Parser)
+    listing = preset_verbs.add_parser("list", help="list the presets of both tiers")
+    listing.add_argument("--dir", dest="directory", action="append", default=[],
+                         help="search directory, repeatable")
+    listing.add_argument("--json", action="store_true", help="print a JSON result")
+    listing.set_defaults(handler=_cmd_presets_list)
+    show = preset_verbs.add_parser("show", help="describe one preset")
+    show.add_argument("name", help="preset file to describe")
+    show.add_argument("--json", action="store_true", help="print a JSON result")
+    show.set_defaults(handler=_cmd_presets_show)
+    check = preset_verbs.add_parser("validate", help="validate one preset or the tiers")
+    check.add_argument("path", nargs="?", default=None, help="preset file to validate")
+    check.add_argument("--json", action="store_true", help="print a JSON result")
+    check.set_defaults(handler=_cmd_presets_validate)
+
+    bridge = verbs.add_parser("bridge", help="talk to PhotoCraft or DesignCraft")
+    bridge_verbs = bridge.add_subparsers(dest="bridge_command", required=True,
+                                         parser_class=_Parser)
+    status = bridge_verbs.add_parser("status", help="report the host state")
+    status.add_argument("host", nargs="?", default=None, choices=HOSTS,
+                        help="host to probe (default: both)")
+    status.add_argument("--json", action="store_true", help="print a JSON result")
+    status.set_defaults(handler=_cmd_bridge_status)
+    pull = bridge_verbs.add_parser("pull", help="render the host document into a file")
+    _add_render_options(pull, output_help="output file")
+    pull.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
+    pull.set_defaults(handler=_cmd_bridge_pull)
+    push = bridge_verbs.add_parser("push", help="place a render in the host as a layer")
+    push.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
+    push.add_argument("--preset", required=True, help="preset JSON file")
+    push.add_argument("--in", dest="source", required=True, help="input image")
+    push.add_argument("--name", default="Lattice Glyph", help="layer or object name")
+    push.add_argument("--json", action="store_true", help="print a JSON result")
+    push.set_defaults(handler=_cmd_bridge_push)
+    return parser
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Run the command line and return its exit code; no traceback ever escapes."""
+    parser = _build_parser()
+    try:
+        args = parser.parse_args(argv)
+    except SystemExit as exc:
+        return int(exc.code or EXIT_OK)
+    try:
+        return int(args.handler(args))
+    except UsageError as exc:
+        _note(str(exc))
+        return EXIT_USAGE
+    except DocumentError as exc:
+        _note(str(exc))
+        return EXIT_RENDER
+    except (BridgeError, OSError) as exc:
+        _note(f"{args.command} failed: {exc}")
+        return EXIT_BRIDGE
+    except Exception as exc:  # noqa: BLE001 - §8 forbids a traceback on stderr
+        _note(f"{args.command} failed: {exc}")
+        return EXIT_RENDER
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/lattice_glyph/document.py b/lattice_glyph/document.py
new file mode 100644
index 0000000..84c7412
--- /dev/null
+++ b/lattice_glyph/document.py
@@ -0,0 +1,210 @@
+"""The single render path of Lattice Glyph: load, render, export bytes (G9, §8, §11).
+
+Every entry point of the application goes through this module. ``render_rgb8`` is
+``lattice_core.pipeline.render`` and nothing else, so the CLI and the GUI cannot drift:
+the GUI export dialog is handed this exact function. SVG and text export need the
+``CellGrid`` the pipeline builds internally (§3); ``grid_bundle`` re-runs the same core
+steps in the same order and never re-implements their maths, and a test pins its frame
+to ``render`` byte for byte.
+
+Promoted effects are raster: they are applied to PNG and not to vector or text output,
+which is reported as a warning instead of being silently dropped.
+"""
+
+from __future__ import annotations
+
+import io
+from dataclasses import dataclass, field
+from pathlib import Path
+
+from PIL import Image as PILImage
+
+import lattice_core.dither  # noqa: F401  (registers every algorithm this path can run)
+import lattice_core.effects  # noqa: F401  (registers every effect a preset may name)
+from lattice_core import color
+from lattice_core import pipeline as _pipeline
+from lattice_core.cell import CellGrid, CellRenderer, RenderStyle, get_renderer
+from lattice_core.pipeline import PipelineSpec, resolve_palette
+from lattice_core.registry import get_algorithm, resolve_params
+from lattice_core.svg import render_svg
+from lattice_core.textout import render_text
+from lattice_core.types import RGB8, Image, Palette
+
+FORMATS: tuple[str, ...] = ("png", "svg", "txt", "ansi", "html")
+TEXT_FORMATS: tuple[str, ...] = ("txt", "ansi", "html")
+SUFFIXES: dict[str, str] = {
+    "png": ".png",
+    "svg": ".svg",
+    "txt": ".txt",
+    "ansi": ".ansi",
+    "html": ".html",
+}
+RASTER_ONLY = "post effects are raster: they are not applied to {fmt} export"
+
+
+class DocumentError(Exception):
+    """A typed failure of the document path: unreadable source, or an impossible export."""
+
+
+class GridError(DocumentError):
+    """An export format that needs a CellGrid, asked for a render that has none."""
+
+
+@dataclass(frozen=True)
+class GridBundle:
+    """The §3 grid of one spec, with the palette, renderer and style that produced it."""
+
+    grid: CellGrid
+    palette: Palette
+    renderer: CellRenderer
+    style: RenderStyle
+
+
+@dataclass(frozen=True)
+class Export:
+    """One written file: where it went, in which format, its size and its warnings."""
+
+    path: Path
+    fmt: str
+    size: int
+    warnings: list[str] = field(default_factory=list)
+
+
+def load_image(path: str | Path) -> Image:
+    """Load path as a float32 RGB image, raising DocumentError when it is unusable."""
+    target = Path(path)
+    if not target.is_file():
+        raise DocumentError(f"image not found: {target}")
+    try:
+        with PILImage.open(target) as handle:
+            return color.to_float(handle)
+    except (OSError, ValueError) as exc:
+        raise DocumentError(f"cannot read image {target}: {exc}") from None
+
+
+def render_rgb8(image: Image, spec: PipelineSpec) -> RGB8:
+    """Render image through the core pipeline, raising DocumentError on any failure."""
+    try:
+        return _pipeline.render(image, spec)
+    except Exception as exc:  # noqa: BLE001 - every pipeline failure is a render error (§8)
+        raise DocumentError(f"render failed: {exc}") from None
+
+
+def grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
+    """Return the §3 grid of spec, built with the core steps in the normative order.
+
+    Steps 1 to 5 come from ``pipeline._prepare``, the geometry from step 6, the cell
+    averages, palette, dither, sub-points and samples from the helpers the pipeline
+    itself calls; nothing is re-implemented here.
+    """
+    if spec.algorithm_id is None or spec.palette is None:
+        raise GridError(
+            "continuous mode has no cell grid: export png instead of svg, txt, ansi or html"
+        )
+    try:
+        return _grid_bundle(image, spec)
+    except (KeyError, ValueError) as exc:
+        raise DocumentError(f"cannot build the cell grid: {exc}") from None
+
+
+def _grid_bundle(image: Image, spec: PipelineSpec) -> GridBundle:
+    """Build the §3 grid of spec; the caller turns a lookup failure into a DocumentError."""
+    work, _ = _pipeline._prepare(image, spec, None)
+    renderer = get_renderer(spec.renderer)
+    style = RenderStyle(options=dict(spec.renderer_style))
+    cell_w, cell_h = _pipeline._cell_geometry(renderer, spec.pixel_size)
+    padded = _pipeline._pad_to_cells(work, cell_w, cell_h)
+    cells = _pipeline._to_cells(padded, cell_w, cell_h)
+    palette = resolve_palette(spec.palette, cells)
+    info = get_algorithm(spec.algorithm_id)
+    params = resolve_params(info.params, spec.algorithm_params)
+    params[_pipeline.RESERVED_METRIC] = color.metric_code(spec.color_metric)
+    subgrid = (int(renderer.subgrid()[0]), int(renderer.subgrid()[1]))
+    subindex = None
+    if subgrid != (1, 1):
+        subindex = _pipeline._subindex(
+            padded, palette, info.fn, params, (cell_w, cell_h), subgrid
+        )
+    grid = _pipeline._make_grid(
+        cells,
+        _pipeline._run(info.fn, params, cells, palette),
+        cell_w,
+        cell_h,
+        palette,
+        samples=_pipeline._derive_samples(renderer, padded, cells, (cell_w, cell_h), subgrid),
+        subindex=subindex,
+    )
+    return GridBundle(grid=grid, palette=palette, renderer=renderer, style=style)
+
+
+def png_bytes(rgb8: RGB8) -> bytes:
+    """Return rgb8 encoded as a PNG file byte for byte as the GUI export writes it."""
+    buffer = io.BytesIO()
+    color.to_pil(rgb8).save(buffer, format="PNG")
+    return buffer.getvalue()
+
+
+def export_bytes(image: Image, spec: PipelineSpec, fmt: str = "png") -> tuple[bytes, list[str]]:
+    """Return the encoded output of spec in fmt, with the warnings of that export."""
+    if fmt not in FORMATS:
+        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
+    if fmt == "png":
+        return png_bytes(render_rgb8(image, spec)), []
+    bundle = grid_bundle(image, spec)
+    warnings: list[str] = []
+    if spec.post_effects:
+        warnings.append(RASTER_ONLY.format(fmt=fmt))
+    if fmt == "svg":
+        document, svg_warnings = render_svg(
+            bundle.grid, bundle.palette, bundle.renderer, bundle.style
+        )
+        return document.encode("utf-8"), warnings + list(svg_warnings)
+    text = render_text(bundle.grid, bundle.palette, bundle.renderer, bundle.style, fmt=fmt)
+    return text.encode("utf-8"), warnings
+
+
+def target_path(path: str | Path, fmt: str) -> Path:
+    """Return path with fmt's suffix appended when it carries none of its own."""
+    target = Path(path)
+    if target.suffix:
+        return target
+    if fmt not in SUFFIXES:
+        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
+    return target.with_name(target.name + SUFFIXES[fmt])
+
+
+def write_render(image: Image, spec: PipelineSpec, path: str | Path, fmt: str = "png") -> Export:
+    """Render spec and write it to path in fmt, creating the parent directories."""
+    payload, warnings = export_bytes(image, spec, fmt)
+    target = target_path(path, fmt)
+    try:
+        target.parent.mkdir(parents=True, exist_ok=True)
+        target.write_bytes(payload)
+    except OSError as exc:
+        raise DocumentError(f"cannot write {target}: {exc}") from None
+    return Export(path=target, fmt=fmt, size=len(payload), warnings=warnings)
+
+
+def format_of(path: str | Path) -> str:
+    """Return the export format named by path's suffix, png when the suffix is unknown."""
+    suffix = Path(path).suffix.lower().lstrip(".")
+    return suffix if suffix in FORMATS else "png"
+
+
+__all__ = [
+    "DocumentError",
+    "Export",
+    "FORMATS",
+    "GridBundle",
+    "GridError",
+    "SUFFIXES",
+    "TEXT_FORMATS",
+    "export_bytes",
+    "format_of",
+    "grid_bundle",
+    "load_image",
+    "png_bytes",
+    "render_rgb8",
+    "target_path",
+    "write_render",
+]
diff --git a/lattice_glyph/export_actions.py b/lattice_glyph/export_actions.py
new file mode 100644
index 0000000..2850755
--- /dev/null
+++ b/lattice_glyph/export_actions.py
@@ -0,0 +1,96 @@
+"""Export controller of the shell: full-resolution export, text export, preset saving.
+
+The window owns one instance and its toolbar calls it. Every render goes through
+:mod:`lattice_glyph.rendering`, which calls the same two functions the CLI calls
+(``render_rgb8`` and ``write_render``), so the GUI cannot drift from the CLI (G9).
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+from typing import TYPE_CHECKING
+
+from PySide6.QtWidgets import QFileDialog
+
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import RGB8, Image
+from lattice_core.ui import ExportDialog
+from lattice_glyph import presets as preset_tools
+from lattice_glyph.document import DocumentError, format_of
+from lattice_glyph.rendering import export_to, render_full
+
+if TYPE_CHECKING:
+    from lattice_glyph.window import MainWindow
+
+TEXT_FILTER = "Text export (*.txt *.ansi *.html);;All files (*)"
+NO_SOURCE = "Load an image before rendering."
+DEFAULT_TEXT_NAME = "glyph.txt"
+
+
+class ExportController:
+    """Export and preset-saving actions of one window."""
+
+    def __init__(self, window: MainWindow) -> None:
+        """Bind the controller to the window that owns the source, the spec and settings."""
+        self.window = window
+
+    def render_full(self, image: Image, spec: PipelineSpec) -> RGB8:
+        """Render spec on image through the function the CLI calls (G9)."""
+        return render_full(image, spec)
+
+    def dialog(self) -> list[Path]:
+        """Open the shared full-resolution export dialog and return the files written."""
+        window = self.window
+        if window.source is None:
+            window.report(NO_SOURCE)
+            return []
+        source = window.source
+        dialog = ExportDialog(source, window.spec, window,
+                              render_full=lambda spec: render_full(source, spec),
+                              settings=window.settings())
+        dialog.exec()
+        if dialog.written:
+            window.status(f"Exported {dialog.written[0].name}")
+        return list(dialog.written)
+
+    def to(self, path: str | Path) -> dict:
+        """Write the current render to path in the format the path names."""
+        window = self.window
+        return export_to(window.source, window.spec, path, window, window.settings())
+
+    def text(self) -> None:
+        """Ask for a text-export path and write txt, ansi or html from the layout."""
+        window = self.window
+        if window.source is None:
+            window.report(NO_SOURCE)
+            return
+        path, _ = QFileDialog.getSaveFileName(
+            window, "Export text", str(Path.home() / DEFAULT_TEXT_NAME), TEXT_FILTER
+        )
+        if not path:
+            return
+        try:
+            result = self.to(Path(path).with_suffix(f".{format_of(path)}"))
+        except DocumentError as exc:
+            window.report(str(exc))
+            return
+        for warning in result["warnings"]:
+            window.status(warning)
+        window.status(f"Exported {Path(result['file']).name}")
+
+    def save_preset(self, path: str | Path) -> Path | None:
+        """Write the current spec as a v3 preset and remember it as the applied one."""
+        window = self.window
+        try:
+            target = preset_tools.save_spec(path, window.spec)
+        except (OSError, ValueError) as exc:
+            window.report(f"Cannot write {path}: {exc}")
+            return None
+        window.preset_panel.refresh()
+        window.preset_panel.select_name(target.name)
+        window.indicator.set_preset(target.name)
+        window.status(f"Saved {target.name}")
+        return target
+
+
+__all__ = ["ExportController", "NO_SOURCE", "TEXT_FILTER"]
diff --git a/lattice_glyph/options.py b/lattice_glyph/options.py
new file mode 100644
index 0000000..6239463
--- /dev/null
+++ b/lattice_glyph/options.py
@@ -0,0 +1,146 @@
+"""Renderer option metadata of Lattice Glyph: what the panel shows and what it writes.
+
+The tables below mirror the option names and defaults documented in §9 and §10 for the
+renderers the core registers. They are the *view* side only: ``clean()`` writes a style
+dict the renderers accept, and the panel drops every option still at its default so a
+preset stays minimal. ``defaults_for()`` must render exactly like ``{}`` — a test pins it.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Mapping
+from dataclasses import dataclass
+from typing import Literal
+
+Kind = Literal["text", "colour", "float", "int", "bool", "choice"]
+
+TRANSPARENT = "transparent"
+RAMP_HINT = "darkest character first"
+COLOUR_HINT = "#rrggbb or transparent"
+
+
+@dataclass(frozen=True)
+class OptionSpec:
+    """One renderer option: its style key, its widget kind, its default and its bounds."""
+
+    key: str
+    label: str
+    kind: Kind
+    default: object = ""
+    choices: tuple[str, ...] = ()
+    minimum: float | None = None
+    maximum: float | None = None
+    step: float = 1.0
+    nullable: bool = False
+    hint: str = ""
+
+
+_RAMP = (
+    OptionSpec("ramp", "Ramp", "text", "@%#*+=-:. ", hint=RAMP_HINT),
+    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
+    OptionSpec("fg", "Foreground", "colour", "#000000", hint=COLOUR_HINT),
+    OptionSpec("bg", "Background", "colour", "#ffffff", hint=COLOUR_HINT),
+    OptionSpec(
+        "mode", "Mode", "choice", "mono",
+        choices=("mono", "fg_colour", "bg_colour", "palette"),
+        hint="palette = each glyph takes its cell colour",
+    ),
+    OptionSpec("offset", "Offset", "float", 0.0, minimum=-1.0, maximum=1.0, step=0.05),
+    OptionSpec("invert", "Invert", "bool", False),
+)
+
+_SHAPE = (
+    OptionSpec("alphabet", "Alphabet", "text", "", nullable=True,
+               hint="empty = every printable ASCII character"),
+    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
+    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
+    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
+    OptionSpec("normalise", "Normalise by the alphabet maximum", "bool", True),
+)
+
+_BITMASK = (
+    OptionSpec("threshold", "Threshold", "float", 0.5, minimum=0.0, maximum=1.0, step=0.05),
+    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
+    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
+)
+
+_TEXT = (
+    OptionSpec(
+        "text", "Paragraph", "text",
+        "Lattice renders a paragraph in a real font, one glyph at a time.",
+    ),
+    OptionSpec("font", "Font file", "text", "", nullable=True, hint="empty = bundled font"),
+    OptionSpec("size", "Point size", "int", 0, minimum=0, maximum=512, nullable=True,
+               hint="0 = fitted to the cells"),
+    OptionSpec("line_distance", "Line distance", "float", 1.2, minimum=0.5, maximum=3.0,
+               step=0.05),
+    OptionSpec("kerning", "Kerning", "float", 1.0, minimum=0.0, maximum=2.0, step=0.05),
+    OptionSpec("size_mode", "Size", "choice", "variable", choices=("fixed", "variable")),
+    OptionSpec("weight_mode", "Weight", "choice", "variable", choices=("fixed", "variable")),
+    OptionSpec("fg", "Foreground", "colour", "#000000", hint="#rrggbb"),
+    OptionSpec("bg", "Background", "colour", "#ffffff", hint="#rrggbb"),
+    OptionSpec("seed", "Seed", "int", 0, minimum=0, maximum=9999),
+)
+
+OPTIONS: dict[str, tuple[OptionSpec, ...]] = {
+    "pixel": (),
+    "glyph_ramp": _RAMP,
+    "glyph_shape": _SHAPE,
+    "braille": _BITMASK,
+    "sextant": _BITMASK,
+    "quadrant": _BITMASK,
+    "half_block": _BITMASK,
+    "text": _TEXT,
+}
+
+
+def specs_for(renderer: str) -> tuple[OptionSpec, ...]:
+    """Return the options of renderer, or no option for a renderer this table does not name."""
+    return OPTIONS.get(renderer, ())
+
+
+def defaults_for(renderer: str) -> dict:
+    """Return every option of renderer at its declared default, as a probe of the table."""
+    resolved: dict = {}
+    for spec in specs_for(renderer):
+        value = _coerce(spec, spec.default)
+        if value is not None:
+            resolved[spec.key] = value
+    return resolved
+
+
+def clean(renderer: str, values: Mapping) -> dict:
+    """Return the style dict of renderer: known keys only, coerced, defaults dropped."""
+    cleaned: dict = {}
+    for spec in specs_for(renderer):
+        if spec.key not in values:
+            continue
+        value = _coerce(spec, values[spec.key])
+        if value is None or value == spec.default:
+            continue
+        cleaned[spec.key] = value
+    return cleaned
+
+
+def _coerce(spec: OptionSpec, value: object) -> object | None:
+    """Coerce one option to its declared type, or return None when it is unset.
+
+    A text option is kept verbatim: a ramp's trailing space is a real glyph, and stripping
+    it would silently change what the renderer draws.
+    """
+    if spec.kind == "bool":
+        return bool(value)
+    if spec.kind == "choice":
+        if value not in spec.choices:
+            raise ValueError(f"{spec.key} must be one of {spec.choices}, got {value!r}")
+        return str(value)
+    if spec.kind == "float":
+        return float(value)  # type: ignore[arg-type]
+    if spec.kind == "int":
+        number = int(value)  # type: ignore[arg-type]
+        return None if spec.nullable and number <= 0 else number
+    text = "" if value is None else str(value)
+    return None if spec.nullable and not text.strip() else text
+
+
+__all__ = ["OptionSpec", "OPTIONS", "clean", "defaults_for", "specs_for"]
diff --git a/lattice_glyph/palette_panel.py b/lattice_glyph/palette_panel.py
new file mode 100644
index 0000000..1a5b8a8
--- /dev/null
+++ b/lattice_glyph/palette_panel.py
@@ -0,0 +1,166 @@
+"""Palette panel: a built-in palette, custom hex colours, or a palette extracted from the image.
+
+Every source maps onto one ``PaletteSpec`` of §3, so the render path never carries a table
+of its own. Library palettes are offered as a starting point for the custom list, which is
+what a ``custom`` source actually renders.
+"""
+
+from __future__ import annotations
+
+from PySide6.QtCore import Signal
+from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QSpinBox, QWidget
+
+from lattice_core.palettes.builtin import builtin_names
+from lattice_core.palettes.io import from_hex_text, hex_list
+from lattice_core.palettes.library import get_library, library_names
+from lattice_core.pipeline import PaletteSpec
+
+BUILTIN_SOURCE = "builtin"
+CUSTOM_SOURCE = "custom"
+EXTRACTED_SOURCE = "extracted"
+PALETTE_KINDS = (
+    (BUILTIN_SOURCE, "Built-in"),
+    (CUSTOM_SOURCE, "Custom colours"),
+    (EXTRACTED_SOURCE, "Extracted from image"),
+)
+EXTRACT_METHODS = ("kmeans", "median_cut")
+MIN_K, MAX_K = 2, 32
+COLOR_HINT = "#000000 #ffffff"
+
+
+class PalettePanel(QWidget):
+    """Palette source: built-in, custom hex colours, or extraction from the loaded image."""
+
+    changed = Signal()
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Build the kind selector, the name list, the hex field and the extraction row."""
+        super().__init__(parent)
+        self.setObjectName("palette_panel")
+        self._loading = False
+        self.kind = QComboBox(self)
+        self.kind.setObjectName("palette_kind")
+        for key, label in PALETTE_KINDS:
+            self.kind.addItem(label, key)
+        self.names = QComboBox(self)
+        self.names.setObjectName("palette_name")
+        for name in builtin_names():
+            self.names.addItem(name, name)
+        self.library = QComboBox(self)
+        self.library.setObjectName("palette_library")
+        self.library.addItem("Load a library palette…", "")
+        for name in library_names():
+            self.library.addItem(name, name)
+        self.colors = QLineEdit(self)
+        self.colors.setObjectName("palette_colors")
+        self.colors.setPlaceholderText(COLOR_HINT)
+        self.extract_k = QSpinBox(self)
+        self.extract_k.setObjectName("palette_extract_k")
+        self.extract_k.setRange(MIN_K, MAX_K)
+        self.extract_k.setValue(8)
+        self.method = QComboBox(self)
+        self.method.setObjectName("palette_method")
+        for name in EXTRACT_METHODS:
+            self.method.addItem(name, name)
+        form = QFormLayout(self)
+        form.setContentsMargins(8, 8, 8, 8)
+        form.addRow("Source", self.kind)
+        form.addRow("Palette", self.names)
+        form.addRow("Library", self.library)
+        form.addRow("Colours", self.colors)
+        form.addRow("Colours to extract", self.extract_k)
+        form.addRow("Method", self.method)
+        self.kind.currentIndexChanged.connect(self._on_kind)
+        self.names.currentIndexChanged.connect(self._announce)
+        self.library.activated.connect(self._on_library)
+        self.colors.textChanged.connect(self._announce)
+        self.extract_k.valueChanged.connect(self._announce)
+        self.method.currentIndexChanged.connect(self._announce)
+        self._sync_enabled()
+
+    def source(self) -> str:
+        """Return the palette source currently selected."""
+        return str(self.kind.currentData())
+
+    def spec(self) -> PaletteSpec:
+        """Return the PaletteSpec the current widgets describe."""
+        source = self.source()
+        if source == CUSTOM_SOURCE:
+            return PaletteSpec(source=CUSTOM_SOURCE, colors=_colours(self.colors.text()))
+        if source == EXTRACTED_SOURCE:
+            return PaletteSpec(
+                source=EXTRACTED_SOURCE,
+                extract_k=self.extract_k.value(),
+                extract_method=str(self.method.currentData()),
+            )
+        return PaletteSpec(source=BUILTIN_SOURCE, name=str(self.names.currentData() or "bw"))
+
+    def set_palette(self, spec: PaletteSpec) -> None:
+        """Show spec in the widgets without announcing a change."""
+        self._loading = True
+        try:
+            self.kind.setCurrentIndex(max(0, self.kind.findData(spec.source)))
+            self.names.setCurrentIndex(max(0, self.names.findData(spec.name)))
+            self.colors.setText(" ".join(spec.colors))
+            self.extract_k.setValue(int(spec.extract_k))
+            self.method.setCurrentIndex(max(0, self.method.findData(spec.extract_method)))
+            self._sync_enabled()
+        finally:
+            self._loading = False
+
+    def valid_colours(self) -> bool:
+        """Return True when the custom colour field parses as a palette, or is not in use."""
+        if self.source() != CUSTOM_SOURCE:
+            return True
+        try:
+            _colours(self.colors.text())
+            from_hex_text(self.colors.text())
+        except ValueError:
+            return False
+        return True
+
+    def _on_kind(self) -> None:
+        """Enable the widgets the new source reads, then announce the change."""
+        self._sync_enabled()
+        self._announce()
+
+    def _on_library(self, _index: int) -> None:
+        """Copy a library palette into the custom colour list, switching to that source."""
+        name = str(self.library.currentData() or "")
+        if not name:
+            return
+        try:
+            colours = " ".join(hex_list(get_library(name)))
+        except KeyError:
+            return
+        self._loading = True
+        try:
+            self.colors.setText(colours)
+            self.kind.setCurrentIndex(max(0, self.kind.findData(CUSTOM_SOURCE)))
+            self._sync_enabled()
+        finally:
+            self._loading = False
+        self._announce()
+
+    def _sync_enabled(self) -> None:
+        """Enable only the widgets the selected source actually reads."""
+        source = self.source()
+        self.names.setEnabled(source == BUILTIN_SOURCE)
+        self.library.setEnabled(True)
+        self.colors.setEnabled(source == CUSTOM_SOURCE)
+        self.extract_k.setEnabled(source == EXTRACTED_SOURCE)
+        self.method.setEnabled(source == EXTRACTED_SOURCE)
+
+    def _announce(self) -> None:
+        """Announce a user change, unless the panel is being loaded."""
+        if not self._loading:
+            self.changed.emit()
+
+
+def _colours(text: str) -> list[str]:
+    """Return the hex tokens of a whitespace-separated list, each with one leading '#'."""
+    tokens = [token.strip() for token in text.replace(",", " ").split()]
+    return [token if token.startswith("#") else f"#{token}" for token in tokens if token]
+
+
+__all__ = ["PALETTE_KINDS", "PalettePanel"]
diff --git a/lattice_glyph/preset_panel.py b/lattice_glyph/preset_panel.py
new file mode 100644
index 0000000..119de38
--- /dev/null
+++ b/lattice_glyph/preset_panel.py
@@ -0,0 +1,131 @@
+"""Preset panel: the shipped and user tiers, with load, save and refresh.
+
+The list never renders anything: it reads v3 presets in this app's context and hands the
+window a ``PipelineSpec``. Saving is asked from the window, which owns the spec; the panel
+only offers a path in the user tier.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+from PySide6.QtCore import Qt, Signal
+from PySide6.QtWidgets import (
+    QFileDialog,
+    QHBoxLayout,
+    QLabel,
+    QListWidget,
+    QListWidgetItem,
+    QPushButton,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_glyph import presets as preset_tools
+
+PRESET_FILTER = "Presets (*.json);;All files (*)"
+DEFAULT_NAME = "preset.json"
+READ_ONLY_SUFFIX = "  (read-only)"
+EMPTY_HINT = "No preset found in the shipped or user tier."
+TIER_HINT = "Saved presets go to the user tier; shipped ones are read-only."
+NO_SELECTION = "Select a preset first."
+
+
+class PresetPanel(QWidget):
+    """Preset list of both tiers, with load, save and refresh."""
+
+    loaded = Signal(object)
+    save_requested = Signal(str)
+    failed = Signal(str)
+
+    def __init__(self, directories: tuple[Path, ...] | None = None,
+                 parent: QWidget | None = None) -> None:
+        """Build the list and its three buttons, then read the tiers."""
+        super().__init__(parent)
+        self.setObjectName("preset_panel")
+        self._directories = directories
+        self.list = QListWidget(self)
+        self.list.setObjectName("preset_list")
+        self.hint = QLabel("", self)
+        self.hint.setObjectName("preset_hint")
+        self.hint.setWordWrap(True)
+        row = QHBoxLayout()
+        self.load_button = QPushButton("Load", self)
+        self.load_button.setObjectName("preset_load")
+        self.save_button = QPushButton("Save…", self)
+        self.save_button.setObjectName("preset_save")
+        self.refresh_button = QPushButton("Refresh", self)
+        self.refresh_button.setObjectName("preset_refresh")
+        for button in (self.load_button, self.save_button, self.refresh_button):
+            row.addWidget(button)
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(8, 8, 8, 8)
+        layout.addWidget(QLabel("Presets", self))
+        layout.addWidget(self.list, 1)
+        layout.addWidget(self.hint)
+        layout.addLayout(row)
+        self.list.itemActivated.connect(lambda _item: self.load_selected())
+        self.load_button.clicked.connect(self.load_selected)
+        self.save_button.clicked.connect(self._ask_path)
+        self.refresh_button.clicked.connect(self.refresh)
+        self._entries: list[preset_tools.PresetEntry] = []
+        self.refresh()
+
+    def refresh(self) -> None:
+        """Reload the preset tiers into the list, shipped entries marked read-only."""
+        self._entries = preset_tools.available(self._directories)
+        self.list.clear()
+        for entry in self._entries:
+            label = entry.name + (READ_ONLY_SUFFIX if entry.read_only else "")
+            item = QListWidgetItem(label)
+            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
+            self.list.addItem(item)
+        self.hint.setText(TIER_HINT if self._entries else EMPTY_HINT)
+
+    def entries(self) -> list[preset_tools.PresetEntry]:
+        """Return the entries currently listed."""
+        return list(self._entries)
+
+    def user_dir(self) -> Path:
+        """Return the directory a new preset is offered in: the user tier."""
+        return self._directories[-1] if self._directories else preset_tools.user_preset_dir()
+
+    def selected_path(self) -> Path | None:
+        """Return the path of the selected entry, or None when nothing is selected."""
+        item = self.list.currentItem()
+        if item is None:
+            return None
+        data = item.data(Qt.ItemDataRole.UserRole)
+        return None if data is None else Path(str(data))
+
+    def select_name(self, name: str) -> bool:
+        """Select the listed preset called name; return True when it was found."""
+        for row in range(self.list.count()):
+            item = self.list.item(row)
+            if item is not None and Path(str(item.data(Qt.ItemDataRole.UserRole))).name == name:
+                self.list.setCurrentItem(item)
+                return True
+        return False
+
+    def load_selected(self) -> None:
+        """Read the selected preset and emit its spec, or report why it cannot be read."""
+        path = self.selected_path()
+        if path is None:
+            self.failed.emit(NO_SELECTION)
+            return
+        try:
+            preset = preset_tools.read_preset(path)
+            self.loaded.emit(preset_tools.spec_of(preset))
+        except (OSError, ValueError, KeyError) as exc:
+            self.failed.emit(f"Cannot read {path.name}: {exc}")
+
+    def _ask_path(self) -> None:
+        """Ask for a path in the user tier and emit it for the window to write."""
+        target, _ = QFileDialog.getSaveFileName(
+            self, "Save preset", str(self.user_dir() / DEFAULT_NAME), PRESET_FILTER
+        )
+        if target:
+            self.save_requested.emit(target)
+
+
+__all__ = ["DEFAULT_NAME", "PresetPanel"]
diff --git a/lattice_glyph/presets.py b/lattice_glyph/presets.py
new file mode 100644
index 0000000..209a061
--- /dev/null
+++ b/lattice_glyph/presets.py
@@ -0,0 +1,229 @@
+"""Presets of Lattice Glyph: the shipped tier, the user tier, and the app default spec.
+
+Presets are v3 documents (``lattice_core.preset``) read in the ``glyph`` app context, so a
+preset that names no renderer falls back on ``glyph_ramp`` and a preset naming a renderer
+this build does not ship is reported as a warning instead of raising. The user tier lives
+under the platform app-data directory of this application, never in the Dither one (§7).
+"""
+
+from __future__ import annotations
+
+import os
+import sys
+from collections.abc import Sequence
+from dataclasses import dataclass
+from pathlib import Path
+
+from lattice_core.pipeline import PaletteSpec, PipelineSpec
+from lattice_core.preset import (
+    Preset,
+    from_pipeline_spec,
+    load_preset,
+    to_json,
+    to_pipeline_spec,
+)
+from lattice_core.preset import from_json as preset_from_json
+from lattice_core.presets import list_presets
+from lattice_core.renderers import list_renderers
+
+APP_CONTEXT = "glyph"
+APP_DIR_NAME = "LatticeGlyph"
+PRESET_DIR_NAME = "presets"
+SHIPPED_PRESET_DIR = Path(__file__).resolve().parent / PRESET_DIR_NAME
+DEFAULT_RENDERER = "glyph_ramp"
+DEFAULT_PIXEL_SIZE = 8
+DEFAULT_PALETTE = "gameboy"
+DEFAULT_RAMP = "@%#*+=-:. "
+
+
+@dataclass(frozen=True)
+class PresetEntry:
+    """One preset file found in a search directory."""
+
+    name: str
+    path: Path
+    read_only: bool
+
+
+@dataclass(frozen=True)
+class PresetReport:
+    """The outcome of validating one preset: its entry, its problems and its warnings."""
+
+    name: str
+    ok: bool
+    errors: list[str]
+    warnings: list[str]
+    renderer: str = ""
+
+
+def app_data_dir() -> Path:
+    """Return this application's data directory: %LOCALAPPDATA% on Windows, XDG elsewhere."""
+    if os.name == "nt":
+        value = os.environ.get("LOCALAPPDATA")
+        root = Path(value) if value else Path.home() / "AppData" / "Local"
+    elif sys.platform == "darwin":
+        root = Path.home() / "Library" / "Application Support"
+    else:
+        value = os.environ.get("XDG_DATA_HOME")
+        root = Path(value) if value else Path.home() / ".local" / "share"
+    return root / APP_DIR_NAME
+
+
+def user_preset_dir() -> Path:
+    """Return the user preset directory of this app, without creating it."""
+    return app_data_dir() / PRESET_DIR_NAME
+
+
+def search_dirs() -> tuple[Path, Path]:
+    """Return the preset search order: the shipped tier first, the user tier second."""
+    return (SHIPPED_PRESET_DIR, user_preset_dir())
+
+
+def available(directories: Sequence[Path] | None = None) -> list[PresetEntry]:
+    """Return every preset of the search directories, a user file winning a name tie."""
+    dirs = tuple(directories) if directories is not None else search_dirs()
+    entries: list[PresetEntry] = []
+    for path in list_presets(dirs):
+        entries.append(PresetEntry(path.name, path, _is_read_only(path, dirs)))
+    return entries
+
+
+def _is_read_only(path: Path, dirs: tuple[Path, ...]) -> bool:
+    """Return True when path belongs to every directory but the last (the user tier)."""
+    try:
+        resolved = path.resolve()
+    except OSError:
+        return True
+    return any(resolved.is_relative_to(directory.resolve()) for directory in dirs[:-1])
+
+
+def default_spec() -> PipelineSpec:
+    """Return the pipeline of a fresh Glyph document: glyph ramp, gameboy, 8 px cells."""
+    spec = PipelineSpec(pixel_size=DEFAULT_PIXEL_SIZE, renderer=DEFAULT_RENDERER)
+    spec.renderer_style = {"ramp": DEFAULT_RAMP}
+    spec.palette = PaletteSpec(source="builtin", name=DEFAULT_PALETTE)
+    return spec
+
+
+def default_preset() -> Preset:
+    """Return the v3 preset of a fresh document, tagged with this application's context."""
+    return to_preset(default_spec())
+
+
+def to_preset(spec: PipelineSpec, name: str = "") -> Preset:
+    """Return the v3 preset of spec, its renderer kept, tagged ``app: glyph``."""
+    preset = from_pipeline_spec(spec)
+    preset.app = APP_CONTEXT
+    if name:
+        preset.meta["name"] = name
+    return preset
+
+
+def spec_of(preset: Preset) -> PipelineSpec:
+    """Return the PipelineSpec of a parsed preset, its renderer and style included."""
+    return to_pipeline_spec(preset)
+
+
+def read_preset(path: str | Path) -> Preset:
+    """Read and parse one preset in this application's context."""
+    return load_preset(path, app=APP_CONTEXT)
+
+
+def read_text(text: str) -> Preset:
+    """Parse one preset document in this application's context."""
+    return preset_from_json(text, app=APP_CONTEXT)
+
+
+def spec_from_text(text: str) -> PipelineSpec:
+    """Parse a preset document straight into its pipeline spec."""
+    return spec_of(read_text(text))
+
+
+def describe(preset: Preset) -> dict:
+    """Return a JSON-serialisable summary of a preset, without rendering it."""
+    style = dict(preset.renderer.get("style", {}))
+    palette = preset.palette or {}
+    pipeline = preset.pipeline
+    return {
+        "name": preset.meta.get("name", ""),
+        "app": preset.app,
+        "renderer": preset.renderer.get("name", ""),
+        "options": style,
+        "palette": {
+            "source": palette.get("source", ""),
+            "name": palette.get("name", ""),
+            "colors": list(palette.get("colors", [])),
+            "n_colors": (palette.get("extract") or {}).get("n_colors"),
+        },
+        "algorithm": pipeline.get("algorithm"),
+        "pixel_size": pipeline.get("pixel_size"),
+        "color_metric": pipeline.get("color_metric"),
+        "seed": preset.seed,
+        "effects": [entry.get("name", "") for entry in preset.effects],
+    }
+
+
+def validate(path: str | Path) -> PresetReport:
+    """Parse one preset and report every problem instead of raising it."""
+    name = Path(path).name
+    errors: list[str] = []
+    warnings: list[str] = []
+    renderer = ""
+    try:
+        preset = read_preset(path)
+        spec = spec_of(preset)
+    except (OSError, ValueError, KeyError) as exc:
+        return PresetReport(name, False, [str(exc)], [])
+    renderer = spec.renderer
+    if renderer not in list_renderers():
+        errors.append(f"renderer {renderer!r} is not registered in this build")
+    if spec.algorithm_id is None and spec.palette is not None:
+        errors.append("continuous mode needs both algorithm and palette null")
+    if spec.palette is None and spec.algorithm_id is not None:
+        errors.append("continuous mode needs both algorithm and palette null")
+    warnings.extend(str(entry) for entry in preset.warnings)
+    return PresetReport(name, not errors, errors, warnings, renderer)
+
+
+def validate_all(directories: Sequence[Path] | None = None) -> list[PresetReport]:
+    """Validate every preset of the search directories, shipped tier first."""
+    return [validate(entry.path) for entry in available(directories)]
+
+
+def save_preset(path: str | Path, preset: Preset) -> Path:
+    """Write preset as UTF-8 v3 JSON, creating the parent directories, and return the path."""
+    target = Path(path)
+    target.parent.mkdir(parents=True, exist_ok=True)
+    target.write_text(to_json(preset), encoding="utf-8")
+    return target
+
+
+def save_spec(path: str | Path, spec: PipelineSpec) -> Path:
+    """Write the v3 preset of spec to path."""
+    return save_preset(path, to_preset(spec))
+
+
+__all__ = [
+    "APP_CONTEXT",
+    "APP_DIR_NAME",
+    "DEFAULT_RENDERER",
+    "PresetEntry",
+    "PresetReport",
+    "SHIPPED_PRESET_DIR",
+    "app_data_dir",
+    "available",
+    "default_preset",
+    "default_spec",
+    "describe",
+    "read_preset",
+    "read_text",
+    "save_preset",
+    "save_spec",
+    "search_dirs",
+    "spec_from_text",
+    "spec_of",
+    "to_preset",
+    "user_preset_dir",
+    "validate",
+    "validate_all",
+]
diff --git a/lattice_glyph/presets/01_ascii_gameboy.json b/lattice_glyph/presets/01_ascii_gameboy.json
new file mode 100644
index 0000000..863f717
--- /dev/null
+++ b/lattice_glyph/presets/01_ascii_gameboy.json
@@ -0,0 +1,60 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "Classic density ramp on the Game Boy palette.",
+    "name": "01_ascii_gameboy",
+    "tags": [
+      "ascii",
+      "gameboy"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "gameboy",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 8,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "glyph_ramp",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "mode": "mono",
+      "ramp": "@%#*+=-:. "
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/presets/02_ramp_palette.json b/lattice_glyph/presets/02_ramp_palette.json
new file mode 100644
index 0000000..41afa91
--- /dev/null
+++ b/lattice_glyph/presets/02_ramp_palette.json
@@ -0,0 +1,60 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "Density ramp whose glyphs take the colour of their cell.",
+    "name": "02_ramp_palette",
+    "tags": [
+      "ascii",
+      "colour"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "pico8",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 6,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "glyph_ramp",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "mode": "palette",
+      "ramp": " .:-=+*#%@"
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/presets/03_braille_grey.json b/lattice_glyph/presets/03_braille_grey.json
new file mode 100644
index 0000000..cd7e72f
--- /dev/null
+++ b/lattice_glyph/presets/03_braille_grey.json
@@ -0,0 +1,59 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "Sub-cell braille dots on sixteen greys.",
+    "name": "03_braille_grey",
+    "tags": [
+      "bitmask",
+      "braille"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "grey_16",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 4,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "braille",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "threshold": 0.5
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/presets/04_quadrant_dither.json b/lattice_glyph/presets/04_quadrant_dither.json
new file mode 100644
index 0000000..73e0a3f
--- /dev/null
+++ b/lattice_glyph/presets/04_quadrant_dither.json
@@ -0,0 +1,59 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "Quadrant blocks, one dither pattern per cell.",
+    "name": "04_quadrant_dither",
+    "tags": [
+      "bitmask",
+      "quadrant"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "ega",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 8,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "quadrant",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "threshold": 0.5
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/presets/05_shape_mono.json b/lattice_glyph/presets/05_shape_mono.json
new file mode 100644
index 0000000..f0d5c5e
--- /dev/null
+++ b/lattice_glyph/presets/05_shape_mono.json
@@ -0,0 +1,59 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "Shape-matched characters on black and white.",
+    "name": "05_shape_mono",
+    "tags": [
+      "glyph",
+      "shape"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "bw",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "floyd_steinberg",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 10,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "glyph_shape",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "normalise": true
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/presets/06_text_halftone.json b/lattice_glyph/presets/06_text_halftone.json
new file mode 100644
index 0000000..585f1c5
--- /dev/null
+++ b/lattice_glyph/presets/06_text_halftone.json
@@ -0,0 +1,63 @@
+{
+  "app": "glyph",
+  "effects": [],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "Lattice",
+    "created": "",
+    "description": "A flowing paragraph whose glyphs thicken with the image.",
+    "name": "06_text_halftone",
+    "tags": [
+      "text",
+      "halftone"
+    ],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": {
+    "colors": [],
+    "extract": {
+      "from": "image",
+      "n_colors": 8,
+      "rows": null
+    },
+    "extract_method": "kmeans",
+    "locked": false,
+    "locked_colours": [],
+    "name": "grey_8",
+    "order": [],
+    "source": "integrated"
+  },
+  "pipeline": {
+    "algorithm": "bayer_4",
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 10,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "text",
+    "style": {
+      "bg": "#ffffff",
+      "fg": "#000000",
+      "kerning": 1.0,
+      "line_distance": 1.2,
+      "size_mode": "variable",
+      "text": "Lattice renders a paragraph in a real font, one glyph at a time.",
+      "weight_mode": "variable"
+    }
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glyph/pyproject.toml b/lattice_glyph/pyproject.toml
new file mode 100644
index 0000000..81cb4cd
--- /dev/null
+++ b/lattice_glyph/pyproject.toml
@@ -0,0 +1,32 @@
+[build-system]
+requires = ["setuptools>=68"]
+build-backend = "setuptools.build_meta"
+
+[project]
+name = "lattice-glyph"
+version = "0.1.0"
+description = "Lattice Glyph: glyph, bitmask and text rendering for PhotoCraft and DesignCraft"
+requires-python = ">=3.13"
+license = "MIT OR Apache-2.0"
+dependencies = [
+    "lattice-core>=0.1,<0.2",
+    "numpy",
+    "numba",
+    "Pillow",
+]
+
+[project.optional-dependencies]
+ui = ["lattice-core[ui]"]
+
+[project.scripts]
+lattice-glyph-cli = "lattice_glyph.cli:main"
+
+# The distribution lives beside the application directory, as lattice-dither does. The
+# mapping below makes a build started from this directory ship the package itself and its
+# presets, instead of a wheel that carries only metadata.
+[tool.setuptools]
+packages = ["lattice_glyph"]
+package-dir = { "lattice_glyph" = "." }
+
+[tool.setuptools.package-data]
+lattice_glyph = ["presets/*.json"]
diff --git a/lattice_glyph/renderer_panel.py b/lattice_glyph/renderer_panel.py
new file mode 100644
index 0000000..0f23dba
--- /dev/null
+++ b/lattice_glyph/renderer_panel.py
@@ -0,0 +1,191 @@
+"""Renderer panel: every registered renderer, with the option form of the selected one.
+
+The selector's list is ``lattice_core.cell.list_renderers()``, never a table, so a renderer
+added to the core becomes selectable here without touching this module (L12 accept). The
+option form is built from ``lattice_glyph.options``: one widget per declared option, at its
+default; a renderer this table does not name shows an honest "no option" line.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+
+from PySide6.QtCore import Signal
+from PySide6.QtWidgets import (
+    QCheckBox,
+    QComboBox,
+    QDoubleSpinBox,
+    QFormLayout,
+    QLabel,
+    QLineEdit,
+    QSpinBox,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_core.cell import list_renderers
+from lattice_glyph import options as option_tools
+
+
+class RendererPanel(QWidget):
+    """Renderer selector plus the option widgets of the selected renderer."""
+
+    changed = Signal()
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Build the selector and the option host, then show the first renderer."""
+        super().__init__(parent)
+        self.setObjectName("renderer_panel")
+        self._loading = False
+        self._renderer = ""
+        self._widgets: dict[str, QWidget] = {}
+        self.selector = QComboBox(self)
+        self.selector.setObjectName("renderer_selector")
+        for name in list_renderers():
+            self.selector.addItem(name, name)
+        self.host = QWidget(self)
+        self.host.setObjectName("renderer_options")
+        self.form = QFormLayout(self.host)
+        self.form.setContentsMargins(0, 0, 0, 0)
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(8, 8, 8, 8)
+        layout.addWidget(QLabel("Renderer", self))
+        layout.addWidget(self.selector)
+        layout.addWidget(self.host)
+        layout.addStretch(1)
+        self.selector.currentIndexChanged.connect(self._on_renderer_chosen)
+        self._show(str(self.selector.currentData() or ""))
+
+    def renderers(self) -> list[str]:
+        """Return every renderer name the selector offers, in display order."""
+        return [str(self.selector.itemData(index)) for index in range(self.selector.count())]
+
+    def current(self) -> str:
+        """Return the renderer currently selected."""
+        return str(self.selector.currentData())
+
+    def option_widget(self, key: str) -> QWidget | None:
+        """Return the widget of one option key, or None for a renderer that lacks it."""
+        return self._widgets.get(key)
+
+    def style_options(self) -> dict:
+        """Return the style options the widgets hold, defaults already dropped."""
+        values: dict = {}
+        for key, widget in self._widgets.items():
+            if isinstance(widget, QLineEdit):
+                values[key] = widget.text()
+            elif isinstance(widget, QCheckBox):
+                values[key] = widget.isChecked()
+            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
+                values[key] = widget.value()
+        return option_tools.clean(self._renderer, values)
+
+    def set_renderer(self, name: str, style: dict | None = None) -> None:
+        """Select name without emitting, then load style into its widgets."""
+        index = self.selector.findData(name)
+        if index < 0:
+            raise ValueError(f"unknown renderer {name!r}")
+        self._loading = True
+        try:
+            self.selector.setCurrentIndex(index)
+            self._show(name)
+            self._load(style or {})
+        finally:
+            self._loading = False
+
+    def _on_renderer_chosen(self) -> None:
+        """Show the option widgets of the chosen renderer and announce the change."""
+        if self._loading:
+            return
+        self._show(str(self.selector.currentData()))
+        self.changed.emit()
+
+    def _show(self, name: str) -> None:
+        """Rebuild the option form for name, every widget at its default."""
+        self._renderer = name
+        while self.form.count():
+            item = self.form.takeAt(0)
+            widget = item.widget() if item is not None else None
+            if widget is not None:
+                widget.deleteLater()
+        self._widgets = {}
+        for spec in option_tools.specs_for(name):
+            widget = _widget_for(spec, self.host)
+            self._widgets[spec.key] = widget
+            label = QLabel(spec.label, self.host)
+            if spec.hint:
+                label.setToolTip(spec.hint)
+            self.form.addRow(label, widget)
+        for widget in self._widgets.values():
+            _connect(widget, self._emit_changed)
+        if not self._widgets:
+            self.form.addRow(QLabel("This renderer has no option.", self.host))
+
+    def _emit_changed(self) -> None:
+        """Announce one user edit of an option, unless the panel is being loaded."""
+        if not self._loading:
+            self.changed.emit()
+
+    def _load(self, style: dict) -> None:
+        """Write style into the widgets, leaving every absent key at its default."""
+        for spec in option_tools.specs_for(self._renderer):
+            widget = self._widgets.get(spec.key)
+            if widget is None:
+                continue
+            value = style.get(spec.key, spec.default)
+            if isinstance(widget, QLineEdit):
+                widget.setText("" if value is None else str(value))
+            elif isinstance(widget, QCheckBox):
+                widget.setChecked(bool(value))
+            elif isinstance(widget, QSpinBox):
+                widget.setValue(int(value) if value is not None else int(spec.minimum or 0))
+            elif isinstance(widget, QDoubleSpinBox):
+                widget.setValue(float(value) if value is not None else float(spec.minimum or 0.0))
+            elif isinstance(widget, QComboBox):
+                widget.setCurrentIndex(max(0, widget.findData(value)))
+
+
+def _widget_for(spec: option_tools.OptionSpec, parent: QWidget) -> QWidget:
+    """Return the input widget a spec kind calls for, at its default value."""
+    default = spec.default
+    if spec.kind == "bool":
+        box = QCheckBox(parent)
+        box.setChecked(bool(default))
+        return box
+    if spec.kind == "choice":
+        combo = QComboBox(parent)
+        for choice in spec.choices:
+            combo.addItem(choice, choice)
+        combo.setCurrentIndex(max(0, combo.findData(default)))
+        return combo
+    if spec.kind == "float":
+        spin = QDoubleSpinBox(parent)
+        spin.setDecimals(2)
+        spin.setSingleStep(float(spec.step))
+        spin.setRange(-1e6, 1e6)
+        if spec.minimum is not None and spec.maximum is not None:
+            spin.setRange(float(spec.minimum), float(spec.maximum))
+        spin.setValue(float(default))  # type: ignore[arg-type]
+        return spin
+    if spec.kind == "int":
+        spin = QSpinBox(parent)
+        spin.setRange(0, 1_000_000)
+        if spec.minimum is not None and spec.maximum is not None:
+            spin.setRange(int(spec.minimum), int(spec.maximum))
+        spin.setValue(int(default))  # type: ignore[arg-type]
+        return spin
+    edit = QLineEdit(parent)
+    edit.setText("" if default is None else str(default))
+    return edit
+
+
+def _connect(widget: QWidget, slot: Callable[[], None]) -> None:
+    """Connect the change signal the widget actually has to slot."""
+    if isinstance(widget, QLineEdit):
+        widget.textChanged.connect(lambda _text: slot())
+    elif isinstance(widget, QCheckBox):
+        widget.toggled.connect(lambda _state: slot())
+    elif isinstance(widget, QComboBox):
+        widget.currentIndexChanged.connect(lambda _index: slot())
+    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
+        widget.valueChanged.connect(lambda _value: slot())
diff --git a/lattice_glyph/rendering.py b/lattice_glyph/rendering.py
new file mode 100644
index 0000000..c3458da
--- /dev/null
+++ b/lattice_glyph/rendering.py
@@ -0,0 +1,59 @@
+"""Render and export service of the Glyph shell: one path, shared with the CLI (G9).
+
+The window delegates here so that the GUI never builds its own pipeline call: ``render_full``
+is :func:`lattice_glyph.document.render_rgb8` and ``export_to`` is
+:func:`lattice_glyph.document.write_render`, the two functions the CLI calls. PNG export
+goes through the shared ``ExportDialog``, which owns the full-resolution render.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+from PySide6.QtCore import QSettings
+from PySide6.QtWidgets import QWidget
+
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import RGB8, Image
+from lattice_core.ui import ExportDialog
+from lattice_glyph.document import DocumentError, format_of, render_rgb8, write_render
+
+PNG = "png"
+TEXT_FORMATS = ("txt", "ansi", "html")
+
+
+def render_full(image: Image, spec: PipelineSpec) -> RGB8:
+    """Render spec on the full source through the CLI's own function (G9)."""
+    return render_rgb8(image, spec)
+
+
+def export_png(image: Image, spec: PipelineSpec, path: str | Path, parent: QWidget | None,
+               settings: QSettings) -> Path:
+    """Write the PNG the shared export dialog produces at full resolution."""
+    dialog = ExportDialog(image, spec, parent,
+                          render_full=lambda current: render_full(image, current),
+                          settings=settings)
+    dialog.format_box.setCurrentIndex(dialog.format_box.findData(PNG))
+    dialog.path_edit.setText(str(path))
+    (written,) = dialog.export_now()
+    return written
+
+
+def export_to(image: Image | None, spec: PipelineSpec, path: str | Path, parent: QWidget | None,
+              settings: QSettings) -> dict:
+    """Write one render of image to path in the format its suffix names."""
+    if image is None:
+        raise DocumentError("load an image before rendering")
+    target = Path(path)
+    fmt = format_of(target)
+    if fmt == PNG:
+        written = export_png(image, spec, target, parent, settings)
+        return {"file": str(written), "format": PNG, "warnings": []}
+    if fmt not in TEXT_FORMATS and fmt != "svg":
+        raise DocumentError(f"unknown export format {fmt!r}")
+    export = write_render(image, spec, target, fmt)
+    return {"file": str(export.path), "format": export.fmt,
+            "warnings": list(export.warnings)}
+
+
+__all__ = ["export_png", "export_to", "render_full"]
diff --git a/lattice_glyph/window.py b/lattice_glyph/window.py
new file mode 100644
index 0000000..f52a7f7
--- /dev/null
+++ b/lattice_glyph/window.py
@@ -0,0 +1,394 @@
+"""Main window of Lattice Glyph: selector, live preview, palette, presets and bridge.
+
+The window owns the only ``PipelineSpec`` and hands every job to a controller:
+
+- previews go to the shared ``RenderWorker`` on a helper thread;
+- exports go to ``ExportController``, which calls the same functions the CLI calls, so the
+  CLI and the GUI cannot produce different bytes for the same preset (G9);
+- host work goes to ``BridgeController``, and an absent host is a status-bar message.
+
+The shared widgets of ``lattice_core.ui`` are consumed, never reimplemented: canvas, worker,
+export dialog, preset indicator, empty state, bridge dot and the glyph browser.
+"""
+
+from __future__ import annotations
+
+import logging
+from pathlib import Path
+
+import numpy as np
+from PySide6.QtCore import QSettings, Qt, QThread, Signal
+from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
+from PySide6.QtWidgets import (
+    QDockWidget,
+    QFileDialog,
+    QLabel,
+    QMainWindow,
+    QMessageBox,
+    QStackedWidget,
+    QTabWidget,
+    QWidget,
+)
+
+import lattice_core.dither  # noqa: F401  (registers every algorithm)
+import lattice_core.effects  # noqa: F401  (registers every effect)
+import lattice_core.renderers  # noqa: F401  (registers every renderer)
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import Image
+from lattice_core.ui import (
+    BridgeStatusDot,
+    EmptyState,
+    PresetIndicator,
+    PreviewCanvas,
+    RenderWorker,
+    oversize_message,
+    preview_proxy,
+)
+from lattice_core.ui.glyph_browser import GlyphBrowser
+from lattice_glyph import APP_NAME
+from lattice_glyph import presets as preset_tools
+from lattice_glyph.actions import build_actions, build_toolbar, dropped_images
+from lattice_glyph.bridge_actions import DEFAULT_HOST
+from lattice_glyph.bridge_controller import BridgeController
+from lattice_glyph.document import DocumentError, load_image
+from lattice_glyph.export_actions import ExportController
+from lattice_glyph.palette_panel import PalettePanel
+from lattice_glyph.preset_panel import PresetPanel
+from lattice_glyph.renderer_panel import RendererPanel
+
+LOGGER = logging.getLogger(__name__)
+
+SETTINGS_NAME = "LatticeGlyph"
+GEOMETRY_KEY = "geometry"
+IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
+PANEL_TABS = ("Renderer", "Palette", "Presets", "Ramps")
+STATUS_MS = 5000
+STOP_MS = 5000
+EMPTY_TEXT = "Open an image, or drop one here, to start rendering glyphs."
+NO_SOURCE = "Load an image before rendering."
+
+
+class MainWindow(QMainWindow):
+    """Application window owning the pipeline spec, the render worker and the bridge."""
+
+    preview_requested = Signal(object)
+    source_changed = Signal(object)
+
+    def __init__(self, parent: QWidget | None = None, *,
+                 preset_dirs: tuple[Path, ...] | None = None) -> None:
+        """Build the canvas, the docks, the status bar and the helper threads."""
+        super().__init__(parent)
+        self.setWindowTitle(APP_NAME)
+        self.resize(1280, 800)
+        self.spec: PipelineSpec = preset_tools.default_spec()
+        self.source: Image | None = None
+        self.source_path: Path | None = None
+        self.worker: RenderWorker | None = None
+        self.render_thread: QThread | None = None
+        self._settings = QSettings(SETTINGS_NAME, SETTINGS_NAME)
+        self.exporter = ExportController(self)
+        self.bridge = BridgeController(self)
+        self.canvas = PreviewCanvas(self)
+        self.empty = EmptyState(EMPTY_TEXT)
+        self.stack = QStackedWidget(self)
+        self.stack.addWidget(self.empty)
+        self.stack.addWidget(self.canvas)
+        self.stack.setCurrentWidget(self.empty)
+        self.setCentralWidget(self.stack)
+        self.setAcceptDrops(True)
+        self.action_map = build_actions(self)
+        self.toolbar = build_toolbar(self, self.action_map)
+        self._build_dock(preset_dirs)
+        self._build_status_bar()
+        geometry = self._settings.value(GEOMETRY_KEY)
+        if geometry:
+            self.restoreGeometry(geometry)
+        self._start_worker()
+        self.bridge.pulled.connect(self._on_pulled)
+        self.bridge.pushed.connect(self._on_pushed)
+        self.bridge.failed.connect(self.report)
+        self.bridge.progress.connect(self.status)
+        self.apply_spec(preset_tools.default_spec(), announce=False)
+
+    # --- construction ------------------------------------------------------------
+
+    def _build_dock(self, preset_dirs: tuple[Path, ...] | None) -> None:
+        """Create the right dock with the renderer, palette, preset and ramp panels."""
+        self.dock = QDockWidget("Panels", self)
+        self.dock.setObjectName("panel_dock")
+        self.dock.setAllowedAreas(
+            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
+        )
+        self.tabs = QTabWidget(self.dock)
+        self.tabs.setObjectName("panel_tabs")
+        self.renderer_panel = RendererPanel(self.tabs)
+        self.palette_panel = PalettePanel(self.tabs)
+        self.preset_panel = PresetPanel(preset_dirs, self.tabs)
+        self.glyph_browser = GlyphBrowser(self.tabs)
+        self.panels: dict[str, QWidget] = dict(zip(
+            PANEL_TABS,
+            (self.renderer_panel, self.palette_panel, self.preset_panel, self.glyph_browser),
+            strict=True,
+        ))
+        for name, panel in self.panels.items():
+            self.tabs.addTab(panel, name)
+        self.dock.setWidget(self.tabs)
+        self.dock.setMinimumWidth(340)
+        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
+        self.renderer_panel.changed.connect(self.on_panels_changed)
+        self.palette_panel.changed.connect(self.on_panels_changed)
+        self.preset_panel.loaded.connect(self.load_spec)
+        self.preset_panel.save_requested.connect(self.save_preset_to)
+        self.preset_panel.failed.connect(self.report)
+        self.glyph_browser.ramp_chosen.connect(self.on_ramp_chosen)
+
+    def _build_status_bar(self) -> None:
+        """Create the status bar with the bridge dot, the preset indicator and times."""
+        bar = self.statusBar()
+        self.bridge_dot = BridgeStatusDot(DEFAULT_HOST, self)
+        self.connection_label = QLabel(f"{DEFAULT_HOST}: unknown", self)
+        self.connection_label.setObjectName("connection_label")
+        self.render_time_label = QLabel("Render: -", self)
+        self.render_time_label.setObjectName("render_time_label")
+        self.indicator = PresetIndicator(self)
+        for widget in (self.bridge_dot, self.connection_label, self.render_time_label,
+                       self.indicator):
+            bar.addPermanentWidget(widget)
+        bar.showMessage("Ready")
+        self.bridge_dot.state_changed.connect(self._on_state)
+
+    def _start_worker(self) -> None:
+        """Create the render worker in its own thread and connect its signals."""
+        thread = QThread(self)
+        worker = RenderWorker()
+        worker.moveToThread(thread)
+        thread.started.connect(worker.start)
+        thread.finished.connect(worker.deleteLater)
+        self.preview_requested.connect(worker.request_preview)
+        self.source_changed.connect(worker.set_source)
+        worker.preview_ready.connect(self._on_preview)
+        worker.failed.connect(self.report)
+        self.render_thread, self.worker = thread, worker
+        thread.start()
+
+    # --- lifecycle ---------------------------------------------------------------
+
+    def shutdown(self) -> None:
+        """Stop the helper threads and the bridge probe; safe to call more than once.
+
+        The worker reference is released only once its thread has actually stopped: PySide
+        deletes the C++ object with the last Python reference, and dropping it earlier frees
+        a worker a running thread is still executing (a hard crash, not an exception).
+        """
+        self.bridge_dot.stop()
+        self.bridge.stop()
+        thread = self.render_thread
+        if thread is None:
+            return
+        thread.quit()
+        if not thread.wait(STOP_MS):
+            LOGGER.warning("the render thread did not stop within %d ms", STOP_MS)
+            thread.wait()
+        self.render_thread = self.worker = None
+
+    def closeEvent(self, event: QCloseEvent) -> None:
+        """Remember the window geometry and stop the helper threads."""
+        self._settings.setValue(GEOMETRY_KEY, self.saveGeometry())
+        self.shutdown()
+        super().closeEvent(event)
+
+    # --- spec, panels and preview ------------------------------------------------
+
+    def settings(self) -> QSettings:
+        """Return the settings object the export dialog remembers its directory in."""
+        return self._settings
+
+    def spec_from_panels(self) -> PipelineSpec:
+        """Return the spec the panels describe, keeping the pipeline settings not shown."""
+        current = self.spec
+        spec = PipelineSpec(algorithm_id=current.algorithm_id or "floyd_steinberg",
+                            pixel_size=current.pixel_size,
+                            renderer=self.renderer_panel.current())
+        spec.algorithm_params = dict(current.algorithm_params)
+        spec.renderer_style = self.renderer_panel.style_options()
+        spec.palette = self.palette_panel.spec()
+        spec.color_metric = current.color_metric
+        spec.seed = current.seed
+        spec.pre_effects = list(current.pre_effects)
+        spec.post_effects = list(current.post_effects)
+        return spec
+
+    def on_panels_changed(self) -> None:
+        """Adopt the panels' spec, mark the preset modified and request a preview."""
+        self.spec = self.spec_from_panels()
+        self.indicator.pipeline_changed()
+        self._request_preview()
+
+    def on_ramp_chosen(self, ramp_id: str) -> None:
+        """Copy the ramp chosen in the glyph browser into the glyph_ramp option."""
+        ramp = self.glyph_browser.catalogue().get(ramp_id).ramp
+        style = dict(self.spec.renderer_style)
+        style["ramp"] = ramp
+        self.renderer_panel.set_renderer("glyph_ramp", style)
+        self.status(f"Ramp {ramp_id}")
+        self.on_panels_changed()
+
+    def apply_spec(self, spec: PipelineSpec, announce: bool = True) -> None:
+        """Adopt spec, load the panels from it and request a preview."""
+        self.spec = spec
+        self.renderer_panel.set_renderer(spec.renderer, dict(spec.renderer_style))
+        if spec.palette is not None:
+            self.palette_panel.set_palette(spec.palette)
+        if announce:
+            self.indicator.pipeline_changed()
+        self._request_preview()
+
+    def load_spec(self, spec: PipelineSpec) -> None:
+        """Load a preset spec; the indicator names the preset as freshly applied."""
+        self.apply_spec(spec, announce=False)
+        path = self.preset_panel.selected_path()
+        self.indicator.set_preset(None if path is None else path.name)
+        self.indicator.set_image_loaded(self.source is not None)
+
+    def _request_preview(self) -> None:
+        """Ask the worker for a preview of the current spec, when an image is loaded."""
+        if self.source is not None:
+            self.preview_requested.emit(self.spec)
+
+    def set_source(self, image: Image | None, path: Path | None = None) -> None:
+        """Adopt image as the document source, refusing an oversized one honestly."""
+        if image is not None:
+            message = oversize_message(np.shape(image))
+            if message is not None:
+                self.report(message)
+                return
+            image = np.ascontiguousarray(image, dtype=np.float32)
+        self.source = image
+        self.source_path = path if image is not None else None
+        self.canvas.set_original(None if image is None else preview_proxy(image))
+        self.stack.setCurrentWidget(self.empty if image is None else self.canvas)
+        self.indicator.set_image_loaded(image is not None)
+        self.source_changed.emit(image)
+        self._request_preview()
+
+    def open_dialog(self) -> None:
+        """Ask for an image file and open it."""
+        path, _ = QFileDialog.getOpenFileName(self, "Open image", str(Path.home()), IMAGE_FILTER)
+        if path:
+            self.open_path(Path(path))
+
+    def open_path(self, path: str | Path) -> bool:
+        """Load path into the document; return True when it became the source."""
+        try:
+            image = load_image(Path(path))
+        except DocumentError as exc:
+            self.report(str(exc))
+            return False
+        self.set_source(image, Path(path))
+        self.status(f"Opened {Path(path).name}")
+        return True
+
+    def _on_preview(self, result) -> None:
+        """Show one finished preview and its duration."""
+        self.canvas.set_image(result.image)
+        self.stack.setCurrentWidget(self.canvas)
+        self.render_time_label.setText(f"Render: {result.seconds * 1000:.0f} ms")
+
+    def set_mode(self, mode: str) -> None:
+        """Switch the preview canvas between before, after and split."""
+        self.canvas.set_mode(mode)  # type: ignore[arg-type]
+        action = self.action_map.get(f"mode_{mode}")
+        if action is not None:
+            action.setChecked(True)
+
+    # --- actions the toolbar and tests call by name -------------------------------
+
+    def export_dialog(self) -> None:
+        """Open the shared full-resolution export dialog."""
+        self.exporter.dialog()
+
+    def export_to(self, path: str | Path) -> dict:
+        """Write the current render to path in the format the path names."""
+        return self.exporter.to(path)
+
+    def export_text(self) -> None:
+        """Ask for a text-export path and write txt, ansi or html."""
+        self.exporter.text()
+
+    def save_preset_to(self, path: str | Path) -> None:
+        """Write the current spec as a v3 preset and remember it as the applied one."""
+        self.exporter.save_preset(str(path))
+
+    def render_full(self, image: Image, spec: PipelineSpec):
+        """Render spec on image through the function the CLI calls (G9)."""
+        return self.exporter.render_full(image, spec)
+
+    # --- bridge ------------------------------------------------------------------
+
+    def get_from_host(self) -> None:
+        """Read the active document of the bridge host into this application."""
+        self.bridge.pull()
+
+    def send_to_host(self) -> None:
+        """Place the current full-resolution render in the bridge host."""
+        if self.source is None:
+            self.report(NO_SOURCE)
+            return
+        try:
+            rgb8 = self.render_full(self.source, self.spec)
+        except DocumentError as exc:
+            self.report(str(exc))
+            return
+        self.bridge.push(np.ascontiguousarray(rgb8, dtype=np.uint8))
+
+    def _on_pulled(self, image: object, host: str) -> None:
+        """Adopt a document pulled from a host, which has no source path."""
+        if image is None:
+            self.report(f"{host}: no document")
+            return
+        self.set_source(np.ascontiguousarray(np.asarray(image), dtype=np.float32))
+        self.status(f"Read the {host} document")
+
+    def _on_pushed(self, object_id: int) -> None:
+        """Report a successful placement in the host."""
+        self.status(f"Placed object {object_id}")
+
+    def _on_state(self, state: str) -> None:
+        """Show the host reachability in the status bar label."""
+        self.connection_label.setText(f"{DEFAULT_HOST}: {state}")
+
+    def check_bridge(self) -> None:
+        """Ask the bridge status dot to probe the host now."""
+        self.bridge_dot.check()
+
+    # --- misc --------------------------------------------------------------------
+
+    def status(self, message: str) -> None:
+        """Show one transient message in the status bar."""
+        self.statusBar().showMessage(message, STATUS_MS)
+
+    def report(self, message: str) -> None:
+        """Show a failure in the status bar and a dialog, never a traceback."""
+        LOGGER.info("reported: %s", message)
+        self.status(message)
+        QMessageBox.critical(self, APP_NAME, message)
+
+    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
+        """Accept a drag carrying at least one local image file."""
+        if dropped_images(event.mimeData()):
+            event.acceptProposedAction()
+        else:
+            event.ignore()
+
+    def dropEvent(self, event: QDropEvent) -> None:
+        """Open the first image of a drop, or report that the drop was ignored."""
+        images = dropped_images(event.mimeData())
+        if not images:
+            self.status("Ignored: no image in the drop")
+            event.ignore()
+            return
+        event.acceptProposedAction()
+        self.open_path(images[0])
+
+
+__all__ = ["MainWindow", "PANEL_TABS"]
diff --git a/tests/test_glyph_app.py b/tests/test_glyph_app.py
new file mode 100644
index 0000000..220b94d
--- /dev/null
+++ b/tests/test_glyph_app.py
@@ -0,0 +1,400 @@
+"""Tests for the Lattice Glyph shell (card L12), one block per accept item, Qt offscreen.
+
+CLI and GUI bytes match on one file (G9); bridge needs no host; the CLI path needs no Qt.
+"""
+
+from __future__ import annotations
+
+import ast
+import json
+import os
+import subprocess
+import sys
+import time
+import xml.etree.ElementTree as ET
+from pathlib import Path
+
+os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
+
+import numpy as np  # noqa: E402
+import pytest  # noqa: E402
+from PIL import Image as PILImage  # noqa: E402
+from PySide6.QtCore import QSettings  # noqa: E402
+from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
+
+import lattice_core.renderers  # noqa: E402,F401  (registers every renderer)
+import lattice_glyph  # noqa: E402
+from lattice_core import color  # noqa: E402
+from lattice_core.cell import list_renderers  # noqa: E402
+from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, render  # noqa: E402
+from lattice_core.svg import SVG_NS  # noqa: E402
+from lattice_glyph import cli, presets  # noqa: E402
+from lattice_glyph.document import (  # noqa: E402
+    FORMATS,
+    DocumentError,
+    GridError,
+    export_bytes,
+    grid_bundle,
+    load_image,
+    render_rgb8,
+    target_path,
+    write_render,
+)
+from lattice_glyph.options import OPTIONS, clean, defaults_for  # noqa: E402
+from lattice_glyph.window import MainWindow  # noqa: E402
+
+PACKAGE = Path(lattice_glyph.__file__).resolve().parent
+SHIPPED = PACKAGE / "presets"
+RENDERERS = sorted(list_renderers())
+
+
+class _FakeClient:
+    """Stand-in for a live ArtCraft client."""
+
+    def render_document(self):
+        return color.to_pil(np.full((16, 16, 3), 128, dtype=np.uint8))
+
+    def disconnect(self) -> None:
+        self.closed = True
+CLI_MODULES = ("__init__", "__main__", "cli", "document", "options", "presets")
+GUI_MODULES = ("actions", "app", "bridge_actions", "bridge_controller", "export_actions",
+               "palette_panel", "preset_panel", "renderer_panel", "rendering", "window")
+BLOCKER = """import sys, importlib.abc
+class Refuse(importlib.abc.MetaPathFinder):
+    def find_spec(self, name, path=None, target=None):
+        if name.split('.')[0] == 'PySide6':
+            raise ImportError('PySide6 is not installed')
+sys.meta_path.insert(0, Refuse())
+sys.path.insert(0, {root!r})
+from lattice_glyph.cli import main
+code = main(['render', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r}])
+assert 'PySide6' not in sys.modules and 'lattice_core.ui' not in sys.modules
+assert not [m for m in sys.modules if m.startswith('lattice_dither')]
+raise SystemExit(code)"""
+
+
+@pytest.fixture(scope="module")
+def qapp() -> QApplication:
+    """Return the shared offscreen QApplication."""
+    app = QApplication.instance()
+    return app if isinstance(app, QApplication) else QApplication([])
+
+
+@pytest.fixture
+def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
+    """Replace the modal error dialog with a list, so a failure never blocks the suite."""
+    seen: list[str] = []
+    monkeypatch.setattr(QMessageBox, "critical", lambda *a: seen.append(str(a[2])))
+    return seen
+
+
+@pytest.fixture
+def image() -> np.ndarray:
+    """Return a deterministic float32 RGB image: noise plus a horizontal gradient."""
+    rng, ramp = np.random.default_rng(7), np.linspace(0, 1, 128, dtype=np.float32)
+    noise = rng.random((96, 128, 3), np.float32)
+    return np.ascontiguousarray(np.clip(0.5 * noise + 0.5 * ramp[None, :, None], 0, 1), np.float32)
+
+
+@pytest.fixture
+def image_file(tmp_path: Path, image: np.ndarray) -> Path:
+    """Write the deterministic image as a PNG and return its path."""
+    return _png(tmp_path / "source.png", color.to_rgb8(image))
+
+
+@pytest.fixture
+def make_window(qapp: QApplication, tmp_path: Path):
+    """Return a factory of isolated windows, each stopped and closed at teardown."""
+    opened: list[MainWindow] = []
+
+    def build() -> MainWindow:
+        window = MainWindow(preset_dirs=(SHIPPED, tmp_path / "user"))
+        window._settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
+        window.show()
+        QApplication.processEvents()
+        opened.append(window)
+        return window
+
+    yield build
+    for window in opened:
+        window.shutdown()
+
+
+def _png(path: str | Path, rgb8: np.ndarray) -> str | Path:
+    color.to_pil(rgb8).save(path, format="PNG")
+    return path
+
+
+def _preset(tmp_path: Path, spec: PipelineSpec | None = None) -> Path:
+    presets.save_spec(path := tmp_path / "preset.json", spec or presets.default_spec())
+    return path
+
+
+def _settle(predicate, timeout_ms: int = 20000) -> None:
+    deadline = time.monotonic() + timeout_ms / 1000.0
+    while not predicate() and time.monotonic() < deadline:
+        QApplication.processEvents()
+        time.sleep(0.005)
+    assert predicate(), "the asynchronous shell never reached the expected state"
+
+
+def _cli(tmp_path: Path, preset: Path, source: Path, fmt: str | None = None) -> bytes:
+    target = tmp_path / f"cli.{fmt or 'png'}"
+    argv = ["render", "--preset", str(preset), "--in", str(source), "--out", str(target)]
+    assert cli.main(argv + (["--format", fmt] if fmt else [])) == cli.EXIT_OK
+    return target_path(target, fmt or "png").read_bytes()
+
+
+def _tops(path: Path) -> set[str]:
+    tree = ast.parse(path.read_text("utf-8"))
+    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
+             for alias in node.names}
+    names |= {node.module for node in ast.walk(tree)
+              if isinstance(node, ast.ImportFrom) and node.module}
+    return {name.split(".")[0] for name in names}
+
+
+def test_window_opens_previews_saves_and_reports_refusals(make_window, tmp_path: Path,
+                                                          image_file: Path,
+                                                          quiet: list[str]) -> None:
+    """The shell opens, previews, saves, and reports every refusal cleanly."""
+    window = make_window()
+    assert window.tabs.count() == 4
+    assert window.bridge_dot.state() in {"unknown", "connected", "disconnected"}
+    window.check_bridge()
+    _settle(lambda: window.bridge_dot.state() != "unknown")
+    assert window.connection_label.text().startswith("photocraft: ")
+    assert window.open_path(tmp_path / "nope.png") is False
+    window.export_dialog()
+    assert window.source is None and quiet
+    with pytest.raises(DocumentError):
+        window.export_to(tmp_path / "out.png")
+    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
+    assert window.source is None and len(quiet) == 3 and "9000" in quiet[-1]
+    assert window.open_path(image_file) is True
+    _settle(lambda: window.canvas.qimage() is not None)
+    assert window.stack.currentWidget() is window.canvas
+    expected = render(window.source, window.spec)
+    window.export_to(tmp_path / "out.png")
+    with PILImage.open(tmp_path / "out.png") as written:
+        assert np.array_equal(np.asarray(written.convert("RGB")), expected)
+
+
+def test_cli_render_matches_the_gui_bytes(make_window, tmp_path: Path, image_file: Path,
+                                          quiet: list[str]) -> None:
+    """For every shipped preset and every format, CLI and GUI write the same bytes."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    for preset in sorted(SHIPPED.glob("*.json")):
+        expected = _cli(tmp_path, preset, image_file)
+        window.apply_spec(presets.spec_of(presets.read_preset(preset)))
+        window.export_to(tmp_path / "gui.png")
+        assert (tmp_path / "gui.png").read_bytes() == expected, preset.name
+    light = _preset(tmp_path)
+    window.apply_spec(presets.spec_of(presets.read_preset(light)))
+    for fmt in FORMATS:
+        expected = _cli(tmp_path, light, image_file, fmt)
+        window.export_to(tmp_path / f"gui.{fmt}")
+        assert (tmp_path / f"gui.{fmt}").read_bytes() == expected, fmt
+        if fmt == "svg":
+            assert ET.fromstring(expected.decode()).tag == f"{{{SVG_NS}}}svg"
+    assert not quiet
+
+
+def test_cli_matches_the_gui_on_a_preset_the_shell_wrote(make_window, tmp_path: Path,
+                                                        image_file: Path, image: np.ndarray,
+                                                        quiet: list[str]) -> None:
+    """A preset the shell saved renders byte-identically; the grid path matches too."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    window.renderer_panel.set_renderer("braille", {"threshold": 0.35, "fg": "#112233"})
+    window.on_panels_changed()
+    window.save_preset_to(str(tmp_path / "user" / "roundtrip.json"))
+    window.export_to(tmp_path / "gui.png")
+    assert _cli(tmp_path, tmp_path / "user" / "roundtrip.json", image_file) == (
+        tmp_path / "gui.png").read_bytes()
+    assert np.array_equal(window.render_full(window.source, window.spec),
+                          render_rgb8(window.source, window.spec))
+    from lattice_core import pipeline as core
+
+    for renderer in RENDERERS:
+        spec = PipelineSpec(pixel_size=6, renderer=renderer,
+                            palette=PaletteSpec(source="builtin", name="grey_8"))
+        bundle = grid_bundle(image, spec)
+        frame = core._render_frame(bundle.renderer, bundle.grid, bundle.palette, bundle.style)
+        rendered = render(image, spec)
+        assert np.array_equal(color.to_rgb8(frame[: rendered.shape[0], : rendered.shape[1]]),
+                              rendered), renderer
+    with pytest.raises(GridError):
+        grid_bundle(image, PipelineSpec(algorithm_id=None, palette=None))
+
+
+def test_bridge_status_and_verbs_without_a_host(capsys: pytest.CaptureFixture[str],
+                                                monkeypatch: pytest.MonkeyPatch,
+                                                tmp_path: Path) -> None:
+    """bridge status and the bridge verbs never crash when no host runs, or when it refuses."""
+    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
+    report = json.loads(capsys.readouterr().out)
+    assert report["ok"] is True
+    assert [entry["host"] for entry in report["hosts"]] == ["photocraft", "designcraft"]
+    assert all(isinstance(entry["connected"], bool) for entry in report["hosts"])
+    assert cli.main(["bridge", "status", "photocraft"]) == cli.EXIT_OK
+    state = "connected" if report["hosts"][0]["connected"] else "not running"
+    assert capsys.readouterr().out.splitlines() == [f"photocraft: {state}"]
+    source = _png(tmp_path / "source.png", np.zeros((8, 8, 3), dtype=np.uint8))
+    preset = _preset(tmp_path)
+
+    def broken(token_path=None, port=None):
+        raise OSError("connection refused")
+
+    monkeypatch.setattr("lattice_core.bridge.photocraft.PhotoCraftClient.discover",
+                        staticmethod(broken))
+    monkeypatch.setattr("lattice_core.bridge.designcraft.DesignCraftClient.discover",
+                        staticmethod(broken))
+    assert cli.host_report(["photocraft", "designcraft"]) == [
+        {"host": "photocraft", "connected": False}, {"host": "designcraft", "connected": False}]
+    assert cli.main(["bridge", "push", "--preset", str(preset), "--in", str(source),
+                     "--host", "designcraft"]) == cli.EXIT_BRIDGE
+    assert cli.main(["bridge", "pull", "--preset", str(preset), "--out",
+                     str(tmp_path / "o.png")]) == cli.EXIT_BRIDGE
+    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
+    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
+    target = tmp_path / "pulled.png"
+    assert cli.main(["bridge", "pull", "--preset", str(preset),
+                     "--out", str(target)]) == cli.EXIT_OK and target.exists()
+
+
+def test_the_cli_path_needs_no_qt_and_runs_without_it(tmp_path: Path) -> None:
+    """No CLI module imports Qt, no module imports a sibling app, and the CLI still renders."""
+    for name, qt in [(n, False) for n in CLI_MODULES] + [(n, True) for n in GUI_MODULES]:
+        tops = _tops(PACKAGE / f"{name}.py")
+        assert ("PySide6" in tops) is qt, name
+        assert "lattice_core.ui" not in tops or qt, name
+    for path in sorted(PACKAGE.rglob("*.py")):
+        assert not _tops(path) & {"lattice_dither", "lattice_glitch"}, path.name
+    source = _png(tmp_path / "source.png", color.to_rgb8(np.full((16, 16, 3), 0.5, np.float32)))
+    target = tmp_path / "out.png"
+    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(source),
+                            target=str(target), preset=str(_preset(tmp_path)))
+    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
+                            text=True, timeout=300, check=False)
+    assert result.returncode == 0, result.stderr
+    with PILImage.open(target) as written:
+        assert written.format == "PNG"
+
+
+def test_every_registered_renderer_is_selectable(make_window, image_file: Path,
+                                                 quiet: list[str]) -> None:
+    """The selector offers exactly the registry, and each choice renders a preview."""
+    window = make_window()
+    assert window.renderer_panel.renderers() == RENDERERS == sorted(OPTIONS)
+    assert window.open_path(image_file) is True
+    image = np.linspace(0.0, 1.0, 48 * 64 * 3, dtype=np.float32).reshape(48, 64, 3)
+    for renderer in RENDERERS:
+        bare = PipelineSpec(pixel_size=6, renderer=renderer, renderer_style={})
+        filled = PipelineSpec(pixel_size=6, renderer=renderer,
+                              renderer_style=defaults_for(renderer))
+        assert np.array_equal(render(image, bare), render(image, filled)), renderer
+        window.renderer_panel.set_renderer(renderer)
+        window.on_panels_changed()
+        assert window.spec.renderer == renderer == window.renderer_panel.current()
+        for spec in OPTIONS[renderer]:
+            assert window.spec.renderer_style.get(spec.key, spec.default) == spec.default
+        _settle(lambda: window.canvas.qimage() is not None)
+    assert clean("glyph_ramp", {"ramp": "@%#*+=-:. ", "offset": 0.0}) == {}
+    assert clean("glyph_ramp", {"ramp": " .:-=+*#%@", "mode": "palette"}) == {
+        "ramp": " .:-=+*#%@", "mode": "palette"}
+    with pytest.raises(ValueError):
+        clean("glyph_ramp", {"mode": "spectral"})
+    assert not quiet
+
+
+def test_the_render_and_presets_verbs(tmp_path: Path, image_file: Path,
+                                      capsys: pytest.CaptureFixture[str]) -> None:
+    """render --json prints only its result; exit codes and the png suffix follow §8."""
+    preset = _preset(tmp_path)
+    target = tmp_path / "out.png"
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(target), "--json"]) == cli.EXIT_OK
+    assert json.loads(capsys.readouterr().out)["bytes"] == target.stat().st_size
+    assert cli.main(["render", "--preset", str(tmp_path / "nope.json"), "--in",
+                     str(image_file), "--out", str(tmp_path / "a.png")]) == cli.EXIT_USAGE
+    assert cli.main(["render", "--preset", str(preset), "--in", str(tmp_path / "nope.png"),
+                     "--out", str(tmp_path / "b.png")]) == cli.EXIT_RENDER
+    bare = tmp_path / "no-suffix"
+    assert cli.main([]) == cli.EXIT_USAGE
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(bare)]) == cli.EXIT_OK and bare.with_suffix(".png").exists()
+    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "show", str(preset), "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "validate", str(preset), "--json"]) == cli.EXIT_OK
+    broken = tmp_path / "broken.json"
+    broken.write_text("{not json", encoding="utf-8")
+    assert cli.main(["presets", "validate", str(broken), "--json"]) == cli.EXIT_USAGE
+    assert '"ok": false' in capsys.readouterr().out
+    source_dir = tmp_path / "in"
+    (source_dir / "sub").mkdir(parents=True)
+    for path in (source_dir / "a.png", source_dir / "sub" / "b.png"):
+        _png(path, color.to_rgb8(np.full((16, 16, 3), 0.4, np.float32)))
+    out_dir = tmp_path / "out"
+    assert cli.main(["batch", "--preset", str(preset), "--in", str(source_dir),
+                     "--out", str(out_dir), "--recursive"]) == cli.EXIT_OK
+    assert sorted(path.name for path in out_dir.rglob("*.png")) == ["a.png", "b.png"]
+
+
+def test_shipped_presets_and_document_helpers(tmp_path: Path, image: np.ndarray) -> None:
+    """Shipped presets validate in context; document failures are typed DocumentErrors."""
+    reports = presets.validate_all((SHIPPED,))
+    assert len(reports) >= 4 and all(report.ok for report in reports)
+    for report in reports:
+        assert presets.read_preset(SHIPPED / report.name).app == presets.APP_CONTEXT
+    spec = presets.default_spec()
+    assert (spec.renderer, spec.pixel_size) == ("glyph_ramp", 8)
+    assert presets.user_preset_dir().parent.name == "LatticeGlyph"
+    assert presets.search_dirs()[0] == SHIPPED
+    with pytest.raises(DocumentError) as raised:
+        load_image(tmp_path / "nope.png")
+    assert "nope.png" in str(raised.value)
+    with pytest.raises(DocumentError):
+        export_bytes(image, spec, "pdf")
+    with pytest.raises(DocumentError):
+        render_rgb8(image, PipelineSpec(palette=PaletteSpec(source="custom",
+                                                           colors=["#zzz"])))
+    assert target_path(tmp_path / "a", "svg").name == "a.svg"
+    assert target_path(tmp_path / "a.png", "svg").name == "a.png"
+    export = write_render(image, spec, tmp_path / "deep" / "out.png")
+    assert export.path.exists() and export.size == export.path.stat().st_size
+    spec.post_effects = [EffectInstance("unsharp", {"amount": 0.5})]
+    assert "raster" in export_bytes(image, spec, "txt")[1][0]
+
+
+def test_the_panels_list_load_save_and_feed_the_spec(make_window, tmp_path: Path,
+                                                     image: np.ndarray,
+                                                     quiet: list[str]) -> None:
+    """Shipped presets load, saving marks the indicator, panels feed the spec."""
+    window = make_window()
+    entries = window.preset_panel.entries()
+    assert entries and all(entry.path.parent == SHIPPED and entry.read_only for entry in entries)
+    assert window.preset_panel.select_name(entries[0].name)
+    window.preset_panel.load_selected()
+    assert window.spec.renderer == presets.spec_of(
+        presets.read_preset(entries[0].path)).renderer
+    assert window.indicator.preset_name() == entries[0].name
+    window.save_preset_to(str(tmp_path / "user" / "mine.json"))
+    assert (tmp_path / "user" / "mine.json").exists()
+    assert window.indicator.preset_name() == "mine.json"
+    window.set_source(image)
+    panel = window.palette_panel
+    panel.kind.setCurrentIndex(panel.kind.findData("custom"))
+    panel.colors.setText("#000000 #ff0000 #ffffff")
+    assert panel.spec().colors == ["#000000", "#ff0000", "#ffffff"] and panel.valid_colours()
+    panel.kind.setCurrentIndex(panel.kind.findData("extracted"))
+    panel.extract_k.setValue(6)
+    window.on_panels_changed()
+    assert window.spec.palette is not None and window.spec.palette.extract_k == 6
+    ramp = next(entry for entry in window.glyph_browser.catalogue().ramps()
+                if entry.ramp != presets.DEFAULT_RAMP)
+    window.glyph_browser.ramp_chosen.emit(ramp.id)
+    assert window.spec.renderer == "glyph_ramp"
+    assert window.spec.renderer_style["ramp"] == ramp.ramp
+    assert not quiet


CODER NOTES AND DEVIATIONS
- AUCUN. Codeur tué par timeout, aucun rapport rendu. Les fichiers sont sur disque, verts, et n'ont
  jamais été relus. Traite l'absence de justification comme un risque : si un choix est ambigu, dis-le
  plutôt que de le présumer voulu.
