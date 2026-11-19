"""Tests for the algorithm gallery, its thumbnail cache and its search box (T26)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import Qt, QThread  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import lattice_core.dither  # noqa: E402,F401  (registers every algorithm)
from lattice_core.pipeline import PaletteSpec  # noqa: E402
from lattice_core.registry import AlgorithmInfo  # noqa: E402

# The widget now lives in the core; the patches must land on the module that READS these
# names, not on the app's thin binding.
from lattice_core.ui import algorithm_gallery as gallery_module  # noqa: E402
from lattice_dither.ui.gallery import (  # noqa: E402
    THUMB_SIZE,
    AlgorithmGallery,
    ThumbnailCell,
    ThumbnailWorker,
    cache_key,
    fold,
    palette_hash,
    params_hash,
    render_thumbnail,
    thumbnail_for,
    thumbs_dir,
)

# aliased: pytest would collect a bare test_image as a test function
from lattice_dither.ui.gallery import test_image as synthetic_image  # noqa: E402

PALETTE = PaletteSpec(source="builtin", name="pico8")
OTHER_PALETTE = PaletteSpec(source="builtin", name="gameboy")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _info(algorithm_id: str, name: str, family: str) -> AlgorithmInfo:
    """Return a registry record with no parameters and a stub renderer."""
    return AlgorithmInfo(algorithm_id, name, family, (), lambda img, palette, params: None)


FAKE_INFOS: tuple[AlgorithmInfo, ...] = (
    _info("floyd_steinberg", "Floyd-Steinberg", "error_diffusion"),
    _info("bayer8", "Bayer 8x8", "ordered"),
    _info("reseau", "Réseau Réticulé", "halftone"),
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Return an empty thumbnail cache directory."""
    return tmp_path / "thumbs"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> tuple[AlgorithmInfo, ...]:
    """Replace the algorithm registry with three fixed entries."""
    monkeypatch.setattr(gallery_module, "list_algorithms", lambda: list(FAKE_INFOS))
    return FAKE_INFOS


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the thumbnail renderer with a counting stub."""
    calls: list[str] = []

    def fake(
        algorithm_id: str, params: dict, palette: PaletteSpec, size: int = THUMB_SIZE
    ) -> np.ndarray:
        calls.append(algorithm_id)
        return _thumb(algorithm_id, size)

    monkeypatch.setattr(gallery_module, "render_thumbnail", fake)
    return calls


@pytest.fixture
def gallery(
    qapp: QApplication,
    cache_dir: Path,
    registry: tuple[AlgorithmInfo, ...],
    rendered: list[str],
) -> Iterator[AlgorithmGallery]:
    """Return a shown gallery over the fake registry, stopped after the test."""
    widget = AlgorithmGallery(cache_dir=cache_dir)
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.shutdown()
    widget.close()


def _thumb(algorithm_id: str, size: int = THUMB_SIZE) -> np.ndarray:
    """Return a deterministic uint8 thumbnail that differs per algorithm id."""
    ramp = np.arange(size, dtype=np.uint8)
    image = np.empty((size, size, 3), dtype=np.uint8)
    image[:, :, 0] = ramp[None, :]
    image[:, :, 1] = ramp[:, None]
    image[:, :, 2] = (sum(ord(char) for char in algorithm_id) * 7) % 256
    return image


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Process GUI events until predicate holds or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(0.005)
    return predicate()


def _all_ready(widget: AlgorithmGallery) -> bool:
    """Return True when every cell of the gallery shows a thumbnail."""
    return all(cell.has_thumbnail() for cell in widget.cells())


def _build(cache_dir: Path, palette: PaletteSpec | None = None) -> AlgorithmGallery:
    """Build a gallery over cache_dir and wait until its thumbnails are in."""
    widget = AlgorithmGallery(cache_dir=cache_dir, palette=palette)
    assert _wait_until(lambda: _all_ready(widget))
    widget.shutdown()
    return widget


def _contact_sheet() -> object:
    """Import tools/contact_sheet.py by path, since tools is not a package."""
    path = Path(__file__).resolve().parents[1] / "tools" / "contact_sheet.py"
    spec = importlib.util.spec_from_file_location("contact_sheet", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_gallery_shows_one_cell_per_registered_algorithm(gallery: AlgorithmGallery) -> None:
    cells = gallery.cells()
    assert len(cells) == 3
    assert [cell.name for cell in cells] == [info.name for info in FAKE_INFOS]
    assert [cell.algorithm_id for cell in cells] == [info.id for info in FAKE_INFOS]
    assert _wait_until(lambda: _all_ready(gallery))


def test_a_cell_shows_a_placeholder_until_its_thumbnail_is_ready(
    qapp: QApplication, cache_dir: Path, registry: tuple[AlgorithmInfo, ...], rendered: list[str]
) -> None:
    widget = AlgorithmGallery(cache_dir=cache_dir)
    try:
        assert all(not cell.has_thumbnail() for cell in widget.cells())
        assert _wait_until(lambda: _all_ready(widget))
        assert all(cell.has_thumbnail() for cell in widget.cells())
    finally:
        widget.shutdown()


def test_the_search_box_filters_by_name_and_restores_when_cleared(
    gallery: AlgorithmGallery,
) -> None:
    gallery.search_box.setText("bayer")
    assert [cell.algorithm_id for cell in gallery.visible_cells()] == ["bayer8"]
    gallery.search_box.setText("")
    assert len(gallery.visible_cells()) == 3


def test_the_search_box_filters_by_family(gallery: AlgorithmGallery) -> None:
    gallery.set_search("error diffusion")
    assert [cell.algorithm_id for cell in gallery.visible_cells()] == ["floyd_steinberg"]
    gallery.set_search("ordered")
    assert [cell.algorithm_id for cell in gallery.visible_cells()] == ["bayer8"]


def test_the_search_is_case_and_accent_insensitive(gallery: AlgorithmGallery) -> None:
    assert fold("Réseau Réticulé") == "reseau reticule"
    gallery.set_search("RESEAU RETICULE")
    assert [cell.algorithm_id for cell in gallery.visible_cells()] == ["reseau"]
    gallery.set_search("réticulé")
    assert [cell.algorithm_id for cell in gallery.visible_cells()] == ["reseau"]


def test_a_search_that_matches_nothing_shows_the_empty_label(gallery: AlgorithmGallery) -> None:
    gallery.set_search("zzz")
    assert gallery.visible_cells() == []
    assert gallery.empty_label.isVisibleTo(gallery)
    gallery.set_search("")
    assert not gallery.empty_label.isVisibleTo(gallery)


def test_a_second_build_reads_the_cache(
    qapp: QApplication, cache_dir: Path, registry: tuple[AlgorithmInfo, ...], rendered: list[str]
) -> None:
    _build(cache_dir)
    _build(cache_dir)
    assert sorted(rendered) == sorted(info.id for info in FAKE_INFOS)
    assert len(list(cache_dir.glob("*.png"))) == 3


def test_a_changed_palette_hash_invalidates_the_cache(
    qapp: QApplication, cache_dir: Path, registry: tuple[AlgorithmInfo, ...], rendered: list[str]
) -> None:
    _build(cache_dir, PALETTE)
    _build(cache_dir, PALETTE)
    assert len(rendered) == 3
    _build(cache_dir, OTHER_PALETTE)
    assert len(rendered) == 6
    assert len(list(cache_dir.glob("*.png"))) == 6


def test_a_stale_cache_file_is_regenerated(
    qapp: QApplication, cache_dir: Path, registry: tuple[AlgorithmInfo, ...], rendered: list[str]
) -> None:
    _build(cache_dir)
    assert len(rendered) == 3
    key = cache_key(FAKE_INFOS[1].id, {}, PALETTE)
    stale = cache_dir / f"{key}.png"
    stale.write_bytes(b"not a png")
    _build(cache_dir)
    assert rendered[3:] == [FAKE_INFOS[1].id]
    assert stale.read_bytes()[:8] == PNG_MAGIC


def test_the_cache_key_covers_algorithm_params_and_palette() -> None:
    base = cache_key("floyd_steinberg", {}, PALETTE)
    assert base == cache_key("floyd_steinberg", {}, PALETTE)
    assert base.startswith("floyd_steinberg-")
    assert base != cache_key("bayer8", {}, PALETTE)
    assert base != cache_key("floyd_steinberg", {"levels": 4}, PALETTE)
    assert base != cache_key("floyd_steinberg", {}, OTHER_PALETTE)
    assert params_hash({"a": 1, "b": 2}) == params_hash({"b": 2, "a": 1})
    assert palette_hash(PALETTE) != palette_hash(OTHER_PALETTE)


def test_thumbnail_for_reads_back_what_it_wrote(cache_dir: Path, rendered: list[str]) -> None:
    key = cache_key("bayer8", {}, PALETTE)
    first = thumbnail_for(key, "bayer8", {}, PALETTE, cache_dir)
    second = thumbnail_for(key, "bayer8", {}, PALETTE, cache_dir)
    assert np.array_equal(first, second)
    assert rendered == ["bayer8"]


def test_no_widget_is_touched_from_the_worker_thread(
    qapp: QApplication,
    cache_dir: Path,
    registry: tuple[AlgorithmInfo, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render_threads: list[QThread] = []
    render_idents: list[int] = []
    update_threads: list[QThread] = []
    update_idents: list[int] = []
    original = ThumbnailCell.set_thumbnail

    def fake_render(
        algorithm_id: str, params: dict, palette: PaletteSpec, size: int = THUMB_SIZE
    ) -> np.ndarray:
        render_threads.append(QThread.currentThread())
        render_idents.append(threading.get_ident())
        return _thumb(algorithm_id, size)

    def spy(self: ThumbnailCell, rgb8: np.ndarray) -> None:
        update_threads.append(QThread.currentThread())
        update_idents.append(threading.get_ident())
        original(self, rgb8)

    monkeypatch.setattr(gallery_module, "render_thumbnail", fake_render)
    monkeypatch.setattr(ThumbnailCell, "set_thumbnail", spy)
    widget = AlgorithmGallery(cache_dir=cache_dir)
    try:
        assert _wait_until(lambda: _all_ready(widget))
        worker = widget._worker
        assert isinstance(worker, ThumbnailWorker)
        assert not isinstance(worker, QWidget)
        assert not [value for value in vars(worker).values() if isinstance(value, QWidget)]
        assert worker.thread() is not qapp.thread()
    finally:
        widget.shutdown()
    gui_thread = qapp.thread()
    assert render_threads and all(thread is not gui_thread for thread in render_threads)
    assert update_threads and all(thread is gui_thread for thread in update_threads)
    assert threading.get_ident() not in render_idents
    assert set(update_idents) == {threading.get_ident()}


def test_a_failing_thumbnail_keeps_the_placeholder(
    qapp: QApplication,
    cache_dir: Path,
    registry: tuple[AlgorithmInfo, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(
        algorithm_id: str, params: dict, palette: PaletteSpec, size: int = THUMB_SIZE
    ) -> np.ndarray:
        raise RuntimeError("no render")

    monkeypatch.setattr(gallery_module, "render_thumbnail", boom)
    widget = AlgorithmGallery(cache_dir=cache_dir)
    try:
        assert _wait_until(lambda: "no render" in widget.cells()[0].toolTip())
        assert len(widget.cells()) == 3
        assert all(not cell.has_thumbnail() for cell in widget.cells())
    finally:
        widget.shutdown()


def test_clicking_a_cell_reports_its_algorithm(gallery: AlgorithmGallery) -> None:
    chosen: list[str] = []
    gallery.algorithm_chosen.connect(chosen.append)
    QTest.mouseClick(gallery.cells()[1], Qt.MouseButton.LeftButton)
    assert chosen == [FAKE_INFOS[1].id]


def test_the_thumbnail_is_96_pixels_of_the_contact_sheet_image() -> None:
    source = synthetic_image()
    assert source.shape == (200, 200, 3)
    assert source.dtype == np.float32
    assert 0.0 <= float(source.min()) and float(source.max()) <= 1.0
    assert np.array_equal(source, _contact_sheet().test_image())
    thumb = render_thumbnail("floyd_steinberg", {}, PALETTE)
    assert thumb.shape == (THUMB_SIZE, THUMB_SIZE, 3)
    assert thumb.dtype == np.uint8
    assert len(np.unique(thumb.reshape(-1, 3), axis=0)) > 1


def test_thumbs_dir_is_under_local_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert thumbs_dir() == tmp_path / "LatticeDither" / "thumbs"
