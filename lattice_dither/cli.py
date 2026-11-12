"""Command-line interface and batch rendering (CONTRACT §17)."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image as PILImage

import lattice_dither.algorithms  # noqa: F401  (importing the package registers every algorithm)
import lattice_dither.effects  # noqa: F401  (importing the package registers every effect)
from lattice_dither.core import color
from lattice_dither.core.pipeline import PipelineSpec, render
from lattice_dither.core.presets import load_preset

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INPUT = 2
EXIT_RENDER = 3

DEFAULT_EXTENSIONS = "png,jpg,jpeg"
OUTPUT_SUFFIX = ".png"


class InputError(Exception):
    """A missing or unreadable input: preset, image or directory."""


class RenderError(Exception):
    """A failure inside the render pipeline."""


class _Parser(argparse.ArgumentParser):
    """Argument parser that reports usage errors with exit code 1, not argparse's 2."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _load_spec(path: str | Path) -> PipelineSpec:
    """Load a preset, raising InputError when it is missing or malformed."""
    target = Path(path)
    if not target.is_file():
        raise InputError(f"preset not found: {target}")
    try:
        return load_preset(target)
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(f"cannot read preset {target}: {exc}") from None


def _load_image(path: str | Path) -> color.Image:
    """Load an image as float32 RGB, raising InputError when it is missing or unreadable."""
    target = Path(path)
    if not target.is_file():
        raise InputError(f"input not found: {target}")
    try:
        with PILImage.open(target) as handle:
            return color.to_float(handle)
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot read image {target}: {exc}") from None


def _render_file(
    spec: PipelineSpec, source: Path, target: Path, max_side: int | None = None
) -> None:
    """Render one image through the pipeline and write it as PNG."""
    image = _load_image(source)
    try:
        rgb8 = render(image, spec, max_side=max_side)
    except Exception as exc:  # noqa: BLE001 - any pipeline failure is a render error
        raise RenderError(f"render failed for {source}: {exc}") from None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        color.to_pil(rgb8).save(target, format="PNG")
    except OSError as exc:
        raise RenderError(f"cannot write {target}: {exc}") from None


def _render_job(payload: tuple[PipelineSpec, str, str, int | None]) -> tuple[str, str | None]:
    """Render one batch item in a worker process, returning (output, error or None)."""
    spec, source, target, max_side = payload
    try:
        _render_file(spec, Path(source), Path(target), max_side)
    except (InputError, RenderError) as exc:
        return target, str(exc)
    return target, None


def _emit(args: argparse.Namespace, ok: bool, files: list[str], errors: list[str]) -> None:
    """Print the machine-readable summary when --json is set."""
    if getattr(args, "json", False):
        print(json.dumps({"ok": ok, "files": files, "errors": errors}))


def _note(message: str) -> None:
    """Print one human-readable progress line on stderr."""
    print(message, file=sys.stderr)


def _describe(spec: PipelineSpec, path: Path) -> dict:
    """Return a JSON-serialisable description of a preset, without rendering it."""
    return {
        "preset": str(path),
        "algorithm": spec.algorithm_id,
        "algorithm_params": dict(spec.algorithm_params),
        "palette": {
            "source": spec.palette.source,
            "name": spec.palette.name,
            "colors": list(spec.palette.colors),
            "extract_k": spec.palette.extract_k,
            "extract_method": spec.palette.extract_method,
            "locked": list(spec.palette.locked),
            "order": list(spec.palette.order),
        },
        "pre_effects": [
            {"id": e.effect_id, "enabled": e.enabled, "params": dict(e.params)}
            for e in spec.pre_effects
        ],
        "post_effects": [
            {"id": e.effect_id, "enabled": e.enabled, "params": dict(e.params)}
            for e in spec.post_effects
        ],
        "color_metric": spec.color_metric,
        "pixel_size": spec.pixel_size,
        "seed": spec.seed,
    }


def _format_description(description: dict) -> str:
    """Render a preset description as aligned text."""
    palette = description["palette"]
    if palette["source"] == "builtin":
        palette_text = f"builtin/{palette['name']}"
    elif palette["source"] == "custom":
        palette_text = f"custom ({len(palette['colors'])} colours)"
    else:
        palette_text = f"extracted ({palette['extract_method']}, k={palette['extract_k']})"
    lines = [
        f"preset:     {description['preset']}",
        f"algorithm:  {description['algorithm']}",
        f"palette:    {palette_text}",
        f"metric:     {description['color_metric']}",
        f"pixel size: {description['pixel_size']}",
    ]
    for label, key in (("pre", "pre_effects"), ("post", "post_effects")):
        chain = description[key]
        if not chain:
            lines.append(f"{label} effects: none")
            continue
        rendered = ", ".join(
            f"{entry['id']}{'' if entry['enabled'] else ' (off)'}" for entry in chain
        )
        lines.append(f"{label} effects: {rendered}")
    return "\n".join(lines)


def _cmd_render(args: argparse.Namespace) -> int:
    """Render one image with one preset."""
    try:
        spec = _load_spec(args.preset)
        _render_file(spec, Path(args.input), Path(args.output), args.max_side)
    except InputError as exc:
        _note(str(exc))
        _emit(args, False, [], [str(exc)])
        return EXIT_INPUT
    except RenderError as exc:
        _note(str(exc))
        _emit(args, False, [], [str(exc)])
        return EXIT_RENDER
    _note(f"wrote {args.output}")
    _emit(args, True, [str(args.output)], [])
    return EXIT_OK


def _batch_inputs(source: Path, extensions: set[str]) -> list[Path]:
    """Return the input files of a directory, sorted, filtered by extension."""
    if not source.is_dir():
        raise InputError(f"input directory not found: {source}")
    return sorted(
        path
        for path in source.iterdir()
        if path.is_file() and path.suffix.lower().lstrip(".") in extensions
    )


def _cmd_batch(args: argparse.Namespace) -> int:
    """Render every image of a directory with one preset."""
    try:
        spec = _load_spec(args.preset)
        extensions = {part.strip().lower().lstrip(".") for part in args.ext.split(",") if part}
        inputs = _batch_inputs(Path(args.input_dir), extensions)
    except InputError as exc:
        _note(str(exc))
        _emit(args, False, [], [str(exc)])
        return EXIT_INPUT
    target_dir = Path(args.output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    payloads: list[tuple[PipelineSpec, str, str, int | None]] = []
    files: list[str] = []
    errors: list[str] = []
    for source in inputs:
        target = target_dir / (source.stem + OUTPUT_SUFFIX)
        if not args.force and target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            _note(f"skip {source.name} (up to date)")
            files.append(str(target))
            continue
        payloads.append((spec, str(source), str(target), args.max_side))
    if args.jobs > 1 and len(payloads) > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(_render_job, payloads))
    else:
        results = [_render_job(payload) for payload in payloads]
    for target, error in results:
        if error is None:
            _note(f"wrote {target}")
            files.append(target)
        else:
            _note(error)
            errors.append(error)
    _emit(args, not errors, files, errors)
    if any("input not found" in error or "cannot read image" in error for error in errors):
        return EXIT_INPUT
    return EXIT_RENDER if errors else EXIT_OK


def _cmd_info(args: argparse.Namespace) -> int:
    """Print what a preset renders with, without rendering it."""
    try:
        spec = _load_spec(args.preset)
    except InputError as exc:
        _note(str(exc))
        _emit(args, False, [], [str(exc)])
        return EXIT_INPUT
    description = _describe(spec, Path(args.preset))
    if args.json:
        print(json.dumps(description, indent=2))
    else:
        print(_format_description(description))
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser with the three subcommands of §17."""
    parser = _Parser(prog="lattice_dither.cli", description="Lattice Dither command line.")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    render_parser = subparsers.add_parser("render", help="render one image with one preset")
    render_parser.add_argument("--preset", required=True, help="preset JSON file")
    render_parser.add_argument("--in", dest="input", required=True, help="input image")
    render_parser.add_argument("--out", dest="output", required=True, help="output PNG")
    render_parser.add_argument("--max-side", type=int, default=None, help="downscale proxy size")
    render_parser.add_argument("--json", action="store_true", help="print a JSON summary")
    render_parser.set_defaults(handler=_cmd_render)

    batch_parser = subparsers.add_parser("batch", help="render a directory with one preset")
    batch_parser.add_argument("--preset", required=True, help="preset JSON file")
    batch_parser.add_argument("--in-dir", dest="input_dir", required=True, help="input directory")
    batch_parser.add_argument(
        "--out-dir", dest="output_dir", required=True, help="output directory"
    )
    batch_parser.add_argument("--jobs", type=int, default=1, help="worker processes")
    batch_parser.add_argument("--ext", default=DEFAULT_EXTENSIONS, help="input extensions")
    batch_parser.add_argument("--force", action="store_true", help="rewrite up-to-date outputs")
    batch_parser.add_argument("--max-side", type=int, default=None, help="downscale proxy size")
    batch_parser.add_argument("--json", action="store_true", help="print a JSON summary")
    batch_parser.set_defaults(handler=_cmd_batch)

    info_parser = subparsers.add_parser("info", help="describe a preset without rendering")
    info_parser.add_argument("--preset", required=True, help="preset JSON file")
    info_parser.add_argument("--json", action="store_true", help="print a JSON description")
    info_parser.set_defaults(handler=_cmd_info)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code, never letting a traceback escape."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or EXIT_OK)
    try:
        return int(args.handler(args))
    except InputError as exc:
        _note(str(exc))
        return EXIT_INPUT
    except RenderError as exc:
        _note(str(exc))
        return EXIT_RENDER
    except Exception as exc:  # noqa: BLE001 - §17 forbids a traceback on stderr
        _note(f"{args.command} failed: {exc}")
        return EXIT_RENDER


if __name__ == "__main__":
    sys.exit(main())
