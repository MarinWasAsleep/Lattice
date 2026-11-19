"""Smoke d'installation Lattice : prouve le demarrage GUI, le CLI et le chargement d'image.

Tout tourne en mode Qt ``offscreen`` : aucun écran n'est requis. Le GUI est
considéré ouvert quand le journal nommé « … window shown » apparaît ; le
chargement d'image est vérifié en instanciant chaque fenêtre et en lui donnant
un PNG déterministe. Sortie JSON, code 1 avec une ligne nommée en cas d'échec.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APPS: tuple[str, ...] = ("dither", "glyph", "glitch")
GUI_TIMEOUT = 10.0


def _python() -> str:
    """Return the interpreter running this tool."""
    return sys.executable


def _run(argv: list[str], timeout: float = 20.0) -> tuple[int, str]:
    """Run argv and return (exit code, combined output)."""
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (124, str(exc))
    return (done.returncode, (done.stdout or "") + (done.stderr or ""))


def check_cli(python: str) -> dict[str, Any]:
    """Return one CLI result per app, using a display-free verb."""
    commands = {
        "dither": [python, "-m", "lattice.modes.dither.cli", "--help"],
        "glyph": [python, "-m", "lattice.modes.glyph", "presets", "list"],
        "glitch": [python, "-m", "lattice.modes.glitch", "presets", "list"],
    }
    results: dict[str, Any] = {}
    for app, argv in commands.items():
        code, output = _run(argv)
        results[app] = {
            "ok": code == 0,
            "command": " ".join(argv[1:]),
            "exit": code,
            "detail": output.strip().splitlines()[:1],
        }
    return results


def check_gui(python: str) -> dict[str, Any]:
    """Launch each app offscreen and wait for its named 'window shown' log line."""
    results: dict[str, Any] = {}
    for app in APPS:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUNBUFFERED="1")
        marker = f"Lattice {app.capitalize()} window shown"
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                [python, "-m", f"lattice_{app}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env,
            )
        except OSError as exc:
            results[app] = {"ok": False, "detail": str(exc)}
            continue
        assert proc.stdout is not None
        sink = lines

        def read(pipe: Any = proc.stdout, out: list[str] = sink) -> None:
            for line in pipe:
                out.append(line.rstrip())

        threading.Thread(target=read, daemon=True).start()
        deadline = time.monotonic() + GUI_TIMEOUT
        while time.monotonic() < deadline and proc.poll() is None:
            if any(marker in line for line in lines):
                break
            time.sleep(0.05)
        shown = any(marker in line for line in lines)
        crashed = any("Traceback" in line for line in lines)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        results[app] = {
            "ok": shown and not crashed,
            "marker": marker,
            "detail": lines[-1] if lines else "no output",
        }
    return results


def _image_check_one(app: str, path: Path) -> dict[str, Any]:
    """Instantiate one app's window, load path, and report whether it adopted it."""
    try:
        if app == "dither":
            from lattice.modes.dither.ui.main_window import MainWindow

            window = MainWindow()
            window.commands.open_path(str(path))
            ok = getattr(window, "source", None) is not None
        else:
            module = __import__(f"lattice_{app}.window", fromlist=["MainWindow"])
            window = module.MainWindow()
            ok = bool(window.open_path(path)) and getattr(window, "source", None) is not None
        window.close()
        return {"ok": bool(ok), "detail": "image adopted as window source"}
    except Exception as exc:  # noqa: BLE001 - verification tool reports, never crashes
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def image_check() -> dict[str, Any]:
    """Load a deterministic PNG into all three windows inside one offscreen Qt app."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PySide6.QtWidgets import QApplication

    app_qt = QApplication.instance() or QApplication([])
    assert app_qt is not None
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "smoke.png"
        Image.new("RGB", (24, 16), (120, 60, 30)).save(path)
        for app in APPS:
            results[app] = _image_check_one(app, path)
    return results


def main(argv: list[str] | None = None) -> int:
    """Run the smoke checks, print JSON, and exit 1 naming the first failing item."""
    parser = argparse.ArgumentParser(prog="smoke_install.py")
    parser.add_argument("--image-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="print only JSON")
    parser.add_argument("--python", default=None, help="interpreter to test (default: this one)")
    args = parser.parse_args(argv)

    if args.image_check:
        print(json.dumps(image_check(), ensure_ascii=False))
        return 0

    python = args.python or _python()
    report = {
        "python": python,
        "cli": check_cli(python),
        "gui": check_gui(python),
        "image": {},
    }
    code, output = _run([python, str(Path(__file__).resolve()), "--image-check"], timeout=60)
    if code == 0:
        try:
            report["image"] = json.loads(output.strip().splitlines()[-1])
        except (ValueError, IndexError):
            report["image"] = {"error": "child produced no JSON"}
    else:
        report["image"] = {"error": output.strip().splitlines()[-1:] or f"exit {code}"}

    failures = [
        f"{section}:{app}"
        for section in ("cli", "gui", "image")
        for app in APPS
        if not report[section].get(app, {}).get("ok", False)
    ]
    report["ok"] = not failures
    report["failures"] = failures
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for section in ("cli", "gui", "image"):
            for app in APPS:
                item = report[section].get(app, {})
                status = "OK" if item.get("ok") else "FAIL"
                print(f"{section:6} {app:7} {status}  {item.get('detail', '')}")
        for failure in failures:
            print(f"SMOKE FAILED: {failure}", file=sys.stderr)
        print("SMOKE OK" if report["ok"] else f"SMOKE FAILED ({len(failures)})")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
