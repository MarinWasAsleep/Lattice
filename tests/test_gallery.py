"""Card L21: the reference gallery, preset interchange and the v3 starter set."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtCore import Qt, QThread  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget  # noqa: E402

import lattice_core.dither  # noqa: E402,F401  (registers every algorithm)
import lattice_core.effects  # noqa: E402,F401  (registers every effect)
import lattice_glitch.presets as glitch_presets  # noqa: E402
import lattice_glyph.document as glyph_doc  # noqa: E402
import lattice_glyph.presets as glyph_presets  # noqa: E402
from lattice_core import gallery as core_gallery  # noqa: E402
from lattice_core.gallery import (  # noqa: E402
    MAX_GALLERY_BYTES,
    PLACEHOLDER_COLOR,
    GalleryEntry,
    GallerySheet,
    gallery_entries,
    gallery_png_bytes,
    load_for_app,
    reference_image,
    render_for_app,
    render_gallery,
    save_gallery,
    starter_preset_dir,
    starter_presets,
)
from lattice_core.pipeline import PaletteSpec, PipelineSpec, render  # noqa: E402
from lattice_core.preset import from_json, to_json, to_pipeline_spec  # noqa: E402
from lattice_core.presets import save_preset as save_v2_preset  # noqa: E402
from lattice_core.registry import get_algorithm, get_effect, list_algorithms  # noqa: E402
from lattice_core.renderers import list_renderers  # noqa: E402
from lattice_core.types import RGB8  # noqa: E402
from lattice_core.ui import gallery as ui_gallery  # noqa: E402
from lattice_core.ui.gallery import THUMB_SIZE, GalleryWorker, ReferenceGallery  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
APPS = ("dither", "glyph", "glitch")
# Renderers each app exposes: dither/glitch draw pixels, glyph offers the whole registry.
APP_AVAILABLE: dict[str, set[str] | None] = {"dither": {"pixel"}, "glitch": {"pixel"},
                                             "glyph": None}


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture(scope="module")
def ref() -> np.ndarray:
    """The deterministic reference image every accept item renders on."""
    return reference_image()


def _wait_until(predicate: Callable[[], bool], timeout: float = 120.0) -> bool:
    """Process GUI events until predicate holds or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(0.005)
    return predicate()


def _all_ready(widget: ReferenceGallery) -> bool:
    """Return True when every cell of the gallery shows a thumbnail."""
    return all(cell.has_thumbnail() for cell in widget.cells())


def _assert_rgb8(rgb8: RGB8, shape: tuple[int, ...]) -> None:
    """Assert one render result is a uint8 RGB image of the expected shape."""
    assert rgb8.dtype == np.uint8
    assert rgb8.shape == shape
    assert len(np.unique(rgb8.reshape(-1, 3), axis=0)) > 1


def _core_errors(path: Path) -> list[str]:
    """Validate a dither-tagged v3 preset against the core registries, glyph-style."""
    spec = to_pipeline_spec(from_json(path.read_text(encoding="utf-8"), app="dither"))
    errors: list[str] = []
    if spec.renderer not in list_renderers():
        errors.append(f"renderer {spec.renderer!r} is not registered")
    if (spec.algorithm_id is None) != (spec.palette is None):
        errors.append("continuous mode needs algorithm and palette both null")
    checks = [(get_algorithm, spec.algorithm_id, "algorithm")]
    checks += [(get_effect, i.effect_id, "effect") for i in spec.pre_effects + spec.post_effects]
    for lookup, ident, kind in checks:
        if ident is None:
            continue
        try:
            lookup(ident)
        except KeyError:
            errors.append(f"{kind} {ident!r} is not registered")
    return errors


@contextmanager
def _open_gallery() -> Iterator[ReferenceGallery]:
    """Yield a reference gallery, stopped and closed afterwards."""
    widget = ReferenceGallery()
    try:
        yield widget
    finally:
        widget.shutdown()
        widget.close()


def test_the_reference_image_is_deterministic_and_valid(ref: np.ndarray) -> None:
    assert ref.shape == (200, 200, 3) and ref.dtype == np.float32
    assert 0.0 <= float(ref.min()) and float(ref.max()) <= 1.0
    assert np.array_equal(ref, reference_image())
    assert np.array_equal(reference_image(64), reference_image(64))


def test_the_entries_cover_every_registered_algorithm_and_renderer() -> None:
    entries = gallery_entries()
    algorithms = [entry for entry in entries if entry.kind == "algorithm"]
    renderers = [entry for entry in entries if entry.kind == "renderer"]
    assert [e.id for e in algorithms] == [f"algorithm:{i.id}" for i in list_algorithms()]
    assert [e.id for e in renderers] == [f"renderer:{n}" for n in list_renderers()]
    assert len(entries) == len(list_algorithms()) + len(list_renderers())
    assert all(entry.spec.renderer == "pixel" for entry in algorithms)
    assert {entry.spec.renderer for entry in renderers} == set(list_renderers())


def test_the_gallery_renders_every_cell_without_raising(ref: np.ndarray) -> None:
    sheet = render_gallery(ref)
    assert sheet.warnings == []
    assert len(sheet.cells) == len(gallery_entries())
    for cell in sheet.cells:
        _assert_rgb8(cell.rgb8, (128, 128, 3))
    assert sheet.image.dtype == np.uint8 and sheet.image.ndim == 3
    assert np.array_equal(sheet.image, render_gallery(ref).image)


def test_a_broken_entry_yields_a_warning_and_a_placeholder(monkeypatch: pytest.MonkeyPatch,
                                                          ref: np.ndarray) -> None:
    healthy = GalleryEntry("algorithm:threshold", "Threshold", "algorithm",
                           PipelineSpec(algorithm_id="threshold", pixel_size=2,
                                        palette=PaletteSpec(source="builtin", name="bw")))
    broken = GalleryEntry("algorithm:nope", "Nope", "algorithm",
                          PipelineSpec(algorithm_id="does_not_exist"))
    monkeypatch.setattr(core_gallery, "gallery_entries", lambda **_kw: [healthy, broken])
    sheet = render_gallery(ref)
    assert len(sheet.cells) == 2
    assert len(sheet.warnings) == 1 and "does_not_exist" in sheet.warnings[0]
    assert np.all(sheet.cells[1].rgb8 == np.array(PLACEHOLDER_COLOR, dtype=np.uint8))
    _assert_rgb8(sheet.cells[0].rgb8, (128, 128, 3))


def test_save_gallery_writes_one_png_under_4mb(tmp_path: Path, ref: np.ndarray) -> None:
    target = save_gallery(tmp_path / "gallery.png", ref)
    assert list(tmp_path.iterdir()) == [target]
    payload = target.read_bytes()
    assert payload[:8] == PNG_MAGIC
    assert len(payload) < MAX_GALLERY_BYTES
    with PILImage.open(target) as image:
        assert image.format == "PNG"
        sheet = render_gallery(ref)
        assert image.size == (sheet.image.shape[1], sheet.image.shape[0])


def test_the_png_budget_downcales_an_oversized_sheet() -> None:
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 256, (2048, 2048, 3), dtype=np.uint8)
    payload = gallery_png_bytes(GallerySheet([], noise))
    assert payload[:8] == PNG_MAGIC
    assert len(payload) <= MAX_GALLERY_BYTES


def test_a_glyph_preset_loads_in_glitch_with_a_warning_and_renders(
        tmp_path: Path, ref: np.ndarray) -> None:
    spec = glyph_presets.default_spec()
    path = glyph_presets.save_preset(tmp_path / "glyph.json",
                                     glyph_presets.to_preset(spec, name="cross"))
    read = glitch_presets.read_preset(path)  # a mismatch is not an error for the app
    assert read.app == "glyph"
    loaded = load_for_app(path, "glitch", available=APP_AVAILABLE["glitch"])
    assert any("glyph_ramp" in warning for warning in loaded.warnings)
    assert loaded.renderer["name"] == "pixel"
    result = render_for_app(ref, loaded, "glitch")
    _assert_rgb8(result.rgb8, ref.shape)
    assert result.renderer == "pixel"
    assert result.warnings and any("glyph_ramp" in warning for warning in result.warnings)
    assert np.array_equal(result.rgb8, render(ref, to_pipeline_spec(loaded)))


def test_dither_presets_load_in_glyph_and_render_with_pixel(tmp_path: Path,
                                                            ref: np.ndarray) -> None:
    v1 = load_for_app(ROOT / "presets" / "01_gameboy.json", "glyph")
    assert v1.renderer["name"] == "pixel"
    spec = to_pipeline_spec(v1)
    assert spec.renderer == "pixel"
    _assert_rgb8(glyph_doc.render_rgb8(ref, spec), ref.shape)
    _assert_rgb8(render_for_app(ref, v1, "glyph").rgb8, ref.shape)
    path = tmp_path / "dither_v2.json"
    save_v2_preset(path, PipelineSpec(pixel_size=2,
                                      palette=PaletteSpec(source="builtin", name="gameboy")))
    v2 = load_for_app(path, "glyph")
    assert v2.renderer["name"] == "pixel"
    result = render_for_app(ref, v2, "glyph")
    assert result.renderer == "pixel"
    _assert_rgb8(result.rgb8, ref.shape)


def test_a_glitch_preset_loads_in_glyph_and_renders(ref: np.ndarray) -> None:
    path = starter_preset_dir() / "glitch_01_vhs_soft.json"
    loaded = load_for_app(path, "glyph", available=APP_AVAILABLE["glyph"])
    assert loaded.renderer["name"] == "pixel"
    _assert_rgb8(render_for_app(ref, loaded, "glyph").rgb8, ref.shape)


def test_an_unknown_renderer_falls_back_with_a_warning(tmp_path: Path,
                                                       ref: np.ndarray) -> None:
    path = tmp_path / "future.json"
    path.write_text(json.dumps({"version": 3, "app": "glyph",
                                "renderer": {"name": "future_renderer"}}), encoding="utf-8")
    loaded = load_for_app(path, "dither", available={"pixel"})
    assert loaded.renderer["name"] == "pixel"
    assert any("future_renderer" in warning for warning in loaded.warnings)
    _assert_rgb8(render_for_app(ref, loaded, "dither").rgb8, ref.shape)


def test_the_starter_set_spans_the_three_apps_with_at_least_12_presets() -> None:
    paths = starter_presets()
    assert len(paths) >= 12
    assert all(path.parent == starter_preset_dir() for path in paths)
    presets = [from_json(path.read_text(encoding="utf-8")) for path in paths]
    apps = Counter(preset.app for preset in presets)
    assert set(apps) == set(APPS)
    assert all(count >= 3 for count in apps.values())
    assert all(preset.version == 3 for preset in presets)


def test_every_starter_preset_validates_in_its_own_app(ref: np.ndarray) -> None:
    for path in starter_presets():
        app = from_json(path.read_text(encoding="utf-8")).app
        if app == "glyph":
            report = glyph_presets.validate(path)
            assert report.ok and report.errors == [], (path.name, report.errors)
        elif app == "glitch":
            report = glitch_presets.validate(path)
            assert report.ok and report.errors == [], (path.name, report.errors)
        else:
            assert _core_errors(path) == [], path.name
        _assert_rgb8(render_for_app(ref, path, app).rgb8, ref.shape)


def test_every_starter_preset_circulates_to_the_other_apps(ref: np.ndarray) -> None:
    for path in starter_presets():
        own = from_json(path.read_text(encoding="utf-8")).app
        for target in APPS:
            if target == own:
                continue
            loaded = load_for_app(path, target, available=APP_AVAILABLE[target])
            assert loaded.warnings, (path.name, target)
            result = render_for_app(ref, loaded, target)
            _assert_rgb8(result.rgb8, ref.shape)
            assert result.renderer in list_renderers()


def test_a_starter_preset_round_trips_with_unknown_keys_preserved() -> None:
    data = json.loads(starter_presets()[0].read_text(encoding="utf-8"))
    data["x_future"] = {"flag": True}
    data["renderer"]["style"]["x_option"] = 1
    preset = from_json(json.dumps(data))
    again = from_json(to_json(preset))
    assert again.extra == {"x_future": {"flag": True}}
    assert again.renderer["style"]["x_option"] == 1
    assert to_json(again) == to_json(preset)


def test_the_widget_shows_one_cell_per_entry(qapp: QApplication) -> None:
    with _open_gallery() as widget:
        assert len(widget.cells()) == len(gallery_entries())
        assert [c.entry_id for c in widget.cells()] == [e.id for e in gallery_entries()]
        assert all(not cell.has_thumbnail() for cell in widget.cells())
        assert _wait_until(lambda: _all_ready(widget)), "thumbnails never arrived"
        assert [c.name_label.text() for c in widget.cells()] == [e.label for e in widget.entries()]


def test_the_widget_renders_on_a_new_source(qapp: QApplication,
                                            rng: np.random.Generator) -> None:
    with _open_gallery() as widget:
        assert _wait_until(lambda: _all_ready(widget))
        widget.set_source(rng.random((96, 128, 3), dtype=np.float32))
        assert all(not cell.has_thumbnail() for cell in widget.cells())
        assert _wait_until(lambda: _all_ready(widget))
        widget.set_source(None)
        assert _wait_until(lambda: _all_ready(widget))


def test_the_widget_save_button_writes_one_small_png(
        qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _open_gallery() as widget:
        assert _wait_until(lambda: _all_ready(widget))
        target = tmp_path / "ui_gallery.png"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
        QTest.mouseClick(widget.save_button, Qt.MouseButton.LeftButton)
        assert target.read_bytes()[:8] == PNG_MAGIC
        assert target.stat().st_size < MAX_GALLERY_BYTES
        assert list(tmp_path.iterdir()) == [target]
        assert widget.save_png(tmp_path / "direct.png").read_bytes() == target.read_bytes()


def test_the_worker_runs_off_the_gui_thread(qapp: QApplication,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    render_threads: list[QThread] = []
    original = ui_gallery.render_entry_thumbnail

    def spy(spec: PipelineSpec, source: np.ndarray, size: int = THUMB_SIZE) -> np.ndarray:
        render_threads.append(QThread.currentThread())
        return original(spec, source, size)

    monkeypatch.setattr(ui_gallery, "render_entry_thumbnail", spy)
    with _open_gallery() as widget:
        assert _wait_until(lambda: _all_ready(widget))
        worker = widget._worker
        assert isinstance(worker, GalleryWorker)
        assert not isinstance(worker, QWidget)
        assert worker.thread() is not qapp.thread()
        assert render_threads and all(thread is not qapp.thread() for thread in render_threads)


def test_a_failing_thumbnail_keeps_the_placeholder(qapp: QApplication,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(spec: PipelineSpec, source: np.ndarray, size: int = THUMB_SIZE) -> np.ndarray:
        raise RuntimeError("no render")

    monkeypatch.setattr(ui_gallery, "render_entry_thumbnail", boom)
    with _open_gallery() as widget:
        assert _wait_until(lambda: "no render" in widget.cells()[0].toolTip())
        assert all(not cell.has_thumbnail() for cell in widget.cells())
        assert len(widget.cells()) == len(gallery_entries())


def test_clicking_a_cell_reports_its_entry_and_shutdown_is_idempotent(
        qapp: QApplication) -> None:
    with _open_gallery() as widget:
        assert _wait_until(lambda: _all_ready(widget))
        chosen: list[str] = []
        widget.cell_chosen.connect(chosen.append)
        QTest.mouseClick(widget.cells()[1], Qt.MouseButton.LeftButton)
        assert chosen == [widget.cells()[1].entry_id]
        widget.shutdown()
        widget.shutdown()


def _import_roots(path: Path) -> set[str]:
    """Return the top-level package names a Python file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_gallery_modules_respect_the_core_packaging_rules() -> None:
    apps = {"lattice_dither", "lattice_glyph", "lattice_glitch"}
    base = _import_roots(ROOT / "lattice_core" / "gallery.py")
    assert not base & (apps | {"PySide6"})
    assert not _import_roots(ROOT / "lattice_core" / "ui" / "gallery.py") & apps
