"""Command line of Lattice Glitch: the four verbs of §8 and their exit codes.

``render`` and ``batch`` go through :mod:`lattice_glitch.document`, the module the GUI
export uses, so their PNG bytes are identical by construction (G9). ``presets`` reads the
v3 preset tiers and ``bridge`` talks to PhotoCraft or DesignCraft; an absent host is a
normal answer reported as text, not a traceback (§7). No verb needs a display and this
module never imports Qt: it only imports the core, whose base install has no PySide6.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
from lattice_core import color
from lattice_core.bridge import HOSTS, BridgeError
from lattice_core.preset import Preset
from lattice_glitch import presets as preset_tools
from lattice_glitch.document import (
    FORMATS,
    DocumentError,
    Export,
    format_of,
    load_image,
    render_preset,
    target_path,
    write_render,
)
from lattice_glitch.hosts import discover as discover_host

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RENDER = 2
EXIT_BRIDGE = 3
DEFAULT_EXTENSIONS = "png,jpg,jpeg,bmp,tif,tiff,webp"
PROG = "lattice-glitch"


class UsageError(Exception):
    """A command line the application cannot honour: a missing or unreadable preset."""


class _Parser(argparse.ArgumentParser):
    """Argument parser reporting usage errors with exit code 1, not argparse's 2."""

    _argv: list[str] | None = None

    def error(self, message: str) -> NoReturn:
        """Print the usage line and exit with the §8 usage code.

        With ``--json`` on the command line the machine result is still printed on
        stdout, so a machine caller never receives an empty answer (§8).
        """
        self.print_usage(sys.stderr)
        if self._argv is not None and "--json" in self._argv:
            print(json.dumps({"ok": False, "errors": [message]},
                             indent=2, ensure_ascii=False, sort_keys=True))
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _note(message: str) -> None:
    """Print one human-readable line on stderr, leaving stdout to the machine result."""
    print(message, file=sys.stderr)


def _emit(args: argparse.Namespace, payload: dict) -> None:
    """Print payload as JSON on stdout when --json is set; stdout stays empty otherwise."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _preset(preset: str) -> Preset:
    """Load a preset file in this app's context, mapping any failure to a usage error."""
    path = Path(preset)
    if not path.is_file():
        raise UsageError(f"preset not found: {path}")
    try:
        return preset_tools.read_preset(path)
    except (OSError, ValueError, KeyError) as exc:
        raise UsageError(f"cannot read preset {path}: {exc}") from None


def _failure(args: argparse.Namespace, message: str, code: int) -> int:
    """Report one failure on stderr and in JSON and return the exit code of its class."""
    _note(message)
    _emit(args, {"ok": False, "errors": [message]})
    return code


def _export_payload(export: Export) -> dict:
    """Return the machine-readable description of one written file."""
    return {"ok": True, "file": str(export.path), "format": export.fmt,
            "bytes": export.size, "warnings": list(export.warnings), "errors": []}


def _cmd_render(args: argparse.Namespace) -> int:
    """Render one image with one preset into one file, in the format it names."""
    try:
        preset = _preset(args.preset)
        image = load_image(Path(args.source))
        fmt = args.format or format_of(args.output)
        export = write_render(image, preset, args.output, fmt)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    for warning in export.warnings:
        _note(f"warning: {warning}")
    _note(f"wrote {export.path} ({export.fmt}, {export.size} bytes)")
    _emit(args, _export_payload(export))
    return EXIT_OK


def _extensions(text: str) -> set[str]:
    """Return the lower-case extensions listed in a comma-separated string."""
    return {part.strip().lower().lstrip(".") for part in text.split(",") if part.strip()}


def _batch_inputs(source: Path, extensions: set[str], recursive: bool) -> list[Path]:
    """Return the image files of a directory, sorted, filtered by extension."""
    if not source.is_dir():
        raise UsageError(f"input directory not found: {source}")
    found = source.rglob("*") if recursive else source.iterdir()
    return sorted(
        path for path in found
        if path.is_file() and path.suffix.lower().lstrip(".") in extensions
    )


def _destination(target_dir: Path, item: Path, source: Path, fmt: str, recursive: bool) -> Path:
    """Return where one batch item is written, mirroring the tree when recursive."""
    relative = item.relative_to(source) if recursive else Path(item.name)
    suffix = target_path(relative.name, fmt).suffix
    return target_dir / relative.with_name(relative.stem + suffix)


def _cmd_batch(args: argparse.Namespace) -> int:
    """Render every image of a directory with one preset, keeping the file names."""
    try:
        preset = _preset(args.preset)
        source = Path(args.source)
        files = _batch_inputs(source, _extensions(args.ext), args.recursive)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    fmt = args.format or "png"
    written: list[str] = []
    errors: list[str] = []
    for item in files:
        destination = _destination(Path(args.output), item, source, fmt, args.recursive)
        try:
            export = write_render(load_image(item), preset, destination, fmt)
        except DocumentError as exc:
            _note(f"{item}: {exc}")
            errors.append(f"{item}: {exc}")
            continue
        _note(f"wrote {export.path}")
        written.append(str(export.path))
    _emit(args, {"ok": not errors, "files": written, "errors": errors})
    return EXIT_OK if not errors else EXIT_RENDER


def _cmd_presets_list(args: argparse.Namespace) -> int:
    """List the presets of the shipped tier and of the user tier."""
    directories = [Path(entry) for entry in args.directory] or None
    entries = preset_tools.available(directories)
    payload = {"presets": [
        {"name": entry.name, "path": str(entry.path), "read_only": entry.read_only}
        for entry in entries
    ]}
    _emit(args, payload)
    if not args.json:
        for entry in entries:
            tier = "shipped" if entry.read_only else "user"
            print(f"{entry.name}\t{tier}\t{entry.path}")
    return EXIT_OK


def _cmd_presets_show(args: argparse.Namespace) -> int:
    """Describe one preset: its seed, its effect stack, its masks and its pipeline."""
    try:
        preset = preset_tools.read_preset(Path(args.name))
    except (OSError, ValueError, KeyError) as exc:
        return _failure(args, f"cannot read preset {args.name}: {exc}", EXIT_USAGE)
    description = preset_tools.describe(preset)
    _emit(args, description)
    if not args.json:
        print(json.dumps(description, indent=2, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


def _cmd_presets_validate(args: argparse.Namespace) -> int:
    """Validate one preset file, or every preset of the tiers when no path is given."""
    reports = [preset_tools.validate(Path(args.path))] if args.path \
        else preset_tools.validate_all()
    payload = {
        "ok": all(report.ok for report in reports),
        "presets": [
            {"name": report.name, "ok": report.ok, "renderer": report.renderer,
             "errors": report.errors, "warnings": report.warnings}
            for report in reports
        ],
    }
    _emit(args, payload)
    if not args.json:
        for report in reports:
            print(f"{report.name}\t{'ok' if report.ok else 'invalid'}\t{report.renderer}")
            for prose in report.errors + report.warnings:
                print(f"  {prose}")
    return EXIT_OK if payload["ok"] else EXIT_USAGE


def host_report(hosts: tuple[str, ...] | list[str]) -> list[dict]:
    """Probe every host and return one {host, connected} record per host."""
    report: list[dict] = []
    for host in hosts:
        client = discover_host(host)
        if client is not None:
            client.disconnect()
        report.append({"host": host, "connected": client is not None})
    return report


def _cmd_bridge_status(args: argparse.Namespace) -> int:
    """Report the reachability of the ArtCraft hosts, with no host running being normal."""
    hosts: list[str] = [args.host] if args.host else list(HOSTS)
    report = host_report(hosts)
    _emit(args, {"ok": True, "hosts": report})
    if not args.json:
        for entry in report:
            print(f"{entry['host']}: {'connected' if entry['connected'] else 'not running'}")
    return EXIT_OK


def _cmd_bridge_pull(args: argparse.Namespace) -> int:
    """Render the active document of a host with a preset and write the result."""
    client = discover_host(args.host)
    if client is None:
        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
    try:
        image = color.to_float(client.render_document())
        export = write_render(image, _preset(args.preset), args.output,
                              args.format or format_of(args.output))
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    except (BridgeError, OSError) as exc:
        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
    finally:
        client.disconnect()
    _note(f"wrote {export.path} ({export.size} bytes)")
    _emit(args, _export_payload(export))
    return EXIT_OK


def _cmd_bridge_push(args: argparse.Namespace) -> int:
    """Render one image with a preset and place it in a host as a layer."""
    client = discover_host(args.host)
    if client is None:
        return _failure(args, f"{args.host}: host not running", EXIT_BRIDGE)
    try:
        rgb8 = render_preset(load_image(Path(args.source)), _preset(args.preset))
        object_id = client.place_as_layer(color.to_pil(rgb8), args.name)
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    except (BridgeError, OSError) as exc:
        return _failure(args, f"{args.host}: {exc}", EXIT_BRIDGE)
    finally:
        client.disconnect()
    _note(f"placed object {object_id} in {args.host}")
    _emit(args, {"ok": True, "host": args.host, "object_id": object_id, "errors": []})
    return EXIT_OK


def _add_render_options(parser: argparse.ArgumentParser, *, output_help: str) -> None:
    """Add the preset, the output and the JSON flag shared by the render verbs."""
    parser.add_argument("--preset", required=True, help="preset JSON file")
    parser.add_argument("--out", dest="output", required=True, help=output_help)
    parser.add_argument("--format", choices=FORMATS, default=None,
                        help="png (default: from --out)")
    parser.add_argument("--json", action="store_true", help="print a JSON result")


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser carrying the four verbs of §8."""
    parser = _Parser(prog=PROG, description="Lattice Glitch command line.")
    verbs = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    render = verbs.add_parser("render", help="render one image with one preset")
    _add_render_options(render, output_help="output file")
    render.add_argument("--in", dest="source", required=True, help="input image")
    render.set_defaults(handler=_cmd_render)

    batch = verbs.add_parser("batch", help="render a directory with one preset")
    _add_render_options(batch, output_help="output directory")
    batch.add_argument("--in", dest="source", required=True, help="input directory")
    batch.add_argument("--recursive", action="store_true", help="walk subdirectories")
    batch.add_argument("--ext", default=DEFAULT_EXTENSIONS, help="input extensions")
    batch.set_defaults(handler=_cmd_batch)

    presets = verbs.add_parser("presets", help="list, show and validate presets")
    preset_verbs = presets.add_subparsers(dest="preset_command", required=True,
                                          parser_class=_Parser)
    listing = preset_verbs.add_parser("list", help="list the presets of both tiers")
    listing.add_argument("--dir", dest="directory", action="append", default=[],
                         help="search directory, repeatable")
    listing.add_argument("--json", action="store_true", help="print a JSON result")
    listing.set_defaults(handler=_cmd_presets_list)
    show = preset_verbs.add_parser("show", help="describe one preset")
    show.add_argument("name", help="preset file to describe")
    show.add_argument("--json", action="store_true", help="print a JSON result")
    show.set_defaults(handler=_cmd_presets_show)
    check = preset_verbs.add_parser("validate", help="validate one preset or the tiers")
    check.add_argument("path", nargs="?", default=None, help="preset file to validate")
    check.add_argument("--json", action="store_true", help="print a JSON result")
    check.set_defaults(handler=_cmd_presets_validate)

    bridge = verbs.add_parser("bridge", help="talk to PhotoCraft or DesignCraft")
    bridge_verbs = bridge.add_subparsers(dest="bridge_command", required=True,
                                         parser_class=_Parser)
    status = bridge_verbs.add_parser("status", help="report the host state")
    status.add_argument("host", nargs="?", default=None, choices=HOSTS,
                        help="host to probe (default: both)")
    status.add_argument("--json", action="store_true", help="print a JSON result")
    status.set_defaults(handler=_cmd_bridge_status)
    pull = bridge_verbs.add_parser("pull", help="render the host document into a file")
    _add_render_options(pull, output_help="output file")
    pull.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
    pull.set_defaults(handler=_cmd_bridge_pull)
    push = bridge_verbs.add_parser("push", help="place a render in the host as a layer")
    push.add_argument("--host", dest="host", default="photocraft", choices=HOSTS)
    push.add_argument("--preset", required=True, help="preset JSON file")
    push.add_argument("--in", dest="source", required=True, help="input image")
    push.add_argument("--name", default="Lattice Glitch", help="layer or object name")
    push.add_argument("--json", action="store_true", help="print a JSON result")
    push.set_defaults(handler=_cmd_bridge_push)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code; no traceback ever escapes."""
    _Parser._argv = list(argv) if argv is not None else sys.argv[1:]
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or EXIT_OK)
    try:
        return int(args.handler(args))
    except UsageError as exc:
        return _failure(args, str(exc), EXIT_USAGE)
    except DocumentError as exc:
        return _failure(args, str(exc), EXIT_RENDER)
    except (BridgeError, OSError) as exc:
        return _failure(args, f"{args.command} failed: {exc}", EXIT_BRIDGE)
    except Exception as exc:  # noqa: BLE001 - §8 forbids a traceback on stderr
        return _failure(args, f"{args.command} failed: {exc}", EXIT_RENDER)


if __name__ == "__main__":
    sys.exit(main())
