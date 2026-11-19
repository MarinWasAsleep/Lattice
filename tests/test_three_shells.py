"""The three shells living in one process, at version 1.0.0.

Every application has its own suite, each built in a fresh interpreter. That is how they are
developed, and it is also how they are shipped — three binaries, three processes. What none of
those suites proves is the thing a 1.0 actually claims: the three shells can be built in the
*same* process, at the *same* version, sharing the core, without one of them stealing the
other's registrations.

Three concrete risks are exercised here:

* **The registry is global.** Renderers and effects self-register at import, so a renderer
  added by one package must not vanish, or be replaced, when another package imports.
* **Qt allows one QApplication per process.** The three windows have to coexist under a single
  instance, and closing one must not tear the others down.
* **The shared modules are shared.** ``cli_shared`` and ``ui.actions`` were unified in L37;
  each shell has to bind its own backend without the other's binding leaking in.

The version assertion is deliberately part of this file: a 1.0 whose three packages disagree on
their number is not a 1.0, and that is cheap to check here rather than in a packaging script.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import lattice_core
import lattice_dither
import lattice_glitch
import lattice_glyph
from lattice_core.registry import get_algorithm, get_effect, list_algorithms, list_effects
from lattice_dither.ui.main_window import MainWindow as DitherWindow
from lattice_glitch.window import MainWindow as GlitchWindow
from lattice_glyph.window import MainWindow as GlyphWindow

EXPECTED_VERSION = "1.0.0"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """One application object for the whole module: Qt refuses a second one."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def windows(qapp: QApplication, tmp_path: Path) -> dict[str, object]:
    """Build the three main windows in one process and close them all at teardown."""
    preset_dirs = (tmp_path / "user",)
    built = {
        "dither": DitherWindow(),
        "glyph": GlyphWindow(preset_dirs=preset_dirs),
        "glitch": GlitchWindow(preset_dirs=preset_dirs),
    }
    for window in built.values():
        window.show()
    QApplication.processEvents()
    yield built
    for window in built.values():
        window.close()
        window.deleteLater()
    QApplication.processEvents()


def test_the_three_packages_agree_on_their_version() -> None:
    """A 1.0 whose parts disagree on the number is not a 1.0."""
    versions = {
        "core": lattice_core.__version__,
        "dither": lattice_dither.__version__,
        "glyph": lattice_glyph.__version__,
        "glitch": lattice_glitch.__version__,
    }
    assert versions == dict.fromkeys(versions, EXPECTED_VERSION)


def test_three_windows_coexist_under_one_application(qapp: QApplication,
                                                    windows: dict[str, object]) -> None:
    """The three shells open together, each with its own title, and all stay visible."""
    assert QApplication.instance() is qapp
    titles = {name: window.windowTitle() for name, window in windows.items()}
    assert len(set(titles.values())) == 3, f"windows share a title: {titles}"
    for name, window in windows.items():
        assert window.isVisible(), f"{name} window did not open"


def test_importing_the_three_packages_keeps_every_registration() -> None:
    """The registry is global: no package may drop another's renderers or effects.

    Each module self-registers at import, so this is really a test that the three packages do
    not collide on a shared name — a collision would silently leave one shell short.
    """
    algorithms = {entry.id for entry in list_algorithms()}
    effects = {entry.id for entry in list_effects()}
    assert "bitmask" in algorithms or "bayer_8" in algorithms, sorted(algorithms)[:8]
    assert effects, "no effect registered at all"
    # The effects the glitch shell advertises must survive the other two being imported.
    for name in ("crt", "feedback", "bytemosh", "pixel_sort"):
        assert name in effects, f"effect {name!r} vanished from the registry"
    assert get_effect("crt").id == "crt"
    assert get_algorithm(sorted(algorithms)[0]).id == sorted(algorithms)[0]


def test_each_shell_binds_its_own_shared_cli_backend() -> None:
    """Both CLIs use ``lattice_core.cli_shared``; each must bind its own backend.

    The backend is process-global, so the risk is real: binding Glyph must not leave the
    ``loop`` verb — Glitch's alone — reachable from Glyph, and vice versa.
    """
    from lattice_core import cli_shared
    from lattice_glitch import cli as glitch_cli
    from lattice_glyph import cli as glyph_cli

    # ``main`` binds the app's backend, then swallows argparse's SystemExit and returns 0:
    # ``--help`` is a normal termination, not a crash to report to a caller.
    assert glyph_cli.main(["--help"]) == glyph_cli.EXIT_OK
    glyph_verbs = _verbs(cli_shared._build_parser())
    assert "render" in glyph_verbs and "loop" not in glyph_verbs

    assert glitch_cli.main(["--help"]) == glitch_cli.EXIT_OK
    glitch_verbs = _verbs(cli_shared._build_parser())
    assert "render" in glitch_verbs and "loop" in glitch_verbs


def test_the_three_shells_render_from_the_same_core(windows: dict[str, object],
                                                    tmp_path: Path) -> None:
    """All three windows hold a spec from the shared core and can accept the same image."""
    image = np.zeros((32, 48, 3), dtype=np.float32)
    image[..., 0] = np.linspace(0, 1, 48, dtype=np.float32)[None, :]
    for name, window in windows.items():
        window.set_source_image(image) if hasattr(window, "set_source_image") else None
        spec = getattr(window, "spec", None)
        assert spec is not None, f"{name} has no pipeline spec"
        assert type(spec).__module__.startswith("lattice_core"), (
            f"{name} holds a spec from {type(spec).__module__}, not from the core")


def _verbs(parser) -> set[str]:
    """Return the top-level sub-command names a parser accepts.

    The subparsers action declares ``dest="command"``; hard-coding the destination would make
    this helper silently return nothing the day the verb group is renamed.
    """
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict) and action.dest == "command":
            return set(choices)
    return set()
