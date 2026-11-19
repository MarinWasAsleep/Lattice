"""Tests for the palette panel."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QMimeData, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lattice.modes.dither.ui.palette_panel import SWATCH_MIME, PalettePanel  # noqa: E402
from lattice.palettes.builtin import builtin_names  # noqa: E402
from lattice.palettes.extract import extract_palette  # noqa: E402
from lattice.palettes.io import MAX_COLORS, hex_list, load_palette  # noqa: E402
from lattice.palettes.library import get_library, library_names  # noqa: E402
from lattice.pipeline import PaletteSpec, PipelineSpec, render  # noqa: E402
from lattice.ui import worker as worker_module  # noqa: E402

import lattice.dither  # noqa: E402, F401  isort:skip

CUSTOM = ["#FF0000", "#00FF00", "#0000FF"]


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def panel(qapp: QApplication) -> PalettePanel:
    """Return a palette panel closed after the test."""
    widget = PalettePanel()
    yield widget
    widget.close()


def _spec(**kwargs: object) -> PipelineSpec:
    """Return a pipeline spec whose palette is built from kwargs."""
    return PipelineSpec(palette=PaletteSpec(**kwargs))


def _counter(panel: PalettePanel) -> list[int]:
    """Connect a counting slot to changed and return its storage list."""
    calls: list[int] = []
    panel.changed.connect(lambda: calls.append(1))
    return calls


def _wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Spin the event loop until predicate is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        QApplication.processEvents()
        time.sleep(0.005)
    return bool(predicate())


def _quad_image() -> np.ndarray:
    """Return a 16x16 image with four distinct colour quadrants."""
    img = np.zeros((16, 16, 3), dtype=np.float32)
    img[:8, :8] = (1.0, 0.0, 0.0)
    img[:8, 8:] = (0.0, 1.0, 0.0)
    img[8:, :8] = (0.0, 0.0, 1.0)
    img[8:, 8:] = (1.0, 1.0, 1.0)
    return img


def _applied(panel: PalettePanel) -> PaletteSpec:
    """Return the palette spec the panel writes into a fresh pipeline spec."""
    spec = PipelineSpec()
    panel.apply_to(spec)
    return spec.palette


def test_defaults_follow_the_pipeline_spec(panel: PalettePanel) -> None:
    """A fresh panel shows the default palette spec and needs an image to extract."""
    assert panel.source_buttons["builtin"].isChecked()
    assert panel.builtin_combo.currentText() == "bw"
    assert panel.extract_k.value() == 8
    assert panel.extract_k.minimum() == 2
    assert panel.extract_method.currentText() == "kmeans"
    assert panel.extract_button.isEnabled() is False
    assert panel.colors() == []
    assert _applied(panel) == PaletteSpec()


def test_builtin_combo_lists_every_palette_with_a_swatch(panel: PalettePanel) -> None:
    """The combo holds one entry per built-in palette, each with a swatch icon."""
    combo = panel.builtin_combo
    names = [combo.itemText(index) for index in range(combo.count())]
    assert names == builtin_names()
    assert all(not combo.itemIcon(index).isNull() for index in range(combo.count()))


def test_load_from_is_silent(panel: PalettePanel) -> None:
    """Loading a spec never emits changed."""
    calls = _counter(panel)
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    panel.load_from(_spec(source="extracted", extract_k=5))
    panel.load_from(_spec(source="builtin", name="ega"))
    assert calls == []


def test_round_trip_builtin(panel: PalettePanel) -> None:
    """A built-in palette survives load_from and apply_to unchanged."""
    spec = _spec(source="builtin", name="pico8")
    panel.load_from(spec)
    assert panel.builtin_combo.currentText() == "pico8"
    assert _applied(panel) == spec.palette


def test_round_trip_extracted(panel: PalettePanel) -> None:
    """An extracted palette spec survives load_from and apply_to unchanged."""
    spec = _spec(source="extracted", extract_k=5, extract_method="median_cut")
    panel.load_from(spec)
    assert panel.extract_k.value() == 5
    assert panel.extract_method.currentText() == "median_cut"
    assert _applied(panel) == spec.palette


def test_round_trip_custom(panel: PalettePanel) -> None:
    """A custom palette survives load_from and apply_to unchanged."""
    spec = _spec(source="custom", colors=CUSTOM)
    panel.load_from(spec)
    assert panel.colors() == CUSTOM
    assert len(panel.swatches) == len(CUSTOM)
    assert _applied(panel) == spec.palette


def test_unknown_builtin_name_falls_back(panel: PalettePanel) -> None:
    """An unknown built-in name falls back to the default palette."""
    panel.load_from(_spec(name="not_a_palette"))
    assert panel.builtin_combo.currentText() == "bw"
    assert _applied(panel).name == "bw"


def test_source_radio_emits_changed_and_seeds_custom(panel: PalettePanel) -> None:
    """Checking Custom emits once and seeds the grid from the built-in palette."""
    calls = _counter(panel)
    panel.source_buttons["custom"].setChecked(True)
    assert len(calls) == 1
    assert _applied(panel).source == "custom"
    assert len(panel.colors()) >= 2


def test_builtin_combo_emits_changed(panel: PalettePanel) -> None:
    """Choosing another built-in palette emits changed once."""
    calls = _counter(panel)
    panel.builtin_combo.setCurrentIndex(panel.builtin_combo.findText("ega"))
    assert len(calls) == 1
    assert _applied(panel).name == "ega"


def test_extract_button_needs_a_source_image(panel: PalettePanel) -> None:
    """Extract stays disabled until an image is supplied."""
    panel.source_buttons["extracted"].setChecked(True)
    assert panel.extract_button.isEnabled() is False
    panel.set_source_image(_quad_image())
    assert panel.extract_button.isEnabled() is True


def test_extract_without_image_reports_an_error(panel: PalettePanel) -> None:
    """Extracting without an image leaves the palette alone and reports the problem."""
    panel.source_buttons["extracted"].setChecked(True)
    calls = _counter(panel)
    panel.extract_now()
    assert calls == []
    assert panel.error_label.text() != ""
    assert panel.colors() == []


def test_extraction_runs_off_the_gui_thread(
    panel: PalettePanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extract returns at once, runs on a helper thread and fills the grid with its result."""
    threads: list[str] = []

    def slow_extract(image: np.ndarray, k: int, method: str) -> np.ndarray:
        threads.append(threading.current_thread().name)
        time.sleep(0.05)
        return extract_palette(image, k, method)

    monkeypatch.setattr(worker_module, "extract_palette", slow_extract)
    img = _quad_image()
    panel.set_source_image(img)
    panel.source_buttons["extracted"].setChecked(True)
    panel.extract_k.setValue(4)
    calls = _counter(panel)
    panel.extract_button.click()
    assert panel.colors() == []
    expected = hex_list(extract_palette(img, 4, "kmeans"))
    assert _wait_until(lambda: panel.colors() == expected)
    assert len(expected) == 4
    assert _applied(panel).source == "custom"
    assert _applied(panel).colors == expected
    assert len(calls) == 1
    assert panel.error_label.text() == ""
    assert threads and threads[0] != threading.main_thread().name


def test_extract_controls_emit_changed(panel: PalettePanel) -> None:
    """Editing k or the extraction method emits changed once, and load_from stays silent."""
    panel.load_from(_spec(source="extracted", extract_k=4, extract_method="kmeans"))
    calls = _counter(panel)
    panel.extract_k.setValue(6)
    assert len(calls) == 1
    panel.extract_method.setCurrentIndex(panel.extract_method.findText("median_cut"))
    assert len(calls) == 2
    applied = _applied(panel)
    assert applied.extract_k == 6
    assert applied.extract_method == "median_cut"
    panel.load_from(_spec(source="extracted", extract_k=8, extract_method="kmeans"))
    assert len(calls) == 2


def test_extract_k_cannot_go_below_two(panel: PalettePanel) -> None:
    """The k spinbox clamps to the contract range 2..32."""
    panel.extract_k.setValue(1)
    assert panel.extract_k.value() == 2
    panel.extract_k.setValue(99)
    assert panel.extract_k.value() == 32


def test_swatch_click_edits_the_colour(
    panel: PalettePanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A left click asks for a colour and replaces the swatch."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    monkeypatch.setattr(panel, "_ask_color", lambda initial: "#123456")
    calls = _counter(panel)
    QTest.mouseClick(panel.swatches[0], Qt.MouseButton.LeftButton)
    assert panel.colors()[0] == "#123456"
    assert len(calls) == 1


def test_cancelled_colour_dialog_keeps_the_swatch(
    panel: PalettePanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling the colour dialog changes nothing and emits nothing."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    monkeypatch.setattr(panel, "_ask_color", lambda initial: None)
    calls = _counter(panel)
    QTest.mouseClick(panel.swatches[1], Qt.MouseButton.LeftButton)
    assert panel.colors() == CUSTOM
    assert calls == []


def test_right_click_removes_a_swatch(panel: PalettePanel) -> None:
    """A right click removes the swatch and emits changed once."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    calls = _counter(panel)
    QTest.mouseClick(panel.swatches[1], Qt.MouseButton.RightButton)
    assert panel.colors() == [CUSTOM[0], CUSTOM[2]]
    assert len(panel.swatches) == 2
    assert len(calls) == 1


def test_removal_below_two_colours_is_prevented(panel: PalettePanel) -> None:
    """The palette never drops below two colours."""
    panel.load_from(_spec(source="custom", colors=CUSTOM[:2]))
    calls = _counter(panel)
    QTest.mouseClick(panel.swatches[0], Qt.MouseButton.RightButton)
    assert panel.colors() == CUSTOM[:2]
    assert calls == []
    assert panel.error_label.text() != ""


def test_add_button_appends_a_colour(panel: PalettePanel) -> None:
    """The add button appends one swatch and emits changed once."""
    panel.load_from(_spec(source="custom", colors=CUSTOM[:2]))
    calls = _counter(panel)
    panel.add_button.click()
    assert len(panel.colors()) == 3
    assert len(panel.swatches) == 3
    assert len(calls) == 1


def test_add_button_stops_at_256_colours(panel: PalettePanel) -> None:
    """A full palette disables the add button and refuses more colours."""
    colors = [f"#{value:02X}{value:02X}{value:02X}" for value in range(MAX_COLORS)]
    panel.load_from(_spec(source="custom", colors=colors))
    assert len(panel.colors()) == MAX_COLORS
    assert panel.add_button.isEnabled() is False
    panel.add_button.click()
    assert len(panel.colors()) == MAX_COLORS


def test_swatches_are_disabled_outside_custom(panel: PalettePanel) -> None:
    """Swatches are only editable while the Custom source is selected."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    assert all(swatch.isEnabled() for swatch in panel.swatches)
    panel.source_buttons["builtin"].setChecked(True)
    assert not any(swatch.isEnabled() for swatch in panel.swatches)


def test_import_hex_file(panel: PalettePanel, tmp_path: Path) -> None:
    """Importing a .hex file fills the grid and switches to Custom."""
    path = tmp_path / "palette.hex"
    path.write_text("#FF0000\n00FF00\n; comment\n0000FF\n", encoding="utf-8")
    calls = _counter(panel)
    panel.import_palette(path)
    assert panel.colors() == CUSTOM
    assert _applied(panel).source == "custom"
    assert len(calls) == 1


def test_import_gpl_file(panel: PalettePanel, tmp_path: Path) -> None:
    """Importing a GIMP .gpl file fills the grid."""
    path = tmp_path / "palette.gpl"
    path.write_text(
        "GIMP Palette\nName: Test\nColumns: 3\n#\n255 0 0\tRed\n0 255 0\tGreen\n",
        encoding="utf-8",
    )
    panel.import_palette(path)
    assert panel.colors() == ["#FF0000", "#00FF00"]


def test_import_of_a_broken_file_reports_an_error(panel: PalettePanel, tmp_path: Path) -> None:
    """A malformed palette file leaves the panel untouched and shows the error."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    path = tmp_path / "broken.hex"
    path.write_text("ZZZZZZ\n", encoding="utf-8")
    calls = _counter(panel)
    panel.import_palette(path)
    assert panel.colors() == CUSTOM
    assert calls == []
    assert panel.error_label.text() != ""


def test_export_round_trip(panel: PalettePanel, tmp_path: Path) -> None:
    """Exporting custom colours to .hex and .gpl reloads to the same palette."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    for suffix in (".hex", ".gpl"):
        path = tmp_path / f"out{suffix}"
        panel.export_palette(path)
        assert hex_list(load_palette(path)) == CUSTOM
    assert panel.error_label.text() == ""


def test_export_of_a_builtin_palette(panel: PalettePanel, tmp_path: Path) -> None:
    """Exporting while a built-in palette is selected writes that palette."""
    path = tmp_path / "bw.hex"
    panel.export_palette(path)
    assert hex_list(load_palette(path)) == ["#000000", "#FFFFFF"]


def test_export_without_colours_reports_an_error(panel: PalettePanel, tmp_path: Path) -> None:
    """Exporting an empty custom palette writes nothing and reports the problem."""
    panel.load_from(_spec(source="custom", colors=[]))
    path = tmp_path / "empty.hex"
    panel.export_palette(path)
    assert path.exists() is False
    assert panel.error_label.text() != ""


def test_set_source_image_rejects_a_bad_shape(panel: PalettePanel) -> None:
    """A source image must be an (H, W, 3) array."""
    with pytest.raises(ValueError):
        panel.set_source_image(np.zeros((4, 4), dtype=np.float32))


def test_apply_to_leaves_other_spec_fields_alone(panel: PalettePanel) -> None:
    """apply_to only writes the palette section of the pipeline spec."""
    spec = PipelineSpec(brightness=0.5, algorithm_id="ordered", pixel_size=4)
    panel.apply_to(spec)
    assert spec.brightness == 0.5
    assert spec.algorithm_id == "ordered"
    assert spec.pixel_size == 4
    assert spec.palette == PaletteSpec()


def test_applied_specs_render_for_every_source(panel: PalettePanel) -> None:
    """Each source type produces a spec the pipeline renders without error."""
    img = _quad_image()
    panel.set_source_image(img)
    specs = (
        _spec(source="builtin", name="ega"),
        _spec(source="extracted", extract_k=4),
        _spec(source="custom", colors=CUSTOM),
    )
    for spec in specs:
        panel.load_from(spec)
        applied = PipelineSpec()
        panel.apply_to(applied)
        rgb8 = render(img, applied)
        assert rgb8.shape == img.shape
        assert rgb8.dtype == np.uint8


def test_middle_click_toggles_the_lock(panel: PalettePanel) -> None:
    """A middle click locks a swatch and a second one unlocks it."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    calls = _counter(panel)
    QTest.mouseClick(panel.swatches[1], Qt.MouseButton.MiddleButton)
    assert panel.locked() == ["#00FF00"]
    assert panel.swatches[1].is_locked()
    assert calls
    QTest.mouseClick(panel.swatches[1], Qt.MouseButton.MiddleButton)
    assert panel.locked() == []
    assert not panel.swatches[1].is_locked()


def test_lock_survives_a_round_trip(panel: PalettePanel) -> None:
    """locked and order are written into the spec and read back unchanged."""
    locked = ["#FF0000", "#0000FF"]
    panel.load_from(_spec(source="custom", colors=CUSTOM, locked=locked, order=[2, 0, 1]))
    applied = _applied(panel)
    assert applied.locked == locked
    assert applied.order == [2, 0, 1]
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    panel.load_from(PipelineSpec(palette=applied))
    assert panel.locked() == locked
    assert panel.order() == [2, 0, 1]


def test_removing_a_swatch_drops_its_lock(panel: PalettePanel) -> None:
    """Removing a colour drops its lock and keeps the locks of the other colours."""
    panel.load_from(_spec(source="custom", colors=CUSTOM, locked=["#FF0000", "#0000FF"]))
    QTest.mouseClick(panel.swatches[0], Qt.MouseButton.RightButton)
    assert panel.locked() == ["#0000FF"]


def test_a_duplicated_locked_colour_keeps_its_lock(panel: PalettePanel) -> None:
    """Removing one of two identical swatches leaves the colour locked."""
    colors = ["#FF0000", "#FF0000", "#0000FF"]
    panel.load_from(_spec(source="custom", colors=colors, locked=["#FF0000"]))
    QTest.mouseClick(panel.swatches[0], Qt.MouseButton.RightButton)
    assert panel.locked() == ["#FF0000"]
    assert panel.swatches[0].is_locked()


def test_editing_a_locked_swatch_moves_the_lock(panel: PalettePanel, monkeypatch) -> None:
    """Recolouring a locked swatch locks the new colour and releases the old one."""
    panel.load_from(_spec(source="custom", colors=CUSTOM, locked=["#FF0000"]))
    monkeypatch.setattr(panel, "_ask_color", lambda _initial: "#123456")
    panel._on_swatch_clicked(0)
    assert panel.locked() == ["#123456"]
    assert panel.swatches[0].is_locked()


def test_reorder_changes_order_but_not_the_render(panel: PalettePanel) -> None:
    """Dragging a swatch permutes order and leaves the rendered image identical."""
    img = _quad_image()
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    before = render(img, PipelineSpec(palette=_applied(panel)))
    panel._on_swatch_dropped(0, 2)
    assert panel.order() == [1, 2, 0]
    assert panel.colors() == CUSTOM
    after = render(img, PipelineSpec(palette=_applied(panel)))
    assert np.array_equal(before, after)


def test_display_indices_follow_the_order(panel: PalettePanel) -> None:
    """The grid shows the colours in display order, not in natural order."""
    panel.load_from(_spec(source="custom", colors=CUSTOM, order=[2, 0, 1]))
    assert panel.display_indices() == [2, 0, 1]
    assert [swatch.color() for swatch in panel.swatches] == [CUSTOM[2], CUSTOM[0], CUSTOM[1]]


def test_invalid_order_falls_back_to_natural(panel: PalettePanel) -> None:
    """A spec whose order is not a permutation is shown in natural order."""
    panel.load_from(_spec(source="custom", colors=CUSTOM, order=[0, 0, 1]))
    assert panel.order() == []
    assert panel.display_indices() == [0, 1, 2]


def test_library_combo_lists_every_palette(panel: PalettePanel) -> None:
    """The library picker offers a placeholder plus every shipped palette."""
    names = [panel.library_combo.itemData(i) for i in range(panel.library_combo.count())]
    assert names[0] == ""
    assert names[1:] == library_names()


def test_library_picker_adopts_the_palette(panel: PalettePanel) -> None:
    """Choosing a library palette switches the panel to Custom with its colours."""
    index = panel.library_combo.findData("nord")
    panel._on_library_chosen(index)
    assert panel.source_buttons["custom"].isChecked()
    assert panel.colors() == hex_list(get_library("nord"))
    assert panel.library_combo.currentIndex() == 0


class _FakeDrop:
    """Minimal stand-in for a QDropEvent carrying a swatch payload."""

    def __init__(self, payload: bytes | None) -> None:
        self._mime = QMimeData()
        if payload is not None:
            self._mime.setData(SWATCH_MIME, payload)
        self.accepted = False

    def mimeData(self) -> QMimeData:
        """Return the carried mime data."""
        return self._mime

    def acceptProposedAction(self) -> None:
        """Record that the drop was accepted."""
        self.accepted = True


def test_drop_event_reports_the_source_position(panel: PalettePanel) -> None:
    """A dropped swatch payload is decoded into the display position it came from."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    seen: list[int] = []
    panel.swatches[2].dropped.connect(seen.append)
    event = _FakeDrop(b"0")
    panel.swatches[2].dropEvent(event)
    assert seen == [0]
    assert event.accepted


def test_drop_event_ignores_foreign_payloads(panel: PalettePanel) -> None:
    """A drop that does not carry a swatch is ignored."""
    panel.load_from(_spec(source="custom", colors=CUSTOM))
    seen: list[int] = []
    panel.swatches[2].dropped.connect(seen.append)
    event = _FakeDrop(None)
    panel.swatches[2].dropEvent(event)
    assert seen == []
    assert not event.accepted
