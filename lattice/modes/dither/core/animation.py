"""Animation: render a sequence of frames with a stable palette (CONTRACT §21).

``stable=True`` pins the palette to the one resolved on the first frame, so colours do not
flicker across the sequence. The other two properties §21 lists for the stable mode are
structural in 1.1 and hold in both modes: ordered matrices are indexed by pixel
coordinates, so they are anchored to the canvas, and every frame is rendered from scratch,
so no error is carried from frame n to frame n+1.

``stable=False`` renders each frame as an independent image, which re-resolves the palette
per frame. The seed is the spec's, not the frame's, so two identical frames still render
identically in either mode.
"""

from __future__ import annotations

from lattice.pipeline import (
    PipelineSpec,
    prepare_image,
    render_with_palette,
    resolve_palette,
)
from lattice.types import RGB8, Image


def render_sequence(
    frames: list[Image], spec: PipelineSpec, *, stable: bool = True
) -> list[RGB8]:
    """Render frames through spec, resolving the palette once when stable."""
    if not frames:
        return []
    if stable:
        palette = resolve_palette(spec.palette, prepare_image(frames[0], spec))
        return [render_with_palette(frame, spec, palette) for frame in frames]
    return [
        render_with_palette(frame, spec, resolve_palette(spec.palette, prepare_image(frame, spec)))
        for frame in frames
    ]
