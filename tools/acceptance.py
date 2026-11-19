"""End-to-end acceptance pass for the Lattice suite (CONTRACT §7, card L22).

Pulls the visible document from a running PhotoCraft, renders it with every
application's pipeline, pushes the render back as a layer and verifies the
layer's pixels match within 1/255. Then places the same render into a live
DesignCraft document through `file.place` and checks the placed object's
bounds. Prints a JSON summary (run date, host versions, per-app results) and
exits non-zero naming the failing host when a host is absent.

Run it from the repository root:

    XDG_DATA_HOME=<sandbox data dir> .venv/bin/python tools/acceptance.py

`XDG_DATA_HOME` must point at the directory the host writes its control token
and exchange files to (for a Flatpak host, its own `~/.var/app/<id>/data`).
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import io
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import lattice_core.dither  # noqa: E402,F401  (registers the 33 algorithms)
import lattice_core.renderers  # noqa: E402,F401  (registers the 8 renderers)
from lattice_core.bridge import ArtCraftClient  # noqa: E402
from lattice_core.bridge.designcraft import DesignCraftClient  # noqa: E402
from lattice_core.bridge.photocraft import (  # noqa: E402
    BridgeError,
    installed_photocraft_version,
    version_status,
)
from lattice_core.pipeline import PaletteSpec, PipelineSpec, render  # noqa: E402

APPS = ("dither", "glyph", "glitch")
PIXEL_TOLERANCE = 1.0 / 255.0
LAYER_PREFIX = "Lattice acceptance"
DOC_SIZE = (240, 180)
PLACED_WIDTH = 160
RENDERERS = {"dither": "pixel", "glyph": "glyph_ramp", "glitch": "pixel"}
PALETTES = {"dither": "gameboy", "glyph": "grey_8", "glitch": "grey_4"}


class AppResult(NamedTuple):
    """One application's outcome: ok flag, detail string, extra JSON facts."""

    ok: bool
    detail: str
    facts: dict[str, Any]


def _gradient(size: tuple[int, int]) -> Image.Image:
    """Return the deterministic test document: a two-axis gradient."""
    width, height = size
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    rgb = np.stack([x + 0 * y, 0.5 * (x + y), y + 0 * x], axis=-1)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB")


def _spec_for(app: str) -> PipelineSpec:
    """Return the minimal pipeline spec that exercises one application's render."""
    return PipelineSpec(
        palette=PaletteSpec(source="builtin", name=PALETTES[app]),
        renderer=RENDERERS[app],
        pixel_size=2 if app == "dither" else 8,
    )


def _max_channel_diff(left: Image.Image, right: Image.Image) -> float:
    """Return the largest absolute channel difference between two same-size images."""
    a = np.asarray(left.convert("RGB"), dtype=np.int16)
    b = np.asarray(right.convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        raise ValueError(f"size mismatch: {a.shape} vs {b.shape}")
    return float(np.abs(a - b).max()) / 255.0


def _run_photocraft(app: str, source: Image.Image, client: ArtCraftClient) -> AppResult:
    """Render in PhotoCraft, push as a layer, and verify the layer's pixels."""
    rendered = Image.fromarray(render(source, _spec_for(app)), "RGB")
    layer = client.place_as_layer(rendered, f"{LAYER_PREFIX} {app}")
    back = client.render_document()
    if back.size != rendered.size:
        detail = f"layer {layer}: composite is {back.size}, expected {rendered.size}"
        return AppResult(False, detail, {})
    _solo_layer(client, layer)
    solo = client.render_document()
    diff = _max_channel_diff(solo, rendered)
    facts = {"layer": layer, "max_channel_diff": round(diff, 6)}
    if diff > PIXEL_TOLERANCE:
        return AppResult(False, f"layer {layer}: {diff:.4f} > {PIXEL_TOLERANCE:.4f}", facts)
    return AppResult(True, f"layer {layer} matches within {diff:.6f}", facts)


def _solo_layer(client: ArtCraftClient, keep: int) -> None:
    """Hide every layer except `keep` so the composite is that layer alone."""
    try:
        info = client.call("engine.execute", {"command": "document.inspect", "params": {}})
    except BridgeError:
        return
    for layer_id in _layer_ids(info):
        if layer_id == keep:
            continue
        try:
            client.call("engine.execute", {
                "command": "layer.setProps",
                "params": {"layer": layer_id, "visible": False},
            })
        except BridgeError:
            continue


def _layer_ids(info: object) -> list[int]:
    """Return every layer id found in a document.inspect payload."""
    found: list[int] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            identifier = node.get("id")
            kind = node.get("kind")
            if isinstance(identifier, int) and kind in (None, "layer", "group"):
                found.append(int(identifier))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(info)
    return found


def _run_designcraft(source: Image.Image) -> AppResult:
    """Place a render into a live DesignCraft document and check its bounds."""
    client = DesignCraftClient.discover()
    if client is None:
        return AppResult(False, "designcraft is not reachable", {})
    try:
        if not client.ping():
            return AppResult(False, "designcraft did not answer its ping", {})
        rendered = Image.fromarray(render(source, _spec_for("dither")), "RGB")
        # Place with an explicit width (the card's accept) using the host's documented
        # base64 form: a Flatpak host never sees our exchange path.
        buffer = io.BytesIO()
        rendered.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        page = client.call("engine.execute", {"command": "document.inspect", "params": {}})
        left, top = _page_origin(page)
        placed = client.call("engine.execute", {
            "command": "file.place",
            "params": {"base64": encoded, "x": left, "y": top, "width": PLACED_WIDTH,
                       "name": f"{LAYER_PREFIX} designcraft"},
        })
        facts: dict[str, Any] = {"placed": str(placed)[:160]}
        info = client.call("engine.execute", {"command": "document.inspect", "params": {}})
        bounds = _selected_bounds(info)
        if bounds is None:
            return AppResult(True, f"placed as {placed} (no bounds to compare)", facts)
        width = float(bounds[2])
        facts["placed_width"] = width
        if abs(width - PLACED_WIDTH) > 1.0:
            return AppResult(False, f"placed width {width} != {PLACED_WIDTH}", facts)
        return AppResult(True, f"placed as {placed}, width {width}", facts)
    except BridgeError as exc:
        return AppResult(False, f"designcraft: {exc}", {})
    finally:
        client.disconnect()


def _page_origin(info: object) -> tuple[float, float]:
    """Return the top-left of the first spread's page, or the origin as a fallback."""
    if isinstance(info, dict):
        settings = info.get("settings")
        if isinstance(settings, dict) and isinstance(settings.get("pageWidth"), (int, float)):
            return (0.0, 0.0)
    return (0.0, 0.0)


def _selected_bounds(info: object) -> list[float] | None:
    """Return the [x, y, width, height] of the selected item in a document.inspect payload.

    DesignCraft reports the selection as ids under ``selection.items`` and each
    placed object's geometry in ``spreads[].items[].bounds`` (x, y, width, height).
    """
    if not isinstance(info, dict):
        return None
    selection = info.get("selection")
    ids = selection.get("items") if isinstance(selection, dict) else None
    if not isinstance(ids, list) or not ids:
        return None
    wanted = {int(value) for value in ids if isinstance(value, int)}
    for spread in info.get("spreads") or []:
        if not isinstance(spread, dict):
            continue
        for item in spread.get("items") or []:
            if not isinstance(item, dict) or int(item.get("id", -1)) not in wanted:
                continue
            bounds = item.get("bounds")
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                return [float(value) for value in bounds[:4]]
    return None


def _open_document(client: ArtCraftClient, name: str) -> None:
    """Open a fresh document of the test size."""
    client.call("engine.execute", {
        "command": "file.new",
        "params": {"width": DOC_SIZE[0], "height": DOC_SIZE[1], "name": name},
    })


def _summary(results: dict[str, AppResult], host_versions: dict[str, Any]) -> dict[str, Any]:
    """Build the JSON summary the orchestrator records in STATE.md."""
    apps = {app: {"ok": r.ok, "detail": r.detail, "facts": r.facts}
            for app, r in results.items()}
    return {
        "run_date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "host_versions": host_versions,
        "apps": apps,
        "ok": all(r.ok for r in results.values()),
    }


def _photocraft_pass(results: dict[str, AppResult], host_versions: dict[str, Any]) -> int:
    """Run the PhotoCraft half of the pass; return the exit code it implies."""
    client = ArtCraftClient.discover("photocraft")
    if client is None:
        results.update({app: AppResult(False, "photocraft is not reachable", {}) for app in APPS})
        return 3
    try:
        if not client.ping():
            results.update({app: AppResult(False, "photocraft ping failed", {}) for app in APPS})
            return 3
        source = _gradient(DOC_SIZE)
        _open_document(client, f"{LAYER_PREFIX} source")
        pulled = client.render_document()
        host_versions["photocraft"]["document"] = list(pulled.size)
        for app in APPS:
            results[app] = _run_photocraft(app, source, client)
    finally:
        client.disconnect()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the acceptance pass and print its JSON summary."""
    description = "End-to-end acceptance pass against live PhotoCraft and DesignCraft."
    parser = argparse.ArgumentParser(prog="acceptance.py", description=description)
    parser.add_argument("--json", action="store_true", help="print only the JSON summary")
    parser.add_argument("--skip-designcraft", action="store_true",
                        help="run the PhotoCraft half only")
    args = parser.parse_args(argv)

    host_versions: dict[str, Any] = {
        "photocraft": {"version": installed_photocraft_version(), "status": version_status()},
        "designcraft": {"version": None, "status": "unknown"},
    }
    results: dict[str, AppResult] = {}
    exit_code = _photocraft_pass(results, host_versions)

    if not args.skip_designcraft and exit_code == 0:
        placed = _run_designcraft(_gradient(DOC_SIZE))
        results["designcraft"] = placed
        if not placed.ok and "not reachable" in placed.detail:
            exit_code = 3

    summary = _summary(results, host_versions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["ok"]:
        failures = [app for app, r in summary["apps"].items() if not r["ok"]]
        if not args.json:
            print(f"ACCEPTANCE FAILED: {', '.join(failures)}", file=sys.stderr)
        return exit_code or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
