"""Tests for undo, shortcuts, drag and drop and recent files (T27, CONTRACT §22.2)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from lattice.bridge.photocraft import PhotoCraftClient  # noqa: E402
from lattice.modes.dither.export.video import export_video  # noqa: E402
from lattice.modes.dither.i18n import tr  # noqa: E402
from lattice.modes.dither.ui import commands as cmd  # noqa: E402
from lattice.modes.dither.ui import main_window as mw  # noqa: E402
from lattice.pipeline import PipelineSpec  # noqa: E402
from lattice.presets import to_json  # noqa: E402
from lattice.ui import worker as worker_module  # noqa: E402

# The eleven shortcuts of §22.2, keyed by the action that carries them.
CONTRACT_SHORTCUTS: dict[str, tuple[str, ...]] = {
    "undo": ("Ctrl+Z",),
    "redo": ("Ctrl+Shift+Z", "Ctrl+Y"),
    "open_image": ("Ctrl+O",),
    "export_png": ("Ctrl+S",),
    "export_dialog": ("Ctrl+E",),
    "send_to_photocraft": ("Ctrl+Shift+S",),
    "rerender": ("F5",),
    "toggle_before_after": ("Space",),
    "preset_prev": ("Left",),
    "preset_next": ("Right",),
}


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


class FakeClock:
    """Monotonic clock the tests advance by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time in seconds."""
        return self.now

    def advance(self, milliseconds: float) -> None:
        """Move the clock forward by milliseconds."""
        self.now += milliseconds / 1000.0


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


@pytest.fixture
def errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the modal error boxes instead of showing them."""
    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[2]))
    return messages


@pytest.fixture
def preset_tiers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point both preset tiers at temporary folders holding two presets each."""
    root = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(root))
    shipped = tmp_path / "shipped"
    monkeypatch.setattr(mw, "PRESET_DIR", shipped)
    user = root / "LatticeDither" / "presets"
    for directory, names in ((shipped, ("01_a.json", "02_b.json")), (user, ("03_c.json",))):
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / name).write_text(to_json(PipelineSpec()), encoding="utf-8")
    return shipped, user


@pytest.fixture
def window(
    qapp: QApplication,
    settings: type[FakeSettings],
    bridge: None,
    errors: list[str],
    preset_tiers: tuple[Path, Path],
) -> Iterator[mw.MainWindow]:
    """Return a shown main window with a temporary preset tier and no image."""
    win = mw.MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


def _spec(brightness: float) -> PipelineSpec:
    """Return a spec that differs from the default only in brightness."""
    spec = PipelineSpec()
    spec.brightness = brightness
    return spec


def _png(path: Path) -> Path:
    """Write a tiny PNG at path and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", (4, 4), (200, 30, 30)).save(path)
    return path


def _drop_event(paths: list[Path], kind: QEvent.Type = QEvent.Type.Drop) -> QEvent:
    """Build a drag-enter or drop event carrying the given local files."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    if kind == QEvent.Type.DragEnter:
        event: QEvent = QDragEnterEvent(
            QPointF(10.0, 10.0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    else:
        event = QDropEvent(
            QPointF(10.0, 10.0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    # Qt keeps a bare pointer to the mime data, so the test must own it for the event's life.
    event.mime = mime
    return event


# --- the undo stack ---------------------------------------------------------------


def test_undo_and_redo_round_trip_five_changes() -> None:
    """Five recorded changes undo back to the start and redo forward again."""
    stack = cmd.UndoStack()
    stack.reset(_spec(0.0))
    for step in range(1, 6):
        stack.push(_spec(step / 10.0))
    assert len(stack) == 6
    for step in (4, 3, 2, 1, 0):
        undone = stack.undo()
        assert undone is not None
        assert undone.brightness == pytest.approx(step / 10.0)
    assert stack.can_undo() is False
    assert stack.undo() is None
    for step in range(1, 6):
        redone = stack.redo()
        assert redone is not None
        assert redone.brightness == pytest.approx(step / 10.0)
    assert stack.can_redo() is False
    assert stack.redo() is None


def test_the_stack_never_exceeds_fifty_entries() -> None:
    """Sixty changes leave exactly the last fifty snapshots on the stack."""
    stack = cmd.UndoStack()
    stack.reset(_spec(0.0))
    for step in range(1, 61):
        stack.push(_spec(step / 100.0))
    assert cmd.UNDO_DEPTH == 50
    assert len(stack) == 50
    current = stack.current()
    assert current is not None
    assert current.brightness == pytest.approx(0.60)
    for _ in range(49):
        assert stack.undo() is not None
    assert stack.can_undo() is False


def test_a_burst_within_four_hundred_ms_is_one_entry() -> None:
    """Ten slider changes inside the coalescing window collapse into one undo step."""
    clock = FakeClock()
    stack = cmd.UndoStack(clock=clock)
    stack.reset(_spec(0.0))
    for step in range(1, 11):
        clock.advance(30.0)
        stack.push(_spec(step / 100.0), coalesce=True)
    assert len(stack) == 2
    undone = stack.undo()
    assert undone is not None
    assert undone.brightness == pytest.approx(0.0)
    assert stack.can_undo() is False


def test_a_change_after_the_window_starts_a_new_entry() -> None:
    """A pause longer than the coalescing window keeps the two changes apart."""
    clock = FakeClock()
    stack = cmd.UndoStack(clock=clock)
    stack.reset(_spec(0.0))
    stack.push(_spec(0.1), coalesce=True)
    clock.advance(500.0)
    stack.push(_spec(0.2), coalesce=True)
    assert len(stack) == 3


def test_a_discrete_change_is_never_coalesced() -> None:
    """A preset load breaks the burst, so the next slider change is its own entry."""
    clock = FakeClock()
    stack = cmd.UndoStack(clock=clock)
    stack.reset(_spec(0.0))
    stack.push(_spec(0.1), coalesce=True)
    stack.push(_spec(0.2), coalesce=False)
    clock.advance(10.0)
    stack.push(_spec(0.3), coalesce=True)
    assert len(stack) == 4


def test_pushing_the_current_state_is_a_no_op() -> None:
    """Recording the state the stack already points at adds nothing."""
    stack = cmd.UndoStack()
    stack.reset(_spec(0.0))
    stack.push(_spec(0.0))
    assert len(stack) == 1


def test_snapshots_are_immutable_copies() -> None:
    """Neither the caller's spec nor the returned one can reach the stored snapshot."""
    stack = cmd.UndoStack()
    spec = _spec(0.0)
    stack.reset(spec)
    spec.brightness = 0.9
    current = stack.current()
    assert current is not None
    assert current.brightness == pytest.approx(0.0)
    current.brightness = 0.5
    again = stack.current()
    assert again is not None
    assert again.brightness == pytest.approx(0.0)


def test_a_new_change_after_undo_drops_the_redo_tail() -> None:
    """Recording after an undo discards the states that were ahead."""
    stack = cmd.UndoStack()
    stack.reset(_spec(0.0))
    stack.push(_spec(0.1))
    stack.push(_spec(0.2))
    stack.undo()
    stack.push(_spec(0.3))
    assert stack.can_redo() is False
    current = stack.current()
    assert current is not None
    assert current.brightness == pytest.approx(0.3)


# --- recent files -----------------------------------------------------------------


def test_recent_files_keep_ten_and_move_to_the_front(tmp_path: Path) -> None:
    """The list is capped at ten, newest first, without duplicates."""
    recent = cmd.RecentFiles(FakeSettings("LatticeDither", "LatticeDither"))
    paths = [_png(tmp_path / f"{index}.png") for index in range(12)]
    for path in paths:
        recent.add(path)
    assert cmd.RECENT_LIMIT == 10
    assert len(recent.paths) == 10
    assert recent.paths[0] == paths[-1]
    recent.add(paths[5])
    assert recent.paths[0] == paths[5]
    assert len(recent.paths) == 10
    assert len(set(recent.paths)) == 10


def test_recent_files_drop_missing_entries_on_load(tmp_path: Path) -> None:
    """A remembered file that has disappeared is pruned and the store rewritten."""
    store = FakeSettings("LatticeDither", "LatticeDither")
    kept = _png(tmp_path / "kept.png")
    gone = tmp_path / "gone.png"
    store.setValue(cmd.RECENT_KEY, [str(gone), str(kept)])
    recent = cmd.RecentFiles(store)
    assert recent.paths == [kept]
    assert store.value(cmd.RECENT_KEY) == [str(kept)]


def test_recent_files_read_a_single_stored_string(tmp_path: Path) -> None:
    """QSettings hands back a bare string when only one path was stored."""
    store = FakeSettings("LatticeDither", "LatticeDither")
    kept = _png(tmp_path / "kept.png")
    store.setValue(cmd.RECENT_KEY, str(kept))
    assert cmd.RecentFiles(store).paths == [kept]


def test_recent_files_survive_a_window_rebuild(
    qapp: QApplication, window: mw.MainWindow, tmp_path: Path
) -> None:
    """A second window reads the list the first one wrote."""
    path = _png(tmp_path / "first.png")
    window.commands.open_path(path)
    assert window.commands.recent.paths == [path]
    window.close()
    qapp.processEvents()
    rebuilt = mw.MainWindow()
    rebuilt.show()
    qapp.processEvents()
    assert rebuilt.commands.recent.paths == [path]
    assert [action.text() for action in rebuilt.commands.recent_menu.actions()] == ["first.png"]
    rebuilt.close()
    qapp.processEvents()


def test_a_missing_recent_file_is_pruned_by_the_next_window(
    qapp: QApplication, window: mw.MainWindow, tmp_path: Path
) -> None:
    """A file deleted between two launches leaves the Recent menu empty."""
    path = _png(tmp_path / "gone.png")
    window.commands.open_path(path)
    window.close()
    qapp.processEvents()
    path.unlink()
    rebuilt = mw.MainWindow()
    rebuilt.show()
    qapp.processEvents()
    assert rebuilt.commands.recent.paths == []
    assert [action.text() for action in rebuilt.commands.recent_menu.actions()] == [
        tr("No recent files")
    ]
    rebuilt.close()
    qapp.processEvents()


def test_opening_a_recent_file_that_vanished_reports_it(
    window: mw.MainWindow, tmp_path: Path
) -> None:
    """Triggering a stale Recent entry drops it and says why nothing opened."""
    path = _png(tmp_path / "stale.png")
    window.commands.remember(path)
    path.unlink()
    window.commands.open_recent(path)
    assert window.commands.recent.paths == []
    assert window.source is None
    assert "stale.png" in window.statusBar().currentMessage()


# --- drag and drop ----------------------------------------------------------------


def test_dropping_a_png_opens_it(window: mw.MainWindow, tmp_path: Path) -> None:
    """A dropped image becomes the pipeline source and joins the recent files."""
    path = _png(tmp_path / "dropped.png")
    window.dropEvent(_drop_event([path]))
    assert window.source is not None
    assert window.source.shape == (4, 4, 3)
    assert window.commands.recent.paths == [path]


def test_dropping_a_non_image_is_ignored_with_a_message(
    window: mw.MainWindow, tmp_path: Path
) -> None:
    """A dropped text file leaves the source alone and names itself in the status bar."""
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    window.dropEvent(_drop_event([path]))
    assert window.source is None
    message = window.statusBar().currentMessage()
    assert message == tr("Ignored {name}: not an image", name="notes.txt")


def test_drag_enter_accepts_images_and_refuses_other_files(
    window: mw.MainWindow, tmp_path: Path
) -> None:
    """The drag is accepted only when it carries at least one image."""
    image = _png(tmp_path / "a.png")
    text = tmp_path / "a.txt"
    text.write_text("x", encoding="utf-8")
    accepted = _drop_event([image], QEvent.Type.DragEnter)
    window.dragEnterEvent(accepted)
    assert accepted.isAccepted() is True
    refused = _drop_event([text], QEvent.Type.DragEnter)
    window.dragEnterEvent(refused)
    assert refused.isAccepted() is False


def test_the_first_image_of_a_multi_file_drop_wins(window: mw.MainWindow, tmp_path: Path) -> None:
    """Only the first image of a drop is opened."""
    first = _png(tmp_path / "one.png")
    second = _png(tmp_path / "two.png")
    window.dropEvent(_drop_event([first, second]))
    assert window.commands.recent.paths == [first]


# --- shortcuts --------------------------------------------------------------------


def test_every_contract_shortcut_is_bound(window: mw.MainWindow) -> None:
    """Every key of §22.2 is either an action shortcut or owned by the preset filter."""
    assert set(cmd.shortcut_keys()) == set(CONTRACT_SHORTCUTS)
    for key, sequences in cmd.SHORTCUTS.items():
        bound = [sequence.toString() for sequence in window.actions[key].shortcuts()]
        assert bound == list(sequences)
    for key in cmd.FILTERED_SHORTCUTS:
        assert window.actions[key].shortcuts() == []


def test_every_shortcut_action_is_attached_to_the_window(window: mw.MainWindow) -> None:
    """Every action carrying a shortcut is attached, so the key is live without a menu.

    An action that is in no menu and not added to the window has an inert shortcut: Qt only
    routes a key to an action that some widget owns. F5 and Space were dead for exactly that
    reason, and triggering the action directly in a test cannot see it.
    """
    attached = {action.objectName() for action in QWidget.actions(window)}
    for key in cmd.SHORTCUTS:
        assert window.actions[key].objectName() in attached, key


def test_the_canvas_does_not_swallow_drops(window: mw.MainWindow) -> None:
    """The preview canvas refuses drops so the window's dropEvent is the one that runs.

    QGraphicsView accepts drops on itself and on its viewport, which stops the event from
    reaching the parent. The window would then never see a dropped file.
    """
    assert window.acceptDrops() is True
    assert window.canvas.acceptDrops() is False
    assert window.canvas.viewport().acceptDrops() is False


def test_undo_and_redo_actions_round_trip_the_window(window: mw.MainWindow) -> None:
    """Ctrl+Z steps back through five changes and Ctrl+Shift+Z steps forward again."""
    original = copy.deepcopy(window.spec)
    for step in range(1, 6):
        spec = copy.deepcopy(original)
        spec.brightness = step / 10.0
        window._load_spec(spec)
    assert window.spec.brightness == pytest.approx(0.5)
    for _ in range(5):
        window.actions["undo"].trigger()
    assert window.spec.brightness == pytest.approx(0.0)
    assert window.actions["undo"].isEnabled() is False
    for _ in range(5):
        window.actions["redo"].trigger()
    assert window.spec.brightness == pytest.approx(0.5)
    assert window.actions["redo"].isEnabled() is False


def test_undo_with_an_empty_history_reports_it(window: mw.MainWindow) -> None:
    """Undoing at the start of the history says so instead of doing nothing silently."""
    window.commands.undo()
    assert window.statusBar().currentMessage() == tr("Nothing to undo")
    window.commands.redo()
    assert window.statusBar().currentMessage() == tr("Nothing to redo")


def test_ctrl_o_opens_an_image(
    window: mw.MainWindow, dialogs: type[FakeDialogs], tmp_path: Path
) -> None:
    """The open action loads the chosen file and remembers it."""
    path = _png(tmp_path / "opened.png")
    dialogs.open_path = str(path)
    window.actions["open_image"].trigger()
    assert window.source is not None
    assert window.commands.recent.paths == [path]


def test_ctrl_s_exports_a_png(
    window: mw.MainWindow, dialogs: type[FakeDialogs], gradient: np.ndarray, tmp_path: Path
) -> None:
    """The save action asks for a path and starts a full-resolution render."""
    window._set_source(gradient)
    dialogs.save_path = str(tmp_path / "out.png")
    window.actions["export_png"].trigger()
    assert window._export_path == tmp_path / "out.png"


def test_ctrl_e_opens_the_export_dialog(
    window: mw.MainWindow, monkeypatch: pytest.MonkeyPatch, gradient: np.ndarray
) -> None:
    """The export action hands source and spec to the shared full-resolution dialog.

    L-UI2 (E1 DEV, test périmé par la carte) : Ctrl+E donnait autrefois l'aperçu
    plafonné (_last_image) au dialogue de l'app ; la carte exige le dialogue du
    core, qui rend la pleine résolution depuis la source et le spec.
    """
    calls: list[tuple[object, object, object, dict]] = []

    def fake(source: object, spec: object, parent: object, **kwargs: object) -> None:
        calls.append((source, spec, parent, kwargs))

    monkeypatch.setattr(cmd, "run_export_dialog", fake)
    window._set_source(gradient)
    window._last_image = np.zeros((4, 4, 3), dtype=np.uint8)
    window.actions["export_dialog"].trigger()
    assert len(calls) == 1
    source, spec, parent, kwargs = calls[0]
    assert np.array_equal(source, window.prepared_source)
    assert not np.array_equal(source, window._last_image)
    assert spec == window.spec
    assert parent is window
    assert kwargs["video_writer"] is export_video
    assert kwargs["tr"] is tr
    assert kwargs["settings"] is window._settings


def test_the_export_dialog_needs_a_render(window: mw.MainWindow, errors: list[str]) -> None:
    """With nothing rendered yet the export action reports it instead of opening."""
    window.actions["export_dialog"].trigger()
    assert errors == [tr("Load an image before exporting.")]


def test_ctrl_shift_s_sends_to_photocraft(window: mw.MainWindow, gradient: np.ndarray) -> None:
    """The send action starts a full-resolution render for PhotoCraft."""
    window._set_source(gradient)
    seen: list[object] = []
    window.send_requested.connect(seen.append)
    window.actions["send_to_photocraft"].trigger()
    assert len(seen) == 1


def test_f5_rerenders_the_current_spec(window: mw.MainWindow, gradient: np.ndarray) -> None:
    """The re-render action asks the worker for a fresh preview."""
    window._set_source(gradient)
    seen: list[object] = []
    window.preview_requested.connect(seen.append)
    window.actions["rerender"].trigger()
    assert len(seen) == 1


def test_f5_without_a_source_reports_it(window: mw.MainWindow) -> None:
    """Re-rendering with no image says so instead of emitting a job."""
    seen: list[object] = []
    window.preview_requested.connect(seen.append)
    window.actions["rerender"].trigger()
    assert seen == []
    assert window.statusBar().currentMessage() == tr("Load an image first.")


def test_space_toggles_before_and_after(window: mw.MainWindow) -> None:
    """The toggle action flips the canvas mode and keeps the mode actions in step."""
    assert window.canvas.mode() == "after"
    window.actions["toggle_before_after"].trigger()
    assert window.canvas.mode() == "before"
    assert window.actions["mode_before"].isChecked() is True
    window.actions["toggle_before_after"].trigger()
    assert window.canvas.mode() == "after"
    assert window.actions["mode_after"].isChecked() is True


def test_the_arrow_actions_step_the_preset(window: mw.MainWindow) -> None:
    """The previous and next preset actions move through the preset list."""
    first = window.presets.label.text()
    window.actions["preset_next"].trigger()
    assert window.presets.label.text() != first
    window.actions["preset_prev"].trigger()
    assert window.presets.label.text() == first


def test_the_file_menu_lists_the_recent_files(window: mw.MainWindow, tmp_path: Path) -> None:
    """The File menu carries a Recent submenu holding the remembered names."""
    path = _png(tmp_path / "menu.png")
    window.commands.remember(path)
    titles = [action.text() for action in window.menuBar().actions()]
    assert titles == [tr("File"), tr("Edit")]
    assert window.commands.recent_menu.title() == tr("Recent")
    assert [action.text() for action in window.commands.recent_menu.actions()] == ["menu.png"]
