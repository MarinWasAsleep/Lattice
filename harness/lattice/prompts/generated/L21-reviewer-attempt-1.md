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


## §6 Preset format v3

One format for the whole suite. Human-readable, diffable, portable.

```json
{
  "version": 3,
  "app": "glyph",
  "meta": {"name": "", "author": "", "created": ""},
  "renderer": {"name": "glyph_ramp", "style": {}},
  "palette": {"colors": ["#000000", "#ffffff"], "locked": false, "order": null,
              "source": "integrated",
              "extract": {"from": "image", "n_colors": 16, "rows": null}},
  "pipeline": {
    "algorithm": "floyd_steinberg", "params": {}, "color_metric": "srgb",
    "pixel_size": 1, "max_side": null, "brightness": 0.0, "contrast": 0.0,
    "gamma": 1.0, "saturation": 0.0, "pre_blur": 0.0, "auto_levels": false
  },
  "effects": [{"name": "scanlines", "params": {}, "enabled": true, "stage": "post", "mask": null}],
  "masks": {"flip": {"kind": "v_flip"}},
  "fonts": {"ramp": {"family": "DejaVu Sans Mono", "style": "", "fallback": ["mono"]}},
  "output": {"scale": 1, "width": null, "dpi": null},
  "seed": 0
}
```

**v3 completeness (S4, decided 2026-11-16).** The v3 format keeps every capability the v1/v2
formats had: `effects[].stage: "pre" | "post"` (default `post`), `palette.source` +
`palette.extract` (how the palette of a preset was obtained — integrated, extracted from the
image, or imported), `masks: {id: {...}}` referenced by `effects[].mask`, `fonts: {id: {family,
style, fallback[]}}` resolved by family name then shipped fallbacks (no absolute paths), and
`output: {scale, width?, dpi?}` feeding §17. Unknown keys remain preserved on round-trip.

Rules:

- `from_json` accepts versions 1, 2 and 3. Versions 1 and 2 are Lattice Dither formats and map to
  `app: "dither"`, `renderer: "pixel"`. Any other version raises `ValueError` naming it.
- Unknown top-level keys and unknown `style` keys are **preserved** on round-trip. A preset written
  by a newer app must survive a load/save by an older one.
- An `app` mismatch is not an error. Any app may load any preset. If the named renderer is absent,
  the app falls back to its default renderer and records a warning in the result.
- `to_json` writes sorted keys, two-space indent, one trailing newline.
- `seed` is part of the preset. Two runs of the same preset produce identical output.



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
### L21 · Preset interchange and gallery
- wave: 3 · deps: L12, L20 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/gallery.py`, `lattice_core/ui/gallery.py`, `tests/test_gallery.py`,
  `presets/**`
- context: §6 §11
- spec: a gallery showing every algorithm and renderer on one reference image, side by side — the
  documentation pattern that makes a 30-algorithm tool legible. Presets circulate between the three
  applications: a preset written by one loads in the others with a warning and a fallback renderer.
  Ship a starter set of at least 12 presets across the three apps.
- accept:
  - a preset written by `glyph` loads in `glitch` with a warning and renders.
  - a preset written by `dither` loads in `glyph` and renders with `pixel`.
  - the gallery renders every registered algorithm and renderer without raising.
  - at least 12 starter presets exist and all validate.
  - the gallery output is a single PNG under 4 MB.


GATE RESULTS
GATES (orchestrateur, rejoués) :
- G1 owns : seuls gallery.py, ui/gallery.py, test_gallery.py + presets/starter/*.json sont ajoutés ;
  presets/ v1 (12 fichiers) et les trois apps intacts ; les seuls autres changements de l'arbre sont
  la carte parallèle L-LOOP (animation.py) et les archives harness.
- G2 : 21 passed (tests/test_gallery.py, 7 s).
- G3 ruff (3 fichiers Python owns) : All checks passed.
- Starter presets : 12 fichiers v3 (dither_01_gameboy_fs.json, dither_02_pico8_bayer8.json, dither_03_ega_riemersma.json, dither_04_grey16_atkinson.json, glitch_01_vhs_soft.json, glitch_02_channel_rift.json, glitch_03_sort_echo.json, glitch_04_crt_finish.json, glyph_01_ascii_gameboy.json, glyph_02_braille_grey8.json, glyph_03_quadrant_pico8.json, glyph_04_shape_ega.json).
REVIEW FULL (cycle 1) : les 5 accepts + les 4 E1 déclarés + la qualité produit de la planche (légende
lisible ? placeholder explicite ? 41 cellules sans warning ?), l'interchange par les VRAIS lecteurs d'app
(l'auteur cite lattice_glyph.document.render_rgb8 et le lecteur de glitch), l'absence de duplication de
registre (available=), l'E8 (aucun import d'app dans le core), et la compat des starters avec les
validateurs réels.

DIFF (cumulatif HEAD -> arbre ; les 12 presets JSON sont listés dans GATE RESULTS — lis-en 2 ou 3 dans le repo pour le format)
diff --git a/lattice_core/gallery.py b/lattice_core/gallery.py
new file mode 100644
index 0000000..e785e05
--- /dev/null
+++ b/lattice_core/gallery.py
@@ -0,0 +1,264 @@
+"""Reference gallery and preset interchange: every algorithm and renderer side by side.
+
+The gallery renders one cell per registered algorithm and per registered renderer on a
+single reference image and composes them into one labelled contact sheet (L21, §6 §11).
+The interchange helpers load a preset written by any app in another app's context, with
+the §6 warning and fallback renderer, and render it through the core pipeline.
+"""
+
+from __future__ import annotations
+
+import io
+from dataclasses import dataclass, field
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+from PIL import ImageDraw
+
+from lattice_core import color
+from lattice_core.pipeline import PaletteSpec, PipelineSpec, render
+from lattice_core.preset import Preset, load_preset, to_pipeline_spec
+from lattice_core.registry import list_algorithms
+from lattice_core.renderers import list_renderers
+from lattice_core.types import RGB8, Image
+
+REFERENCE_SIDE = 200
+CELL_SIZE = 128
+LABEL_HEIGHT = 18
+COLUMNS = 6
+SHEET_BACKGROUND = (24, 24, 28)
+LABEL_COLOR = (235, 235, 240)
+PLACEHOLDER_COLOR = (42, 42, 48)
+MAX_GALLERY_BYTES = 4 * 1024 * 1024
+MIN_SHEET_SIDE = 64
+ALGORITHM_PIXEL_SIZE = 2
+RENDERER_PIXEL_SIZE = 8
+DEFAULT_PALETTE = "pico8"
+STARTER_DIR_NAME = "starter"
+_DISCS = (
+    (0.28, 0.30, 0.16, (1.0, 0.95, 0.2)),
+    (0.72, 0.34, 0.13, (0.1, 0.9, 1.0)),
+    (0.50, 0.74, 0.19, (1.0, 0.25, 0.55)),
+)
+
+
+def reference_image(size: int = REFERENCE_SIDE) -> Image:
+    """Build the deterministic reference image: gradients, three discs, a checker band."""
+    if size < 8:
+        raise ValueError(f"reference image side must be >= 8, got {size}")
+    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
+    u, v = xs / (size - 1), ys / (size - 1)
+    img = np.empty((size, size, 3), dtype=np.float32)
+    img[:, :, 0] = 0.15 + 0.8 * u
+    img[:, :, 1] = 0.15 + 0.8 * v
+    img[:, :, 2] = 0.15 + 0.7 * (1.0 - u) * (1.0 - v)
+    for cx, cy, radius, colour in _DISCS:
+        disc = (u - cx) * (u - cx) + (v - cy) * (v - cy) < radius * radius
+        for channel in range(3):
+            img[:, :, channel] = np.where(disc, colour[channel], img[:, :, channel])
+    checker = ((xs // 12 + ys // 12) % 2).astype(np.float32)
+    band = (v > 0.86) & (v < 0.96)
+    for channel in range(3):
+        img[:, :, channel] = np.where(band, checker * 0.9 + 0.05, img[:, :, channel])
+    return np.ascontiguousarray(np.clip(img, 0.0, 1.0), dtype=np.float32)
+
+
+def square_proxy(source: Image, side: int) -> Image:
+    """Return source box-resized to a side×side float32 proxy, whatever its shape."""
+    if side < 1:
+        raise ValueError(f"proxy side must be >= 1, got {side}")
+    pil = color.to_pil(color.to_rgb8(np.asarray(source, dtype=np.float32)))
+    return color.to_float(pil.resize((side, side), PILImage.Resampling.BOX))
+
+
+def _default_algorithm() -> str | None:
+    """Return floyd_steinberg when registered, else the first algorithm, else None."""
+    ids = [info.id for info in list_algorithms()]
+    if "floyd_steinberg" in ids:
+        return "floyd_steinberg"
+    return ids[0] if ids else None
+
+
+@dataclass(frozen=True)
+class GalleryEntry:
+    """One gallery cell: an algorithm or a renderer, with the spec that draws it."""
+
+    id: str
+    label: str
+    kind: str
+    spec: PipelineSpec
+
+
+def gallery_entries(*, palette: str = DEFAULT_PALETTE) -> list[GalleryEntry]:
+    """Return one entry per registered algorithm, then one per registered renderer."""
+    entries: list[GalleryEntry] = []
+    for info in list_algorithms():
+        spec = PipelineSpec(algorithm_id=info.id, pixel_size=ALGORITHM_PIXEL_SIZE,
+                            palette=PaletteSpec(source="builtin", name=palette))
+        entries.append(GalleryEntry(f"algorithm:{info.id}", info.name, "algorithm", spec))
+    algorithm = _default_algorithm()
+    for name in list_renderers():
+        spec = PipelineSpec(algorithm_id=algorithm, pixel_size=RENDERER_PIXEL_SIZE,
+                            palette=PaletteSpec(source="builtin", name=palette), renderer=name)
+        if algorithm is None:
+            spec.palette = None
+        entries.append(GalleryEntry(f"renderer:{name}", name, "renderer", spec))
+    return entries
+
+
+@dataclass(frozen=True)
+class GalleryCell:
+    """One rendered gallery cell: its entry identity and its square thumbnail."""
+
+    entry_id: str
+    label: str
+    kind: str
+    rgb8: RGB8
+
+
+@dataclass(frozen=True)
+class GallerySheet:
+    """The whole gallery: every cell, the composed contact sheet and the warnings."""
+
+    cells: list[GalleryCell]
+    image: RGB8
+    warnings: list[str] = field(default_factory=list)
+
+
+def _resize(rgb8: RGB8, size: int) -> RGB8:
+    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
+    if rgb8.shape[:2] == (size, size):
+        return np.ascontiguousarray(rgb8, dtype=np.uint8)
+    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
+    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
+
+
+def _render_cell(entry: GalleryEntry, proxy: Image, size: int) -> tuple[RGB8, str]:
+    """Render one entry on the proxy; a failure yields a placeholder and its message."""
+    try:
+        return _resize(render(proxy, entry.spec), size), ""
+    except Exception as exc:  # noqa: BLE001 - one broken entry must not stop the gallery
+        placeholder = np.empty((size, size, 3), dtype=np.uint8)
+        placeholder[:, :] = PLACEHOLDER_COLOR
+        return placeholder, f"{entry.id}: {exc}"
+
+
+def _compose_sheet(cells: list[GalleryCell], size: int, columns: int) -> RGB8:
+    """Paste the cells into one labelled contact sheet, columns per row."""
+    rows = max(1, (len(cells) + columns - 1) // columns)
+    sheet = PILImage.new("RGB", (columns * size, rows * (size + LABEL_HEIGHT)),
+                         SHEET_BACKGROUND)
+    draw = ImageDraw.Draw(sheet)
+    for index, cell in enumerate(cells):
+        x = (index % columns) * size
+        y = (index // columns) * (size + LABEL_HEIGHT)
+        draw.text((x + 4, y + 4), cell.label, fill=LABEL_COLOR)
+        sheet.paste(color.to_pil(cell.rgb8), (x, y + LABEL_HEIGHT))
+    return np.ascontiguousarray(np.asarray(sheet, dtype=np.uint8))
+
+
+def render_gallery(source: Image | None = None, *, cell_size: int = CELL_SIZE,
+                   columns: int = COLUMNS, palette: str = DEFAULT_PALETTE) -> GallerySheet:
+    """Render every registered algorithm and renderer on one image, side by side."""
+    if cell_size < 8:
+        raise ValueError(f"cell_size must be >= 8, got {cell_size}")
+    proxy = square_proxy(reference_image() if source is None else source, cell_size)
+    cells: list[GalleryCell] = []
+    warnings: list[str] = []
+    for entry in gallery_entries(palette=palette):
+        rgb8, problem = _render_cell(entry, proxy, cell_size)
+        if problem:
+            warnings.append(problem)
+        cells.append(GalleryCell(entry.id, entry.label, entry.kind, rgb8))
+    image = _compose_sheet(cells, cell_size, max(1, int(columns)))
+    return GallerySheet(cells, image, warnings)
+
+
+def gallery_png_bytes(sheet: GallerySheet) -> bytes:
+    """Encode the sheet as one PNG, downscaling until it fits the 4 MB budget."""
+    image = color.to_pil(sheet.image)
+    while True:
+        buffer = io.BytesIO()
+        image.save(buffer, format="PNG")
+        payload = buffer.getvalue()
+        if len(payload) <= MAX_GALLERY_BYTES or min(image.size) <= MIN_SHEET_SIDE:
+            return payload
+        image = image.resize((max(MIN_SHEET_SIDE, image.width * 3 // 4),
+                              max(MIN_SHEET_SIDE, image.height * 3 // 4)),
+                             PILImage.Resampling.BOX)
+
+
+def save_gallery(path: str | Path, source: Image | None = None, *,
+                 cell_size: int = CELL_SIZE, columns: int = COLUMNS,
+                 palette: str = DEFAULT_PALETTE) -> Path:
+    """Render the gallery and write it as a single PNG under 4 MB, returning its path."""
+    sheet = render_gallery(source, cell_size=cell_size, columns=columns, palette=palette)
+    target = Path(path)
+    target.parent.mkdir(parents=True, exist_ok=True)
+    target.write_bytes(gallery_png_bytes(sheet))
+    return target
+
+
+@dataclass(frozen=True)
+class InterchangeResult:
+    """One cross-app load and render: the preset, its renderer, the image, the warnings."""
+
+    preset: Preset
+    renderer: str
+    rgb8: RGB8
+    warnings: list[str]
+
+
+def load_for_app(path: str | Path, app: str, *,
+                 available: frozenset[str] | set[str] | None = None) -> Preset:
+    """Load a preset in app's context; an app mismatch is a warning, never an error (§6)."""
+    preset = load_preset(path, app=app, available=available)
+    if preset.app != app:
+        preset.warnings.append(f"preset written for app {preset.app!r}; loaded in app {app!r}")
+    return preset
+
+
+def render_for_app(source: Image, preset: Preset | str | Path, app: str, *,
+                   available: frozenset[str] | set[str] | None = None,
+                   max_side: int | None = None) -> InterchangeResult:
+    """Load preset for app when needed, then render it through the core pipeline."""
+    if not isinstance(preset, Preset):
+        preset = load_for_app(preset, app, available=available)
+    spec = to_pipeline_spec(preset)
+    rgb8 = render(source, spec, max_side=max_side)
+    return InterchangeResult(preset, spec.renderer, rgb8, list(preset.warnings))
+
+
+def starter_preset_dir() -> Path:
+    """Return the suite starter preset directory: presets/starter next to the package."""
+    return Path(__file__).resolve().parents[1] / "presets" / STARTER_DIR_NAME
+
+
+def starter_presets(directory: str | Path | None = None) -> list[Path]:
+    """Return the starter preset files of directory, sorted by name."""
+    base = Path(directory) if directory is not None else starter_preset_dir()
+    return sorted(path for path in base.glob("*.json") if path.is_file())
+
+
+__all__ = [
+    "CELL_SIZE",
+    "COLUMNS",
+    "DEFAULT_PALETTE",
+    "MAX_GALLERY_BYTES",
+    "REFERENCE_SIDE",
+    "GalleryCell",
+    "GalleryEntry",
+    "GallerySheet",
+    "InterchangeResult",
+    "gallery_entries",
+    "gallery_png_bytes",
+    "load_for_app",
+    "reference_image",
+    "render_for_app",
+    "render_gallery",
+    "save_gallery",
+    "square_proxy",
+    "starter_preset_dir",
+    "starter_presets",
+]
diff --git a/lattice_core/ui/gallery.py b/lattice_core/ui/gallery.py
new file mode 100644
index 0000000..d508f03
--- /dev/null
+++ b/lattice_core/ui/gallery.py
@@ -0,0 +1,300 @@
+"""Shared reference gallery widget: every registered algorithm and renderer, side by side.
+
+One cell per algorithm and per renderer of the core registries, rendered on the current
+source (the deterministic reference image when none is loaded) on a helper thread, plus
+a Save PNG button that writes the single contact sheet through ``lattice_core.gallery``.
+"""
+
+from __future__ import annotations
+
+import logging
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
+from PySide6.QtGui import QCloseEvent, QColor, QImage, QMouseEvent, QPixmap
+from PySide6.QtWidgets import (
+    QFileDialog,
+    QGridLayout,
+    QHBoxLayout,
+    QLabel,
+    QPushButton,
+    QVBoxLayout,
+    QWidget,
+)
+
+from lattice_core import color
+from lattice_core.gallery import (
+    DEFAULT_PALETTE,
+    GalleryEntry,
+    gallery_entries,
+    reference_image,
+    save_gallery,
+    square_proxy,
+)
+from lattice_core.pipeline import PipelineSpec, render
+from lattice_core.types import RGB8, Image
+
+LOGGER = logging.getLogger(__name__)
+
+THUMB_SIZE = 96
+THUMB_COLUMNS = 6
+PLACEHOLDER_COLOR = "#2a2a30"
+JOIN_MS = 2000
+FAILED_TIP = "{name}: {message}"
+SAVE_FILTER = "PNG image (*.png)"
+SAVE_DEFAULT_NAME = "gallery.png"
+
+
+def render_entry_thumbnail(spec: PipelineSpec, source: Image, size: int = THUMB_SIZE) -> RGB8:
+    """Render one gallery entry on a square proxy of the source and return size×size."""
+    proxy = square_proxy(source, size * 2)
+    return _resize(render(proxy, spec), size)
+
+
+def _resize(rgb8: RGB8, size: int) -> RGB8:
+    """Return rgb8 resized to size×size with a box filter, as uint8 RGB."""
+    if rgb8.shape[:2] == (size, size):
+        return np.ascontiguousarray(rgb8, dtype=np.uint8)
+    image = color.to_pil(rgb8).resize((size, size), PILImage.Resampling.BOX)
+    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
+
+
+def _pixmap(rgb8: RGB8) -> QPixmap:
+    """Return a QPixmap copy of a uint8 RGB array."""
+    data = np.ascontiguousarray(rgb8, dtype=np.uint8)
+    # QImage wraps the buffer instead of copying it, so the bytes must outlive the image.
+    buffer = data.tobytes()
+    image = QImage(buffer, data.shape[1], data.shape[0], QImage.Format.Format_RGB888)
+    return QPixmap.fromImage(image)
+
+
+class GalleryWorker(QObject):
+    """Renders gallery thumbnails on a helper thread and reports them by signal."""
+
+    thumbnail_ready = Signal(str, object)
+    failed = Signal(str, str)
+
+    def __init__(self, size: int = THUMB_SIZE) -> None:
+        super().__init__()
+        self._size = int(size)
+
+    @Slot(str, object, object)
+    def build(self, entry_id: str, spec: PipelineSpec, source: Image) -> None:
+        """Render one thumbnail and emit it; this slot never touches a widget."""
+        try:
+            rgb8 = render_entry_thumbnail(spec, source, self._size)
+        except Exception as exc:  # noqa: BLE001 - one broken entry must not stop the rest
+            LOGGER.exception("gallery entry %s failed", entry_id)
+            self.failed.emit(entry_id, str(exc))
+            return
+        self.thumbnail_ready.emit(entry_id, rgb8)
+
+
+_ACTIVE_WORKERS: set[GalleryWorker] = set()
+# A QThread that outlived its join timeout must not be destroyed while it still runs.
+_ORPHAN_THREADS: set[QThread] = set()
+
+
+def _release_worker(gallery: ReferenceGallery, worker: GalleryWorker) -> None:
+    """Drop every reference the gallery and this module keep to a stopped worker."""
+    worker.thumbnail_ready.disconnect(gallery._on_thumbnail_ready)
+    worker.failed.disconnect(gallery._on_thumbnail_failed)
+    gallery._request.disconnect(worker.build)
+    _ACTIVE_WORKERS.discard(worker)
+
+
+class GalleryCell(QWidget):
+    """One gallery cell: a thumbnail above the entry label."""
+
+    clicked = Signal(str)
+
+    def __init__(self, entry: GalleryEntry, size: int = THUMB_SIZE,
+                 parent: QWidget | None = None) -> None:
+        super().__init__(parent)
+        self.entry_id = entry.id
+        self.setObjectName(f"gallery_cell_{entry.id.replace(':', '_')}")
+        self.setToolTip(entry.label)
+        self.image_label = QLabel(self)
+        self.image_label.setObjectName("gallery_thumb")
+        self.image_label.setFixedSize(size, size)
+        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.name_label = QLabel(entry.label, self)
+        self.name_label.setObjectName("gallery_name")
+        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
+        self.name_label.setWordWrap(True)
+        layout = QVBoxLayout(self)
+        layout.setContentsMargins(4, 4, 4, 4)
+        layout.setSpacing(2)
+        layout.addWidget(self.image_label)
+        layout.addWidget(self.name_label)
+        self._placeholder = QPixmap(size, size)
+        self._placeholder.fill(QColor(PLACEHOLDER_COLOR))
+        self._ready = False
+        self.show_placeholder()
+
+    def has_thumbnail(self) -> bool:
+        """Return True once a rendered thumbnail has replaced the placeholder."""
+        return self._ready
+
+    def show_placeholder(self) -> None:
+        """Show the neutral placeholder instead of a thumbnail."""
+        self.image_label.setPixmap(self._placeholder)
+        self._ready = False
+
+    def set_thumbnail(self, rgb8: RGB8) -> None:
+        """Show rgb8 as this cell's thumbnail; call it from the GUI thread only."""
+        self.image_label.setPixmap(_pixmap(rgb8))
+        self._ready = True
+
+    def mousePressEvent(self, event: QMouseEvent) -> None:
+        """Report the entry of the cell when it is clicked."""
+        self.clicked.emit(self.entry_id)
+        super().mousePressEvent(event)
+
+
+class ReferenceGallery(QWidget):
+    """Grid of every registered algorithm and renderer on one reference image."""
+
+    cell_chosen = Signal(str)
+    _request = Signal(str, object, object)
+
+    def __init__(self, parent: QWidget | None = None, *, size: int = THUMB_SIZE,
+                 columns: int = THUMB_COLUMNS, palette: str = DEFAULT_PALETTE) -> None:
+        super().__init__(parent)
+        self.setObjectName("reference_gallery")
+        self._size = int(size)
+        self._columns = max(1, int(columns))
+        self._entries: dict[str, GalleryEntry] = {}
+        self._cells: list[GalleryCell] = []
+        self._cache: dict[str, RGB8] = {}
+        self._source: Image = reference_image()
+        self._thread: QThread | None = None
+        self._worker: GalleryWorker | None = None
+        self.save_button = QPushButton("Save PNG…", self)
+        self.save_button.setObjectName("gallery_save")
+        self.save_button.clicked.connect(self._ask_save)
+        toolbar = QHBoxLayout()
+        toolbar.addWidget(QLabel("Reference gallery", self))
+        toolbar.addStretch(1)
+        toolbar.addWidget(self.save_button)
+        self.grid = QGridLayout()
+        self.grid.setContentsMargins(0, 0, 0, 0)
+        self.grid.setSpacing(6)
+        outer = QVBoxLayout(self)
+        outer.setContentsMargins(6, 6, 6, 6)
+        outer.addLayout(toolbar)
+        outer.addLayout(self.grid)
+        outer.addStretch(1)
+        self._build_cells(gallery_entries(palette=palette))
+        self._queue_thumbnails()
+
+    def cells(self) -> list[GalleryCell]:
+        """Return every cell of the gallery, in display order."""
+        return list(self._cells)
+
+    def entries(self) -> list[GalleryEntry]:
+        """Return the gallery entries, in display order."""
+        return [self._entries[cell.entry_id] for cell in self._cells]
+
+    def set_source(self, image: Image | None) -> None:
+        """Set the current image; None restores the reference image and re-renders all."""
+        self._source = (reference_image() if image is None
+                        else np.ascontiguousarray(image, dtype=np.float32))
+        self._cache.clear()
+        for cell in self._cells:
+            cell.show_placeholder()
+        self._queue_thumbnails()
+
+    def save_png(self, path: str | Path) -> Path:
+        """Write the whole gallery as one contact-sheet PNG under 4 MB."""
+        return save_gallery(path, self._source)
+
+    def shutdown(self) -> None:
+        """Stop the helper thread and release its worker; safe to call more than once."""
+        thread, worker = self._thread, self._worker
+        self._thread = self._worker = None
+        if thread is None:
+            return
+        if worker is not None:
+            _release_worker(self, worker)
+        thread.quit()
+        if not thread.wait(JOIN_MS):
+            LOGGER.warning("the gallery thread did not stop within %d ms", JOIN_MS)
+            _ORPHAN_THREADS.add(thread)
+
+    def closeEvent(self, event: QCloseEvent) -> None:
+        """Stop the helper thread before the widget goes away."""
+        self.shutdown()
+        super().closeEvent(event)
+
+    def _build_cells(self, entries: list[GalleryEntry]) -> None:
+        """Create one cell per entry and place them in the grid, columns per row."""
+        for index, entry in enumerate(entries):
+            self._entries[entry.id] = entry
+            cell = GalleryCell(entry, self._size, self)
+            cell.clicked.connect(self.cell_chosen)
+            self._cells.append(cell)
+            self.grid.addWidget(cell, index // self._columns, index % self._columns)
+
+    def _ask_save(self) -> None:
+        """Ask for a PNG path and write the contact sheet there."""
+        path, _filter = QFileDialog.getSaveFileName(self, "Save gallery", SAVE_DEFAULT_NAME,
+                                                    SAVE_FILTER)
+        if path:
+            self.save_png(path)
+
+    def _ensure_worker(self) -> GalleryWorker:
+        """Create the helper thread and its worker on first use."""
+        if self._worker is not None:
+            return self._worker
+        thread = QThread()
+        worker = GalleryWorker(self._size)
+        worker.moveToThread(thread)
+        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
+        worker.failed.connect(self._on_thumbnail_failed)
+        self._request.connect(worker.build)
+        _ACTIVE_WORKERS.add(worker)
+        thread.finished.connect(worker.deleteLater)
+        thread.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker))
+        thread.start()
+        self._thread, self._worker = thread, worker
+        return worker
+
+    def _queue_thumbnails(self) -> None:
+        """Ask the worker for every cell's thumbnail, cache hits included."""
+        if not self._cells:
+            return
+        self._ensure_worker()
+        for cell in self._cells:
+            if cell.entry_id in self._cache:
+                cell.set_thumbnail(self._cache[cell.entry_id])
+                continue
+            self._request.emit(cell.entry_id, self._entries[cell.entry_id].spec, self._source)
+
+    @Slot(str, object)
+    def _on_thumbnail_ready(self, entry_id: str, rgb8: object) -> None:
+        """Show a finished thumbnail; this slot runs on the GUI thread."""
+        cell = next((cell for cell in self._cells if cell.entry_id == entry_id), None)
+        if cell is None:
+            return
+        image = np.ascontiguousarray(np.asarray(rgb8, dtype=np.uint8))
+        self._cache[entry_id] = image
+        cell.set_thumbnail(image)
+
+    @Slot(str, str)
+    def _on_thumbnail_failed(self, entry_id: str, message: str) -> None:
+        """Keep the placeholder of a cell whose thumbnail could not be rendered."""
+        cell = next((cell for cell in self._cells if cell.entry_id == entry_id), None)
+        if cell is not None:
+            cell.setToolTip(FAILED_TIP.format(name=entry_id, message=message))
+
+
+__all__ = [
+    "THUMB_SIZE",
+    "GalleryCell",
+    "GalleryWorker",
+    "ReferenceGallery",
+    "render_entry_thumbnail",
+]
diff --git a/tests/test_gallery.py b/tests/test_gallery.py
new file mode 100644
index 0000000..33be3be
--- /dev/null
+++ b/tests/test_gallery.py
@@ -0,0 +1,386 @@
+"""Card L21: the reference gallery, preset interchange and the v3 starter set."""
+
+from __future__ import annotations
+
+import os
+
+os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
+
+import ast  # noqa: E402
+import json  # noqa: E402
+import time  # noqa: E402
+from collections import Counter  # noqa: E402
+from collections.abc import Callable, Iterator  # noqa: E402
+from contextlib import contextmanager  # noqa: E402
+from pathlib import Path  # noqa: E402
+
+import numpy as np  # noqa: E402
+import pytest  # noqa: E402
+from PIL import Image as PILImage  # noqa: E402
+from PySide6.QtCore import Qt, QThread  # noqa: E402
+from PySide6.QtTest import QTest  # noqa: E402
+from PySide6.QtWidgets import QApplication, QFileDialog, QWidget  # noqa: E402
+
+import lattice_core.dither  # noqa: E402,F401  (registers every algorithm)
+import lattice_core.effects  # noqa: E402,F401  (registers every effect)
+import lattice_glitch.presets as glitch_presets  # noqa: E402
+import lattice_glyph.document as glyph_doc  # noqa: E402
+import lattice_glyph.presets as glyph_presets  # noqa: E402
+from lattice_core import gallery as core_gallery  # noqa: E402
+from lattice_core.gallery import (  # noqa: E402
+    MAX_GALLERY_BYTES,
+    PLACEHOLDER_COLOR,
+    GalleryEntry,
+    GallerySheet,
+    gallery_entries,
+    gallery_png_bytes,
+    load_for_app,
+    reference_image,
+    render_for_app,
+    render_gallery,
+    save_gallery,
+    starter_preset_dir,
+    starter_presets,
+)
+from lattice_core.pipeline import PaletteSpec, PipelineSpec, render  # noqa: E402
+from lattice_core.preset import from_json, to_json, to_pipeline_spec  # noqa: E402
+from lattice_core.presets import save_preset as save_v2_preset  # noqa: E402
+from lattice_core.registry import get_algorithm, get_effect, list_algorithms  # noqa: E402
+from lattice_core.renderers import list_renderers  # noqa: E402
+from lattice_core.types import RGB8  # noqa: E402
+from lattice_core.ui import gallery as ui_gallery  # noqa: E402
+from lattice_core.ui.gallery import THUMB_SIZE, GalleryWorker, ReferenceGallery  # noqa: E402
+
+ROOT = Path(__file__).resolve().parents[1]
+PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
+APPS = ("dither", "glyph", "glitch")
+# Renderers each app exposes: dither/glitch draw pixels, glyph offers the whole registry.
+APP_AVAILABLE: dict[str, set[str] | None] = {"dither": {"pixel"}, "glitch": {"pixel"},
+                                             "glyph": None}
+
+
+@pytest.fixture(scope="module")
+def qapp() -> QApplication:
+    """Return the shared offscreen QApplication."""
+    app = QApplication.instance()
+    return app if isinstance(app, QApplication) else QApplication([])
+
+
+@pytest.fixture(scope="module")
+def ref() -> np.ndarray:
+    """The deterministic reference image every accept item renders on."""
+    return reference_image()
+
+
+def _wait_until(predicate: Callable[[], bool], timeout: float = 120.0) -> bool:
+    """Process GUI events until predicate holds or the timeout expires."""
+    deadline = time.monotonic() + timeout
+    while time.monotonic() < deadline:
+        if predicate():
+            return True
+        QApplication.processEvents()
+        time.sleep(0.005)
+    return predicate()
+
+
+def _all_ready(widget: ReferenceGallery) -> bool:
+    """Return True when every cell of the gallery shows a thumbnail."""
+    return all(cell.has_thumbnail() for cell in widget.cells())
+
+
+def _assert_rgb8(rgb8: RGB8, shape: tuple[int, ...]) -> None:
+    """Assert one render result is a uint8 RGB image of the expected shape."""
+    assert rgb8.dtype == np.uint8
+    assert rgb8.shape == shape
+    assert len(np.unique(rgb8.reshape(-1, 3), axis=0)) > 1
+
+
+def _core_errors(path: Path) -> list[str]:
+    """Validate a dither-tagged v3 preset against the core registries, glyph-style."""
+    spec = to_pipeline_spec(from_json(path.read_text(encoding="utf-8"), app="dither"))
+    errors: list[str] = []
+    if spec.renderer not in list_renderers():
+        errors.append(f"renderer {spec.renderer!r} is not registered")
+    if (spec.algorithm_id is None) != (spec.palette is None):
+        errors.append("continuous mode needs algorithm and palette both null")
+    checks = [(get_algorithm, spec.algorithm_id, "algorithm")]
+    checks += [(get_effect, i.effect_id, "effect") for i in spec.pre_effects + spec.post_effects]
+    for lookup, ident, kind in checks:
+        if ident is None:
+            continue
+        try:
+            lookup(ident)
+        except KeyError:
+            errors.append(f"{kind} {ident!r} is not registered")
+    return errors
+
+
+@contextmanager
+def _open_gallery() -> Iterator[ReferenceGallery]:
+    """Yield a reference gallery, stopped and closed afterwards."""
+    widget = ReferenceGallery()
+    try:
+        yield widget
+    finally:
+        widget.shutdown()
+        widget.close()
+
+
+def test_the_reference_image_is_deterministic_and_valid(ref: np.ndarray) -> None:
+    assert ref.shape == (200, 200, 3) and ref.dtype == np.float32
+    assert 0.0 <= float(ref.min()) and float(ref.max()) <= 1.0
+    assert np.array_equal(ref, reference_image())
+    assert np.array_equal(reference_image(64), reference_image(64))
+
+
+def test_the_entries_cover_every_registered_algorithm_and_renderer() -> None:
+    entries = gallery_entries()
+    algorithms = [entry for entry in entries if entry.kind == "algorithm"]
+    renderers = [entry for entry in entries if entry.kind == "renderer"]
+    assert [e.id for e in algorithms] == [f"algorithm:{i.id}" for i in list_algorithms()]
+    assert [e.id for e in renderers] == [f"renderer:{n}" for n in list_renderers()]
+    assert len(entries) == len(list_algorithms()) + len(list_renderers())
+    assert all(entry.spec.renderer == "pixel" for entry in algorithms)
+    assert {entry.spec.renderer for entry in renderers} == set(list_renderers())
+
+
+def test_the_gallery_renders_every_cell_without_raising(ref: np.ndarray) -> None:
+    sheet = render_gallery(ref)
+    assert sheet.warnings == []
+    assert len(sheet.cells) == len(gallery_entries())
+    for cell in sheet.cells:
+        _assert_rgb8(cell.rgb8, (128, 128, 3))
+    assert sheet.image.dtype == np.uint8 and sheet.image.ndim == 3
+    assert np.array_equal(sheet.image, render_gallery(ref).image)
+
+
+def test_a_broken_entry_yields_a_warning_and_a_placeholder(monkeypatch: pytest.MonkeyPatch,
+                                                          ref: np.ndarray) -> None:
+    healthy = GalleryEntry("algorithm:threshold", "Threshold", "algorithm",
+                           PipelineSpec(algorithm_id="threshold", pixel_size=2,
+                                        palette=PaletteSpec(source="builtin", name="bw")))
+    broken = GalleryEntry("algorithm:nope", "Nope", "algorithm",
+                          PipelineSpec(algorithm_id="does_not_exist"))
+    monkeypatch.setattr(core_gallery, "gallery_entries", lambda **_kw: [healthy, broken])
+    sheet = render_gallery(ref)
+    assert len(sheet.cells) == 2
+    assert len(sheet.warnings) == 1 and "does_not_exist" in sheet.warnings[0]
+    assert np.all(sheet.cells[1].rgb8 == np.array(PLACEHOLDER_COLOR, dtype=np.uint8))
+    _assert_rgb8(sheet.cells[0].rgb8, (128, 128, 3))
+
+
+def test_save_gallery_writes_one_png_under_4mb(tmp_path: Path, ref: np.ndarray) -> None:
+    target = save_gallery(tmp_path / "gallery.png", ref)
+    assert list(tmp_path.iterdir()) == [target]
+    payload = target.read_bytes()
+    assert payload[:8] == PNG_MAGIC
+    assert len(payload) < MAX_GALLERY_BYTES
+    with PILImage.open(target) as image:
+        assert image.format == "PNG"
+        sheet = render_gallery(ref)
+        assert image.size == (sheet.image.shape[1], sheet.image.shape[0])
+
+
+def test_the_png_budget_downcales_an_oversized_sheet() -> None:
+    rng = np.random.default_rng(0)
+    noise = rng.integers(0, 256, (2048, 2048, 3), dtype=np.uint8)
+    payload = gallery_png_bytes(GallerySheet([], noise))
+    assert payload[:8] == PNG_MAGIC
+    assert len(payload) <= MAX_GALLERY_BYTES
+
+
+def test_a_glyph_preset_loads_in_glitch_with_a_warning_and_renders(
+        tmp_path: Path, ref: np.ndarray) -> None:
+    spec = glyph_presets.default_spec()
+    path = glyph_presets.save_preset(tmp_path / "glyph.json",
+                                     glyph_presets.to_preset(spec, name="cross"))
+    read = glitch_presets.read_preset(path)  # a mismatch is not an error for the app
+    assert read.app == "glyph"
+    loaded = load_for_app(path, "glitch", available=APP_AVAILABLE["glitch"])
+    assert any("glyph_ramp" in warning for warning in loaded.warnings)
+    assert loaded.renderer["name"] == "pixel"
+    result = render_for_app(ref, loaded, "glitch")
+    _assert_rgb8(result.rgb8, ref.shape)
+    assert result.renderer == "pixel"
+    assert result.warnings and any("glyph_ramp" in warning for warning in result.warnings)
+    assert np.array_equal(result.rgb8, render(ref, to_pipeline_spec(loaded)))
+
+
+def test_dither_presets_load_in_glyph_and_render_with_pixel(tmp_path: Path,
+                                                            ref: np.ndarray) -> None:
+    v1 = load_for_app(ROOT / "presets" / "01_gameboy.json", "glyph")
+    assert v1.renderer["name"] == "pixel"
+    spec = to_pipeline_spec(v1)
+    assert spec.renderer == "pixel"
+    _assert_rgb8(glyph_doc.render_rgb8(ref, spec), ref.shape)
+    _assert_rgb8(render_for_app(ref, v1, "glyph").rgb8, ref.shape)
+    path = tmp_path / "dither_v2.json"
+    save_v2_preset(path, PipelineSpec(pixel_size=2,
+                                      palette=PaletteSpec(source="builtin", name="gameboy")))
+    v2 = load_for_app(path, "glyph")
+    assert v2.renderer["name"] == "pixel"
+    result = render_for_app(ref, v2, "glyph")
+    assert result.renderer == "pixel"
+    _assert_rgb8(result.rgb8, ref.shape)
+
+
+def test_a_glitch_preset_loads_in_glyph_and_renders(ref: np.ndarray) -> None:
+    path = starter_preset_dir() / "glitch_01_vhs_soft.json"
+    loaded = load_for_app(path, "glyph", available=APP_AVAILABLE["glyph"])
+    assert loaded.renderer["name"] == "pixel"
+    _assert_rgb8(render_for_app(ref, loaded, "glyph").rgb8, ref.shape)
+
+
+def test_an_unknown_renderer_falls_back_with_a_warning(tmp_path: Path,
+                                                       ref: np.ndarray) -> None:
+    path = tmp_path / "future.json"
+    path.write_text(json.dumps({"version": 3, "app": "glyph",
+                                "renderer": {"name": "future_renderer"}}), encoding="utf-8")
+    loaded = load_for_app(path, "dither", available={"pixel"})
+    assert loaded.renderer["name"] == "pixel"
+    assert any("future_renderer" in warning for warning in loaded.warnings)
+    _assert_rgb8(render_for_app(ref, loaded, "dither").rgb8, ref.shape)
+
+
+def test_the_starter_set_spans_the_three_apps_with_at_least_12_presets() -> None:
+    paths = starter_presets()
+    assert len(paths) >= 12
+    assert all(path.parent == starter_preset_dir() for path in paths)
+    presets = [from_json(path.read_text(encoding="utf-8")) for path in paths]
+    apps = Counter(preset.app for preset in presets)
+    assert set(apps) == set(APPS)
+    assert all(count >= 3 for count in apps.values())
+    assert all(preset.version == 3 for preset in presets)
+
+
+def test_every_starter_preset_validates_in_its_own_app(ref: np.ndarray) -> None:
+    for path in starter_presets():
+        app = from_json(path.read_text(encoding="utf-8")).app
+        if app == "glyph":
+            report = glyph_presets.validate(path)
+            assert report.ok and report.errors == [], (path.name, report.errors)
+        elif app == "glitch":
+            report = glitch_presets.validate(path)
+            assert report.ok and report.errors == [], (path.name, report.errors)
+        else:
+            assert _core_errors(path) == [], path.name
+        _assert_rgb8(render_for_app(ref, path, app).rgb8, ref.shape)
+
+
+def test_every_starter_preset_circulates_to_the_other_apps(ref: np.ndarray) -> None:
+    for path in starter_presets():
+        own = from_json(path.read_text(encoding="utf-8")).app
+        for target in APPS:
+            if target == own:
+                continue
+            loaded = load_for_app(path, target, available=APP_AVAILABLE[target])
+            assert loaded.warnings, (path.name, target)
+            result = render_for_app(ref, loaded, target)
+            _assert_rgb8(result.rgb8, ref.shape)
+            assert result.renderer in list_renderers()
+
+
+def test_a_starter_preset_round_trips_with_unknown_keys_preserved() -> None:
+    data = json.loads(starter_presets()[0].read_text(encoding="utf-8"))
+    data["x_future"] = {"flag": True}
+    data["renderer"]["style"]["x_option"] = 1
+    preset = from_json(json.dumps(data))
+    again = from_json(to_json(preset))
+    assert again.extra == {"x_future": {"flag": True}}
+    assert again.renderer["style"]["x_option"] == 1
+    assert to_json(again) == to_json(preset)
+
+
+def test_the_widget_shows_one_cell_per_entry(qapp: QApplication) -> None:
+    with _open_gallery() as widget:
+        assert len(widget.cells()) == len(gallery_entries())
+        assert [c.entry_id for c in widget.cells()] == [e.id for e in gallery_entries()]
+        assert all(not cell.has_thumbnail() for cell in widget.cells())
+        assert _wait_until(lambda: _all_ready(widget)), "thumbnails never arrived"
+        assert [c.name_label.text() for c in widget.cells()] == [e.label for e in widget.entries()]
+
+
+def test_the_widget_renders_on_a_new_source(qapp: QApplication,
+                                            rng: np.random.Generator) -> None:
+    with _open_gallery() as widget:
+        assert _wait_until(lambda: _all_ready(widget))
+        widget.set_source(rng.random((96, 128, 3), dtype=np.float32))
+        assert all(not cell.has_thumbnail() for cell in widget.cells())
+        assert _wait_until(lambda: _all_ready(widget))
+        widget.set_source(None)
+        assert _wait_until(lambda: _all_ready(widget))
+
+
+def test_the_widget_save_button_writes_one_small_png(
+        qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
+    with _open_gallery() as widget:
+        assert _wait_until(lambda: _all_ready(widget))
+        target = tmp_path / "ui_gallery.png"
+        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
+        QTest.mouseClick(widget.save_button, Qt.MouseButton.LeftButton)
+        assert target.read_bytes()[:8] == PNG_MAGIC
+        assert target.stat().st_size < MAX_GALLERY_BYTES
+        assert list(tmp_path.iterdir()) == [target]
+        assert widget.save_png(tmp_path / "direct.png").read_bytes() == target.read_bytes()
+
+
+def test_the_worker_runs_off_the_gui_thread(qapp: QApplication,
+                                            monkeypatch: pytest.MonkeyPatch) -> None:
+    render_threads: list[QThread] = []
+    original = ui_gallery.render_entry_thumbnail
+
+    def spy(spec: PipelineSpec, source: np.ndarray, size: int = THUMB_SIZE) -> np.ndarray:
+        render_threads.append(QThread.currentThread())
+        return original(spec, source, size)
+
+    monkeypatch.setattr(ui_gallery, "render_entry_thumbnail", spy)
+    with _open_gallery() as widget:
+        assert _wait_until(lambda: _all_ready(widget))
+        worker = widget._worker
+        assert isinstance(worker, GalleryWorker)
+        assert not isinstance(worker, QWidget)
+        assert worker.thread() is not qapp.thread()
+        assert render_threads and all(thread is not qapp.thread() for thread in render_threads)
+
+
+def test_a_failing_thumbnail_keeps_the_placeholder(qapp: QApplication,
+                                                   monkeypatch: pytest.MonkeyPatch) -> None:
+    def boom(spec: PipelineSpec, source: np.ndarray, size: int = THUMB_SIZE) -> np.ndarray:
+        raise RuntimeError("no render")
+
+    monkeypatch.setattr(ui_gallery, "render_entry_thumbnail", boom)
+    with _open_gallery() as widget:
+        assert _wait_until(lambda: "no render" in widget.cells()[0].toolTip())
+        assert all(not cell.has_thumbnail() for cell in widget.cells())
+        assert len(widget.cells()) == len(gallery_entries())
+
+
+def test_clicking_a_cell_reports_its_entry_and_shutdown_is_idempotent(
+        qapp: QApplication) -> None:
+    with _open_gallery() as widget:
+        assert _wait_until(lambda: _all_ready(widget))
+        chosen: list[str] = []
+        widget.cell_chosen.connect(chosen.append)
+        QTest.mouseClick(widget.cells()[1], Qt.MouseButton.LeftButton)
+        assert chosen == [widget.cells()[1].entry_id]
+        widget.shutdown()
+        widget.shutdown()
+
+
+def _import_roots(path: Path) -> set[str]:
+    """Return the top-level package names a Python file imports."""
+    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
+    roots: set[str] = set()
+    for node in ast.walk(tree):
+        if isinstance(node, ast.Import):
+            roots.update(alias.name.split(".")[0] for alias in node.names)
+        elif isinstance(node, ast.ImportFrom) and node.module:
+            roots.add(node.module.split(".")[0])
+    return roots
+
+
+def test_the_gallery_modules_respect_the_core_packaging_rules() -> None:
+    apps = {"lattice_dither", "lattice_glyph", "lattice_glitch"}
+    base = _import_roots(ROOT / "lattice_core" / "gallery.py")
+    assert not base & (apps | {"PySide6"})
+    assert not _import_roots(ROOT / "lattice_core" / "ui" / "gallery.py") & apps


CODER NOTES AND DEVIATIONS (4 E1 — juge-les)
(vide)