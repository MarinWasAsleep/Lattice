"""Tests for preset browsing and the arrow-key navigation (T14 follow-up)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402

from lattice_dither.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice_dither.core.pipeline import PipelineSpec  # noqa: E402
from lattice_dither.core.presets import to_json  # noqa: E402
from lattice_dither.ui import main_window as mw  # noqa: E402
from lattice_dither.ui import preset_browser as pb  # noqa: E402
from lattice_dither.ui import worker as worker_module  # noqa: E402
from lattice_dither.ui.preset_browser import PresetBrowser  # noqa: E402


class FakeSettings:
    """In-memory stand-in for QSettings so tests never touch the registry."""

    store: dict[str, object] = {}

    def __init__(self, organisation: str, application: str) -> None:
        self._prefix = f"{organisation}/{application}/"

    def value(self, key: str, default: object = None) -> object:
        """Return the stored value of key, or default."""
        return FakeSettings.store.get(self._prefix + key, default)

    def setValue(self, key: str, value: object) -> None:
        """Store value under key."""
        FakeSettings.store[self._prefix + key] = value


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> type[FakeSettings]:
    """Replace QSettings with an in-memory store."""
    FakeSettings.store.clear()
    monkeypatch.setattr(mw, "QSettings", FakeSettings)
    return FakeSettings


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test away from the real PhotoCraft app."""
    monkeypatch.setattr(PhotoCraftClient, "discover", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_module, "version_status", lambda: "tested")
    monkeypatch.setattr(worker_module, "installed_photocraft_version", lambda: None)


def _write_presets(directory: Path, names: list[str]) -> list[Path]:
    """Write one valid preset per name and return the paths in sorted order."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = directory / name
        path.write_text(to_json(PipelineSpec()), encoding="utf-8")
        paths.append(path)
    return sorted(paths)


@pytest.fixture
def preset_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the window's default preset directory at a temporary folder."""
    directory = tmp_path / "presets"
    _write_presets(directory, ["01_a.json", "02_b.json", "03_c.json"])
    monkeypatch.setattr(mw, "PRESET_DIR", directory)
    return directory


@pytest.fixture
def window(qapp: QApplication, settings: type[FakeSettings], bridge: None, preset_dir: Path):
    """Return a shown main window whose preset directory holds three presets."""
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


def _key(key: Qt.Key, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    """Build a key-press event for key."""
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def test_browser_on_an_empty_directory(tmp_path: Path) -> None:
    """An empty directory yields no current preset and a neutral label."""
    browser = PresetBrowser(tmp_path / "absent")
    assert browser.paths == []
    assert browser.current() is None
    assert browser.step(1) is None
    assert browser.label() == "Preset: none"


def test_browser_sorts_and_wraps(preset_dir: Path) -> None:
    """Presets are sorted by name and stepping wraps around both ends."""
    browser = PresetBrowser(preset_dir)
    assert [p.name for p in browser.paths] == ["01_a.json", "02_b.json", "03_c.json"]
    assert browser.current() == preset_dir / "01_a.json"
    assert browser.step(1) == preset_dir / "02_b.json"
    assert browser.step(1) == preset_dir / "03_c.json"
    assert browser.step(1) == preset_dir / "01_a.json"
    assert browser.step(-1) == preset_dir / "03_c.json"


def test_browser_refresh_keeps_the_selection(preset_dir: Path) -> None:
    """A rescan keeps the current preset selected when it still exists."""
    browser = PresetBrowser(preset_dir)
    browser.step(1)
    browser.refresh()
    assert browser.current() == preset_dir / "02_b.json"
    (preset_dir / "02_b.json").unlink()
    browser.refresh()
    assert browser.current() is not None
    assert browser.current().name != "02_b.json"


def test_browser_select_ignores_unknown_paths(preset_dir: Path) -> None:
    """Selecting a path outside the list leaves the position untouched."""
    browser = PresetBrowser(preset_dir)
    browser.select(preset_dir / "nope.json")
    assert browser.current() == preset_dir / "01_a.json"


def test_window_exposes_the_preset_actions(window: mw.MainWindow) -> None:
    """The four preset actions exist and the arrows sit around load and save."""
    for key in ("preset_prev", "load_preset", "save_preset", "preset_next"):
        assert key in window.actions
    texts = [a.text() for a in window.toolbar.actions() if not a.isSeparator()]
    assert texts.index("\u25c0") < texts.index("Load preset") < texts.index("Save preset")
    assert texts.index("Save preset") < texts.index("\u25b6")


def test_label_reports_the_position(window: mw.MainWindow) -> None:
    """The status label names the current preset and its rank."""
    assert window.presets.label.text() == "Preset 1/3: 01_a.json"
    window.presets.step(1)
    assert window.presets.label.text() == "Preset 2/3: 02_b.json"


def test_stepping_loads_the_preset(window: mw.MainWindow, preset_dir: Path) -> None:
    """Stepping adopts the next preset as the current pipeline."""
    window.presets.step(1)
    assert window.presets.browser.current() == preset_dir / "02_b.json"
    assert window.spec.algorithm_id == PipelineSpec().algorithm_id


def test_arrow_keys_step_the_preset(
    window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Left and Right step the preset when the focus is not an arrow consumer."""
    monkeypatch.setattr(pb.QApplication, "focusWidget", staticmethod(lambda: window.canvas))
    monkeypatch.setattr(pb.QApplication, "activeModalWidget", staticmethod(lambda: None))
    assert window.presets.eventFilter(window.canvas, _key(Qt.Key.Key_Right)) is True
    assert window.presets.label.text() == "Preset 2/3: 02_b.json"
    assert window.presets.eventFilter(window.canvas, _key(Qt.Key.Key_Left)) is True
    assert window.presets.label.text() == "Preset 1/3: 01_a.json"


def test_arrows_are_left_alone_in_a_list(
    window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A focused list keeps its own arrow navigation."""
    listing = QListWidget(window)
    monkeypatch.setattr(pb.QApplication, "focusWidget", staticmethod(lambda: listing))
    monkeypatch.setattr(pb.QApplication, "activeModalWidget", staticmethod(lambda: None))
    assert window.presets.eventFilter(listing, _key(Qt.Key.Key_Right)) is False
    assert window.presets.label.text() == "Preset 1/3: 01_a.json"


def test_arrows_need_no_modifier(window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl+Right and friends are not preset navigation."""
    monkeypatch.setattr(pb.QApplication, "focusWidget", staticmethod(lambda: window.canvas))
    monkeypatch.setattr(pb.QApplication, "activeModalWidget", staticmethod(lambda: None))
    event = _key(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert window.presets.eventFilter(window.canvas, event) is False


def test_a_modal_dialog_blocks_the_arrows(
    window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While a modal dialog is open the arrows belong to it."""
    monkeypatch.setattr(pb.QApplication, "focusWidget", staticmethod(lambda: window.canvas))
    monkeypatch.setattr(pb.QApplication, "activeModalWidget", staticmethod(lambda: object()))
    assert window.presets.eventFilter(window.canvas, _key(Qt.Key.Key_Right)) is False


def test_other_keys_are_ignored(window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the two arrow keys are intercepted."""
    monkeypatch.setattr(pb.QApplication, "focusWidget", staticmethod(lambda: window.canvas))
    monkeypatch.setattr(pb.QApplication, "activeModalWidget", staticmethod(lambda: None))
    assert window.presets.eventFilter(window.canvas, _key(Qt.Key.Key_Space)) is False
    release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    assert window.presets.eventFilter(window.canvas, release) is False
