"""Tests for the Lattice Glitch shell (card L20), Qt offscreen: G9, seeds, masks, no-Qt CLI."""

import ast
import json
import os
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QSlider  # noqa: E402

import lattice_core.effects  # noqa: E402,F401  (registers every effect)
import lattice_glitch  # noqa: E402
from lattice_core import color, mask  # noqa: E402
from lattice_core.animation import render_loop  # noqa: E402
from lattice_core.effects.ntsc import LABEL_NOTES, PRESET_NAMES, SIMPLE_PARAM_IDS  # noqa: E402
from lattice_core.pipeline import PipelineSpec  # noqa: E402
from lattice_core.preset import to_pipeline_spec  # noqa: E402
from lattice_core.registry import get_effect, list_effects, resolve_params  # noqa: E402
from lattice_core.seed import SeedController  # noqa: E402
from lattice_core.ui import ExportDialog, ExportError  # noqa: E402
from lattice_glitch import cli, presets  # noqa: E402
from lattice_glitch import document as doc  # noqa: E402
from lattice_glitch.stack import EffectStack  # noqa: E402
from lattice_glitch.window import MainWindow  # noqa: E402

PACKAGE = Path(lattice_glitch.__file__).resolve().parent
SHIPPED = PACKAGE / "presets"
EFFECT_IDS = [info.id for info in list_effects()]
CLI_MODULES = ("__init__", "__main__", "cli", "document", "hosts", "presets", "stack",
               "window_bridge")
GUI_MODULES = ("actions", "app", "bridge_actions", "bridge_controller", "effects_panel",
               "export_actions", "mask_painter", "mask_panel", "params", "preset_panel",
               "seed_panel", "window", "worker")
BLOCKER = """import sys, importlib.abc
class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] == 'PySide6': raise ImportError('PySide6 is not installed')
sys.meta_path.insert(0, Refuse()); sys.path.insert(0, {root!r})
from lattice_glitch.__main__ import main
code = main(['render', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r}])
forbidden = ('lattice_core.ui', 'lattice_core.animation', 'lattice_dither', 'lattice_glyph')
assert not [m for m in sys.modules if m.split('.')[0] == 'PySide6' or m.startswith(forbidden)]
raise SystemExit(code)"""
LOOP_BLOCKER = """import sys, importlib.abc
class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] == 'PySide6': raise ImportError('PySide6 is not installed')
sys.meta_path.insert(0, Refuse()); sys.path.insert(0, {root!r})
from lattice_glitch.__main__ import main
code = main(['loop', '--preset', {preset!r}, '--in', {source!r}, '--out', {target!r},
             '--frames', '4'])
forbidden = ('lattice_core.ui', 'lattice_dither', 'lattice_glyph')
assert not [m for m in sys.modules if m.split('.')[0] == 'PySide6' or m.startswith(forbidden)]
assert 'lattice_core.animation' in sys.modules
raise SystemExit(code)"""


class _FakeClient:
    """Stand-in for a live ArtCraft client used by the bridge verbs."""
    def render_document(self):
        return color.to_pil(np.full((16, 16, 3), 128, np.uint8))

    def place_as_layer(self, img, name=None):
        return 3

    def disconnect(self):
        return None


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


def _png(path: str | Path, rgb8: np.ndarray) -> Path:
    color.to_pil(rgb8).save(path, format="PNG")
    return Path(path)


def _settle(predicate, timeout_ms: int = 20000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate(), "the asynchronous shell never reached the expected state"


def _r(preset, source, out, *extra) -> int:
    return cli.main(["render", "--preset", str(preset), "--in", str(source),
                     "--out", str(out), *extra])


def _loop(preset, source, out, frames, *extra) -> int:
    return cli.main(["loop", "--preset", str(preset), "--in", str(source),
                     "--out", str(out), "--frames", str(frames), *extra])


def _cli(tmp_path: Path, preset: Path, source: Path, name: str = "cli") -> bytes:
    target = tmp_path / f"{name}.png"
    assert _r(preset, source, target) == cli.EXIT_OK
    return target.read_bytes()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    return names


def test_shell_opens_stacks_reorders_saves(make_window, tmp_path: Path, image_file: Path,
                                           image: np.ndarray, monkeypatch: pytest.MonkeyPatch,
                                           quiet: list[str]) -> None:
    """Accept: launch, open, stack two effects, reorder, save; the bridge dot probes live."""
    window = make_window()
    assert window.windowTitle() == lattice_glitch.APP_NAME
    assert window.tabs.count() == 4 and "reroll" in window.action_map
    _settle(lambda: window.bridge_dot.state() != "unknown")
    assert window.bridge_dot.state() == "disconnected"
    assert "disconnected" in window.connection_label.text()
    assert window.open_path(tmp_path / "nope.png") is False
    window.export_dialog()
    assert window.source is None and quiet
    with pytest.raises(doc.DocumentError):
        window.export_to(tmp_path / "out.png")
    window.set_source(np.zeros((9000, 4, 3), dtype=np.float32))
    assert window.source is None and "9000" in quiet[-1]
    assert window.open_path(image_file) is True
    window.effects_panel.add_effect("noise")
    window.effects_panel.add_effect("rgb_shift")
    assert window.effect_stack.effect_ids() == ["noise", "rgb_shift"]
    _settle(lambda: window.canvas.qimage() is not None)
    window.effects_panel.list.setCurrentRow(1)
    window.effects_panel.move_selected(-1)
    assert window.effect_stack.effect_ids() == ["rgb_shift", "noise"]
    assert [i.effect_id for i in window.spec.post_effects] == ["rgb_shift", "noise"]
    window.save_preset_to(str(tmp_path / "user" / "mine.json"))
    saved = presets.read_preset(tmp_path / "user" / "mine.json")
    assert [e["name"] for e in saved.effects] == ["rgb_shift", "noise"]
    assert window.indicator.preset_name() == "mine.json"
    window.apply_preset(saved)
    assert window.effect_stack.effect_ids() == ["rgb_shift", "noise"]
    entries = window.preset_panel.entries()
    assert entries and any(e.name == "mine.json" and not e.read_only for e in entries)
    monkeypatch.setattr("lattice_glitch.bridge_actions.discover", lambda host: None)
    window.send_to_host()
    _settle(lambda: "not running" in window.statusBar().currentMessage())
    window.get_from_host()
    _settle(lambda: "not running" in window.statusBar().currentMessage())
    assert window.source is not None and len(quiet) == 3
    assert window.bridge_dot.state() == "disconnected"


def test_cli_and_gui_write_identical_bytes(make_window, tmp_path: Path,
                                           image_file: Path, quiet: list[str]) -> None:
    """Accept (G9): CLI render and GUI export are byte-identical for the same preset."""
    window = make_window()
    assert window.open_path(image_file) is True
    for preset in sorted(SHIPPED.glob("*.json")):
        expected = _cli(tmp_path, preset, image_file, preset.stem)
        window.apply_preset(presets.read_preset(preset))
        window.export_to(tmp_path / "gui.png")
        assert (tmp_path / "gui.png").read_bytes() == expected, preset.name
    spec = presets.default_spec()
    spec.seed, spec.brightness = 42, 0.1
    stack = EffectStack()
    stack.add("channel_shift", {"amount": 10.0})
    stack.add("noise", {"amount": 0.2})
    window.spec, window.effect_stack = spec, stack
    window.controller = SeedController(spec.seed)
    window.effects_panel.load(stack, [])
    window.sync_spec()
    window.save_preset_to(str(tmp_path / "user" / "edited.json"))
    expected = _cli(tmp_path, tmp_path / "user" / "edited.json", image_file, "edited")
    window.export_to(tmp_path / "gui.png")
    assert (tmp_path / "gui.png").read_bytes() == expected
    mid = window.mask_panel.new_mask()
    window.mask_panel.painter.set_brush(1.0, 9)
    window.mask_panel.painter.paint_at(40, 40)
    window.effect_stack.set_mask(1, mid)
    window.sync_spec()
    window.save_preset_to(str(tmp_path / "user" / "masked.json"))
    expected = _cli(tmp_path, tmp_path / "user" / "masked.json", image_file, "masked")
    window.export_to(tmp_path / "gui.png")
    assert (tmp_path / "gui.png").read_bytes() == expected
    assert window.effects_panel.effect_choices() == EFFECT_IDS and len(EFFECT_IDS) == 17
    small = window.source[:48, :64]
    for effect_id in EFFECT_IDS:
        while len(window.effect_stack):
            window.effect_stack.remove(0)
        window.effects_panel.add_effect(effect_id)
        window.sync_spec()
        assert window.effect_stack.effect_ids() == [effect_id]
        assert [i.effect_id for i in window.spec.post_effects] == window.effect_stack.effect_ids()
        assert window.render_full(small, window.spec).shape == (48, 64, 3), effect_id
    assert not quiet


def test_reroll_lock_and_stream_parity(make_window, tmp_path: Path, image_file: Path) -> None:
    """Accept: reroll changes output; lock keeps module 0 (both active); the stream survives G9."""
    window = make_window()
    assert window.open_path(image_file) is True
    window.effects_panel.add_effect("noise")
    window.effects_panel.add_effect("jpeg_glitch")
    full0 = window.render_full(window.source, window.spec)
    window.reroll()
    assert not np.array_equal(full0, window.render_full(window.source, window.spec))
    assert window.spec.seed == window.controller.seed
    assert window.seed_panel.seed_edit.text() == str(window.controller.seed)
    window.seed_panel.lock_check(0).setChecked(True)
    assert window.controller.locked() == frozenset({0})
    params = resolve_params(get_effect("noise").params, window.effect_stack.params_of(0))
    noise = get_effect("noise").fn
    stage0 = noise(window.source, params, window.controller.rng(0))
    both_locked = window.render_full(window.source, window.spec)
    seed_before = window.controller.seed
    window.reroll()
    assert window.controller.seed != seed_before
    assert np.array_equal(stage0, noise(window.source, params, window.controller.rng(0)))
    assert not np.array_equal(both_locked, window.render_full(window.source, window.spec))
    locked_stream = window.controller.module_seed_for(0)
    target = tmp_path / "user" / "locked.json"
    window.save_preset_to(str(target))
    entries = json.loads(target.read_text())["effects"]
    assert entries[0]["seed"] == locked_stream and "seed" not in entries[1]
    expected = _cli(tmp_path, target, image_file, "locked")
    window.export_to(tmp_path / "gui.png")
    assert (tmp_path / "gui.png").read_bytes() == expected
    window.apply_preset(presets.read_preset(target))
    assert window.controller.locked() == frozenset({0})
    assert window.render_context().streams[0] == locked_stream
    window.export_to(tmp_path / "gui.png")
    assert (tmp_path / "gui.png").read_bytes() == expected
    before = window.render_context().streams
    window.reroll()
    after = window.render_context().streams
    assert after[0] == before[0] == locked_stream and after[1] != before[1]
    window.seed_panel.lock_check(0).setChecked(False)
    assert window.controller.locked() == frozenset()
    window.reroll()
    assert not np.array_equal(both_locked, window.render_full(window.source, window.spec))


def test_ntsc_simple_mode_presets_and_tooltips(make_window, image_file: Path) -> None:
    """§16: ntsc defaults to four sliders, six named presets, honest tooltips, advanced toggle."""
    window = make_window()
    assert window.open_path(image_file) is True
    window.effects_panel.add_effect("ntsc")
    panel = window.effects_panel
    assert not panel.ntsc_row.isHidden()
    assert tuple(s.id for s in panel.form.specs()) == SIMPLE_PARAM_IDS
    assert len(panel.form.specs()) == 4 and len(panel.form.findChildren(QSlider)) == 4
    for spec in panel.form.specs():
        assert panel.form.widget(spec.id).toolTip() == LABEL_NOTES[spec.id]
    names = [panel.ntsc_preset_box.itemText(i) for i in range(panel.ntsc_preset_box.count())]
    assert names == list(PRESET_NAMES) and len(names) == 6
    panel.ntsc_preset_box.setCurrentIndex(names.index("VHS Home"))
    assert window.effect_stack.params_of(0)["tape_speed"] == "ep"
    assert window.effect_stack.params_of(0)["tracking_noise"] == 0.7
    panel.ntsc_advanced.setChecked(True)
    assert len(panel.form.specs()) == 14
    assert window.effect_stack.params_of(0)["tape_speed"] == "ep"
    panel.ntsc_advanced.setChecked(False)
    assert len(panel.form.specs()) == 4
    window.effects_panel.add_effect("noise")
    assert panel.ntsc_row.isHidden()


def test_mask_painter_produces_a_mask_the_renderer_honours(make_window, image_file: Path,
                                                           image: np.ndarray,
                                                           tmp_path: Path) -> None:
    """Accept: the painted mask localises the effect; deleting it purges slots and exports safe."""
    window = make_window()
    assert window.open_path(image_file) is True
    mid = window.mask_panel.new_mask()
    plane = window.mask_panel.planes()[mid]
    assert plane.shape == image.shape[:2] and not plane.any()
    window.mask_panel.painter.set_brush(1.0, 6)
    window.mask_panel.painter.paint_at(20, 20)
    assert plane[20, 20] == 1.0 and plane[80, 110] == 0.0
    window.effects_panel.add_effect("noise", {"amount": 1.0})
    window.effect_stack.set_mask(0, mid)
    window.sync_spec()
    rendered = window.render_full(window.source, window.spec)
    params = resolve_params(get_effect("noise").params, {"amount": 1.0})
    rng = SeedController(window.spec.seed).rng(0)
    effect = np.ascontiguousarray(np.clip(get_effect("noise").fn(window.source, params, rng),
                                          0, 1), np.float32)
    expected = color.to_rgb8(mask.apply(window.source, effect, mask=plane))
    assert np.array_equal(rendered, expected)
    assert np.array_equal(rendered[80, 110], color.to_rgb8(window.source)[80, 110])
    window.mask_panel.generate("h")
    ramp = np.linspace(0, 1, image.shape[1], dtype=np.float32)[None, :]
    assert np.array_equal(plane, mask.from_png(mask.to_png(np.broadcast_to(ramp, plane.shape))))
    window.mask_panel.lo_spin.setValue(0.2)
    window.mask_panel.hi_spin.setValue(0.8)
    window.mask_panel.generate("luma")
    want = mask.from_png(mask.to_png(np.clip((color.luminance(window.source) - 0.2) / 0.6, 0, 1)))
    assert np.array_equal(plane, want)
    out = window.mask_panel.export_png(tmp_path / "m.png")
    assert out is not None and np.array_equal(mask.import_png(out), plane)
    window.mask_panel.delete_active()
    assert window.mask_panel.mask_ids() == [] and window.effect_stack.mask_ids() == (None,)
    window.effect_stack.set_mask(0, "ghost")
    window.sync_spec()
    dialog = ExportDialog(window.source, window.spec, window,
                          render_full=lambda s: window.exporter.render_full(window.source, s),
                          settings=window.settings())
    dialog.format_box.setCurrentIndex(dialog.format_box.findData("png"))
    dialog.path_edit.setText(str(tmp_path / "orphan.png"))
    with pytest.raises(ExportError):
        window.exporter.render_full(window.source, window.spec)
    dialog._on_export()
    assert "ghost" in dialog.report.text() and not (tmp_path / "orphan.png").exists()
    dialog.deleteLater()


def test_presets_document_stack_and_masks(tmp_path: Path, image: np.ndarray) -> None:
    """Shipped presets validate; document failures are typed; stack and large masks round-trip."""
    reports = presets.validate_all((SHIPPED,))
    assert len(reports) >= 6 and all(report.ok for report in reports)
    assert all(presets.read_preset(SHIPPED / r.name).app == presets.APP_CONTEXT for r in reports)
    spec = presets.default_spec()
    assert spec.algorithm_id is None and spec.palette is None
    assert presets.user_preset_dir().parent.name == "LatticeGlitch"
    with pytest.raises(doc.DocumentError, match="nope.png"):
        doc.load_image(tmp_path / "nope.png")
    with pytest.raises(doc.DocumentError):
        doc.render_rgb8(image, PipelineSpec())
    with pytest.raises(doc.DocumentError):
        doc.format_of("a.jpg")
    preset = presets.to_preset(spec, name="x")
    export = doc.write_render(image, preset, tmp_path / "deep" / "out.png")
    assert export.path.read_bytes() == doc.png_bytes(doc.render_preset(image, preset))
    assert presets.describe(preset)["app"] == "glitch"
    stack = EffectStack()
    stack.add("noise", {"amount": 0.3}, "gate")
    stack.add("crt")
    stack.set_enabled(1, False)
    rebuilt = EffectStack.from_entries(stack.to_entries())
    assert rebuilt.effect_ids() == ["noise", "crt"] and rebuilt.mask_ids() == ("gate", None)
    assert rebuilt.slots()[1].instance.enabled is False
    rebuilt.move(0, 1)
    assert rebuilt.effect_ids() == ["crt", "noise"]
    with pytest.raises(IndexError):
        rebuilt.move(0, 5)
    with pytest.raises(KeyError):
        stack.add("not_an_effect")
    assert doc.fit_mask(np.zeros((8, 8), np.float32), (4, 4)).shape == (4, 4)
    rng = np.random.default_rng(1)
    big = EffectStack()
    big.add("noise", {"amount": 0.5}, "big")
    target = tmp_path / "big.json"
    presets.save_spec(target, spec, stack=big, masks={"big": rng.random((320, 320), np.float32)})
    entry = json.loads(target.read_text())["masks"]["big"]
    assert "path" in entry and "data" not in entry and Path(entry["path"]).exists()
    assert presets.validate(target).ok
    loaded = presets.read_preset(target)
    assert doc.render_preset(rng.random((320, 320, 3), np.float32), loaded).shape == (320, 320, 3)
    assert doc.context_of_preset(loaded).mask_ids == ("big",)


def test_cli_render_verbs_and_no_qt(capsys: pytest.CaptureFixture[str], tmp_path: Path,
                                    image_file: Path) -> None:
    """§8 render: exit codes, --json purity, suffix rules, and the CLI path imports no Qt."""
    T = tmp_path
    P, SRC = T / "preset.json", image_file
    presets.save_spec(P, presets.default_spec())
    out = T / "out.png"
    assert _r(P, SRC, out, "--json") == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["bytes"] == out.stat().st_size
    assert cli.main(["render", "--json"]) == cli.EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert _r(T / "nope.json", SRC, T / "a.png") == cli.EXIT_USAGE
    assert _r(P, T / "nope.png", T / "b.png") == cli.EXIT_RENDER
    bare = T / "no-suffix"
    assert cli.main([]) == cli.EXIT_USAGE
    assert _r(P, SRC, bare) == cli.EXIT_OK and bare.with_suffix(".png").exists()
    jpg = T / "photo.jpg"
    assert _r(P, SRC, jpg) == cli.EXIT_RENDER
    assert not jpg.exists() and ".jpg" in capsys.readouterr().err
    for path in sorted(PACKAGE.glob("*.py")):
        full = _imports(path)
        tops = {n.split(".")[0] for n in full}
        qt = "PySide6" in tops or any(n.startswith("lattice_core.ui") for n in full)
        assert qt == (path.stem in GUI_MODULES), path.name
        assert not tops & {"lattice_dither", "lattice_glyph"}, path.name
        assert not any(n.startswith("lattice_core.animation") for n in full), path.name
    script = BLOCKER.format(root=str(PACKAGE.parent), source=str(SRC),
                            target=str(T / "bare.png"), preset=str(P))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=300, check=False)
    assert result.returncode == 0, result.stderr
    assert (T / "bare.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_presets_bridge_and_batch(capsys: pytest.CaptureFixture[str],
                                      monkeypatch: pytest.MonkeyPatch,
                                      tmp_path: Path, image_file: Path) -> None:
    """§8 presets/bridge/batch: tiers, host absent vs present, and a recursive batch."""
    T = tmp_path
    P, SRC = str(T / "preset.json"), str(image_file)
    presets.save_spec(P, presets.default_spec())
    assert cli.main(["presets", "list", "--dir", str(SHIPPED), "--json"]) == cli.EXIT_OK
    assert cli.main(["presets", "show", P, "--json"]) == cli.EXIT_OK
    assert cli.main(["presets", "validate", P, "--json"]) == cli.EXIT_OK
    (T / "broken.json").write_text("{not json", encoding="utf-8")
    assert cli.main(["presets", "validate", str(T / "broken.json"), "--json"]) == cli.EXIT_USAGE
    assert '"ok": false' in capsys.readouterr().out
    assert cli.main(["bridge", "status", "--json"]) == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and [e["host"] for e in report["hosts"]] == ["photocraft", "designcraft"]
    monkeypatch.setattr(cli, "discover_host", lambda host: None)
    assert cli.host_report(["photocraft", "designcraft"]) == [
        {"host": "photocraft", "connected": False}, {"host": "designcraft", "connected": False}]
    assert cli.main(["bridge", "push", "--preset", P, "--host", "designcraft",
                     "--in", SRC]) == cli.EXIT_BRIDGE
    assert cli.main(["bridge", "pull", "--preset", P, "--out", str(T / "o.png")]) == cli.EXIT_BRIDGE
    monkeypatch.setattr(cli, "discover_host", lambda host: _FakeClient())
    assert cli.host_report(["photocraft"]) == [{"host": "photocraft", "connected": True}]
    assert cli.main(["bridge", "pull", "--preset", P, "--out", str(T/"pulled.png")]) == cli.EXIT_OK
    assert (T / "pulled.png").exists()
    assert cli.main(["bridge", "push", "--preset", P, "--host", "photocraft",
                     "--in", SRC, "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["object_id"] == 3
    source_dir = T / "in"
    (source_dir / "sub").mkdir(parents=True)
    for path in (source_dir / "a.png", source_dir / "sub" / "b.png"):
        _png(path, color.to_rgb8(np.full((16, 16, 3), 0.4, np.float32)))
    out_dir = T / "out"
    assert cli.main(["batch", "--preset", P, "--in", str(source_dir),
                     "--out", str(out_dir), "--recursive"]) == cli.EXIT_OK
    assert sorted(p.name for p in out_dir.rglob("*.png")) == ["a.png", "b.png"]


def test_loop_frame_zero_is_the_preset_png_byte_for_byte(tmp_path: Path,
                                                         image_file: Path) -> None:
    """Accept (B2): frame 0 of a Glitch loop IS the PNG of the same preset, byte for byte."""
    source = doc.load_image(image_file)
    for preset_path in sorted(SHIPPED.glob("*.json")):
        preset = presets.read_preset(preset_path)
        expected = _cli(tmp_path, preset_path, image_file, preset_path.stem)
        context = doc.context_of_preset(preset)
        frames = render_loop(source, to_pipeline_spec(preset), count=3, axis="seed",
                             render_fn=partial(doc.render_rgb8, context=context))
        assert len(frames) == 3
        assert doc.png_bytes(frames[0]) == expected, preset_path.name
        target = tmp_path / f"{preset_path.stem}_loop.png"
        assert _loop(preset_path, image_file, target, 3, "--axis", "offset") == cli.EXIT_OK
        with PILImage.open(target) as handle:
            assert handle.format == "PNG" and handle.n_frames == 3
            handle.seek(0)
            frame0 = np.asarray(handle.convert("RGB"))
        assert doc.png_bytes(frame0) == expected, preset_path.name


def test_loop_keeps_the_mask_and_the_session_on_every_frame(make_window, tmp_path: Path,
                                                            image_file: Path) -> None:
    """Accept: the mask holds on all N frames; locks and streams ride the injected loop."""
    window = make_window()
    assert window.open_path(image_file) is True
    mid = window.mask_panel.new_mask()
    window.mask_panel.painter.set_brush(1.0, 6)
    window.mask_panel.painter.paint_at(20, 20)
    window.effects_panel.add_effect("noise", {"amount": 1.0})
    window.effect_stack.set_mask(0, mid)
    window.sync_spec()
    source_rgb8 = color.to_rgb8(window.source)
    frames = window.exporter.loop_frames(4, "seed")
    assert len(frames) == 4
    for frame in frames:
        assert np.array_equal(frame[80, 110], source_rgb8[80, 110])
        assert not np.array_equal(frame[20, 20], source_rgb8[20, 20])
    assert np.array_equal(frames[0], window.render_full(window.source, window.spec))
    masked = tmp_path / "user" / "masked_loop.json"
    window.save_preset_to(str(masked))
    masked_expected = _cli(tmp_path, masked, image_file, "masked_loop")
    assert doc.png_bytes(frames[0]) == masked_expected
    window.seed_panel.lock_check(0).setChecked(True)
    window.reroll()
    locked_frames = window.exporter.loop_frames(3, "seed")
    assert np.array_equal(locked_frames[0], window.render_full(window.source, window.spec))
    locked = tmp_path / "user" / "locked_loop.json"
    window.save_preset_to(str(locked))
    expected = _cli(tmp_path, locked, image_file, "locked_loop")
    assert doc.png_bytes(locked_frames[0]) == expected
    target = tmp_path / "masked_anim.png"
    plane = window.mask_panel.planes()[mid]
    stack = EffectStack()
    stack.add("feedback", {"decay": 0.5, "transform": "displace", "amount": 4.0,
                           "iterations": 1}, mid)
    fb = tmp_path / "user" / "masked_feedback.json"
    presets.save_spec(fb, presets.default_spec(), stack=stack, masks={mid: plane})
    fb_expected = _cli(tmp_path, fb, image_file, "masked_feedback")
    assert _loop(fb, image_file, target, 4, "--axis", "iterations") == cli.EXIT_OK
    with PILImage.open(target) as handle:
        assert handle.n_frames == 4
        for index in range(4):
            handle.seek(index)
            frame = np.asarray(handle.convert("RGB"))
            assert np.array_equal(frame[80, 110], source_rgb8[80, 110])
            assert not np.array_equal(frame[20, 20], source_rgb8[20, 20])
        handle.seek(0)
        assert doc.png_bytes(np.asarray(handle.convert("RGB"))) == fb_expected


def test_export_dialog_writes_gif_and_apng(make_window, tmp_path: Path,
                                           image_file: Path) -> None:
    """Accept (B1): the export dialog offers GIF and APNG, N frames, frame 0 on the G9 path."""
    window = make_window()
    assert window.open_path(image_file) is True
    window.effects_panel.add_effect("noise")
    window.sync_spec()
    dialog = window.exporter.build_dialog()
    box = dialog.format_box
    assert [box.itemData(i) for i in range(box.count())] == ["png", "gif", "apng"]
    assert dialog.stack.count() == 2
    assert [dialog.loop_axis.itemData(i) for i in range(dialog.loop_axis.count())] == [
        "seed", "offset", "iterations", "param"]
    box.setCurrentIndex(box.findData("gif"))
    assert dialog.stack.currentIndex() == 1
    assert dialog.path_edit.text().endswith(".gif")
    assert dialog.loop_axis.currentData() == "seed"
    dialog.loop_axis.setCurrentIndex(dialog.loop_axis.findData("offset"))
    dialog.loop_count.setValue(4)
    dialog.path_edit.setText(str(tmp_path / "clip.gif"))
    dialog._on_export()
    assert "Exported" in dialog.report.text()
    with PILImage.open(tmp_path / "clip.gif") as handle:
        assert handle.format == "GIF" and handle.n_frames == 4
    box.setCurrentIndex(box.findData("apng"))
    assert dialog.path_edit.text().endswith(".png")
    dialog.path_edit.setText(str(tmp_path / "clip.png"))
    dialog._on_export()
    with PILImage.open(tmp_path / "clip.png") as handle:
        assert handle.format == "PNG" and handle.n_frames == 4
        handle.seek(0)
        frame0 = np.asarray(handle.convert("RGB"))
    assert np.array_equal(frame0, window.render_full(window.source, window.spec))
    box.setCurrentIndex(box.findData("png"))
    dialog.path_edit.setText(str(tmp_path / "still.png"))
    dialog._on_export()
    with PILImage.open(tmp_path / "still.png") as handle:
        assert handle.n_frames == 1
    assert dialog.written == [tmp_path / "still.png"]
    dialog.deleteLater()


def test_loop_cli_is_qt_free_and_reports_errors(capsys: pytest.CaptureFixture[str],
                                                tmp_path: Path, image_file: Path) -> None:
    """§8: the loop verb keeps the exit codes and --json purity, and imports no Qt."""
    T = tmp_path
    P = T / "preset.json"
    presets.save_spec(P, presets.default_spec())
    gif = T / "x.gif"
    assert _loop(P, image_file, gif, 0) == cli.EXIT_USAGE
    assert _loop(P, image_file, gif, 3, "--axis", "time") == cli.EXIT_USAGE
    assert _loop(P, image_file, T / "x.jpg", 3) == cli.EXIT_USAGE
    assert _loop(P, image_file, T / "no-suffix", 3) == cli.EXIT_USAGE
    assert _loop(T / "nope.json", image_file, gif, 3) == cli.EXIT_USAGE
    assert _loop(P, T / "nope.png", gif, 3) == cli.EXIT_RENDER
    assert cli.main(["loop", "--preset", str(P), "--in", str(image_file),
                     "--out", str(gif), "--json"]) == cli.EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert _loop(P, image_file, gif, 5, "--axis", "offset", "--json") == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] and payload["frames"] == 5 and payload["format"] == "gif"
    assert payload["axis"] == "offset" and payload["bytes"] == gif.stat().st_size
    with PILImage.open(gif) as handle:
        assert handle.format == "GIF" and handle.n_frames == 5
    echo = SHIPPED / "07_feedback_echo.json"
    iterated = T / "iterated.png"
    assert _loop(echo, image_file, iterated, 4, "--axis", "iterations", "--json") == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["format"] == "apng"
    with PILImage.open(iterated) as handle:
        assert handle.n_frames == 4
        stills = []
        for index in range(4):
            handle.seek(index)
            stills.append(np.asarray(handle.convert("RGB")).copy())
    assert any(not np.array_equal(stills[0], other) for other in stills[1:])
    shifted = T / "shifted.gif"
    assert _loop(P, image_file, shifted, 4, "--axis", "offset") == cli.EXIT_OK
    with PILImage.open(shifted) as handle:
        assert handle.n_frames == 4
        handle.seek(0)
        first = np.asarray(handle.convert("RGB")).copy()
        handle.seek(1)
        assert not np.array_equal(first, np.asarray(handle.convert("RGB")))
    script = LOOP_BLOCKER.format(root=str(PACKAGE.parent), source=str(image_file),
                                 target=str(T / "bare.gif"), preset=str(P))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=300, check=False)
    assert result.returncode == 0, result.stderr
    assert (T / "bare.gif").read_bytes()[:6] in (b"GIF87a", b"GIF89a")


def test_cli_loop_exposes_every_axis_the_core_accepts() -> None:
    """The CLI and the export dialog must advertise exactly the core's axes.

    A hard-coded tuple hid ``param`` from the command line while the core had supported it
    since L27: only the tests could animate an effect. This pins the two lists together.
    """
    from lattice_core import animation, axes
    from lattice_glitch.cli import _build_parser

    assert axes.AXES == animation.AXES
    loop = _build_parser()._subparsers._group_actions[0].choices["loop"]
    axis_action = next(a for a in loop._actions if a.dest == "axis")
    assert tuple(axis_action.choices) == animation.AXES
    assert "param" in axis_action.choices


def test_cli_loop_rejects_param_without_the_parameter_name(tmp_path: Path) -> None:
    """`--axis param` alone is a usage error, not a crash inside the renderer."""
    from lattice_glitch.cli import EXIT_USAGE, main

    preset = tmp_path / "bare.json"
    preset.write_text(json.dumps({
        "version": 3, "app": "glitch", "seed": 7,
        "pipeline": {"algorithm": None, "palette": None, "pixel_size": 1},
        "palette": None, "effects": []}))
    image = _png(tmp_path / "src.png", np.full((16, 16, 3), 128, dtype=np.uint8))
    code = main(["loop", "--preset", str(preset), "--in", str(image),
                 "--out", str(tmp_path / "o.gif"), "--frames", "4", "--axis", "param"])
    assert code == EXIT_USAGE
