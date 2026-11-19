"""Host-facing slots of the Glitch window, mixed into MainWindow (§7, E9).

Pull adopts the host document as the source; push renders through the CLI's own
function with the session context and places the result. An absent host is a status
line, never a dialog; a real failure is reported. Keeping these slots here leaves the
window file under its size budget without changing the public surface.
"""

from __future__ import annotations

import numpy as np

NO_SOURCE = "Load an image before rendering."


class BridgeMixin:
    """The bridge half of the window: pull, push, status answers and the probe."""

    def get_from_host(self) -> None:
        """Read the active document of the bridge host into this application."""
        self.bridge.pull()

    def send_to_host(self) -> None:
        """Place the current render in the bridge host; an absent host is a status line."""
        if self.source is None:
            self.report(NO_SOURCE)
            return
        self.bridge.push(self.source, self.spec, self.render_context())

    def _on_pulled(self, image: object, host: str) -> None:
        """Adopt a document pulled from a host, which has no source path."""
        self.check_bridge()
        if image is None:
            self.report(f"{host}: no document")
            return
        self.set_source(np.ascontiguousarray(np.asarray(image), np.float32))
        self.status(f"Read the {host} document")

    def _on_pushed(self, object_id: int) -> None:
        """Report a successful placement in the host and re-probe its reachability."""
        self.status(f"Placed object {object_id}")
        self.check_bridge()

    def _on_state(self, state: str) -> None:
        """Show the host reachability in the status bar label."""
        self.connection_label.setText(f"{self.bridge.host}: {state}")

    def check_bridge(self) -> None:
        """Ask the bridge status dot to probe the host now."""
        self.bridge_dot.check()


__all__ = ["BridgeMixin", "NO_SOURCE"]
