"""PhotoCraft desktop control-server bridge (CONTRACT §8)."""

from __future__ import annotations

import ctypes
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
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _local_appdata() -> Path:
    """Return %LOCALAPPDATA%, falling back to the default Windows location."""
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Local"


EXCHANGE_DIR = _local_appdata() / "DitherCraft" / "exchange"
TOKEN_PATH = _local_appdata() / "DitherCraft" / "control.token"


class BridgeError(Exception):
    """Any failure while talking to the PhotoCraft control server."""


class _Channel:
    """Line-delimited JSON channel over one TCP connection."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._file = sock.makefile("rwb")
        self._next_id = 0
        self.broken = False

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send one request and return its result, raising BridgeError on failure."""
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
        result = response.get("result")
        return result if isinstance(result, dict) else {}

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


class PhotoCraftClient:
    """Client for the PhotoCraft desktop control server on 127.0.0.1:47600."""

    def __init__(self, port: int, token: str, timeout: float = 10.0) -> None:
        self._port = port
        self._token = token
        self._timeout = timeout
        self._lock = threading.Lock()

    @staticmethod
    def discover(
        token_path: Path | None = None, port: int = CONTROL_PORT
    ) -> PhotoCraftClient | None:
        """Return an authenticated client, or None when PhotoCraft is not reachable."""
        path = TOKEN_PATH if token_path is None else Path(token_path)
        try:
            token = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return None
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

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send one raw request on its own authenticated connection and return the result."""
        with self._lock:
            _cleanup_exchange()
            with self._session() as channel:
                return channel.call(method, params)

    def render_document(self) -> Image.Image:
        """Save the active document as a flattened PNG and return it as an image."""
        with self._lock:
            _cleanup_exchange()
            name = f"get_{uuid.uuid4().hex}.png"
            path = EXCHANGE_DIR / name
            try:
                with self._session() as channel:
                    channel.call("engine.execute", {"command": "document.inspect"})
                    channel.call("app.save", {"path": name})
                with Image.open(path) as handle:
                    return handle.copy()
            except OSError as exc:
                raise BridgeError(f"cannot read the saved PNG {name!r}: {exc}") from exc
            finally:
                path.unlink(missing_ok=True)

    def place_as_layer(self, img: Image.Image, layer_name: str = "DitherCraft") -> int:
        """Copy the image into the active document as a new layer and return its id."""
        with self._lock:
            _cleanup_exchange()
            name = f"send_{uuid.uuid4().hex}.png"
            path = EXCHANGE_DIR / name
            target: int | None = None
            helper: int | None = None
            with self._session() as channel:
                try:
                    result = channel.call(
                        "engine.execute",
                        {"command": "document.activate", "params": {"offset": 0}},
                    )
                    target = _as_index(result.get("document"), "document.activate")
                    _save_png(img, path)
                    channel.call("app.open", {"path": name})
                    helper = self._find_document(channel, name)
                    channel.call(
                        "engine.execute",
                        {
                            "command": "layer.copyToDocument",
                            "params": {"document": target, "center": True, "name": layer_name},
                        },
                    )
                    channel.call(
                        "engine.execute",
                        {
                            "command": "file.close",
                            "params": {"document": helper, "save": "discard"},
                        },
                    )
                    helper = None
                    result = channel.call("engine.execute", {"command": "document.inspect"})
                    return _as_index(result.get("activeLayer"), "document.inspect")
                except BridgeError:
                    self._recover(channel, name, helper, target)
                    raise
                finally:
                    path.unlink(missing_ok=True)

    @contextmanager
    def _session(self) -> Iterator[_Channel]:
        """Open one authenticated connection and close it afterwards."""
        try:
            sock = socket.create_connection((HOST, self._port), timeout=self._timeout)
        except OSError as exc:
            raise BridgeError(
                f"cannot connect to PhotoCraft on {HOST}:{self._port}: {exc}"
            ) from exc
        channel = _Channel(sock)
        try:
            try:
                result = channel.call("auth", {"token": self._token})
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
        result = channel.call("ui.inspect")
        session = result.get("session") or {}
        for document in session.get("documents") or []:
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


def _kernel32() -> object | None:
    """Return the kernel32 DLL handle, or None when ctypes cannot load it."""
    if not hasattr(ctypes, "WinDLL"):
        return None
    try:
        return ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return None


def is_process_alive(pid: int) -> bool:
    """Return True when the process with this pid is still running."""
    if pid <= 0:
        return False
    kernel32 = _kernel32()
    if kernel32 is None:
        return False
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


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
