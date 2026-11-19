"""Command line of Lattice Glyph: the eleven shared verbs.

The eleven verbs every shell has — ``render``, ``batch``, ``presets``, ``bridge`` — live in
``lattice_core.cli_shared``, together with their flags, JSON payloads and exit codes. Glyph
adds none: it does not render animation loops, which is the one verb Glitch has and it does
not. No verb needs a display and this module never imports Qt.
"""

from __future__ import annotations

import lattice_core.effects  # noqa: F401  (importing the package registers every effect)
import lattice_glyph
from lattice_core.bridge_hosts import discover as discover_host
from lattice_core.cli_shared import (
    EXIT_BRIDGE,
    EXIT_OK,
    EXIT_RENDER,
    EXIT_USAGE,
    CliBackend,
    install,
)
from lattice_core.cli_shared import _default_host_report as host_report
from lattice_core.cli_shared import (
    main as _main,
)
from lattice_glyph import presets as preset_tools
from lattice_glyph.document import (
    FORMATS as document_formats,
)
from lattice_glyph.document import (
    DocumentError,
    format_of,
    load_image,
    render_rgb8,
    target_path,
    write_render,
)

PROG = "lattice-glyph"
FORMATS = document_formats
def install_backend() -> None:
    """Bind Glitch to the shared command line."""
    install(CliBackend(
        prog=PROG,
        version=lattice_glyph.__version__,
        read_preset=preset_tools.read_preset,
        # Glyph renders a spec, not a preset: the two shells disagree on that step, which is
        # exactly why the backend names it instead of the shared module guessing.
        render_preset=lambda image, preset: render_rgb8(
            image, preset_tools.spec_of(preset)),
        # Glyph's writer takes a spec; Glitch's takes the preset. Converting here keeps the
        # shared verb free of the difference, which is the whole point of the backend.
        write_render=lambda image, preset, path, fmt: write_render(
            image, preset_tools.spec_of(preset), path, fmt),
        load_image=load_image,
        format_of=format_of,
        target_path=target_path,
        document_error=DocumentError,
        preset_tools=preset_tools,
        discover_module=__import__('sys').modules[__name__],
        formats=FORMATS,
    ))


def main(argv: list[str] | None = None) -> int:
    """Run the command line with Glitch's backend installed."""
    install_backend()
    return _main(argv)


__all__ = [
    "EXIT_BRIDGE", "EXIT_OK", "EXIT_RENDER", "EXIT_USAGE", "FORMATS",
    "discover_host", "host_report", "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
