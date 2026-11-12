"""Tests for the PhotoCraft bridge (CONTRACT §8), against an in-process fake server."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from lattice_dither.bridge import photocraft
from lattice_dither.bridge.photocraft import BridgeError, PhotoCraftClient

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

    def __init__(self, handler, token: str = TOKEN) -> None:
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
                if len(record) == 1:
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
