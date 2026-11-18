"""L-UI2: the shared core RenderWorker bridge verbs and PaletteExtraction.

These tests import only ``lattice_core`` (never an application), so they also
prove the shared worker is usable standalone under ``lattice-core[ui]``. They
cover the verbs the Dither copy used to own: ``request_send``, ``request_get``,
``check_version``, ``check_connection`` and the threaded ``PaletteExtraction``.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lattice_core.dither  # noqa: E402,F401  (registers every algorithm)
import lattice_core.effects  # noqa: E402,F401  (registers every effect)
from lattice_core.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice_core.palettes.extract import extract_palette  # noqa: E402
from lattice_core.palettes.io import hex_list  # noqa: E402
from lattice_core.pipeline import PipelineSpec, render  # noqa: E402
from lattice_core.ui import worker as worker_module  # noqa: E402
from lattice_core.ui.worker import PaletteExtraction, RenderWorker  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def _ramp(height: int, width: int) -> np.ndarray:
    """Return a deterministic float32 grey ramp of the given shape."""
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:, :, :] = ramp[None, :, None]
    return image


def _pump(cond, timeout_ms: int = 8000) -> None:
    """Process Qt events until cond() is true or the deadline passes."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while not cond() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert cond(), "the asynchronous worker never reached the expected state"


class FakeClient:
    """Stand-in for PhotoCraftClient recording the layers it receives."""

    def __init__(self) -> None:
        self.placed: list[tuple[PILImage.Image, str]] = []

    def place_as_layer(self, img: PILImage.Image, name: str) -> int:
        """Record the image and return a fixed layer id."""
        self.placed.append((img, name))
        return 7

    def render_document(self) -> PILImage.Image:
        """Return a small solid image as the visible document."""
        return PILImage.new("RGB", (32, 24), (10, 20, 30))


def test_default_worker_renders_only_and_has_no_probe(qapp: QApplication) -> None:
    """Without bridge=True the worker exposes no probe, so other apps are unaffected."""
    worker = RenderWorker()
    assert worker.probe is None
    worker.start()
    assert worker._connection is None
    worker.set_source(_ramp(8, 8))
    assert worker.source() is not None


def test_request_send_places_one_full_resolution_layer(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send renders at full resolution and places exactly one PNG as a layer."""
    client = FakeClient()
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *a, **k: client)
    worker = RenderWorker(bridge=True)
    sent: list[int] = []
    worker.send_finished.connect(sent.append)
    source = _ramp(48, 64)
    worker.set_source(source)
    spec = PipelineSpec()
    worker.request_send(spec)
    assert sent == [7]
    assert len(client.placed) == 1
    image, name = client.placed[0]
    assert name == "Lattice Dither"
    assert image.size == (64, 48)
    assert np.array_equal(np.asarray(image), render(source, spec))
    worker.stop_probing()


def test_request_send_without_a_client_reports_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused PhotoCraft is a normal state: the worker reports, never raises."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *a, **k: None)
    worker = RenderWorker(bridge=True)
    errors: list[str] = []
    worker.failed.connect(errors.append)
    worker.set_source(_ramp(8, 8))
    worker.request_send(PipelineSpec())
    assert len(errors) == 1
    assert "PhotoCraft" in errors[0]
    worker.stop_probing()


def test_request_get_emits_the_document_as_float32(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Get adopts the visible PhotoCraft document and emits it as a float32 image."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *a, **k: FakeClient())
    worker = RenderWorker(bridge=True)
    got: list[np.ndarray] = []
    worker.image_ready.connect(got.append)
    worker.request_get()
    assert len(got) == 1
    assert got[0].shape == (24, 32, 3)
    assert got[0].dtype == np.float32
    worker.stop_probing()


def test_check_version_emits_untested_with_the_installed_version(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The version verb reports the status and, when untested, the installed version."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "untested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: "0.23.0")
    worker = RenderWorker(bridge=True)
    seen: list[tuple[str, object]] = []
    worker.version_status_ready.connect(lambda status, installed: seen.append((status, installed)))
    worker.check_version()
    assert seen == [("untested", "0.23.0")]
    worker.stop_probing()


def test_check_version_unknown_reports_no_installed(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown status carries no installed version."""
    monkeypatch.setattr(worker_module, "version_status", lambda: "unknown")
    worker = RenderWorker(bridge=True)
    seen: list[tuple[str, object]] = []
    worker.version_status_ready.connect(lambda status, installed: seen.append((status, installed)))
    worker.check_version()
    assert seen == [("unknown", None)]
    worker.stop_probing()


def test_check_connection_reports_connected_then_disconnected(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connection probe forwards discover()'s reachability as a state signal."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *a, **k: object())
    worker = RenderWorker(bridge=True)
    states: list[str] = []
    worker.connection_state.connect(states.append)
    worker.check_connection()
    _pump(lambda: states)
    assert states[-1] == "connected"
    worker.stop_probing()


def test_palette_extraction_emits_hex_colours_off_the_gui_thread(qapp: QApplication) -> None:
    """PaletteExtraction runs on a helper thread and reports the extracted hex list."""
    image = np.zeros((16, 16, 3), dtype=np.float32)
    image[:8, :8] = (1.0, 0.0, 0.0)
    image[:8, 8:] = (0.0, 1.0, 0.0)
    image[8:, :8] = (0.0, 0.0, 1.0)
    image[8:, 8:] = (1.0, 1.0, 0.0)
    job = PaletteExtraction(image, 4, "kmeans")
    done: list[object] = []
    job.finished.connect(done.append)
    job.start()
    _pump(lambda: done)
    assert done[0] == hex_list(extract_palette(image, 4, "kmeans"))
    _pump(lambda: job not in worker_module._ACTIVE_EXTRACTIONS)


def test_palette_extraction_reports_a_bad_method(qapp: QApplication) -> None:
    """An invalid extraction reports the error through failed, never raises."""
    image = np.zeros((8, 8, 3), dtype=np.float32)
    job = PaletteExtraction(image, 4, "no_such_method")
    errors: list[str] = []
    job.failed.connect(errors.append)
    job.start()
    _pump(lambda: errors)
    assert len(errors) == 1
    _pump(lambda: job not in worker_module._ACTIVE_EXTRACTIONS)
