"""Greyscale effect masks: PNG round-trip, path/base64 references and composition (§18)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from lattice_core.types import Image

MAX_EMBED_BYTES = 64 * 1024
"""Reference is embedded as base64 below this PNG size; larger masks must use a path."""


@dataclass(frozen=True)
class MaskRef:
    """Serialisable reference to one greyscale mask: a path or embedded base64 data.

    ``data`` holds the base64 PNG payload when the mask is small enough to embed
    (under ``MAX_EMBED_BYTES``); ``path`` points at an external PNG for larger
    masks. Exactly one of the two is set, mirroring the §16 preset `masks` entry.
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
                f"mask of {len(payload)} bytes needs a path (over {MAX_EMBED_BYTES} - 1 bytes)"
            )
        return cls(ref_id, plane.shape[1], plane.shape[0], path=str(path))

    @classmethod
    def from_path(cls, path: str | Path, ref_id: str) -> MaskRef:
        """Load the dimensions of an exported PNG mask without decoding its values."""
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


def from_png(data: bytes) -> Image:
    """Decode 8-bit PNG bytes back to a float32 greyscale mask in [0, 1]."""
    with PILImage.open(io.BytesIO(data)) as pil:
        pil = pil.convert("L")
        values = np.asarray(pil, dtype=np.float32) / np.float32(255.0)
    return np.ascontiguousarray(values, dtype=np.float32)


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
    """Read an 8-bit greyscale PNG mask from disk into [0, 1]."""
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


def _weights(mask: Image, shape: tuple[int, int]) -> np.ndarray:
    """Return the (H, W, 1) clip-mask weights, raising ValueError on a shape mismatch."""
    plane = np.clip(_plane(mask), 0.0, 1.0)
    if plane.shape != shape:
        raise ValueError(f"mask must be {shape}, got {plane.shape}")
    return plane[:, :, None]


def apply(source: Image, effect: Image, *, mask: Image) -> Image:
    """Compose a localised effect over source: 0 keeps source, 1 keeps the effect.

    The mask is keyword-only and shared with the effects; a shape mismatch raises
    ValueError. A mask of all zeros returns the source unchanged for any effect.
    """
    weight = _weights(mask, source.shape[:2])
    one = np.float32(1.0)
    out = (one - weight) * source + weight * effect
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)
