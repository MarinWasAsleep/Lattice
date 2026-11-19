"""DesignCraft desktop control-server bridge (CONTRACT §7).

DesignCraft 0.20.1 answers JSON lines on 127.0.0.1:7979 and has no token: its
channel refuses ``auth`` as an unknown method, so a session is a plain
connection and ``engine.commands`` is the liveness probe. The wire helpers are
PhotoCraft's, reused so both hosts fail with the same ``BridgeError``.

A Flatpak host reads only ``xdg-documents``/``xdg-pictures``, never the
per-application exchange directory, so ``file.place`` is tried with the
contract's ``path`` form and retried with the documented ``base64`` form when
the host answers that it cannot read the path. ``render_document`` uses
``file.exportBatch``, which returns the PNG inline as base64 when it gets no
``dir``, so no exchange file is written at all.
"""

from __future__ import annotations

import base64
import binascii
import io
import socket
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from lattice.bridge import photocraft as _photocraft

HOST = "127.0.0.1"
CONTROL_PORT = 7979
CONTROL_TIMEOUT = 5.0
EXPORT_TIMEOUT = 60.0
EXPORT_PPI = 72
DEFAULT_LAYER_NAME = "Lattice Dither"
IMAGE_KIND = "<image>"
UNREADABLE = "No such file or directory"
BridgeError = _photocraft.BridgeError


def _png_bytes(img: Image.Image) -> bytes:
    """Return the image as PNG bytes, keeping transparency when the image has any."""
    keep_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    buffer = io.BytesIO()
    try:
        img.convert("RGBA" if keep_alpha else "RGB").save(buffer, format="PNG")
    except OSError as exc:
        raise BridgeError(f"cannot encode the image as PNG: {exc}") from exc
    return buffer.getvalue()


class DesignCraftClient:
    """Client for the DesignCraft desktop control server on 127.0.0.1:7979."""

    def __init__(self, port: int = CONTROL_PORT, timeout: float = CONTROL_TIMEOUT) -> None:
        self._port = port
        self._timeout = timeout
        self._lock = threading.Lock()

    @property
    def port(self) -> int:
        """Return the control port this client talks to."""
        return self._port

    @staticmethod
    def discover(port: int = CONTROL_PORT) -> DesignCraftClient | None:
        """Return a live client, or None when DesignCraft is not reachable."""
        client = DesignCraftClient(port)
        return client if client.ping() else None

    def ping(self) -> bool:
        """Return True when the server answers an engine.commands call."""
        try:
            with self._lock:
                _photocraft._cleanup_exchange()
                with self._session() as channel:
                    channel.call("engine.commands")
        except BridgeError:
            return False
        return True

    def call(self, method: str, params: dict | None = None) -> object:
        """Send one raw request on its own connection and return its result."""
        with self._lock:
            _photocraft._cleanup_exchange()
            with self._session() as channel:
                return channel.call(method, params)

    def disconnect(self) -> None:
        """Hold nothing: connections are per call, so this only drops the handle."""
        return None

    def render_document(self) -> Image.Image:
        """Export the first page as a 72 ppi PNG and return it as an image."""
        with self._lock:
            _photocraft._cleanup_exchange()
            params = {
                "job": {
                    "versions": [
                        {"name": f"get_{uuid.uuid4().hex}", "format": "png", "ppi": EXPORT_PPI}
                    ]
                }
            }
            with self._session() as channel:
                channel.set_timeout(EXPORT_TIMEOUT)
                try:
                    result = _photocraft._as_dict(
                        _photocraft._execute(channel, "file.exportBatch", params),
                        "file.exportBatch",
                    )
                finally:
                    channel.set_timeout(self._timeout)
            return self._decode(result)

    def place_as_layer(self, img: Image.Image, name: str = DEFAULT_LAYER_NAME) -> int:
        """Place the image into the selected frame or a new one and return its id."""
        with self._lock:
            _photocraft._cleanup_exchange()
            png = _png_bytes(img)
            path = self._write(png)
            try:
                with self._session() as channel:
                    base = self._place_params(channel, name)
                    return self._place(channel, base | {"path": str(path)}, png)
            finally:
                _photocraft._discard(path)

    def _place(self, channel: _photocraft._Channel, params: dict, png: bytes) -> int:
        """Run file.place, retrying with base64 when the host cannot read the path."""
        try:
            result = _photocraft._as_dict(
                _photocraft._execute(channel, "file.place", params), "file.place"
            )
        except BridgeError as exc:
            if UNREADABLE not in str(exc) or channel.broken:
                raise
            fallback = {key: value for key, value in params.items() if key != "path"}
            fallback |= {"base64": base64.b64encode(png).decode("ascii")}
            result = _photocraft._as_dict(
                _photocraft._execute(channel, "file.place", fallback), "file.place"
            )
        return _photocraft._as_index(result.get("id"), "file.place")

    def _write(self, png: bytes) -> Path:
        """Write the PNG into the exchange directory and return its path."""
        directory = _photocraft.EXCHANGE_DIR
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BridgeError(f"cannot create the exchange directory: {exc}") from exc
        path = directory / f"send_{uuid.uuid4().hex}.png"
        try:
            path.write_bytes(png)
        except OSError as exc:
            raise BridgeError(f"cannot write {path.name!r}: {exc}") from exc
        return path

    @staticmethod
    def _decode(result: dict) -> Image.Image:
        """Return the exported PNG carried by a file.exportBatch result."""
        files = result.get("files")
        first = files[0] if isinstance(files, list) and files else None
        first = first if isinstance(first, dict) else {}
        for encoded in (first.get("base64"), result.get("base64")):
            if isinstance(encoded, str) and encoded:
                try:
                    with Image.open(io.BytesIO(base64.b64decode(encoded))) as handle:
                        return handle.copy()
                except (binascii.Error, OSError, ValueError) as exc:
                    raise BridgeError(f"cannot read the exported PNG: {exc}") from exc
        path = first.get("path")
        if not isinstance(path, str):
            raise BridgeError(f"file.exportBatch returned no file: {result!r}")
        try:
            with Image.open(path) as handle:
                return handle.copy()
        except OSError as exc:
            raise BridgeError(f"cannot read the exported PNG {path!r}: {exc}") from exc

    def _place_params(self, channel: _photocraft._Channel, name: str) -> dict:
        """Return file.place parameters: into the selected frame, or into a new one."""
        result = _photocraft._as_dict(
            _photocraft._execute(channel, "document.inspect"), "document.inspect"
        )
        kinds = self._item_kinds(result)
        frame = next(
            (item for item in self._selected_ids(result) if kinds.get(item) != IMAGE_KIND), None
        )
        if frame is not None:
            params: dict = {"frame": frame}
        else:
            left, top, right, _bottom = self._page_bounds(result)
            params = {"x": left, "y": top, "width": right - left}
        if name:
            params["name"] = name
        return params

    @staticmethod
    def _selected_ids(result: dict) -> list[int]:
        """Return the selected object ids of a document.inspect result."""
        selection = result.get("selection")
        items = selection.get("items") if isinstance(selection, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, int) and not isinstance(item, bool)]

    @staticmethod
    def _item_kinds(result: dict) -> dict[int, str]:
        """Return the kind of every object of a document.inspect result, by id."""
        kinds: dict[int, str] = {}
        for spread in result.get("spreads") or []:
            items = spread.get("items") if isinstance(spread, dict) else None
            for item in items or []:
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    kinds[item["id"]] = str(item.get("kind"))
        return kinds

    @staticmethod
    def _page_bounds(result: dict) -> list[float]:
        """Return [left, top, right, bottom] of the first page, or raise BridgeError."""
        for spread in result.get("spreads") or []:
            pages = spread.get("pages") if isinstance(spread, dict) else None
            for page in pages or []:
                bounds = page.get("bounds") if isinstance(page, dict) else None
                if isinstance(bounds, list) and len(bounds) == 4:
                    if all(isinstance(value, (int, float)) for value in bounds):
                        return [float(value) for value in bounds]
        raise BridgeError("document.inspect returned no page bounds")

    @contextmanager
    def _session(self) -> Iterator[_photocraft._Channel]:
        """Open one control connection; DesignCraft's channel carries no token."""
        try:
            sock = socket.create_connection((HOST, self._port), timeout=self._timeout)
        except OSError as exc:
            raise BridgeError(
                f"cannot connect to DesignCraft on {HOST}:{self._port}: {exc}"
            ) from exc
        channel = _photocraft._Channel(sock, self._timeout)
        try:
            yield channel
        finally:
            channel.close()
