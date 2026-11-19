"""Render the H13 proof sheet: 4 GIF loops + one frame montage each.

The montage exists because a CLI reader only ever sees frame 0 of a GIF. It picks four
distinct frames along the loop so the movement is judgeable — and it never pads with
duplicates: a loop of 3 frames shows 3 tiles, not 4 with one repeated (the H13c judge read
a duplicated tile as a fourth state that did not exist).

Usage: QT_QPA_PLATFORM=offscreen .venv/bin/python tools/h13_planche.py [--reseed STEP]
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "harness/lattice/docs/h13/new"
SOURCE = ROOT / "docs/bytemosh/00_source.png"
# preset, parameter of the animation, A, B. The ranges are chosen so the effect really
# moves: a range that saturates makes two different settings produce the same image.
LOOPS = (
    ("glitch_01_vhs_soft", "ntsc.snow", 0.02, 0.30),
    ("glitch_02_channel_rift", "channel_shift.amount", 2.0, 24.0),
    # sort_echo animates the ECHO, not the sort: pixel_sort.brightness barely moves the
    # image (measured steps of 0.00-0.01) because above ~0.6 the sort band already covers
    # the row. feedback.amount gives steps of 2.5-3.4.
    ("glitch_03_sort_echo", "feedback.amount", 0.5, 9.0),
    # Animate the BEAM, not the curvature: the judge rejected curvature ("aucun tube
    # ne fait ça") because it swells and shrinks the whole picture. `roll` scrolls the
    # scanlines with the usable surface held constant (measured: 0.7554 on every phase).
    ("glitch_04_crt_finish", "crt.roll", 0.0, 8.0),
)


def _frames(gif: pathlib.Path) -> list[Image.Image]:
    """Return every frame of gif as an RGB image."""
    return [frame.convert("RGB") for frame in ImageSequence.Iterator(Image.open(gif))]


def _montage(gif: pathlib.Path, tiles: int = 4, width: int = 360) -> pathlib.Path:
    """Write a montage of distinct frames of gif, without ever repeating one."""
    frames = _frames(gif)
    height = int(width * frames[0].height / frames[0].width)
    picks = sorted({int(round(i * (len(frames) - 1) / (tiles - 1))) for i in range(tiles)})
    sheet = Image.new("RGB", (width * len(picks), height + 24), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for column, index in enumerate(picks):
        sheet.paste(frames[index].resize((width, height), Image.LANCZOS), (column * width, 24))
        draw.text((column * width + 8, 6), f"frame {index}/{len(frames) - 1}", fill=(230, 230, 230))
    target = OUT / "planches" / f"{gif.stem}_frames.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return target


def _report(gif: pathlib.Path) -> str:
    """Return one line describing how much the loop really moves."""
    raw = [np.asarray(frame.convert("L"), np.float32) for frame in ImageSequence.Iterator(
        Image.open(gif))]
    distinct = len({frame.tobytes() for frame in raw})
    steps = [float(np.abs(raw[i] - raw[i + 1]).mean()) for i in range(len(raw) - 1)]
    return (f"{gif.name:30s} {len(raw):2d} frames | {distinct} distinctes | "
            f"pas {min(steps):5.2f}-{max(steps):5.2f}")


def main() -> int:
    """Render every loop with the CLI, then write the montages and the report."""
    import subprocess
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--reseed", type=int, default=7)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, param, low, high in LOOPS:
        command = [
            sys.executable, "-m", "lattice_glitch.cli", "loop",
            "--preset", str(ROOT / f"presets/starter/{name}.json"),
            "--in", str(SOURCE), "--out", str(OUT / f"{name}.gif"),
            "--frames", "8", "--axis", "param", "--param", param,
            "--from", str(low), "--to", str(high),
        ]
        if args.reseed:
            command += ["--reseed", str(args.reseed)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"{name}: ECHEC {result.stderr.strip()[-200:]}")
            continue
        print(_report(OUT / f"{name}.gif"))
    for gif in sorted(OUT.glob("*.gif")):
        print("planche:", _montage(gif).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
