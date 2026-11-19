"""ArtCraft bridge: one client, one adapter per host (CONTRACT §7).

``ArtCraftClient`` is the single entry point an application uses. It delegates
to ``photocraft.PhotoCraftClient`` or ``designcraft.DesignCraftClient``; both
raise the same ``BridgeError`` and both return ``None`` from ``discover`` when
their host is not running, so an application always works standalone.

    client = ArtCraftClient.discover("photocraft")
    if client is not None:
        client.place_as_layer(image, "Lattice Dither")
"""

from __future__ import annotations

from typing import Literal, Protocol, cast

from PIL import Image

from lattice.bridge import designcraft as _designcraft
from lattice.bridge import photocraft as _photocraft
from lattice.bridge._client import PhotoCraftClient
from lattice.bridge.designcraft import DesignCraftClient
from lattice.bridge.photocraft import BridgeError

__all__ = [
    "ArtCraftClient",
    "BridgeError",
    "DesignCraftClient",
    "HOSTS",
    "PhotoCraftClient",
]

HOSTS = ("photocraft", "designcraft")
HostName = Literal["photocraft", "designcraft"]
DEFAULT_LAYER_NAME = "Lattice Dither"


class _Adapter(Protocol):
    """The part of a host adapter ``ArtCraftClient`` relies on."""

    def ping(self) -> bool: ...

    def call(self, method: str, params: dict | None = None) -> object: ...

    def render_document(self) -> Image.Image: ...

    def place_as_layer(self, img: Image.Image, name: str) -> int: ...

    def disconnect(self) -> None: ...


class ArtCraftClient:
    """One ArtCraft host, reached through the adapter that speaks to it."""

    def __init__(self, host: HostName, client: _Adapter) -> None:
        self._host = host
        self._client = client

    @property
    def host(self) -> HostName:
        """Return the host name this client talks to."""
        return self._host

    @property
    def client(self) -> _Adapter:
        """Return the host adapter underneath, for host-specific calls."""
        return self._client

    @staticmethod
    def discover(host: HostName, port: int | None = None) -> ArtCraftClient | None:
        """Return a live client for `host`, or None when that host is not reachable."""
        if host == "photocraft":
            found = PhotoCraftClient.discover(
                port=_photocraft.CONTROL_PORT if port is None else port
            )
        elif host == "designcraft":
            found = DesignCraftClient.discover(
                port=_designcraft.CONTROL_PORT if port is None else port
            )
        else:
            raise ValueError(f"unknown ArtCraft host {host!r}; expected one of {HOSTS}")
        return None if found is None else ArtCraftClient(host, cast(_Adapter, found))

    def ping(self) -> bool:
        """Return True when the host answers its liveness probe."""
        return bool(self._client.ping())

    def render_document(self) -> Image.Image:
        """Return the active document of the host as an image."""
        return self._client.render_document()

    def place_as_layer(self, img: Image.Image, name: str = DEFAULT_LAYER_NAME) -> int:
        """Place the image in the host as a layer or placed object and return its id."""
        return int(self._client.place_as_layer(img, name))

    def call(self, method: str, params: dict | None = None) -> object:
        """Send one raw request to the host and return its result."""
        return self._client.call(method, params)

    def disconnect(self) -> None:
        """Drop whatever the adapter holds; connections are per call."""
        self._client.disconnect()
