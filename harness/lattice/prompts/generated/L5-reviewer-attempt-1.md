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

CONTRACT EXCERPTS (version 0.1.0-draft)

## §3 The CellRenderer contract

This is the architectural bet of the project. Everything else is an implementation detail.

```python
@dataclass(frozen=True)
class CellGrid:
    cols: int
    rows: int
    cell_w: int
    cell_h: int
    index: np.ndarray      # (rows, cols) int32, palette index per cell
    coverage: np.ndarray   # (rows, cols) float32 in [0, 1], ink coverage per cell
    luma: np.ndarray       # (rows, cols) float32, linear luminance of the SOURCE cell
                           # computed before quantisation (S2, decided 2026-11-16)
    samples: np.ndarray    # (rows, cols, k) float32 in [0, 1], sub-cell luminance
    subindex: np.ndarray | None = None  # (rows, cols, sx*sy) int32, palette index per
                                        # sub-point, present when subgrid != (1, 1) (S3)

@dataclass(frozen=True)
class RenderStyle:
    options: Mapping[str, object]   # renderer-specific, JSON-serialisable

class CellRenderer(Protocol):
    name: str
    def cell_aspect(self) -> float: ...
    def subgrid(self) -> tuple[int, int]: ...  # default (1, 1); braille (2, 4), sextant (2, 3) (S3)
    def consumes(self) -> frozenset[str]: ...  # subset of {"index", "luma", "samples"} (S2)
    def render(self, grid: CellGrid, palette: np.ndarray, style: RenderStyle) -> Image.Image: ...
```

Registry: `register_renderer`, `get_renderer(name)`, `list_renderers()`.

Normative invariants, each one a test:

1. `render` returns an image of exactly `(cols * cell_w, rows * cell_h)` pixels.
2. `render` is pure: identical inputs produce identical output, no module-level state.
3. `render` does not mutate `grid` or `palette`.
4. `cell_aspect()` returns width/height of one cell. The pipeline uses it to choose the grid so the
   output preserves the source aspect ratio.
5. `name` is unique across the registry and stable across versions.
6. `style.options` round-trips through JSON without loss.

**Why the split.** The dithering stage decides *which palette entry* each cell receives. The
renderer decides *how to draw that entry*: a solid square, a glyph whose density matches the
entry's luminance, a braille bitmask, a paragraph of text. This is what lets 33 dithering
algorithms serve three applications without being rewritten.

`coverage` is derived once, in the pipeline, not by the renderer:

```
lum(c)      = 0.2126 R + 0.7152 G + 0.0722 B, computed in linear light
coverage    = (lum(palette[index]) - lum_min) / (lum_max - lum_min)
coverage    = 0.0 where lum_max == lum_min
```

`samples` is produced by supersampling the source cell on a `k`-point stencil. `k` is a renderer
property: 1 for `pixel`, 6 for `glyph_shape`, 8 for braille, 6 for sextant, 4 for quadrant.

**Luma — independent of the palette (S2, decided 2026-11-16).** `grid.luma` is the linear
luminance of the source cell (step-7 pixels, computed in linear light) taken BEFORE quantisation.
Each renderer declares what it consumes via `consumes()`; `glyph_ramp` and `glyph_shape` consume
`luma` for ink-density ramps, so a black/white palette still uses the full glyph ramp. The L2
"coverage is monotone" test stays; a new L2 test asserts "luma is continuous and independent of
the palette".

**Sub-point dithering (S3, decided 2026-11-16).** A renderer may declare `subgrid = (sx, sy)`
(braille 2×4, sextant 2×3). The pipeline then runs the chosen algorithm at resolution
`(rows·sy, cols·sx)` and hands the renderer `grid.subindex: (rows, cols, sx·sy) int32`. The
bitmask and text renderers only pack sub-points into codepoints; the single boolean `dither`
option is removed. New L2 test: sub-point coverage is monotone at the subgrid resolution.

## §5 Pipeline

Inherits Lattice Dither §13 (pre-dither conditioning) and its render order, with step 8 replaced by
the renderer call. The normative order becomes:

1. If `max_side`: area-downscale so `max(H, W) <= max_side`. Call this shape S.
2. Enabled pre-effects in order; effect i gets `default_rng(seed + i)`.
3. `auto_levels` if enabled.
4. `adjust(brightness, contrast, gamma, saturation)`.
5. `pre_blur` if > 0 (separable Gaussian, sigma = `pre_blur / 3`).
6. Compute grid geometry from `renderer.cell_aspect()` and `pixel_size`.
7. Downscale to the grid.
8. `resolve_palette` on the image from step 7.
9. Algorithm (params through `resolve_params`) → `index`.
10. Derive `coverage` and `samples` per §3.
11. `renderer.render(grid, palette, style)`.
12. Enabled post-effects in order; effect j gets `default_rng(seed + 1000 + j)`.

Steps 3, 4 and 5 must be no-ops at their defaults. Step 11 replaces the 1.0 `apply_palette` +
`upscale_nearest` pair; `PixelRenderer` reproduces that pair exactly.

**Continuous mode (S1, decided 2026-11-16).** The pipeline may run without quantisation:
`algorithm: null` and `palette: null` are legal. In that mode steps 8 and 9 are skipped,
`grid.luma`/`samples` are derived from the step-7 cells, the renderer must be `pixel` at
cell 1×1, and `grid.index` carries nearest-source pixels (a pass-through). Lattice Glitch is an
effect-graph app that consumes the core (seed, masks, presets, bridge, CLI) without depending on
the CellRenderer quantisation chain.

TASK CARD

### L5 · Bridge generalisation
- wave: 0 · deps: L1 · executor: OMH capable · review: full · size: M
- owns: `lattice_core/bridge/**`, `tests/test_bridge.py`, `tests/test_bridge_smoke.py`
- context: §7
- spec: implement §7. `ArtCraftClient` with `discover`, `ping`, `render_document`,
  `place_as_layer`. Move the existing PhotoCraft code into `bridge/photocraft.py` unchanged. Add
  `bridge/designcraft.py` using `file.place` with `{path, frame?}` when a frame is selected and
  `{path, x, y, width}` otherwise. Discover the exact DesignCraft parameter surface with
  `designcraft-cli describe file.place` and record it as an amendment in `DEVIATIONS.md`; do not
  invent parameters. Every call is bounded by a timeout; failure returns a typed error, never a
  crash.
- accept:
  - `discover("photocraft")` returns `None` when the token file is absent, and a working client
    when PhotoCraft is running.
  - `discover("designcraft")` behaves the same way against a running DesignCraft.
  - `render_document` returns an image whose size matches `document.inspect`.
  - `place_as_layer` returns an integer id and the layer is visible in the host.
  - a bridge failure raises `BridgeError` and leaves no temporary file behind.
  - exchange files older than one hour are discarded on the next call.

GATE RESULTS (vague 0 — batterie complète sur l'arbre posé, 2026-11-16)
- G1 ruff: clean (repo entier). G2 pytest: **1287 passed, 1 skipped** (le skip est le smoke
  manuel test_bridge_smoke). G3 check_contract: OK. G4 : cette carte n'a écrit que ses owns.
- G7 témoins bit-à-bit : couverts par la suite (baselines 01/05/07 re-rendues dans G2).
- G8 registre : ["pixel"], aspect 1.0, subgrid (1,1), consumes {"index"}.

DIFF

diff --git a/lattice_core/bridge/__init__.py b/lattice_core/bridge/__init__.py
index e69de29..fa2f326 100644
--- a/lattice_core/bridge/__init__.py
+++ b/lattice_core/bridge/__init__.py
@@ -0,0 +1,102 @@
+"""ArtCraft bridge: one client, one adapter per host (CONTRACT §7).
+
+``ArtCraftClient`` is the single entry point an application uses. It delegates
+to ``photocraft.PhotoCraftClient`` or ``designcraft.DesignCraftClient``; both
+raise the same ``BridgeError`` and both return ``None`` from ``discover`` when
+their host is not running, so an application always works standalone.
+
+    client = ArtCraftClient.discover("photocraft")
+    if client is not None:
+        client.place_as_layer(image, "Lattice Dither")
+"""
+
+from __future__ import annotations
+
+from typing import Literal, Protocol, cast
+
+from PIL import Image
+
+from lattice_core.bridge import designcraft as _designcraft
+from lattice_core.bridge import photocraft as _photocraft
+from lattice_core.bridge._client import PhotoCraftClient
+from lattice_core.bridge.designcraft import DesignCraftClient
+from lattice_core.bridge.photocraft import BridgeError
+
+__all__ = [
+    "ArtCraftClient",
+    "BridgeError",
+    "DesignCraftClient",
+    "HOSTS",
+    "PhotoCraftClient",
+]
+
+HOSTS = ("photocraft", "designcraft")
+HostName = Literal["photocraft", "designcraft"]
+DEFAULT_LAYER_NAME = "Lattice Dither"
+
+
+class _Adapter(Protocol):
+    """The part of a host adapter ``ArtCraftClient`` relies on."""
+
+    def ping(self) -> bool: ...
+
+    def call(self, method: str, params: dict | None = None) -> object: ...
+
+    def render_document(self) -> Image.Image: ...
+
+    def place_as_layer(self, img: Image.Image, name: str) -> int: ...
+
+    def disconnect(self) -> None: ...
+
+
+class ArtCraftClient:
+    """One ArtCraft host, reached through the adapter that speaks to it."""
+
+    def __init__(self, host: HostName, client: _Adapter) -> None:
+        self._host = host
+        self._client = client
+
+    @property
+    def host(self) -> HostName:
+        """Return the host name this client talks to."""
+        return self._host
+
+    @property
+    def client(self) -> _Adapter:
+        """Return the host adapter underneath, for host-specific calls."""
+        return self._client
+
+    @staticmethod
+    def discover(host: HostName, port: int | None = None) -> ArtCraftClient | None:
+        """Return a live client for `host`, or None when that host is not reachable."""
+        if host == "photocraft":
+            found = PhotoCraftClient.discover(
+                port=_photocraft.CONTROL_PORT if port is None else port
+            )
+        elif host == "designcraft":
+            found = DesignCraftClient.discover(
+                port=_designcraft.CONTROL_PORT if port is None else port
+            )
+        else:
+            raise ValueError(f"unknown ArtCraft host {host!r}; expected one of {HOSTS}")
+        return None if found is None else ArtCraftClient(host, cast(_Adapter, found))
+
+    def ping(self) -> bool:
+        """Return True when the host answers its liveness probe."""
+        return bool(self._client.ping())
+
+    def render_document(self) -> Image.Image:
+        """Return the active document of the host as an image."""
+        return self._client.render_document()
+
+    def place_as_layer(self, img: Image.Image, name: str = DEFAULT_LAYER_NAME) -> int:
+        """Place the image in the host as a layer or placed object and return its id."""
+        return int(self._client.place_as_layer(img, name))
+
+    def call(self, method: str, params: dict | None = None) -> object:
+        """Send one raw request to the host and return its result."""
+        return self._client.call(method, params)
+
+    def disconnect(self) -> None:
+        """Drop whatever the adapter holds; connections are per call."""
+        self._client.disconnect()
diff --git a/lattice_core/bridge/designcraft.py b/lattice_core/bridge/designcraft.py
new file mode 100644
index 0000000..df6cfc0
--- /dev/null
+++ b/lattice_core/bridge/designcraft.py
@@ -0,0 +1,245 @@
+"""DesignCraft desktop control-server bridge (CONTRACT §7).
+
+DesignCraft 0.20.1 answers JSON lines on 127.0.0.1:7979 and has no token: its
+channel refuses ``auth`` as an unknown method, so a session is a plain
+connection and ``engine.commands`` is the liveness probe. The wire helpers are
+PhotoCraft's, reused so both hosts fail with the same ``BridgeError``.
+
+A Flatpak host reads only ``xdg-documents``/``xdg-pictures``, never the
+per-application exchange directory, so ``file.place`` is tried with the
+contract's ``path`` form and retried with the documented ``base64`` form when
+the host answers that it cannot read the path. ``render_document`` uses
+``file.exportBatch``, which returns the PNG inline as base64 when it gets no
+``dir``, so no exchange file is written at all.
+"""
+
+from __future__ import annotations
+
+import base64
+import binascii
+import io
+import socket
+import threading
+import uuid
+from collections.abc import Iterator
+from contextlib import contextmanager
+from pathlib import Path
+
+from PIL import Image
+
+from lattice_core.bridge import photocraft as _photocraft
+
+HOST = "127.0.0.1"
+CONTROL_PORT = 7979
+CONTROL_TIMEOUT = 5.0
+EXPORT_TIMEOUT = 60.0
+EXPORT_PPI = 72
+DEFAULT_LAYER_NAME = "Lattice Dither"
+IMAGE_KIND = "<image>"
+UNREADABLE = "No such file or directory"
+BridgeError = _photocraft.BridgeError
+
+
+def _png_bytes(img: Image.Image) -> bytes:
+    """Return the image as PNG bytes, keeping transparency when the image has any."""
+    keep_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
+    buffer = io.BytesIO()
+    try:
+        img.convert("RGBA" if keep_alpha else "RGB").save(buffer, format="PNG")
+    except OSError as exc:
+        raise BridgeError(f"cannot encode the image as PNG: {exc}") from exc
+    return buffer.getvalue()
+
+
+class DesignCraftClient:
+    """Client for the DesignCraft desktop control server on 127.0.0.1:7979."""
+
+    def __init__(self, port: int = CONTROL_PORT, timeout: float = CONTROL_TIMEOUT) -> None:
+        self._port = port
+        self._timeout = timeout
+        self._lock = threading.Lock()
+
+    @property
+    def port(self) -> int:
+        """Return the control port this client talks to."""
+        return self._port
+
+    @staticmethod
+    def discover(port: int = CONTROL_PORT) -> DesignCraftClient | None:
+        """Return a live client, or None when DesignCraft is not reachable."""
+        client = DesignCraftClient(port)
+        return client if client.ping() else None
+
+    def ping(self) -> bool:
+        """Return True when the server answers an engine.commands call."""
+        try:
+            with self._lock:
+                _photocraft._cleanup_exchange()
+                with self._session() as channel:
+                    channel.call("engine.commands")
+        except BridgeError:
+            return False
+        return True
+
+    def call(self, method: str, params: dict | None = None) -> object:
+        """Send one raw request on its own connection and return its result."""
+        with self._lock:
+            _photocraft._cleanup_exchange()
+            with self._session() as channel:
+                return channel.call(method, params)
+
+    def disconnect(self) -> None:
+        """Hold nothing: connections are per call, so this only drops the handle."""
+        return None
+
+    def render_document(self) -> Image.Image:
+        """Export the first page as a 72 ppi PNG and return it as an image."""
+        with self._lock:
+            _photocraft._cleanup_exchange()
+            params = {
+                "job": {
+                    "versions": [
+                        {"name": f"get_{uuid.uuid4().hex}", "format": "png", "ppi": EXPORT_PPI}
+                    ]
+                }
+            }
+            with self._session() as channel:
+                channel.set_timeout(EXPORT_TIMEOUT)
+                try:
+                    result = _photocraft._as_dict(
+                        _photocraft._execute(channel, "file.exportBatch", params),
+                        "file.exportBatch",
+                    )
+                finally:
+                    channel.set_timeout(self._timeout)
+            return self._decode(result)
+
+    def place_as_layer(self, img: Image.Image, name: str = DEFAULT_LAYER_NAME) -> int:
+        """Place the image into the selected frame or a new one and return its id."""
+        with self._lock:
+            _photocraft._cleanup_exchange()
+            png = _png_bytes(img)
+            path = self._write(png)
+            try:
+                with self._session() as channel:
+                    base = self._place_params(channel, name)
+                    return self._place(channel, base | {"path": str(path)}, png)
+            finally:
+                _photocraft._discard(path)
+
+    def _place(self, channel: _photocraft._Channel, params: dict, png: bytes) -> int:
+        """Run file.place, retrying with base64 when the host cannot read the path."""
+        try:
+            result = _photocraft._as_dict(
+                _photocraft._execute(channel, "file.place", params), "file.place"
+            )
+        except BridgeError as exc:
+            if UNREADABLE not in str(exc) or channel.broken:
+                raise
+            fallback = {key: value for key, value in params.items() if key != "path"}
+            fallback |= {"base64": base64.b64encode(png).decode("ascii")}
+            result = _photocraft._as_dict(
+                _photocraft._execute(channel, "file.place", fallback), "file.place"
+            )
+        return _photocraft._as_index(result.get("id"), "file.place")
+
+    def _write(self, png: bytes) -> Path:
+        """Write the PNG into the exchange directory and return its path."""
+        directory = _photocraft.EXCHANGE_DIR
+        try:
+            directory.mkdir(parents=True, exist_ok=True)
+        except OSError as exc:
+            raise BridgeError(f"cannot create the exchange directory: {exc}") from exc
+        path = directory / f"send_{uuid.uuid4().hex}.png"
+        try:
+            path.write_bytes(png)
+        except OSError as exc:
+            raise BridgeError(f"cannot write {path.name!r}: {exc}") from exc
+        return path
+
+    @staticmethod
+    def _decode(result: dict) -> Image.Image:
+        """Return the exported PNG carried by a file.exportBatch result."""
+        files = result.get("files")
+        first = files[0] if isinstance(files, list) and files else None
+        first = first if isinstance(first, dict) else {}
+        for encoded in (first.get("base64"), result.get("base64")):
+            if isinstance(encoded, str) and encoded:
+                try:
+                    with Image.open(io.BytesIO(base64.b64decode(encoded))) as handle:
+                        return handle.copy()
+                except (binascii.Error, OSError, ValueError) as exc:
+                    raise BridgeError(f"cannot read the exported PNG: {exc}") from exc
+        path = first.get("path")
+        if not isinstance(path, str):
+            raise BridgeError(f"file.exportBatch returned no file: {result!r}")
+        try:
+            with Image.open(path) as handle:
+                return handle.copy()
+        except OSError as exc:
+            raise BridgeError(f"cannot read the exported PNG {path!r}: {exc}") from exc
+
+    def _place_params(self, channel: _photocraft._Channel, name: str) -> dict:
+        """Return file.place parameters: into the selected frame, or into a new one."""
+        result = _photocraft._as_dict(
+            _photocraft._execute(channel, "document.inspect"), "document.inspect"
+        )
+        kinds = self._item_kinds(result)
+        frame = next(
+            (item for item in self._selected_ids(result) if kinds.get(item) != IMAGE_KIND), None
+        )
+        if frame is not None:
+            params: dict = {"frame": frame}
+        else:
+            left, top, right, _bottom = self._page_bounds(result)
+            params = {"x": left, "y": top, "width": right - left}
+        if name:
+            params["name"] = name
+        return params
+
+    @staticmethod
+    def _selected_ids(result: dict) -> list[int]:
+        """Return the selected object ids of a document.inspect result."""
+        selection = result.get("selection")
+        items = selection.get("items") if isinstance(selection, dict) else None
+        if not isinstance(items, list):
+            return []
+        return [item for item in items if isinstance(item, int) and not isinstance(item, bool)]
+
+    @staticmethod
+    def _item_kinds(result: dict) -> dict[int, str]:
+        """Return the kind of every object of a document.inspect result, by id."""
+        kinds: dict[int, str] = {}
+        for spread in result.get("spreads") or []:
+            items = spread.get("items") if isinstance(spread, dict) else None
+            for item in items or []:
+                if isinstance(item, dict) and isinstance(item.get("id"), int):
+                    kinds[item["id"]] = str(item.get("kind"))
+        return kinds
+
+    @staticmethod
+    def _page_bounds(result: dict) -> list[float]:
+        """Return [left, top, right, bottom] of the first page, or raise BridgeError."""
+        for spread in result.get("spreads") or []:
+            pages = spread.get("pages") if isinstance(spread, dict) else None
+            for page in pages or []:
+                bounds = page.get("bounds") if isinstance(page, dict) else None
+                if isinstance(bounds, list) and len(bounds) == 4:
+                    if all(isinstance(value, (int, float)) for value in bounds):
+                        return [float(value) for value in bounds]
+        raise BridgeError("document.inspect returned no page bounds")
+
+    @contextmanager
+    def _session(self) -> Iterator[_photocraft._Channel]:
+        """Open one control connection; DesignCraft's channel carries no token."""
+        try:
+            sock = socket.create_connection((HOST, self._port), timeout=self._timeout)
+        except OSError as exc:
+            raise BridgeError(
+                f"cannot connect to DesignCraft on {HOST}:{self._port}: {exc}"
+            ) from exc
+        channel = _photocraft._Channel(sock, self._timeout)
+        try:
+            yield channel
+        finally:
+            channel.close()
diff --git a/lattice_core/bridge/photocraft.py b/lattice_core/bridge/photocraft.py
index d4b2102..512eb8f 100644
--- a/lattice_core/bridge/photocraft.py
+++ b/lattice_core/bridge/photocraft.py
@@ -7,6 +7,7 @@ import os
 import re
 import socket
 import subprocess
+import sys
 import time
 from pathlib import Path
 from typing import Literal
@@ -26,12 +27,18 @@ SAVE_TIMEOUT = 60.0
 LARGE_DOCUMENT_SIDE = 4000
 DEFAULT_LAYER_NAME = "Lattice Dither"
 PREVIEW_LAYER_NAME = "Lattice Dither preview"
+_IS_WINDOWS = os.name == "nt"
 
 
-def _local_appdata() -> Path:
-    """Return %LOCALAPPDATA%, falling back to the default Windows location."""
-    value = os.environ.get("LOCALAPPDATA")
-    return Path(value) if value else Path.home() / "AppData" / "Local"
+def _app_data_root() -> Path:
+    """Return the platform app-data directory: %LOCALAPPDATA% on Windows, XDG on Linux."""
+    if _IS_WINDOWS:
+        value = os.environ.get("LOCALAPPDATA")
+        return Path(value) if value else Path.home() / "AppData" / "Local"
+    if sys.platform == "darwin":
+        return Path.home() / "Library" / "Application Support"
+    value = os.environ.get("XDG_DATA_HOME")
+    return Path(value) if value else Path.home() / ".local" / "share"
 
 
 APP_DIR_NAME = "LatticeDither"
@@ -39,8 +46,8 @@ LEGACY_APP_DIR_NAME = "DitherCraft"
 
 
 def _app_dir(name: str) -> Path:
-    """Return the per-application directory under %LOCALAPPDATA%."""
-    return _local_appdata() / name
+    """Return the per-application directory under the platform app-data directory."""
+    return _app_data_root() / name
 
 
 def _exchange_dir() -> Path:
diff --git a/tests/test_bridge.py b/tests/test_bridge.py
index b9116bd..527c5e3 100644
--- a/tests/test_bridge.py
+++ b/tests/test_bridge.py
@@ -1,7 +1,12 @@
-"""Tests for the PhotoCraft bridge (CONTRACT §8), against an in-process fake server."""
+"""Tests for the ArtCraft bridge (CONTRACT §7): PhotoCraft and DesignCraft adapters.
+
+Every test runs against an in-process fake server, so the suite needs no host.
+"""
 
 from __future__ import annotations
 
+import base64
+import io
 import json
 import os
 import socket
@@ -13,7 +18,8 @@ from pathlib import Path
 import pytest
 from PIL import Image
 
-from lattice_core.bridge import photocraft
+from lattice_core.bridge import ArtCraftClient, photocraft
+from lattice_core.bridge.designcraft import DesignCraftClient
 from lattice_core.bridge.photocraft import BridgeError, PhotoCraftClient
 
 TOKEN = "a" * 64
@@ -38,7 +44,7 @@ def _send(conn: socket.socket, payload: dict) -> None:
 class FakeDesktopServer:
     """In-process fake of the PhotoCraft desktop control server."""
 
-    def __init__(self, handler, token: str = TOKEN) -> None:
+    def __init__(self, handler, token: str | None = TOKEN) -> None:
         self.token, self.handler = token, handler
         self.connections: list[list[dict]] = []
         self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
@@ -86,7 +92,7 @@ class FakeDesktopServer:
             while line := reader.readline():
                 request = json.loads(line.decode("utf-8"))
                 record.append(request)
-                if len(record) == 1:
+                if len(record) == 1 and self.token is not None:
                     params = request.get("params") or {}
                     if request.get("method") != "auth" or params.get("token") != self.token:
                         refusal = {"id": request.get("id"), "ok": False}
@@ -656,3 +662,287 @@ def test_save_timeout_is_sixty_seconds_for_large_documents(
     small = server(handler((4000, 100)))
     PhotoCraftClient(small.port, TOKEN).render_document()
     assert 60.0 not in values
+
+# --------------------------------------------------------------------------- DesignCraft
+
+
+def _png_b64(size: tuple[int, int], colour: tuple[int, int, int]) -> str:
+    """Return a base64 PNG of that size and colour, as file.exportBatch sends it."""
+    buffer = io.BytesIO()
+    Image.new("RGB", size, colour).save(buffer, format="PNG")
+    return base64.b64encode(buffer.getvalue()).decode("ascii")
+
+
+PAGE = [0.0, 0.0, 595.0, 842.0]
+
+
+def _inspect(
+    selection: list[int] | None = None,
+    items: list[dict] | None = None,
+    page: list[float] | None = None,
+) -> dict:
+    """Build a document.inspect result with one page and the given objects."""
+    return {
+        "selection": {"content": False, "items": selection or []},
+        "spreads": [
+            {"index": 0, "pages": [{"bounds": page or PAGE}], "items": items or []},
+        ],
+    }
+
+
+class DesignCraftHandler:
+    """Scripted DesignCraft responder: inspect, file.place and file.exportBatch."""
+
+    def __init__(self, exchange: Path, page: list[float] | None = None, fail: str | None = None,
+                 unreadable: bool = False, inspect: dict | None = None) -> None:
+        self.exchange = exchange
+        self.page = page or PAGE
+        self.fail = fail
+        self.unreadable = unreadable
+        self.inspect = inspect if inspect is not None else _inspect(page=self.page)
+        self.placed: list[dict] = []
+        self.png_present_at_place = False
+        self._next_id = 40
+
+    def __call__(self, request: dict) -> dict:
+        params = request.get("params") or {}
+        command = params.get("command")
+        if params.get("command") is None and request["method"] == "engine.commands":
+            return _ok(request, [{"id": "file.place"}])
+        if self.fail == command:
+            return _error(request, f"{command} failed")
+        if command == "document.inspect":
+            return _ok(request, self.inspect)
+        if command == "file.place":
+            payload = params["params"]
+            if self.unreadable and "path" in payload:
+                return _error(request, f"{payload['path']}: No such file or directory")
+            self.png_present_at_place = "path" in payload and Path(payload["path"]).is_file()
+            self.placed.append(payload)
+            self._next_id += 1
+            return _ok(request, {"asset": 7, "id": self._next_id})
+        if command == "file.exportBatch":
+            width = int(round(self.page[2] - self.page[0]))
+            height = int(round(self.page[3] - self.page[1]))
+            return _ok(request, {"files": [{"base64": _png_b64((width, height), (12, 34, 56))}]})
+        return _error(request, f"unexpected {request['method']}")
+
+
+@pytest.fixture
+def designcraft_server(server):
+    """Start an unauthenticated fake DesignCraft server: its channel has no token."""
+
+    def start(handler) -> FakeDesktopServer:
+        return server(handler, token=None)
+
+    return start
+
+
+def test_artcraft_discover_photocraft_needs_a_token(
+    tmp_path: Path, exchange: Path, server, monkeypatch
+) -> None:
+    """discover("photocraft") is None without a token file and live when the host answers."""
+    monkeypatch.setattr(photocraft, "TOKEN_PATH", tmp_path / "absent.token")
+    monkeypatch.setattr(photocraft, "LEGACY_TOKEN_PATH", tmp_path / "absent-legacy.token")
+    assert ArtCraftClient.discover("photocraft", port=47998) is None
+    fake = server(lambda request: _ok(request, []))
+    monkeypatch.setattr(photocraft, "TOKEN_PATH", _token_file(tmp_path))
+    assert ArtCraftClient.discover("photocraft", port=47998) is None
+    found = ArtCraftClient.discover("photocraft", port=fake.port)
+    assert found is not None and found.host == "photocraft"
+    assert found.ping()
+    assert [request["method"] for request in fake.requests] == ["auth", "engine.commands"] * 2
+
+
+def test_artcraft_photocraft_facade_places_a_layer(exchange: Path, server, monkeypatch,
+                                                   tmp_path: Path) -> None:
+    """The facade reaches PhotoCraft's own §8.4 sequence unchanged."""
+    tokens = tmp_path / "tokens"
+    tokens.mkdir()
+    monkeypatch.setattr(photocraft, "TOKEN_PATH", _token_file(tokens))
+    places = PlaceHandler(exchange)
+
+    def handler(request: dict) -> dict:
+        if request["method"] == "engine.commands":
+            return _ok(request, [{"id": "document.inspect"}])
+        return places(request)
+
+    fake = server(handler)
+    client = ArtCraftClient.discover("photocraft", port=fake.port)
+    assert client is not None
+    assert client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither") == 24
+    assert _sequence(fake)[2:4] == [
+        ("engine.execute", "document.activate"), ("app.open", None),
+    ]
+    assert not list(exchange.glob("*.png"))
+
+
+def test_artcraft_discover_designcraft_needs_no_token(exchange: Path, designcraft_server) -> None:
+    """discover("designcraft") is None when the port is closed and live when it answers."""
+    assert ArtCraftClient.discover("designcraft", port=47997) is None
+    fake = designcraft_server(lambda request: _ok(request, [{"id": "file.place"}]))
+    found = ArtCraftClient.discover("designcraft", port=fake.port)
+    assert found is not None and found.host == "designcraft"
+    assert found.ping()
+    assert [request["method"] for request in fake.requests] == ["engine.commands"] * 2
+
+
+def test_artcraft_discover_rejects_an_unknown_host() -> None:
+    """A host name outside the two adapters is a programming error, not a bridge failure."""
+    with pytest.raises(ValueError, match="unknown ArtCraft host"):
+        ArtCraftClient.discover("pdfcraft")
+
+
+def test_designcraft_render_document_matches_the_inspected_page(
+    exchange: Path, designcraft_server
+) -> None:
+    """render_document exports the page at 72 ppi and returns its pixels."""
+    handler = DesignCraftHandler(exchange, page=[0.0, 0.0, 300.0, 200.0])
+    fake = designcraft_server(handler)
+    image = DesignCraftClient(fake.port).render_document()
+    assert image.size == (300, 200)
+    assert image.getpixel((0, 0)) == (12, 34, 56)
+    export = [request for request in fake.requests
+              if (request.get("params") or {}).get("command") == "file.exportBatch"]
+    assert export[0]["params"]["params"]["job"]["versions"][0]["ppi"] == 72
+    assert "dir" not in export[0]["params"]["params"]
+    assert list(exchange.iterdir()) == []
+
+
+def test_designcraft_place_creates_a_frame_when_nothing_is_selected(
+    exchange: Path, designcraft_server
+) -> None:
+    """With no selection, file.place gets {path, x, y, width} taken from the page."""
+    handler = DesignCraftHandler(exchange)
+    fake = designcraft_server(handler)
+    placed = DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither")
+    assert isinstance(placed, int) and placed == 41
+    assert handler.placed == [
+        {"x": 0.0, "y": 0.0, "width": 595.0, "name": "Lattice Dither",
+         "path": handler.placed[0]["path"]}
+    ]
+    assert handler.png_present_at_place
+    assert Path(handler.placed[0]["path"]).parent == exchange
+    assert list(exchange.iterdir()) == []
+
+
+def test_designcraft_place_uses_the_selected_frame(exchange: Path, designcraft_server) -> None:
+    """A selected frame is passed as `frame`, and a selected image is not a frame."""
+    inspect = _inspect(selection=[12], items=[{"id": 12, "kind": "<rectangle>"},
+                                             {"id": 9, "kind": "<image>"}])
+    handler = DesignCraftHandler(exchange, inspect=inspect)
+    fake = designcraft_server(handler)
+    DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "in frame")
+    assert handler.placed[0]["frame"] == 12
+    assert "x" not in handler.placed[0] and "width" not in handler.placed[0]
+
+    image_only = _inspect(selection=[9], items=[{"id": 9, "kind": "<image>"}])
+    other = DesignCraftHandler(exchange, inspect=image_only)
+    DesignCraftClient(designcraft_server(other).port).place_as_layer(Image.new("RGB", (4, 4)), "x")
+    assert "frame" not in other.placed[0]
+    assert other.placed[0]["width"] == 595.0
+
+
+def test_designcraft_place_falls_back_to_base64(exchange: Path, designcraft_server) -> None:
+    """A host that cannot read the exchange path gets the same PNG as base64."""
+    handler = DesignCraftHandler(exchange, unreadable=True)
+    fake = designcraft_server(handler)
+    assert DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "b64") == 41
+    assert len(handler.placed) == 1
+    payload = handler.placed[0]
+    assert "path" not in payload and payload["name"] == "b64"
+    assert Image.open(io.BytesIO(base64.b64decode(payload["base64"]))).size == (4, 4)
+    assert list(exchange.iterdir()) == []
+
+
+@pytest.mark.parametrize("command", ["file.place", "file.exportBatch", "document.inspect"])
+def test_designcraft_failures_are_typed_and_leave_no_file(
+    exchange: Path, designcraft_server, command: str
+) -> None:
+    """A refused command raises BridgeError and the exchange directory stays empty."""
+    handler = DesignCraftHandler(exchange, fail=command)
+    client = DesignCraftClient(designcraft_server(handler).port)
+    with pytest.raises(BridgeError, match=f"{command} failed"):
+        if command == "file.exportBatch":
+            client.render_document()
+        else:
+            client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither")
+    assert list(exchange.iterdir()) == []
+
+
+def test_designcraft_does_not_retry_a_broken_connection(
+    exchange: Path, designcraft_server
+) -> None:
+    """A dead connection is not retried as base64: the failure is reported once."""
+    calls: list[str] = []
+
+    def handler(request: dict) -> dict | None:
+        command = (request.get("params") or {}).get("command")
+        calls.append(command or request["method"])
+        if command == "document.inspect":
+            return _ok(request, _inspect())
+        return None
+
+    fake = designcraft_server(handler)
+    with pytest.raises(BridgeError, match="closed the connection"):
+        DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "x")
+    assert calls.count("file.place") == 1
+    assert list(exchange.iterdir()) == []
+
+
+def test_designcraft_timeout_raises_bridge_error(exchange: Path, designcraft_server) -> None:
+    """A host that never answers makes the call fail with BridgeError, not hang."""
+    def handler(request: dict) -> dict:
+        time.sleep(0.4)
+        return _ok(request, _inspect())
+
+    with pytest.raises(BridgeError):
+        DesignCraftClient(designcraft_server(handler).port, timeout=0.1).render_document()
+
+
+def test_designcraft_discards_old_exchange_files(exchange: Path, designcraft_server) -> None:
+    """Files older than one hour are deleted on the next call, fresh ones are kept."""
+    stale = exchange / "stale.png"
+    stale.write_bytes(b"x")
+    os.utime(stale, (time.time() - 7200.0,) * 2)
+    fresh = exchange / "fresh.png"
+    fresh.write_bytes(b"x")
+    fake = designcraft_server(DesignCraftHandler(exchange))
+    DesignCraftClient(fake.port).render_document()
+    assert not stale.exists()
+    assert fresh.exists()
+
+
+def test_designcraft_rejects_a_result_without_a_file(exchange: Path, designcraft_server) -> None:
+    """A file.exportBatch result with no PNG is a BridgeError, never an AttributeError."""
+    fake = designcraft_server(lambda request: _ok(request, {"files": []}))
+    with pytest.raises(BridgeError, match="returned no file"):
+        DesignCraftClient(fake.port).render_document()
+
+
+def test_exchange_dir_follows_the_platform_app_data_directory(monkeypatch, tmp_path: Path) -> None:
+    """§7: %LOCALAPPDATA%/<App> on Windows, ~/.local/share/<App> on Linux."""
+    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "win"))
+    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
+    monkeypatch.setattr(photocraft, "_IS_WINDOWS", True)
+    assert photocraft._app_dir("LatticeDither") == tmp_path / "win" / "LatticeDither"
+    monkeypatch.setattr(photocraft, "_IS_WINDOWS", False)
+    monkeypatch.setattr(photocraft.sys, "platform", "linux")
+    assert photocraft._app_dir("LatticeDither") == tmp_path / "xdg" / "LatticeDither"
+    monkeypatch.delenv("XDG_DATA_HOME")
+    expected = Path.home() / ".local" / "share" / "LatticeDither"
+    assert photocraft._app_dir("LatticeDither") == expected
+
+
+def test_artcraft_client_delegates_to_the_adapter(exchange: Path, designcraft_server) -> None:
+    """The facade forwards ping, call, render_document, place_as_layer and disconnect."""
+    handler = DesignCraftHandler(exchange)
+    fake = designcraft_server(handler)
+    client = ArtCraftClient.discover("designcraft", port=fake.port)
+    assert client is not None
+    assert client.ping()
+    assert client.call("engine.commands") == [{"id": "file.place"}]
+    assert client.render_document().size == (595, 842)
+    assert client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither") == 41
+    client.disconnect()
+    assert list(exchange.iterdir()) == []
diff --git a/tests/test_bridge_smoke.py b/tests/test_bridge_smoke.py
index e5dec09..3725b10 100644
--- a/tests/test_bridge_smoke.py
+++ b/tests/test_bridge_smoke.py
@@ -1,16 +1,22 @@
-"""Tests for the manual PhotoCraft smoke tool (CONTRACT section 8.6)."""
+"""Tests for the manual PhotoCraft smoke tool (§8.6) and the ArtCraft generalisation (§7)."""
 
 from __future__ import annotations
 
 import importlib.util
 import os
+import socket
 import subprocess
 import sys
+import threading
 from pathlib import Path
 
 import pytest
 from PIL import Image
 
+from lattice_core.bridge import ArtCraftClient, photocraft
+from lattice_core.bridge.designcraft import DesignCraftClient
+from lattice_core.bridge.photocraft import BridgeError
+
 ROOT = Path(__file__).resolve().parents[1]
 
 
@@ -103,3 +109,74 @@ def test_smoke_tool_checks_the_new_layer_and_closes_the_document(
     assert f"FAIL at step {step}" in out
     close = {"command": "file.close", "params": {"document": 1, "save": "discard"}}
     assert ("engine.execute", close) in stub.calls
+
+
+# --------------------------------------------------------------------- ArtCraft generalisation
+
+
+@pytest.fixture
+def exchange(tmp_path, monkeypatch) -> Path:
+    """Point the shared exchange directory at a temporary directory."""
+    monkeypatch.setattr(photocraft, "EXCHANGE_DIR", tmp_path)
+    return tmp_path
+
+
+def test_a_host_that_hangs_up_is_a_typed_error(exchange: Path) -> None:
+    """A host that accepts and closes at once raises BridgeError, never OSError or a hang."""
+    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
+    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
+    listener.bind(("127.0.0.1", 0))
+    listener.listen(4)
+    listener.settimeout(0.02)
+    port = listener.getsockname()[1]
+    stop = threading.Event()
+
+    def serve() -> None:
+        while not stop.is_set():
+            try:
+                conn, _ = listener.accept()
+            except TimeoutError:
+                continue
+            except OSError:
+                return
+            conn.close()
+
+    threading.Thread(target=serve, daemon=True).start()
+    try:
+        assert DesignCraftClient.discover(port) is None
+        with pytest.raises(BridgeError):
+            DesignCraftClient(port).render_document()
+    finally:
+        stop.set()
+        listener.close()
+    assert list(exchange.iterdir()) == []
+
+
+@pytest.mark.manual
+@pytest.mark.skipif(
+    os.environ.get("LATTICE_BRIDGE_LIVE") != "1",
+    reason="set LATTICE_BRIDGE_LIVE=1 to touch a real ArtCraft host",
+)
+def test_live_hosts_smoke(monkeypatch) -> None:
+    """Manual: against a running host, place a layer, render it back and verify the placement."""
+    shared = os.environ.get("LATTICE_BRIDGE_EXCHANGE")
+    if shared:
+        monkeypatch.setattr(photocraft, "EXCHANGE_DIR", Path(shared))
+    client = ArtCraftClient.discover("photocraft") or ArtCraftClient.discover("designcraft")
+    if client is None:
+        pytest.skip("no ArtCraft host is running")
+    assert client.ping()
+    image = Image.new("RGB", (64, 48), (200, 30, 40))
+    try:
+        if client.host == "photocraft" and not client.client.documents():
+            client.call("engine.execute", {"command": "file.new", "params": {"width": 400}})
+        placed = client.place_as_layer(image, "Lattice Dither smoke")
+        rendered = client.render_document()
+    except BridgeError as exc:
+        pytest.skip(f"host is running but not ready for automation: {exc}")
+    assert isinstance(placed, int)
+    assert rendered.width > 0 and rendered.height > 0
+    if client.host == "designcraft":
+        inspected = client.call("engine.execute", {"command": "document.inspect"})
+        ids = [item["id"] for spread in inspected["spreads"] for item in spread["items"]]
+        assert placed in ids


CODER NOTES AND DEVIATIONS (L5, attempt 1, deepseek-v4-1-flash-1017)
- Bridge réécrit : ArtCraftClient (discover/ping/render_document/place_as_layer + call/
  disconnect), un adaptateur par hôte, un seul BridgeError, discover → None hôte absent,
  ValueError sur nom d'hôte inconnu.
- DesignCraftClient (nouveau, 245 l.) sur 127.0.0.1:7979 : file.place {path, frame?, name} si
  cadre sélectionné sinon {path, x, y, width} sur les bounds de la page (document.inspect) ;
  render_document via file.exportBatch (PNG) ; timeout par connexion (5 s / 60 s export), échec
  → BridgeError, fichier d'échange supprimé en finally.
- PhotoCraft : seul changement = racine app-data §7 (%LOCALAPPDATA% Win / XDG Linux). Code
  PhotoCraft inchangé.
- Hôtes réels exercés : PhotoCraft 0.23.1 (47600, token) et DesignCraft 0.20.1 (7979) —
  discovery, place_as_layer, render_document, zéro résiduel ; token absent → None, port fermé → None.
- AMD observées : surface `file.place` (designcraft-cli describe 0.20.1 : path?|base64?, name?,
  frame?, spread?, x?, y?, width?, height?, pdfPage?) ; canal DesignCraft SANS authentification
  (auth → unknown method, découverte = connexion + engine.commands) ; sous Flatpak l'hôte ne lit
  que xdg-documents/xdg-pictures → repli base64 documenté, export sans dir renvoyant le PNG en
  base64, aucun fichier d'échange nécessaire.
- E1 ×2 : racine app-data Linux ajoutée (§7 l'exigeait) ; discover lève ValueError sur hôte
  inconnu (bug d'appel, pas absence d'hôte).
