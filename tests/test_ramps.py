"""Card L10 acceptance: the glyph ramp catalogue and its browser (§9).

Accept, item by item: the document validates against its schema and every ramp is non-empty and
darkest-first (an ordered subsequence of its category ladder, never measured ink); every set
previews without raising, and cell i of a preview is proven to hold glyph i; at least eight
categories and six non-Latin ramps ship; a cold selection repaints within 100 ms.
"""

from __future__ import annotations

import gc
import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lattice_core.renderers import glyph_ramp as renderer  # noqa: E402
from lattice_core.ui import glyph_browser as module  # noqa: E402
from lattice_core.ui.glyph_browser import (  # noqa: E402
    DATA_FILE,
    MIN_CATEGORIES,
    MIN_NON_LATIN_RAMPS,
    PREVIEW_CELL,
    SCHEMA,
    Catalogue,
    GlyphBrowser,
    load_catalogue,
    render_ramp_preview,
    validate_catalogue,
)

SELECT_DEADLINE = 0.100  # accept: selecting a set updates the preview within 100 ms
CAT, RAMP = "$.categories[0]", "$.categories[0].ramps[0]"  # paths of the mutated objects
RGB888 = QImage.Format.Format_RGB888


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    """Return the shipped catalogue, parsed once for the whole module."""
    return load_catalogue()


def document() -> dict:
    """Return the shipped ramps document as raw JSON."""
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def minimal_document() -> dict:
    """Return the smallest document that satisfies the schema, for mutation tests."""
    categories = [
        {"id": f"cat_{at}", "name": f"Category {at}", "ladder": "@#. ",
         "ramps": [{"id": f"ramp_{at}", "name": "One", "script": "latin", "ramp": "@#. "}]}
        for at in range(MIN_CATEGORIES)
    ]
    for at in range(MIN_NON_LATIN_RAMPS):
        categories[at]["ramps"].append(
            {"id": f"nonlatin_{at}", "name": "Two", "script": "japanese", "ramp": "@. "}
        )
    return {"schema": SCHEMA, "categories": categories}


def first_ramp(doc: dict) -> dict:
    """Return the first ramp object of the first category of a document."""
    return doc["categories"][0]["ramps"][0]


def ramp_ids(catalogue: Catalogue) -> list[str]:
    """Return every ramp id of the catalogue, in display order."""
    return [ramp.id for ramp in catalogue.ramps()]


def cells(rgb8: np.ndarray, count: int) -> list[np.ndarray]:
    """Return a preview sliced into count cells of PREVIEW_CELL[0] columns."""
    width = PREVIEW_CELL[0]
    return [rgb8[:, at * width : (at + 1) * width] for at in range(count)]


def clear_glyph_caches() -> None:
    """Empty the renderer's glyph mask caches, so the next preview really rasterises."""
    for glyph_cache in (renderer._cached_mask, renderer._metrics):
        assert hasattr(glyph_cache, "cache_clear")  # the test must reach the real cache
        glyph_cache.cache_clear()


# --- accept 1: the document validates against the schema --------------------------


def test_shipped_catalogue_validates_against_the_schema(catalogue: Catalogue) -> None:
    """The shipped ramps.json loads as typed objects that name its own schema version."""
    raw = document()
    assert raw["schema"] == SCHEMA == "lattice.ramps/1"
    assert validate_catalogue(raw) == catalogue
    assert [c.id for c in catalogue.categories] == [item["id"] for item in raw["categories"]]
    assert len(ramp_ids(catalogue)) == len({ramp.id for ramp in catalogue.ramps()})


def test_data_file_is_found_next_to_the_module_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped path derives from __file__, so any working directory loads the same data."""
    expected = Path(module.__file__).resolve().parents[1] / "data" / "ramps.json"
    assert Path(DATA_FILE).resolve() == expected and DATA_FILE.parent.name == "data"
    expected_ids = [item["id"] for item in document()["categories"]]
    load_catalogue.cache_clear()  # force a real read, from a directory holding no data
    monkeypatch.chdir(tmp_path)
    assert not Path("lattice_core/data/ramps.json").exists()
    assert [c.id for c in load_catalogue().categories] == expected_ids
    load_catalogue.cache_clear()


def test_catalogue_lookup_is_by_id(catalogue: Catalogue) -> None:
    """Catalogue.get and Catalogue.category resolve ids and name unknown ones in a KeyError."""
    first = catalogue.ramps()[0]
    assert catalogue.get(first.id) is first
    assert catalogue.category(first.category_id).id == first.category_id
    assert catalogue.get(first.id) is catalogue.ramp_index[first.id]  # indexed once, then reused
    with pytest.raises(KeyError, match="unknown glyph ramp"):
        catalogue.get("no_such_ramp")
    with pytest.raises(KeyError, match="unknown glyph category"):
        catalogue.category("no_such_category")


def test_every_ramp_is_non_empty_and_darkest_first(catalogue: Catalogue) -> None:
    """Every ramp follows its ladder, recomputed from the document at the data level of §9."""
    raw = document()
    for category, item in zip(catalogue.categories, raw["categories"], strict=True):
        ladder = item["ladder"]
        assert ladder and len(set(ladder)) == len(ladder)
        for ramp in category.ramps:
            assert 2 <= len(ramp.ramp) <= len(ladder)
            positions = [ladder.index(glyph) for glyph in ramp.ramp]
            assert positions == sorted(set(positions)), f"{ramp.id} is not darkest-first"


def test_every_ladder_starts_dense_and_ends_on_blank_paper(catalogue: Catalogue) -> None:
    """A ladder opens on a dense glyph and closes on a space, its documented light end."""
    for category in catalogue.categories:
        assert category.ladder[0] not in " ·" and category.ladder[-1] == " ", category.id
        assert len(category.ladder) >= len(max(category.ramps, key=lambda r: len(r.ramp)).ramp)


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda doc: doc.update({"schema": "lattice.ramps/2"}), "$.schema"),
        (lambda doc: doc["categories"][0].update({"ladder": "@#. .  "}), f"{CAT}.ladder"),
        (lambda doc: doc["categories"][0].update({"ramps": []}), f"{CAT}.ramps"),
        (lambda doc: first_ramp(doc).update({"ramp": " .#@"}), f"{RAMP}.ramp"),
        (lambda doc: first_ramp(doc).update({"ramp": "@#@. "}), f"{RAMP}.ramp"),
        (lambda doc: first_ramp(doc).update({"ramp": "@"}), f"{RAMP}.ramp"),
        (lambda doc: first_ramp(doc).update({"script": "klingon"}), f"{RAMP}.script"),
        (lambda doc: doc["categories"][0].update({"id": "Not A Slug"}), f"{CAT}.id"),
        (lambda doc: first_ramp(doc).pop("name"), f"{RAMP}.name"),
        (lambda doc: doc.update({"categories": doc["categories"][:2]}), "$.categories"),
    ],
)
def test_the_schema_rejects_invalid_documents(mutate, path: str) -> None:
    """A broken document raises ValueError naming the offending path of the catalogue."""
    doc = minimal_document()
    mutate(doc)
    with pytest.raises(ValueError) as error:
        validate_catalogue(doc)
    assert path in str(error.value)


def test_minimal_document_is_accepted() -> None:
    """The fixture used by the mutation tests is itself valid, so each case proves one rule."""
    assert len(validate_catalogue(minimal_document()).categories) == MIN_CATEGORIES


# --- accept 3: at least 8 categories and 6 non-Latin ramps -------------------------


def test_enough_categories_and_non_latin_ramps(catalogue: Catalogue) -> None:
    """§9 asks for eight categories and six non-Latin ramps; the card names all seven scripts."""
    assert len(catalogue.categories) >= MIN_CATEGORIES == 8
    scripts = {ramp.script for ramp in catalogue.ramps()}
    non_latin = [ramp for ramp in catalogue.ramps() if ramp.script in module.NON_LATIN_SCRIPTS]
    assert len(non_latin) >= MIN_NON_LATIN_RAMPS == 6
    assert {"japanese", "korean", "chinese", "russian", "german", "french", "spanish"} <= scripts
    classic = {category.id for category in catalogue.categories}
    assert {"classic_ascii", "numbers", "symbols", "blocks"} <= classic
    assert {"geometric", "braille", "playing_cards"} <= classic


# --- accept 2: cell i of a preview holds glyph i, and every set renders -----------


def test_cell_i_of_a_preview_shows_glyph_i_of_the_ramp() -> None:
    """Each column equals that glyph rendered alone, and no two columns draw alike.

    The mapping proof of accept 2: a luma transform that shifted, reversed or collapsed the
    glyph index, or drew one glyph everywhere, changes at least one column.
    """
    ramp = load_catalogue().get("classic_10").ramp  # dense ASCII to blank: distinct masks
    image = render_ramp_preview(ramp)
    drawn = cells(image, len(ramp))
    for glyph, cell in zip(ramp, drawn, strict=True):
        assert np.array_equal(cell, render_ramp_preview(glyph)), repr(glyph)
    assert len({cell.tobytes() for cell in drawn}) == len(ramp)
    assert int(drawn[0].min()) == 0x11, "the densest glyph must ink the paper"
    assert int(drawn[-1].min()) == 255, "the blank glyph must leave the paper untouched"


def test_every_shipped_ramp_renders_without_raising(catalogue: Catalogue) -> None:
    """The sweep of accept 2: one cell per glyph as uint8 RGB, for every shipped ramp."""
    for ramp in catalogue.ramps():
        image = render_ramp_preview(ramp.ramp)
        assert image.dtype.name == "uint8", ramp.id
        assert image.shape == (PREVIEW_CELL[1], PREVIEW_CELL[0] * len(ramp.ramp), 3), ramp.id
        assert 0 <= int(image.min()) and int(image.max()) <= 255, ramp.id


def test_preview_composites_a_transparent_ink_over_white() -> None:
    """A transparent colour still yields uint8 RGB, white where no ink is drawn."""
    image = render_ramp_preview("@. ", fg="transparent", bg="transparent")
    assert image.shape[2] == 3
    assert int(image.min()) == 255


def test_preview_uses_the_font_it_is_given() -> None:
    """A font path that does not exist is refused instead of silently drawing nothing."""
    with pytest.raises(ValueError, match="font file not found"):
        render_ramp_preview("@. ", font="/nonexistent/font.ttf")


def test_browser_renders_a_preview_for_every_set(qapp: QApplication, catalogue: Catalogue) -> None:
    """Walking every category and every set repaints the preview without raising."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        assert browser.category_list.count() == len(catalogue.categories)
        seen: list[str] = []
        for row, category in enumerate(catalogue.categories):
            browser.category_list.setCurrentRow(row)
            QApplication.processEvents()
            assert browser.set_list.count() == len(category.ramps), category.id
            for at, ramp in enumerate(category.ramps):
                browser.set_list.setCurrentRow(at)
                QApplication.processEvents()
                preview = browser.preview_rgb8()
                assert browser.current_ramp() is ramp
                assert preview is not None and preview.shape[2] == 3
                assert browser.preview_label.pixmap().size().width() == preview.shape[1]
                assert browser.name_label.text() == ramp.name
                seen.append(ramp.id)
        assert seen == ramp_ids(catalogue)
    finally:
        browser.close()


def test_first_selection_is_previewed_on_construction(
    qapp: QApplication, catalogue: Catalogue
) -> None:
    """A fresh browser already shows the first set of the first category."""
    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
    try:
        assert browser.current_ramp() is catalogue.categories[0].ramps[0]
        assert browser.preview_rgb8() is not None
    finally:
        browser.close()


# --- accept 4: selecting a set updates the preview within 100 ms -------------------


def test_cold_selection_repaints_within_100_ms(qapp: QApplication, catalogue: Catalogue) -> None:
    """Each category's last set repaints inside 100 ms with the glyph caches emptied first.

    Nothing of the timed ramp was rasterised before: the cold path of browsing, not a hit.
    """
    browser = GlyphBrowser(catalogue=catalogue)
    timings: list[tuple[float, str]] = []
    try:
        for category in catalogue.categories:
            clear_glyph_caches()
            target = category.ramps[-1]
            start = time.perf_counter()
            browser.select_ramp(target.id)
            QApplication.processEvents()
            timings.append((time.perf_counter() - start, target.id))
            assert renderer._cached_mask.cache_info().misses >= len(target.ramp)  # really cold
            assert browser.current_ramp() is target
    finally:
        browser.close()
    slowest, ramp_id = max(timings)
    assert slowest < SELECT_DEADLINE, f"{ramp_id} took {slowest * 1000:.1f} ms"


def test_select_ramp_repaints_a_silent_list(qapp: QApplication, catalogue: Catalogue) -> None:
    """A silent list (already on that row) still repaints: the preview is not left stale."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        first, second = catalogue.categories[0].ramps[:2]
        browser.select_ramp(first.id)
        browser.set_list.blockSignals(True)  # the lists now point at `second`, the pane at `first`
        browser.set_list.setCurrentRow(1)
        browser.set_list.blockSignals(False)
        assert browser.current_ramp() is first
        browser.select_ramp(second.id)  # setCurrentRow(1) is a no-op, so no signal is emitted
        assert browser.current_ramp() is second
        assert np.array_equal(browser.preview_rgb8(), render_ramp_preview(second.ramp))
    finally:
        browser.close()


def test_cross_category_jump_announces_once(qapp: QApplication, catalogue: Catalogue) -> None:
    """A jump to another category emits exactly one ramp_chosen, and it is the target.

    The old path refilled the set list and selected row 0 first, announcing a spurious set.
    """
    browser = GlyphBrowser(catalogue=catalogue)
    chosen: list[str] = []
    browser.ramp_chosen.connect(chosen.append)
    try:
        target = catalogue.categories[-1].ramps[-1]
        browser.select_ramp(target.id)
        QApplication.processEvents()
        assert chosen == [target.id]
        assert browser.current_ramp() is target
        back = catalogue.ramps()[0]
        browser.select_ramp(back.id)
        QApplication.processEvents()
        assert chosen == [target.id, back.id]
        assert browser.current_ramp() is back
    finally:
        browser.close()


def test_pixmap_keeps_its_pixels_after_gc(qapp: QApplication, catalogue: Catalogue) -> None:
    """The pixmap owns a copy: its pixels still equal the preview after gc and image churn."""
    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
    try:
        expected = browser.preview_rgb8()
        assert expected is not None
        height, width = int(expected.shape[0]), int(expected.shape[1])
        for _ in range(4):  # churn same-size images over memory a dangling QImage would read
            poison = QImage(width, height, RGB888)
            poison.fill(0xFF00FF)
            del poison
        gc.collect()
        image = browser.preview_label.pixmap().toImage().convertToFormat(RGB888)
        raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
        lines = raw.reshape(image.height(), image.bytesPerLine())
        assert np.array_equal(lines[:, : width * 3].reshape(height, width, 3), expected)
    finally:
        browser.close()


def test_select_ramp_names_an_unknown_id(qapp: QApplication, catalogue: Catalogue) -> None:
    """An unknown id raises KeyError instead of silently showing something else."""
    browser = GlyphBrowser(catalogue=catalogue)
    try:
        with pytest.raises(KeyError, match="unknown glyph ramp"):
            browser.select_ramp("no_such_ramp")
    finally:
        browser.close()


def test_ramp_chosen_follows_the_selection(qapp: QApplication, catalogue: Catalogue) -> None:
    """Every list selection announces its ramp id, which is how the app learns the choice."""
    browser = GlyphBrowser(catalogue=catalogue)
    chosen: list[str] = []
    browser.ramp_chosen.connect(chosen.append)
    try:
        last = catalogue.categories[-1]
        browser.category_list.setCurrentRow(len(catalogue.categories) - 1)
        browser.set_list.setCurrentRow(len(last.ramps) - 1)
        QApplication.processEvents()
        assert chosen[-1] == last.ramps[-1].id
    finally:
        browser.close()


def test_set_font_repaints_the_current_ramp(qapp: QApplication, catalogue: Catalogue) -> None:
    """set_font(None) restores the bundled font and keeps the selection."""
    browser = GlyphBrowser(catalogue=catalogue, cell=(6, 12))
    try:
        browser.select_ramp(catalogue.ramps()[1].id)
        browser.set_font(None)
        assert browser.current_ramp() is catalogue.ramps()[1]
        assert browser.preview_rgb8() is not None
    finally:
        browser.close()
