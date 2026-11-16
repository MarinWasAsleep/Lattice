"""Tests for the manual PhotoCraft smoke tool (§8.6) and the ArtCraft generalisation (§7)."""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image

from lattice_core.bridge import ArtCraftClient, photocraft
from lattice_core.bridge.designcraft import DesignCraftClient
from lattice_core.bridge.photocraft import BridgeError

ROOT = Path(__file__).resolve().parents[1]


def _load_smoke():
    """Import tools/smoke_photocraft.py as a module without running main."""
    path = ROOT / "tools" / "smoke_photocraft.py"
    spec = importlib.util.spec_from_file_location("smoke_photocraft", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_tool(monkeypatch, capsys) -> None:
    """--help exits 0 without touching the app, and an unreachable server fails at step 1."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "smoke_photocraft.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=ROOT, check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0
    assert "usage" in completed.stdout.lower()
    module = _load_smoke()
    monkeypatch.setattr(
        module.PhotoCraftClient, "discover", staticmethod(lambda *args, **kwargs: None)
    )
    assert module.main([]) == 1
    assert "FAIL at step 1" in capsys.readouterr().out


class _SmokeStub:
    """Client stub for the smoke tool: scripted session, layer list and placement."""

    def __init__(self, layers: list[dict] | None, grow: bool = True, hide: bool = False) -> None:
        self.layers, self.grow, self.hide = layers, grow, hide
        self.calls: list[tuple[str, dict | None]] = []
        self.opened: str | None = None

    def call(self, method: str, params: dict | None = None) -> object:
        self.calls.append((method, params))
        command = (params or {}).get("command")
        if method == "app.open":
            self.opened = params["path"]
            return {"name": self.opened, "path": self.opened}
        if method == "ui.inspect":
            documents = [{"index": 0, "name": "user.png", "path": "user.png"}]
            if self.opened and self.hide:
                self.hide = False
            elif self.opened:
                documents.append({"index": 1, "name": self.opened, "path": self.opened})
            return {"session": {"active": 0, "documents": documents}}
        if command == "file.close":
            self.opened = None
        elif command == "document.inspect":
            return {"activeLayer": 7, "layers": self.layers}
        return {}

    def render_document(self) -> Image.Image:
        return Image.new("RGB", (4, 4))

    def place_as_layer(self, img: Image.Image, layer_name: str = "Lattice Dither") -> int:
        if self.grow:
            self.layers = [*(self.layers or []), {"id": 7, "name": layer_name, "kind": "pixel"}]
        return 7


@pytest.mark.parametrize(
    ("layers", "grow", "hide", "step"),
    [
        (None, True, False, 7),
        ([{"id": 7, "name": "Lattice Dither smoke", "kind": "pixel"}], False, False, 8),
        ([{"id": 3, "name": "Background", "kind": "pixel"}], True, True, 5),
        ([{"id": 3, "name": "Background", "kind": "pixel"}], True, False, 0),
    ],
)
def test_smoke_tool_checks_the_new_layer_and_closes_the_document(
    tmp_path, monkeypatch, capsys, layers, grow, hide, step
) -> None:
    """A blind layer check, a count that did not grow and a missing index fail; cleanup runs."""
    module = _load_smoke()
    monkeypatch.setattr(module, "EXCHANGE_DIR", tmp_path)
    monkeypatch.setattr(module, "installed_photocraft_version", lambda: "0.22.0")
    monkeypatch.setattr(module, "version_status", lambda: "tested")
    stub = _SmokeStub(layers, grow, hide)
    monkeypatch.setattr(module.PhotoCraftClient, "discover", staticmethod(lambda *a, **k: stub))
    assert module.main([]) == (0 if step == 0 else 1)
    out = capsys.readouterr().out
    if step == 0:
        assert "OK" in out
        return
    assert f"FAIL at step {step}" in out
    close = {"command": "file.close", "params": {"document": 1, "save": "discard"}}
    assert ("engine.execute", close) in stub.calls


# --------------------------------------------------------------------- ArtCraft generalisation


@pytest.fixture
def exchange(tmp_path, monkeypatch) -> Path:
    """Point the shared exchange directory at a temporary directory."""
    monkeypatch.setattr(photocraft, "EXCHANGE_DIR", tmp_path)
    return tmp_path


def test_a_host_that_hangs_up_is_a_typed_error(exchange: Path) -> None:
    """A host that accepts and closes at once raises BridgeError, never OSError or a hang."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(0.02)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        assert DesignCraftClient.discover(port) is None
        with pytest.raises(BridgeError):
            DesignCraftClient(port).render_document()
    finally:
        stop.set()
        listener.close()
    assert list(exchange.iterdir()) == []


@pytest.mark.manual
@pytest.mark.skipif(
    os.environ.get("LATTICE_BRIDGE_LIVE") != "1",
    reason="set LATTICE_BRIDGE_LIVE=1 to touch a real ArtCraft host",
)
def test_live_hosts_smoke(monkeypatch) -> None:
    """Manual: against a running host, place a layer, render it back and verify the placement."""
    shared = os.environ.get("LATTICE_BRIDGE_EXCHANGE")
    if shared:
        monkeypatch.setattr(photocraft, "EXCHANGE_DIR", Path(shared))
    client = ArtCraftClient.discover("photocraft") or ArtCraftClient.discover("designcraft")
    if client is None:
        pytest.skip("no ArtCraft host is running")
    assert client.ping()
    image = Image.new("RGB", (64, 48), (200, 30, 40))
    try:
        if client.host == "photocraft" and not client.client.documents():
            client.call("engine.execute", {"command": "file.new", "params": {"width": 400}})
        placed = client.place_as_layer(image, "Lattice Dither smoke")
        rendered = client.render_document()
    except BridgeError as exc:
        pytest.skip(f"host is running but not ready for automation: {exc}")
    assert isinstance(placed, int)
    assert rendered.width > 0 and rendered.height > 0
    if client.host == "designcraft":
        inspected = client.call("engine.execute", {"command": "document.inspect"})
        ids = [item["id"] for spread in inspected["spreads"] for item in spread["items"]]
        assert placed in ids
