"""Tests for preset browsing, the two preset tiers and the arrow keys (T14, T34)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402

from lattice_core.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice_core.pipeline import PipelineSpec  # noqa: E402
from lattice_core.presets import to_json  # noqa: E402
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


class FakeDialogs:
    """Stand-in for QFileDialog that returns scripted paths and records its calls."""

    open_path = ""
    save_path = ""
    calls: list[tuple[str, str, str]] = []

    @classmethod
    def getOpenFileName(cls, parent: object, title: str, directory: str, filters: str) -> tuple:
        """Return the scripted open path."""
        cls.calls.append((title, directory, filters))
        return (cls.open_path, "")

    @classmethod
    def getSaveFileName(cls, parent: object, title: str, directory: str, filters: str) -> tuple:
        """Return the scripted save path."""
        cls.calls.append((title, directory, filters))
        return (cls.save_path, "")


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
def dialogs(monkeypatch: pytest.MonkeyPatch) -> type[FakeDialogs]:
    """Replace QFileDialog with a scripted stand-in."""
    FakeDialogs.open_path = ""
    FakeDialogs.save_path = ""
    FakeDialogs.calls = []
    monkeypatch.setattr(mw, "QFileDialog", FakeDialogs)
    return FakeDialogs


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
def appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point %APPDATA% at a temporary folder so the user tier stays inside tmp_path."""
    root = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(root))
    return root


@pytest.fixture
def shipped_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the shipped preset directory at an empty temporary folder."""
    directory = tmp_path / "shipped"
    monkeypatch.setattr(mw, "PRESET_DIR", directory)
    return directory


@pytest.fixture
def user_dir(appdata: Path) -> Path:
    """Return the user preset directory under the temporary %APPDATA%."""
    return appdata / "LatticeDither" / "presets"


@pytest.fixture
def preset_dir(user_dir: Path) -> Path:
    """Fill the user preset directory with three presets."""
    _write_presets(user_dir, ["01_a.json", "02_b.json", "03_c.json"])
    return user_dir


def _shown_window(qapp: QApplication) -> Iterator[mw.MainWindow]:
    """Create and show a main window, closing it when the test ends."""
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


@pytest.fixture
def window(
    qapp: QApplication, settings: type[FakeSettings], bridge: None, preset_dir: Path,
    shipped_dir: Path,
) -> Iterator[mw.MainWindow]:
    """Return a shown main window whose user preset directory holds three presets."""
    yield from _shown_window(qapp)


@pytest.fixture
def bare_window(
    qapp: QApplication, settings: type[FakeSettings], bridge: None, shipped_dir: Path,
    user_dir: Path,
) -> Iterator[mw.MainWindow]:
    """Return a shown main window with no user presets and no user directory yet."""
    yield from _shown_window(qapp)


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


def test_browser_lists_shipped_presets_when_the_user_dir_is_absent(
    shipped_dir: Path, user_dir: Path
) -> None:
    """With no user directory the browser lists the shipped presets, marked read-only."""
    _write_presets(shipped_dir, ["01_a.json", "02_b.json"])
    assert not user_dir.exists()
    browser = PresetBrowser([shipped_dir, user_dir])
    assert [p.name for p in browser.paths] == ["01_a.json", "02_b.json"]
    assert all(browser.is_shipped(path) for path in browser.paths)
    assert browser.label() == "Preset 1/2: 01_a.json (read-only)"


def test_browser_lists_shipped_presets_when_the_user_dir_is_empty(
    shipped_dir: Path, user_dir: Path
) -> None:
    """An empty user directory leaves the shipped presets as the whole list."""
    _write_presets(shipped_dir, ["01_a.json"])
    user_dir.mkdir(parents=True)
    browser = PresetBrowser([shipped_dir, user_dir])
    assert browser.paths == [shipped_dir / "01_a.json"]


def test_a_user_preset_shadows_the_shipped_one(shipped_dir: Path, user_dir: Path) -> None:
    """A name present in both tiers is listed once, as the user file."""
    _write_presets(shipped_dir, ["01_a.json", "02_b.json"])
    _write_presets(user_dir, ["02_b.json"])
    browser = PresetBrowser([shipped_dir, user_dir])
    assert browser.paths == [shipped_dir / "01_a.json", user_dir / "02_b.json"]
    assert browser.is_shipped(browser.paths[0]) is True
    assert browser.is_shipped(browser.paths[1]) is False


def test_the_window_searches_both_tiers(
    window: mw.MainWindow, shipped_dir: Path, user_dir: Path
) -> None:
    """The window searches the shipped tier first and saves into the user tier."""
    assert window._preset_dirs() == (shipped_dir, user_dir)
    assert window.presets.browser.directories == (shipped_dir, user_dir)
    assert window._preset_dir() == user_dir


def test_stepping_onto_a_shipped_preset_marks_it_read_only(
    bare_window: mw.MainWindow, shipped_dir: Path
) -> None:
    """Stepping onto a shipped preset shows the read-only marker in the status label."""
    _write_presets(shipped_dir, ["01_a.json", "02_b.json"])
    bare_window.presets.browser.refresh()
    bare_window.presets.step(1)
    assert bare_window.presets.label.text() == "Preset 2/2: 02_b.json (read-only)"


def test_both_dialogs_open_in_the_user_directory(
    window: mw.MainWindow, dialogs: type[FakeDialogs], user_dir: Path
) -> None:
    """Once the user directory exists, Load and Save both open there."""
    window.actions["load_preset"].trigger()
    assert Path(dialogs.calls[-1][1]) == user_dir
    dialogs.save_path = str(user_dir / "mine.json")
    window.actions["save_preset"].trigger()
    assert Path(dialogs.calls[-1][1]).parent == user_dir
    assert (user_dir / "mine.json").read_text(encoding="utf-8") == to_json(window.spec)


def test_the_load_dialog_opens_in_the_shipped_tier_on_a_fresh_install(
    bare_window: mw.MainWindow, dialogs: type[FakeDialogs], shipped_dir: Path, user_dir: Path
) -> None:
    """With no user directory yet, Load opens where the shipped presets are."""
    assert not user_dir.exists()
    bare_window.actions["load_preset"].trigger()
    assert Path(dialogs.calls[-1][1]) == shipped_dir


def test_a_remembered_shipped_directory_is_ignored(
    window: mw.MainWindow, dialogs: type[FakeDialogs], settings: type[FakeSettings],
    shipped_dir: Path, user_dir: Path,
) -> None:
    """A 1.0 setting pointing at the shipped tier does not send the dialog there."""
    settings.store["LatticeDither/LatticeDither/preset_dir"] = str(shipped_dir)
    dialogs.save_path = str(user_dir / "mine.json")
    window.actions["save_preset"].trigger()
    assert Path(dialogs.calls[-1][1]).parent == user_dir


def test_the_user_directory_is_created_on_first_save(
    bare_window: mw.MainWindow, dialogs: type[FakeDialogs], user_dir: Path
) -> None:
    """The user directory appears only when the first preset is saved into it."""
    assert not user_dir.exists()
    dialogs.save_path = str(user_dir / "mine.json")
    bare_window.actions["save_preset"].trigger()
    assert user_dir.is_dir()
    assert (user_dir / "mine.json").exists()


def test_saving_never_writes_into_the_shipped_directory(
    bare_window: mw.MainWindow, dialogs: type[FakeDialogs], shipped_dir: Path, user_dir: Path
) -> None:
    """A save aimed at the shipped tier is redirected to the user tier."""
    shipped_dir.mkdir(parents=True, exist_ok=True)
    target = shipped_dir / "01_a.json"
    target.write_text('{"version": 2, "algorithm_id": "bayer_8"}', encoding="utf-8")
    bare_window.presets.browser.refresh()
    dialogs.save_path = str(target)
    bare_window.actions["save_preset"].trigger()
    assert target.read_text(encoding="utf-8") == '{"version": 2, "algorithm_id": "bayer_8"}'
    assert (user_dir / "01_a.json").read_text(encoding="utf-8") == to_json(bare_window.spec)


def test_the_shipped_directory_is_untouched_when_it_is_the_only_tier(
    bare_window: mw.MainWindow, dialogs: type[FakeDialogs], shipped_dir: Path, user_dir: Path
) -> None:
    """With only the shipped tier present, a save still creates and fills the user tier."""
    _write_presets(shipped_dir, ["01_a.json", "02_b.json"])
    bare_window.presets.browser.refresh()
    snapshot = {path.name: path.read_text(encoding="utf-8") for path in shipped_dir.glob("*.json")}
    dialogs.save_path = str(shipped_dir / "02_b.json")
    bare_window.actions["save_preset"].trigger()
    after = {path.name: path.read_text(encoding="utf-8") for path in shipped_dir.glob("*.json")}
    assert after == snapshot
    assert sorted(path.name for path in user_dir.glob("*.json")) == ["02_b.json"]


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


def test_arrow_keys_step_the_preset(window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
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
