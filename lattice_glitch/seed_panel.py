"""Seed panel of the Glitch shell: one seed, one reroll button, per-module locks (§18).

The panel is a view over the window's ``SeedController``: the field shows the global
seed (a reroll mixes it to a full 64-bit value, so the field is text, not a spin box),
the reroll button asks for a new one, and one checkbox per stack position freezes or
releases that module's stream. Locks are session-only; the preset serialises the seed.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SeedPanel(QWidget):
    """Global seed editor, reroll button and the per-module lock list of one stack."""

    seed_changed = Signal(int)
    reroll_requested = Signal()
    lock_changed = Signal(int, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the seed row and the empty lock list."""
        super().__init__(parent)
        self.setObjectName("seed_panel")
        self._loading = False
        self._seed = 0
        self._locks: list[QCheckBox] = []
        self.seed_edit = QLineEdit(self)
        self.seed_edit.setObjectName("seed_edit")
        self.seed_edit.setText("0")
        self.reroll_button = QPushButton("Reroll", self)
        self.reroll_button.setObjectName("seed_reroll")
        row = QHBoxLayout()
        row.addWidget(QLabel("Seed", self))
        row.addWidget(self.seed_edit, 1)
        row.addWidget(self.reroll_button)
        self.lock_box = QVBoxLayout()
        self.lock_box.setContentsMargins(0, 0, 0, 0)
        self.hint = QLabel("Lock a module to keep its noise across a reroll.", self)
        self.hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(row)
        layout.addWidget(QLabel("Module locks", self))
        layout.addLayout(self.lock_box)
        layout.addWidget(self.hint)
        layout.addStretch(1)
        self.seed_edit.returnPressed.connect(self._on_seed_text)
        self.reroll_button.clicked.connect(lambda: self.reroll_requested.emit())

    def set_seed(self, seed: int) -> None:
        """Show seed without emitting seed_changed."""
        self._loading = True
        try:
            self._seed = int(seed)
            self.seed_edit.setText(str(self._seed))
        finally:
            self._loading = False

    def set_modules(self, labels: list[str], locked: frozenset[int]) -> None:
        """Rebuild one lock checkbox per stack position, checked for the locked ones."""
        self._loading = True
        try:
            for check in self._locks:
                self.lock_box.removeWidget(check)
                check.deleteLater()
            self._locks = []
            for index, label in enumerate(labels):
                check = QCheckBox(f"{index + 1}. {label}", self)
                check.setObjectName(f"seed_lock_{index}")
                check.setChecked(index in locked)
                check.toggled.connect(lambda state, i=index: self._on_lock(i, state))
                self.lock_box.addWidget(check)
                self._locks.append(check)
        finally:
            self._loading = False

    def lock_check(self, index: int) -> QCheckBox:
        """Return the lock checkbox of one stack position."""
        return self._locks[index]

    def _on_seed_text(self) -> None:
        """Adopt a typed non-negative integer seed; restore the display otherwise."""
        if self._loading:
            return
        try:
            value = int(self.seed_edit.text().strip())
        except ValueError:
            value = -1
        if value < 0:
            self.seed_edit.setText(str(self._seed))
            return
        self._seed = value
        self.seed_changed.emit(value)

    def _on_lock(self, index: int, state: bool) -> None:
        """Emit lock_changed for a user toggle, never for a programmatic load."""
        if not self._loading:
            self.lock_changed.emit(index, bool(state))


__all__ = ["SeedPanel"]
