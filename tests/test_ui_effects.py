"""Tests for the effects panel."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QMimeData, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QDoubleSpinBox,
    QGroupBox,
    QSpinBox,
)

from dithercraft.core import registry  # noqa: E402
from dithercraft.core.pipeline import EffectInstance, PipelineSpec  # noqa: E402
from dithercraft.core.types import ParamSpec  # noqa: E402
from dithercraft.ui.effects_panel import (  # noqa: E402
    NO_SELECTION_TEXT,
    PARAMS_TITLE,
    POST_TITLE,
    PRE_TITLE,
    EffectList,
    EffectsPanel,
)


def _identity(img, params, rng):  # noqa: ANN001, ANN202
    """Return the image unchanged; the panel never runs effects."""
    return img


FAKE_EFFECTS: dict[str, registry.EffectInfo] = {
    "test_blur": registry.EffectInfo(
        "test_blur",
        "Test Blur",
        (ParamSpec(id="radius", label="Radius", kind="int", default=3, min=0, max=20, step=1),),
        _identity,
    ),
    "test_grain": registry.EffectInfo(
        "test_grain",
        "Test Grain",
        (
            ParamSpec(id="amount", label="Amount", kind="float", default=0.25, min=0.0, max=1.0),
            ParamSpec(id="mono", label="Monochrome", kind="bool", default=True),
        ),
        _identity,
    ),
    "test_tint": registry.EffectInfo(
        "test_tint",
        "Test Tint",
        (
            ParamSpec(
                id="mode",
                label="Mode",
                kind="choice",
                default="warm",
                choices=("warm", "cool"),
            ),
        ),
        _identity,
    ),
}

THREE_PRE: list[EffectInstance] = [
    EffectInstance("test_blur", {"radius": 7}, True),
    EffectInstance("test_grain", {"amount": 0.4, "mono": False}, False),
    EffectInstance("test_tint", {"mode": "cool"}, True),
]
TWO_POST: list[EffectInstance] = [
    EffectInstance("test_grain", {"amount": 0.1, "mono": True}, True),
    EffectInstance("test_blur", {"radius": 0}, True),
]


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, registry.EffectInfo]:
    """Replace the effect registry with three deterministic fake effects."""
    monkeypatch.setattr(registry, "_EFFECTS", dict(FAKE_EFFECTS))
    return FAKE_EFFECTS


@pytest.fixture
def panel(qapp: QApplication, fake_registry: dict[str, registry.EffectInfo]) -> EffectsPanel:
    """Return an effects panel built on the fake registry."""
    widget = EffectsPanel()
    yield widget
    widget.close()


def _counter(panel: EffectsPanel) -> list[int]:
    """Connect a counting slot to changed and return its storage list."""
    calls: list[int] = []
    panel.changed.connect(lambda: calls.append(1))
    return calls


def _add(panel: EffectsPanel, effect_id: str) -> None:
    """Trigger the Add menu action of one effect id."""
    for action in panel.add_menu.actions():
        if action.data() == effect_id:
            action.trigger()
            return
    raise AssertionError(f"no Add action for {effect_id!r}")


def _ids(instances: list[EffectInstance]) -> list[str]:
    """Return the effect ids of a list of instances."""
    return [instance.effect_id for instance in instances]


def test_builds_two_lists_and_controls(panel: EffectsPanel) -> None:
    """The panel has both lists, the three buttons and an empty parameter form."""
    assert isinstance(panel.pre_list, EffectList)
    assert isinstance(panel.post_list, EffectList)
    assert panel.pre_list is not panel.post_list
    for widget in (panel.pre_list, panel.post_list):
        assert widget.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove
        assert widget.count() == 0
    titles = [box.title() for box in panel.findChildren(QGroupBox)]
    assert titles == [PRE_TITLE, POST_TITLE, PARAMS_TITLE]
    assert panel.add_button.text() == "Add"
    assert panel.remove_button.text() == "Remove"
    assert panel.duplicate_button.text() == "Duplicate"
    assert panel.param_label.text() == NO_SELECTION_TEXT
    assert not panel.param_form.isEnabled()
    assert not panel.remove_button.isEnabled()
    assert not panel.duplicate_button.isEnabled()


def test_add_menu_lists_registered_effects(panel: EffectsPanel) -> None:
    """The Add menu holds one action per registered effect, sorted by name."""
    assert [action.text() for action in panel.add_menu.actions()] == [
        "Test Blur",
        "Test Grain",
        "Test Tint",
    ]
    assert [action.data() for action in panel.add_menu.actions()] == [
        "test_blur",
        "test_grain",
        "test_tint",
    ]
    panel.add_menu.aboutToShow.emit()
    assert len(panel.add_menu.actions()) == 3


def test_add_appends_to_pre_list(panel: EffectsPanel) -> None:
    """Add appends a checked item with default parameters and emits changed once."""
    calls = _counter(panel)
    _add(panel, "test_blur")
    assert panel.pre_list.count() == 1
    assert panel.post_list.count() == 0
    item = panel.pre_list.item(0)
    assert item.text() == "Test Blur"
    assert item.checkState() == Qt.CheckState.Checked
    assert calls == [1]
    assert panel.param_form.values() == {"radius": 3}
    assert panel.param_label.text() == "Test Blur"
    assert panel.remove_button.isEnabled()


def test_add_targets_active_list(panel: EffectsPanel) -> None:
    """Add appends to the list that holds the current selection."""
    _add(panel, "test_blur")
    item = panel.pre_list.takeItem(0)
    panel.post_list.addItem(item)
    panel.post_list.setCurrentRow(0)
    _add(panel, "test_grain")
    assert panel.pre_list.count() == 0
    assert _ids(panel._instances(panel.post_list)) == ["test_blur", "test_grain"]


def test_duplicate_and_remove(panel: EffectsPanel) -> None:
    """Duplicate copies the selected effect below it; Remove deletes it."""
    _add(panel, "test_blur")
    _add(panel, "test_tint")
    panel.pre_list.setCurrentRow(0)
    panel.param_form.widget("radius").setValue(9)
    calls = _counter(panel)
    panel.duplicate_button.click()
    assert panel.pre_list.count() == 3
    assert _ids(panel._instances(panel.pre_list)) == ["test_blur", "test_blur", "test_tint"]
    assert panel._instances(panel.pre_list)[1].params == {"radius": 9}
    assert panel.pre_list.currentRow() == 1
    assert calls == [1]
    panel.remove_button.click()
    assert panel.pre_list.count() == 2
    assert _ids(panel._instances(panel.pre_list)) == ["test_blur", "test_tint"]
    assert calls == [1, 1]


def test_disabling_keeps_the_item(panel: EffectsPanel) -> None:
    """Unchecking an item keeps it in the list and marks it disabled."""
    _add(panel, "test_blur")
    _add(panel, "test_tint")
    calls = _counter(panel)
    panel.pre_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert panel.pre_list.count() == 2
    assert calls == [1]
    spec = PipelineSpec()
    panel.apply_to(spec)
    assert [instance.enabled for instance in spec.pre_effects] == [False, True]
    assert _ids(spec.pre_effects) == ["test_blur", "test_tint"]


def test_reorder_is_reflected_in_apply_to(panel: EffectsPanel) -> None:
    """Moving a row changes the order written by apply_to."""
    for effect_id in ("test_blur", "test_grain", "test_tint"):
        _add(panel, effect_id)
    calls = _counter(panel)
    panel.pre_list.move_item(0, 2)
    assert _ids(panel._instances(panel.pre_list)) == ["test_grain", "test_tint", "test_blur"]
    assert calls == [1]
    spec = PipelineSpec()
    panel.apply_to(spec)
    assert _ids(spec.pre_effects) == ["test_grain", "test_tint", "test_blur"]
    panel.pre_list.move_item(2, 0)
    panel.apply_to(spec)
    assert _ids(spec.pre_effects) == ["test_blur", "test_grain", "test_tint"]


def test_drop_from_another_source_is_ignored(panel: EffectsPanel) -> None:
    """A drop that does not come from the list itself is rejected."""
    _add(panel, "test_blur")
    _add(panel, "test_tint")
    event = QDropEvent(
        QPointF(2.0, 2.0),
        Qt.DropAction.MoveAction,
        QMimeData(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.pre_list.dropEvent(event)
    assert not event.isAccepted()
    assert _ids(panel._instances(panel.pre_list)) == ["test_blur", "test_tint"]


def test_round_trip_three_pre_and_two_post(panel: EffectsPanel) -> None:
    """A spec with three pre and two post effects survives load_from/apply_to."""
    spec = PipelineSpec(pre_effects=list(THREE_PRE), post_effects=list(TWO_POST))
    panel.load_from(spec)
    assert panel.pre_list.count() == 3
    assert panel.post_list.count() == 2
    assert panel.pre_list.item(1).checkState() == Qt.CheckState.Unchecked
    target = PipelineSpec(algorithm_id="bayer_4", pixel_size=3)
    panel.apply_to(target)
    assert target.pre_effects == THREE_PRE
    assert target.post_effects == TWO_POST
    assert target.algorithm_id == "bayer_4"
    assert target.pixel_size == 3


def test_load_from_does_not_emit_changed(panel: EffectsPanel) -> None:
    """Loading a spec stays silent, including the selection reset."""
    calls = _counter(panel)
    panel.load_from(PipelineSpec(pre_effects=list(THREE_PRE), post_effects=list(TWO_POST)))
    panel.load_from(PipelineSpec())
    assert calls == []
    assert panel.pre_list.count() == 0
    assert panel.post_list.count() == 0
    assert panel.param_label.text() == NO_SELECTION_TEXT


def test_selecting_an_item_shows_its_param_form(panel: EffectsPanel) -> None:
    """Selecting a row loads that effect's specs and values into the form."""
    panel.load_from(PipelineSpec(pre_effects=list(THREE_PRE), post_effects=list(TWO_POST)))
    panel.pre_list.setCurrentRow(1)
    assert panel.param_label.text() == "Test Grain"
    assert [spec.id for spec in panel.param_form.specs()] == ["amount", "mono"]
    assert panel.param_form.values() == {"amount": 0.4, "mono": False}
    panel.post_list.setCurrentRow(0)
    assert panel.pre_list.currentItem() is None
    assert panel.param_label.text() == "Test Grain"
    assert panel.param_form.values() == {"amount": 0.1, "mono": True}


def test_editing_the_form_updates_the_item(panel: EffectsPanel) -> None:
    """A form edit is stored in the selected item and emits changed once."""
    panel.load_from(PipelineSpec(pre_effects=list(THREE_PRE)))
    panel.pre_list.setCurrentRow(0)
    calls = _counter(panel)
    panel.param_form.widget("radius").setValue(11)
    assert calls == [1]
    spec = PipelineSpec()
    panel.apply_to(spec)
    assert spec.pre_effects[0].params == {"radius": 11}
    assert spec.pre_effects[1] == THREE_PRE[1]


def test_float_and_choice_edits_reach_apply_to(panel: EffectsPanel) -> None:
    """Float and choice editors also write through to the spec."""
    panel.load_from(PipelineSpec(pre_effects=list(THREE_PRE)))
    panel.pre_list.setCurrentRow(1)
    panel.param_form.widget("amount").findChild(QDoubleSpinBox).setValue(0.75)
    panel.pre_list.setCurrentRow(2)
    panel.param_form.widget("mode").setCurrentIndex(0)
    spec = PipelineSpec()
    panel.apply_to(spec)
    assert spec.pre_effects[1].params == {"amount": 0.75, "mono": False}
    assert spec.pre_effects[2].params == {"mode": "warm"}


def test_unknown_effect_id_is_skipped(panel: EffectsPanel) -> None:
    """An effect id missing from the registry is dropped instead of raising."""
    spec = PipelineSpec(
        pre_effects=[EffectInstance("nope", {}, True), EffectInstance("test_blur", {}, True)]
    )
    panel.load_from(spec)
    assert _ids(panel._instances(panel.pre_list)) == ["test_blur"]


def test_apply_to_empty_panel_clears_effect_lists(panel: EffectsPanel) -> None:
    """An empty panel writes empty effect lists and leaves other fields alone."""
    spec = PipelineSpec(pre_effects=list(THREE_PRE), post_effects=list(TWO_POST))
    panel.apply_to(spec)
    assert spec.pre_effects == []
    assert spec.post_effects == []
    assert spec.algorithm_id == "floyd_steinberg"


def test_int_editor_is_a_spinbox(panel: EffectsPanel) -> None:
    """The int parameter of the selected effect uses a spinbox editor."""
    _add(panel, "test_blur")
    assert isinstance(panel.param_form.widget("radius"), QSpinBox)


def test_real_registry_populates_the_add_menu(qapp: QApplication) -> None:
    """The panel registers the built-in effects itself, so the menu is never empty."""
    registered = registry.list_effects()
    if not registered:
        pytest.skip("no effects registered")
    widget = EffectsPanel()
    assert [action.data() for action in widget.add_menu.actions()] == [
        info.id for info in registered
    ]
    widget.close()
