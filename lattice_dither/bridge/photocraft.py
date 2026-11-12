"""PhotoCraft desktop control-server bridge (CONTRACT §8, §24)."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from PIL import Image

HOST = "127.0.0.1"
CONTROL_PORT = 47600
TESTED_PHOTOCRAFT_VERSION = "0.22.0"
PHOTOCRAFT_CLI = Path(r"C:\Program Files\ArtCraft\PhotoCraft\photocraft-cli.exe")
EXCHANGE_MAX_AGE = 3600.0
VERSION_TIMEOUT = 10.0
_VERSION_RE = re.compile(r"photocraft-cli\s+(\d+\.\d+\.\d+)")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CONTROL_TIMEOUT = 5.0
SAVE_TIMEOUT = 60.0
LARGE_DOCUMENT_SIDE = 4000
DEFAULT_LAYER_NAME = "Lattice Dither"
PREVIEW_LAYER_NAME = "Lattice Dither preview"


def _local_appdata() -> Path:
    """Return %LOCALAPPDATA%, falling back to the default Windows location."""
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Local"


APP_DIR_NAME = "LatticeDither"
LEGACY_APP_DIR_NAME = "DitherCraft"


def _app_dir(name: str) -> Path:
    """Return the per-application directory under %LOCALAPPDATA%."""
    return _local_appdata() / name


def _exchange_dir() -> Path:
    """Return the exchange directory, keeping the legacy one when it already exists."""
    current = _app_dir(APP_DIR_NAME) / "exchange"
    legacy = _app_dir(LEGACY_APP_DIR_NAME) / "exchange"
    if not current.exists() and legacy.exists():
        return legacy
    return current


EXCHANGE_DIR = _exchange_dir()
TOKEN_PATH = _app_dir(APP_DIR_NAME) / "control.token"
LEGACY_TOKEN_PATH = _app_dir(LEGACY_APP_DIR_NAME) / "control.token"


class BridgeError(Exception):
    """Any failure while talking to the PhotoCraft control server."""


class _Channel:
    """Line-delimited JSON channel over one TCP connection."""

    def __init__(self, sock: socket.socket, timeout: float) -> None:
        self._sock = sock
        self._file = sock.makefile("rwb")
        self._next_id = 0
        self.timeout = timeout
        self.broken = False

    def call(self, method: str, params: dict | None = None) -> object:
        """Send one request and return its raw result, raising BridgeError on failure."""
        request: dict = {"id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            request["params"] = params
        try:
            self._file.write(json.dumps(request).encode("utf-8") + b"\n")
            self._file.flush()
            line = self._file.readline()
        except OSError as exc:
            self.broken = True
            raise BridgeError(f"{method}: connection error: {exc}") from exc
        if not line:
            self.broken = True
            raise BridgeError(f"{method}: the server closed the connection")
        try:
            response = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(f"{method}: invalid response: {exc}") from exc
        if not isinstance(response, dict):
            raise BridgeError(f"{method}: invalid response: {response!r}")
        if not response.get("ok"):
            raise BridgeError(str(response.get("error") or f"{method} failed"))
        return response.get("result")

    def set_timeout(self, value: float) -> None:
        """Change the socket timeout for the following calls, ignoring a closed socket."""
        if value == self.timeout:
            return
        self.timeout = value
        try:
            self._sock.settimeout(value)
        except OSError:
            self.broken = True

    def close(self) -> None:
        """Close the buffered file and the socket, ignoring errors."""
        for closer in (self._file.close, self._sock.close):
            try:
                closer()
            except OSError:
                pass


def _cleanup_exchange(max_age: float = EXCHANGE_MAX_AGE) -> None:
    """Delete exchange files older than one hour; ignore a missing directory."""
    try:
        entries = list(EXCHANGE_DIR.iterdir())
    except OSError:
        return
    cutoff = time.time() - max_age
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def _as_dict(value: object, where: str) -> dict:
    """Return a dict result, or raise BridgeError when the server sent something else."""
    if not isinstance(value, dict):
        raise BridgeError(f"{where} returned no result object: {value!r}")
    return value


def _discard(path: Path) -> None:
    """Delete an exchange file, ignoring a Windows sharing violation."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _as_index(value: object, where: str) -> int:
    """Return an integer document or layer index, or raise BridgeError."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise BridgeError(f"{where} returned no usable index: {value!r}")
    return value


def _save_png(img: Image.Image, path: Path) -> None:
    """Write the image as PNG, keeping transparency when the image has any."""
    keep_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    try:
        img.convert("RGBA" if keep_alpha else "RGB").save(path, format="PNG")
    except OSError as exc:
        raise BridgeError(f"cannot write {path.name!r}: {exc}") from exc


def _execute(channel: _Channel, command: str, params: dict | None = None) -> object:
    """Run one engine command on the channel and return its result."""
    payload: dict = {"command": command}
    if params is not None:
        payload["params"] = params
    return channel.call("engine.execute", payload)


class PhotoCraftClient:
    """Client for the PhotoCraft desktop control server on 127.0.0.1:47600."""

    def __init__(self, port: int, token: str, timeout: float = CONTROL_TIMEOUT) -> None:
        self._port = port
        self._token = token
        self._timeout = timeout
        self._lock = threading.Lock()
        self._preview_layer: int | None = None
        self._preview_name = ""

    @staticmethod
    def discover(
        token_path: Path | None = None, port: int = CONTROL_PORT
    ) -> PhotoCraftClient | None:
        """Return an authenticated client, or None when PhotoCraft is not reachable."""
        paths = (TOKEN_PATH, LEGACY_TOKEN_PATH) if token_path is None else (Path(token_path),)
        token = ""
        for path in paths:
            try:
                token = path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                continue
            if token:
                break
        if not token:
            return None
        client = PhotoCraftClient(port, token)
        return client if client.ping() else None

    def ping(self) -> bool:
        """Return True when the server answers an authenticated engine.commands call."""
        try:
            with self._lock:
                _cleanup_exchange()
                with self._session() as channel:
                    channel.call("engine.commands")
        except BridgeError:
            return False
        return True

    def call(self, method: str, params: dict | None = None) -> object:
        """Send one raw request on its own authenticated connection and return its result."""
        with self._lock:
            _cleanup_exchange()
            with self._session() as channel:
                return channel.call(method, params)

    def render_document(self, index: int | None = None) -> Image.Image:
        """Save a document as a flattened PNG and return it as an image."""
        with self._lock:
            _cleanup_exchange()
            name = f"get_{uuid.uuid4().hex}.png"
            path = EXCHANGE_DIR / name
            try:
                with self._session() as channel:
                    if index is None:
                        result = _execute(channel, "document.inspect")
                        self._save(channel, name, result if isinstance(result, dict) else None)
                    else:
                        self._save_indexed(channel, name, index)
                with Image.open(path) as handle:
                    return handle.copy()
            except OSError as exc:
                raise BridgeError(f"cannot read the saved PNG {name!r}: {exc}") from exc
            finally:
                _discard(path)

    def _save(self, channel: _Channel, name: str, document: dict | None) -> None:
        """Call app.save, allowing 60 s when the document is above 4000 px."""
        data = document or {}
        sides = [data.get("width"), data.get("height")]
        big = any(isinstance(side, int) and side > LARGE_DOCUMENT_SIDE for side in sides)
        channel.set_timeout(SAVE_TIMEOUT if big else self._timeout)
        try:
            channel.call("app.save", {"path": name})
        finally:
            channel.set_timeout(self._timeout)

    def _save_indexed(self, channel: _Channel, name: str, index: int) -> None:
        """Save the document at `index`, leaving the previously active document active."""
        active, documents = self._session_info(channel)
        target = next((item for item in documents if item.get("index") == index), None)
        if target is None:
            raise BridgeError(f"no document at index {index}")
        if active != index:
            _execute(channel, "document.activate", {"document": index})
        try:
            self._save(channel, name, target)
        finally:
            if active is not None and active != index:
                try:
                    _execute(channel, "document.activate", {"document": active})
                except BridgeError:
                    pass

    def _session_info(self, channel: _Channel) -> tuple[int | None, list[dict]]:
        """Return the active document index and the document list from ui.inspect."""
        result = _as_dict(channel.call("ui.inspect"), "ui.inspect")
        session = result.get("session")
        documents = session.get("documents") if isinstance(session, dict) else None
        if not isinstance(documents, list):
            raise BridgeError(f"ui.inspect returned no document list: {result!r}")
        active = session.get("active")
        if isinstance(active, bool) or not isinstance(active, int):
            active = None
        return active, [item for item in documents if isinstance(item, dict)]

    def place_as_layer(self, img: Image.Image, layer_name: str | None = None) -> int:
        """Copy the image into the active document as a new layer and return its id."""
        with self._lock:
            _cleanup_exchange()
            return self._place(img, layer_name or DEFAULT_LAYER_NAME)

    def preview_layer(self, rgb8: Image.Image, name: str) -> int:
        """Place the preview layer, or refresh the open one, and return its id."""
        with self._lock:
            _cleanup_exchange()
            if self._preview_layer is None:
                self._preview_layer = self._place(rgb8, PREVIEW_LAYER_NAME)
                self._preview_name = name
                return self._preview_layer
            return self._replace_preview(rgb8)

    def update_preview_layer(self, rgb8: Image.Image) -> int:
        """Replace the content of the open preview layer and return its id."""
        with self._lock:
            _cleanup_exchange()
            if self._preview_layer is None:
                raise BridgeError("no preview layer is open")
            return self._replace_preview(rgb8)

    def commit_preview_layer(self) -> int:
        """Rename the open preview layer to its committed name and forget the handle."""
        with self._lock:
            _cleanup_exchange()
            layer = self._preview_layer
            if layer is None:
                raise BridgeError("no preview layer is open")
            with self._session() as channel:
                _execute(channel, "layer.renameLayer", {"layer": layer, "name": self._preview_name})
            self._preview_layer = None
            return layer

    def documents(self) -> list[dict]:
        """Return the ui.inspect document list."""
        with self._lock:
            _cleanup_exchange()
            with self._session() as channel:
                return self._session_info(channel)[1]

    def disconnect(self) -> None:
        """Forget the preview layer handle; connections are per call, so nothing else is held."""
        with self._lock:
            self._preview_layer = None

    def _place(self, img: Image.Image, layer_name: str) -> int:
        """Run the §8.4 sequence and return the new layer id; the caller holds the lock."""
        name = f"send_{uuid.uuid4().hex}.png"
        path = EXCHANGE_DIR / name
        target: int | None = None
        helper: int | None = None
        with self._session() as channel:
            try:
                result = _as_dict(
                    _execute(channel, "document.activate", {"offset": 0}), "document.activate"
                )
                target = _as_index(result.get("document"), "document.activate")
                _save_png(img, path)
                channel.call("app.open", {"path": name})
                helper = self._find_document(channel, name)
                _execute(
                    channel,
                    "layer.copyToDocument",
                    {"document": target, "center": True, "name": layer_name},
                )
                _execute(channel, "file.close", {"document": helper, "save": "discard"})
                helper = None
                result = _as_dict(_execute(channel, "document.inspect"), "document.inspect")
                return _as_index(result.get("activeLayer"), "document.inspect")
            except BridgeError:
                self._recover(channel, name, helper, target)
                raise
            finally:
                _discard(path)

    def _replace_preview(self, rgb8: Image.Image) -> int:
        """Write the PNG and replace the preview layer's content; the caller holds the lock."""
        layer = self._preview_layer
        if layer is None:
            raise BridgeError("no preview layer is open")
        name = f"preview_{uuid.uuid4().hex}.png"
        path = EXCHANGE_DIR / name
        try:
            _save_png(rgb8, path)
            with self._session() as channel:
                try:
                    _execute(channel, "layer.replaceContent", {"layer": layer, "path": name})
                except BridgeError:
                    if channel.broken:
                        self._preview_layer = None
                    raise
        finally:
            _discard(path)
        return layer

    @contextmanager
    def _session(self) -> Iterator[_Channel]:
        """Open one authenticated connection and close it afterwards."""
        try:
            sock = socket.create_connection((HOST, self._port), timeout=self._timeout)
        except OSError as exc:
            raise BridgeError(
                f"cannot connect to PhotoCraft on {HOST}:{self._port}: {exc}"
            ) from exc
        channel = _Channel(sock, self._timeout)
        try:
            try:
                result = _as_dict(channel.call("auth", {"token": self._token}), "auth")
            except BridgeError:
                if channel.broken:
                    raise
                raise BridgeError("authentication failed") from None
            if not result.get("authenticated"):
                raise BridgeError("authentication failed")
            yield channel
        finally:
            channel.close()

    def _find_document(self, channel: _Channel, name: str) -> int:
        """Return the index of the document whose path or name is `name`."""
        for document in self._session_info(channel)[1]:
            if document.get("path") == name or document.get("name") == name:
                return _as_index(document.get("index"), "ui.inspect")
        raise BridgeError(f"helper document {name!r} not found in the session")

    def _recover(
        self, channel: _Channel, name: str, helper: int | None, target: int | None
    ) -> None:
        """Best-effort cleanup after a failed §8.4 sequence: close the helper, reactivate T."""
        if channel.broken:
            return
        index = helper
        if index is None:
            try:
                index = self._find_document(channel, name)
            except BridgeError:
                index = None
        if index is not None:
            try:
                channel.call(
                    "engine.execute",
                    {"command": "file.close", "params": {"document": index, "save": "discard"}},
                )
            except BridgeError:
                pass
        if target is not None:
            try:
                channel.call(
                    "engine.execute",
                    {"command": "document.activate", "params": {"document": target}},
                )
            except BridgeError:
                pass


def installed_photocraft_version(cli: Path = PHOTOCRAFT_CLI) -> str | None:
    """Return the installed PhotoCraft version, or None when it cannot be determined."""
    executable = Path(cli)
    try:
        if not executable.is_file():
            return None
        completed = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=VERSION_TIMEOUT,
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    match = _VERSION_RE.search(completed.stdout or "")
    return match.group(1) if match else None


def version_status() -> Literal["tested", "untested", "unknown"]:
    """Compare the installed PhotoCraft version with the tested one."""
    installed = installed_photocraft_version()
    if installed is None:
        return "unknown"
    return "tested" if installed == TESTED_PHOTOCRAFT_VERSION else "untested"
