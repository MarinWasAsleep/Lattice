"""PhotoCraft desktop control-server bridge (CONTRACT §8, §24)."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
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

from lattice_core.bridge._client import PhotoCraftClient  # noqa: E402, F401
