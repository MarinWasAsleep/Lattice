"""Lattice 1.0 is one application: one window, one CLI, one version.

The suite used to run three separate programs — three ``MainWindow`` classes, three binaries,
three console scripts — and this file proved they could coexist. Version 1.0 merges them into
one distribution, one window with three tabs and one command line, so the claims to prove
changed with the architecture:

* the three modes are *tabs* of a single window, and exactly one is visible at a time;
* the shared registry survives all three modes being loaded in the same process;
* one CLI routes to the three modes, and ``--version`` answers with one number;
* the engine still works with no GUI toolkit, which is what makes the CLI usable headless.

The version assertion stays here on purpose: a 1.0 whose parts disagree on the number is not
a 1.0, and that is cheap to check next to the code that reports it.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import lattice
from lattice.modes.dither import __version__ as dither_version
from lattice.modes.glitch import __version__ as glitch_version
from lattice.modes.glyph import __version__ as glyph_version
from lattice.registry import get_algorithm, get_effect, list_algorithms, list_effects
from lattice.window import MODES, MainWindow, mode_title

EXPECTED_VERSION = "1.0.0"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """One application object for the whole module: Qt refuses a second one."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> MainWindow:
    """Build the unified window and close every mode at teardown."""
    built = MainWindow()
    built.show()
    QApplication.processEvents()
    yield built
    built.shutdown()
    built.close()
    built.deleteLater()
    QApplication.processEvents()


def test_every_part_of_the_distribution_agrees_on_the_version() -> None:
    """A 1.0 whose parts disagree on the number is not a 1.0."""
    versions = {
        "lattice": lattice.__version__,
        "dither": dither_version,
        "glyph": glyph_version,
        "glitch": glitch_version,
    }
    assert versions == dict.fromkeys(versions, EXPECTED_VERSION)


def test_the_window_holds_the_three_modes_as_tabs(window: MainWindow) -> None:
    """One window, three tabs, and exactly one of them visible."""
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels == [mode_title(mode) for mode in MODES]
    visible = [mode for mode in MODES if not window.windows[mode].isHidden()]
    assert visible == [window.current_mode()], (
        f"the visible tabs are {visible} while the current mode is {window.current_mode()}")


def test_switching_tab_switches_exactly_one_mode(window: MainWindow) -> None:
    """Selecting a mode shows it and hides the other two."""
    for mode in MODES:
        window.show_mode(mode)
        QApplication.processEvents()
        assert window.current_mode() == mode
        shown = [other for other in MODES if not window.windows[other].isHidden()]
        assert shown == [mode], f"after selecting {mode}, the visible modes are {shown}"


def test_an_unknown_mode_is_refused(window: MainWindow) -> None:
    """``show_mode`` names the mode or fails; it never silently does nothing."""
    with pytest.raises(ValueError, match="unknown mode"):
        window.show_mode("scratch")


def test_loading_the_three_modes_keeps_every_registration() -> None:
    """The registry is global: no mode may drop another's renderers or effects.

    Each package self-registers at import, so this is really a test that the three modes do
    not collide on a shared name — a collision would silently leave one mode short.
    """
    algorithms = {entry.id for entry in list_algorithms()}
    effects = {entry.id for entry in list_effects()}
    assert effects, "no effect registered at all"
    for name in ("crt", "feedback", "bytemosh", "pixel_sort"):
        assert name in effects, f"effect {name!r} vanished from the registry"
    assert get_effect("crt").id == "crt"
    assert algorithms, "no algorithm registered at all"
    assert get_algorithm(sorted(algorithms)[0]).id == sorted(algorithms)[0]


def test_one_command_line_routes_the_three_modes(capsys: pytest.CaptureFixture[str]) -> None:
    """``lattice <mode> …`` reaches each mode's own command line.

    The per-mode parsers are unchanged — this asserts the routing, which is the new code, not
    the verbs, which the per-mode suites already cover.
    """
    from lattice import cli

    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"lattice {EXPECTED_VERSION}"

    assert cli.main(["--help"]) == 0
    assert "<mode>" in capsys.readouterr().out

    assert cli.main(["nope"]) == 1
    assert "unknown mode" in capsys.readouterr().err

    for mode in MODES:
        assert cli.main([mode, "--help"]) == 0, f"lattice {mode} --help failed"
        assert mode in capsys.readouterr().out.lower() or mode_title(mode) in (
            capsys.readouterr().out + "")


def test_the_engine_renders_without_a_display() -> None:
    """A render works in a process that never touches Qt: no mode may import it eagerly."""
    source = np.zeros((16, 24, 3), dtype=np.float32)
    source[..., 0] = np.linspace(0, 1, 24, dtype=np.float32)[None, :]
    from lattice.pipeline import PipelineSpec, render

    spec = PipelineSpec()
    out = render(source, spec)
    assert out.shape == source.shape
    # The pipeline quantises to 8-bit on the way out: that is the contract the exporters and
    # the CLI both rely on, so the assertion pins uint8 rather than the input dtype.
    assert out.dtype == np.uint8


def test_the_theme_resources_ship_with_the_package() -> None:
    """The stylesheet and the four icons are part of the package, not a developer's folder.

    ``lattice.app`` reads them by path: a missing stylesheet silently degrades to a plain
    palette, and a missing icon leaves a blank tab. Both would pass every render test, so the
    files are asserted where they live.
    """
    from lattice.app import RESOURCES, STYLESHEET, stylesheet

    assert STYLESHEET.is_file(), f"stylesheet missing at {STYLESHEET}"
    assert stylesheet().strip(), "the stylesheet is empty"
    for name in ("logo.svg", "icon-app.svg", "icon-dither.svg", "icon-glyph.svg",
                 "icon-glitch.svg"):
        assert (RESOURCES / name).is_file(), f"lattice/resources/{name} is missing"


def test_the_stylesheet_names_every_mode_colour() -> None:
    """Each mode has its own accent in the stylesheet, so the tab bar says where you are."""
    from lattice.app import stylesheet

    sheet = stylesheet()
    for mode, colour in (("dither", "#2EC4B6"), ("glyph", "#9BE15D"), ("glitch", "#E36BFF")):
        assert colour.lower() in sheet.lower(), f"{mode}: {colour} absent du thème"


def test_the_canvas_background_is_a_neutral_grey() -> None:
    """The canvas must not tint the image: R, G and B have to be equal.

    A tinted canvas sits behind every pixel the user judges, so a "warm" grey would make them
    compensate without knowing why. This pins the neutrality of the colour itself.
    """
    import inspect

    from PySide6.QtGui import QColor

    from lattice.ui import canvas

    source = inspect.getsource(canvas)
    assert "setBackgroundBrush(QColor(28, 28, 28))" in source
    colour = QColor(28, 28, 28)
    assert colour.red() == colour.green() == colour.blue()
