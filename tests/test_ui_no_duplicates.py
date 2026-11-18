"""L-UI2: lattice_dither/ui must not redefine the widgets shared by lattice_core/ui.

The card's structural defect S5 was two parallel UIs. This test compares the
class names and ``__all__`` of every module in both packages and asserts the
shared widgets come from core, never from a second app-side definition. The
export dialog moved into core (attempt 2), so no overlap is tolerated at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import lattice_core.ui
import lattice_dither.ui

CORE_DIR = Path(lattice_core.ui.__file__).resolve().parent
APP_DIR = Path(lattice_dither.ui.__file__).resolve().parent

# Widgets the card requires to come from core, never redefined in the app.
SHARED_WIDGETS = (
    "PreviewCanvas",
    "RenderWorker",
    "PaletteExtraction",
    "LookGallery",
    "PresetIndicator",
    "RenderResult",
    "PreviewResult",
    "ConnectionProbe",
    "ExportDialog",
    "ExportError",
)


def _module_classes(directory: Path) -> dict[str, set[str]]:
    """Return the top-level class names defined in each .py module of directory."""
    out: dict[str, set[str]] = {}
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        out[path.name] = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    return out


def _module_all(directory: Path) -> dict[str, set[str]]:
    """Return the literal __all__ names of each module that defines one."""
    out: dict[str, set[str]] = {}
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            out[path.name] = {
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            }
    return out


def test_shared_widgets_are_defined_in_core_and_not_in_the_app() -> None:
    """Every shared widget exists in core and is absent from every app module."""
    core = _module_classes(CORE_DIR)
    app = _module_classes(APP_DIR)
    core_names = set().union(*core.values())
    app_names = set().union(*app.values())
    for name in SHARED_WIDGETS:
        assert name in core_names, f"{name} is missing from lattice_core/ui"
        assert name not in app_names, f"{name} is still defined in lattice_dither/ui"


def test_the_app_does_not_redefine_core_widgets() -> None:
    """No class name is defined in both packages: the app redefines nothing."""
    core_names = set().union(*_module_classes(CORE_DIR).values())
    app_names = set().union(*_module_classes(APP_DIR).values())
    overlap = core_names & app_names
    assert not overlap, f"new widget duplication: {overlap}"


def test_the_app_ui_imports_the_shared_widgets_from_core() -> None:
    """The app modules that use the shared widgets import them from lattice_core.ui."""
    main_window = (APP_DIR / "main_window.py").read_text(encoding="utf-8")
    assert "from lattice_core.ui.canvas import PreviewCanvas" in main_window
    assert "from lattice_core.ui.worker import" in main_window
    palette_panel = (APP_DIR / "palette_panel.py").read_text(encoding="utf-8")
    assert "from lattice_core.ui.worker import PaletteExtraction" in palette_panel
    commands = (APP_DIR / "commands.py").read_text(encoding="utf-8")
    assert "from lattice_core.ui.export_dialog import run_export_dialog" in commands


def test_no_app_module_defines_a_core___all__widget() -> None:
    """No name exported by a core module's __all__ is redefined as a class in the app."""
    core_all = set().union(*_module_all(CORE_DIR).values()) if _module_all(CORE_DIR) else set()
    app_names = set().union(*_module_classes(APP_DIR).values())
    overlap = core_all & app_names
    assert not overlap, f"__all__ widget redefined in app: {overlap}"
