"""Tests for the ArtCraft bridge (CONTRACT §7): PhotoCraft and DesignCraft adapters.

Every test runs against an in-process fake server, so the suite needs no host.
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from lattice.bridge import ArtCraftClient, photocraft
from lattice.bridge.designcraft import DesignCraftClient
from lattice.bridge.photocraft import BridgeError, PhotoCraftClient

TOKEN = "a" * 64
ROOT = Path(__file__).resolve().parents[1]


def _ok(request: dict, result: object = None) -> dict:
    """Build a successful response."""
    return {"id": request["id"], "ok": True, "result": {} if result is None else result}


def _error(request: dict, message: str) -> dict:
    """Build a failed response."""
    return {"id": request["id"], "ok": False, "error": message}


def _send(conn: socket.socket, payload: dict) -> None:
    """Write one JSON line to the connection."""
    conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")


class FakeDesktopServer:
    """In-process fake of the PhotoCraft desktop control server."""

    def __init__(self, handler, token: str | None = TOKEN) -> None:
        self.token, self.handler = token, handler
        self.connections: list[list[dict]] = []
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._listener.settimeout(0.02)
        self.port = self._listener.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def requests(self) -> list[dict]:
        """Every request received, in arrival order."""
        return [request for connection in self.connections for request in connection]

    def wait_for_requests(self, count: int = 1, timeout: float = 2.0) -> list[dict]:
        """Block until count requests are recorded, so a client that gave up early is not raced."""
        deadline = time.monotonic() + timeout
        while len(self.requests) < count and time.monotonic() < deadline:
            time.sleep(0.005)
        return self.requests

    def close(self) -> None:
        """Stop the accept loop and release the listening socket."""
        self._stop.set()
        self._listener.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        record: list[dict] = []
        self.connections.append(record)
        reader = conn.makefile("rwb")
        try:
            while line := reader.readline():
                request = json.loads(line.decode("utf-8"))
                record.append(request)
                if len(record) == 1 and self.token is not None:
                    params = request.get("params") or {}
                    if request.get("method") != "auth" or params.get("token") != self.token:
                        refusal = {"id": request.get("id"), "ok": False}
                        _send(conn, refusal | {"error": "authentication required"})
                        return
                    granted = {"id": request.get("id"), "ok": True}
                    _send(conn, granted | {"result": {"authenticated": True}})
                    continue
                response = self.handler(request)
                if response is None:
                    return
                _send(conn, response)
        except (OSError, json.JSONDecodeError):
            return
        finally:
            reader.close()


@pytest.fixture
def exchange(tmp_path, monkeypatch) -> Path:
    """Point EXCHANGE_DIR at a temporary directory."""
    monkeypatch.setattr(photocraft, "EXCHANGE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def server():
    """Factory fixture that starts fake servers and closes them after the test."""
    started: list[FakeDesktopServer] = []

    def start(handler, token: str = TOKEN) -> FakeDesktopServer:
        fake = FakeDesktopServer(handler, token)
        started.append(fake)
        return fake

    yield start
    for fake in started:
        fake.close()


def _token_file(tmp_path: Path, content: str = TOKEN) -> Path:
    """Write a control token file and return its path."""
    path = tmp_path / "control.token"
    path.write_text(content, encoding="utf-8")
    return path


def test_discover_returns_none(tmp_path: Path, exchange: Path, server, monkeypatch) -> None:
    """A missing file, an empty file, a refused port and a bad token all yield no client."""
    assert PhotoCraftClient.discover(token_path=tmp_path / "absent.token") is None
    assert PhotoCraftClient.discover(token_path=_token_file(tmp_path, "  \n")) is None

    def refuse(*args, **kwargs):
        raise ConnectionRefusedError(10061, "connection refused")

    with monkeypatch.context() as patch:
        patch.setattr(photocraft.socket, "create_connection", refuse)
        assert PhotoCraftClient.discover(token_path=_token_file(tmp_path), port=47999) is None
    fake = server(lambda request: _ok(request), token="b" * 64)
    assert PhotoCraftClient.discover(token_path=_token_file(tmp_path), port=fake.port) is None
    assert [r["method"] for r in fake.wait_for_requests(1)] == ["auth"]


def test_discover_never_reads_instance_json(
    tmp_path: Path, exchange: Path, server, monkeypatch
) -> None:
    """discover reads the token file only, never the single-instance IPC file."""
    fake = server(lambda request: _ok(request))
    read: list[str] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        read.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    path = _token_file(tmp_path)
    assert PhotoCraftClient.discover(token_path=path, port=fake.port) is not None
    assert read == [str(path)]


def test_every_connection_authenticates_first(exchange: Path, server) -> None:
    """Each public call opens one connection whose first request is auth with id 0."""
    fake = server(lambda request: _ok(request, {"commands": [1, 2]}))
    client = PhotoCraftClient(fake.port, TOKEN)
    assert client.call("engine.commands") == {"commands": [1, 2]}
    assert client.ping()
    assert client.ping()
    assert len(fake.connections) == 3
    for connection in fake.connections:
        assert connection[0]["method"] == "auth"
        assert connection[0]["id"] == 0
        assert connection[0]["params"] == {"token": TOKEN}
        assert [request["id"] for request in connection] == list(range(len(connection)))


def test_list_result_survives_the_channel(exchange: Path, server) -> None:
    """engine.commands answers with a list of 1005 entries; the channel must not discard it."""
    commands = [{"id": f"cmd.{index}", "label": str(index)} for index in range(1005)]
    fake = server(lambda request: _ok(request, commands))
    client = PhotoCraftClient(fake.port, TOKEN)
    assert client.call("engine.commands") == commands
    assert client.ping()


def test_render_document_saves_reads_and_deletes(exchange: Path, server) -> None:
    """render_document saves a relative '/'-separated PNG, reads it and deletes it."""

    def handler(request: dict) -> dict:
        if request["method"] == "engine.execute":
            return _ok(request, {"activeLayer": 10})
        if request["method"] == "app.save":
            Image.new("RGB", (5, 3), (10, 20, 30)).save(exchange / request["params"]["path"])
            return _ok(request, {"warnings": []})
        return _error(request, f"unexpected {request['method']}")

    fake = server(handler)
    image = PhotoCraftClient(fake.port, TOKEN).render_document()
    assert image.size == (5, 3)
    assert image.getpixel((0, 0)) == (10, 20, 30)
    assert list(exchange.iterdir()) == []
    assert [r["method"] for r in fake.requests] == ["auth", "engine.execute", "app.save"]
    name = fake.requests[2]["params"]["path"]
    assert name.startswith("get_") and name.endswith(".png")
    assert "\\" not in name and not Path(name).is_absolute()
    failing = server(lambda request: _error(request, "no document open"))
    with pytest.raises(BridgeError, match="no document open"):
        PhotoCraftClient(failing.port, TOKEN).render_document()
    assert [r["method"] for r in failing.requests] == ["auth", "engine.execute"]


class PlaceHandler:
    """Scripted §8.4 responder that records the helper document lifecycle."""

    def __init__(self, exchange: Path, fail_at: str | None = None) -> None:
        self.exchange = exchange
        self.fail_at = fail_at
        self.saved_name: str | None = None
        self.png_present_at_open = False

    def __call__(self, request: dict) -> dict:
        method = request["method"]
        params = request.get("params") or {}
        command = params.get("command")
        if method == "app.open":
            if self.fail_at == "open":
                return _error(request, "open refused")
            self.saved_name = params["path"]
            self.png_present_at_open = (self.exchange / self.saved_name).is_file()
            return _ok(request, {"name": self.saved_name, "path": self.saved_name})
        if method == "ui.inspect":
            documents = [{"index": 0, "name": "a.png", "path": "a.png"},
                         {"index": 1, "name": "target.png", "path": "target.png"}]
            if self.saved_name:
                documents.append({"index": 2, "name": self.saved_name, "path": self.saved_name})
            return _ok(request, {"session": {"active": 1, "documents": documents}})
        if command == "layer.copyToDocument" and self.fail_at == "copy":
            return _error(request, "copy failed")
        canned = {
            "document.activate": {"document": 1},
            "layer.copyToDocument": {"document": 1, "layers": [24], "offset": [0, 0]},
            "file.close": {},
            "document.inspect": {"activeLayer": 24},
        }
        if command in canned:
            return _ok(request, canned[command])
        return _error(request, f"unexpected {method}")


def _sequence(fake: FakeDesktopServer) -> list[tuple[str, str | None]]:
    """Summarise the requests after auth as (method, command) pairs."""
    return [
        (request["method"], (request.get("params") or {}).get("command"))
        for request in fake.requests[1:]
    ]


def test_place_as_layer_follows_step_order(exchange: Path, server) -> None:
    """place_as_layer issues the §8.4 requests in the documented order."""
    handler = PlaceHandler(exchange)
    fake = server(handler)
    layer_id = PhotoCraftClient(fake.port, TOKEN).place_as_layer(
        Image.new("RGB", (4, 4), (1, 2, 3)), "Lattice Dither"
    )
    assert layer_id == 24
    assert _sequence(fake) == [
        ("engine.execute", "document.activate"), ("app.open", None), ("ui.inspect", None),
        ("engine.execute", "layer.copyToDocument"), ("engine.execute", "file.close"),
        ("engine.execute", "document.inspect"),
    ]
    activate, opened, _, copy, close, _ = fake.requests[1:]
    assert activate["params"]["params"] == {"offset": 0}
    assert copy["params"]["params"] == {"document": 1, "center": True, "name": "Lattice Dither"}
    assert close["params"]["params"] == {"document": 2, "save": "discard"}
    assert handler.png_present_at_open
    assert "\\" not in opened["params"]["path"]
    assert list(exchange.iterdir()) == []


@pytest.mark.parametrize(
    ("fail_at", "message"), [("copy", "copy failed"), ("open", "open refused")]
)
def test_place_as_layer_failure_cleans_up(
    exchange: Path, server, fail_at: str, message: str
) -> None:
    """A failure after step 1 closes the helper when it exists and reactivates the target."""
    fake = server(PlaceHandler(exchange, fail_at=fail_at))
    with pytest.raises(BridgeError, match=message):
        PhotoCraftClient(fake.port, TOKEN).place_as_layer(Image.new("RGB", (4, 4)))
    tail = _sequence(fake)[2:]
    assert ("engine.execute", "document.activate") in tail
    if fail_at == "copy":
        assert tail[-2:] == [
            ("engine.execute", "file.close"),
            ("engine.execute", "document.activate"),
        ]
        assert fake.requests[-2]["params"]["params"] == {"document": 2, "save": "discard"}
        assert fake.requests[-1]["params"]["params"] == {"document": 1}
    else:
        assert ("engine.execute", "file.close") not in _sequence(fake)
    assert list(exchange.iterdir()) == []


def test_locked_png_does_not_mask_success(exchange: Path, server, monkeypatch) -> None:
    """A PermissionError while deleting the exchange PNG must not turn a success into a failure."""

    def locked(self, *args, **kwargs):
        raise PermissionError(32, "The process cannot access the file")

    def saving(request: dict) -> dict:
        if request["method"] == "engine.execute":
            return _ok(request, {"activeLayer": 10})
        Image.new("RGB", (5, 3), (10, 20, 30)).save(exchange / request["params"]["path"])
        return _ok(request)

    monkeypatch.setattr(Path, "unlink", locked)
    placing = server(PlaceHandler(exchange))
    assert PhotoCraftClient(placing.port, TOKEN).place_as_layer(Image.new("RGB", (4, 4))) == 24
    assert PhotoCraftClient(server(saving).port, TOKEN).render_document().size == (5, 3)


def test_old_exchange_files_are_cleaned(exchange: Path, server) -> None:
    """Files older than one hour are deleted at each call, fresh ones are kept."""

    def handler(request: dict) -> dict:
        if request["method"] == "engine.execute":
            return _ok(request, {"activeLayer": 1})
        Image.new("RGB", (2, 2)).save(exchange / request["params"]["path"])
        return _ok(request)

    stale = exchange / "stale.png"
    stale.write_bytes(b"x")
    os.utime(stale, (time.time() - 7200.0,) * 2)
    fresh = exchange / "fresh.png"
    fresh.write_bytes(b"x")
    fake = server(handler)
    PhotoCraftClient(fake.port, TOKEN).render_document()
    assert not stale.exists()
    assert fresh.exists()


def test_timeout_raises_bridge_error(exchange: Path, server) -> None:
    """A server that never answers makes the call fail with BridgeError."""

    def handler(request: dict) -> dict:
        time.sleep(0.4)
        return _ok(request, {"activeLayer": 1})

    fake = server(handler)
    with pytest.raises(BridgeError):
        PhotoCraftClient(fake.port, TOKEN, timeout=0.1).render_document()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [("ok", "0.22.0"), ("missing", None), ("nonzero", None), ("timeout", None), ("bad", None)],
)
def test_installed_version(tmp_path: Path, monkeypatch, outcome: str, expected: str | None) -> None:
    """The CLI banner is parsed, and every failure mode returns None instead of raising."""
    cli = tmp_path / "photocraft-cli.exe"
    if outcome != "missing":
        cli.write_bytes(b"")
    calls: list[dict] = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, 10)
        if outcome == "nonzero":
            return subprocess.CompletedProcess(args, 3, "", "boom")
        if outcome == "bad":
            return subprocess.CompletedProcess(args, 0, "something else entirely", "")
        return subprocess.CompletedProcess(
            args, 0, "photocraft-cli 0.22.0 (5000240c6, 2026-11-09)\n", ""
        )

    monkeypatch.setattr(photocraft.subprocess, "run", fake_run)
    assert photocraft.installed_photocraft_version(cli) == expected
    if outcome == "ok":
        assert calls[0]["args"] == [str(cli), "--version"]
        assert calls[0]["timeout"] == 10
        assert calls[0]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.parametrize(
    ("installed", "expected"),
    [("0.22.0", "tested"), ("0.23.1", "untested"), (None, "unknown")],
)
def test_version_status(monkeypatch, installed: str | None, expected: str) -> None:
    """version_status maps the installed version onto the three contract states."""
    monkeypatch.setattr(photocraft, "installed_photocraft_version", lambda cli=None: installed)
    assert photocraft.version_status() == expected


class PreviewHandler:
    """Scripted responder that tracks the layers of one document."""

    def __init__(self, exchange: Path) -> None:
        self.exchange = exchange
        self.layers: list[dict] = []
        self.saved_name: str | None = None
        self.fail_replace = False
        self._next_id = 24

    def __call__(self, request: dict) -> dict | None:
        method = request["method"]
        params = request.get("params") or {}
        command = params.get("command")
        if method == "app.open":
            self.saved_name = params["path"]
            return _ok(request, {"name": self.saved_name, "path": self.saved_name})
        if method == "ui.inspect":
            documents = [{"index": 0, "name": "target.png", "path": "target.png"}]
            if self.saved_name:
                documents.append({"index": 1, "name": self.saved_name, "path": self.saved_name})
            return _ok(request, {"session": {"active": 0, "documents": documents}})
        if command == "layer.copyToDocument":
            self.layers.append({"id": self._next_id, "name": params["params"]["name"]})
            self._next_id += 1
            new = self.layers[-1]["id"]
            return _ok(request, {"document": 0, "layers": [new], "offset": [0, 0]})
        if command == "layer.replaceContent":
            if self.fail_replace:
                return None
            layer = self._layer(params["params"]["layer"])
            if layer is None:
                return _error(request, "no such layer")
            layer["content"] = params["params"]["path"]
            return _ok(request, {"layer": layer["id"]})
        if command == "layer.renameLayer":
            layer = self._layer(params["params"]["layer"])
            if layer is None:
                return _error(request, "no such layer")
            layer["name"] = params["params"]["name"]
            return _ok(request, {"layer": layer["id"]})
        canned = {
            "document.activate": {"document": 0},
            "file.close": {},
            "document.inspect": {"activeLayer": self.layers[-1]["id"] if self.layers else 0},
        }
        if command in canned:
            return _ok(request, canned[command])
        return _error(request, f"unexpected {method}")

    def _layer(self, layer_id: int) -> dict | None:
        """Return the tracked layer with this id, or None."""
        return next((layer for layer in self.layers if layer["id"] == layer_id), None)


def _commands(fake: FakeDesktopServer) -> list[str | None]:
    """Return the engine command of every request after the first auth."""
    return [command for _, command in _sequence(fake)]


def test_place_as_layer_name_is_optional(exchange: Path, server) -> None:
    """The layer name defaults to "Lattice Dither" and None means that default."""
    fake = server(PlaceHandler(exchange))
    client = PhotoCraftClient(fake.port, TOKEN)
    image = Image.new("RGB", (4, 4), (1, 2, 3))
    assert client.place_as_layer(image) == 24
    assert client.place_as_layer(image, None) == 24
    assert client.place_as_layer(image, "Preset A") == 24
    names = [
        request["params"]["params"]["name"]
        for request in fake.requests
        if (request.get("params") or {}).get("command") == "layer.copyToDocument"
    ]
    assert names == ["Lattice Dither", "Lattice Dither", "Preset A"]


def test_preview_layer_replaces_instead_of_stacking(exchange: Path, server) -> None:
    """Two previews and an update keep one layer: one copy, two content replacements."""
    handler = PreviewHandler(exchange)
    fake = server(handler)
    client = PhotoCraftClient(fake.port, TOKEN)
    image = Image.new("RGB", (4, 4), (1, 2, 3))
    assert client.preview_layer(image, "Preset A") == 24
    assert client.preview_layer(image, "Preset A") == 24
    assert client.update_preview_layer(image) == 24
    commands = _commands(fake)
    assert commands.count("layer.copyToDocument") == 1
    assert commands.count("layer.replaceContent") == 2
    assert [layer["id"] for layer in handler.layers] == [24]
    assert handler.layers[0]["name"] != "Preset A"
    assert list(exchange.iterdir()) == []


def test_commit_preview_layer_renames_and_forgets(exchange: Path, server) -> None:
    """commit renames the layer to the preset name and the next preview stacks a new one."""
    handler = PreviewHandler(exchange)
    fake = server(handler)
    client = PhotoCraftClient(fake.port, TOKEN)
    image = Image.new("RGB", (4, 4), (1, 2, 3))
    assert client.preview_layer(image, "Preset A") == 24
    assert client.commit_preview_layer() == 24
    assert handler.layers[0]["name"] == "Preset A"
    renames = [
        request["params"]["params"]
        for request in fake.requests
        if (request.get("params") or {}).get("command") == "layer.renameLayer"
    ]
    assert renames == [{"layer": 24, "name": "Preset A"}]
    with pytest.raises(BridgeError, match="no preview layer"):
        client.update_preview_layer(image)
    assert client.preview_layer(image, "Preset B") == 25
    assert [layer["id"] for layer in handler.layers] == [24, 25]
    assert _commands(fake).count("layer.copyToDocument") == 2


def test_preview_handle_is_per_client(exchange: Path, server) -> None:
    """Two clients do not share the preview handle."""
    handler = PreviewHandler(exchange)
    fake = server(handler)
    image = Image.new("RGB", (4, 4))
    first = PhotoCraftClient(fake.port, TOKEN)
    second = PhotoCraftClient(fake.port, TOKEN)
    assert first.preview_layer(image, "Preset A") == 24
    with pytest.raises(BridgeError, match="no preview layer"):
        second.update_preview_layer(image)
    assert second.preview_layer(image, "Preset B") == 25
    assert [layer["id"] for layer in handler.layers] == [24, 25]


def test_disconnect_clears_the_preview_handle(exchange: Path, server) -> None:
    """A disconnect forgets the preview layer, so the next update refuses instead of guessing."""
    handler = PreviewHandler(exchange)
    fake = server(handler)
    client = PhotoCraftClient(fake.port, TOKEN)
    image = Image.new("RGB", (4, 4))
    assert client.preview_layer(image, "Preset A") == 24
    client.disconnect()
    with pytest.raises(BridgeError, match="no preview layer"):
        client.update_preview_layer(image)
    assert "layer.replaceContent" not in _commands(fake)
    assert client.preview_layer(image, "Preset A") == 25
    assert [layer["id"] for layer in handler.layers] == [24, 25]


def test_a_broken_connection_clears_the_preview_handle(exchange: Path, server) -> None:
    """When the connection dies during an update, the stale handle is dropped."""
    handler = PreviewHandler(exchange)
    fake = server(handler)
    client = PhotoCraftClient(fake.port, TOKEN)
    image = Image.new("RGB", (4, 4))
    assert client.preview_layer(image, "Preset A") == 24
    handler.fail_replace = True
    with pytest.raises(BridgeError, match="closed the connection"):
        client.update_preview_layer(image)
    handler.fail_replace = False
    with pytest.raises(BridgeError, match="no preview layer"):
        client.update_preview_layer(image)


def test_documents_returns_the_inspect_list(exchange: Path, server) -> None:
    """documents() returns the ui.inspect document list unchanged."""
    documents = [
        {"index": 0, "name": "a.png", "path": "a.png", "dirty": False, "width": 10, "height": 20},
        {"index": 1, "name": "b.png", "path": "b.png", "dirty": True, "width": 30, "height": 40},
    ]
    fake = server(lambda request: _ok(request, {"session": {"active": 1, "documents": documents}}))
    assert PhotoCraftClient(fake.port, TOKEN).documents() == documents
    assert [request["method"] for request in fake.requests] == ["auth", "ui.inspect"]


def test_render_document_pulls_the_requested_document(exchange: Path, server) -> None:
    """render_document(1) activates the second document, saves it and restores the first."""
    documents = [
        {"index": 0, "name": "a.png", "path": "a.png", "width": 8, "height": 8},
        {"index": 1, "name": "b.png", "path": "b.png", "width": 5, "height": 3},
    ]
    state = {"active": 0}

    def handler(request: dict) -> dict:
        params = request.get("params") or {}
        command = params.get("command")
        if request["method"] == "ui.inspect":
            return _ok(request, {"session": {"active": state["active"], "documents": documents}})
        if command == "document.activate":
            state["active"] = params["params"]["document"]
            return _ok(request, {"document": state["active"]})
        if request["method"] == "app.save":
            size, colour = ((5, 3), (200, 10, 10)) if state["active"] else ((8, 8), (10, 10, 200))
            Image.new("RGB", size, colour).save(exchange / params["path"])
            return _ok(request, {"warnings": []})
        return _error(request, f"unexpected {request['method']}")

    fake = server(handler)
    image = PhotoCraftClient(fake.port, TOKEN).render_document(1)
    assert image.size == (5, 3)
    assert image.getpixel((0, 0)) == (200, 10, 10)
    assert state["active"] == 0
    assert _sequence(fake) == [
        ("ui.inspect", None),
        ("engine.execute", "document.activate"),
        ("app.save", None),
        ("engine.execute", "document.activate"),
    ]
    assert fake.requests[2]["params"]["params"] == {"document": 1}
    assert fake.requests[4]["params"]["params"] == {"document": 0}
    assert list(exchange.iterdir()) == []


def test_control_calls_use_the_five_second_timeout(exchange: Path, server, monkeypatch) -> None:
    """Every connection is opened with the 5 s control timeout unless the caller overrides it."""
    recorded: list[float | None] = []
    original = socket.create_connection

    def spy(address, timeout=None, **kwargs):
        recorded.append(timeout)
        return original(address, timeout=timeout, **kwargs)

    monkeypatch.setattr(photocraft.socket, "create_connection", spy)
    fake = server(lambda request: _ok(request, {"session": {"active": 0, "documents": []}}))
    PhotoCraftClient(fake.port, TOKEN).documents()
    PhotoCraftClient(fake.port, TOKEN, timeout=0.5).documents()
    assert recorded == [5.0, 0.5]


def test_save_timeout_is_sixty_seconds_for_large_documents(
    exchange: Path, server, monkeypatch
) -> None:
    """app.save gets 60 s above 4000 px, keeps the control timeout below it, and restores it."""
    values: list[float] = []
    original = socket.socket.settimeout

    def spy(self, value):
        values.append(value)
        return original(self, value)

    monkeypatch.setattr(socket.socket, "settimeout", spy)

    def handler(size: tuple[int, int]):
        def respond(request: dict) -> dict:
            if request["method"] == "engine.execute":
                return _ok(request, {"activeLayer": 1, "width": size[0], "height": size[1]})
            Image.new("RGB", (2, 2)).save(exchange / request["params"]["path"])
            return _ok(request)

        return respond

    big = server(handler((4001, 100)))
    PhotoCraftClient(big.port, TOKEN).render_document()
    assert values.count(60.0) == 1
    assert values[-1] == 5.0

    values.clear()
    small = server(handler((4000, 100)))
    PhotoCraftClient(small.port, TOKEN).render_document()
    assert 60.0 not in values

# --------------------------------------------------------------------------- DesignCraft


def _png_b64(size: tuple[int, int], colour: tuple[int, int, int]) -> str:
    """Return a base64 PNG of that size and colour, as file.exportBatch sends it."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


PAGE = [0.0, 0.0, 595.0, 842.0]


def _inspect(
    selection: list[int] | None = None,
    items: list[dict] | None = None,
    page: list[float] | None = None,
) -> dict:
    """Build a document.inspect result with one page and the given objects."""
    return {
        "selection": {"content": False, "items": selection or []},
        "spreads": [
            {"index": 0, "pages": [{"bounds": page or PAGE}], "items": items or []},
        ],
    }


class DesignCraftHandler:
    """Scripted DesignCraft responder: inspect, file.place and file.exportBatch."""

    def __init__(self, exchange: Path, page: list[float] | None = None, fail: str | None = None,
                 unreadable: bool = False, inspect: dict | None = None) -> None:
        self.exchange = exchange
        self.page = page or PAGE
        self.fail = fail
        self.unreadable = unreadable
        self.inspect = inspect if inspect is not None else _inspect(page=self.page)
        self.placed: list[dict] = []
        self.png_present_at_place = False
        self._next_id = 40

    def __call__(self, request: dict) -> dict:
        params = request.get("params") or {}
        command = params.get("command")
        if params.get("command") is None and request["method"] == "engine.commands":
            return _ok(request, [{"id": "file.place"}])
        if self.fail == command:
            return _error(request, f"{command} failed")
        if command == "document.inspect":
            return _ok(request, self.inspect)
        if command == "file.place":
            payload = params["params"]
            if self.unreadable and "path" in payload:
                return _error(request, f"{payload['path']}: No such file or directory")
            self.png_present_at_place = "path" in payload and Path(payload["path"]).is_file()
            self.placed.append(payload)
            self._next_id += 1
            return _ok(request, {"asset": 7, "id": self._next_id})
        if command == "file.exportBatch":
            width = int(round(self.page[2] - self.page[0]))
            height = int(round(self.page[3] - self.page[1]))
            return _ok(request, {"files": [{"base64": _png_b64((width, height), (12, 34, 56))}]})
        return _error(request, f"unexpected {request['method']}")


@pytest.fixture
def designcraft_server(server):
    """Start an unauthenticated fake DesignCraft server: its channel has no token."""

    def start(handler) -> FakeDesktopServer:
        return server(handler, token=None)

    return start


def test_artcraft_discover_photocraft_needs_a_token(
    tmp_path: Path, exchange: Path, server, monkeypatch
) -> None:
    """discover("photocraft") is None without a token file and live when the host answers."""
    monkeypatch.setattr(photocraft, "TOKEN_PATH", tmp_path / "absent.token")
    monkeypatch.setattr(photocraft, "LEGACY_TOKEN_PATH", tmp_path / "absent-legacy.token")
    assert ArtCraftClient.discover("photocraft", port=47998) is None
    fake = server(lambda request: _ok(request, []))
    monkeypatch.setattr(photocraft, "TOKEN_PATH", _token_file(tmp_path))
    assert ArtCraftClient.discover("photocraft", port=47998) is None
    found = ArtCraftClient.discover("photocraft", port=fake.port)
    assert found is not None and found.host == "photocraft"
    assert found.ping()
    assert [request["method"] for request in fake.requests] == ["auth", "engine.commands"] * 2


def test_artcraft_photocraft_facade_places_a_layer(exchange: Path, server, monkeypatch,
                                                   tmp_path: Path) -> None:
    """The facade reaches PhotoCraft's own §8.4 sequence unchanged."""
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    monkeypatch.setattr(photocraft, "TOKEN_PATH", _token_file(tokens))
    places = PlaceHandler(exchange)

    def handler(request: dict) -> dict:
        if request["method"] == "engine.commands":
            return _ok(request, [{"id": "document.inspect"}])
        return places(request)

    fake = server(handler)
    client = ArtCraftClient.discover("photocraft", port=fake.port)
    assert client is not None
    assert client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither") == 24
    assert _sequence(fake)[2:4] == [
        ("engine.execute", "document.activate"), ("app.open", None),
    ]
    assert not list(exchange.glob("*.png"))


def test_artcraft_discover_designcraft_needs_no_token(exchange: Path, designcraft_server) -> None:
    """discover("designcraft") is None when the port is closed and live when it answers."""
    assert ArtCraftClient.discover("designcraft", port=47997) is None
    fake = designcraft_server(lambda request: _ok(request, [{"id": "file.place"}]))
    found = ArtCraftClient.discover("designcraft", port=fake.port)
    assert found is not None and found.host == "designcraft"
    assert found.ping()
    assert [request["method"] for request in fake.requests] == ["engine.commands"] * 2


def test_artcraft_discover_rejects_an_unknown_host() -> None:
    """A host name outside the two adapters is a programming error, not a bridge failure."""
    with pytest.raises(ValueError, match="unknown ArtCraft host"):
        ArtCraftClient.discover("pdfcraft")


def test_designcraft_render_document_matches_the_inspected_page(
    exchange: Path, designcraft_server
) -> None:
    """render_document exports the page at 72 ppi and returns its pixels."""
    handler = DesignCraftHandler(exchange, page=[0.0, 0.0, 300.0, 200.0])
    fake = designcraft_server(handler)
    image = DesignCraftClient(fake.port).render_document()
    assert image.size == (300, 200)
    assert image.getpixel((0, 0)) == (12, 34, 56)
    export = [request for request in fake.requests
              if (request.get("params") or {}).get("command") == "file.exportBatch"]
    assert export[0]["params"]["params"]["job"]["versions"][0]["ppi"] == 72
    assert "dir" not in export[0]["params"]["params"]
    assert list(exchange.iterdir()) == []


def test_designcraft_place_creates_a_frame_when_nothing_is_selected(
    exchange: Path, designcraft_server
) -> None:
    """With no selection, file.place gets {path, x, y, width} taken from the page."""
    handler = DesignCraftHandler(exchange)
    fake = designcraft_server(handler)
    placed = DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither")
    assert isinstance(placed, int) and placed == 41
    assert handler.placed == [
        {"x": 0.0, "y": 0.0, "width": 595.0, "name": "Lattice Dither",
         "path": handler.placed[0]["path"]}
    ]
    assert handler.png_present_at_place
    assert Path(handler.placed[0]["path"]).parent == exchange
    assert list(exchange.iterdir()) == []


def test_designcraft_place_uses_the_selected_frame(exchange: Path, designcraft_server) -> None:
    """A selected frame is passed as `frame`, and a selected image is not a frame."""
    inspect = _inspect(selection=[12], items=[{"id": 12, "kind": "<rectangle>"},
                                             {"id": 9, "kind": "<image>"}])
    handler = DesignCraftHandler(exchange, inspect=inspect)
    fake = designcraft_server(handler)
    DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "in frame")
    assert handler.placed[0]["frame"] == 12
    assert "x" not in handler.placed[0] and "width" not in handler.placed[0]

    image_only = _inspect(selection=[9], items=[{"id": 9, "kind": "<image>"}])
    other = DesignCraftHandler(exchange, inspect=image_only)
    DesignCraftClient(designcraft_server(other).port).place_as_layer(Image.new("RGB", (4, 4)), "x")
    assert "frame" not in other.placed[0]
    assert other.placed[0]["width"] == 595.0


def test_designcraft_place_falls_back_to_base64(exchange: Path, designcraft_server) -> None:
    """A host that cannot read the exchange path gets the same PNG as base64."""
    handler = DesignCraftHandler(exchange, unreadable=True)
    fake = designcraft_server(handler)
    assert DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "b64") == 41
    assert len(handler.placed) == 1
    payload = handler.placed[0]
    assert "path" not in payload and payload["name"] == "b64"
    assert Image.open(io.BytesIO(base64.b64decode(payload["base64"]))).size == (4, 4)
    assert list(exchange.iterdir()) == []


@pytest.mark.parametrize("command", ["file.place", "file.exportBatch", "document.inspect"])
def test_designcraft_failures_are_typed_and_leave_no_file(
    exchange: Path, designcraft_server, command: str
) -> None:
    """A refused command raises BridgeError and the exchange directory stays empty."""
    handler = DesignCraftHandler(exchange, fail=command)
    client = DesignCraftClient(designcraft_server(handler).port)
    with pytest.raises(BridgeError, match=f"{command} failed"):
        if command == "file.exportBatch":
            client.render_document()
        else:
            client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither")
    assert list(exchange.iterdir()) == []


def test_designcraft_does_not_retry_a_broken_connection(
    exchange: Path, designcraft_server
) -> None:
    """A dead connection is not retried as base64: the failure is reported once."""
    calls: list[str] = []

    def handler(request: dict) -> dict | None:
        command = (request.get("params") or {}).get("command")
        calls.append(command or request["method"])
        if command == "document.inspect":
            return _ok(request, _inspect())
        return None

    fake = designcraft_server(handler)
    with pytest.raises(BridgeError, match="closed the connection"):
        DesignCraftClient(fake.port).place_as_layer(Image.new("RGB", (4, 4)), "x")
    assert calls.count("file.place") == 1
    assert list(exchange.iterdir()) == []


def test_designcraft_timeout_raises_bridge_error(exchange: Path, designcraft_server) -> None:
    """A host that never answers makes the call fail with BridgeError, not hang."""
    def handler(request: dict) -> dict:
        time.sleep(0.4)
        return _ok(request, _inspect())

    with pytest.raises(BridgeError):
        DesignCraftClient(designcraft_server(handler).port, timeout=0.1).render_document()


def test_designcraft_discards_old_exchange_files(exchange: Path, designcraft_server) -> None:
    """Files older than one hour are deleted on the next call, fresh ones are kept."""
    stale = exchange / "stale.png"
    stale.write_bytes(b"x")
    os.utime(stale, (time.time() - 7200.0,) * 2)
    fresh = exchange / "fresh.png"
    fresh.write_bytes(b"x")
    fake = designcraft_server(DesignCraftHandler(exchange))
    DesignCraftClient(fake.port).render_document()
    assert not stale.exists()
    assert fresh.exists()


def test_designcraft_rejects_a_result_without_a_file(exchange: Path, designcraft_server) -> None:
    """A file.exportBatch result with no PNG is a BridgeError, never an AttributeError."""
    fake = designcraft_server(lambda request: _ok(request, {"files": []}))
    with pytest.raises(BridgeError, match="returned no file"):
        DesignCraftClient(fake.port).render_document()


def test_exchange_dir_follows_the_platform_app_data_directory(monkeypatch, tmp_path: Path) -> None:
    """§7: %LOCALAPPDATA%/<App> on Windows, ~/.local/share/<App> on Linux."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "win"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(photocraft, "_IS_WINDOWS", True)
    assert photocraft._app_dir("LatticeDither") == tmp_path / "win" / "LatticeDither"
    monkeypatch.setattr(photocraft, "_IS_WINDOWS", False)
    monkeypatch.setattr(photocraft.sys, "platform", "linux")
    assert photocraft._app_dir("LatticeDither") == tmp_path / "xdg" / "LatticeDither"
    monkeypatch.delenv("XDG_DATA_HOME")
    expected = Path.home() / ".local" / "share" / "LatticeDither"
    assert photocraft._app_dir("LatticeDither") == expected


def test_artcraft_client_delegates_to_the_adapter(exchange: Path, designcraft_server) -> None:
    """The facade forwards ping, call, render_document, place_as_layer and disconnect."""
    handler = DesignCraftHandler(exchange)
    fake = designcraft_server(handler)
    client = ArtCraftClient.discover("designcraft", port=fake.port)
    assert client is not None
    assert client.ping()
    assert client.call("engine.commands") == [{"id": "file.place"}]
    assert client.render_document().size == (595, 842)
    assert client.place_as_layer(Image.new("RGB", (4, 4)), "Lattice Dither") == 41
    client.disconnect()
    assert list(exchange.iterdir()) == []
