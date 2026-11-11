"""Core type aliases and parameter specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

Image = np.ndarray
Indices = np.ndarray
Palette = np.ndarray
RGB8 = np.ndarray


@dataclass(frozen=True)
class ParamSpec:
    """Description of one user-facing parameter of an algorithm or an effect."""

    id: str
    label: str
    kind: Literal["float", "int", "bool", "choice"]
    default: float | int | bool | str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
