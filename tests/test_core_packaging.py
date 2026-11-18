"""Card L1 acceptance: lattice_core is a self-contained engine package.

Walks the package tree from source so the checks hold even before any
installation: ``lattice_core`` must import nothing from ``lattice_dither``,
must not import PySide6 (Qt lives behind the optional ``ui`` extra only), and
must not contain any application module (the app keeps ``ui``, ``export``,
``preprocess``, ``i18n``, ``cli`` and ``core/animation.py`` in
``lattice_dither``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import lattice_core  # noqa: F401  (the package must import cleanly)

CORE = Path(lattice_core.__file__).resolve().parent

# Application packages/app-only modules that must never live inside lattice_core.
# "ui" was removed from this set at H11 (AMD-008/S5, décision humaine 2026-11-17) :
# lattice_core/ui est le paquet de widgets PARTAGÉS, légal sous l'extra [ui].
# "animation" a été retiré par la carte L-LOOP (2026-11-19, DEV-226) : le module
# N-image loop vit désormais LÉGITIMEMENT dans lattice_core (aucun import applicatif) ;
# la copie app (lattice_dither/core/animation.py) reste pour les exports 1.1 gelés,
# une carte de déduplication la résorbera.
APPLICATION_MODULES = {"export", "preprocess", "i18n", "cli"}


def _core_modules() -> list[Path]:
    """Return every Python file of the lattice_core package, sorted."""
    return sorted(path for path in CORE.rglob("*.py") if path.name != "__init__.py")


def _imported(targets: list[ast.alias]) -> list[str]:
    """Return the dotted module paths a list of import aliases names."""
    return [alias.name for alias in targets]


def test_core_imports_nothing_from_lattice_dither() -> None:
    """No module of lattice_core may reference lattice_dither in an import."""
    for path in _core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = _imported(node.names)
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert not name.split(".")[0] == "lattice_dither", (
                    f"{path.name} imports {name!r} from the application package"
                )


def test_core_imports_no_pyside6() -> None:
    """The base install must never pull Qt; PySide6 stays behind the ui extra.
    lattice_core/ui (widgets partagés, AMD-008/S5) vit SOUS l'extra [ui] :
    ses modules peuvent importer PySide6 — seuls les modules de base sont contrôlés."""
    for path in _core_modules():
        if path.relative_to(CORE).parts[0] == "ui":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = _imported(node.names)
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert not name.split(".")[0] == "PySide6", (
                    f"{path.name} imports {name!r}, which is not a base dependency"
                )


def test_core_contains_no_application_module() -> None:
    """The moved package excludes the app-only modules by name and by directory."""
    for path in _core_modules():
        relative = path.relative_to(CORE)
        assert relative.parts[0] not in APPLICATION_MODULES, (
            f"application package directory moved into lattice_core: {relative}"
        )
        assert path.stem not in APPLICATION_MODULES, (
            f"application module moved into lattice_core: {relative}"
        )


def test_core_exposes_the_moved_modules() -> None:
    """The five core modules and the four moved packages are importable."""
    import lattice_core.bridge  # noqa: F401
    import lattice_core.color  # noqa: F401
    import lattice_core.dither  # noqa: F401
    import lattice_core.effects  # noqa: F401
    import lattice_core.palettes  # noqa: F401
    import lattice_core.pipeline  # noqa: F401
    import lattice_core.presets  # noqa: F401
    import lattice_core.registry  # noqa: F401
    import lattice_core.types  # noqa: F401

    assert lattice_core.dither.__file__ is not None
    assert lattice_core.effects.__file__ is not None
