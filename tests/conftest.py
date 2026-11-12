"""Shared fixtures for the Lattice Dither test suite."""

from __future__ import annotations

import numpy as np
import pytest

from lattice_dither.core.types import Image, Palette


@pytest.fixture
def rng() -> np.random.Generator:
    """Deterministic generator shared by randomized tests."""
    return np.random.default_rng(0)


@pytest.fixture
def gradient() -> Image:
    """64x64 horizontal grey ramp from black to white."""
    ramp = np.linspace(0.0, 1.0, 64, dtype=np.float32)
    img = np.repeat(ramp[None, :, None], 64, axis=0)
    return np.ascontiguousarray(np.repeat(img, 3, axis=2))


@pytest.fixture
def photo_like(rng: np.random.Generator) -> Image:
    """96x64 smooth pseudo-photographic image."""
    img = rng.random((96, 64, 3), dtype=np.float32)
    for _ in range(3):
        img = (img + np.roll(img, 1, axis=0) + np.roll(img, 1, axis=1)) / 3.0
    return np.ascontiguousarray(np.clip(img, 0.0, 1.0).astype(np.float32))


@pytest.fixture
def pal_bw() -> Palette:
    """Black and white palette."""
    return np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)


@pytest.fixture
def pal_4() -> Palette:
    """Black, red, green and white palette."""
    return np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 1.0]],
        dtype=np.float32,
    )
