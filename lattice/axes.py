"""The animation axes, in one place.

This module exists so the command line and the export dialog can advertise the axes
without importing :mod:`lattice.animation`. Rendering one still image must not pull
that module in (tests/test_glitch_app.py::test_cli_render_verbs_and_no_qt pins it), and a
duplicated tuple is how ``param`` went missing from the CLI for a while: the core gained
the axis, the two hard-coded lists did not, and only the tests could reach it.
"""

from __future__ import annotations

AXES: tuple[str, ...] = ("seed", "offset", "iterations", "param")
