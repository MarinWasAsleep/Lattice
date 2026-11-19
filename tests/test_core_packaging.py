"""The shape of the single ``lattice`` package: one distribution, three modes inside.

These checks used to guard a *separation*: ``lattice_core`` was a standalone engine and the
three applications lived in their own top-level packages, so the tests walked the tree to prove
the engine imported nothing application-side. Lattice 1.0 collapses that split — one package
now holds the engine and the three modes — so what has to be guarded changed with it:

* the modes may not reach *sideways* into each other (Dither must not import the Glitch mode),
  which is the real coupling that would make the tabs unseparable;
* Qt stays an optional extra, so the CLI and the engine still work without PySide6 installed;
* the package keeps exposing the modules the rest of the suite (and the shipped presets) use.

A rule that no longer exists was deleted rather than kept green by pretending: there is no
"engine must not contain an application module" once the two are the same package.
"""

from __future__ import annotations

import ast
from pathlib import Path

import lattice  # noqa: F401  (the package must import cleanly)

ROOT = Path(lattice.__file__).resolve().parent
MODES = ("dither", "glyph", "glitch")


def _modules() -> list[Path]:
    """Return every Python file of the package, sorted."""
    return sorted(path for path in ROOT.rglob("*.py") if path.name != "__init__.py")


def _imported(node: ast.AST) -> list[str]:
    """Return the dotted module paths one import node names."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module] if node.module else []
    return []


def test_a_mode_never_imports_another_mode() -> None:
    """The three modes share the engine and nothing else.

    They sit side by side in one package, so a stray ``from lattice.modes.glitch import …``
    inside Dither would bind two tabs together and make each of them impossible to separate.
    This is the coupling the old top-level split used to prevent by construction.
    """
    for path in _modules():
        parts = path.relative_to(ROOT).parts
        if len(parts) < 3 or parts[0] != "modes":
            continue
        owner = parts[1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            for name in _imported(node):
                for other in MODES:
                    if other == owner:
                        continue
                    assert not name.startswith(f"lattice.modes.{other}"), (
                        f"{path.relative_to(ROOT)} (mode {owner}) imports {name!r} "
                        f"from mode {other}"
                    )


def test_qt_stays_behind_the_ui_extra() -> None:
    """Only the GUI entry points and the UI code may import PySide6.

    ``lattice/ui``, the mode windows and the two GUI entry points at the top of the package
    (``window.py``, ``app.py``) need Qt. The engine — renderers, effects, palettes, pipeline,
    presets, registry, cli — is what ``lattice dither render`` runs on a headless machine, and
    it must never pull a GUI toolkit.
    """
    gui_entry_points = {"window.py", "app.py"}
    for path in _modules():
        relative = path.relative_to(ROOT)
        if relative.parts[0] in {"ui", "modes"} or relative.name in gui_entry_points:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            for name in _imported(node):
                assert not name.startswith("PySide6"), (
                    f"{relative} imports {name!r}, which is not a base dependency"
                )


def test_the_engine_modules_are_importable() -> None:
    """The engine surface the suite and the shipped presets depend on stays importable."""
    import lattice.bridge  # noqa: F401
    import lattice.color  # noqa: F401
    import lattice.dither  # noqa: F401
    import lattice.effects  # noqa: F401
    import lattice.palettes  # noqa: F401
    import lattice.pipeline  # noqa: F401
    import lattice.presets  # noqa: F401
    import lattice.registry  # noqa: F401
    import lattice.types  # noqa: F401

    assert lattice.dither.__file__ is not None
    assert lattice.effects.__file__ is not None


def test_the_three_modes_live_inside_the_package() -> None:
    """One distribution: the three modes are subpackages of ``lattice``, not siblings."""
    for mode in MODES:
        directory = ROOT / "modes" / mode
        assert directory.is_dir(), f"mode {mode} is missing from lattice/modes"
        assert (directory / "__init__.py").is_file(), f"lattice/modes/{mode} is not a package"
        assert not (ROOT.parent / f"lattice_{mode}").exists(), (
            f"the old top-level package lattice_{mode} still exists next to the monorepo")
