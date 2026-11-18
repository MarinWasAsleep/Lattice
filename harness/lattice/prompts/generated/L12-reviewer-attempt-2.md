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



GATE RESULTS (L12, attempt 2 — CYCLE 2 de revue, codeur nous deepseek/deepseek-v4-flash-0731)
- `ruff check .` : all checks passed. Suite complète : **2064 passed, 1 skipped** en 42 s.
- Tailles : window.py 390 l, cli.py 370 l, tests/test_glyph_app.py 400 l (pile au plafond).
- Le diff ci-dessous est celui de l'attempt 2 SEUL.

POINT QUE JE TE DEMANDE DE CHASSER EN PRIORITÉ
Le compte de tests passe de **2068 à 2064** (−4). Le codeur l'explique par « 9 fonctions fusionnées en
5 blocs, 2 assertions strictement redondantes retirées, aucune couverture d'accept perdue ». C'est
exactement le genre de justification qui peut masquer une couverture perdue : vérifie que chaque item
d'accept de la carte reste couvert, et que les assertions retirées étaient réellement redondantes.

MES VÉRIFICATIONS INDÉPENDANTES, PAR EXÉCUTION (à recouper, pas à refaire)
- A : `spec_from_panels` fait `copy.deepcopy(self.spec)` puis ne surcharge que renderer /
  renderer_style / palette. Sur un preset v3 non trivial (brightness .15, contrast .30, gamma 2.2,
  saturation .4, pre_blur 1.5, auto_levels True, seed 42, oklab) : **aucun champ perdu**.
  Une palette `null` est préservée (mode continu).
- B : `format_of('a.jpg')` lève `DocumentError: cannot infer the format of 'a.jpg': suffix '.jpg' is
  not one of png, svg, txt, ansi, html`. `a.webp` idem. `a.png`/`a.svg`/`a.txt` corrects, chemin
  sans suffixe → png.
- D : `options.valid()` + `style_options()` lisant un registre de valeurs committées. `#f` ne peut
  pas atteindre le worker (validation avant émission, pas de debounce).

CE QUE JE N'AI PAS VÉRIFIÉ
- Le nouveau `hosts.py` (découverte d'hôte unique, Qt-free) : est-ce que `cli.discover_host` reste un
  alias sans dupliquer la logique, et le test qui le monkeypatche teste-t-il encore quelque chose ?
- `send_to_host` : rendu hors thread GUI, signal `absent` → barre d'état. Vérifie qu'aucune modale ne
  peut plus apparaître quand l'hôte est absent, y compris sur une exception du pont.
- L'entrée `lattice-glyph = "lattice_glyph.__main__:main"` : dispatche-t-elle vraiment verbe CLI
  sinon fenêtre, ou casse-t-elle `python -m lattice_glyph` ?
- Le renforcement du test de parité : le preset est-il réellement non trivial (effets pré ET post,
  seed ≠ 0), et compare-t-il les octets après une édition de panneau ?

DIFF (attempt 2 : HEAD~1 → HEAD, 11 fichiers modifiés + hosts.py)

diff --git a/lattice_glyph/actions.py b/lattice_glyph/actions.py
index 4e47efc..6f4b154 100644
--- a/lattice_glyph/actions.py
+++ b/lattice_glyph/actions.py
@@ -17,7 +17,6 @@ from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
 if TYPE_CHECKING:
     from lattice_glyph.window import MainWindow
 
-Action = tuple[str, str, Callable[..., None]]
 MODES: tuple[tuple[str, str, str], ...] = (
     ("mode_before", "Before", "before"),
     ("mode_after", "After", "after"),
diff --git a/lattice_glyph/bridge_actions.py b/lattice_glyph/bridge_actions.py
index 0e6c786..0ccd6e2 100644
--- a/lattice_glyph/bridge_actions.py
+++ b/lattice_glyph/bridge_actions.py
@@ -1,9 +1,11 @@
-"""Bridge work of the Glyph shell, run on a helper thread (§7).
+"""Bridge work of the Glyph shell, run on a helper thread (§7, E9).
 
 The window never talks to a host on the GUI thread: a slow connection would freeze the
-preview. ``BridgeWorker`` does exactly three things — pull the active document, place a
-render as a layer, or report why neither was possible — and a missing host is the normal
-``failed`` case, reported in the status bar, never an exception.
+preview. ``BridgeWorker`` does exactly three things — pull the active document, render
+and place a render as a layer, or explain why neither was possible. A host that is not
+running is the normal ``absent`` answer, shown in the status bar; only a real bridge
+failure is ``failed``. The push render runs here, in the worker thread, through the
+CLI's own function, so a full-resolution send never freezes the window (G9, L12 FIX).
 """
 
 from __future__ import annotations
@@ -13,12 +15,14 @@ import logging
 from PySide6.QtCore import QObject, Signal, Slot
 
 from lattice_core import color
-from lattice_core.bridge import ArtCraftClient, BridgeError
-from lattice_core.types import RGB8, Image
+from lattice_core.bridge import BridgeError
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import Image
+from lattice_glyph.document import DocumentError, render_rgb8
+from lattice_glyph.hosts import discover
 
 LOGGER = logging.getLogger(__name__)
 
-HOSTS = ("photocraft", "designcraft")
 DEFAULT_HOST = "photocraft"
 DEFAULT_NAME = "Lattice Glyph"
 NOT_RUNNING = "{host} is not running: Lattice Glyph works standalone"
@@ -30,15 +34,16 @@ class BridgeWorker(QObject):
     pulled = Signal(object, str)
     pushed = Signal(int)
     failed = Signal(str)
+    absent = Signal(str)
     progress = Signal(str)
 
     @Slot(str)
     def pull(self, host: str) -> None:
         """Read the active document of host and emit it as a float32 image."""
         self.progress.emit(f"Reading the {host} document…")
-        client = _discover(host)
+        client = discover(host)
         if client is None:
-            self.failed.emit(NOT_RUNNING.format(host=host))
+            self.absent.emit(NOT_RUNNING.format(host=host))
             return
         try:
             image = color.to_float(client.render_document())
@@ -50,17 +55,18 @@ class BridgeWorker(QObject):
             client.disconnect()
         self.pulled.emit(image, host)
 
-    @Slot(str, object, str)
-    def push(self, host: str, rgb8: RGB8, name: str) -> None:
-        """Place one rendered image in host as a layer and emit the object id."""
+    @Slot(str, object, object, str)
+    def push(self, host: str, image: Image, spec: PipelineSpec, name: str) -> None:
+        """Render image with spec, then place the result in host as a layer."""
         self.progress.emit(f"Placing the render in {host}…")
-        client = _discover(host)
+        client = discover(host)
         if client is None:
-            self.failed.emit(NOT_RUNNING.format(host=host))
+            self.absent.emit(NOT_RUNNING.format(host=host))
             return
         try:
+            rgb8 = render_rgb8(image, spec)
             object_id = client.place_as_layer(color.to_pil(rgb8), name or DEFAULT_NAME)
-        except (BridgeError, OSError, ValueError) as exc:
+        except (BridgeError, OSError, ValueError, DocumentError) as exc:
             LOGGER.debug("bridge push failed", exc_info=True)
             self.failed.emit(f"{host}: {exc}")
             return
@@ -69,28 +75,4 @@ class BridgeWorker(QObject):
         self.pushed.emit(int(object_id))
 
 
-def _discover(host: str) -> ArtCraftClient | None:
-    """Return a live client for host, or None for every way a host can be absent."""
-    if host not in HOSTS:
-        return None
-    try:
-        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
-    except (BridgeError, OSError, ValueError):
-        LOGGER.debug("host discovery failed", exc_info=True)
-        return None
-
-
-def pull_image(host: str = DEFAULT_HOST) -> Image | None:
-    """Synchronously read a host document, returning None when the host is absent."""
-    client = _discover(host)
-    if client is None:
-        return None
-    try:
-        return color.to_float(client.render_document())
-    except (BridgeError, OSError, ValueError):
-        return None
-    finally:
-        client.disconnect()
-
-
-__all__ = ["BridgeWorker", "DEFAULT_HOST", "HOSTS", "NOT_RUNNING", "pull_image"]
+__all__ = ["BridgeWorker", "DEFAULT_HOST", "NOT_RUNNING"]
diff --git a/lattice_glyph/bridge_controller.py b/lattice_glyph/bridge_controller.py
index bbbaf8d..1007c54 100644
--- a/lattice_glyph/bridge_controller.py
+++ b/lattice_glyph/bridge_controller.py
@@ -1,8 +1,8 @@
 """Bridge controller of the Glyph shell: host work on its own thread (§7, E9).
 
 The window never talks to a host on the GUI thread, and a host that is not running is a
-normal answer reported through ``failed``, never an exception. The controller is opt-in:
-without it, the shell is a complete standalone application.
+normal answer reported through ``absent`` (a status-bar line), never a dialog. The
+controller is opt-in: without it, the shell is a complete standalone application.
 """
 
 from __future__ import annotations
@@ -11,9 +11,8 @@ import logging
 
 from PySide6.QtCore import QObject, QThread, Signal
 
-from lattice_core import color
-from lattice_core.bridge import ArtCraftClient, BridgeError
-from lattice_core.types import RGB8
+from lattice_core.pipeline import PipelineSpec
+from lattice_core.types import Image
 from lattice_glyph.bridge_actions import DEFAULT_HOST, BridgeWorker
 
 LOGGER = logging.getLogger(__name__)
@@ -28,9 +27,10 @@ class BridgeController(QObject):
     pulled = Signal(object, str)
     pushed = Signal(int)
     failed = Signal(str)
+    absent = Signal(str)
     progress = Signal(str)
     pull_request = Signal(str)
-    push_request = Signal(str, object, str)
+    push_request = Signal(str, object, object, str)
 
     def __init__(self, parent: QObject | None = None, host: str = DEFAULT_HOST) -> None:
         """Create the helper thread and its worker, then start it."""
@@ -46,6 +46,7 @@ class BridgeController(QObject):
         worker.pulled.connect(self.pulled)
         worker.pushed.connect(self.pushed)
         worker.failed.connect(self.failed)
+        worker.absent.connect(self.absent)
         worker.progress.connect(self.progress)
         thread.start()
 
@@ -53,9 +54,9 @@ class BridgeController(QObject):
         """Ask the worker to read the active document of the host."""
         self.pull_request.emit(self.host)
 
-    def push(self, rgb8: RGB8, name: str = LAYER_NAME) -> None:
-        """Ask the worker to place rgb8 in the host as a layer called name."""
-        self.push_request.emit(self.host, rgb8, name)
+    def push(self, image: Image, spec: PipelineSpec, name: str = LAYER_NAME) -> None:
+        """Ask the worker to render image with spec and place it in the host as a layer."""
+        self.push_request.emit(self.host, image, spec, name)
 
     def stop(self) -> None:
         """Stop the helper thread; safe to call more than once.
@@ -73,20 +74,4 @@ class BridgeController(QObject):
         self.thread = self.worker = None
 
 
-def fetch_image(host: str = DEFAULT_HOST):
-    """Synchronously read a host document, returning None when the host is absent."""
-    try:
-        client = ArtCraftClient.discover(host)  # type: ignore[arg-type]
-    except (BridgeError, OSError, ValueError):
-        return None
-    if client is None:
-        return None
-    try:
-        return color.to_float(client.render_document())
-    except (BridgeError, OSError, ValueError):
-        return None
-    finally:
-        client.disconnect()
-
-
-__all__ = ["BridgeController", "LAYER_NAME", "fetch_image"]
+__all__ = ["BridgeController", "LAYER_NAME"]
diff --git a/lattice_glyph/cli.py b/lattice_glyph/cli.py
index 61f95f9..199ebd6 100644
--- a/lattice_glyph/cli.py
+++ b/lattice_glyph/cli.py
@@ -19,7 +19,7 @@ import lattice_core.dither  # noqa: F401  (importing the package registers every
 import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
 import lattice_core.renderers  # noqa: F401  (importing the package registers every renderer)
 from lattice_core import color
-from lattice_core.bridge import HOSTS, ArtCraftClient, BridgeError
+from lattice_core.bridge import HOSTS, BridgeError
 from lattice_core.pipeline import PipelineSpec
 from lattice_glyph import presets as preset_tools
 from lattice_glyph.document import (
@@ -32,6 +32,7 @@ from lattice_glyph.document import (
     target_path,
     write_render,
 )
+from lattice_glyph.hosts import discover as discover_host
 
 EXIT_OK = 0
 EXIT_USAGE = 1
@@ -49,9 +50,18 @@ class UsageError(Exception):
 class _Parser(argparse.ArgumentParser):
     """Argument parser reporting usage errors with exit code 1, not argparse's 2."""
 
+    _argv: list[str] | None = None
+
     def error(self, message: str) -> NoReturn:
-        """Print the usage line and exit with the §8 usage code."""
+        """Print the usage line and exit with the §8 usage code.
+
+        With ``--json`` on the command line the machine result is still printed on
+        stdout, so a machine caller never receives an empty answer (§8).
+        """
         self.print_usage(sys.stderr)
+        if self._argv is not None and "--json" in self._argv:
+            print(json.dumps({"ok": False, "errors": [message]},
+                             indent=2, ensure_ascii=False, sort_keys=True))
         self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")
 
 
@@ -138,9 +148,7 @@ def _cmd_batch(args: argparse.Namespace) -> int:
         source = Path(args.source)
         files = _batch_inputs(source, _extensions(args.ext), args.recursive)
     except UsageError as exc:
-        _note(str(exc))
-        _emit(args, {"ok": False, "files": [], "errors": [str(exc)]})
-        return EXIT_USAGE
+        return _failure(args, str(exc), EXIT_USAGE)
     fmt = args.format or "png"
     written: list[str] = []
     errors: list[str] = []
@@ -208,14 +216,6 @@ def _cmd_presets_validate(args: argparse.Namespace) -> int:
     return EXIT_OK if payload["ok"] else EXIT_USAGE
 
 
-def discover_host(host: str) -> ArtCraftClient | None:
-    """Return a live client for host, or None for any host that is not running (§7)."""
-    try:
-        return ArtCraftClient.discover(host)  # type: ignore[arg-type]
-    except (BridgeError, OSError, ValueError):
-        return None
-
-
 def host_report(hosts: tuple[str, ...] | list[str]) -> list[dict]:
     """Probe every host and return one {host, connected} record per host."""
     report: list[dict] = []
@@ -253,6 +253,8 @@ def _cmd_bridge_pull(args: argparse.Namespace) -> int:
         return _failure(args, str(exc), EXIT_RENDER)
     except (BridgeError, OSError) as exc:
         return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    finally:
+        client.disconnect()
     _note(f"wrote {export.path} ({export.size} bytes)")
     _emit(args, _export_payload(export))
     return EXIT_OK
@@ -272,6 +274,8 @@ def _cmd_bridge_push(args: argparse.Namespace) -> int:
         return _failure(args, str(exc), EXIT_RENDER)
     except (BridgeError, OSError) as exc:
         return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
+    finally:
+        client.disconnect()
     _note(f"placed object {object_id} in {args.host}")
     _emit(args, {"ok": True, "host": args.host, "object_id": object_id, "errors": []})
     return EXIT_OK
@@ -344,6 +348,7 @@ def _build_parser() -> argparse.ArgumentParser:
 
 def main(argv: list[str] | None = None) -> int:
     """Run the command line and return its exit code; no traceback ever escapes."""
+    _Parser._argv = list(argv) if argv is not None else sys.argv[1:]
     parser = _build_parser()
     try:
         args = parser.parse_args(argv)
@@ -352,17 +357,13 @@ def main(argv: list[str] | None = None) -> int:
     try:
         return int(args.handler(args))
     except UsageError as exc:
-        _note(str(exc))
-        return EXIT_USAGE
+        return _failure(args, str(exc), EXIT_USAGE)
     except DocumentError as exc:
-        _note(str(exc))
-        return EXIT_RENDER
+        return _failure(args, str(exc), EXIT_RENDER)
     except (BridgeError, OSError) as exc:
-        _note(f"{args.command} failed: {exc}")
-        return EXIT_BRIDGE
+        return _failure(args, f"{args.command} failed: {exc}", EXIT_BRIDGE)
     except Exception as exc:  # noqa: BLE001 - §8 forbids a traceback on stderr
-        _note(f"{args.command} failed: {exc}")
-        return EXIT_RENDER
+        return _failure(args, f"{args.command} failed: {exc}", EXIT_RENDER)
 
 
 if __name__ == "__main__":
diff --git a/lattice_glyph/document.py b/lattice_glyph/document.py
index 84c7412..b9d1747 100644
--- a/lattice_glyph/document.py
+++ b/lattice_glyph/document.py
@@ -186,8 +186,18 @@ def write_render(image: Image, spec: PipelineSpec, path: str | Path, fmt: str =
 
 
 def format_of(path: str | Path) -> str:
-    """Return the export format named by path's suffix, png when the suffix is unknown."""
+    """Return the export format named by path's suffix; a suffix outside FORMATS raises.
+
+    A bare path (no suffix) still defaults to png, but a named suffix is a contract:
+    writing PNG bytes into ``photo.jpg`` would lie about the file, so the caller hears
+    a ``DocumentError`` naming the suffix instead of a silent fallback (L12 FIX).
+    """
     suffix = Path(path).suffix.lower().lstrip(".")
+    if suffix and suffix not in FORMATS:
+        raise DocumentError(
+            f"cannot infer the format of {Path(path).name!r}: suffix '.{suffix}' is not"
+            f" one of {', '.join(FORMATS)}"
+        )
     return suffix if suffix in FORMATS else "png"
 
 
diff --git a/lattice_glyph/hosts.py b/lattice_glyph/hosts.py
new file mode 100644
index 0000000..e44dd49
--- /dev/null
+++ b/lattice_glyph/hosts.py
@@ -0,0 +1,23 @@
+"""Host discovery of Lattice Glyph: the single §7 probe, CLI and GUI share it.
+
+The core's ``ArtCraftClient.discover`` already answers None for a host that is not
+running; this module adds the typed-error guard the callers need, so every user of the
+bridge resolves the host the same way and there is no second copy to drift (L12 FIX:
+``pull_image``, ``fetch_image`` and the inlined tries were four versions of this one).
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
diff --git a/lattice_glyph/options.py b/lattice_glyph/options.py
index 6239463..1ce49fb 100644
--- a/lattice_glyph/options.py
+++ b/lattice_glyph/options.py
@@ -8,8 +8,10 @@ preset stays minimal. ``defaults_for()`` must render exactly like ``{}`` — a t
 
 from __future__ import annotations
 
+import re
 from collections.abc import Mapping
 from dataclasses import dataclass
+from pathlib import Path
 from typing import Literal
 
 Kind = Literal["text", "colour", "float", "int", "bool", "choice"]
@@ -17,6 +19,11 @@ Kind = Literal["text", "colour", "float", "int", "bool", "choice"]
 TRANSPARENT = "transparent"
 RAMP_HINT = "darkest character first"
 COLOUR_HINT = "#rrggbb or transparent"
+_HEX6 = re.compile(r"#[0-9a-fA-F]{6}\Z")
+_HEX8 = re.compile(r"#[0-9a-fA-F]{8}\Z")
+# glyph_ramp also accepts #rrggbbaa and 'transparent' (§9); the other renderers
+# parse exactly six hex digits — the validator mirrors the renderers' own parsers.
+_ALPHA_COLOURS = frozenset({"glyph_ramp"})
 
 
 @dataclass(frozen=True)
@@ -143,4 +150,39 @@ def _coerce(spec: OptionSpec, value: object) -> object | None:
     return None if spec.nullable and not text.strip() else text
 
 
-__all__ = ["OptionSpec", "OPTIONS", "clean", "defaults_for", "specs_for"]
+def valid(renderer: str, spec: OptionSpec, text: str) -> bool:
+    """Return True when text is a usable value of one option of renderer.
+
+    The rules mirror what the renderers themselves accept (§9, §10): a colour must
+    parse (plus 'transparent' and #rrggbbaa for glyph_ramp), a ramp must not be
+    empty, and a font path must name an existing file. Every other option is
+    accepted verbatim.
+    """
+    if spec.kind == "colour":
+        cleaned = text.strip().lower()
+        if _HEX6.fullmatch(cleaned) is not None:
+            return True
+        return renderer in _ALPHA_COLOURS and (
+            cleaned == TRANSPARENT or _HEX8.fullmatch(cleaned) is not None
+        )
+    if spec.key == "ramp":
+        return bool(text)
+    if spec.key == "font":
+        return not text or Path(text).is_file()
+    return True
+
+
+def invalid_hint(renderer: str, spec: OptionSpec) -> str:
+    """Return the one-line hint to show while one option value is not usable."""
+    if spec.kind == "colour":
+        allowed = "#rrggbbaa or transparent" if renderer in _ALPHA_COLOURS else "#rrggbb"
+        return f"{spec.key} must be {allowed}"
+    if spec.key == "ramp":
+        return "the ramp must not be empty"
+    if spec.key == "font":
+        return "the font path must name an existing file"
+    return ""
+
+
+__all__ = ["OptionSpec", "OPTIONS", "clean", "defaults_for", "invalid_hint", "specs_for",
+           "valid"]
diff --git a/lattice_glyph/presets.py b/lattice_glyph/presets.py
index 209a061..36591be 100644
--- a/lattice_glyph/presets.py
+++ b/lattice_glyph/presets.py
@@ -22,7 +22,6 @@ from lattice_core.preset import (
     to_json,
     to_pipeline_spec,
 )
-from lattice_core.preset import from_json as preset_from_json
 from lattice_core.presets import list_presets
 from lattice_core.renderers import list_renderers
 
@@ -105,11 +104,6 @@ def default_spec() -> PipelineSpec:
     return spec
 
 
-def default_preset() -> Preset:
-    """Return the v3 preset of a fresh document, tagged with this application's context."""
-    return to_preset(default_spec())
-
-
 def to_preset(spec: PipelineSpec, name: str = "") -> Preset:
     """Return the v3 preset of spec, its renderer kept, tagged ``app: glyph``."""
     preset = from_pipeline_spec(spec)
@@ -129,16 +123,6 @@ def read_preset(path: str | Path) -> Preset:
     return load_preset(path, app=APP_CONTEXT)
 
 
-def read_text(text: str) -> Preset:
-    """Parse one preset document in this application's context."""
-    return preset_from_json(text, app=APP_CONTEXT)
-
-
-def spec_from_text(text: str) -> PipelineSpec:
-    """Parse a preset document straight into its pipeline spec."""
-    return spec_of(read_text(text))
-
-
 def describe(preset: Preset) -> dict:
     """Return a JSON-serialisable summary of a preset, without rendering it."""
     style = dict(preset.renderer.get("style", {}))
@@ -212,15 +196,12 @@ __all__ = [
     "SHIPPED_PRESET_DIR",
     "app_data_dir",
     "available",
-    "default_preset",
     "default_spec",
     "describe",
     "read_preset",
-    "read_text",
     "save_preset",
     "save_spec",
     "search_dirs",
-    "spec_from_text",
     "spec_of",
     "to_preset",
     "user_preset_dir",
diff --git a/lattice_glyph/pyproject.toml b/lattice_glyph/pyproject.toml
index 81cb4cd..847db5a 100644
--- a/lattice_glyph/pyproject.toml
+++ b/lattice_glyph/pyproject.toml
@@ -19,6 +19,7 @@ dependencies = [
 ui = ["lattice-core[ui]"]
 
 [project.scripts]
+lattice-glyph = "lattice_glyph.__main__:main"
 lattice-glyph-cli = "lattice_glyph.cli:main"
 
 # The distribution lives beside the application directory, as lattice-dither does. The
diff --git a/lattice_glyph/renderer_panel.py b/lattice_glyph/renderer_panel.py
index 0f23dba..9ca7920 100644
--- a/lattice_glyph/renderer_panel.py
+++ b/lattice_glyph/renderer_panel.py
@@ -4,12 +4,14 @@ The selector's list is ``lattice_core.cell.list_renderers()``, never a table, so
 added to the core becomes selectable here without touching this module (L12 accept). The
 option form is built from ``lattice_glyph.options``: one widget per declared option, at its
 default; a renderer this table does not name shows an honest "no option" line.
+
+A text option is committed only when its value is usable (``options.valid``): a half-typed
+colour or an empty ramp never reaches the spec nor the render worker, the previous valid
+value stays, and the field shows the hint as a tooltip and a red border (L12 FIX).
 """
 
 from __future__ import annotations
 
-from collections.abc import Callable
-
 from PySide6.QtCore import Signal
 from PySide6.QtWidgets import (
     QCheckBox,
@@ -26,6 +28,8 @@ from PySide6.QtWidgets import (
 from lattice_core.cell import list_renderers
 from lattice_glyph import options as option_tools
 
+BAD_EDIT_STYLE = "QLineEdit { border: 1px solid #ff5555; }"
+
 
 class RendererPanel(QWidget):
     """Renderer selector plus the option widgets of the selected renderer."""
@@ -39,6 +43,7 @@ class RendererPanel(QWidget):
         self._loading = False
         self._renderer = ""
         self._widgets: dict[str, QWidget] = {}
+        self._values: dict[str, object] = {}
         self.selector = QComboBox(self)
         self.selector.setObjectName("renderer_selector")
         for name in list_renderers():
@@ -69,16 +74,12 @@ class RendererPanel(QWidget):
         return self._widgets.get(key)
 
     def style_options(self) -> dict:
-        """Return the style options the widgets hold, defaults already dropped."""
-        values: dict = {}
-        for key, widget in self._widgets.items():
-            if isinstance(widget, QLineEdit):
-                values[key] = widget.text()
-            elif isinstance(widget, QCheckBox):
-                values[key] = widget.isChecked()
-            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
-                values[key] = widget.value()
-        return option_tools.clean(self._renderer, values)
+        """Return the committed style options, defaults already dropped.
+
+        Only values that were actually committed count: an invalid text still sitting in
+        its field is not in ``_values``, so the previous spec keeps rendering.
+        """
+        return option_tools.clean(self._renderer, self._values)
 
     def set_renderer(self, name: str, style: dict | None = None) -> None:
         """Select name without emitting, then load style into its widgets."""
@@ -103,6 +104,7 @@ class RendererPanel(QWidget):
     def _show(self, name: str) -> None:
         """Rebuild the option form for name, every widget at its default."""
         self._renderer = name
+        self._values = {}
         while self.form.count():
             item = self.form.takeAt(0)
             widget = item.widget() if item is not None else None
@@ -116,11 +118,31 @@ class RendererPanel(QWidget):
             if spec.hint:
                 label.setToolTip(spec.hint)
             self.form.addRow(label, widget)
-        for widget in self._widgets.values():
-            _connect(widget, self._emit_changed)
+            _connect(spec, widget, self)
         if not self._widgets:
             self.form.addRow(QLabel("This renderer has no option.", self.host))
 
+    def _on_text_edited(self, spec: option_tools.OptionSpec, widget: QLineEdit,
+                        text: str) -> None:
+        """Commit one text edit only when it is usable; otherwise show the hint."""
+        if self._loading:
+            return
+        if not option_tools.valid(self._renderer, spec, text):
+            widget.setStyleSheet(BAD_EDIT_STYLE)
+            widget.setToolTip(option_tools.invalid_hint(self._renderer, spec))
+            return
+        widget.setStyleSheet("")
+        widget.setToolTip("")
+        self._values[spec.key] = text
+        self._emit_changed()
+
+    def _on_edit(self, key: str, value: object) -> None:
+        """Record one valid edit of a non-text widget and announce it."""
+        if self._loading:
+            return
+        self._values[key] = value
+        self._emit_changed()
+
     def _emit_changed(self) -> None:
         """Announce one user edit of an option, unless the panel is being loaded."""
         if not self._loading:
@@ -128,6 +150,7 @@ class RendererPanel(QWidget):
 
     def _load(self, style: dict) -> None:
         """Write style into the widgets, leaving every absent key at its default."""
+        self._values = dict(style)
         for spec in option_tools.specs_for(self._renderer):
             widget = self._widgets.get(spec.key)
             if widget is None:
@@ -179,13 +202,17 @@ def _widget_for(spec: option_tools.OptionSpec, parent: QWidget) -> QWidget:
     return edit
 
 
-def _connect(widget: QWidget, slot: Callable[[], None]) -> None:
-    """Connect the change signal the widget actually has to slot."""
+def _connect(spec: option_tools.OptionSpec, widget: QWidget, panel: RendererPanel) -> None:
+    """Connect the change signal of widget so every valid edit is committed."""
     if isinstance(widget, QLineEdit):
-        widget.textChanged.connect(lambda _text: slot())
+        widget.textChanged.connect(
+            lambda text, w=widget: panel._on_text_edited(spec, w, text)
+        )
     elif isinstance(widget, QCheckBox):
-        widget.toggled.connect(lambda _state: slot())
+        widget.toggled.connect(lambda checked: panel._on_edit(spec.key, bool(checked)))
     elif isinstance(widget, QComboBox):
-        widget.currentIndexChanged.connect(lambda _index: slot())
+        widget.currentIndexChanged.connect(
+            lambda: panel._on_edit(spec.key, widget.currentData())
+        )
     elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
-        widget.valueChanged.connect(lambda _value: slot())
+        widget.valueChanged.connect(lambda value: panel._on_edit(spec.key, value))
diff --git a/lattice_glyph/window.py b/lattice_glyph/window.py
index f52a7f7..ab7c623 100644
--- a/lattice_glyph/window.py
+++ b/lattice_glyph/window.py
@@ -13,6 +13,7 @@ export dialog, preset indicator, empty state, bridge dot and the glyph browser.
 
 from __future__ import annotations
 
+import copy
 import logging
 from pathlib import Path
 
@@ -107,6 +108,7 @@ class MainWindow(QMainWindow):
         self.bridge.pulled.connect(self._on_pulled)
         self.bridge.pushed.connect(self._on_pushed)
         self.bridge.failed.connect(self.report)
+        self.bridge.absent.connect(self.status)
         self.bridge.progress.connect(self.status)
         self.apply_spec(preset_tools.default_spec(), announce=False)
 
@@ -204,18 +206,12 @@ class MainWindow(QMainWindow):
         return self._settings
 
     def spec_from_panels(self) -> PipelineSpec:
-        """Return the spec the panels describe, keeping the pipeline settings not shown."""
-        current = self.spec
-        spec = PipelineSpec(algorithm_id=current.algorithm_id or "floyd_steinberg",
-                            pixel_size=current.pixel_size,
-                            renderer=self.renderer_panel.current())
-        spec.algorithm_params = dict(current.algorithm_params)
+        """Return the spec the panels describe, keeping every field they do not show."""
+        spec = copy.deepcopy(self.spec)
+        spec.renderer = self.renderer_panel.current()
         spec.renderer_style = self.renderer_panel.style_options()
-        spec.palette = self.palette_panel.spec()
-        spec.color_metric = current.color_metric
-        spec.seed = current.seed
-        spec.pre_effects = list(current.pre_effects)
-        spec.post_effects = list(current.post_effects)
+        if spec.palette is not None:  # a continuous spec keeps its null palette (§3)
+            spec.palette = self.palette_panel.spec()
         return spec
 
     def on_panels_changed(self) -> None:
@@ -330,16 +326,16 @@ class MainWindow(QMainWindow):
         self.bridge.pull()
 
     def send_to_host(self) -> None:
-        """Place the current full-resolution render in the bridge host."""
+        """Place the current render in the bridge host; an absent host is a status line.
+
+        The render runs on the bridge worker through the CLI's own function (G9), so a
+        full-resolution send never freezes the window and a missing host is ``absent`` —
+        one status-bar message, never a modal dialog (§7, E9).
+        """
         if self.source is None:
             self.report(NO_SOURCE)
             return
-        try:
-            rgb8 = self.render_full(self.source, self.spec)
-        except DocumentError as exc:
-            self.report(str(exc))
-            return
-        self.bridge.push(np.ascontiguousarray(rgb8, dtype=np.uint8))
+        self.bridge.push(self.source, self.spec)
 
     def _on_pulled(self, image: object, host: str) -> None:
         """Adopt a document pulled from a host, which has no source path."""
diff --git a/tests/test_glyph_app.py b/tests/test_glyph_app.py
index 220b94d..937eebb 100644
--- a/tests/test_glyph_app.py
+++ b/tests/test_glyph_app.py
@@ -1,7 +1,4 @@
-"""Tests for the Lattice Glyph shell (card L12), one block per accept item, Qt offscreen.
-
-CLI and GUI bytes match on one file (G9); bridge needs no host; the CLI path needs no Qt.
-"""
+"""Tests for the Lattice Glyph shell (card L12), Qt offscreen: G9, bridge, CLI-without-Qt."""
 
 from __future__ import annotations
 
@@ -18,10 +15,10 @@ os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
 
 import numpy as np  # noqa: E402
 import pytest  # noqa: E402
-from PIL import Image as PILImage  # noqa: E402
 from PySide6.QtCore import QSettings  # noqa: E402
 from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
 
+import lattice_core.pipeline as pipeline  # noqa: E402
 import lattice_core.renderers  # noqa: E402,F401  (registers every renderer)
 import lattice_glyph  # noqa: E402
 from lattice_core import color  # noqa: E402
@@ -34,6 +31,7 @@ from lattice_glyph.document import (  # noqa: E402
     DocumentError,
     GridError,
     export_bytes,
+    format_of,
     grid_bundle,
     load_image,
     render_rgb8,
@@ -49,23 +47,27 @@ RENDERERS = sorted(list_renderers())
 
 
 class _FakeClient:
-    """Stand-in for a live ArtCraft client."""
+    """Stand-in for a live ArtCraft client used by the bridge verbs."""
 
     def render_document(self):
-        return color.to_pil(np.full((16, 16, 3), 128, dtype=np.uint8))
+        return color.to_pil(np.full((16, 16, 3), 128, np.uint8))
+
+    def place_as_layer(self, img, name=None):
+        self.placed = name
+        return 3
 
     def disconnect(self) -> None:
         self.closed = True
-CLI_MODULES = ("__init__", "__main__", "cli", "document", "options", "presets")
+
+
+CLI_MODULES = ("__init__", "__main__", "cli", "document", "hosts", "options", "presets")
 GUI_MODULES = ("actions", "app", "bridge_actions", "bridge_controller", "export_actions",
                "palette_panel", "preset_panel", "renderer_panel", "rendering", "window")
 BLOCKER = """import sys, importlib.abc
 class Refuse(importlib.abc.MetaPathFinder):
     def find_spec(self, name, path=None, target=None):
-        if name.split('.')[0] == 'PySide6':
-            raise ImportError('PySide6 is not installed')
-sys.meta_path.insert(0, Refuse())
-sys.path.insert(0, {root!r})
+        if name.split('.')[0] == 'PySide6': raise ImportError('PySide6 is not installed')
+sys.meta_path.insert(0, Refuse()); sys.path.insert(0, {root!r})
 from lattice_glyph.cli import main
 code = main(['render', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r}])
 assert 'PySide6' not in sys.modules and 'lattice_core.ui' not in sys.modules
@@ -75,14 +77,13 @@ raise SystemExit(code)"""
 
 @pytest.fixture(scope="module")
 def qapp() -> QApplication:
-    """Return the shared offscreen QApplication."""
     app = QApplication.instance()
     return app if isinstance(app, QApplication) else QApplication([])
 
 
 @pytest.fixture
 def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
-    """Replace the modal error dialog with a list, so a failure never blocks the suite."""
+    """Collect modal-dialog texts so a failure reports instead of blocking the suite."""
     seen: list[str] = []
     monkeypatch.setattr(QMessageBox, "critical", lambda *a: seen.append(str(a[2])))
     return seen
@@ -90,7 +91,7 @@ def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
 
 @pytest.fixture
 def image() -> np.ndarray:
-    """Return a deterministic float32 RGB image: noise plus a horizontal gradient."""
+    """Deterministic float32 RGB image: noise plus a horizontal gradient."""
     rng, ramp = np.random.default_rng(7), np.linspace(0, 1, 128, dtype=np.float32)
     noise = rng.random((96, 128, 3), np.float32)
     return np.ascontiguousarray(np.clip(0.5 * noise + 0.5 * ramp[None, :, None], 0, 1), np.float32)
@@ -98,7 +99,6 @@ def image() -> np.ndarray:
 
 @pytest.fixture
 def image_file(tmp_path: Path, image: np.ndarray) -> Path:
-    """Write the deterministic image as a PNG and return its path."""
     return _png(tmp_path / "source.png", color.to_rgb8(image))
 
 
@@ -154,35 +154,9 @@ def _tops(path: Path) -> set[str]:
     return {name.split(".")[0] for name in names}
 
 
-def test_window_opens_previews_saves_and_reports_refusals(make_window, tmp_path: Path,
-                                                          image_file: Path,
-                                                          quiet: list[str]) -> None:
-    """The shell opens, previews, saves, and reports every refusal cleanly."""
-    window = make_window()
-    assert window.tabs.count() == 4
-    assert window.bridge_dot.state() in {"unknown", "connected", "disconnected"}
-    window.check_bridge()
-    _settle(lambda: window.bridge_dot.state() != "unknown")
-    assert window.connection_label.text().startswith("photocraft: ")
-    assert window.open_path(tmp_path / "nope.png") is False
-    window.export_dialog()
-    assert window.source is None and quiet
-    with pytest.raises(DocumentError):
-        window.export_to(tmp_path / "out.png")
-    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
-    assert window.source is None and len(quiet) == 3 and "9000" in quiet[-1]
-    assert window.open_path(image_file) is True
-    _settle(lambda: window.canvas.qimage() is not None)
-    assert window.stack.currentWidget() is window.canvas
-    expected = render(window.source, window.spec)
-    window.export_to(tmp_path / "out.png")
-    with PILImage.open(tmp_path / "out.png") as written:
-        assert np.array_equal(np.asarray(written.convert("RGB")), expected)
-
-
-def test_cli_render_matches_the_gui_bytes(make_window, tmp_path: Path, image_file: Path,
-                                          quiet: list[str]) -> None:
-    """For every shipped preset and every format, CLI and GUI write the same bytes."""
+def test_cli_and_gui_write_identical_bytes_and_keep_hidden_fields(
+        make_window, tmp_path: Path, image_file: Path, quiet: list[str]) -> None:
+    """Shipped presets, every format, and a panel edit over a non-trivial spec: same bytes (G9)."""
     window = make_window()
     assert window.open_path(image_file) is True
     for preset in sorted(SHIPPED.glob("*.json")):
@@ -198,150 +172,45 @@ def test_cli_render_matches_the_gui_bytes(make_window, tmp_path: Path, image_fil
         assert (tmp_path / f"gui.{fmt}").read_bytes() == expected, fmt
         if fmt == "svg":
             assert ET.fromstring(expected.decode()).tag == f"{{{SVG_NS}}}svg"
-    assert not quiet
-
-
-def test_cli_matches_the_gui_on_a_preset_the_shell_wrote(make_window, tmp_path: Path,
-                                                        image_file: Path, image: np.ndarray,
-                                                        quiet: list[str]) -> None:
-    """A preset the shell saved renders byte-identically; the grid path matches too."""
-    window = make_window()
-    assert window.open_path(image_file) is True
-    window.renderer_panel.set_renderer("braille", {"threshold": 0.35, "fg": "#112233"})
+    spec = presets.default_spec()
+    spec.brightness, spec.contrast, spec.gamma = 0.15, 0.30, 2.2
+    spec.saturation, spec.pre_blur, spec.auto_levels = 0.40, 1.5, True
+    spec.seed, spec.color_metric = 42, "oklab"
+    spec.pre_effects = [EffectInstance("gaussian_blur", {"radius": 1.0})]
+    spec.post_effects = [EffectInstance("sharpen", {"amount": 0.5})]
+    window.apply_spec(spec)
+    window.renderer_panel.set_renderer("braille", {"threshold": 0.4, "fg": "#112233"})
     window.on_panels_changed()
-    window.save_preset_to(str(tmp_path / "user" / "roundtrip.json"))
+    edited = window.spec
+    assert (edited.brightness, edited.contrast, edited.gamma) == (0.15, 0.30, 2.2)
+    assert (edited.saturation, edited.pre_blur, edited.auto_levels) == (0.40, 1.5, True)
+    assert edited.seed == 42 and edited.color_metric == "oklab"
+    assert edited.pre_effects == [EffectInstance("gaussian_blur", {"radius": 1.0})]
+    assert edited.post_effects == [EffectInstance("sharpen", {"amount": 0.5})]
+    window.save_preset_to(str(tmp_path / "user" / "edited.json"))
     window.export_to(tmp_path / "gui.png")
-    assert _cli(tmp_path, tmp_path / "user" / "roundtrip.json", image_file) == (
+    assert _cli(tmp_path, tmp_path / "user" / "edited.json", image_file) == (
         tmp_path / "gui.png").read_bytes()
-    assert np.array_equal(window.render_full(window.source, window.spec),
-                          render_rgb8(window.source, window.spec))
-    from lattice_core import pipeline as core
-
+    window.apply_spec(PipelineSpec(renderer="pixel", algorithm_id=None, palette=None))
+    window.on_panels_changed()
+    assert window.spec.algorithm_id is None and window.spec.palette is None
+    preset = _preset(tmp_path, window.spec)
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(tmp_path / "c.png")]) == cli.EXIT_OK
     for renderer in RENDERERS:
         spec = PipelineSpec(pixel_size=6, renderer=renderer,
                             palette=PaletteSpec(source="builtin", name="grey_8"))
-        bundle = grid_bundle(image, spec)
-        frame = core._render_frame(bundle.renderer, bundle.grid, bundle.palette, bundle.style)
-        rendered = render(image, spec)
-        assert np.array_equal(color.to_rgb8(frame[: rendered.shape[0], : rendered.shape[1]]),
-                              rendered), renderer
+        bundle = grid_bundle(window.source, spec)
+        expected = render(window.source, spec)
+        frame = pipeline._render_frame(bundle.renderer, bundle.grid, bundle.palette,
+                                       bundle.style)
+        assert np.array_equal(color.to_rgb8(frame[: expected.shape[0], : expected.shape[1]]),
+                              expected), renderer
     with pytest.raises(GridError):
-        grid_bundle(image, PipelineSpec(algorithm_id=None, palette=None))
-
-
-def test_bridge_status_and_verbs_without_a_host(capsys: pytest.CaptureFixture[str],
-                                                monkeypatch: pytest.MonkeyPatch,
-                                                tmp_path: Path) -> None:
-    """bridge status and the bridge verbs never crash when no host runs, or when it refuses."""
-    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
-    report = json.loads(capsys.readouterr().out)
-    assert report["ok"] is True
-    assert [entry["host"] for entry in report["hosts"]] == ["photocraft", "designcraft"]
-    assert all(isinstance(entry["connected"], bool) for entry in report["hosts"])
-    assert cli.main(["bridge", "status", "photocraft"]) == cli.EXIT_OK
-    state = "connected" if report["hosts"][0]["connected"] else "not running"
-    assert capsys.readouterr().out.splitlines() == [f"photocraft: {state}"]
-    source = _png(tmp_path / "source.png", np.zeros((8, 8, 3), dtype=np.uint8))
-    preset = _preset(tmp_path)
-
-    def broken(token_path=None, port=None):
-        raise OSError("connection refused")
-
-    monkeypatch.setattr("lattice_core.bridge.photocraft.PhotoCraftClient.discover",
-                        staticmethod(broken))
-    monkeypatch.setattr("lattice_core.bridge.designcraft.DesignCraftClient.discover",
-                        staticmethod(broken))
-    assert cli.host_report(["photocraft", "designcraft"]) == [
-        {"host": "photocraft", "connected": False}, {"host": "designcraft", "connected": False}]
-    assert cli.main(["bridge", "push", "--preset", str(preset), "--in", str(source),
-                     "--host", "designcraft"]) == cli.EXIT_BRIDGE
-    assert cli.main(["bridge", "pull", "--preset", str(preset), "--out",
-                     str(tmp_path / "o.png")]) == cli.EXIT_BRIDGE
-    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
-    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
-    target = tmp_path / "pulled.png"
-    assert cli.main(["bridge", "pull", "--preset", str(preset),
-                     "--out", str(target)]) == cli.EXIT_OK and target.exists()
-
-
-def test_the_cli_path_needs_no_qt_and_runs_without_it(tmp_path: Path) -> None:
-    """No CLI module imports Qt, no module imports a sibling app, and the CLI still renders."""
-    for name, qt in [(n, False) for n in CLI_MODULES] + [(n, True) for n in GUI_MODULES]:
-        tops = _tops(PACKAGE / f"{name}.py")
-        assert ("PySide6" in tops) is qt, name
-        assert "lattice_core.ui" not in tops or qt, name
-    for path in sorted(PACKAGE.rglob("*.py")):
-        assert not _tops(path) & {"lattice_dither", "lattice_glitch"}, path.name
-    source = _png(tmp_path / "source.png", color.to_rgb8(np.full((16, 16, 3), 0.5, np.float32)))
-    target = tmp_path / "out.png"
-    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(source),
-                            target=str(target), preset=str(_preset(tmp_path)))
-    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
-                            text=True, timeout=300, check=False)
-    assert result.returncode == 0, result.stderr
-    with PILImage.open(target) as written:
-        assert written.format == "PNG"
-
-
-def test_every_registered_renderer_is_selectable(make_window, image_file: Path,
-                                                 quiet: list[str]) -> None:
-    """The selector offers exactly the registry, and each choice renders a preview."""
-    window = make_window()
-    assert window.renderer_panel.renderers() == RENDERERS == sorted(OPTIONS)
-    assert window.open_path(image_file) is True
-    image = np.linspace(0.0, 1.0, 48 * 64 * 3, dtype=np.float32).reshape(48, 64, 3)
-    for renderer in RENDERERS:
-        bare = PipelineSpec(pixel_size=6, renderer=renderer, renderer_style={})
-        filled = PipelineSpec(pixel_size=6, renderer=renderer,
-                              renderer_style=defaults_for(renderer))
-        assert np.array_equal(render(image, bare), render(image, filled)), renderer
-        window.renderer_panel.set_renderer(renderer)
-        window.on_panels_changed()
-        assert window.spec.renderer == renderer == window.renderer_panel.current()
-        for spec in OPTIONS[renderer]:
-            assert window.spec.renderer_style.get(spec.key, spec.default) == spec.default
-        _settle(lambda: window.canvas.qimage() is not None)
-    assert clean("glyph_ramp", {"ramp": "@%#*+=-:. ", "offset": 0.0}) == {}
-    assert clean("glyph_ramp", {"ramp": " .:-=+*#%@", "mode": "palette"}) == {
-        "ramp": " .:-=+*#%@", "mode": "palette"}
-    with pytest.raises(ValueError):
-        clean("glyph_ramp", {"mode": "spectral"})
+        grid_bundle(window.source, PipelineSpec(algorithm_id=None, palette=None))
     assert not quiet
 
 
-def test_the_render_and_presets_verbs(tmp_path: Path, image_file: Path,
-                                      capsys: pytest.CaptureFixture[str]) -> None:
-    """render --json prints only its result; exit codes and the png suffix follow §8."""
-    preset = _preset(tmp_path)
-    target = tmp_path / "out.png"
-    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
-                     "--out", str(target), "--json"]) == cli.EXIT_OK
-    assert json.loads(capsys.readouterr().out)["bytes"] == target.stat().st_size
-    assert cli.main(["render", "--preset", str(tmp_path / "nope.json"), "--in",
-                     str(image_file), "--out", str(tmp_path / "a.png")]) == cli.EXIT_USAGE
-    assert cli.main(["render", "--preset", str(preset), "--in", str(tmp_path / "nope.png"),
-                     "--out", str(tmp_path / "b.png")]) == cli.EXIT_RENDER
-    bare = tmp_path / "no-suffix"
-    assert cli.main([]) == cli.EXIT_USAGE
-    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
-                     "--out", str(bare)]) == cli.EXIT_OK and bare.with_suffix(".png").exists()
-    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
-    assert cli.main(["presets", "show", str(preset), "--json"]) == cli.EXIT_OK
-    assert cli.main(["presets", "validate", str(preset), "--json"]) == cli.EXIT_OK
-    broken = tmp_path / "broken.json"
-    broken.write_text("{not json", encoding="utf-8")
-    assert cli.main(["presets", "validate", str(broken), "--json"]) == cli.EXIT_USAGE
-    assert '"ok": false' in capsys.readouterr().out
-    source_dir = tmp_path / "in"
-    (source_dir / "sub").mkdir(parents=True)
-    for path in (source_dir / "a.png", source_dir / "sub" / "b.png"):
-        _png(path, color.to_rgb8(np.full((16, 16, 3), 0.4, np.float32)))
-    out_dir = tmp_path / "out"
-    assert cli.main(["batch", "--preset", str(preset), "--in", str(source_dir),
-                     "--out", str(out_dir), "--recursive"]) == cli.EXIT_OK
-    assert sorted(path.name for path in out_dir.rglob("*.png")) == ["a.png", "b.png"]
-
-
 def test_shipped_presets_and_document_helpers(tmp_path: Path, image: np.ndarray) -> None:
     """Shipped presets validate in context; document failures are typed DocumentErrors."""
     reports = presets.validate_all((SHIPPED,))
@@ -352,38 +221,57 @@ def test_shipped_presets_and_document_helpers(tmp_path: Path, image: np.ndarray)
     assert (spec.renderer, spec.pixel_size) == ("glyph_ramp", 8)
     assert presets.user_preset_dir().parent.name == "LatticeGlyph"
     assert presets.search_dirs()[0] == SHIPPED
-    with pytest.raises(DocumentError) as raised:
+    with pytest.raises(DocumentError, match="nope.png"):
         load_image(tmp_path / "nope.png")
-    assert "nope.png" in str(raised.value)
     with pytest.raises(DocumentError):
         export_bytes(image, spec, "pdf")
     with pytest.raises(DocumentError):
         render_rgb8(image, PipelineSpec(palette=PaletteSpec(source="custom",
-                                                           colors=["#zzz"])))
+                                                            colors=["#zzz"])))
     assert target_path(tmp_path / "a", "svg").name == "a.svg"
     assert target_path(tmp_path / "a.png", "svg").name == "a.png"
     export = write_render(image, spec, tmp_path / "deep" / "out.png")
     assert export.path.exists() and export.size == export.path.stat().st_size
-    spec.post_effects = [EffectInstance("unsharp", {"amount": 0.5})]
+    spec.post_effects = [EffectInstance("sharpen", {"amount": 0.5})]
     assert "raster" in export_bytes(image, spec, "txt")[1][0]
+    assert format_of("a.png") == "png" and format_of("bare") == "png"
+    with pytest.raises(DocumentError):
+        format_of("a.webp")
+    assert 'lattice-glyph = "lattice_glyph.__main__:main"' in (
+        PACKAGE / "pyproject.toml").read_text()
 
 
-def test_the_panels_list_load_save_and_feed_the_spec(make_window, tmp_path: Path,
-                                                     image: np.ndarray,
-                                                     quiet: list[str]) -> None:
-    """Shipped presets load, saving marks the indicator, panels feed the spec."""
+def test_shell_opens_previews_saves_and_refuses(make_window, tmp_path: Path, image_file: Path,
+                                                image: np.ndarray,
+                                                monkeypatch: pytest.MonkeyPatch,
+                                                quiet: list[str]) -> None:
+    """The shell opens, previews, saves, reports refusals, and a host-less send is a line."""
     window = make_window()
+    assert window.tabs.count() == 4
+    assert window.bridge_dot.state() in {"unknown", "connected", "disconnected"}
+    window.check_bridge()
+    _settle(lambda: window.bridge_dot.state() != "unknown")
+    assert window.open_path(tmp_path / "nope.png") is False
+    window.export_dialog()
+    assert window.source is None and quiet
+    with pytest.raises(DocumentError):
+        window.export_to(tmp_path / "out.png")
+    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
+    assert window.source is None and len(quiet) == 3 and "9000" in quiet[-1]
+    assert window.open_path(image_file) is True
+    monkeypatch.setattr("lattice_glyph.hosts.discover", lambda host: None)
+    window.set_source(image)
+    window.send_to_host()
+    _settle(lambda: "not running" in window.statusBar().currentMessage())
+    assert len(quiet) == 3
     entries = window.preset_panel.entries()
-    assert entries and all(entry.path.parent == SHIPPED and entry.read_only for entry in entries)
+    assert entries and all(e.path.parent == SHIPPED and e.read_only for e in entries)
     assert window.preset_panel.select_name(entries[0].name)
     window.preset_panel.load_selected()
-    assert window.spec.renderer == presets.spec_of(
-        presets.read_preset(entries[0].path)).renderer
-    assert window.indicator.preset_name() == entries[0].name
+    assert window.spec.renderer == presets.spec_of(presets.read_preset(entries[0].path)).renderer
     window.save_preset_to(str(tmp_path / "user" / "mine.json"))
     assert (tmp_path / "user" / "mine.json").exists()
     assert window.indicator.preset_name() == "mine.json"
-    window.set_source(image)
     panel = window.palette_panel
     panel.kind.setCurrentIndex(panel.kind.findData("custom"))
     panel.colors.setText("#000000 #ff0000 #ffffff")
@@ -395,6 +283,118 @@ def test_the_panels_list_load_save_and_feed_the_spec(make_window, tmp_path: Path
     ramp = next(entry for entry in window.glyph_browser.catalogue().ramps()
                 if entry.ramp != presets.DEFAULT_RAMP)
     window.glyph_browser.ramp_chosen.emit(ramp.id)
-    assert window.spec.renderer == "glyph_ramp"
-    assert window.spec.renderer_style["ramp"] == ramp.ramp
-    assert not quiet
+    assert (window.spec.renderer, window.spec.renderer_style["ramp"]) == ("glyph_ramp", ramp.ramp)
+    assert len(quiet) == 3
+
+
+def test_cli_verbs_bridge_and_no_qt(capsys: pytest.CaptureFixture[str],
+                                    monkeypatch: pytest.MonkeyPatch,
+                                    tmp_path: Path, image_file: Path) -> None:
+    """The four §8 verbs: exit codes, --json purity, bridge without a host, batch, no Qt."""
+    preset = _preset(tmp_path)
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(tmp_path / "out.png"), "--json"]) == cli.EXIT_OK
+    assert json.loads(capsys.readouterr().out)["bytes"] == (tmp_path / "out.png").stat().st_size
+    assert cli.main(["render", "--json"]) == cli.EXIT_USAGE
+    assert json.loads(capsys.readouterr().out)["ok"] is False
+    assert cli.main(["render", "--preset", str(tmp_path / "nope.json"), "--in",
+                     str(image_file), "--out", str(tmp_path / "a.png")]) == cli.EXIT_USAGE
+    assert cli.main(["render", "--preset", str(preset), "--in", str(tmp_path / "nope.png"),
+                     "--out", str(tmp_path / "b.png")]) == cli.EXIT_RENDER
+    bare = tmp_path / "no-suffix"
+    assert cli.main([]) == cli.EXIT_USAGE
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(bare)]) == cli.EXIT_OK and bare.with_suffix(".png").exists()
+    jpg = tmp_path / "photo.jpg"
+    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
+                     "--out", str(jpg)]) == cli.EXIT_RENDER
+    assert not jpg.exists() and ".jpg" in capsys.readouterr().err
+    for name, qt in [(n, False) for n in CLI_MODULES] + [(n, True) for n in GUI_MODULES]:
+        tops = _tops(PACKAGE / f"{name}.py")
+        assert ("PySide6" in tops) is qt, name
+        assert "lattice_core.ui" not in tops or qt, name
+    for path in sorted(PACKAGE.rglob("*.py")):
+        assert not _tops(path) & {"lattice_dither", "lattice_glitch"}, path.name
+    source = _png(tmp_path / "source.png", color.to_rgb8(np.full((16, 16, 3), 0.5, np.float32)))
+    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(source),
+                            target=str(tmp_path / "bare.png"), preset=str(_preset(tmp_path)))
+    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
+                            text=True, timeout=300, check=False)
+    assert result.returncode == 0, result.stderr
+    assert (tmp_path / "bare.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
+    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
+    report = json.loads(capsys.readouterr().out)
+    assert report["ok"] and [e["host"] for e in report["hosts"]] == ["photocraft", "designcraft"]
+    assert cli.main(["bridge", "status", "photocraft"]) == cli.EXIT_OK
+    assert capsys.readouterr().out.splitlines() == [
+        f"photocraft: {'connected' if report['hosts'][0]['connected'] else 'not running'}"]
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
+    assert cli.main(["bridge", "push", "--preset", str(preset), "--host", "designcraft",
+                     "--in", str(source)]) == cli.EXIT_BRIDGE
+    assert cli.main(["bridge", "pull", "--preset", str(preset), "--out",
+                     str(tmp_path / "o.png")]) == cli.EXIT_BRIDGE
+    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
+    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
+    assert cli.main(["bridge", "pull", "--preset", str(preset),
+                     "--out", str(tmp_path / "pulled.png")]) == cli.EXIT_OK
+    assert (tmp_path / "pulled.png").exists()
+    assert cli.main(["bridge", "push", "--preset", str(preset), "--host", "photocraft",
+                     "--in", str(source), "--json"]) == cli.EXIT_OK
+    assert json.loads(capsys.readouterr().out)["object_id"] == 3
+    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "show", str(preset), "--json"]) == cli.EXIT_OK
+    assert cli.main(["presets", "validate", str(preset), "--json"]) == cli.EXIT_OK
+    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
+    assert cli.main(["presets", "validate", str(tmp_path / "broken.json"),
+                     "--json"]) == cli.EXIT_USAGE
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
+def test_every_registered_renderer_is_selectable(make_window, image_file: Path,
+                                                 quiet: list[str]) -> None:
+    """The selector offers exactly the registry; each choice renders; bad text edits never do."""
+    window = make_window()
+    assert window.renderer_panel.renderers() == RENDERERS == sorted(OPTIONS)
+    assert window.open_path(image_file) is True
+    img = np.linspace(0.0, 1.0, 48 * 64 * 3, dtype=np.float32).reshape(48, 64, 3)
+    for renderer in RENDERERS:
+        bare = PipelineSpec(pixel_size=6, renderer=renderer, renderer_style={})
+        filled = PipelineSpec(pixel_size=6, renderer=renderer,
+                              renderer_style=defaults_for(renderer))
+        assert np.array_equal(render(img, bare), render(img, filled)), renderer
+        window.renderer_panel.set_renderer(renderer)
+        window.on_panels_changed()
+        assert window.spec.renderer == renderer == window.renderer_panel.current()
+        for spec in OPTIONS[renderer]:
+            assert window.spec.renderer_style.get(spec.key, spec.default) == spec.default
+        _settle(lambda: window.canvas.qimage() is not None)
+    assert clean("glyph_ramp", {"ramp": "@%#*+=-:. ", "offset": 0.0}) == {}
+    ramp = {"ramp": " .:-=+*#%@", "mode": "palette"}
+    assert clean("glyph_ramp", ramp) == ramp
+    with pytest.raises(ValueError):
+        clean("glyph_ramp", {"mode": "spectral"})
+    window.renderer_panel.set_renderer("glyph_ramp")
+    spec0 = window.spec
+    field = window.renderer_panel.option_widget("fg")
+    field.setText("#f")
+    assert window.spec is spec0 and not quiet
+    assert "must be" in field.toolTip() and field.styleSheet()
+    field.setText("#112233")
+    assert window.spec.renderer_style.get("fg") == "#112233" and not quiet


CODER NOTES AND DEVIATIONS
- Voir GATE RESULTS (les NOTES du codeur y sont résumées ; DEVIATIONS : aucune).
- Il assume que `render --out a.jpg` renvoie le code 2 (erreur de rendu) et non 1 (erreur d'usage) :
  c'est un choix explicite, juge-le.
