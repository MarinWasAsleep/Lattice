"""Direct Binary Search halftoning.

DBS starts from the nearest-colour quantisation and then repeatedly tries to
improve the halftone, keeping a change only when it lowers the perceived error.
The perceived error is the difference between the original and the halftone,
both blurred by a Gaussian point-spread function, so the search optimises local
average colour rather than per-pixel distance.

Two moves are tried: replacing a pixel's colour, and swapping the colours of two
neighbouring pixels. The swap is what lets the search redistribute dots without
changing the local average, so a flat grey converges to the right density
instead of stalling on the first overshoot. Pixels are visited in a fixed
shuffled order, because a raster scan biases the error towards the top-left and
overshoots badly on flat areas.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from dithercraft.core.color import nearest_index_px
from dithercraft.core.registry import register_algorithm
from dithercraft.core.types import Image, Indices, Palette, ParamSpec

_PARAMS = (
    ParamSpec("iterations", "Iterations", "int", 2, 1, 8, 1),
    ParamSpec("radius", "Radius", "int", 2, 1, 4, 1),
)

_SWAP_OFFSETS = np.array(
    [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)],
    dtype=np.int64,
)


def gaussian_kernel(radius: int) -> np.ndarray:
    """Return a normalised (2r+1) x (2r+1) Gaussian with sigma = radius / 2."""
    sigma = max(radius / 2.0, 0.5)
    axis = np.arange(-radius, radius + 1, dtype=np.float32)
    dy, dx = np.meshgrid(axis, axis, indexing="ij")
    kernel = np.exp(-(dy * dy + dx * dx) / (2.0 * sigma * sigma))
    return np.ascontiguousarray(kernel / kernel.sum(), dtype=np.float32)


def swap_stencils(kernel: np.ndarray, radius: int) -> np.ndarray:
    """Return, per swap offset, the stencil g(u) = w(u) - w(u - offset)."""
    size = 2 * radius + 3
    padded = np.zeros((size, size), dtype=np.float32)
    padded[1 : size - 1, 1 : size - 1] = kernel
    stencils = np.empty((_SWAP_OFFSETS.shape[0], size, size), dtype=np.float32)
    for index in range(_SWAP_OFFSETS.shape[0]):
        ox = int(_SWAP_OFFSETS[index, 0])
        oy = int(_SWAP_OFFSETS[index, 1])
        shifted = np.zeros((size, size), dtype=np.float32)
        shifted[1 + oy : size - 1 + oy, 1 + ox : size - 1 + ox] = kernel
        stencils[index] = padded - shifted
    return np.ascontiguousarray(stencils)


def _mix(index: np.ndarray) -> np.ndarray:
    """Return a splitmix64 hash of index, so the visit order is stable across NumPy versions."""
    value = index.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15)
    value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


def pixel_order(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the pixel visit order: a fixed shuffle, so the scan has no directional bias."""
    order = np.argsort(_mix(np.arange(height * width, dtype=np.int64)), kind="stable")
    ys, xs = np.unravel_index(order, (height, width))
    return np.ascontiguousarray(ys, dtype=np.int64), np.ascontiguousarray(xs, dtype=np.int64)


@njit(cache=True)
def _blur(src: np.ndarray, kernel: np.ndarray, radius: int) -> np.ndarray:
    """Convolve a float32 image with a square kernel, dropping out-of-bounds taps."""
    height = src.shape[0]
    width = src.shape[1]
    out = np.zeros((height, width, 3), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            acc_r = 0.0
            acc_g = 0.0
            acc_b = 0.0
            for ky in range(-radius, radius + 1):
                ny = y + ky
                if ny < 0 or ny >= height:
                    continue
                for kx in range(-radius, radius + 1):
                    nx = x + kx
                    if nx < 0 or nx >= width:
                        continue
                    weight = kernel[ky + radius, kx + radius]
                    acc_r += src[ny, nx, 0] * weight
                    acc_g += src[ny, nx, 1] * weight
                    acc_b += src[ny, nx, 2] * weight
            out[y, x, 0] = acc_r
            out[y, x, 1] = acc_g
            out[y, x, 2] = acc_b
    return out


@njit(cache=True)
def _toggle_delta(
    error: np.ndarray,
    palette: np.ndarray,
    old: int,
    candidate: int,
    kernel: np.ndarray,
    radius: int,
    y: int,
    x: int,
) -> float:
    """Return the change in perceived squared error if the pixel takes candidate."""
    height = error.shape[0]
    width = error.shape[1]
    dr = palette[candidate, 0] - palette[old, 0]
    dg = palette[candidate, 1] - palette[old, 1]
    db = palette[candidate, 2] - palette[old, 2]
    square = dr * dr + dg * dg + db * db
    delta = 0.0
    for ky in range(-radius, radius + 1):
        ny = y + ky
        if ny < 0 or ny >= height:
            continue
        for kx in range(-radius, radius + 1):
            nx = x + kx
            if nx < 0 or nx >= width:
                continue
            weight = kernel[ky + radius, kx + radius]
            delta += weight * weight * square - 2.0 * weight * (
                error[ny, nx, 0] * dr + error[ny, nx, 1] * dg + error[ny, nx, 2] * db
            )
    return delta


@njit(cache=True)
def _swap_delta(
    error: np.ndarray,
    palette: np.ndarray,
    old: int,
    other: int,
    stencils: np.ndarray,
    index: int,
    y: int,
    x: int,
    pad: int,
) -> float:
    """Return the change in perceived squared error if the pixel swaps with its neighbour."""
    height = error.shape[0]
    width = error.shape[1]
    size = stencils.shape[1]
    dr = palette[other, 0] - palette[old, 0]
    dg = palette[other, 1] - palette[old, 1]
    db = palette[other, 2] - palette[old, 2]
    square = dr * dr + dg * dg + db * db
    delta = 0.0
    for i in range(size):
        uy = y + i - pad
        if uy < 0 or uy >= height:
            continue
        for j in range(size):
            ux = x + j - pad
            if ux < 0 or ux >= width:
                continue
            value = stencils[index, i, j]
            delta += value * value * square - 2.0 * value * (
                error[uy, ux, 0] * dr + error[uy, ux, 1] * dg + error[uy, ux, 2] * db
            )
    return delta


@njit(cache=True)
def _apply_toggle(
    error: np.ndarray,
    palette: np.ndarray,
    old: int,
    new: int,
    kernel: np.ndarray,
    radius: int,
    y: int,
    x: int,
) -> None:
    """Move the error of one recoloured pixel into its neighbourhood."""
    height = error.shape[0]
    width = error.shape[1]
    dr = palette[new, 0] - palette[old, 0]
    dg = palette[new, 1] - palette[old, 1]
    db = palette[new, 2] - palette[old, 2]
    for ky in range(-radius, radius + 1):
        ny = y + ky
        if ny < 0 or ny >= height:
            continue
        for kx in range(-radius, radius + 1):
            nx = x + kx
            if nx < 0 or nx >= width:
                continue
            weight = kernel[ky + radius, kx + radius]
            error[ny, nx, 0] -= weight * dr
            error[ny, nx, 1] -= weight * dg
            error[ny, nx, 2] -= weight * db


@njit(cache=True)
def _apply_swap(
    error: np.ndarray,
    palette: np.ndarray,
    old: int,
    other: int,
    stencils: np.ndarray,
    index: int,
    y: int,
    x: int,
    pad: int,
) -> None:
    """Move the error of one swapped pair into its neighbourhood."""
    height = error.shape[0]
    width = error.shape[1]
    size = stencils.shape[1]
    dr = palette[other, 0] - palette[old, 0]
    dg = palette[other, 1] - palette[old, 1]
    db = palette[other, 2] - palette[old, 2]
    for i in range(size):
        uy = y + i - pad
        if uy < 0 or uy >= height:
            continue
        for j in range(size):
            ux = x + j - pad
            if ux < 0 or ux >= width:
                continue
            value = stencils[index, i, j]
            error[uy, ux, 0] -= value * dr
            error[uy, ux, 1] -= value * dg
            error[uy, ux, 2] -= value * db


@njit(cache=True)
def _search(
    img: np.ndarray,
    palette: np.ndarray,
    kernel: np.ndarray,
    stencils: np.ndarray,
    offsets: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
    radius: int,
    iterations: int,
) -> np.ndarray:
    """Greedily recolour and swap pixels while the perceived squared error decreases."""
    height = img.shape[0]
    width = img.shape[1]
    count = palette.shape[0]
    halftone = np.empty((height, width), dtype=np.int32)
    rendered = np.empty((height, width, 3), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            index = nearest_index_px(img[y, x, 0], img[y, x, 1], img[y, x, 2], palette)
            halftone[y, x] = index
            rendered[y, x, 0] = palette[index, 0]
            rendered[y, x, 1] = palette[index, 1]
            rendered[y, x, 2] = palette[index, 2]
    target = _blur(img, kernel, radius)
    current = _blur(rendered, kernel, radius)
    error = np.empty((height, width, 3), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            error[y, x, 0] = target[y, x, 0] - current[y, x, 0]
            error[y, x, 1] = target[y, x, 1] - current[y, x, 1]
            error[y, x, 2] = target[y, x, 2] - current[y, x, 2]
    swap_count = offsets.shape[0]
    pad = radius + 1
    for _ in range(iterations):
        for step in range(ys.shape[0]):
            y = ys[step]
            x = xs[step]
            old = halftone[y, x]
            best_delta = 0.0
            best_colour = old
            best_swap = -1
            for candidate in range(count):
                if candidate == old:
                    continue
                delta = _toggle_delta(error, palette, old, candidate, kernel, radius, y, x)
                if delta < best_delta:
                    best_delta = delta
                    best_colour = candidate
                    best_swap = -1
            for index in range(swap_count):
                ny = y + offsets[index, 1]
                nx = x + offsets[index, 0]
                if ny < 0 or ny >= height or nx < 0 or nx >= width:
                    continue
                other = halftone[ny, nx]
                if other == old:
                    continue
                delta = _swap_delta(error, palette, old, other, stencils, index, y, x, pad)
                if delta < best_delta:
                    best_delta = delta
                    best_colour = old
                    best_swap = index
            if best_swap >= 0:
                ny = y + offsets[best_swap, 1]
                nx = x + offsets[best_swap, 0]
                other = halftone[ny, nx]
                halftone[y, x] = other
                halftone[ny, nx] = old
                _apply_swap(error, palette, old, other, stencils, best_swap, y, x, pad)
            elif best_colour != old:
                halftone[y, x] = best_colour
                _apply_toggle(error, palette, old, best_colour, kernel, radius, y, x)
    return halftone


@register_algorithm("direct_binary_search", "Direct Binary Search", "other", _PARAMS)
def direct_binary_search(img: Image, palette: Palette, params: dict) -> Indices:
    """Minimise the Gaussian-blurred error by recolouring and swapping pixels."""
    radius = int(params["radius"])
    kernel = gaussian_kernel(radius)
    height, width = img.shape[:2]
    ys, xs = pixel_order(height, width)
    return _search(
        np.ascontiguousarray(img, dtype=np.float32),
        np.ascontiguousarray(palette, dtype=np.float32),
        kernel,
        swap_stencils(kernel, radius),
        _SWAP_OFFSETS,
        ys,
        xs,
        radius,
        int(params["iterations"]),
    )
