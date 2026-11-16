"""PhotoCraft client, split out of ``lattice_core.bridge.photocraft`` to stay under the
400-line per-file limit.

Module-level names are resolved through the parent module at call time
(``_photocraft.NAME``) so that runtime monkeypatching of
``lattice_core.bridge.photocraft`` attributes — which the bridge tests rely
on — keeps working exactly as in the single-module layout.
"""

from __future__ import annotations

import socket
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from lattice_core.bridge import photocraft as _photocraft


class PhotoCraftClient:
    """Client for the PhotoCraft desktop control server on 127.0.0.1:47600."""

    def __init__(self, port: int, token: str, timeout: float = _photocraft.CONTROL_TIMEOUT) -> None:
        self._port = port
        self._token = token
        self._timeout = timeout
        self._lock = threading.Lock()
        self._preview_layer: int | None = None
        self._preview_name = ""

    @staticmethod
    def discover(
        token_path: Path | None = None, port: int = _photocraft.CONTROL_PORT
    ) -> PhotoCraftClient | None:
        """Return an authenticated client, or None when PhotoCraft is not reachable."""
        paths = (
            (_photocraft.TOKEN_PATH, _photocraft.LEGACY_TOKEN_PATH)
            if token_path is None
            else (Path(token_path),)
        )
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
                _photocraft._cleanup_exchange()
                with self._session() as channel:
                    channel.call("engine.commands")
        except _photocraft.BridgeError:
            return False
        return True

    def call(self, method: str, params: dict | None = None) -> object:
        """Send one raw request on its own authenticated connection and return its result."""
        with self._lock:
            _photocraft._cleanup_exchange()
            with self._session() as channel:
                return channel.call(method, params)

    def render_document(self, index: int | None = None) -> Image.Image:
        """Save a document as a flattened PNG and return it as an image."""
        with self._lock:
            _photocraft._cleanup_exchange()
            name = f"get_{uuid.uuid4().hex}.png"
            path = _photocraft.EXCHANGE_DIR / name
            try:
                with self._session() as channel:
                    if index is None:
                        result = _photocraft._execute(channel, "document.inspect")
                        self._save(channel, name, result if isinstance(result, dict) else None)
                    else:
                        self._save_indexed(channel, name, index)
                with Image.open(path) as handle:
                    return handle.copy()
            except OSError as exc:
                raise _photocraft.BridgeError(f"cannot read the saved PNG {name!r}: {exc}") from exc
            finally:
                _photocraft._discard(path)

    def _save(self, channel: _photocraft._Channel, name: str, document: dict | None) -> None:
        """Call app.save, allowing 60 s when the document is above 4000 px."""
        data = document or {}
        sides = [data.get("width"), data.get("height")]
        big = any(
            isinstance(side, int) and side > _photocraft.LARGE_DOCUMENT_SIDE for side in sides
        )
        channel.set_timeout(_photocraft.SAVE_TIMEOUT if big else self._timeout)
        try:
            channel.call("app.save", {"path": name})
        finally:
            channel.set_timeout(self._timeout)

    def _save_indexed(self, channel: _photocraft._Channel, name: str, index: int) -> None:
        """Save the document at `index`, leaving the previously active document active."""
        active, documents = self._session_info(channel)
        target = next((item for item in documents if item.get("index") == index), None)
        if target is None:
            raise _photocraft.BridgeError(f"no document at index {index}")
        if active != index:
            _photocraft._execute(channel, "document.activate", {"document": index})
        try:
            self._save(channel, name, target)
        finally:
            if active is not None and active != index:
                try:
                    _photocraft._execute(channel, "document.activate", {"document": active})
                except _photocraft.BridgeError:
                    pass

    def _session_info(self, channel: _photocraft._Channel) -> tuple[int | None, list[dict]]:
        """Return the active document index and the document list from ui.inspect."""
        result = _photocraft._as_dict(channel.call("ui.inspect"), "ui.inspect")
        session = result.get("session")
        documents = session.get("documents") if isinstance(session, dict) else None
        if not isinstance(documents, list):
            raise _photocraft.BridgeError(f"ui.inspect returned no document list: {result!r}")
        active = session.get("active")
        if isinstance(active, bool) or not isinstance(active, int):
            active = None
        return active, [item for item in documents if isinstance(item, dict)]

    def place_as_layer(self, img: Image.Image, layer_name: str | None = None) -> int:
        """Copy the image into the active document as a new layer and return its id."""
        with self._lock:
            _photocraft._cleanup_exchange()
            return self._place(img, layer_name or _photocraft.DEFAULT_LAYER_NAME)

    def preview_layer(self, rgb8: Image.Image, name: str) -> int:
        """Place the preview layer, or refresh the open one, and return its id."""
        with self._lock:
            _photocraft._cleanup_exchange()
            if self._preview_layer is None:
                self._preview_layer = self._place(rgb8, _photocraft.PREVIEW_LAYER_NAME)
                self._preview_name = name
                return self._preview_layer
            return self._replace_preview(rgb8)

    def update_preview_layer(self, rgb8: Image.Image) -> int:
        """Replace the content of the open preview layer and return its id."""
        with self._lock:
            _photocraft._cleanup_exchange()
            if self._preview_layer is None:
                raise _photocraft.BridgeError("no preview layer is open")
            return self._replace_preview(rgb8)

    def commit_preview_layer(self) -> int:
        """Rename the open preview layer to its committed name and forget the handle."""
        with self._lock:
            _photocraft._cleanup_exchange()
            layer = self._preview_layer
            if layer is None:
                raise _photocraft.BridgeError("no preview layer is open")
            with self._session() as channel:
                _photocraft._execute(
                    channel, "layer.renameLayer", {"layer": layer, "name": self._preview_name}
                )
            self._preview_layer = None
            return layer

    def documents(self) -> list[dict]:
        """Return the ui.inspect document list."""
        with self._lock:
            _photocraft._cleanup_exchange()
            with self._session() as channel:
                return self._session_info(channel)[1]

    def disconnect(self) -> None:
        """Forget the preview layer handle; connections are per call, so nothing else is held."""
        with self._lock:
            self._preview_layer = None

    def _place(self, img: Image.Image, layer_name: str) -> int:
        """Run the §8.4 sequence and return the new layer id; the caller holds the lock."""
        name = f"send_{uuid.uuid4().hex}.png"
        path = _photocraft.EXCHANGE_DIR / name
        target: int | None = None
        helper: int | None = None
        with self._session() as channel:
            try:
                result = _photocraft._as_dict(
                    _photocraft._execute(channel, "document.activate", {"offset": 0}),
                    "document.activate",
                )
                target = _photocraft._as_index(result.get("document"), "document.activate")
                _photocraft._save_png(img, path)
                channel.call("app.open", {"path": name})
                helper = self._find_document(channel, name)
                _photocraft._execute(
                    channel,
                    "layer.copyToDocument",
                    {"document": target, "center": True, "name": layer_name},
                )
                _photocraft._execute(channel, "file.close", {"document": helper, "save": "discard"})
                helper = None
                result = _photocraft._as_dict(
                    _photocraft._execute(channel, "document.inspect"), "document.inspect"
                )
                return _photocraft._as_index(result.get("activeLayer"), "document.inspect")
            except _photocraft.BridgeError:
                self._recover(channel, name, helper, target)
                raise
            finally:
                _photocraft._discard(path)

    def _replace_preview(self, rgb8: Image.Image) -> int:
        """Write the PNG and replace the preview layer's content; the caller holds the lock."""
        layer = self._preview_layer
        if layer is None:
            raise _photocraft.BridgeError("no preview layer is open")
        name = f"preview_{uuid.uuid4().hex}.png"
        path = _photocraft.EXCHANGE_DIR / name
        try:
            _photocraft._save_png(rgb8, path)
            with self._session() as channel:
                try:
                    _photocraft._execute(
                        channel, "layer.replaceContent", {"layer": layer, "path": name}
                    )
                except _photocraft.BridgeError:
                    if channel.broken:
                        self._preview_layer = None
                    raise
        finally:
            _photocraft._discard(path)
        return layer

    @contextmanager
    def _session(self) -> Iterator[_photocraft._Channel]:
        """Open one authenticated connection and close it afterwards."""
        try:
            sock = socket.create_connection((_photocraft.HOST, self._port), timeout=self._timeout)
        except OSError as exc:
            raise _photocraft.BridgeError(
                f"cannot connect to PhotoCraft on {_photocraft.HOST}:{self._port}: {exc}"
            ) from exc
        channel = _photocraft._Channel(sock, self._timeout)
        try:
            try:
                result = _photocraft._as_dict(channel.call("auth", {"token": self._token}), "auth")
            except _photocraft.BridgeError:
                if channel.broken:
                    raise
                raise _photocraft.BridgeError("authentication failed") from None
            if not result.get("authenticated"):
                raise _photocraft.BridgeError("authentication failed")
            yield channel
        finally:
            channel.close()

    def _find_document(self, channel: _photocraft._Channel, name: str) -> int:
        """Return the index of the document whose path or name is `name`."""
        for document in self._session_info(channel)[1]:
            if document.get("path") == name or document.get("name") == name:
                return _photocraft._as_index(document.get("index"), "ui.inspect")
        raise _photocraft.BridgeError(f"helper document {name!r} not found in the session")

    def _recover(
        self, channel: _photocraft._Channel, name: str, helper: int | None, target: int | None
    ) -> None:
        """Best-effort cleanup after a failed §8.4 sequence: close the helper, reactivate T."""
        if channel.broken:
            return
        index = helper
        if index is None:
            try:
                index = self._find_document(channel, name)
            except _photocraft.BridgeError:
                index = None
        if index is not None:
            try:
                channel.call(
                    "engine.execute",
                    {"command": "file.close", "params": {"document": index, "save": "discard"}},
                )
            except _photocraft.BridgeError:
                pass
        if target is not None:
            try:
                channel.call(
                    "engine.execute",
                    {"command": "document.activate", "params": {"document": target}},
                )
            except _photocraft.BridgeError:
                pass


