"""Tests for the print export (CONTRACT §20)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lattice_dither.export.print import INKS, export_print

DPI = 300
BLEED_MM = 3.0
BLEED_PX = 35
MARK_PX = 35


def _image(height: int = 40, width: int = 60) -> np.ndarray:
    """Return a deterministic two-tone RGB image."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = 200
    image[:, :, 1] = 30
    image[:, :, 2] = 90
    image[: height // 2, :, 1] = 240
    return image


def _plates(written: list[Path]) -> dict[str, np.ndarray]:
    """Return the four ink plates of a separation export, keyed by ink letter."""
    return {
        ink: np.asarray(Image.open(path))
        for ink, path in zip(INKS, written[1:], strict=True)
    }


def _cyan(size: int = 8) -> np.ndarray:
    """Return a pure-cyan image."""
    image = np.zeros((size, size, 3), dtype=np.uint8)
    image[:, :, 1] = 255
    image[:, :, 2] = 255
    return image


def test_a_plain_export_writes_exactly_one_file(tmp_path: Path) -> None:
    """With no bleed, no marks and no separations, one file is written and returned."""
    target = tmp_path / "print.png"
    written = export_print(_image(), target)
    assert written == [target]
    assert target.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["print.png"]


def test_separations_write_five_files_in_write_order(tmp_path: Path) -> None:
    """The main file comes first, then the four plates in C, M, Y, K order."""
    target = tmp_path / "print.png"
    written = export_print(_image(), target, separations=True)
    assert written == [target] + [tmp_path / f"print_{ink}.png" for ink in INKS]
    assert all(path.exists() for path in written)
    assert len(list(tmp_path.iterdir())) == 5


def test_the_plates_are_single_channel_at_the_input_shape(tmp_path: Path) -> None:
    """Every separation is a greyscale image the size of the input, not of the canvas."""
    image = _image()
    written = export_print(image, tmp_path / "print.png", separations=True)
    for path in written[1:]:
        with Image.open(path) as plate:
            assert plate.mode == "L"
            assert plate.size == (image.shape[1], image.shape[0])


def test_pure_cyan_lands_entirely_on_the_cyan_plate(tmp_path: Path) -> None:
    """A pure-cyan input gives a full C plate and three empty plates."""
    written = export_print(_cyan(), tmp_path / "cyan.png", separations=True)
    plates = _plates(written)
    assert plates["C"].min() == 255
    for ink in ("M", "Y", "K"):
        assert plates[ink].max() == 0


def test_a_neutral_grey_lands_entirely_on_the_black_plate(tmp_path: Path) -> None:
    """The separation uses the textbook conversion, so grey is pure K ink."""
    grey = np.full((8, 8, 3), 128, dtype=np.uint8)
    written = export_print(grey, tmp_path / "grey.png", separations=True)
    plates = _plates(written)
    assert plates["K"].min() > 0
    for ink in ("C", "M", "Y"):
        assert plates[ink].max() == 0


def test_dpi_is_written_without_changing_the_pixels(tmp_path: Path) -> None:
    """The dpi lands in the PNG metadata and the pixel dimensions stay the input size."""
    image = _image()
    target = tmp_path / "print.png"
    export_print(image, target, dpi=DPI)
    with Image.open(target) as written:
        assert written.size == (image.shape[1], image.shape[0])
        stored = written.info["dpi"]
    assert stored[0] == pytest.approx(DPI, abs=0.01)
    assert stored[1] == pytest.approx(DPI, abs=0.01)


def test_a_different_dpi_keeps_the_same_pixels(tmp_path: Path) -> None:
    """Changing dpi changes the metadata only."""
    image = _image()
    low, high = tmp_path / "low.png", tmp_path / "high.png"
    export_print(image, low, dpi=72)
    export_print(image, high, dpi=600)
    with Image.open(low) as a, Image.open(high) as b:
        assert a.size == b.size
        assert a.info["dpi"][0] == pytest.approx(72, abs=0.01)
        assert b.info["dpi"][0] == pytest.approx(600, abs=0.01)


def test_bleed_extends_the_canvas_with_the_edge_colour(tmp_path: Path) -> None:
    """The bleed border is the edge colour replicated outward, on all four sides."""
    image = _image()
    target = tmp_path / "bleed.png"
    export_print(image, target, bleed_mm=BLEED_MM)
    with Image.open(target) as written:
        assert written.size == (image.shape[1] + 2 * BLEED_PX, image.shape[0] + 2 * BLEED_PX)
        canvas = np.asarray(written)
    expected = np.pad(
        image, ((BLEED_PX, BLEED_PX), (BLEED_PX, BLEED_PX), (0, 0)), mode="edge"
    )
    assert np.array_equal(canvas, expected)


def test_the_trim_area_is_untouched_by_the_bleed(tmp_path: Path) -> None:
    """The image itself sits in the middle of the bleed canvas, unchanged."""
    image = _image()
    target = tmp_path / "bleed.png"
    export_print(image, target, bleed_mm=BLEED_MM)
    with Image.open(target) as written:
        canvas = np.asarray(written)
    inner = canvas[BLEED_PX : BLEED_PX + image.shape[0], BLEED_PX : BLEED_PX + image.shape[1]]
    assert np.array_equal(inner, image)


def test_crop_marks_are_black_on_a_transparent_margin(tmp_path: Path) -> None:
    """The margin is transparent except for the black marks, which never touch the trim."""
    image = _image()
    target = tmp_path / "marks.png"
    export_print(image, target, bleed_mm=BLEED_MM, crop_marks=True)
    with Image.open(target) as written:
        assert written.mode == "RGBA"
        canvas = np.asarray(written)
    assert canvas.shape[:2] == (
        image.shape[0] + 2 * BLEED_PX + 2 * MARK_PX,
        image.shape[1] + 2 * BLEED_PX + 2 * MARK_PX,
    )
    assert canvas[0, 0, 3] == 0
    assert canvas[0, 0, :3].tolist() == [0, 0, 0]
    tall = image.shape[0] + 2 * BLEED_PX
    wide = image.shape[1] + 2 * BLEED_PX
    trim = canvas[MARK_PX : MARK_PX + tall, MARK_PX : MARK_PX + wide]
    assert trim[:, :, 3].min() == 255
    inner = trim[BLEED_PX : BLEED_PX + image.shape[0], BLEED_PX : BLEED_PX + image.shape[1], :3]
    assert np.array_equal(inner, image)


def test_crop_marks_alone_keep_the_trim_size(tmp_path: Path) -> None:
    """Without bleed the margin is added directly around the image."""
    image = _image()
    target = tmp_path / "marks.png"
    export_print(image, target, crop_marks=True)
    with Image.open(target) as written:
        assert written.size == (image.shape[1] + 2 * MARK_PX, image.shape[0] + 2 * MARK_PX)


def test_separations_ignore_the_bleed_and_the_marks(tmp_path: Path) -> None:
    """The plates are always the trim image, whatever the canvas looks like."""
    image = _image()
    written = export_print(
        image, tmp_path / "print.png", bleed_mm=BLEED_MM, crop_marks=True, separations=True
    )
    for path in written[1:]:
        with Image.open(path) as plate:
            assert plate.size == (image.shape[1], image.shape[0])


def test_an_invalid_shape_raises(tmp_path: Path) -> None:
    """A non-RGB array is rejected before anything is written."""
    with pytest.raises(ValueError, match="expected an"):
        export_print(np.zeros((4, 4), dtype=np.uint8), tmp_path / "x.png")


def test_an_invalid_dpi_raises(tmp_path: Path) -> None:
    """dpi below one is rejected."""
    with pytest.raises(ValueError, match="dpi"):
        export_print(_image(), tmp_path / "x.png", dpi=0)


def test_a_negative_bleed_raises(tmp_path: Path) -> None:
    """A negative bleed is rejected."""
    with pytest.raises(ValueError, match="bleed_mm"):
        export_print(_image(), tmp_path / "x.png", bleed_mm=-1.0)


def test_an_empty_image_raises(tmp_path: Path) -> None:
    """A zero-sized image is rejected."""
    with pytest.raises(ValueError, match="empty"):
        export_print(np.zeros((0, 4, 3), dtype=np.uint8), tmp_path / "x.png")
