"""Undo history, shortcuts, recent files and drag and drop for the main window (§22.2).

The window keeps one :class:`CommandController`. It owns the undo stack over immutable
``PipelineSpec`` snapshots, the ``File > Recent`` menu backed by ``QSettings``, the shortcut
table of the contract and the drop target that opens a dragged image.

The arrow keys are the one exception in the shortcut table: ``PresetController`` already
intercepts ``Left`` and ``Right`` with an application event filter, so that a focused list or
spin box keeps its own arrow navigation. Binding them again on the preset actions would step
the preset twice, so the table records them as filtered rather than as action shortcuts.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image as PILImage
from PySide6.QtCore import QMimeData, QObject, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence

from lattice_core import color
from lattice_core.pipeline import PipelineSpec
from lattice_dither.i18n import tr
from lattice_dither.ui.export_dialog import run_export_dialog

if TYPE_CHECKING:
    from lattice_dither.ui.main_window import MainWindow

UNDO_DEPTH = 50
COALESCE_MS = 400
RECENT_LIMIT = 10
RECENT_KEY = "recent_files"
STATUS_MS = 5000
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})

# Action key -> the key sequences bound to it. Every shortcut of §22.2 is here except the
# two arrows, which the preset event filter owns; see FILTERED_SHORTCUTS.
SHORTCUTS: dict[str, tuple[str, ...]] = {
    "undo": ("Ctrl+Z",),
    "redo": ("Ctrl+Shift+Z", "Ctrl+Y"),
    "open_image": ("Ctrl+O",),
    "export_png": ("Ctrl+S",),
    "export_dialog": ("Ctrl+E",),
    "send_to_photocraft": ("Ctrl+Shift+S",),
    "rerender": ("F5",),
    "toggle_before_after": ("Space",),
}
FILTERED_SHORTCUTS: dict[str, tuple[str, ...]] = {
    "preset_prev": ("Left",),
    "preset_next": ("Right",),
}


def snapshot(spec: PipelineSpec) -> PipelineSpec:
    """Return a deep copy of spec that no caller can mutate in place."""
    return copy.deepcopy(spec)


class UndoStack:
    """Bounded undo/redo history over immutable PipelineSpec snapshots."""

    def __init__(
        self,
        depth: int = UNDO_DEPTH,
        coalesce_ms: int = COALESCE_MS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an empty stack keeping at most depth snapshots."""
        self.depth = depth
        self.coalesce_ms = coalesce_ms
        self._clock = clock
        self._entries: list[PipelineSpec] = []
        self._index = -1
        self._coalescing = False
        self._last_push = 0.0

    def reset(self, spec: PipelineSpec) -> None:
        """Forget the whole history and start again from spec."""
        self._entries = [snapshot(spec)]
        self._index = 0
        self._coalescing = False

    def push(self, spec: PipelineSpec, *, coalesce: bool = False) -> None:
        """Record spec as the newest state, merging it into the previous entry when asked."""
        entry = snapshot(spec)
        if self._entries and self._entries[self._index] == entry:
            return
        now = self._clock()
        if self._merge(entry, coalesce, now):
            self._last_push = now
            return
        del self._entries[self._index + 1 :]
        self._entries.append(entry)
        self._index = len(self._entries) - 1
        self._trim()
        self._coalescing = coalesce
        self._last_push = now

    def undo(self) -> PipelineSpec | None:
        """Step back one entry and return it, or None when there is nothing to undo."""
        if not self.can_undo():
            return None
        self._index -= 1
        self._coalescing = False
        return snapshot(self._entries[self._index])

    def redo(self) -> PipelineSpec | None:
        """Step forward one entry and return it, or None when there is nothing to redo."""
        if not self.can_redo():
            return None
        self._index += 1
        self._coalescing = False
        return snapshot(self._entries[self._index])

    def can_undo(self) -> bool:
        """Return True when there is an older snapshot to step back to."""
        return self._index > 0

    def can_redo(self) -> bool:
        """Return True when there is a newer snapshot to step forward to."""
        return 0 <= self._index < len(self._entries) - 1

    def current(self) -> PipelineSpec | None:
        """Return the snapshot the stack points at, or None when it is empty."""
        if 0 <= self._index < len(self._entries):
            return snapshot(self._entries[self._index])
        return None

    def __len__(self) -> int:
        """Return the number of stored snapshots."""
        return len(self._entries)

    def _merge(self, entry: PipelineSpec, coalesce: bool, now: float) -> bool:
        """Replace the newest entry with entry when it belongs to the same rapid burst."""
        if not coalesce or not self._coalescing or self._index < 1:
            return False
        if self._index != len(self._entries) - 1:
            return False
        if (now - self._last_push) * 1000.0 > self.coalesce_ms:
            return False
        self._entries[self._index] = entry
        return True

    def _trim(self) -> None:
        """Drop the oldest snapshots so the stack never exceeds depth entries."""
        excess = len(self._entries) - self.depth
        if excess > 0:
            del self._entries[:excess]
            self._index -= excess


class RecentFiles:
    """The last RECENT_LIMIT opened images, persisted in QSettings."""

    def __init__(
        self, settings: QSettings, limit: int = RECENT_LIMIT, key: str = RECENT_KEY
    ) -> None:
        """Read the stored list, dropping the entries whose file has disappeared."""
        self._settings = settings
        self.limit = limit
        self.key = key
        self.paths = self._read()

    def add(self, path: str | Path) -> list[Path]:
        """Move path to the front of the list, drop duplicates and cap the length."""
        entry = Path(path)
        self.paths = [entry, *(item for item in self.paths if item != entry)][: self.limit]
        self._write(self.paths)
        return self.paths

    def remove(self, path: str | Path) -> list[Path]:
        """Drop path from the list and return what is left."""
        entry = Path(path)
        self.paths = [item for item in self.paths if item != entry]
        self._write(self.paths)
        return self.paths

    def clear(self) -> None:
        """Forget every remembered path."""
        self.paths = []
        self._write(self.paths)

    def _read(self) -> list[Path]:
        """Return the stored paths that still exist, in order, capped at limit."""
        stored = self._settings.value(self.key, [])
        if isinstance(stored, str):
            stored = [stored]
        paths = [Path(str(item)) for item in (stored or [])]
        kept = [path for path in paths if path.is_file()][: self.limit]
        if len(kept) != len(paths):
            self._write(kept)
        return kept

    def _write(self, paths: Sequence[Path]) -> None:
        """Store paths in QSettings as a list of strings."""
        self._settings.setValue(self.key, [str(path) for path in paths])


class CommandController(QObject):
    """Undo, shortcuts, recent files and drag and drop for one main window."""

    def __init__(self, window: MainWindow) -> None:
        """Create the actions, bind the shortcuts, build the menus and accept drops."""
        super().__init__(window)
        self.window = window
        self.undo_stack = UndoStack()
        self.recent = RecentFiles(window._settings)
        self.undo_stack.reset(window.spec)
        self._build_actions()
        self._bind_shortcuts()
        self._build_menus()
        window.setAcceptDrops(True)
        self._update_actions()

    def record(self, spec: PipelineSpec, *, coalesce: bool = True) -> None:
        """Push spec onto the undo stack, merging rapid slider changes into one entry."""
        self.undo_stack.push(spec, coalesce=coalesce)
        self._update_actions()

    def on_panels_changed(self) -> None:
        """Record the edited pipeline in the undo history and refresh the preview."""
        self.window._rebuild_spec()
        self.record(self.window.spec)
        self.window._request_preview()

    def open_path(self, path: str | Path) -> None:
        """Load one image file as the pipeline source and remember it as recent."""
        target = Path(path)
        try:
            with PILImage.open(target) as handle:
                image = handle.copy()
        except (OSError, ValueError) as exc:
            message = tr("Cannot open {path}: {error}", path=repr(str(target)), error=str(exc))
            self.window._error(message)
            return
        self.window._set_source(color.to_float(image))
        self.remember(target)
        self.window.statusBar().showMessage(tr("Loaded {name}", name=target.name), STATUS_MS)

    def undo(self) -> None:
        """Step the pipeline back one entry and show it."""
        self._apply(self.undo_stack.undo(), tr("Nothing to undo"))

    def redo(self) -> None:
        """Step the pipeline forward one entry and show it."""
        self._apply(self.undo_stack.redo(), tr("Nothing to redo"))

    def remember(self, path: str | Path) -> None:
        """Add path to the recent files and rebuild the Recent submenu."""
        self.recent.add(path)
        self._fill_recent()

    def open_recent(self, path: Path) -> None:
        """Open one remembered image, dropping it from the list when it has gone."""
        if not Path(path).is_file():
            self.recent.remove(path)
            self._fill_recent()
            message = tr(
                "Cannot open {path}: {error}", path=repr(str(path)), error=tr("file not found")
            )
            self.window.statusBar().showMessage(message, STATUS_MS)
            return
        self.open_path(Path(path))

    def export_dialog(self) -> None:
        """Open the export dialog on the last rendered preview."""
        image = self.window._last_image
        if image is None:
            self.window._error(tr("Load an image before exporting."))
            return
        run_export_dialog(image, self.window)

    def rerender(self) -> None:
        """Render the current pipeline again, reporting when there is no source."""
        if self.window.source is None:
            self.window.statusBar().showMessage(tr("Load an image first."), STATUS_MS)
            return
        self.window._request_preview()

    def toggle_before_after(self) -> None:
        """Flip the preview between the before and the after view."""
        mode = "before" if self.window.canvas.mode() == "after" else "after"
        self.window._on_mode(mode)
        self.window.actions[f"mode_{mode}"].setChecked(True)

    def _apply(self, spec: PipelineSpec | None, empty: str) -> None:
        """Adopt spec when the history moved, or report that it could not."""
        if spec is None:
            self.window.statusBar().showMessage(empty, STATUS_MS)
            return
        self.window._load_spec(spec, record=False)
        self._update_actions()

    def _build_actions(self) -> None:
        """Create the undo, redo, export, re-render and before/after actions."""
        add = self.window._add_action
        self.undo_action = add("undo", tr("Undo"), self.undo)
        self.redo_action = add("redo", tr("Redo"), self.redo)
        self.export_action = add("export_dialog", tr("Export…"), self.export_dialog)
        self.rerender_action = add("rerender", tr("Re-render"), self.rerender)
        self.toggle_action = add(
            "toggle_before_after", tr("Before / after"), self.toggle_before_after
        )

    def _bind_shortcuts(self) -> None:
        """Give every action of the shortcut table its key sequences."""
        for key, sequences in SHORTCUTS.items():
            action = self.window.actions.get(key)
            if action is not None:
                action.setShortcuts([QKeySequence(sequence) for sequence in sequences])

    def _build_menus(self) -> None:
        """Create the File menu with the Recent submenu, and the Edit menu."""
        bar = self.window.menuBar()
        file_menu = bar.addMenu(tr("File"))
        for key in ("open_image", "export_png", "send_to_photocraft"):
            file_menu.addAction(self.window.actions[key])
        file_menu.addAction(self.export_action)
        self.recent_menu = file_menu.addMenu(tr("Recent"))
        self._fill_recent()
        edit_menu = bar.addMenu(tr("Edit"))
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

    def _fill_recent(self) -> None:
        """Rebuild the Recent submenu from the remembered paths."""
        self.recent_menu.clear()
        if not self.recent.paths:
            empty = self.recent_menu.addAction(tr("No recent files"))
            empty.setEnabled(False)
            return
        for path in self.recent.paths:
            action = self.recent_menu.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked=False, item=path: self.open_recent(item))

    def _update_actions(self) -> None:
        """Enable undo and redo only when the history has somewhere to go."""
        self.undo_action.setEnabled(self.undo_stack.can_undo())
        self.redo_action.setEnabled(self.undo_stack.can_redo())

    def drag_enter(self, event: QDragEnterEvent) -> None:
        """Accept the drag when it carries at least one local image file."""
        if self._dropped_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop(self, event: QDropEvent) -> None:
        """Open the first dropped image, or report that the drop was ignored."""
        images = self._dropped_images(event.mimeData())
        if not images:
            self.window.statusBar().showMessage(self._ignored_message(event.mimeData()), STATUS_MS)
            event.ignore()
            return
        event.acceptProposedAction()
        self.open_path(images[0])

    def _ignored_message(self, mime: QMimeData) -> str:
        """Return the status text naming the first dropped item that is not an image."""
        names = [Path(url.toLocalFile()).name for url in mime.urls() if url.isLocalFile()]
        return tr("Ignored {name}: not an image", name=names[0] if names else tr("the drop"))

    def _dropped_images(self, mime: QMimeData) -> list[Path]:
        """Return the local image files carried by mime, in drop order."""
        if not mime.hasUrls():
            return []
        paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
        return [path for path in paths if path.suffix.lower() in IMAGE_SUFFIXES]


def shortcut_keys() -> dict[str, tuple[str, ...]]:
    """Return every §22.2 shortcut, action shortcuts first and the filtered arrows last."""
    return {**SHORTCUTS, **FILTERED_SHORTCUTS}
