"""Main window shell: toolbar, preview canvas, right panel dock and status bar."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QTabWidget,
    QToolBar,
    QWidget,
)

from dithercraft.ui.canvas import PreviewCanvas

LOGGER = logging.getLogger(__name__)

PANEL_TABS: tuple[str, ...] = ("Algorithm", "Palette", "Effects")
DOCK_MIN_WIDTH = 320


class MainWindow(QMainWindow):
    """Application shell holding the preview canvas, panel dock and toolbar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DitherCraft")
        self.resize(1280, 800)
        self.canvas = PreviewCanvas(self)
        self.setCentralWidget(self.canvas)
        self.actions: dict[str, QAction] = {}
        self._build_actions()
        self._build_toolbar()
        self._build_dock()
        self._build_status_bar()

    def _add_action(
        self,
        key: str,
        text: str,
        slot: Callable[..., None],
        shortcut: QKeySequence | None = None,
        checkable: bool = False,
        group: QActionGroup | None = None,
    ) -> QAction:
        """Create one action, register it under key and connect it to slot."""
        action = QAction(text, self)
        action.setObjectName(key)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setCheckable(checkable)
        if group is not None:
            group.addAction(action)
        action.triggered.connect(slot)
        self.actions[key] = action
        return action

    def _build_actions(self) -> None:
        """Create every toolbar action of the contract and connect its slot."""
        self._add_action(
            "open_image", "Open image", self._on_open_image, QKeySequence.StandardKey.Open
        )
        self._add_action("get_from_photocraft", "Get from PhotoCraft", self._on_get_from_photocraft)
        self._add_action(
            "send_to_photocraft", "Send to PhotoCraft", self._on_send_to_photocraft
        )
        self._add_action(
            "export_png", "Export PNG", self._on_export_png, QKeySequence.StandardKey.Save
        )
        self._add_action("load_preset", "Load preset", self._on_load_preset)
        self._add_action("save_preset", "Save preset", self._on_save_preset)
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        for key, text, mode in (
            ("mode_before", "Before", "before"),
            ("mode_after", "After", "after"),
            ("mode_split", "Split", "split"),
        ):
            action = self._add_action(
                key, text, lambda _checked=False, m=mode: self._on_mode(m), checkable=True,
                group=self.mode_group,
            )
            action.setChecked(mode == "after")
        self._add_action("zoom_fit", "Zoom Fit", self._on_zoom_fit)
        self._add_action("zoom_100", "100 %", lambda: self._on_zoom(1.0))
        self._add_action("zoom_200", "200 %", lambda: self._on_zoom(2.0))
        self._add_action("zoom_400", "400 %", lambda: self._on_zoom(4.0))

    def _build_toolbar(self) -> None:
        """Create the main toolbar with the actions in contract order."""
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        groups = (
            ("open_image", "get_from_photocraft", "send_to_photocraft", "export_png"),
            ("load_preset", "save_preset"),
            ("mode_before", "mode_after", "mode_split"),
            ("zoom_fit", "zoom_100", "zoom_200", "zoom_400"),
        )
        for index, keys in enumerate(groups):
            if index:
                self.toolbar.addSeparator()
            for key in keys:
                self.toolbar.addAction(self.actions[key])

    def _build_dock(self) -> None:
        """Create the right dock with the three placeholder panel tabs."""
        self.dock = QDockWidget("Panels", self)
        self.dock.setObjectName("panel_dock")
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.tabs = QTabWidget(self.dock)
        self.tabs.setObjectName("panel_tabs")
        self.placeholder_tabs: dict[str, QLabel] = {}
        for name in PANEL_TABS:
            label = QLabel(f"{name} panel placeholder", self.tabs)
            label.setObjectName(f"placeholder_{name.lower()}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.placeholder_tabs[name] = label
            self.tabs.addTab(label, name)
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(DOCK_MIN_WIDTH)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _build_status_bar(self) -> None:
        """Create the status bar with the connection state and render time labels."""
        bar = self.statusBar()
        self.connection_label = QLabel("PhotoCraft: unknown", self)
        self.connection_label.setObjectName("connection_label")
        self.render_time_label = QLabel("Render: -", self)
        self.render_time_label.setObjectName("render_time_label")
        bar.addPermanentWidget(self.connection_label)
        bar.addPermanentWidget(self.render_time_label)
        bar.showMessage("Ready")

    def tab_index(self, name: str) -> int:
        """Return the index of the panel tab called name, or -1."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                return index
        return -1

    def replace_tab(self, name: str, widget: QWidget) -> None:
        """Replace the placeholder tab called name with a real panel widget."""
        index = self.tab_index(name)
        if index < 0:
            raise KeyError(f"unknown tab {name!r}")
        old = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, name)
        self.placeholder_tabs.pop(name, None)
        if old is not None:
            old.deleteLater()

    def set_connection_state(self, state: str) -> None:
        """Show the PhotoCraft connection state in the status bar."""
        self.connection_label.setText(f"PhotoCraft: {state}")

    def set_render_time(self, seconds: float | None) -> None:
        """Show the last render time in the status bar."""
        if seconds is None:
            self.render_time_label.setText("Render: -")
        else:
            self.render_time_label.setText(f"Render: {seconds * 1000.0:.0f} ms")

    def _placeholder(self, name: str) -> None:
        """Log that an action is not wired yet and report it in the status bar."""
        LOGGER.info("%s is not wired yet", name)
        self.statusBar().showMessage(f"{name}: not implemented yet", 3000)

    def _on_open_image(self) -> None:
        """Placeholder for T14: open an image file."""
        self._placeholder("Open image")

    def _on_get_from_photocraft(self) -> None:
        """Placeholder for T14: fetch the visible image from PhotoCraft."""
        self._placeholder("Get from PhotoCraft")

    def _on_send_to_photocraft(self) -> None:
        """Placeholder for T14: send the render back as a new layer."""
        self._placeholder("Send to PhotoCraft")

    def _on_export_png(self) -> None:
        """Placeholder for T14: export the render as a PNG file."""
        self._placeholder("Export PNG")

    def _on_load_preset(self) -> None:
        """Placeholder for T14: load a preset file."""
        self._placeholder("Load preset")

    def _on_save_preset(self) -> None:
        """Placeholder for T14: save the current settings as a preset."""
        self._placeholder("Save preset")

    def _on_mode(self, mode: str) -> None:
        """Switch the preview canvas to the given mode."""
        self.canvas.set_mode(mode)
        self.statusBar().showMessage(f"Preview: {mode}", 2000)

    def _on_zoom_fit(self) -> None:
        """Fit the preview image into the viewport."""
        self.canvas.zoom_fit()

    def _on_zoom(self, factor: float) -> None:
        """Set the preview zoom factor."""
        self.canvas.set_zoom(factor)
