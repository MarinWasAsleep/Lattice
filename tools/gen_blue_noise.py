"""Generate the committed 64x64 blue-noise rank array with the void-and-cluster method.

Run once from the project root: ``python tools/gen_blue_noise.py``.
The result is written to ``data/blue_noise_64.npy`` and never regenerated at runtime.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

SIZE = 64
SIGMA = 1.5
SEED = 0
INITIAL_FRACTION = 0.1
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "blue_noise_64.npy"


def gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    """Return a toroidal Gaussian kernel of shape (size, size)."""
    axis = np.arange(size, dtype=np.float64)
    dist = np.minimum(axis, size - axis)
    return np.exp(-(dist[:, None] ** 2 + dist[None, :] ** 2) / (2.0 * sigma * sigma))


def convolve(pattern: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Return the toroidal convolution of pattern with kernel, via the FFT."""
    return np.real(np.fft.ifft2(np.fft.fft2(pattern) * np.fft.fft2(kernel)))


def _shifted(kernel: np.ndarray, y: int, x: int) -> np.ndarray:
    """Return kernel rolled so that its origin lands on (y, x)."""
    return np.roll(np.roll(kernel, y, axis=0), x, axis=1)


def _tightest_cluster(field: np.ndarray, pattern: np.ndarray) -> int:
    """Return the flat index of the set pixel with the highest filtered value."""
    return int(np.argmax(np.where(pattern > 0.0, field, -np.inf)))


def _largest_void(field: np.ndarray, pattern: np.ndarray) -> int:
    """Return the flat index of the unset pixel with the lowest filtered value."""
    return int(np.argmin(np.where(pattern > 0.0, np.inf, field)))


def relax(pattern: np.ndarray, field: np.ndarray, kernel: np.ndarray) -> None:
    """Move ones from the tightest cluster to the largest void until the pattern is stable."""
    size = pattern.shape[0]
    while True:
        cluster = _tightest_cluster(field, pattern)
        cy, cx = divmod(cluster, size)
        pattern[cy, cx] = 0.0
        field -= _shifted(kernel, cy, cx)
        void = _largest_void(field, pattern)
        if void == cluster:
            pattern[cy, cx] = 1.0
            field += _shifted(kernel, cy, cx)
            return
        vy, vx = divmod(void, size)
        pattern[vy, vx] = 1.0
        field += _shifted(kernel, vy, vx)


def generate(size: int = SIZE, sigma: float = SIGMA, seed: int = SEED) -> np.ndarray:
    """Return a size x size blue-noise rank array holding a permutation of 0..size*size-1."""
    rng = np.random.default_rng(seed)
    total = size * size
    kernel = gaussian_kernel(size, sigma)
    pattern = np.zeros((size, size), dtype=np.float64)
    initial = max(1, int(round(INITIAL_FRACTION * total)))
    pattern.flat[rng.choice(total, size=initial, replace=False)] = 1.0
    field = convolve(pattern, kernel)
    relax(pattern, field, kernel)
    prototype = pattern.copy()
    prototype_field = field.copy()
    ones = int(prototype.sum())
    ranks = np.full((size, size), -1, dtype=np.int32)

    work = prototype.copy()
    work_field = prototype_field.copy()
    for rank in range(ones - 1, -1, -1):
        cluster = _tightest_cluster(work_field, work)
        cy, cx = divmod(cluster, size)
        ranks[cy, cx] = rank
        work[cy, cx] = 0.0
        work_field -= _shifted(kernel, cy, cx)

    work = prototype.copy()
    work_field = prototype_field.copy()
    for rank in range(ones, total):
        void = _largest_void(work_field, work)
        vy, vx = divmod(void, size)
        ranks[vy, vx] = rank
        work[vy, vx] = 1.0
        work_field += _shifted(kernel, vy, vx)
    return ranks


def main() -> int:
    """Generate the rank array, verify it is a permutation and write it to data/."""
    start = time.perf_counter()
    ranks = generate()
    elapsed = time.perf_counter() - start
    expected = np.arange(ranks.size, dtype=np.int32)
    if ranks.shape != (SIZE, SIZE) or not np.array_equal(np.sort(ranks.ravel()), expected):
        print("generated array is not a permutation of 0..4095")
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.save(OUTPUT, ranks)
    print(f"wrote {OUTPUT} in {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
