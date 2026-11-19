"""Command line of Lattice Glitch: the shared verbs plus ``loop``.

The eleven verbs every shell has — ``render``, ``batch``, ``presets``, ``bridge`` — live in
``lattice_core.cli_shared``, together with their flags, JSON payloads and exit codes. Glitch
is the only shell that renders animation loops, so ``loop`` is added from here.

No verb needs a display and neither module imports Qt: ``lattice_core.animation`` is imported
lazily inside ``loop`` so the still-image verbs never pay for it.
"""

from __future__ import annotations

import argparse
import importlib
from functools import partial
from pathlib import Path

import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
import lattice_glitch
from lattice_core import axes
from lattice_core.bridge_hosts import discover as discover_host
from lattice_core.cli_shared import (
    EXIT_BRIDGE,
    EXIT_OK,
    EXIT_RENDER,
    EXIT_USAGE,
    CliBackend,
    UsageError,
    _emit,
    _failure,
    _note,
    install,
)
from lattice_core.cli_shared import _default_host_report as host_report
from lattice_core.cli_shared import (
    main as _main,
)
from lattice_core.preset import to_pipeline_spec
from lattice_glitch import presets as preset_tools
from lattice_glitch.document import (
    DocumentError,
    context_of_preset,
    format_of,
    load_image,
    render_preset,
    render_rgb8,
    target_path,
    write_render,
)

PROG = "lattice-glitch"
FORMATS = ("png",)
LOOP_AXES = axes.AXES  # single source of truth, and it imports without Qt or the renderer
LOOP_WRITERS = {"gif": "gif", "png": "apng", "apng": "apng"}


def _cmd_loop(args: argparse.Namespace) -> int:
    """Render an N-image loop on the glitch path and write it as GIF or APNG (L25)."""
    try:
        path = Path(args.preset)
        if not path.is_file():
            raise UsageError(f"preset not found: {path}")
        preset = preset_tools.read_preset(path)
        image = load_image(Path(args.source))
        suffix = Path(args.output).suffix.lower().lstrip(".")
        if suffix not in LOOP_WRITERS:
            raise UsageError(f"loop output must end in .gif, .png or .apng: {args.output!r}")
        if args.frames < 1:
            raise UsageError(f"--frames must be >= 1, got {args.frames}")
        fmt = LOOP_WRITERS[suffix]
        animation = importlib.import_module("lattice_core.animation")
        if args.axis == "param" and not args.param:
            raise UsageError("--axis param needs --param <effect>.<key>")
        frames = animation.render_loop(
            image, to_pipeline_spec(preset), count=args.frames, axis=args.axis,
            param=args.param, from_value=args.from_value, to_value=args.to_value,
            curve=args.curve, reseed=args.reseed,
            render_fn=partial(render_rgb8, context=context_of_preset(preset)))
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = animation.export_gif if fmt == "gif" else animation.export_apng
        writer(frames, target)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except (DocumentError, OSError, ValueError) as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    size = target.stat().st_size
    _note(f"wrote {target} ({fmt}, {args.frames} frames, {size} bytes)")
    _emit(args, {"ok": True, "file": str(target), "format": fmt, "frames": args.frames,
                 "axis": args.axis, "bytes": size, "errors": []})
    return EXIT_OK


def _add_loop_verb(verbs: argparse._SubParsersAction) -> None:
    """Add the loop verb: an N-image GIF or APNG rendered on the glitch path."""
    loop = verbs.add_parser("loop", help="render an N-image loop as GIF or APNG")
    loop.add_argument("--preset", required=True, help="preset JSON file")
    loop.add_argument("--in", dest="source", required=True, help="input image")
    loop.add_argument("--out", dest="output", required=True, help="output .gif, .png or .apng")
    loop.add_argument("--frames", type=int, required=True, help="number of frames (>= 1)")
    loop.add_argument("--axis", default="seed", choices=LOOP_AXES, help="the axis that varies")
    loop.add_argument("--param", dest="param",
                      help="with --axis param: the effect parameter, '<effect>.<key>'")
    loop.add_argument("--from", dest="from_value", type=float, default=0.0,
                      help="with --axis param: the A value")
    loop.add_argument("--to", dest="to_value", type=float, default=1.0,
                      help="with --axis param: the B value")
    loop.add_argument("--curve", default="sin", choices=("sin", "linear"),
                      help="with --axis param: the A->B->A curve")
    loop.add_argument("--reseed", type=int, default=0, metavar="STEP",
                      help="with --axis param: also step the seed every STEP frames, so the "
                           "random modules draw a new stream instead of repeating the same "
                           "structure (0 = off, the historical behaviour)")
    loop.add_argument("--json", action="store_true", help="print a JSON result")
    loop.set_defaults(handler=_cmd_loop)


def install_backend() -> None:
    """Bind Glitch to the shared command line."""
    install(CliBackend(
        prog=PROG,
        version=lattice_glitch.__version__,
        read_preset=preset_tools.read_preset,
        render_preset=render_preset,
        write_render=write_render,
        load_image=load_image,
        format_of=format_of,
        target_path=target_path,
        document_error=DocumentError,
        preset_tools=preset_tools,
        discover_module=__import__('sys').modules[__name__],
        formats=FORMATS,
        extra_verbs=(_add_loop_verb,),
    ))


def main(argv: list[str] | None = None) -> int:
    """Run the command line with Glitch's backend installed."""
    install_backend()
    return _main(argv)


__all__ = [
    "EXIT_BRIDGE", "EXIT_OK", "EXIT_RENDER", "EXIT_USAGE", "FORMATS", "LOOP_AXES",
    "discover_host", "host_report", "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
