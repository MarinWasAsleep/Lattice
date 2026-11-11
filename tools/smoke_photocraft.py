"""Manual smoke test of the PhotoCraft bridge (CONTRACT §8.6).

Never run by the gates. Requires PhotoCraft started from the Desktop shortcut
"PhotoCraft (DitherCraft)" so that the control server and both automation roots
are configured. The tool only touches the test document it opens itself.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from dithercraft.bridge.photocraft import (  # noqa: E402
    EXCHANGE_DIR,
    BridgeError,
    PhotoCraftClient,
    installed_photocraft_version,
    version_status,
)

LAYER_NAME = "DitherCraft smoke"
TEST_SIZE = (64, 48)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line of the smoke tool."""
    parser = argparse.ArgumentParser(
        prog="smoke_photocraft.py",
        description=(
            "Manual smoke test of the PhotoCraft bridge (CONTRACT §8.6). "
            "Launch PhotoCraft from the 'PhotoCraft (DitherCraft)' shortcut first."
        ),
    )
    parser.add_argument("--keep", action="store_true", help="keep the generated test PNG")
    return parser.parse_args(argv)


def _write_png(path: Path) -> None:
    """Write the 64x48 grey gradient used as the test document."""
    width, height = TEST_SIZE
    ramp = np.linspace(0.0, 255.0, width, dtype=np.uint8)
    data = np.repeat(np.repeat(ramp[None, :, None], height, axis=0), 3, axis=2)
    Image.fromarray(data, "RGB").save(path, format="PNG")


def _snapshot(client: PhotoCraftClient) -> tuple[int, int]:
    """Return the document count and the active document index."""
    session = client.call("ui.inspect").get("session") or {}
    documents = session.get("documents") or []
    return len(documents), int(session.get("active", -1))


def _find_index(client: PhotoCraftClient, name: str) -> int:
    """Return the index of the document whose path or name is `name`."""
    session = client.call("ui.inspect").get("session") or {}
    for document in session.get("documents") or []:
        if document.get("path") == name or document.get("name") == name:
            return int(document["index"])
    raise BridgeError(f"test document {name!r} not found in the session")


def _invert(img: Image.Image) -> Image.Image:
    """Return an inverted RGB copy of the image."""
    return Image.eval(img.convert("RGB"), lambda value: 255 - value)


def _check_layer(client: PhotoCraftClient, layer_name: str) -> None:
    """Check that the active layer is the new Pixel layer created by the bridge."""
    result = client.call("engine.execute", {"command": "document.inspect"})
    active = result.get("activeLayer")
    if active is None:
        raise BridgeError("document.inspect returned no activeLayer")
    layers = result.get("layers") or []
    for layer in layers:
        if layer.get("id") != active:
            continue
        if layer.get("name") != layer_name:
            raise BridgeError(f"active layer is {layer.get('name')!r}, expected {layer_name!r}")
        kind = str(layer.get("kind") or layer.get("type") or "").lower()
        if kind and "pixel" not in kind:
            raise BridgeError(f"active layer kind is {kind!r}, expected a Pixel layer")
        return
    if layers:
        raise BridgeError(f"active layer {active} is missing from document.inspect")


def _close(client: PhotoCraftClient, index: int) -> None:
    """Close one document, discarding it."""
    client.call(
        "engine.execute",
        {"command": "file.close", "params": {"document": index, "save": "discard"}},
    )


def _verify_restored(client: PhotoCraftClient, before: tuple[int, int]) -> None:
    """Check that the document count and the active index are back to their initial values."""
    after = _snapshot(client)
    if after != before:
        raise BridgeError(f"session not restored: before {before}, after {after}")


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test and return the process exit code."""
    args = _parse_args(argv)
    step = 0
    client: PhotoCraftClient | None = None
    helper: int | None = None
    before: tuple[int, int] | None = None
    png = EXCHANGE_DIR / f"smoke_{uuid.uuid4().hex}.png"
    try:
        step = 1
        client = PhotoCraftClient.discover()
        if client is None:
            raise BridgeError(
                "control server not reachable; launch PhotoCraft from the "
                "'PhotoCraft (DitherCraft)' shortcut"
            )
        installed = installed_photocraft_version() or "unknown"
        print(f"installed PhotoCraft: {installed} ({version_status()})")
        step = 2
        before = _snapshot(client)
        step = 3
        _write_png(png)
        step = 4
        client.call("app.open", {"path": png.name})
        step = 5
        helper = _find_index(client, png.name)
        step = 6
        image = client.render_document()
        step = 7
        client.place_as_layer(_invert(image), LAYER_NAME)
        step = 8
        _check_layer(client, LAYER_NAME)
        step = 9
        _close(client, helper)
        helper = None
        step = 10
        _verify_restored(client, before)
    except Exception as exc:
        print(f"FAIL at step {step}: {exc}")
        return 1
    finally:
        if helper is not None and client is not None:
            try:
                _close(client, helper)
            except BridgeError:
                pass
        if not args.keep:
            png.unlink(missing_ok=True)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
