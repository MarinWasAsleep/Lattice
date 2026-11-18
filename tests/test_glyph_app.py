"""Tests for the Lattice Glyph shell (card L12), Qt offscreen: G9, bridge, CLI-without-Qt."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import lattice_core.pipeline as pipeline  # noqa: E402
import lattice_core.renderers  # noqa: E402,F401  (registers every renderer)
import lattice_glyph  # noqa: E402
from lattice_core import color  # noqa: E402
from lattice_core.cell import list_renderers  # noqa: E402
from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, render  # noqa: E402
from lattice_core.svg import SVG_NS  # noqa: E402
from lattice_glyph import cli, presets  # noqa: E402
from lattice_glyph.document import (  # noqa: E402
    FORMATS,
    DocumentError,
    GridError,
    export_bytes,
    format_of,
    grid_bundle,
    load_image,
    render_rgb8,
    target_path,
    write_render,
)
from lattice_glyph.options import OPTIONS, clean, defaults_for  # noqa: E402
from lattice_glyph.window import MainWindow  # noqa: E402

PACKAGE = Path(lattice_glyph.__file__).resolve().parent
SHIPPED = PACKAGE / "presets"
RENDERERS = sorted(list_renderers())


class _FakeClient:
    """Stand-in for a live ArtCraft client used by the bridge verbs."""

    def render_document(self):
        return color.to_pil(np.full((16, 16, 3), 128, np.uint8))

    def place_as_layer(self, img, name=None):
        self.placed = name
        return 3

    def disconnect(self) -> None:
        self.closed = True


CLI_MODULES = ("__init__", "__main__", "cli", "document", "hosts", "options", "presets")
GUI_MODULES = ("actions", "app", "bridge_actions", "bridge_controller", "export_actions",
               "palette_panel", "preset_panel", "renderer_panel", "rendering", "window")
BLOCKER = """import sys, importlib.abc
class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] == 'PySide6': raise ImportError('PySide6 is not installed')
sys.meta_path.insert(0, Refuse()); sys.path.insert(0, {root!r})
from lattice_glyph.cli import main
code = main(['render', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r}])
assert 'PySide6' not in sys.modules and 'lattice_core.ui' not in sys.modules
assert not [m for m in sys.modules if m.startswith('lattice_dither')]
raise SystemExit(code)"""


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collect modal-dialog texts so a failure reports instead of blocking the suite."""
    seen: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: seen.append(str(a[2])))
    return seen


@pytest.fixture
def image() -> np.ndarray:
    """Deterministic float32 RGB image: noise plus a horizontal gradient."""
    rng, ramp = np.random.default_rng(7), np.linspace(0, 1, 128, dtype=np.float32)
    noise = rng.random((96, 128, 3), np.float32)
    return np.ascontiguousarray(np.clip(0.5 * noise + 0.5 * ramp[None, :, None], 0, 1), np.float32)


@pytest.fixture
def image_file(tmp_path: Path, image: np.ndarray) -> Path:
    return _png(tmp_path / "source.png", color.to_rgb8(image))


@pytest.fixture
def make_window(qapp: QApplication, tmp_path: Path):
    """Return a factory of isolated windows, each stopped and closed at teardown."""
    opened: list[MainWindow] = []

    def build() -> MainWindow:
        window = MainWindow(preset_dirs=(SHIPPED, tmp_path / "user"))
        window._settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        window.show()
        QApplication.processEvents()
        opened.append(window)
        return window

    yield build
    for window in opened:
        window.shutdown()


def _png(path: str | Path, rgb8: np.ndarray) -> str | Path:
    color.to_pil(rgb8).save(path, format="PNG")
    return path


def _preset(tmp_path: Path, spec: PipelineSpec | None = None) -> Path:
    presets.save_spec(path := tmp_path / "preset.json", spec or presets.default_spec())
    return path


def _settle(predicate, timeout_ms: int = 20000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate(), "the asynchronous shell never reached the expected state"


def _cli(tmp_path: Path, preset: Path, source: Path, fmt: str | None = None) -> bytes:
    target = tmp_path / f"cli.{fmt or 'png'}"
    argv = ["render", "--preset", str(preset), "--in", str(source), "--out", str(target)]
    assert cli.main(argv + (["--format", fmt] if fmt else [])) == cli.EXIT_OK
    return target_path(target, fmt or "png").read_bytes()


def _tops(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
             for alias in node.names}
    names |= {node.module for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module}
    return {name.split(".")[0] for name in names}


def test_cli_and_gui_write_identical_bytes_and_keep_hidden_fields(
        make_window, tmp_path: Path, image_file: Path, quiet: list[str]) -> None:
    """Shipped presets, every format, and a panel edit over a non-trivial spec: same bytes (G9)."""
    window = make_window()
    assert window.open_path(image_file) is True
    for preset in sorted(SHIPPED.glob("*.json")):
        expected = _cli(tmp_path, preset, image_file)
        window.apply_spec(presets.spec_of(presets.read_preset(preset)))
        window.export_to(tmp_path / "gui.png")
        assert (tmp_path / "gui.png").read_bytes() == expected, preset.name
    light = _preset(tmp_path)
    window.apply_spec(presets.spec_of(presets.read_preset(light)))
    for fmt in FORMATS:
        expected = _cli(tmp_path, light, image_file, fmt)
        window.export_to(tmp_path / f"gui.{fmt}")
        assert (tmp_path / f"gui.{fmt}").read_bytes() == expected, fmt
        if fmt == "svg":
            assert ET.fromstring(expected.decode()).tag == f"{{{SVG_NS}}}svg"
    spec = presets.default_spec()
    spec.brightness, spec.contrast, spec.gamma = 0.15, 0.30, 2.2
    spec.saturation, spec.pre_blur, spec.auto_levels = 0.40, 1.5, True
    spec.seed, spec.color_metric = 42, "oklab"
    spec.pre_effects = [EffectInstance("gaussian_blur", {"radius": 1.0})]
    spec.post_effects = [EffectInstance("sharpen", {"amount": 0.5})]
    window.apply_spec(spec)
    window.renderer_panel.set_renderer("braille", {"threshold": 0.4, "fg": "#112233"})
    window.on_panels_changed()
    edited = window.spec
    assert (edited.brightness, edited.contrast, edited.gamma) == (0.15, 0.30, 2.2)
    assert (edited.saturation, edited.pre_blur, edited.auto_levels) == (0.40, 1.5, True)
    assert edited.seed == 42 and edited.color_metric == "oklab"
    assert edited.pre_effects == [EffectInstance("gaussian_blur", {"radius": 1.0})]
    assert edited.post_effects == [EffectInstance("sharpen", {"amount": 0.5})]
    window.save_preset_to(str(tmp_path / "user" / "edited.json"))
    window.export_to(tmp_path / "gui.png")
    assert _cli(tmp_path, tmp_path / "user" / "edited.json", image_file) == (
        tmp_path / "gui.png").read_bytes()
    window.apply_spec(PipelineSpec(renderer="pixel", algorithm_id=None, palette=None))
    window.on_panels_changed()
    assert window.spec.algorithm_id is None and window.spec.palette is None
    preset = _preset(tmp_path, window.spec)
    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
                     "--out", str(tmp_path / "c.png")]) == cli.EXIT_OK
    for renderer in RENDERERS:
        spec = PipelineSpec(pixel_size=6, renderer=renderer,
                            palette=PaletteSpec(source="builtin", name="grey_8"))
        bundle = grid_bundle(window.source, spec)
        expected = render(window.source, spec)
        frame = pipeline._render_frame(bundle.renderer, bundle.grid, bundle.palette,
                                       bundle.style)
        assert np.array_equal(color.to_rgb8(frame[: expected.shape[0], : expected.shape[1]]),
                              expected), renderer
    with pytest.raises(GridError):
        grid_bundle(window.source, PipelineSpec(algorithm_id=None, palette=None))
    assert not quiet


def test_shipped_presets_and_document_helpers(tmp_path: Path, image: np.ndarray) -> None:
    """Shipped presets validate in context; document failures are typed DocumentErrors."""
    reports = presets.validate_all((SHIPPED,))
    assert len(reports) >= 4 and all(report.ok for report in reports)
    for report in reports:
        assert presets.read_preset(SHIPPED / report.name).app == presets.APP_CONTEXT
    spec = presets.default_spec()
    assert (spec.renderer, spec.pixel_size) == ("glyph_ramp", 8)
    assert presets.user_preset_dir().parent.name == "LatticeGlyph"
    assert presets.search_dirs()[0] == SHIPPED
    with pytest.raises(DocumentError, match="nope.png"):
        load_image(tmp_path / "nope.png")
    with pytest.raises(DocumentError):
        export_bytes(image, spec, "pdf")
    with pytest.raises(DocumentError):
        render_rgb8(image, PipelineSpec(palette=PaletteSpec(source="custom",
                                                            colors=["#zzz"])))
    assert target_path(tmp_path / "a", "svg").name == "a.svg"
    assert target_path(tmp_path / "a.png", "svg").name == "a.png"
    export = write_render(image, spec, tmp_path / "deep" / "out.png")
    assert export.path.exists() and export.size == export.path.stat().st_size
    spec.post_effects = [EffectInstance("sharpen", {"amount": 0.5})]
    assert "raster" in export_bytes(image, spec, "txt")[1][0]
    assert format_of("a.png") == "png" and format_of("bare") == "png"
    with pytest.raises(DocumentError):
        format_of("a.webp")
    assert 'lattice-glyph = "lattice_glyph.__main__:main"' in (
        PACKAGE / "pyproject.toml").read_text()


def test_shell_opens_previews_saves_and_refuses(make_window, tmp_path: Path, image_file: Path,
                                                image: np.ndarray,
                                                monkeypatch: pytest.MonkeyPatch,
                                                quiet: list[str]) -> None:
    """The shell opens, previews, saves, reports refusals, and a host-less send is a line."""
    window = make_window()
    assert window.tabs.count() == 4
    assert window.bridge_dot.state() in {"unknown", "connected", "disconnected"}
    window.check_bridge()
    _settle(lambda: window.bridge_dot.state() != "unknown")
    assert window.open_path(tmp_path / "nope.png") is False
    window.export_dialog()
    assert window.source is None and quiet
    with pytest.raises(DocumentError):
        window.export_to(tmp_path / "out.png")
    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
    assert window.source is None and len(quiet) == 3 and "9000" in quiet[-1]
    assert window.open_path(image_file) is True
    monkeypatch.setattr("lattice_glyph.hosts.discover", lambda host: None)
    window.set_source(image)
    window.send_to_host()
    _settle(lambda: "not running" in window.statusBar().currentMessage())
    assert len(quiet) == 3
    entries = window.preset_panel.entries()
    assert entries and all(e.path.parent == SHIPPED and e.read_only for e in entries)
    assert window.preset_panel.select_name(entries[0].name)
    window.preset_panel.load_selected()
    assert window.spec.renderer == presets.spec_of(presets.read_preset(entries[0].path)).renderer
    window.save_preset_to(str(tmp_path / "user" / "mine.json"))
    assert (tmp_path / "user" / "mine.json").exists()
    assert window.indicator.preset_name() == "mine.json"
    panel = window.palette_panel
    panel.kind.setCurrentIndex(panel.kind.findData("custom"))
    panel.colors.setText("#000000 #ff0000 #ffffff")
    assert panel.spec().colors == ["#000000", "#ff0000", "#ffffff"] and panel.valid_colours()
    panel.kind.setCurrentIndex(panel.kind.findData("extracted"))
    panel.extract_k.setValue(6)
    window.on_panels_changed()
    assert window.spec.palette is not None and window.spec.palette.extract_k == 6
    ramp = next(entry for entry in window.glyph_browser.catalogue().ramps()
                if entry.ramp != presets.DEFAULT_RAMP)
    window.glyph_browser.ramp_chosen.emit(ramp.id)
    assert (window.spec.renderer, window.spec.renderer_style["ramp"]) == ("glyph_ramp", ramp.ramp)
    assert len(quiet) == 3


def test_cli_verbs_bridge_and_no_qt(capsys: pytest.CaptureFixture[str],
                                    monkeypatch: pytest.MonkeyPatch,
                                    tmp_path: Path, image_file: Path) -> None:
    """The four §8 verbs: exit codes, --json purity, bridge without a host, batch, no Qt."""
    preset = _preset(tmp_path)
    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
                     "--out", str(tmp_path / "out.png"), "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["bytes"] == (tmp_path / "out.png").stat().st_size
    assert cli.main(["render", "--json"]) == cli.EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert cli.main(["render", "--preset", str(tmp_path / "nope.json"), "--in",
                     str(image_file), "--out", str(tmp_path / "a.png")]) == cli.EXIT_USAGE
    assert cli.main(["render", "--preset", str(preset), "--in", str(tmp_path / "nope.png"),
                     "--out", str(tmp_path / "b.png")]) == cli.EXIT_RENDER
    bare = tmp_path / "no-suffix"
    assert cli.main([]) == cli.EXIT_USAGE
    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
                     "--out", str(bare)]) == cli.EXIT_OK and bare.with_suffix(".png").exists()
    jpg = tmp_path / "photo.jpg"
    assert cli.main(["render", "--preset", str(preset), "--in", str(image_file),
                     "--out", str(jpg)]) == cli.EXIT_RENDER
    assert not jpg.exists() and ".jpg" in capsys.readouterr().err
    for name, qt in [(n, False) for n in CLI_MODULES] + [(n, True) for n in GUI_MODULES]:
        tops = _tops(PACKAGE / f"{name}.py")
        assert ("PySide6" in tops) is qt, name
        assert "lattice_core.ui" not in tops or qt, name
    for path in sorted(PACKAGE.rglob("*.py")):
        assert not _tops(path) & {"lattice_dither", "lattice_glitch"}, path.name
    source = _png(tmp_path / "source.png", color.to_rgb8(np.full((16, 16, 3), 0.5, np.float32)))
    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(source),
                            target=str(tmp_path / "bare.png"), preset=str(_preset(tmp_path)))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=300, check=False)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bare.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and [e["host"] for e in report["hosts"]] == ["photocraft", "designcraft"]
    assert cli.main(["bridge", "status", "photocraft"]) == cli.EXIT_OK
    assert capsys.readouterr().out.splitlines() == [
        f"photocraft: {'connected' if report['hosts'][0]['connected'] else 'not running'}"]

    def broken(token_path=None, port=None):
        raise OSError("connection refused")

    monkeypatch.setattr("lattice_core.bridge.photocraft.PhotoCraftClient.discover",
                        staticmethod(broken))
    monkeypatch.setattr("lattice_core.bridge.designcraft.DesignCraftClient.discover",
                        staticmethod(broken))
    assert cli.host_report(["photocraft", "designcraft"]) == [
        {"host": "photocraft", "connected": False}, {"host": "designcraft", "connected": False}]
    assert cli.main(["bridge", "push", "--preset", str(preset), "--host", "designcraft",
                     "--in", str(source)]) == cli.EXIT_BRIDGE
    assert cli.main(["bridge", "pull", "--preset", str(preset), "--out",
                     str(tmp_path / "o.png")]) == cli.EXIT_BRIDGE
    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
    assert cli.main(["bridge", "pull", "--preset", str(preset),
                     "--out", str(tmp_path / "pulled.png")]) == cli.EXIT_OK
    assert (tmp_path / "pulled.png").exists()
    assert cli.main(["bridge", "push", "--preset", str(preset), "--host", "photocraft",
                     "--in", str(source), "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["object_id"] == 3
    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
    assert cli.main(["presets", "show", str(preset), "--json"]) == cli.EXIT_OK
    assert cli.main(["presets", "validate", str(preset), "--json"]) == cli.EXIT_OK
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert cli.main(["presets", "validate", str(tmp_path / "broken.json"),
                     "--json"]) == cli.EXIT_USAGE
    assert '"ok": false' in capsys.readouterr().out
    source_dir = tmp_path / "in"
    (source_dir / "sub").mkdir(parents=True)
    for path in (source_dir / "a.png", source_dir / "sub" / "b.png"):
        _png(path, color.to_rgb8(np.full((16, 16, 3), 0.4, np.float32)))
    out_dir = tmp_path / "out"
    assert cli.main(["batch", "--preset", str(preset), "--in", str(source_dir),
                     "--out", str(out_dir), "--recursive"]) == cli.EXIT_OK
    assert sorted(path.name for path in out_dir.rglob("*.png")) == ["a.png", "b.png"]


def test_every_registered_renderer_is_selectable(make_window, image_file: Path,
                                                 quiet: list[str]) -> None:
    """The selector offers exactly the registry; each choice renders; bad text edits never do."""
    window = make_window()
    assert window.renderer_panel.renderers() == RENDERERS == sorted(OPTIONS)
    assert window.open_path(image_file) is True
    img = np.linspace(0.0, 1.0, 48 * 64 * 3, dtype=np.float32).reshape(48, 64, 3)
    for renderer in RENDERERS:
        bare = PipelineSpec(pixel_size=6, renderer=renderer, renderer_style={})
        filled = PipelineSpec(pixel_size=6, renderer=renderer,
                              renderer_style=defaults_for(renderer))
        assert np.array_equal(render(img, bare), render(img, filled)), renderer
        window.renderer_panel.set_renderer(renderer)
        window.on_panels_changed()
        assert window.spec.renderer == renderer == window.renderer_panel.current()
        for spec in OPTIONS[renderer]:
            assert window.spec.renderer_style.get(spec.key, spec.default) == spec.default
        _settle(lambda: window.canvas.qimage() is not None)
    assert clean("glyph_ramp", {"ramp": "@%#*+=-:. ", "offset": 0.0}) == {}
    ramp = {"ramp": " .:-=+*#%@", "mode": "palette"}
    assert clean("glyph_ramp", ramp) == ramp
    with pytest.raises(ValueError):
        clean("glyph_ramp", {"mode": "spectral"})
    window.renderer_panel.set_renderer("glyph_ramp")
    spec0 = window.spec
    field = window.renderer_panel.option_widget("fg")
    field.setText("#f")
    assert window.spec is spec0 and not quiet
    assert "must be" in field.toolTip() and field.styleSheet()
    field.setText("#112233")
    assert window.spec.renderer_style.get("fg") == "#112233" and not quiet
