"""Greyscale effect masks: PNG round-trip, path/base64 references and composition (§18)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice.types import Image

MAX_EMBED_BYTES = 64 * 1024
"""Threshold on the raw 8-bit PNG size (not its base64 text, which is ~4/3 larger).

A mask whose PNG is at least this size must be referenced by path; smaller masks are
embedded as base64 data in the preset `masks` entry (§6 masks / §18).
"""


@dataclass(frozen=True)
class MaskRef:
    """Serialisable reference to one greyscale mask: a path or embedded base64 data.

    ``data`` holds the base64 PNG payload when the mask's PNG is smaller than
    ``MAX_EMBED_BYTES``; ``path`` points at an external PNG for larger masks. Exactly
    one of the two is set, mirroring the §6 preset `masks` entry (see also §18).
    The path is stored verbatim, so a relative one resolves against the process
    working directory, not against the preset's own folder.
    """

    id: str
    width: int
    height: int
    path: str | None = None
    data: str | None = None

    @classmethod
    def from_mask(cls, mask: Image, ref_id: str, *, path: str | None = None) -> MaskRef:
        """Build a reference for mask, embedding when possible and requiring a path otherwise."""
        plane = _plane(mask)
        payload = to_png(plane)
        if len(payload) < MAX_EMBED_BYTES:
            data = base64.b64encode(payload).decode("ascii")
            return cls(ref_id, plane.shape[1], plane.shape[0], data=data)
        if path is None:
            raise ValueError(
                f"mask PNG is {len(payload)} bytes, at or over the {MAX_EMBED_BYTES} byte "
                "(64 KiB) embed limit; pass path= to reference it on disk"
            )
        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))

    @classmethod
    def from_path(cls, path: str | Path, ref_id: str) -> MaskRef:
        """Reference an existing PNG mask by path, decoding it once to read its dimensions."""
        plane = import_png(path)
        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))

    @property
    def embedded(self) -> bool:
        """True when the mask is embedded as base64 data rather than referenced by path."""
        return self.data is not None

    def to_dict(self) -> dict[str, str | int | None]:
        """Return the JSON dict of the reference; exactly one of path/data is present."""
        item: dict[str, str | int | None] = {
            "id": self.id, "width": self.width, "height": self.height,
        }
        item["data" if self.embedded else "path"] = self.data if self.embedded else self.path
        return item

    @classmethod
    def from_dict(cls, item: dict) -> MaskRef:
        """Rebuild a reference from its JSON dict, rejecting an entry with both keys."""
        ref = cls(str(item["id"]), _int(item, "width"), _int(item, "height"),
                  path=_str_or_none(item.get("path")),
                  data=_str_or_none(item.get("data")))
        if not ref.path and not ref.data:
            raise ValueError("mask reference needs a path or embedded data")
        if ref.path and ref.data:
            raise ValueError("mask reference cannot carry both a path and embedded data")
        return ref


def _int(item: dict, key: str) -> int:
    value = item[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"mask reference key {key!r} must be an integer")
    return value


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _plane(mask: Image) -> np.ndarray:
    """Return the (H, W) float32 mask plane, accepting an (H, W, 1) channel image."""
    data = np.asarray(mask, dtype=np.float32)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2:
        raise ValueError(f"mask must be a greyscale plane, got shape {mask.shape}")
    return data


def to_png(mask: Image) -> bytes:
    """Encode a greyscale mask as 8-bit PNG bytes with exact rounding."""
    plane = np.clip(_plane(mask), 0.0, 1.0)
    buffer = io.BytesIO()
    PILImage.fromarray((plane * 255.0).round().astype(np.uint8), mode="L").save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def _decode_grey(pil: PILImage.Image) -> np.ndarray:
    """Return 8-bit grey values from a decoded PNG, handling 16-bit and alpha modes.

    ``I;16``/``I`` samples are divided by 65535 rather than saturated through
    ``convert("L")``; RGBA is composited over white first, so an imported painted
    mask from another tool keeps its tones.
    """
    if pil.mode in ("RGBA", "LA", "PA"):
        flat = pil.convert("RGBA")
        backdrop = PILImage.new("RGBA", flat.size, (255, 255, 255, 255))
        return np.asarray(PILImage.alpha_composite(backdrop, flat).convert("L"))
    if pil.mode in ("I;16", "I;16B", "I;16L", "I"):
        wide = np.clip(np.asarray(pil, dtype=np.float32), 0.0, 65535.0)
        return np.round(wide / 257.0)
    return np.asarray(pil.convert("L"))


def from_png(data: bytes) -> Image:
    """Decode PNG bytes (8 or 16 bit, grey or alpha) to a float32 mask in [0, 1]."""
    with PILImage.open(io.BytesIO(data)) as pil:
        pil.load()
        values = _decode_grey(pil)
    return np.ascontiguousarray(np.clip(values / 255.0, 0.0, 1.0), dtype=np.float32)


def from_base64(text: str) -> Image:
    """Decode a base64 PNG payload back to a float32 greyscale mask."""
    return from_png(base64.b64decode(text))


def export_png(mask: Image, path: str | Path) -> Path:
    """Write a mask as an 8-bit greyscale PNG, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(to_png(mask))
    return target


def import_png(path: str | Path) -> Image:
    """Read a greyscale PNG mask from disk into [0, 1]."""
    return from_png(Path(path).read_bytes())


def load_ref(ref: MaskRef | dict) -> Image:
    """Resolve a MaskRef (or its dict) into the greyscale mask it references."""
    item = ref.to_dict() if isinstance(ref, MaskRef) else dict(ref)
    parsed = MaskRef.from_dict(item)
    if parsed.data is not None:
        return from_base64(parsed.data)
    if parsed.path is None:
        raise ValueError("mask reference carries no data or path")
    return import_png(parsed.path)


def resolve_masks(section: dict[str, object] | None) -> dict[str, Image]:
    """Resolve the `masks` section of a v3 preset into its greyscale mask planes.

    Two entry shapes are accepted: a procedural descriptor (``{"kind": "v_flip"}``,
    kept by the preset as opaque data and not handled here) is skipped, while a
    mask reference (``{"path": ...}`` or ``{"data": ...}``, with the optional
    ``id``/``width``/``height`` fields of ``MaskRef.to_dict()``) is decoded into a
    float32 plane keyed by its section id. The input dict is never mutated, so the
    preset section survives a ``to_json`` round-trip unchanged.
    """
    planes: dict[str, Image] = {}
    for mask_id, entry in dict(section or {}).items():
        if not isinstance(entry, dict) or "kind" in entry:
            continue
        if "path" in entry and "data" in entry:
            raise ValueError(f"mask {mask_id!r} cannot carry both a path and embedded data")
        if entry.get("data") is not None:
            planes[str(mask_id)] = from_base64(str(entry["data"]))
        elif entry.get("path") is not None:
            planes[str(mask_id)] = import_png(str(entry["path"]))
    return planes


def _weights(mask: Image, shape: tuple[int, int]) -> np.ndarray:
    """Return the (H, W, 1) clip-mask weights, raising ValueError on a shape mismatch."""
    plane = np.clip(_plane(mask), 0.0, 1.0)
    if plane.shape != shape:
        raise ValueError(f"mask must be {shape}, got {plane.shape}")
    return plane[:, :, None]


def apply(source: Image, effect: Image, *, mask: Image) -> Image:
    """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.

    The mask is keyword-only and shared with the effects; a shape mismatch raises
    ValueError. A mask of all zeros returns the source unchanged for any effect,
    NaN or inf in the effect included (a zero weight never multiplies the effect).
    """
    weight = _weights(mask, source.shape[:2])
    one = np.float32(1.0)
    with np.errstate(invalid="ignore"):
        blended = (one - weight) * source + weight * effect
    out = np.where(weight == 0.0, source, blended)
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)
