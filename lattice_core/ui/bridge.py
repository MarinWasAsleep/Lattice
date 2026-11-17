"""Shared bridge status dot: live ArtCraft reachability as a small widget.

The dot probes ``ArtCraftClient.discover`` on a helper thread so a slow or
refused connection never blocks the GUI. A missing host is a normal state:
every application must work standalone, and the dot simply shows orange.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from lattice_core.bridge import ArtCraftClient
from lattice_core.bridge.designcraft import CONTROL_PORT as DESIGNCRAFT_PORT
from lattice_core.bridge.photocraft import CONTROL_PORT as PHOTOCRAFT_PORT

LOGGER = logging.getLogger(__name__)

CONNECTED = "connected"
DISCONNECTED = "disconnected"
UNKNOWN = "unknown"
STATES: tuple[str, ...] = (CONNECTED, DISCONNECTED, UNKNOWN)
PROBE_JOIN_MS = 250
HOSTS = ("photocraft", "designcraft")
DEFAULT_PORT: dict[str, int | None] = {
    "photocraft": PHOTOCRAFT_PORT,
    "designcraft": DESIGNCRAFT_PORT,
}
_STATE_COLOURS = {
    CONNECTED: QColor(70, 190, 90),
    DISCONNECTED: QColor(210, 70, 70),
    UNKNOWN: QColor(220, 160, 50),
}
_STATE_TIPS = {
    CONNECTED: "Connected",
    DISCONNECTED: "Disconnected",
    UNKNOWN: "Unknown",
}
HostName = Literal["photocraft", "designcraft"]
Discover = Callable[[HostName, int | None], ArtCraftClient | None]


class ConnectionProbe(QObject):
    """Runs one discover() on a helper thread so a slow probe never blocks the GUI."""

    state_changed = Signal(str)

    def __init__(
        self,
        discover: Discover = ArtCraftClient.discover,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._discover = discover
        self._host: HostName = "photocraft"
        self._port: int | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def check(self) -> None:
        """Start one discover() probe unless the previous one is still running."""
        with self._lock:
            if self._stopped or (self._thread is not None and self._thread.is_alive()):
                return
            self._thread = threading.Thread(
                target=self._run, name="artcraft-probe", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop emitting probe results and wait briefly for the running probe."""
        with self._lock:
            self._stopped = True
            thread = self._thread
        if thread is not None:
            thread.join(PROBE_JOIN_MS / 1000.0)

    def _run(self) -> None:
        """Probe the host and emit the resulting connection state."""
        try:
            client = self._discover(self._host, self._port)
        except Exception:  # noqa: BLE001 - a probe must never raise
            LOGGER.exception("ArtCraft discovery failed")
            client = None
        if not self._stopped:
            self.state_changed.emit(CONNECTED if client is not None else DISCONNECTED)

    def set_host(self, host: HostName, port: int | None = None) -> None:
        """Set the host probed by the next check() call."""
        if host not in HOSTS:
            raise ValueError(f"unknown ArtCraft host {host!r}; expected one of {HOSTS}")
        self._host = host
        self._port = DEFAULT_PORT[host] if port is None else port


class BridgeStatusDot(QWidget):
    """A coloured dot showing the reachability of one ArtCraft host."""

    state_changed = Signal(str)

    def __init__(
        self,
        host: HostName = "photocraft",
        parent: QWidget | None = None,
        *,
        port: int | None = None,
        discover: Discover = ArtCraftClient.discover,
        diameter: int = 12,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("bridge_status_dot")
        self._diameter = int(diameter)
        self.setFixedSize(self._diameter, self._diameter)
        self._state = UNKNOWN
        self.probe = ConnectionProbe(discover, self)
        self.probe.set_host(host, port)
        self.probe.state_changed.connect(self.set_state)
        self.probe.state_changed.connect(self.state_changed)
        self._update_tip()

    def host(self) -> str:
        """Return the host this dot probes."""
        return self.probe._host

    def set_host(self, host: HostName, port: int | None = None) -> None:
        """Retarget the dot at another host; the next check() probes it."""
        self.probe.set_host(host, port)
        self.set_state(UNKNOWN)
        self.check()

    def state(self) -> str:
        """Return the current state: connected, disconnected or unknown."""
        return self._state

    def set_state(self, state: str) -> None:
        """Set the displayed state and repaint the dot."""
        if state not in STATES:
            raise ValueError(f"unknown bridge state {state!r}")
        self._state = state
        self._update_tip()
        self.update()

    @Slot()
    def check(self) -> None:
        """Start one asynchronous probe; the dot updates when the probe answers."""
        self.probe.check()

    def start(self) -> None:
        """Probe now; scheduling belongs to the owning application."""
        self.check()

    def stop(self) -> None:
        """Stop the probe thread; safe to call more than once."""
        self.probe.stop()

    def _update_tip(self) -> None:
        """Refresh the tooltip with the state and the probed host."""
        self.setToolTip(f"{_STATE_TIPS[self._state]} ({self.probe._host})")

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the state colour as a filled circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self._diameter / 2.0
        painter.setBrush(_STATE_COLOURS[self._state])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0.0, 0.0, radius * 2.0, radius * 2.0)
        painter.end()
        super().paintEvent(event)


__all__ = ["BridgeStatusDot", "ConnectionProbe", "CONNECTED", "DISCONNECTED", "UNKNOWN"]
