"""The effect stack of Lattice Glitch: ordered slots with parameters and a mask id.

The stack is the application's view of ``PipelineSpec.post_effects``: one
:class:`EffectSlot` per configured effect, in render order. Mask assignments travel
with the slots (the v3 preset carries them as ``effects[].mask``), while the spec
itself keeps only what ``lattice_core`` understands. No Qt here: the CLI path uses
this module too.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from lattice_core.pipeline import EffectInstance
from lattice_core.registry import get_effect


@dataclass
class EffectSlot:
    """One configured effect of the stack: its instance and the mask id it wears."""

    instance: EffectInstance
    mask_id: str | None = None


class EffectStack:
    """Ordered effect slots with add, remove, reorder, enable, params and mask edits."""

    def __init__(self, slots: list[EffectSlot] | None = None) -> None:
        """Adopt slots (deep-copied) as the stack, empty when none are given."""
        self._slots: list[EffectSlot] = copy.deepcopy(slots) if slots else []

    def slots(self) -> list[EffectSlot]:
        """Return a deep copy of the slots, in render order."""
        return copy.deepcopy(self._slots)

    def __len__(self) -> int:
        """Return the number of slots, enabled or not."""
        return len(self._slots)

    def instances(self) -> list[EffectInstance]:
        """Return the EffectInstance list a PipelineSpec carries as post_effects."""
        return [copy.deepcopy(slot.instance) for slot in self._slots]

    def mask_ids(self) -> tuple[str | None, ...]:
        """Return the mask id of every slot, aligned with instances()."""
        return tuple(slot.mask_id for slot in self._slots)

    def effect_ids(self) -> list[str]:
        """Return the effect id of every slot, in render order."""
        return [slot.instance.effect_id for slot in self._slots]

    def add(self, effect_id: str, params: dict | None = None,
            mask_id: str | None = None) -> int:
        """Append one registered effect and return its position; unknown ids raise."""
        get_effect(effect_id)  # raises KeyError before anything is mutated
        self._slots.append(EffectSlot(EffectInstance(effect_id, dict(params or {})), mask_id))
        return len(self._slots) - 1

    def remove(self, index: int) -> None:
        """Drop the slot at index; an out-of-range index raises IndexError."""
        del self._slots[index]

    def move(self, index: int, new_index: int) -> None:
        """Move the slot at index to new_index, shifting the others; bounds raise."""
        if not (0 <= index < len(self._slots) and 0 <= new_index < len(self._slots)):
            raise IndexError(f"stack move out of range: {index} -> {new_index}")
        slot = self._slots.pop(index)
        self._slots.insert(new_index, slot)

    def set_enabled(self, index: int, enabled: bool) -> None:
        """Enable or disable the slot at index without moving it."""
        self._slots[index].instance.enabled = bool(enabled)

    def set_params(self, index: int, params: dict) -> None:
        """Replace the parameters of the slot at index (validated by the renderer)."""
        self._slots[index].instance.params = dict(params)

    def set_mask(self, index: int, mask_id: str | None) -> None:
        """Assign a mask id to the slot at index, or None for a global effect."""
        self._slots[index].mask_id = mask_id

    def params_of(self, index: int) -> dict:
        """Return a copy of the parameters of the slot at index."""
        return dict(self._slots[index].instance.params)

    def to_entries(self) -> list[dict]:
        """Return the v3 preset effect entries of the stack, stage post, mask kept."""
        entries: list[dict] = []
        for slot in self._slots:
            entries.append({
                "name": slot.instance.effect_id,
                "params": dict(slot.instance.params),
                "enabled": bool(slot.instance.enabled),
                "mask": slot.mask_id,
                "stage": "post",
            })
        return entries

    @classmethod
    def from_entries(cls, entries: list[dict]) -> EffectStack:
        """Build the stack from the post-stage entries of a v3 preset, in order."""
        slots: list[EffectSlot] = []
        for entry in entries:
            if entry.get("stage", "post") == "pre":
                continue
            instance = EffectInstance(
                effect_id=str(entry.get("name", "")),
                params=dict(entry.get("params", {})),
                enabled=bool(entry.get("enabled", True)),
            )
            mask = entry.get("mask")
            slots.append(EffectSlot(instance, None if mask is None else str(mask)))
        return cls(slots)


__all__ = ["EffectSlot", "EffectStack"]
