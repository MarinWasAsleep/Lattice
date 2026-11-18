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

## §12 Feedback buffer

The mechanism that makes a glitch tool an instrument rather than a filter.

```
f(n) = decay * T(f(n-1)) + input
```

- `decay` in `[0, 0.99]`. Values at or above 1 are rejected at validation.
- `T` is one of: `translate`, `rotate`, `scale`, `displace`, `identity`. Composable.
- The buffer is normalised per frame so it cannot diverge.
- Stability test: 200 iterations on a fixed input, no NaN, no value outside `[0, 1]`, and the mean
  converges.
- Options: `decay`, `transform`, `amount`, `iterations` (1..8), `blend` (`add` | `max` | `screen`).

## §13 Displacement

- Map source: a still image, an image sequence, a noise field, or the feedback buffer.
- Map modes: `luma`, `r`, `g`, `b`, `hue`.
- `dst(x, y) = src(x + k * (mapR - 0.5), y + k * (mapG - 0.5))`, with `k` in pixels.
- `iterations` repeats the displacement with decay, producing a smear without a feedback loop.
- `mask` restricts the effect spatially (§18).
- Sampling is bilinear; edges clamp.

## §14 Pixel sort

- Three thresholds: `black`, `brightness`, `white`. A run starts when a pixel passes `brightness`
  and continues while it stays inside the `black`..`white` band.
- Direction: `rows`, `columns`, `diagonal`.
- Sort key: `luma`, `hue`, `saturation`, `r`, `g`, `b`.
- `mask` acts as an interval map: white pixels are sorted, black pixels are not.
- Runs are sorted with a stable sort so the result is deterministic.

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

## §17 CRT / scanlines

The finishing layer. Static by nature, and that is fine.

- Scanline beam profile, phosphor mask (`slot` | `aperture_grille` | `shadow_mask`), bloom,
  curvature, vignette.
- **The mask scales in device pixels, not image pixels.** A CRT effect that does not know its
  output resolution is a lie.
- Options: `scanline_intensity`, `mask`, `mask_scale`, `bloom`, `curvature`, `vignette`.

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

TASK CARD
### L20 · Lattice Glitch application shell
- wave: 2 · deps: L13, L14, L15, L16, L17, L18, L19 · executor: OMH deep-work · review: full · size: L
- owns: `lattice_glitch/**`, `tests/test_glitch_app.py`
- context: §1 §2 §7 §8 §12 §13 §14 §15 §16 §17 §18
- spec: the `lattice-glitch` distribution. PySide6 window with an effect stack, a live preview, a
  seed control with reroll and per-module lock, a mask painter, a preset browser, and the four CLI
  verbs of §8. Bridge to PhotoCraft and DesignCraft. Works standalone.
- accept:
  - the app launches, opens an image, stacks two effects, reorders them, and saves.
  - the CLI `render` and the GUI produce identical bytes for the same preset (G9).
  - reroll changes the output; locking a module keeps that module's contribution.
  - the mask painter produces a mask that the renderer honours.
  - the app runs with `lattice-core` without the `[ui]` extra only for the CLI path.


GATE RESULTS
GATES (orchestrateur, rejoués après l'attempt 2) :
- G2 pytest : 8 passed (tests/test_glitch_app.py) (orchestrateur).
- G3 ruff (owns) : All checks passed.
- G1 : lattice_glitch/pyproject.toml créé (vérifié) ; 21 modules ≤ 392 l ; E1 DEV-222 (test 459 l) et DEV-223 (streams verrouillés sérialisés, G9) enregistrés par l'orchestrateur.
RE-REVUE PASS 1 (verdict FIX) — VÉRIFIE finding par finding que le correctif du retry est réel ; le codeur
affirme avoir appliqué dans l'ordre du JSON. Juge le diff CUMULATIF (HEAD -> arbre), pas la prose :
- [BLOCKER] lattice_glitch/export_actions.py:54 — Dans render_full, convertir DocumentError en ExportError ; purger les mask_id des slots à la suppression d'un masque ; test : masque supprimé → export via dialogue → rapport, aucune exceptio
- [MAJOR] lattice_glitch/pyproject.toml:0 — Ajouter lattice_glitch/pyproject.toml calqué sur lattice_glyph/pyproject.toml : name lattice-glitch, version 0.1.0, license MIT OR Apache-2.0, dependencies lattice-core>=0.1,<0.2 + numpy/num
- [MAJOR] lattice_glitch/effects_panel.py:180 — Pour ntsc, formulaire depuis params_for_mode avec bascule simple/avancé (simple par défaut, 4 sliders) + sélecteur des six PRESETS ; tooltips honnêtes via LABEL_NOTES ; test : le mode simple
- [MAJOR] lattice_glitch/presets.py:115 — Sérialiser le stream de chaque slot verrouillé dans son entrée d'effet (p. ex. « seed »: controller.module_seed_for(i)) et le relire vers RenderContext.streams ; test verrou → reroll → sauve
- [MAJOR] lattice_glitch/window.py:215 — Copier les plans : masks={k: v.copy() for k, v in self.mask_panel.planes().items()}.
- [MAJOR] lattice_glitch/window_bridge.py:46 — Prober au démarrage et après chaque pull/push (ou QTimer périodique) ; test : après check_bridge, l'état quitte « unknown ».
- [MINOR] tests/test_glitch_app.py:301 — Remplacer par des assertions discriminantes (octets PNG relus == png_bytes(render_preset), ordre du stack après move).
- [MINOR] tests/test_glitch_app.py:235 — Garder les deux effets actifs, verrouiller 0, reroll, assert module 0 identique et module 1 différent.
- [MINOR] lattice_glitch/actions.py:90 — Typer QMimeData, QDragEnterEvent, QDropEvent, PreviewResult, QPaintEvent.

DIFF (cumulatif HEAD -> arbre)
diff --git a/lattice_glitch/__init__.py b/lattice_glitch/__init__.py
new file mode 100644
index 0000000..d485494
--- /dev/null
+++ b/lattice_glitch/__init__.py
@@ -0,0 +1,7 @@
+"""Lattice Glitch: feedback, displacement, sorting and signal degradation for ArtCraft."""
+
+from __future__ import annotations
+
+APP_NAME = "Lattice Glitch"
+APP_ID = "glitch"
+__version__ = "0.1.0"
diff --git a/lattice_glitch/__main__.py b/lattice_glitch/__main__.py
new file mode 100644
index 0000000..90c585a
--- /dev/null
+++ b/lattice_glitch/__main__.py
@@ -0,0 +1,25 @@
+"""Entry point of Lattice Glitch: ``python -m lattice_glitch`` starts the window.
+
+With a verb on the command line it runs the CLI instead, so ``python -m lattice_glitch
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
+        from lattice_glitch.cli import main as cli_main
+
+        return cli_main(arguments)
+    from lattice_glitch.app import main as app_main
+
+    return app_main([])
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/lattice_glitch/actions.py b/lattice_glitch/actions.py
new file mode 100644
index 0000000..bdb3d4b
--- /dev/null
+++ b/lattice_glitch/actions.py
@@ -0,0 +1,136 @@
+"""Actions and toolbar of the Glitch shell, built from one table so nothing is half-wired.
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
+from PySide6.QtCore import QMimeData
+from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
+from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
+
+if TYPE_CHECKING:
+    from lattice_glitch.window import MainWindow
+
+MODES: tuple[tuple[str, str, str], ...] = (
+    ("mode_before", "Before", "before"),
+    ("mode_after", "After", "after"),
+    ("mode_split", "Split", "split"),
+)
+TOOLBAR_GROUPS: tuple[tuple[str, ...], ...] = (
+    ("open_image", "get_from_host", "send_to_host"),
+    ("export_image", "reroll"),
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
+        ("reroll", "Reroll seed", window.reroll, QKeySequence("R")),
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
+def dropped_images(mime: QMimeData) -> list[Path]:
+    """Return the local image files carried by mime, in drop order."""
+    if not mime.hasUrls():
+        return []
+    paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
+    return [path for path in paths if path.suffix.lower() in IMAGE_SUFFIXES]
+
+
+def handle_drag_enter(window: MainWindow, event: QDragEnterEvent) -> None:
+    """Accept a drag carrying at least one local image file, ignore the rest."""
+    if dropped_images(event.mimeData()):
+        event.acceptProposedAction()
+    else:
+        event.ignore()
+
+
+def handle_drop(window: MainWindow, event: QDropEvent) -> None:
+    """Open the first image of a drop, or report that the drop was ignored."""
+    images = dropped_images(event.mimeData())
+    if not images:
+        window.status("Ignored: no image in the drop")
+        event.ignore()
+        return
+    event.acceptProposedAction()
+    window.open_path(images[0])
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
+    "handle_drag_enter",
+    "handle_drop",
+]
diff --git a/lattice_glitch/app.py b/lattice_glitch/app.py
new file mode 100644
index 0000000..cce5185
--- /dev/null
+++ b/lattice_glitch/app.py
@@ -0,0 +1,74 @@
+"""QApplication bootstrap of Lattice Glitch: the Fusion dark theme and the window."""
+
+from __future__ import annotations
+
+import logging
+import sys
+
+from PySide6.QtGui import QColor, QPalette
+from PySide6.QtWidgets import QApplication
+
+from lattice_glitch import APP_NAME
+from lattice_glitch.actions import connect_shutdown
+from lattice_glitch.window import MainWindow
+
+LOGGER = logging.getLogger(__name__)
+BASE_COLOR = QColor(35, 35, 38)
+WINDOW_COLOR = QColor(53, 53, 56)
+TEXT_COLOR = QColor(220, 220, 220)
+DISABLED_COLOR = QColor(120, 120, 120)
+HIGHLIGHT_COLOR = QColor(214, 106, 64)
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
+    """Start the Lattice Glitch GUI and return the Qt exit code."""
+    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
+    app = create_application(argv)
+    window = MainWindow()
+    connect_shutdown(window)
+    window.show()
+    LOGGER.info("Lattice Glitch window shown")
+    return app.exec()
+
+
+__all__ = ["create_application", "dark_palette", "main"]
diff --git a/lattice_glitch/bridge_actions.py b/lattice_glitch/bridge_actions.py
new file mode 100644
index 0000000..17ac564
--- /dev/null
+++ b/lattice_glitch/bridge_actions.py
@@ -0,0 +1,80 @@
+"""Bridge work of the Glitch shell, run on a helper thread (§7, E9).
+
+The window never talks to a host on the GUI thread: a slow connection would freeze the
+preview. ``BridgeWorker`` does exactly three things — pull the active document, render
+and place a render as a layer, or explain why neither was possible. A host that is not
+running is the normal ``absent`` answer, shown in the status bar; only a real bridge
+failure is ``failed``. The push render runs here, in the worker thread, through the
+CLI's own function with the session's render context, so a full-resolution send never
+freezes the window (G9).
+"""
+
+from __future__ import annotations
+
+import logging
+
+from PySide6.QtCore import QObject, Signal, Slot
+
+from lattice_core import color
+from lattice_core.bridge import BridgeError
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import Image
+from lattice_glitch.document import DocumentError, RenderContext, render_rgb8
+from lattice_glitch.hosts import discover
+
+LOGGER = logging.getLogger(__name__)
+
+DEFAULT_HOST = "photocraft"
+DEFAULT_NAME = "Lattice Glitch"
+NOT_RUNNING = "{host} is not running: Lattice Glitch works standalone"
+
+
+class BridgeWorker(QObject):
+    """Pulls documents from a host and pushes renders to it, off the GUI thread."""
+
+    pulled = Signal(object, str)
+    pushed = Signal(int)
+    failed = Signal(str)
+    absent = Signal(str)
+    progress = Signal(str)
+
+    @Slot(str)
+    def pull(self, host: str) -> None:
+        """Read the active document of host and emit it as a float32 image."""
+        self.progress.emit(f"Reading the {host} document…")
+        client = discover(host)
+        if client is None:
+            self.absent.emit(NOT_RUNNING.format(host=host))
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
+    @Slot(str, object, object, str, object)
+    def push(self, host: str, image: Image, spec: PipelineSpec, name: str,
+             context: RenderContext) -> None:
+        """Render image with spec and the session context, then place it in host."""
+        self.progress.emit(f"Placing the render in {host}…")
+        client = discover(host)
+        if client is None:
+            self.absent.emit(NOT_RUNNING.format(host=host))
+            return
+        try:
+            rgb8 = render_rgb8(image, spec, context=context)
+            object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
+        except (BridgeError, OSError, ValueError, DocumentError) as exc:
+            LOGGER.debug("bridge push failed", exc_info=True)
+            self.failed.emit(f"{host}: {exc}")
+            return
+        finally:
+            client.disconnect()
+        self.pushed.emit(int(object_id))
+
+
+__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
diff --git a/lattice_glitch/bridge_controller.py b/lattice_glitch/bridge_controller.py
new file mode 100644
index 0000000..35176be
--- /dev/null
+++ b/lattice_glitch/bridge_controller.py
@@ -0,0 +1,78 @@
+"""Bridge controller of the Glitch shell: host work on its own thread (§7, E9).
+
+The window never talks to a host on the GUI thread, and a host that is not running is a
+normal answer reported through ``absent`` (a status-bar line), never a dialog. The
+controller is opt-in: without it, the shell is a complete standalone application.
+"""
+
+from __future__ import annotations
+
+import logging
+
+from PySide6.QtCore import QObject, QThread, Signal
+
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import Image
+from lattice_glitch.bridge_actions import DEFAULT_HOST, BridgeWorker
+from lattice_glitch.document import RenderContext
+
+LOGGER = logging.getLogger(__name__)
+STOP_MS = 5000
+LAYER_NAME = "Lattice Glitch"
+
+
+class BridgeController(QObject):
+    """Owns the bridge thread and re-emits its results in the window's vocabulary."""
+
+    pulled = Signal(object, str)
+    pushed = Signal(int)
+    failed = Signal(str)
+    absent = Signal(str)
+    progress = Signal(str)
+    pull_request = Signal(str)
+    push_request = Signal(str, object, object, str, object)
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
+        worker.absent.connect(self.absent)
+        worker.progress.connect(self.progress)
+        thread.start()
+
+    def pull(self) -> None:
+        """Ask the worker to read the active document of the host."""
+        self.pull_request.emit(self.host)
+
+    def push(self, image: Image, spec: PipelineSpec, context: RenderContext,
+             name: str = LAYER_NAME) -> None:
+        """Ask the worker to render image with spec and place it in the host as a layer."""
+        self.push_request.emit(self.host, image, spec, name, context)
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
+__all__ = ["BridgeController", "LAYER_NAME"]
diff --git a/lattice_glitch/cli.py b/lattice_glitch/cli.py
new file mode 100644
index 0000000..26fd69d
--- /dev/null
+++ b/lattice_glitch/cli.py
@@ -0,0 +1,367 @@
+"""Command line of Lattice Glitch: the four verbs of §8 and their exit codes.
+
+``render`` and ``batch`` go through :mod:`lattice_glitch.document`, the module the GUI
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
+import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
+from lattice_core import color
+from lattice_core.bridge import HOSTS, BridgeError
+from lattice_core.preset import Preset
+from lattice_glitch import presets as preset_tools
+from lattice_glitch.document import (
+    FORMATS,
+    DocumentError,
+    Export,
+    format_of,
+    load_image,
+    render_preset,
+    target_path,
+    write_render,
+)
+from lattice_glitch.hosts import discover as discover_host
+
+EXIT_OK = 0
+EXIT_USAGE = 1
+EXIT_RENDER = 2
+EXIT_BRIDGE = 3
+DEFAULT_EXTENSIONS = "png,jpg,jpeg,bmp,tif,tiff,webp"
+PROG = "lattice-glitch"
+
+
+class UsageError(Exception):
+    """A command line the application cannot honour: a missing or unreadable preset."""
+
+
+class _Parser(argparse.ArgumentParser):
+    """Argument parser reporting usage errors with exit code 1, not argparse's 2."""
+
+    _argv: list[str] | None = None
+
+    def error(self, message: str) -> NoReturn:
+        """Print the usage line and exit with the §8 usage code.
+
+        With ``--json`` on the command line the machine result is still printed on
+        stdout, so a machine caller never receives an empty answer (§8).
+        """
+        self.print_usage(sys.stderr)
+        if self._argv is not None and "--json" in self._argv:
+            print(json.dumps({"ok": False, "errors": [message]},
+                             indent=2, ensure_ascii=False, sort_keys=True))
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
+def _preset(preset: str) -> Preset:
+    """Load a preset file in this app's context, mapping any failure to a usage error."""
+    path = Path(preset)
+    if not path.is_file():
+        raise UsageError(f"preset not found: {path}")
+    try:
+        return preset_tools.read_preset(path)
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
+def _export_payload(export: Export) -> dict:
+    """Return the machine-readable description of one written file."""
+    return {"ok": True, "file": str(export.path), "format": export.fmt,
+            "bytes": export.size, "warnings": list(export.warnings), "errors": []}
+
+
+def _cmd_render(args: argparse.Namespace) -> int:
+    """Render one image with one preset into one file, in the format it names."""
+    try:
+        preset = _preset(args.preset)
+        image = load_image(Path(args.source))
+        fmt = args.format or format_of(args.output)
+        export = write_render(image, preset, args.output, fmt)
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
+        preset = _preset(args.preset)
+        source = Path(args.source)
+        files = _batch_inputs(source, _extensions(args.ext), args.recursive)
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    fmt = args.format or "png"
+    written: list[str] = []
+    errors: list[str] = []
+    for item in files:
+        destination = _destination(Path(args.output), item, source, fmt, args.recursive)
+        try:
+            export = write_render(load_image(item), preset, destination, fmt)
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
+    """Describe one preset: its seed, its effect stack, its masks and its pipeline."""
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
+        export = write_render(image, _preset(args.preset), args.output,
+                              args.format or format_of(args.output))
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    except (BridgeError, OSError) as exc:
+        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    finally:
+        client.disconnect()
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
+        rgb8 = render_preset(load_image(Path(args.source)), _preset(args.preset))
+        object_id = client.place_as_layer(color.to_pil(rgb8), args.name)
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    except (BridgeError, OSError) as exc:
+        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    finally:
+        client.disconnect()
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
+                        help="png (default: from --out)")
+    parser.add_argument("--json", action="store_true", help="print a JSON result")
+
+
+def _build_parser() -> argparse.ArgumentParser:
+    """Return the argument parser carrying the four verbs of §8."""
+    parser = _Parser(prog=PROG, description="Lattice Glitch command line.")
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
+    push.add_argument("--name", default="Lattice Glitch", help="layer or object name")
+    push.add_argument("--json", action="store_true", help="print a JSON result")
+    push.set_defaults(handler=_cmd_bridge_push)
+    return parser
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Run the command line and return its exit code; no traceback ever escapes."""
+    _Parser._argv = list(argv) if argv is not None else sys.argv[1:]
+    parser = _build_parser()
+    try:
+        args = parser.parse_args(argv)
+    except SystemExit as exc:
+        return int(exc.code or EXIT_OK)
+    try:
+        return int(args.handler(args))
+    except UsageError as exc:
+        return _failure(args, str(exc), EXIT_USAGE)
+    except DocumentError as exc:
+        return _failure(args, str(exc), EXIT_RENDER)
+    except (BridgeError, OSError) as exc:
+        return _failure(args, f"{args.command} failed: {exc}", EXIT_BRIDGE)
+    except Exception as exc:  # noqa: BLE001 - §8 forbids a traceback on stderr
+        return _failure(args, f"{args.command} failed: {exc}", EXIT_RENDER)
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/lattice_glitch/document.py b/lattice_glitch/document.py
new file mode 100644
index 0000000..c768cfe
--- /dev/null
+++ b/lattice_glitch/document.py
@@ -0,0 +1,231 @@
+"""The single render path of Lattice Glitch: load, stack render, export bytes (G9, §8).
+
+Every entry point goes through this module. ``render_rgb8`` runs the core pipeline's
+steps 1 to 5 (``prepare_image``), then applies the effect stack itself so the §18
+per-module seed streams and masks are honoured — ``pipeline.render`` keeps the 1.0
+seeding rule and knows no masks, so the glitch chain cannot ride on it. The CLI and
+the GUI export call the same function with the same inputs, so their PNG bytes are
+identical by construction (G9). Glitch renders continuous images only: algorithm and
+palette stay null (§5 S1).
+"""
+
+from __future__ import annotations
+
+import io
+from collections.abc import Mapping
+from dataclasses import dataclass, field
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+
+import lattice_core.effects  # noqa: F401  (registers every effect a preset may name)
+from lattice_core import color, mask
+from lattice_core import pipeline as _pipeline
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.preset import Preset, to_pipeline_spec
+from lattice_core.registry import get_effect, resolve_params
+from lattice_core.seed import SeedController, module_seed
+from lattice_core.types import RGB8, Image
+
+FORMATS: tuple[str, ...] = ("png",)
+SUFFIXES: dict[str, str] = {"png": ".png"}
+
+
+class DocumentError(Exception):
+    """A typed failure of the document path: unreadable source, or an impossible render."""
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
+@dataclass(frozen=True)
+class RenderContext:
+    """The session side of one glitch render: mask ids, mask planes and stream seeds.
+
+    ``streams`` carries one seed per stack position (``SeedController.module_seed_for``),
+    so a worker thread renders an immutable snapshot of the session's locks; when it is
+    empty the render falls back on ``controller`` or on a fresh ``SeedController(seed)``.
+    """
+
+    mask_ids: tuple[str | None, ...] = ()
+    masks: Mapping[str, Image] = field(default_factory=dict)
+    streams: tuple[int, ...] = ()
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
+def fit_mask(plane: Image, shape: tuple[int, int]) -> Image:
+    """Resample a mask plane to shape: area-average down, bilinear up, exact when equal."""
+    data = np.ascontiguousarray(np.asarray(plane, dtype=np.float32))
+    if data.shape == shape:
+        return data
+    pil = PILImage.fromarray(data, mode="F")
+    resample = PILImage.Resampling.BOX if data.size >= shape[0] * shape[1] \
+        else PILImage.Resampling.BILINEAR
+    resized = pil.resize((shape[1], shape[0]), resample)
+    return np.ascontiguousarray(np.clip(np.asarray(resized, dtype=np.float32), 0.0, 1.0))
+
+
+def _module_rng(position: int, context: RenderContext,
+                controller: SeedController) -> np.random.Generator:
+    """Return the generator of one stack position: snapshot stream first, controller next."""
+    if position < len(context.streams):
+        return np.random.default_rng(context.streams[position])
+    return controller.rng(position)
+
+
+def _render(image: Image, spec: PipelineSpec, context: RenderContext,
+            controller: SeedController | None) -> RGB8:
+    """Run steps 1 to 5, then the masked, per-module-seeded effect stack."""
+    if spec.algorithm_id is not None or spec.palette is not None:
+        raise DocumentError(
+            "glitch renders continuous images: algorithm and palette must both be null"
+        )
+    work = _pipeline.prepare_image(image, spec)
+    controller = controller if controller is not None else SeedController(spec.seed)
+    for position, instance in enumerate(spec.post_effects):
+        if not instance.enabled:
+            continue
+        info = get_effect(instance.effect_id)
+        params = resolve_params(info.params, instance.params)
+        rng = _module_rng(position, context, controller)
+        before = work
+        out = np.ascontiguousarray(
+            np.clip(info.fn(work, params, rng), 0.0, 1.0), dtype=np.float32
+        )
+        mask_id = context.mask_ids[position] if position < len(context.mask_ids) else None
+        if mask_id is not None:
+            if mask_id not in context.masks:
+                raise DocumentError(f"mask {mask_id!r} is not in the document")
+            plane = fit_mask(context.masks[mask_id], work.shape[:2])
+            out = mask.apply(before, out, mask=plane)
+        work = out
+    return color.to_rgb8(work)
+
+
+def render_rgb8(image: Image, spec: PipelineSpec, *, context: RenderContext | None = None,
+                controller: SeedController | None = None) -> RGB8:
+    """Render image through the glitch path, raising DocumentError on any failure."""
+    try:
+        return _render(image, spec, context or RenderContext(), controller)
+    except DocumentError:
+        raise
+    except Exception as exc:  # noqa: BLE001 - every render failure is a render error (§8)
+        raise DocumentError(f"render failed: {exc}") from None
+
+
+def _entry_stream(entry: dict, seed: int, position: int) -> int:
+    """Return the frozen stream of one effect entry, or the seed-derived default."""
+    if "seed" not in entry:
+        return module_seed(seed, position)
+    value = entry["seed"]
+    if isinstance(value, bool) or not isinstance(value, int):
+        raise ValueError(f"effect stream seed must be an integer, got {value!r}")
+    return value
+
+
+def context_of_preset(preset: Preset) -> RenderContext:
+    """Return the mask ids, planes and per-slot stream seeds a v3 preset carries."""
+    post = [entry for entry in preset.effects if entry.get("stage", "post") != "pre"]
+    mask_ids = tuple(entry.get("mask") for entry in post)
+    try:
+        streams = tuple(_entry_stream(entry, preset.seed, position)
+                        for position, entry in enumerate(post))
+        planes = mask.resolve_masks(preset.masks)
+    except (OSError, ValueError) as exc:
+        raise DocumentError(f"cannot resolve the preset context: {exc}") from None
+    return RenderContext(mask_ids=mask_ids, masks=planes, streams=streams)
+
+
+def render_preset(image: Image, preset: Preset) -> RGB8:
+    """Render image with a parsed v3 preset: its seed, its stack and its masks."""
+    return render_rgb8(image, to_pipeline_spec(preset), context=context_of_preset(preset))
+
+
+def png_bytes(rgb8: RGB8) -> bytes:
+    """Return rgb8 encoded as a PNG file byte for byte as the GUI export writes it."""
+    buffer = io.BytesIO()
+    color.to_pil(rgb8).save(buffer, format="PNG")
+    return buffer.getvalue()
+
+
+def export_bytes(image: Image, preset: Preset, fmt: str = "png") -> tuple[bytes, list[str]]:
+    """Return the encoded output of preset in fmt, with the warnings of that export."""
+    if fmt not in FORMATS:
+        raise DocumentError(f"unknown format {fmt!r}; expected one of {FORMATS}")
+    return png_bytes(render_preset(image, preset)), []
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
+def write_render(image: Image, preset: Preset, path: str | Path, fmt: str = "png") -> Export:
+    """Render preset and write it to path in fmt, creating the parent directories."""
+    payload, warnings = export_bytes(image, preset, fmt)
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
+    """Return the export format named by path's suffix; a suffix outside FORMATS raises.
+
+    A bare path (no suffix) still defaults to png, but a named suffix is a contract:
+    writing PNG bytes into ``photo.jpg`` would lie about the file, so the caller hears
+    a ``DocumentError`` naming the suffix instead of a silent fallback.
+    """
+    suffix = Path(path).suffix.lower().lstrip(".")
+    if suffix and suffix not in FORMATS:
+        raise DocumentError(
+            f"cannot infer the format of {Path(path).name!r}: suffix '.{suffix}' is not"
+            f" one of {', '.join(FORMATS)}"
+        )
+    return suffix if suffix in FORMATS else "png"
+
+
+__all__ = [
+    "FORMATS",
+    "SUFFIXES",
+    "DocumentError",
+    "Export",
+    "RenderContext",
+    "context_of_preset",
+    "export_bytes",
+    "fit_mask",
+    "format_of",
+    "load_image",
+    "png_bytes",
+    "render_preset",
+    "render_rgb8",
+    "target_path",
+    "write_render",
+]
diff --git a/lattice_glitch/effects_panel.py b/lattice_glitch/effects_panel.py
new file mode 100644
index 0000000..5f6edd7
--- /dev/null
+++ b/lattice_glitch/effects_panel.py
@@ -0,0 +1,292 @@
+"""Effect stack panel of the Glitch shell: add, reorder, enable, tune and mask (§12-§18).
+
+The list shows the stack in render order; the form below edits the selected slot with
+the registry's own parameter specs, and a combo assigns one of the document's masks.
+Every edit mutates the shared ``EffectStack`` and emits ``changed`` once, so the window
+rebuilds the spec and requests a preview; nothing renders inside the panel.
+"""
+
+from __future__ import annotations
+
+from PySide6.QtCore import Qt, Signal
+from PySide6.QtWidgets import (
+    QCheckBox,
+    QComboBox,
+    QHBoxLayout,
+    QLabel,
+    QListWidget,
+    QListWidgetItem,
+    QPushButton,
+    QVBoxLayout,
+    QWidget,
+)
+
+import lattice_core.effects  # noqa: F401  (registers every effect the combo offers)
+from lattice_core.effects.ntsc import LABEL_NOTES, PRESET_NAMES, params_for_mode
+from lattice_core.effects.ntsc import preset as ntsc_preset
+from lattice_core.registry import get_effect, list_effects
+from lattice_core.types import ParamSpec
+from lattice_glitch.params import ParamForm
+from lattice_glitch.stack import EffectStack
+
+NO_MASK = "No mask"
+NTSC_ID = "ntsc"
+
+
+class EffectsPanel(QWidget):
+    """Stack list, add/remove/move buttons, mask assignment and the parameter form."""
+
+    changed = Signal()
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Build the stack controls over an empty stack."""
+        super().__init__(parent)
+        self.setObjectName("effects_panel")
+        self._stack = EffectStack()
+        self._mask_ids: list[str] = []
+        self._loading = False
+        self.add_box = QComboBox(self)
+        self.add_box.setObjectName("effect_add_box")
+        for info in list_effects():
+            self.add_box.addItem(info.name, info.id)
+        self.add_button = QPushButton("Add", self)
+        self.add_button.setObjectName("effect_add")
+        add_row = QHBoxLayout()
+        add_row.addWidget(self.add_box, 1)
+        add_row.addWidget(self.add_button)
+        self.list = QListWidget(self)
+        self.list.setObjectName("effect_list")
+        self.up_button = QPushButton("Up", self)
+        self.up_button.setObjectName("effect_up")
+        self.down_button = QPushButton("Down", self)
+        self.down_button.setObjectName("effect_down")
+        self.remove_button = QPushButton("Remove", self)
+        self.remove_button.setObjectName("effect_remove")
+        move_row = QHBoxLayout()
+        for button in (self.up_button, self.down_button, self.remove_button):
+            move_row.addWidget(button)
+        self.mask_box = QComboBox(self)
+        self.mask_box.setObjectName("effect_mask_box")
+        mask_row = QHBoxLayout()
+        mask_row.addWidget(QLabel("Mask", self))
+        mask_row.addWidget(self.mask_box, 1)
+        self.form = ParamForm(parent=self)
+        self.form.setObjectName("effect_params")
+        self.ntsc_row = self._build_ntsc_row()
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(8, 8, 8, 8)
+        layout.addLayout(add_row)
+        layout.addWidget(self.list, 1)
+        layout.addLayout(move_row)
+        layout.addLayout(mask_row)
+        layout.addWidget(self.ntsc_row)
+        layout.addWidget(self.form)
+        self.add_button.clicked.connect(lambda: self.add_effect())
+        self.up_button.clicked.connect(lambda: self.move_selected(-1))
+        self.down_button.clicked.connect(lambda: self.move_selected(1))
+        self.remove_button.clicked.connect(self.remove_selected)
+        self.list.currentRowChanged.connect(self._on_selection)
+        self.list.itemChanged.connect(self._on_item_changed)
+        self.mask_box.currentIndexChanged.connect(self._on_mask)
+        self.form.changed.connect(self._on_params)
+        self.ntsc_advanced.toggled.connect(self._on_ntsc_mode)
+        self.ntsc_preset_box.currentIndexChanged.connect(self._on_ntsc_preset)
+        self.set_mask_ids([])
+
+    def _build_ntsc_row(self) -> QWidget:
+        """Build the §16 usability row: six named presets and the simple/advanced toggle."""
+        row = QWidget(self)
+        row.setObjectName("ntsc_row")
+        self.ntsc_preset_box = QComboBox(row)
+        self.ntsc_preset_box.setObjectName("ntsc_preset")
+        for name in PRESET_NAMES:
+            self.ntsc_preset_box.addItem(name, name)
+        self.ntsc_preset_box.setToolTip("Apply one of the six named NTSC / VHS presets.")
+        self.ntsc_advanced = QCheckBox("Advanced", row)
+        self.ntsc_advanced.setObjectName("ntsc_advanced")
+        self.ntsc_advanced.setToolTip("Show all 14 signal parameters instead of the four sliders.")
+        layout = QHBoxLayout(row)
+        layout.setContentsMargins(0, 0, 0, 0)
+        layout.addWidget(self.ntsc_preset_box, 1)
+        layout.addWidget(self.ntsc_advanced)
+        row.hide()
+        return row
+
+    def stack(self) -> EffectStack:
+        """Return the stack this panel edits (the window's own object)."""
+        return self._stack
+
+    def effect_choices(self) -> list[str]:
+        """Return the effect ids the add combo offers, in display order."""
+        return [str(self.add_box.itemData(i)) for i in range(self.add_box.count())]
+
+    def load(self, stack: EffectStack, mask_ids: list[str]) -> None:
+        """Adopt a stack and the available mask ids, rebuilding the list silently."""
+        self._stack = stack
+        self.set_mask_ids(mask_ids)
+        self.refresh()
+
+    def set_mask_ids(self, mask_ids: list[str]) -> None:
+        """Offer exactly these mask ids, keeping the selection; drop orphan assignments."""
+        self._mask_ids = list(mask_ids)
+        for position, mask_id in enumerate(self._stack.mask_ids()):
+            if mask_id is not None and mask_id not in self._mask_ids:
+                self._stack.set_mask(position, None)
+        current = self.mask_box.currentData()
+        self._loading = True
+        try:
+            self.mask_box.clear()
+            self.mask_box.addItem(NO_MASK, None)
+            for mask_id in self._mask_ids:
+                self.mask_box.addItem(mask_id, mask_id)
+            index = self.mask_box.findData(current)
+            self.mask_box.setCurrentIndex(max(0, index))
+        finally:
+            self._loading = False
+
+    def refresh(self) -> None:
+        """Rebuild the list from the stack, keeping the current row when possible."""
+        row = self.list.currentRow()
+        self._loading = True
+        try:
+            self.list.clear()
+            for position, slot in enumerate(self._stack.slots()):
+                info = get_effect(slot.instance.effect_id)
+                item = QListWidgetItem(f"{position + 1}. {info.name}")
+                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
+                state = Qt.CheckState.Checked if slot.instance.enabled else Qt.CheckState.Unchecked
+                item.setCheckState(state)
+                self.list.addItem(item)
+            if self.list.count():
+                self.list.setCurrentRow(min(max(0, row), self.list.count() - 1))
+        finally:
+            self._loading = False
+        self._on_selection(self.list.currentRow())
+
+    def selected_index(self) -> int | None:
+        """Return the selected stack position, or None when the list is empty."""
+        row = self.list.currentRow()
+        return None if row < 0 else row
+
+    def add_effect(self, effect_id: str | None = None, params: dict | None = None) -> int:
+        """Append the chosen effect (or effect_id) to the stack and select it."""
+        chosen = effect_id if effect_id is not None else str(self.add_box.currentData())
+        position = self._stack.add(chosen, params)
+        self.refresh()
+        self.list.setCurrentRow(position)
+        self.changed.emit()
+        return position
+
+    def remove_selected(self) -> None:
+        """Remove the selected slot, if any, and emit changed."""
+        row = self.selected_index()
+        if row is None:
+            return
+        self._stack.remove(row)
+        self.refresh()
+        self.changed.emit()
+
+    def move_selected(self, delta: int) -> None:
+        """Move the selected slot by delta positions, clamped to the stack bounds."""
+        row = self.selected_index()
+        if row is None:
+            return
+        target = max(0, min(len(self._stack) - 1, row + delta))
+        if target == row:
+            return
+        self._stack.move(row, target)
+        self.refresh()
+        self.list.setCurrentRow(target)
+        self.changed.emit()
+
+    def _on_selection(self, row: int) -> None:
+        """Load the parameter form and mask combo of the selected slot."""
+        self._loading = True
+        try:
+            if row < 0 or row >= len(self._stack):
+                self.form.set_specs(())
+                self.ntsc_row.hide()
+                self.mask_box.setCurrentIndex(0)
+                return
+            slot = self._stack.slots()[row]
+            effect_id = slot.instance.effect_id
+            self.ntsc_row.setVisible(effect_id == NTSC_ID)
+            specs = self._ntsc_specs() if effect_id == NTSC_ID else get_effect(effect_id).params
+            self.form.set_specs(specs)
+            self.form.set_values(slot.instance.params)
+            if effect_id == NTSC_ID:
+                self._ntsc_tooltips(specs)
+            index = self.mask_box.findData(slot.mask_id)
+            self.mask_box.setCurrentIndex(max(0, index))
+        finally:
+            self._loading = False
+
+    def _ntsc_specs(self) -> tuple[ParamSpec, ...]:
+        """Return the §16 parameters of the current mode: four sliders, or all fourteen."""
+        return params_for_mode("advanced" if self.ntsc_advanced.isChecked() else "simple")
+
+    def _ntsc_tooltips(self, specs: tuple[ParamSpec, ...]) -> None:
+        """Give every ntsc editor the honest reading of its catalogue label."""
+        for spec in specs:
+            note = LABEL_NOTES.get(spec.id, "")
+            if note:
+                self.form.widget(spec.id).setToolTip(note)
+
+    def _on_ntsc_mode(self, _checked: bool) -> None:
+        """Rebuild the ntsc form for the toggled mode, keeping every current value."""
+        if self._loading:
+            return
+        row = self.selected_index()
+        if row is None or self._stack.effect_ids()[row] != NTSC_ID:
+            return
+        values = dict(self._stack.params_of(row))
+        values.update(self.form.values())
+        specs = self._ntsc_specs()
+        self.form.set_specs(specs)
+        self.form.set_values(values)
+        self._ntsc_tooltips(specs)
+
+    def _on_ntsc_preset(self, index: int) -> None:
+        """Apply the chosen named preset over the slot's parameters and emit changed."""
+        if self._loading or index < 0:
+            return
+        row = self.selected_index()
+        if row is None or self._stack.effect_ids()[row] != NTSC_ID:
+            return
+        values = dict(self._stack.params_of(row))
+        values.update(ntsc_preset(str(self.ntsc_preset_box.itemText(index))))
+        self._stack.set_params(row, values)
+        self.form.set_values(values)
+        self.changed.emit()
+
+    def _on_item_changed(self, item: QListWidgetItem) -> None:
+        """Mirror a list check state into the slot's enabled flag."""
+        if self._loading:
+            return
+        row = self.list.row(item)
+        self._stack.set_enabled(row, item.checkState() == Qt.CheckState.Checked)
+        self.changed.emit()
+
+    def _on_params(self) -> None:
+        """Merge the form's values into the selected slot (hidden params kept) and emit."""
+        row = self.selected_index()
+        if row is None or self._loading:
+            return
+        params = dict(self._stack.params_of(row))
+        params.update(self.form.values())
+        self._stack.set_params(row, params)
+        self.changed.emit()
+
+    def _on_mask(self, _index: int) -> None:
+        """Assign the combo's mask id to the selected slot and emit changed."""
+        if self._loading:
+            return
+        row = self.selected_index()
+        if row is None:
+            return
+        data = self.mask_box.currentData()
+        self._stack.set_mask(row, None if data is None else str(data))
+        self.changed.emit()
+
+
+__all__ = ["NO_MASK", "NTSC_ID", "EffectsPanel"]
diff --git a/lattice_glitch/export_actions.py b/lattice_glitch/export_actions.py
new file mode 100644
index 0000000..5a114c6
--- /dev/null
+++ b/lattice_glitch/export_actions.py
@@ -0,0 +1,106 @@
+"""Export controller of the Glitch shell: full-resolution export and preset saving.
+
+The window owns one instance and its toolbar calls it. Every render goes through
+:func:`lattice_glitch.document.render_rgb8` with the window's render context and seed
+controller — the same function, masks and streams the CLI uses for the same preset —
+so the GUI cannot drift from the CLI (G9). PNG export goes through the shared
+``ExportDialog``, restricted to the one raster format this application writes.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+from typing import TYPE_CHECKING
+
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import RGB8, Image
+from lattice_core.ui import ExportDialog, ExportError
+from lattice_glitch import presets as preset_tools
+from lattice_glitch.document import (
+    DocumentError,
+    format_of,
+    png_bytes,
+    render_rgb8,
+    target_path,
+)
+
+if TYPE_CHECKING:
+    from lattice_glitch.window import MainWindow
+
+NO_SOURCE = "Load an image before rendering."
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
+        """Render spec on image through the CLI's function (G9); a DocumentError becomes
+        an ExportError so the dialog's Qt slot reports it instead of crashing."""
+        window = self.window
+        try:
+            return render_rgb8(image, spec, context=window.render_context(),
+                               controller=window.controller)
+        except DocumentError as exc:
+            raise ExportError(str(exc)) from exc
+
+    def dialog(self) -> list[Path]:
+        """Open the shared full-resolution export dialog, PNG only, and return the files."""
+        window = self.window
+        if window.source is None:
+            window.report(NO_SOURCE)
+            return []
+        source = window.source
+        dialog = ExportDialog(source, window.spec, window,
+                              render_full=lambda spec: self.render_full(source, spec),
+                              settings=window.settings())
+        dialog.format_box.clear()
+        dialog.format_box.addItem("PNG", "png")
+        dialog.exec()
+        if dialog.written:
+            window.status(f"Exported {dialog.written[0].name}")
+        return list(dialog.written)
+
+    def to(self, path: str | Path) -> dict:
+        """Write the current full-resolution render to path as PNG."""
+        window = self.window
+        if window.source is None:
+            raise DocumentError(NO_SOURCE)
+        fmt = format_of(path)
+        try:
+            payload = png_bytes(self.render_full(window.source, window.spec))
+        except ExportError as exc:
+            raise DocumentError(str(exc)) from None
+        target = target_path(path, fmt)
+        try:
+            target.parent.mkdir(parents=True, exist_ok=True)
+            target.write_bytes(payload)
+        except OSError as exc:
+            raise DocumentError(f"cannot write {target}: {exc}") from None
+        return {"file": str(target), "format": fmt, "warnings": []}
+
+    def save_preset(self, path: str | Path) -> Path | None:
+        """Write the current document as a v3 preset and remember it as the applied one."""
+        window = self.window
+        streams = window.render_context().streams
+        locked_streams = {i: streams[i] for i in sorted(window.controller.locked())
+                          if i < len(streams)}
+        try:
+            target = preset_tools.save_spec(
+                path, window.spec, stack=window.effect_stack,
+                masks=window.mask_panel.planes(), locked_streams=locked_streams,
+            )
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
+__all__ = ["ExportController", "NO_SOURCE"]
diff --git a/lattice_glitch/hosts.py b/lattice_glitch/hosts.py
new file mode 100644
index 0000000..f7a41a6
--- /dev/null
+++ b/lattice_glitch/hosts.py
@@ -0,0 +1,22 @@
+"""Host discovery of Lattice Glitch: the single §7 probe, CLI and GUI share it.
+
+The core's ``ArtCraftClient.discover`` already answers None for a host that is not
+running; this module adds the typed-error guard the callers need, so every user of the
+bridge resolves the host the same way and there is no second copy to drift.
+"""
+
+from __future__ import annotations
+
+from lattice_core.bridge import HOSTS, ArtCraftClient, BridgeError
+
+__all__ = ["HOSTS", "discover"]
+
+
+def discover(host: str) -> ArtCraftClient | None:
+    """Return a live client for host, or None for every way a host can be absent (§7)."""
+    if host not in HOSTS:
+        return None
+    try:
+        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
+    except (BridgeError, OSError, ValueError):
+        return None
diff --git a/lattice_glitch/mask_painter.py b/lattice_glitch/mask_painter.py
new file mode 100644
index 0000000..5c129cc
--- /dev/null
+++ b/lattice_glitch/mask_painter.py
@@ -0,0 +1,129 @@
+"""Mask painter of the Glitch shell: a zoom-to-fit greyscale plane, paintable (§18).
+
+The painter stamps a circular brush in mask coordinates; 0 keeps the source and 1 keeps
+the effect. Planes are kept at the 8-bit precision of their PNG storage, so the GUI
+render and a preset reload agree byte for byte (G9).
+"""
+
+from __future__ import annotations
+
+import numpy as np
+from PySide6.QtCore import QPoint, Qt, Signal
+from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPaintEvent
+from PySide6.QtWidgets import QWidget
+
+from lattice_core import mask
+from lattice_core.types import Image
+
+DEFAULT_RADIUS = 8
+
+
+def quantize(plane: Image) -> Image:
+    """Return the plane at the 8-bit precision of its PNG storage, in [0, 1]."""
+    return mask.from_png(mask.to_png(plane))
+
+
+class MaskPainter(QWidget):
+    """Zoom-to-fit greyscale view of one mask plane, paintable with a circular brush."""
+
+    painted = Signal()
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Start with no plane, a white brush and the default radius."""
+        super().__init__(parent)
+        self.setObjectName("mask_painter")
+        self.setMinimumSize(220, 180)
+        self._plane: Image | None = None
+        self._value = 1.0
+        self._radius = DEFAULT_RADIUS
+        self._painting = False
+
+    def set_plane(self, plane: Image | None) -> None:
+        """Adopt a mask plane (or None) and repaint."""
+        self._plane = plane
+        self.update()
+
+    def plane(self) -> Image | None:
+        """Return the plane being painted, or None."""
+        return self._plane
+
+    def set_brush(self, value: float, radius: int) -> None:
+        """Set the stamp value (1 brush, 0 eraser) and the radius in mask pixels."""
+        self._value = float(value)
+        self._radius = max(1, int(radius))
+
+    def paint_at(self, x: int, y: int) -> None:
+        """Stamp the brush at mask coordinates (x, y), clipping at the plane edges."""
+        plane = self._plane
+        if plane is None:
+            return
+        height, width = plane.shape
+        radius = self._radius
+        x0, x1 = max(0, x - radius), min(width, x + radius + 1)
+        y0, y1 = max(0, y - radius), min(height, y + radius + 1)
+        if x0 >= x1 or y0 >= y1:
+            return
+        yy, xx = np.ogrid[y0:y1, x0:x1]
+        inside = (xx - x) ** 2 + (yy - y) ** 2 <= radius * radius
+        plane[y0:y1, x0:x1][inside] = self._value
+        self.update()
+        self.painted.emit()
+
+    def _geometry(self) -> tuple[float, float, float] | None:
+        """Return the (scale, offset_x, offset_y) that fits the plane in the widget."""
+        if self._plane is None:
+            return None
+        height, width = self._plane.shape
+        scale = min(self.width() / width, self.height() / height)
+        return scale, (self.width() - width * scale) / 2, (self.height() - height * scale) / 2
+
+    def _to_mask(self, position: QPoint) -> tuple[int, int] | None:
+        """Map a widget position to mask coordinates, or None outside the plane."""
+        geometry = self._geometry()
+        if geometry is None or self._plane is None:
+            return None
+        scale, ox, oy = geometry
+        x, y = int((position.x() - ox) / scale), int((position.y() - oy) / scale)
+        height, width = self._plane.shape
+        if not (0 <= x < width and 0 <= y < height):
+            return None
+        return x, y
+
+    def paintEvent(self, event: QPaintEvent) -> None:
+        """Draw the plane as greyscale, letterboxed on a dark background."""
+        painter = QPainter(self)
+        painter.fillRect(self.rect(), Qt.GlobalColor.darkGray)
+        geometry = self._geometry()
+        if geometry is not None and self._plane is not None:
+            scale, ox, oy = geometry
+            height, width = self._plane.shape
+            data = np.ascontiguousarray((self._plane * 255.0).round().astype(np.uint8))
+            image = QImage(data.data, width, height, width, QImage.Format.Format_Grayscale8)
+            scaled = image.scaled(int(width * scale), int(height * scale),
+                                  Qt.AspectRatioMode.IgnoreAspectRatio,
+                                  Qt.TransformationMode.SmoothTransformation)
+            painter.drawImage(int(ox), int(oy), scaled)
+        painter.end()
+
+    def mousePressEvent(self, event: QMouseEvent) -> None:
+        """Start painting on a left-button press inside the plane."""
+        if event.button() == Qt.MouseButton.LeftButton:
+            point = self._to_mask(event.position().toPoint())
+            if point is not None:
+                self._painting = True
+                self.paint_at(*point)
+
+    def mouseMoveEvent(self, event: QMouseEvent) -> None:
+        """Continue the stroke while the left button is held."""
+        if self._painting:
+            point = self._to_mask(event.position().toPoint())
+            if point is not None:
+                self.paint_at(*point)
+
+    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
+        """Finish the stroke when the left button is released."""
+        if event.button() == Qt.MouseButton.LeftButton:
+            self._painting = False
+
+
+__all__ = ["DEFAULT_RADIUS", "MaskPainter", "quantize"]
diff --git a/lattice_glitch/mask_panel.py b/lattice_glitch/mask_panel.py
new file mode 100644
index 0000000..45fe2f0
--- /dev/null
+++ b/lattice_glitch/mask_panel.py
@@ -0,0 +1,308 @@
+"""Mask panel of the Glitch shell: paint, generate, import and export §18 masks.
+
+A mask is a greyscale plane where 0 keeps the source and 1 keeps the effect. The painter
+stamps a circular brush in mask coordinates; gradient and luminance-range generators
+produce planes without a mouse. Planes are kept at the 8-bit precision of their PNG
+storage, so the GUI render and a preset reload agree byte for byte (G9).
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import numpy as np
+from PySide6.QtCore import Signal
+from PySide6.QtWidgets import (
+    QComboBox,
+    QDoubleSpinBox,
+    QFileDialog,
+    QHBoxLayout,
+    QLabel,
+    QListWidget,
+    QPushButton,
+    QSpinBox,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_core import color, mask
+from lattice_core.types import Image
+from lattice_glitch.document import fit_mask
+from lattice_glitch.mask_painter import DEFAULT_RADIUS, MaskPainter, quantize
+
+MASK_FILTER = "Mask PNG (*.png);;All files (*)"
+NO_SOURCE = "Load an image before creating or generating a mask."
+
+
+class MaskPanel(QWidget):
+    """Mask list, painter, generators and PNG import/export of one document."""
+
+    masks_changed = Signal()
+    mask_painted = Signal(str)
+    failed = Signal(str)
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Build the list, the painter and the tool rows over an empty mask set."""
+        super().__init__(parent)
+        self.setObjectName("mask_panel")
+        self._masks: dict[str, Image] = {}
+        self._active: str | None = None
+        self._source: Image | None = None
+        self._loading = False
+        self.list = QListWidget(self)
+        self.list.setObjectName("mask_list")
+        self.list.setMaximumHeight(96)
+        self.new_button = QPushButton("New", self)
+        self.import_button = QPushButton("Import…", self)
+        self.export_button = QPushButton("Export…", self)
+        self.delete_button = QPushButton("Delete", self)
+        list_row = QHBoxLayout()
+        for button in (self.new_button, self.import_button,
+                       self.export_button, self.delete_button):
+            list_row.addWidget(button)
+        self.painter = MaskPainter(self)
+        self.tool_box = QComboBox(self)
+        self.tool_box.setObjectName("mask_tool")
+        self.tool_box.addItem("Brush", 1.0)
+        self.tool_box.addItem("Eraser", 0.0)
+        self.radius_spin = QSpinBox(self)
+        self.radius_spin.setObjectName("mask_radius")
+        self.radius_spin.setRange(1, 256)
+        self.radius_spin.setValue(DEFAULT_RADIUS)
+        tool_row = QHBoxLayout()
+        tool_row.addWidget(QLabel("Tool", self))
+        tool_row.addWidget(self.tool_box)
+        tool_row.addWidget(QLabel("Radius", self))
+        tool_row.addWidget(self.radius_spin)
+        self.clear_button = QPushButton("Clear", self)
+        self.fill_button = QPushButton("Fill", self)
+        self.gradient_box = QComboBox(self)
+        self.gradient_box.addItem("Horizontal", "h")
+        self.gradient_box.addItem("Vertical", "v")
+        self.gradient_button = QPushButton("Gradient", self)
+        self.lo_spin = QDoubleSpinBox(self)
+        self.lo_spin.setRange(0.0, 1.0)
+        self.lo_spin.setSingleStep(0.05)
+        self.lo_spin.setValue(0.2)
+        self.hi_spin = QDoubleSpinBox(self)
+        self.hi_spin.setRange(0.0, 1.0)
+        self.hi_spin.setSingleStep(0.05)
+        self.hi_spin.setValue(0.8)
+        self.luma_button = QPushButton("From luminance", self)
+        gen_row, luma_row = self._build_generators()
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(8, 8, 8, 8)
+        layout.addWidget(self.list)
+        layout.addLayout(list_row)
+        layout.addWidget(self.painter, 1)
+        layout.addLayout(tool_row)
+        layout.addLayout(gen_row)
+        layout.addLayout(luma_row)
+        self._connect()
+
+    def _build_generators(self) -> tuple[QHBoxLayout, QHBoxLayout]:
+        """Lay out the clear/fill/gradient row and the luminance-range row."""
+        gen_row = QHBoxLayout()
+        for widget in (self.clear_button, self.fill_button,
+                       self.gradient_box, self.gradient_button):
+            gen_row.addWidget(widget)
+        luma_row = QHBoxLayout()
+        luma_row.addWidget(QLabel("Lo", self))
+        luma_row.addWidget(self.lo_spin)
+        luma_row.addWidget(QLabel("Hi", self))
+        luma_row.addWidget(self.hi_spin)
+        luma_row.addWidget(self.luma_button)
+        return gen_row, luma_row
+
+    def _connect(self) -> None:
+        """Wire every control to its slot."""
+        self.list.currentRowChanged.connect(self._on_selection)
+        self.new_button.clicked.connect(lambda: self.new_mask())
+        self.import_button.clicked.connect(self.import_dialog)
+        self.export_button.clicked.connect(self.export_dialog)
+        self.delete_button.clicked.connect(self.delete_active)
+        self.tool_box.currentIndexChanged.connect(self._sync_brush)
+        self.radius_spin.valueChanged.connect(self._sync_brush)
+        self.painter.painted.connect(self._on_painted)
+        self.clear_button.clicked.connect(lambda: self.generate("clear"))
+        self.fill_button.clicked.connect(lambda: self.generate("fill"))
+        self.gradient_button.clicked.connect(
+            lambda: self.generate(str(self.gradient_box.currentData())))
+        self.luma_button.clicked.connect(lambda: self.generate("luma"))
+
+    # --- state -------------------------------------------------------------------
+
+    def planes(self) -> dict[str, Image]:
+        """Return the mask planes of the document, keyed by id."""
+        return self._masks
+
+    def mask_ids(self) -> list[str]:
+        """Return the mask ids in list order."""
+        return list(self._masks)
+
+    def active_id(self) -> str | None:
+        """Return the id of the mask being painted, or None."""
+        return self._active
+
+    def set_source(self, source: Image | None) -> None:
+        """Adopt the document source the generators read and new masks size from."""
+        self._source = source
+
+    def set_planes(self, planes: dict[str, Image]) -> None:
+        """Adopt a whole mask set (quantized), rebuilding the list silently."""
+        self._masks = {str(key): quantize(np.asarray(plane, dtype=np.float32))
+                       for key, plane in planes.items()}
+        self._refresh()
+        self.masks_changed.emit()
+
+    def _refresh(self) -> None:
+        """Rebuild the list from the mask set, keeping the active id when possible."""
+        self._loading = True
+        try:
+            self.list.clear()
+            for mask_id in self._masks:
+                self.list.addItem(mask_id)
+            if self._active in self._masks:
+                self.list.setCurrentRow(list(self._masks).index(self._active))
+            elif self.list.count():
+                self.list.setCurrentRow(0)
+            else:
+                self._active = None
+                self.painter.set_plane(None)
+        finally:
+            self._loading = False
+        self._on_selection(self.list.currentRow())
+
+    def _on_selection(self, row: int) -> None:
+        """Point the painter at the selected mask."""
+        if self._loading:
+            return
+        ids = list(self._masks)
+        self._active = ids[row] if 0 <= row < len(ids) else None
+        self.painter.set_plane(None if self._active is None else self._masks[self._active])
+        self._sync_brush()
+
+    def _sync_brush(self, *_args: object) -> None:
+        """Mirror the tool combo and radius spin into the painter."""
+        self.painter.set_brush(float(self.tool_box.currentData()), self.radius_spin.value())
+
+    def _on_painted(self) -> None:
+        """Quantize the painted plane in place and announce the content change."""
+        if self._active is None:
+            return
+        plane = self._masks[self._active]
+        plane[:] = quantize(plane)
+        self.painter.update()
+        self.mask_painted.emit(self._active)
+
+    # --- operations --------------------------------------------------------------
+
+    def _next_id(self) -> str:
+        """Return the first unused mask_N id."""
+        index = 1
+        while f"mask_{index}" in self._masks:
+            index += 1
+        return f"mask_{index}"
+
+    def new_mask(self, mask_id: str | None = None) -> str | None:
+        """Create a black mask at the source size; without a source, report and stop."""
+        if self._source is None:
+            self.failed.emit(NO_SOURCE)
+            return None
+        name = mask_id or self._next_id()
+        height, width = self._source.shape[:2]
+        self._masks[name] = np.zeros((height, width), dtype=np.float32)
+        self._active = name
+        self._refresh()
+        self.masks_changed.emit()
+        return name
+
+    def import_dialog(self) -> None:
+        """Ask for a PNG mask and import it."""
+        path, _ = QFileDialog.getOpenFileName(self, "Import mask", str(Path.home()), MASK_FILTER)
+        if path:
+            self.import_png(Path(path))
+
+    def import_png(self, path: str | Path, mask_id: str | None = None) -> str | None:
+        """Read a PNG mask, fit it to the source when one is loaded, and adopt it."""
+        try:
+            plane = mask.import_png(path)
+        except (OSError, ValueError) as exc:
+            self.failed.emit(f"Cannot read mask {path}: {exc}")
+            return None
+        if self._source is not None:
+            plane = fit_mask(plane, self._source.shape[:2])
+        name = mask_id or Path(path).stem or self._next_id()
+        self._masks[name] = quantize(plane)
+        self._active = name
+        self._refresh()
+        self.masks_changed.emit()
+        return name
+
+    def export_dialog(self) -> None:
+        """Ask for a path and export the active mask as PNG."""
+        if self._active is None:
+            self.failed.emit("Select a mask first.")
+            return
+        target = str(Path.home() / f"{self._active}.png")
+        path, _ = QFileDialog.getSaveFileName(self, "Export mask", target, MASK_FILTER)
+        if path:
+            self.export_png(Path(path))
+
+    def export_png(self, path: str | Path) -> Path | None:
+        """Write the active mask as an 8-bit greyscale PNG."""
+        if self._active is None:
+            self.failed.emit("Select a mask first.")
+            return None
+        return mask.export_png(self._masks[self._active], path)
+
+    def delete_active(self) -> None:
+        """Drop the active mask from the document."""
+        if self._active is None:
+            return
+        del self._masks[self._active]
+        self._active = None
+        self._refresh()
+        self.masks_changed.emit()
+
+    def generate(self, kind: str) -> None:
+        """Replace the active plane with clear, fill, a gradient or a luminance range."""
+        if self._active is None:
+            self.failed.emit("Create or select a mask first.")
+            return
+        plane = self._masks[self._active]
+        height, width = plane.shape
+        if kind == "clear":
+            plane[:] = 0.0
+        elif kind == "fill":
+            plane[:] = 1.0
+        elif kind == "h":
+            plane[:] = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
+        elif kind == "v":
+            plane[:] = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
+        elif kind == "luma":
+            self._generate_luma(plane)
+            return
+        else:
+            self.failed.emit(f"Unknown mask generator {kind!r}.")
+            return
+        plane[:] = quantize(plane)
+        self.painter.update()
+        self.mask_painted.emit(self._active)
+
+    def _generate_luma(self, plane: Image) -> None:
+        """Fill plane from the source luminance between the lo and hi spins."""
+        if self._source is None:
+            self.failed.emit(NO_SOURCE)
+            return
+        lo, hi = self.lo_spin.value(), self.hi_spin.value()
+        if hi <= lo:
+            self.failed.emit("The luminance range needs hi > lo.")
+            return
+        lum = color.luminance(self._source)
+        plane[:] = quantize(np.clip((lum - lo) / (hi - lo), 0.0, 1.0))
+        self.painter.update()
+        self.mask_painted.emit(self._active)
+
+
+__all__ = ["MASK_FILTER", "MaskPanel"]
diff --git a/lattice_glitch/params.py b/lattice_glitch/params.py
new file mode 100644
index 0000000..9e2b056
--- /dev/null
+++ b/lattice_glitch/params.py
@@ -0,0 +1,244 @@
+"""Parameter form of the Glitch shell: one editor per registry ParamSpec.
+
+The form is built from the effect registry itself, so every registered parameter of
+every effect gets an editor with the registry's own bounds and defaults; no parameter
+table is duplicated in the application.
+"""
+
+from __future__ import annotations
+
+from PySide6.QtCore import Qt, Signal
+from PySide6.QtWidgets import (
+    QCheckBox,
+    QComboBox,
+    QDoubleSpinBox,
+    QFormLayout,
+    QHBoxLayout,
+    QSlider,
+    QSpinBox,
+    QWidget,
+)
+
+from lattice_core.types import ParamSpec
+
+SLIDER_STEPS = 1000
+MAX_SLIDER_STEPS = 10000
+DEFAULT_FLOAT_RANGE = (0.0, 1.0)
+DEFAULT_INT_RANGE = (0, 100)
+Value = float | int | bool | str
+
+
+def _bounds(spec: ParamSpec, fallback: tuple[float, float]) -> tuple[float, float]:
+    """Return the (min, max) range of a spec, falling back when it is incomplete."""
+    low = fallback[0] if spec.min is None else float(spec.min)
+    high = fallback[1] if spec.max is None else float(spec.max)
+    if high <= low:
+        high = low + 1.0
+    return low, high
+
+
+def _decimals(spec: ParamSpec) -> int:
+    """Return the number of decimals implied by the step of a float spec."""
+    if not spec.step:
+        return 2
+    text = f"{float(spec.step):.6f}".rstrip("0")
+    if "." not in text:
+        return 0
+    return max(0, min(4, len(text.split(".")[1])))
+
+
+def _slider_steps(spec: ParamSpec, low: float, high: float) -> int:
+    """Return the number of slider divisions for a float spec."""
+    if spec.step and float(spec.step) > 0.0:
+        steps = int(round((high - low) / float(spec.step)))
+        return max(1, min(MAX_SLIDER_STEPS, steps))
+    return SLIDER_STEPS
+
+
+def _to_slider(value: float, low: float, high: float, steps: int) -> int:
+    """Map a float value onto a slider position."""
+    if high <= low or steps <= 0:
+        return 0
+    position = int(round((float(value) - low) / (high - low) * steps))
+    return max(0, min(steps, position))
+
+
+class ParamForm(QWidget):
+    """Form with one editor per ParamSpec that emits changed on user edits."""
+
+    changed = Signal()
+
+    def __init__(self, specs: tuple[ParamSpec, ...] = (), parent: QWidget | None = None) -> None:
+        """Build an empty form layout, then show the given parameter specs."""
+        super().__init__(parent)
+        self._specs: tuple[ParamSpec, ...] = ()
+        self._editors: dict[str, QWidget] = {}
+        self._loading = False
+        self._form = QFormLayout(self)
+        self._form.setContentsMargins(4, 4, 4, 4)
+        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
+        self.set_specs(specs)
+
+    def specs(self) -> tuple[ParamSpec, ...]:
+        """Return the parameter specs currently shown by the form."""
+        return self._specs
+
+    def widget(self, spec_id: str) -> QWidget:
+        """Return the editor widget of one parameter."""
+        return self._editors[spec_id]
+
+    def set_specs(self, specs: tuple[ParamSpec, ...]) -> None:
+        """Rebuild the form for a new parameter tuple without emitting changed."""
+        self._loading = True
+        try:
+            while self._form.rowCount():
+                self._form.removeRow(0)
+            self._editors.clear()
+            self._specs = tuple(specs)
+            for spec in self._specs:
+                editor = self._build_editor(spec)
+                self._editors[spec.id] = editor
+                self._form.addRow(spec.label, editor)
+        finally:
+            self._loading = False
+
+    def values(self) -> dict[str, Value]:
+        """Return the current value of every parameter, keyed by spec id."""
+        result: dict[str, Value] = {}
+        for spec in self._specs:
+            editor = self._editors[spec.id]
+            if spec.kind == "float":
+                spin = editor.findChild(QDoubleSpinBox)
+                result[spec.id] = float(spin.value()) if spin is not None else 0.0
+            elif spec.kind == "int":
+                result[spec.id] = int(editor.value())  # type: ignore[union-attr]
+            elif spec.kind == "bool":
+                result[spec.id] = bool(editor.isChecked())  # type: ignore[union-attr]
+            else:
+                result[spec.id] = str(editor.currentText())  # type: ignore[union-attr]
+        return result
+
+    def set_values(self, values: dict) -> None:
+        """Apply values without emitting changed; out-of-range values are clamped."""
+        self._loading = True
+        try:
+            for spec in self._specs:
+                if spec.id in values:
+                    self._apply(spec, values[spec.id])
+        finally:
+            self._loading = False
+
+    def _apply(self, spec: ParamSpec, value: object) -> None:
+        """Write one value into its editor, clamping and ignoring unknown choices."""
+        editor = self._editors[spec.id]
+        if spec.kind == "float":
+            low, high = _bounds(spec, DEFAULT_FLOAT_RANGE)
+            spin = editor.findChild(QDoubleSpinBox)
+            slider = editor.findChild(QSlider)
+            if spin is not None:
+                spin.setValue(min(max(float(value), low), high))  # type: ignore[arg-type]
+                if slider is not None:
+                    slider.setValue(_to_slider(spin.value(), low, high, slider.maximum()))
+        elif spec.kind == "int":
+            low, high = _bounds(spec, DEFAULT_INT_RANGE)
+            editor.setValue(int(min(max(int(value), int(round(low))),  # type: ignore[union-attr]
+                                    int(round(high)))))
+        elif spec.kind == "bool":
+            editor.setChecked(bool(value))  # type: ignore[union-attr]
+        else:
+            index = editor.findText(str(value))  # type: ignore[union-attr]
+            if index >= 0:
+                editor.setCurrentIndex(index)  # type: ignore[union-attr]
+
+    def _build_editor(self, spec: ParamSpec) -> QWidget:
+        """Create the editor widget matching the kind of a spec."""
+        if spec.kind == "float":
+            return self._build_float(spec)
+        if spec.kind == "int":
+            return self._build_int(spec)
+        if spec.kind == "bool":
+            return self._build_bool(spec)
+        return self._build_choice(spec)
+
+    def _build_float(self, spec: ParamSpec) -> QWidget:
+        """Build a slider plus spinbox row for a float parameter."""
+        low, high = _bounds(spec, DEFAULT_FLOAT_RANGE)
+        steps = _slider_steps(spec, low, high)
+        box = QWidget(self)
+        row = QHBoxLayout(box)
+        row.setContentsMargins(0, 0, 0, 0)
+        slider = QSlider(Qt.Orientation.Horizontal, box)
+        slider.setRange(0, steps)
+        spin = QDoubleSpinBox(box)
+        spin.setRange(low, high)
+        spin.setDecimals(_decimals(spec))
+        spin.setSingleStep(float(spec.step) if spec.step else (high - low) / 100.0)
+        spin.setKeyboardTracking(False)
+        value = min(max(float(spec.default), low), high)
+        slider.setValue(_to_slider(value, low, high, steps))
+        spin.setValue(value)
+        slider.valueChanged.connect(
+            lambda position: self._on_slider(position, spin, low, high, steps)
+        )
+        spin.valueChanged.connect(lambda v: self._on_spin(v, slider, low, high, steps))
+        row.addWidget(slider, 1)
+        row.addWidget(spin, 0)
+        return box
+
+    def _build_int(self, spec: ParamSpec) -> QWidget:
+        """Build a spinbox for an int parameter."""
+        low, high = _bounds(spec, DEFAULT_INT_RANGE)
+        spin = QSpinBox(self)
+        spin.setRange(int(round(low)), int(round(high)))
+        spin.setSingleStep(int(spec.step) if spec.step else 1)
+        spin.setKeyboardTracking(False)
+        spin.setValue(int(min(max(int(spec.default), int(round(low))), int(round(high)))))
+        spin.valueChanged.connect(self._emit_changed)
+        return spin
+
+    def _build_bool(self, spec: ParamSpec) -> QWidget:
+        """Build a checkbox for a bool parameter."""
+        check = QCheckBox(self)
+        check.setChecked(bool(spec.default))
+        check.toggled.connect(self._emit_changed)
+        return check
+
+    def _build_choice(self, spec: ParamSpec) -> QWidget:
+        """Build a combobox for a choice parameter."""
+        combo = QComboBox(self)
+        combo.addItems([str(choice) for choice in spec.choices])
+        combo.setCurrentIndex(max(0, combo.findText(str(spec.default))))
+        combo.currentIndexChanged.connect(self._emit_changed)
+        return combo
+
+    def _emit_changed(self, *_args: object) -> None:
+        """Emit changed unless the form is being loaded programmatically."""
+        if not self._loading:
+            self.changed.emit()
+
+    def _on_slider(self, position: int, spin: QDoubleSpinBox, low: float, high: float,
+                   steps: int) -> None:
+        """Mirror a slider move into the spinbox and emit changed once."""
+        if self._loading:
+            return
+        self._loading = True
+        try:
+            spin.setValue(low + (high - low) * position / steps)
+        finally:
+            self._loading = False
+        self.changed.emit()
+
+    def _on_spin(self, value: float, slider: QSlider, low: float, high: float,
+                 steps: int) -> None:
+        """Mirror a spinbox edit into the slider and emit changed once."""
+        if self._loading:
+            return
+        self._loading = True
+        try:
+            slider.setValue(_to_slider(value, low, high, steps))
+        finally:
+            self._loading = False
+        self.changed.emit()
+
+
+__all__ = ["ParamForm"]
diff --git a/lattice_glitch/preset_panel.py b/lattice_glitch/preset_panel.py
new file mode 100644
index 0000000..9db276b
--- /dev/null
+++ b/lattice_glitch/preset_panel.py
@@ -0,0 +1,130 @@
+"""Preset browser of the Glitch shell: the shipped and user tiers, load, save, refresh.
+
+The list never renders anything: it reads v3 presets in this app's context and hands the
+window the whole ``Preset`` — spec, stack, masks and seed travel together. Saving is asked
+from the window, which owns the document; the panel only offers a path in the user tier.
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
+from lattice_glitch import presets as preset_tools
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
+        """Read the selected preset and emit it, or report why it cannot be read."""
+        path = self.selected_path()
+        if path is None:
+            self.failed.emit(NO_SELECTION)
+            return
+        try:
+            self.loaded.emit(preset_tools.read_preset(path))
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
diff --git a/lattice_glitch/presets.py b/lattice_glitch/presets.py
new file mode 100644
index 0000000..992c6f0
--- /dev/null
+++ b/lattice_glitch/presets.py
@@ -0,0 +1,272 @@
+"""Presets of Lattice Glitch: the shipped tier, the user tier, and the app default spec.
+
+Presets are v3 documents (``lattice_core.preset``) read in the ``glitch`` app context.
+Glitch is a continuous-mode application: the default spec nulls algorithm and palette
+(§5 S1) and the effect stack lives in the preset ``effects`` entries, mask assignments
+included. The user tier lives under this application's own app-data directory (§7).
+"""
+
+from __future__ import annotations
+
+import os
+import sys
+from collections.abc import Mapping, Sequence
+from dataclasses import dataclass
+from pathlib import Path
+
+import lattice_core.effects  # noqa: F401  (registers every effect validate() checks)
+from lattice_core import mask
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.preset import (
+    Preset,
+    from_pipeline_spec,
+    load_preset,
+    to_json,
+    to_pipeline_spec,
+)
+from lattice_core.presets import list_presets
+from lattice_core.registry import get_effect
+from lattice_glitch.stack import EffectStack
+
+APP_CONTEXT = "glitch"
+APP_DIR_NAME = "LatticeGlitch"
+PRESET_DIR_NAME = "presets"
+SHIPPED_PRESET_DIR = Path(__file__).resolve().parent / PRESET_DIR_NAME
+CONTINUOUS_ERROR = "glitch renders continuous images: algorithm and palette must both be null"
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
+    return [PresetEntry(path.name, path, _is_read_only(path, dirs))
+            for path in list_presets(dirs)]
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
+    """Return the pipeline of a fresh Glitch document: continuous mode, no effect yet."""
+    return PipelineSpec(pixel_size=1, renderer="pixel", algorithm_id=None, palette=None)
+
+
+def _mask_section(masks: Mapping[str, object], mask_dir: Path) -> dict:
+    """Return the v3 masks section: embed small planes, write the large ones to mask_dir."""
+    section: dict = {}
+    for mask_id, plane in masks.items():
+        try:
+            ref = mask.MaskRef.from_mask(plane, mask_id)
+        except ValueError:
+            target = mask.export_png(plane, mask_dir / f"{mask_id}.png")
+            ref = mask.MaskRef.from_path(target, mask_id)
+        section[mask_id] = ref.to_dict()
+    return section
+
+
+def to_preset(spec: PipelineSpec, *, stack: EffectStack | None = None,
+              masks: Mapping[str, object] | None = None, name: str = "",
+              mask_dir: Path | None = None,
+              locked_streams: Mapping[int, int] | None = None) -> Preset:
+    """Return the v3 preset of spec, tagged ``app: glitch``, stack masks attached.
+
+    Locked slots carry their frozen stream as ``seed`` so a reload renders the same
+    bytes (G9); the core keeps locks session-only, this is the shell's format (E1).
+    """
+    preset = from_pipeline_spec(spec)
+    preset.app = APP_CONTEXT
+    if name:
+        preset.meta["name"] = name
+    if stack is not None:
+        pre = [entry for entry in preset.effects if entry.get("stage") == "pre"]
+        entries = stack.to_entries()
+        for position, stream in (locked_streams or {}).items():
+            if 0 <= position < len(entries):
+                entries[position]["seed"] = int(stream)
+        preset.effects = pre + entries
+    if masks:
+        directory = mask_dir if mask_dir is not None else user_preset_dir() / "masks"
+        preset.masks = _mask_section(masks, directory)
+    return preset
+
+
+def locked_streams_of(preset: Preset) -> dict[int, int]:
+    """Return the frozen stream seed of each post slot whose entry carries one."""
+    streams: dict[int, int] = {}
+    position = 0
+    for entry in preset.effects:
+        if entry.get("stage", "post") == "pre":
+            continue
+        if "seed" in entry:
+            streams[position] = int(entry["seed"])
+        position += 1
+    return streams
+
+
+def spec_of(preset: Preset) -> PipelineSpec:
+    """Return the PipelineSpec of a parsed preset, its renderer and style included."""
+    return to_pipeline_spec(preset)
+
+
+def stack_of(preset: Preset) -> EffectStack:
+    """Return the effect stack a parsed preset carries, mask assignments included."""
+    return EffectStack.from_entries(preset.effects)
+
+
+def masks_of(preset: Preset) -> dict:
+    """Return the resolved mask planes of a parsed preset, keyed by section id."""
+    return mask.resolve_masks(preset.masks)
+
+
+def read_preset(path: str | Path) -> Preset:
+    """Read and parse one preset in this application's context."""
+    return load_preset(path, app=APP_CONTEXT)
+
+
+def describe(preset: Preset) -> dict:
+    """Return a JSON-serialisable summary of a preset, without rendering it."""
+    return {
+        "name": preset.meta.get("name", ""),
+        "app": preset.app,
+        "renderer": preset.renderer.get("name", ""),
+        "seed": preset.seed,
+        "effects": [
+            {"name": entry.get("name", ""), "params": dict(entry.get("params", {})),
+             "enabled": bool(entry.get("enabled", True)), "mask": entry.get("mask")}
+            for entry in preset.effects
+        ],
+        "masks": sorted(preset.masks),
+        "pipeline": {key: preset.pipeline.get(key) for key in
+                     ("brightness", "contrast", "gamma", "saturation", "pre_blur",
+                      "auto_levels", "algorithm")},
+    }
+
+
+def _check_effects(preset: Preset, errors: list[str]) -> None:
+    """Report unknown effect ids and mask ids the masks section does not carry."""
+    known = set(preset.masks)
+    for entry in preset.effects:
+        name = str(entry.get("name", ""))
+        try:
+            get_effect(name)
+        except KeyError:
+            errors.append(f"effect {name!r} is not registered in this build")
+        mask_id = entry.get("mask")
+        if mask_id is not None and str(mask_id) not in known:
+            errors.append(f"effect {name!r} names mask {mask_id!r}, absent from the masks section")
+
+
+def validate(path: str | Path) -> PresetReport:
+    """Parse one preset and report every problem instead of raising it."""
+    name = Path(path).name
+    try:
+        preset = read_preset(path)
+        spec = spec_of(preset)
+    except (OSError, ValueError, KeyError) as exc:
+        return PresetReport(name, False, [str(exc)], [])
+    errors: list[str] = []
+    if spec.algorithm_id is not None or spec.palette is not None:
+        errors.append(CONTINUOUS_ERROR)
+    _check_effects(preset, errors)
+    try:
+        masks_of(preset)
+    except (OSError, ValueError) as exc:
+        errors.append(f"cannot resolve the masks: {exc}")
+    warnings = [str(entry) for entry in preset.warnings]
+    return PresetReport(name, not errors, errors, warnings, spec.renderer)
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
+def save_spec(path: str | Path, spec: PipelineSpec, *, stack: EffectStack | None = None,
+              masks: Mapping[str, object] | None = None, name: str = "",
+              locked_streams: Mapping[int, int] | None = None) -> Path:
+    """Write the v3 preset of spec to path, large masks landing beside the preset."""
+    preset = to_preset(spec, stack=stack, masks=masks, name=name,
+                       mask_dir=Path(path).parent, locked_streams=locked_streams)
+    return save_preset(path, preset)
+
+
+__all__ = [
+    "APP_CONTEXT",
+    "APP_DIR_NAME",
+    "CONTINUOUS_ERROR",
+    "PresetEntry",
+    "PresetReport",
+    "SHIPPED_PRESET_DIR",
+    "app_data_dir",
+    "available",
+    "default_spec",
+    "describe",
+    "locked_streams_of",
+    "masks_of",
+    "read_preset",
+    "save_preset",
+    "save_spec",
+    "search_dirs",
+    "spec_of",
+    "stack_of",
+    "to_preset",
+    "user_preset_dir",
+    "validate",
+    "validate_all",
+]
diff --git a/lattice_glitch/presets/01_vhs_sp.json b/lattice_glitch/presets/01_vhs_sp.json
new file mode 100644
index 0000000..95aea1e
--- /dev/null
+++ b/lattice_glitch/presets/01_vhs_sp.json
@@ -0,0 +1,64 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "ntsc",
+      "params": {
+        "chroma_lowpass": 0.5,
+        "head_switching": 0.25,
+        "luma_smear": 0.2,
+        "snow": 0.08,
+        "tape_speed": "sp",
+        "tracking_noise": 0.15
+      },
+      "stage": "post"
+    },
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "scanlines",
+      "params": {
+        "darkness": 0.25,
+        "spacing": 4
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "01_vhs_sp",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/02_vhs_lp.json b/lattice_glitch/presets/02_vhs_lp.json
new file mode 100644
index 0000000..35840a6
--- /dev/null
+++ b/lattice_glitch/presets/02_vhs_lp.json
@@ -0,0 +1,54 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "ntsc",
+      "params": {
+        "chroma_lowpass": 0.7,
+        "head_switching": 0.4,
+        "luma_noise": 0.1,
+        "snow": 0.15,
+        "tape_speed": "lp",
+        "tracking_noise": 0.3
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "02_vhs_lp",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/03_vhs_ep.json b/lattice_glitch/presets/03_vhs_ep.json
new file mode 100644
index 0000000..ff434cf
--- /dev/null
+++ b/lattice_glitch/presets/03_vhs_ep.json
@@ -0,0 +1,64 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "ntsc",
+      "params": {
+        "chroma_lowpass": 0.9,
+        "composite_noise": 0.2,
+        "head_switching": 0.6,
+        "snow": 0.3,
+        "tape_speed": "ep",
+        "tracking_noise": 0.5
+      },
+      "stage": "post"
+    },
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "crt",
+      "params": {
+        "scanline_intensity": 0.2,
+        "vignette": 0.2
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "03_vhs_ep",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/04_ntsc_clean.json b/lattice_glitch/presets/04_ntsc_clean.json
new file mode 100644
index 0000000..d46e25a
--- /dev/null
+++ b/lattice_glitch/presets/04_ntsc_clean.json
@@ -0,0 +1,51 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "ntsc",
+      "params": {
+        "bandwidth": 0.8,
+        "chroma_lowpass": 0.4,
+        "ringing": "butterworth"
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "04_ntsc_clean",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/05_channel_rift.json b/lattice_glitch/presets/05_channel_rift.json
new file mode 100644
index 0000000..f23de89
--- /dev/null
+++ b/lattice_glitch/presets/05_channel_rift.json
@@ -0,0 +1,61 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "channel_shift",
+      "params": {
+        "amount": 12.0,
+        "channels": 5,
+        "mode": "translate"
+      },
+      "stage": "post"
+    },
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "noise",
+      "params": {
+        "amount": 0.06,
+        "monochrome": false
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "05_channel_rift",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 7,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/06_sort_gate.json b/lattice_glitch/presets/06_sort_gate.json
new file mode 100644
index 0000000..f43d037
--- /dev/null
+++ b/lattice_glitch/presets/06_sort_gate.json
@@ -0,0 +1,58 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": "gate",
+      "name": "pixel_sort",
+      "params": {
+        "brightness": 0.35,
+        "direction": "rows",
+        "key": "luma"
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {
+    "gate": {
+      "data": "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAAAAABWESUoAAAAIElEQVR4nGNk4ODg5IBgOAOZw8RAAIwqGFUwqmC4KgAAk00BP90Mw/QAAAAASUVORK5CYII=",
+      "height": 32,
+      "id": "gate",
+      "width": 32
+    }
+  },
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "06_sort_gate",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/07_feedback_echo.json b/lattice_glitch/presets/07_feedback_echo.json
new file mode 100644
index 0000000..b31e51e
--- /dev/null
+++ b/lattice_glitch/presets/07_feedback_echo.json
@@ -0,0 +1,66 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "feedback",
+      "params": {
+        "amount": 6.0,
+        "blend": "screen",
+        "decay": 0.7,
+        "iterations": 4,
+        "transform": "translate"
+      },
+      "stage": "post"
+    },
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "crt",
+      "params": {
+        "bloom": 0.25,
+        "curvature": 0.15,
+        "mask": "slot",
+        "scanline_intensity": 0.3,
+        "vignette": 0.25
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "07_feedback_echo",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 3,
+  "version": 3
+}
diff --git a/lattice_glitch/presets/08_crt_finish.json b/lattice_glitch/presets/08_crt_finish.json
new file mode 100644
index 0000000..409d321
--- /dev/null
+++ b/lattice_glitch/presets/08_crt_finish.json
@@ -0,0 +1,54 @@
+{
+  "app": "glitch",
+  "effects": [
+    {
+      "enabled": true,
+      "mask": null,
+      "name": "crt",
+      "params": {
+        "bloom": 0.3,
+        "curvature": 0.2,
+        "mask": "aperture_grille",
+        "mask_scale": 6,
+        "scanline_intensity": 0.45,
+        "vignette": 0.35
+      },
+      "stage": "post"
+    }
+  ],
+  "fonts": {},
+  "masks": {},
+  "meta": {
+    "author": "",
+    "created": "",
+    "description": "",
+    "name": "08_crt_finish",
+    "tags": [],
+    "thumbnail": ""
+  },
+  "output": {
+    "dpi": null,
+    "scale": 1,
+    "width": null
+  },
+  "palette": null,
+  "pipeline": {
+    "algorithm": null,
+    "auto_levels": false,
+    "brightness": 0.0,
+    "color_metric": "srgb",
+    "contrast": 0.0,
+    "gamma": 1.0,
+    "max_side": null,
+    "params": {},
+    "pixel_size": 1,
+    "pre_blur": 0.0,
+    "saturation": 0.0
+  },
+  "renderer": {
+    "name": "pixel",
+    "style": {}
+  },
+  "seed": 0,
+  "version": 3
+}
diff --git a/lattice_glitch/pyproject.toml b/lattice_glitch/pyproject.toml
new file mode 100644
index 0000000..db7e500
--- /dev/null
+++ b/lattice_glitch/pyproject.toml
@@ -0,0 +1,33 @@
+[build-system]
+requires = ["setuptools>=68"]
+build-backend = "setuptools.build_meta"
+
+[project]
+name = "lattice-glitch"
+version = "0.1.0"
+description = "Lattice Glitch: feedback, displacement, sorting and signal degradation for PhotoCraft and DesignCraft"
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
+lattice-glitch = "lattice_glitch.__main__:main"
+lattice-glitch-cli = "lattice_glitch.cli:main"
+
+# The distribution lives beside the application directory, as lattice-glyph does. The
+# mapping below makes a build started from this directory ship the package itself and its
+# presets, instead of a wheel that carries only metadata.
+[tool.setuptools]
+packages = ["lattice_glitch"]
+package-dir = { "lattice_glitch" = "." }
+
+[tool.setuptools.package-data]
+lattice_glitch = ["presets/*.json"]
diff --git a/lattice_glitch/seed_panel.py b/lattice_glitch/seed_panel.py
new file mode 100644
index 0000000..c335310
--- /dev/null
+++ b/lattice_glitch/seed_panel.py
@@ -0,0 +1,111 @@
+"""Seed panel of the Glitch shell: one seed, one reroll button, per-module locks (§18).
+
+The panel is a view over the window's ``SeedController``: the field shows the global
+seed (a reroll mixes it to a full 64-bit value, so the field is text, not a spin box),
+the reroll button asks for a new one, and one checkbox per stack position freezes or
+releases that module's stream. Locks are session-only; the preset serialises the seed.
+"""
+
+from __future__ import annotations
+
+from PySide6.QtCore import Signal
+from PySide6.QtWidgets import (
+    QCheckBox,
+    QHBoxLayout,
+    QLabel,
+    QLineEdit,
+    QPushButton,
+    QVBoxLayout,
+    QWidget,
+)
+
+
+class SeedPanel(QWidget):
+    """Global seed editor, reroll button and the per-module lock list of one stack."""
+
+    seed_changed = Signal(int)
+    reroll_requested = Signal()
+    lock_changed = Signal(int, bool)
+
+    def __init__(self, parent: QWidget | None = None) -> None:
+        """Build the seed row and the empty lock list."""
+        super().__init__(parent)
+        self.setObjectName("seed_panel")
+        self._loading = False
+        self._seed = 0
+        self._locks: list[QCheckBox] = []
+        self.seed_edit = QLineEdit(self)
+        self.seed_edit.setObjectName("seed_edit")
+        self.seed_edit.setText("0")
+        self.reroll_button = QPushButton("Reroll", self)
+        self.reroll_button.setObjectName("seed_reroll")
+        row = QHBoxLayout()
+        row.addWidget(QLabel("Seed", self))
+        row.addWidget(self.seed_edit, 1)
+        row.addWidget(self.reroll_button)
+        self.lock_box = QVBoxLayout()
+        self.lock_box.setContentsMargins(0, 0, 0, 0)
+        self.hint = QLabel("Lock a module to keep its noise across a reroll.", self)
+        self.hint.setWordWrap(True)
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(8, 8, 8, 8)
+        layout.addLayout(row)
+        layout.addWidget(QLabel("Module locks", self))
+        layout.addLayout(self.lock_box)
+        layout.addWidget(self.hint)
+        layout.addStretch(1)
+        self.seed_edit.returnPressed.connect(self._on_seed_text)
+        self.reroll_button.clicked.connect(lambda: self.reroll_requested.emit())
+
+    def set_seed(self, seed: int) -> None:
+        """Show seed without emitting seed_changed."""
+        self._loading = True
+        try:
+            self._seed = int(seed)
+            self.seed_edit.setText(str(self._seed))
+        finally:
+            self._loading = False
+
+    def set_modules(self, labels: list[str], locked: frozenset[int]) -> None:
+        """Rebuild one lock checkbox per stack position, checked for the locked ones."""
+        self._loading = True
+        try:
+            for check in self._locks:
+                self.lock_box.removeWidget(check)
+                check.deleteLater()
+            self._locks = []
+            for index, label in enumerate(labels):
+                check = QCheckBox(f"{index + 1}. {label}", self)
+                check.setObjectName(f"seed_lock_{index}")
+                check.setChecked(index in locked)
+                check.toggled.connect(lambda state, i=index: self._on_lock(i, state))
+                self.lock_box.addWidget(check)
+                self._locks.append(check)
+        finally:
+            self._loading = False
+
+    def lock_check(self, index: int) -> QCheckBox:
+        """Return the lock checkbox of one stack position."""
+        return self._locks[index]
+
+    def _on_seed_text(self) -> None:
+        """Adopt a typed non-negative integer seed; restore the display otherwise."""
+        if self._loading:
+            return
+        try:
+            value = int(self.seed_edit.text().strip())
+        except ValueError:
+            value = -1
+        if value < 0:
+            self.seed_edit.setText(str(self._seed))
+            return
+        self._seed = value
+        self.seed_changed.emit(value)
+
+    def _on_lock(self, index: int, state: bool) -> None:
+        """Emit lock_changed for a user toggle, never for a programmatic load."""
+        if not self._loading:
+            self.lock_changed.emit(index, bool(state))
+
+
+__all__ = ["SeedPanel"]
diff --git a/lattice_glitch/stack.py b/lattice_glitch/stack.py
new file mode 100644
index 0000000..fa8e072
--- /dev/null
+++ b/lattice_glitch/stack.py
@@ -0,0 +1,118 @@
+"""The effect stack of Lattice Glitch: ordered slots with parameters and a mask id.
+
+The stack is the application's view of ``PipelineSpec.post_effects``: one
+:class:`EffectSlot` per configured effect, in render order. Mask assignments travel
+with the slots (the v3 preset carries them as ``effects[].mask``), while the spec
+itself keeps only what ``lattice_core`` understands. No Qt here: the CLI path uses
+this module too.
+"""
+
+from __future__ import annotations
+
+import copy
+from dataclasses import dataclass
+
+from lattice_core.pipeline import EffectInstance
+from lattice_core.registry import get_effect
+
+
+@dataclass
+class EffectSlot:
+    """One configured effect of the stack: its instance and the mask id it wears."""
+
+    instance: EffectInstance
+    mask_id: str | None = None
+
+
+class EffectStack:
+    """Ordered effect slots with add, remove, reorder, enable, params and mask edits."""
+
+    def __init__(self, slots: list[EffectSlot] | None = None) -> None:
+        """Adopt slots (deep-copied) as the stack, empty when none are given."""
+        self._slots: list[EffectSlot] = copy.deepcopy(slots) if slots else []
+
+    def slots(self) -> list[EffectSlot]:
+        """Return a deep copy of the slots, in render order."""
+        return copy.deepcopy(self._slots)
+
+    def __len__(self) -> int:
+        """Return the number of slots, enabled or not."""
+        return len(self._slots)
+
+    def instances(self) -> list[EffectInstance]:
+        """Return the EffectInstance list a PipelineSpec carries as post_effects."""
+        return [copy.deepcopy(slot.instance) for slot in self._slots]
+
+    def mask_ids(self) -> tuple[str | None, ...]:
+        """Return the mask id of every slot, aligned with instances()."""
+        return tuple(slot.mask_id for slot in self._slots)
+
+    def effect_ids(self) -> list[str]:
+        """Return the effect id of every slot, in render order."""
+        return [slot.instance.effect_id for slot in self._slots]
+
+    def add(self, effect_id: str, params: dict | None = None,
+            mask_id: str | None = None) -> int:
+        """Append one registered effect and return its position; unknown ids raise."""
+        get_effect(effect_id)  # raises KeyError before anything is mutated
+        self._slots.append(EffectSlot(EffectInstance(effect_id, dict(params or {})), mask_id))
+        return len(self._slots) - 1
+
+    def remove(self, index: int) -> None:
+        """Drop the slot at index; an out-of-range index raises IndexError."""
+        del self._slots[index]
+
+    def move(self, index: int, new_index: int) -> None:
+        """Move the slot at index to new_index, shifting the others; bounds raise."""
+        if not (0 <= index < len(self._slots) and 0 <= new_index < len(self._slots)):
+            raise IndexError(f"stack move out of range: {index} -> {new_index}")
+        slot = self._slots.pop(index)
+        self._slots.insert(new_index, slot)
+
+    def set_enabled(self, index: int, enabled: bool) -> None:
+        """Enable or disable the slot at index without moving it."""
+        self._slots[index].instance.enabled = bool(enabled)
+
+    def set_params(self, index: int, params: dict) -> None:
+        """Replace the parameters of the slot at index (validated by the renderer)."""
+        self._slots[index].instance.params = dict(params)
+
+    def set_mask(self, index: int, mask_id: str | None) -> None:
+        """Assign a mask id to the slot at index, or None for a global effect."""
+        self._slots[index].mask_id = mask_id
+
+    def params_of(self, index: int) -> dict:
+        """Return a copy of the parameters of the slot at index."""
+        return dict(self._slots[index].instance.params)
+
+    def to_entries(self) -> list[dict]:
+        """Return the v3 preset effect entries of the stack, stage post, mask kept."""
+        entries: list[dict] = []
+        for slot in self._slots:
+            entries.append({
+                "name": slot.instance.effect_id,
+                "params": dict(slot.instance.params),
+                "enabled": bool(slot.instance.enabled),
+                "mask": slot.mask_id,
+                "stage": "post",
+            })
+        return entries
+
+    @classmethod
+    def from_entries(cls, entries: list[dict]) -> EffectStack:
+        """Build the stack from the post-stage entries of a v3 preset, in order."""
+        slots: list[EffectSlot] = []
+        for entry in entries:
+            if entry.get("stage", "post") == "pre":
+                continue
+            instance = EffectInstance(
+                effect_id=str(entry.get("name", "")),
+                params=dict(entry.get("params", {})),
+                enabled=bool(entry.get("enabled", True)),
+            )
+            mask = entry.get("mask")
+            slots.append(EffectSlot(instance, None if mask is None else str(mask)))
+        return cls(slots)
+
+
+__all__ = ["EffectSlot", "EffectStack"]
diff --git a/lattice_glitch/window.py b/lattice_glitch/window.py
new file mode 100644
index 0000000..2246902
--- /dev/null
+++ b/lattice_glitch/window.py
@@ -0,0 +1,392 @@
+"""Main window of Lattice Glitch: effect stack, live preview, seeds, masks, presets, bridge.
+
+The window owns the spec, the stack, the mask planes and the SeedController. Previews go
+to the GlitchWorker with an immutable context snapshot; exports call the CLI's own
+render function (G9); an absent host is a status-bar message. Shared lattice_core.ui
+widgets are consumed, never reimplemented.
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
+import lattice_core.effects  # noqa: F401  (registers every effect)
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.preset import Preset
+from lattice_core.seed import SeedController
+from lattice_core.types import RGB8, Image
+from lattice_core.ui import (
+    BridgeStatusDot,
+    EmptyState,
+    PresetIndicator,
+    PreviewCanvas,
+    PreviewResult,
+    oversize_message,
+    preview_proxy,
+)
+from lattice_glitch import APP_NAME
+from lattice_glitch import presets as preset_tools
+from lattice_glitch.actions import (
+    build_actions,
+    build_toolbar,
+    handle_drag_enter,
+    handle_drop,
+)
+from lattice_glitch.bridge_actions import DEFAULT_HOST
+from lattice_glitch.bridge_controller import BridgeController
+from lattice_glitch.document import DocumentError, RenderContext, load_image
+from lattice_glitch.effects_panel import EffectsPanel
+from lattice_glitch.export_actions import ExportController
+from lattice_glitch.mask_panel import MaskPanel
+from lattice_glitch.preset_panel import PresetPanel
+from lattice_glitch.seed_panel import SeedPanel
+from lattice_glitch.stack import EffectStack
+from lattice_glitch.window_bridge import BridgeMixin
+from lattice_glitch.worker import GlitchWorker
+
+LOGGER = logging.getLogger(__name__)
+SETTINGS_NAME = "LatticeGlitch"
+GEOMETRY_KEY = "geometry"
+IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
+PANEL_TABS = ("Effects", "Seed", "Masks", "Presets")
+STATUS_MS = 5000
+STOP_MS = 5000
+EMPTY_TEXT = "Open an image, or drop one here, to start glitching."
+
+
+class MainWindow(BridgeMixin, QMainWindow):
+    """Application window owning the spec, the stack, the seeds, the masks and the bridge."""
+
+    preview_requested = Signal(object)
+    source_changed = Signal(object)
+    context_changed = Signal(object)
+
+    def __init__(self, parent: QWidget | None = None, *,
+                 preset_dirs: tuple[Path, ...] | None = None) -> None:
+        """Build the canvas, the docks, the status bar and the helper threads."""
+        super().__init__(parent)
+        self.setWindowTitle(APP_NAME)
+        self.resize(1280, 800)
+        self.spec: PipelineSpec = preset_tools.default_spec()
+        self.effect_stack = EffectStack()
+        self.controller = SeedController(self.spec.seed)
+        self._fixed_streams: dict[int, int] = {}
+        self.source: Image | None = None
+        self.source_path: Path | None = None
+        self.worker: GlitchWorker | None = None
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
+        self.bridge.absent.connect(self.status)
+        self.bridge.progress.connect(self.status)
+        self.bridge.absent.connect(lambda _msg: self.check_bridge())
+        self.bridge.failed.connect(lambda _msg: self.check_bridge())
+        self.check_bridge()
+        self.effects_panel.load(self.effect_stack, self.mask_panel.mask_ids())
+        self.refresh_seed_panel()
+
+    def _build_dock(self, preset_dirs: tuple[Path, ...] | None) -> None:
+        """Create the right dock with the effects, seed, mask and preset panels."""
+        self.dock = QDockWidget("Panels", self)
+        self.dock.setObjectName("panel_dock")
+        self.dock.setAllowedAreas(
+            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
+        )
+        self.tabs = QTabWidget(self.dock)
+        self.tabs.setObjectName("panel_tabs")
+        self.effects_panel = EffectsPanel(self.tabs)
+        self.seed_panel = SeedPanel(self.tabs)
+        self.mask_panel = MaskPanel(self.tabs)
+        self.preset_panel = PresetPanel(preset_dirs, self.tabs)
+        self.panels: dict[str, QWidget] = dict(zip(
+            PANEL_TABS, (self.effects_panel, self.seed_panel, self.mask_panel,
+                         self.preset_panel), strict=True,
+        ))
+        for name, panel in self.panels.items():
+            self.tabs.addTab(panel, name)
+        self.dock.setWidget(self.tabs)
+        self.dock.setMinimumWidth(360)
+        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
+        self.effects_panel.changed.connect(self.on_panels_changed)
+        self.seed_panel.seed_changed.connect(self.set_seed)
+        self.seed_panel.reroll_requested.connect(self.reroll)
+        self.seed_panel.lock_changed.connect(self.toggle_lock)
+        self.mask_panel.masks_changed.connect(self.on_masks_changed)
+        self.mask_panel.mask_painted.connect(lambda _id: self.on_masks_changed())
+        self.mask_panel.failed.connect(self.report)
+        self.preset_panel.loaded.connect(self.load_preset)
+        self.preset_panel.save_requested.connect(self.save_preset_to)
+        self.preset_panel.failed.connect(self.report)
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
+        """Create the glitch render worker in its own thread and connect its signals."""
+        thread = QThread(self)
+        worker = GlitchWorker()
+        worker.moveToThread(thread)
+        thread.started.connect(worker.start)
+        thread.finished.connect(worker.deleteLater)
+        self.context_changed.connect(worker.set_context)
+        self.preview_requested.connect(worker.request_preview)
+        self.source_changed.connect(worker.set_source)
+        worker.preview_ready.connect(self._on_preview)
+        worker.failed.connect(self.report)
+        self.render_thread, self.worker = thread, worker
+        thread.start()
+
+    def shutdown(self) -> None:
+        """Stop the helper threads and the bridge probe; safe to call more than once.
+
+        The worker reference is released only once its thread has stopped: freeing a
+        worker a running thread is still executing is a hard crash, not an exception.
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
+    # --- spec, stack, seeds and preview --------------------------------------------
+
+    def settings(self) -> QSettings:
+        """Return the settings object the export dialog remembers its directory in."""
+        return self._settings
+
+    def render_context(self) -> RenderContext:
+        """Return the immutable render snapshot: mask ids, copied planes and stream seeds."""
+        count = len(self.effect_stack)
+        streams = tuple(self._fixed_streams.get(i, self.controller.module_seed_for(i))
+                        for i in range(count))
+        return RenderContext(mask_ids=self.effect_stack.mask_ids(),
+                             masks={k: v.copy() for k, v in self.mask_panel.planes().items()},
+                             streams=streams)
+
+    def sync_spec(self) -> None:
+        """Mirror the stack and the controller into the spec the renderers read."""
+        self.spec.post_effects = self.effect_stack.instances()
+        self.spec.seed = self.controller.seed
+
+    def refresh_seed_panel(self) -> None:
+        """Show the current seed and one lock checkbox per stack position."""
+        labels = [slot.instance.effect_id for slot in self.effect_stack.slots()]
+        self.seed_panel.set_seed(self.controller.seed)
+        self.seed_panel.set_modules(labels, self.controller.locked())
+
+    def on_panels_changed(self) -> None:
+        """Adopt the stack edits, mark the preset modified and request a preview."""
+        self.sync_spec()
+        self.refresh_seed_panel()
+        self.indicator.pipeline_changed()
+        self._request_preview()
+
+    def on_masks_changed(self) -> None:
+        """Offer the current mask ids to the stack and request a preview."""
+        self.effects_panel.set_mask_ids(self.mask_panel.mask_ids())
+        self.sync_spec()
+        self._request_preview()
+
+    def reroll(self) -> None:
+        """Reroll the global seed; locked modules keep their streams (§18)."""
+        self.controller.reroll()
+        self.sync_spec()
+        self.seed_panel.set_seed(self.controller.seed)
+        self.indicator.pipeline_changed()
+        self._request_preview()
+        self.status(f"Seed {self.controller.seed}")
+
+    def set_seed(self, seed: int) -> None:
+        """Adopt an explicit global seed, keeping the current locks."""
+        self.controller.reroll(int(seed))
+        self.sync_spec()
+        self.indicator.pipeline_changed()
+        self._request_preview()
+
+    def toggle_lock(self, module: int, locked: bool) -> None:
+        """Freeze or release one module's stream and request a preview."""
+        if locked:
+            self.controller.lock(module)
+        else:
+            self.controller.unlock(module)
+            self._fixed_streams.pop(module, None)
+        self._request_preview()
+
+    def apply_preset(self, preset: Preset, announce: bool = True) -> None:
+        """Adopt a whole preset: spec, stack, masks and seed, then request a preview."""
+        try:
+            spec = preset_tools.spec_of(preset)
+            stack = preset_tools.stack_of(preset)
+            planes = preset_tools.masks_of(preset)
+            fixed = preset_tools.locked_streams_of(preset)
+        except (OSError, ValueError, KeyError) as exc:
+            self.report(f"Cannot apply preset: {exc}")
+            return
+        self.spec = spec
+        self.effect_stack = stack
+        self.controller = SeedController(preset.seed)
+        self._fixed_streams = fixed
+        for module in fixed:
+            self.controller.lock(module)
+        self.mask_panel.set_planes(planes)
+        self.effects_panel.load(self.effect_stack, self.mask_panel.mask_ids())
+        self.sync_spec()
+        self.refresh_seed_panel()
+        if announce:
+            self.indicator.pipeline_changed()
+        self._request_preview()
+
+    def load_preset(self, preset: Preset) -> None:
+        """Load a preset from the browser; the indicator names it as freshly applied."""
+        self.apply_preset(preset, announce=False)
+        path = self.preset_panel.selected_path()
+        self.indicator.set_preset(None if path is None else path.name)
+        self.indicator.set_image_loaded(self.source is not None)
+
+    def _request_preview(self) -> None:
+        """Ask the worker for a preview of the current document, when an image is loaded."""
+        if self.source is not None:
+            self.context_changed.emit(self.render_context())
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
+        self.mask_panel.set_source(image)
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
+    def _on_preview(self, result: PreviewResult) -> None:
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
+    def export_dialog(self) -> None:
+        """Open the shared full-resolution export dialog."""
+        self.exporter.dialog()
+
+    def export_to(self, path: str | Path) -> dict:
+        """Write the current render to path as PNG."""
+        return self.exporter.to(path)
+
+    def save_preset_to(self, path: str | Path) -> None:
+        """Write the current document as a v3 preset and remember it as the applied one."""
+        self.exporter.save_preset(str(path))
+
+    def render_full(self, image: Image, spec: PipelineSpec) -> RGB8:
+        """Render spec on image through the function the CLI calls (G9)."""
+        return self.exporter.render_full(image, spec)
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
+        handle_drag_enter(self, event)
+
+    def dropEvent(self, event: QDropEvent) -> None:
+        """Open the first image of a drop, or report that the drop was ignored."""
+        handle_drop(self, event)
+
+
+__all__ = ["MainWindow", "PANEL_TABS"]
diff --git a/lattice_glitch/window_bridge.py b/lattice_glitch/window_bridge.py
new file mode 100644
index 0000000..e63d08e
--- /dev/null
+++ b/lattice_glitch/window_bridge.py
@@ -0,0 +1,53 @@
+"""Host-facing slots of the Glitch window, mixed into MainWindow (§7, E9).
+
+Pull adopts the host document as the source; push renders through the CLI's own
+function with the session context and places the result. An absent host is a status
+line, never a dialog; a real failure is reported. Keeping these slots here leaves the
+window file under its size budget without changing the public surface.
+"""
+
+from __future__ import annotations
+
+import numpy as np
+
+NO_SOURCE = "Load an image before rendering."
+
+
+class BridgeMixin:
+    """The bridge half of the window: pull, push, status answers and the probe."""
+
+    def get_from_host(self) -> None:
+        """Read the active document of the bridge host into this application."""
+        self.bridge.pull()
+
+    def send_to_host(self) -> None:
+        """Place the current render in the bridge host; an absent host is a status line."""
+        if self.source is None:
+            self.report(NO_SOURCE)
+            return
+        self.bridge.push(self.source, self.spec, self.render_context())
+
+    def _on_pulled(self, image: object, host: str) -> None:
+        """Adopt a document pulled from a host, which has no source path."""
+        self.check_bridge()
+        if image is None:
+            self.report(f"{host}: no document")
+            return
+        self.set_source(np.ascontiguousarray(np.asarray(image), np.float32))
+        self.status(f"Read the {host} document")
+
+    def _on_pushed(self, object_id: int) -> None:
+        """Report a successful placement in the host and re-probe its reachability."""
+        self.status(f"Placed object {object_id}")
+        self.check_bridge()
+
+    def _on_state(self, state: str) -> None:
+        """Show the host reachability in the status bar label."""
+        self.connection_label.setText(f"{self.bridge.host}: {state}")
+
+    def check_bridge(self) -> None:
+        """Ask the bridge status dot to probe the host now."""
+        self.bridge_dot.check()
+
+
+__all__ = ["BridgeMixin", "NO_SOURCE"]
diff --git a/lattice_glitch/worker.py b/lattice_glitch/worker.py
new file mode 100644
index 0000000..ae6fdaa
--- /dev/null
+++ b/lattice_glitch/worker.py
@@ -0,0 +1,83 @@
+"""Render worker of the Glitch shell: the shared worker, rendering the glitch path.
+
+The shared ``RenderWorker`` debounces, proxies and stages previews, but renders through
+``pipeline.render``, which knows neither §18 masks nor per-module seed locks. This
+subclass keeps all of that machinery and swaps only the render call for
+:func:`lattice_glitch.document.render_rgb8`, fed with an immutable ``RenderContext``
+snapshot so the worker thread never reads a controller the GUI thread is mutating.
+"""
+
+from __future__ import annotations
+
+import logging
+import time
+
+from PySide6.QtCore import Slot
+
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.ui.worker import (
+    PREVIEW_STAGES,
+    PreviewResult,
+    RenderResult,
+    RenderWorker,
+)
+from lattice_glitch.document import RenderContext, render_rgb8
+
+LOGGER = logging.getLogger(__name__)
+
+
+class GlitchWorker(RenderWorker):
+    """Renders debounced, staged previews of one source through the glitch path."""
+
+    def __init__(self, parent=None) -> None:
+        """Start from the shared worker with an empty render context."""
+        super().__init__(parent)
+        self._context = RenderContext()
+
+    @Slot(object)
+    def set_context(self, context: RenderContext) -> None:
+        """Adopt the mask ids, mask planes and stream seeds of the next renders."""
+        self._context = context
+
+    def _render_preview(self) -> None:
+        """Render the latest spec through the preview stages, dropping superseded jobs."""
+        spec, source = self._spec, self._source
+        if spec is None or source is None:
+            return
+        job = self._pending_job
+        if job != self._job:
+            return
+        previous: tuple[int, int] | None = None
+        for max_side in PREVIEW_STAGES:
+            if job != self._job:
+                LOGGER.debug("dropping superseded preview job %d", job)
+                return
+            started = time.perf_counter()
+            try:
+                proxy, original = self._proxy_for(max_side)
+                rgb8 = render_rgb8(proxy, spec, context=self._context)
+            except Exception as exc:  # noqa: BLE001 - report any render failure to the user
+                self.failed.emit(f"Render failed: {exc}")
+                return
+            if rgb8.shape == previous:
+                continue
+            previous = rgb8.shape
+            seconds = time.perf_counter() - started
+            self.preview_ready.emit(PreviewResult(job, rgb8, original, seconds, max_side))
+
+    def _render_full(self, spec: PipelineSpec) -> RenderResult | None:
+        """Render spec at full resolution through the glitch path, reporting failures."""
+        source = self._source
+        if source is None:
+            self.failed.emit("Load an image before rendering.")
+            return None
+        started = time.perf_counter()
+        try:
+            rgb8 = render_rgb8(source, spec, context=self._context)
+        except Exception as exc:  # noqa: BLE001 - report any render failure to the user
+            self.failed.emit(f"Render failed: {exc}")
+            return None
+        return RenderResult(self._job, rgb8, time.perf_counter() - started)
+
+
+__all__ = ["GlitchWorker"]
diff --git a/tests/test_glitch_app.py b/tests/test_glitch_app.py
new file mode 100644
index 0000000..6e1f4fb
--- /dev/null
+++ b/tests/test_glitch_app.py
@@ -0,0 +1,459 @@
+"""Tests for the Lattice Glitch shell (card L20), Qt offscreen: G9, seeds, masks, no-Qt CLI."""
+
+import ast
+import json
+import os
+import subprocess
+import sys
+import time
+from pathlib import Path
+
+os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
+import numpy as np  # noqa: E402
+import pytest  # noqa: E402
+from PySide6.QtCore import QSettings  # noqa: E402
+from PySide6.QtWidgets import QApplication, QMessageBox, QSlider  # noqa: E402
+
+import lattice_core.effects  # noqa: E402,F401  (registers every effect)
+import lattice_glitch  # noqa: E402
+from lattice_core import color, mask  # noqa: E402
+from lattice_core.effects.ntsc import LABEL_NOTES, PRESET_NAMES, SIMPLE_PARAM_IDS  # noqa: E402
+from lattice_core.pipeline import PipelineSpec  # noqa: E402
+from lattice_core.registry import get_effect, list_effects, resolve_params  # noqa: E402
+from lattice_core.seed import SeedController  # noqa: E402
+from lattice_core.ui import ExportDialog, ExportError  # noqa: E402
+from lattice_glitch import cli, presets  # noqa: E402
+from lattice_glitch import document as doc  # noqa: E402
+from lattice_glitch.stack import EffectStack  # noqa: E402
+from lattice_glitch.window import MainWindow  # noqa: E402
+
+PACKAGE = Path(lattice_glitch.__file__).resolve().parent
+SHIPPED = PACKAGE / "presets"
+EFFECT_IDS = [info.id for info in list_effects()]
+CLI_MODULES = ("__init__", "__main__", "cli", "document", "hosts", "presets", "stack",
+               "window_bridge")
+GUI_MODULES = ("actions", "app", "bridge_actions", "bridge_controller", "effects_panel",
+               "export_actions", "mask_painter", "mask_panel", "params", "preset_panel",
+               "seed_panel", "window", "worker")
+BLOCKER = """import sys, importlib.abc
+class Refuse(importlib.abc.MetaPathFinder):
+    def find_spec(self, name, path=None, target=None):
+        if name.split('.')[0] == 'PySide6': raise ImportError('PySide6 is not installed')
+sys.meta_path.insert(0, Refuse()); sys.path.insert(0, {root!r})
+from lattice_glitch.__main__ import main
+code = main(['render', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r}])
+forbidden = ('lattice_core.ui', 'lattice_core.animation', 'lattice_dither', 'lattice_glyph')
+assert not [m for m in sys.modules if m.split('.')[0] == 'PySide6' or m.startswith(forbidden)]
+raise SystemExit(code)"""
+
+
+class _FakeClient:
+    """Stand-in for a live ArtCraft client used by the bridge verbs."""
+    def render_document(self):
+        return color.to_pil(np.full((16, 16, 3), 128, np.uint8))
+
+    def place_as_layer(self, img, name=None):
+        return 3
+
+    def disconnect(self):
+        return None
+
+
+@pytest.fixture(scope="module")
+def qapp() -> QApplication:
+    app = QApplication.instance()
+    return app if isinstance(app, QApplication) else QApplication([])
+
+
+@pytest.fixture
+def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
+    """Collect modal-dialog texts so a failure reports instead of blocking the suite."""
+    seen: list[str] = []
+    monkeypatch.setattr(QMessageBox, "critical", lambda *a: seen.append(str(a[2])))
+    return seen
+
+
+@pytest.fixture
+def image() -> np.ndarray:
+    """Deterministic float32 RGB image: noise plus a horizontal gradient."""
+    rng, ramp = np.random.default_rng(7), np.linspace(0, 1, 128, dtype=np.float32)
+    noise = rng.random((96, 128, 3), np.float32)
+    return np.ascontiguousarray(np.clip(0.5 * noise + 0.5 * ramp[None, :, None], 0, 1), np.float32)
+
+
+@pytest.fixture
+def image_file(tmp_path: Path, image: np.ndarray) -> Path:
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
+    yield build
+    for window in opened:
+        window.shutdown()
+
+
+def _png(path: str | Path, rgb8: np.ndarray) -> Path:
+    color.to_pil(rgb8).save(path, format="PNG")
+    return Path(path)
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
+def _r(preset, source, out, *extra) -> int:
+    return cli.main(["render", "--preset", str(preset), "--in", str(source),
+                     "--out", str(out), *extra])
+
+
+def _cli(tmp_path: Path, preset: Path, source: Path, name: str = "cli") -> bytes:
+    target = tmp_path / f"{name}.png"
+    assert _r(preset, source, target) == cli.EXIT_OK
+    return target.read_bytes()
+
+
+def _imports(path: Path) -> set[str]:
+    tree = ast.parse(path.read_text("utf-8"))
+    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
+    names |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
+    return names
+
+
+def test_shell_opens_stacks_reorders_saves(make_window, tmp_path: Path, image_file: Path,
+                                           image: np.ndarray, monkeypatch: pytest.MonkeyPatch,
+                                           quiet: list[str]) -> None:
+    """Accept: launch, open, stack two effects, reorder, save; the bridge dot probes live."""
+    window = make_window()
+    assert window.windowTitle() == lattice_glitch.APP_NAME
+    assert window.tabs.count() == 4 and "reroll" in window.action_map
+    _settle(lambda: window.bridge_dot.state() != "unknown")
+    assert window.bridge_dot.state() == "disconnected"
+    assert "disconnected" in window.connection_label.text()
+    assert window.open_path(tmp_path / "nope.png") is False
+    window.export_dialog()
+    assert window.source is None and quiet
+    with pytest.raises(doc.DocumentError):
+        window.export_to(tmp_path / "out.png")
+    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
+    assert window.source is None and "9000" in quiet[-1]
+    assert window.open_path(image_file) is True
+    window.effects_panel.add_effect("noise")
+    window.effects_panel.add_effect("rgb_shift")
+    assert window.effect_stack.effect_ids() == ["noise", "rgb_shift"]
+    _settle(lambda: window.canvas.qimage() is not None)
+    window.effects_panel.list.setCurrentRow(1)
+    window.effects_panel.move_selected(-1)
+    assert window.effect_stack.effect_ids() == ["rgb_shift", "noise"]
+    assert [i.effect_id for i in window.spec.post_effects] == ["rgb_shift", "noise"]
+    window.save_preset_to(str(tmp_path / "user" / "mine.json"))
+    saved = presets.read_preset(tmp_path / "user" / "mine.json")
+    assert [e["name"] for e in saved.effects] == ["rgb_shift", "noise"]
+    assert window.indicator.preset_name() == "mine.json"
+    window.apply_preset(saved)
+    assert window.effect_stack.effect_ids() == ["rgb_shift", "noise"]
+    entries = window.preset_panel.entries()
+    assert entries and any(e.name == "mine.json" and not e.read_only for e in entries)
+    monkeypatch.setattr("lattice_glitch.bridge_actions.discover", lambda host: None)
+    window.send_to_host()
+    _settle(lambda: "not running" in window.statusBar().currentMessage())
+    window.get_from_host()
+    _settle(lambda: "not running" in window.statusBar().currentMessage())
+    assert window.source is not None and len(quiet) == 3
+    assert window.bridge_dot.state() == "disconnected"
+
+
+def test_cli_and_gui_write_identical_bytes(make_window, tmp_path: Path,
+                                           image_file: Path, quiet: list[str]) -> None:
+    """Accept (G9): CLI render and GUI export are byte-identical for the same preset."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    for preset in sorted(SHIPPED.glob("*.json")):
+        expected = _cli(tmp_path, preset, image_file, preset.stem)
+        window.apply_preset(presets.read_preset(preset))
+        window.export_to(tmp_path / "gui.png")
+        assert (tmp_path / "gui.png").read_bytes() == expected, preset.name
+    spec = presets.default_spec()
+    spec.seed, spec.brightness = 42, 0.1
+    stack = EffectStack()
+    stack.add("channel_shift", {"amount": 10.0})
+    stack.add("noise", {"amount": 0.2})
+    window.spec, window.effect_stack = spec, stack
+    window.controller = SeedController(spec.seed)
+    window.effects_panel.load(stack, [])
+    window.sync_spec()
+    window.save_preset_to(str(tmp_path / "user" / "edited.json"))
+    expected = _cli(tmp_path, tmp_path / "user" / "edited.json", image_file, "edited")
+    window.export_to(tmp_path / "gui.png")
+    assert (tmp_path / "gui.png").read_bytes() == expected
+    mid = window.mask_panel.new_mask()
+    window.mask_panel.painter.set_brush(1.0, 9)
+    window.mask_panel.painter.paint_at(40, 40)
+    window.effect_stack.set_mask(1, mid)
+    window.sync_spec()
+    window.save_preset_to(str(tmp_path / "user" / "masked.json"))
+    expected = _cli(tmp_path, tmp_path / "user" / "masked.json", image_file, "masked")
+    window.export_to(tmp_path / "gui.png")
+    assert (tmp_path / "gui.png").read_bytes() == expected
+    assert window.effects_panel.effect_choices() == EFFECT_IDS and len(EFFECT_IDS) == 16
+    small = window.source[:48, :64]
+    for effect_id in EFFECT_IDS:
+        while len(window.effect_stack):
+            window.effect_stack.remove(0)
+        window.effects_panel.add_effect(effect_id)
+        window.sync_spec()
+        assert window.effect_stack.effect_ids() == [effect_id]
+        assert [i.effect_id for i in window.spec.post_effects] == window.effect_stack.effect_ids()
+        assert window.render_full(small, window.spec).shape == (48, 64, 3), effect_id
+    assert not quiet
+
+
+def test_reroll_lock_and_stream_parity(make_window, tmp_path: Path, image_file: Path) -> None:
+    """Accept: reroll changes output; lock keeps module 0 (both active); the stream survives G9."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    window.effects_panel.add_effect("noise")
+    window.effects_panel.add_effect("jpeg_glitch")
+    full0 = window.render_full(window.source, window.spec)
+    window.reroll()
+    assert not np.array_equal(full0, window.render_full(window.source, window.spec))
+    assert window.spec.seed == window.controller.seed
+    assert window.seed_panel.seed_edit.text() == str(window.controller.seed)
+    window.seed_panel.lock_check(0).setChecked(True)
+    assert window.controller.locked() == frozenset({0})
+    params = resolve_params(get_effect("noise").params, window.effect_stack.params_of(0))
+    noise = get_effect("noise").fn
+    stage0 = noise(window.source, params, window.controller.rng(0))
+    both_locked = window.render_full(window.source, window.spec)
+    seed_before = window.controller.seed
+    window.reroll()
+    assert window.controller.seed != seed_before
+    assert np.array_equal(stage0, noise(window.source, params, window.controller.rng(0)))
+    assert not np.array_equal(both_locked, window.render_full(window.source, window.spec))
+    locked_stream = window.controller.module_seed_for(0)
+    target = tmp_path / "user" / "locked.json"
+    window.save_preset_to(str(target))
+    entries = json.loads(target.read_text())["effects"]
+    assert entries[0]["seed"] == locked_stream and "seed" not in entries[1]
+    expected = _cli(tmp_path, target, image_file, "locked")
+    window.export_to(tmp_path / "gui.png")
+    assert (tmp_path / "gui.png").read_bytes() == expected
+    window.apply_preset(presets.read_preset(target))
+    assert window.controller.locked() == frozenset({0})
+    assert window.render_context().streams[0] == locked_stream
+    window.export_to(tmp_path / "gui.png")
+    assert (tmp_path / "gui.png").read_bytes() == expected
+    before = window.render_context().streams
+    window.reroll()
+    after = window.render_context().streams
+    assert after[0] == before[0] == locked_stream and after[1] != before[1]
+    window.seed_panel.lock_check(0).setChecked(False)
+    assert window.controller.locked() == frozenset()
+    window.reroll()
+    assert not np.array_equal(both_locked, window.render_full(window.source, window.spec))
+
+
+def test_ntsc_simple_mode_presets_and_tooltips(make_window, image_file: Path) -> None:
+    """§16: ntsc defaults to four sliders, six named presets, honest tooltips, advanced toggle."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    window.effects_panel.add_effect("ntsc")
+    panel = window.effects_panel
+    assert not panel.ntsc_row.isHidden()
+    assert tuple(s.id for s in panel.form.specs()) == SIMPLE_PARAM_IDS
+    assert len(panel.form.specs()) == 4 and len(panel.form.findChildren(QSlider)) == 4
+    for spec in panel.form.specs():
+        assert panel.form.widget(spec.id).toolTip() == LABEL_NOTES[spec.id]
+    names = [panel.ntsc_preset_box.itemText(i) for i in range(panel.ntsc_preset_box.count())]
+    assert names == list(PRESET_NAMES) and len(names) == 6
+    panel.ntsc_preset_box.setCurrentIndex(names.index("VHS Home"))
+    assert window.effect_stack.params_of(0)["tape_speed"] == "ep"
+    assert window.effect_stack.params_of(0)["tracking_noise"] == 0.7
+    panel.ntsc_advanced.setChecked(True)
+    assert len(panel.form.specs()) == 14
+    assert window.effect_stack.params_of(0)["tape_speed"] == "ep"
+    panel.ntsc_advanced.setChecked(False)
+    assert len(panel.form.specs()) == 4
+    window.effects_panel.add_effect("noise")
+    assert panel.ntsc_row.isHidden()
+
+
+def test_mask_painter_produces_a_mask_the_renderer_honours(make_window, image_file: Path,
+                                                           image: np.ndarray,
+                                                           tmp_path: Path) -> None:
+    """Accept: the painted mask localises the effect; deleting it purges slots and exports safe."""
+    window = make_window()
+    assert window.open_path(image_file) is True
+    mid = window.mask_panel.new_mask()
+    plane = window.mask_panel.planes()[mid]
+    assert plane.shape == image.shape[:2] and not plane.any()
+    window.mask_panel.painter.set_brush(1.0, 6)
+    window.mask_panel.painter.paint_at(20, 20)
+    assert plane[20, 20] == 1.0 and plane[80, 110] == 0.0
+    window.effects_panel.add_effect("noise", {"amount": 1.0})
+    window.effect_stack.set_mask(0, mid)
+    window.sync_spec()
+    rendered = window.render_full(window.source, window.spec)
+    params = resolve_params(get_effect("noise").params, {"amount": 1.0})
+    rng = SeedController(window.spec.seed).rng(0)
+    effect = np.ascontiguousarray(np.clip(get_effect("noise").fn(window.source, params, rng),
+                                          0, 1), np.float32)
+    expected = color.to_rgb8(mask.apply(window.source, effect, mask=plane))
+    assert np.array_equal(rendered, expected)
+    assert np.array_equal(rendered[80, 110], color.to_rgb8(window.source)[80, 110])
+    window.mask_panel.generate("h")
+    ramp = np.linspace(0, 1, image.shape[1], dtype=np.float32)[None, :]
+    assert np.array_equal(plane, mask.from_png(mask.to_png(np.broadcast_to(ramp, plane.shape))))
+    window.mask_panel.lo_spin.setValue(0.2)
+    window.mask_panel.hi_spin.setValue(0.8)
+    window.mask_panel.generate("luma")
+    want = mask.from_png(mask.to_png(np.clip((color.luminance(window.source) - 0.2) / 0.6, 0, 1)))
+    assert np.array_equal(plane, want)
+    out = window.mask_panel.export_png(tmp_path / "m.png")
+    assert out is not None and np.array_equal(mask.import_png(out), plane)
+    window.mask_panel.delete_active()
+    assert window.mask_panel.mask_ids() == [] and window.effect_stack.mask_ids() == (None,)
+    window.effect_stack.set_mask(0, "ghost")
+    window.sync_spec()
+    dialog = ExportDialog(window.source, window.spec, window,
+                          render_full=lambda s: window.exporter.render_full(window.source, s),
+                          settings=window.settings())
+    dialog.format_box.setCurrentIndex(dialog.format_box.findData("png"))
+    dialog.path_edit.setText(str(tmp_path / "orphan.png"))
+    with pytest.raises(ExportError):
+        window.exporter.render_full(window.source, window.spec)
+    dialog._on_export()
+    assert "ghost" in dialog.report.text() and not (tmp_path / "orphan.png").exists()
+    dialog.deleteLater()
+
+
+def test_presets_document_stack_and_masks(tmp_path: Path, image: np.ndarray) -> None:
+    """Shipped presets validate; document failures are typed; stack and large masks round-trip."""
+    reports = presets.validate_all((SHIPPED,))
+    assert len(reports) >= 6 and all(report.ok for report in reports)
+    assert all(presets.read_preset(SHIPPED / r.name).app == presets.APP_CONTEXT for r in reports)
+    spec = presets.default_spec()
+    assert spec.algorithm_id is None and spec.palette is None
+    assert presets.user_preset_dir().parent.name == "LatticeGlitch"
+    with pytest.raises(doc.DocumentError, match="nope.png"):
+        doc.load_image(tmp_path / "nope.png")
+    with pytest.raises(doc.DocumentError):
+        doc.render_rgb8(image, PipelineSpec())
+    with pytest.raises(doc.DocumentError):
+        doc.format_of("a.jpg")
+    preset = presets.to_preset(spec, name="x")
+    export = doc.write_render(image, preset, tmp_path / "deep" / "out.png")
+    assert export.path.read_bytes() == doc.png_bytes(doc.render_preset(image, preset))
+    assert presets.describe(preset)["app"] == "glitch"
+    stack = EffectStack()
+    stack.add("noise", {"amount": 0.3}, "gate")
+    stack.add("crt")
+    stack.set_enabled(1, False)
+    rebuilt = EffectStack.from_entries(stack.to_entries())
+    assert rebuilt.effect_ids() == ["noise", "crt"] and rebuilt.mask_ids() == ("gate", None)
+    assert rebuilt.slots()[1].instance.enabled is False
+    rebuilt.move(0, 1)
+    assert rebuilt.effect_ids() == ["crt", "noise"]
+    with pytest.raises(IndexError):
+        rebuilt.move(0, 5)
+    with pytest.raises(KeyError):
+        stack.add("not_an_effect")
+    assert doc.fit_mask(np.zeros((8, 8), np.float32), (4, 4)).shape == (4, 4)
+    rng = np.random.default_rng(1)
+    big = EffectStack()
+    big.add("noise", {"amount": 0.5}, "big")
+    target = tmp_path / "big.json"
+    presets.save_spec(target, spec, stack=big, masks={"big": rng.random((320, 320), np.float32)})
+    entry = json.loads(target.read_text())["masks"]["big"]
+    assert "path" in entry and "data" not in entry and Path(entry["path"]).exists()
+    assert presets.validate(target).ok
+    loaded = presets.read_preset(target)
+    assert doc.render_preset(rng.random((320, 320, 3), np.float32), loaded).shape == (320, 320, 3)
+    assert doc.context_of_preset(loaded).mask_ids == ("big",)
+
+
+def test_cli_render_verbs_and_no_qt(capsys: pytest.CaptureFixture[str], tmp_path: Path,
+                                    image_file: Path) -> None:
+    """§8 render: exit codes, --json purity, suffix rules, and the CLI path imports no Qt."""
+    T = tmp_path
+    P, SRC = T / "preset.json", image_file
+    presets.save_spec(P, presets.default_spec())
+    out = T / "out.png"
+    assert _r(P, SRC, out, "--json") == cli.EXIT_OK
+    assert json.loads(capsys.readouterr().out)["bytes"] == out.stat().st_size
+    assert cli.main(["render", "--json"]) == cli.EXIT_USAGE
+    assert json.loads(capsys.readouterr().out)["ok"] is False
+    assert _r(T / "nope.json", SRC, T / "a.png") == cli.EXIT_USAGE
+    assert _r(P, T / "nope.png", T / "b.png") == cli.EXIT_RENDER
+    bare = T / "no-suffix"
+    assert cli.main([]) == cli.EXIT_USAGE
+    assert _r(P, SRC, bare) == cli.EXIT_OK and bare.with_suffix(".png").exists()
+    jpg = T / "photo.jpg"
+    assert _r(P, SRC, jpg) == cli.EXIT_RENDER
+    assert not jpg.exists() and ".jpg" in capsys.readouterr().err
+    for path in sorted(PACKAGE.glob("*.py")):
+        full = _imports(path)
+        tops = {n.split(".")[0] for n in full}
+        qt = "PySide6" in tops or any(n.startswith("lattice_core.ui") for n in full)
+        assert qt == (path.stem in GUI_MODULES), path.name
+        assert not tops & {"lattice_dither", "lattice_glyph"}, path.name
+        assert not any(n.startswith("lattice_core.animation") for n in full), path.name
+    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(SRC),
+                            target=str(T / "bare.png"), preset=str(P))
+    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
+                            text=True, timeout=300, check=False)
+    assert result.returncode == 0, result.stderr
+    assert (T / "bare.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
+
+
+def test_cli_presets_bridge_and_batch(capsys: pytest.CaptureFixture[str],
+                                      monkeypatch: pytest.MonkeyPatch,
+                                      tmp_path: Path, image_file: Path) -> None:
+    """§8 presets/bridge/batch: tiers, host absent vs present, and a recursive batch."""
+    T = tmp_path
+    P, SRC = str(T / "preset.json"), str(image_file)
+    presets.save_spec(P, presets.default_spec())
+    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "show", P, "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "validate", P, "--json"]) == cli.EXIT_OK
+    (T / "broken.json").write_text("{not json", encoding="utf-8")
+    assert cli.main(["presets", "validate", str(T / "broken.json"), "--json"]) == cli.EXIT_USAGE
+    assert '"ok": false' in capsys.readouterr().out
+    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
+    report = json.loads(capsys.readouterr().out)
+    assert report["ok"] and [e["host"] for e in report["hosts"]] == ["photocraft", "designcraft"]
+    monkeypatch.setattr(cli, "discover_host", lambda host: None)
+    assert cli.host_report(["photocraft", "designcraft"]) == [
+        {"host": "photocraft", "connected": False}, {"host": "designcraft", "connected": False}]
+    assert cli.main(["bridge", "push", "--preset", P, "--host", "designcraft",
+                     "--in", SRC]) == cli.EXIT_BRIDGE
+    assert cli.main(["bridge", "pull", "--preset", P, "--out", str(T / "o.png")]) == cli.EXIT_BRIDGE
+    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
+    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
+    assert cli.main(["bridge", "pull", "--preset", P, "--out", str(T/"pulled.png")]) == cli.EXIT_OK
+    assert (T / "pulled.png").exists()
+    assert cli.main(["bridge", "push", "--preset", P, "--host", "photocraft",
+                     "--in", SRC, "--json"]) == cli.EXIT_OK
+    assert json.loads(capsys.readouterr().out)["object_id"] == 3
+    source_dir = T / "in"
+    (source_dir / "sub").mkdir(parents=True)
+    for path in (source_dir / "a.png", source_dir / "sub" / "b.png"):
+        _png(path, color.to_rgb8(np.full((16, 16, 3), 0.4, np.float32)))
+    out_dir = T / "out"
+    assert cli.main(["batch", "--preset", P, "--in", str(source_dir),
+                     "--out", str(out_dir), "--recursive"]) == cli.EXIT_OK
+    assert sorted(p.name for p in out_dir.rglob("*.png")) == ["a.png", "b.png"]


CODER NOTES AND DEVIATIONS (attempt 2, transcript)
(vide)