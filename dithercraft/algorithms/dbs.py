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

The search keeps the *filtered* error S = w * e rather than the raw error e.
Every candidate move then costs a dot product instead of a convolution: a
recolour changes the perceived error by |d|^2 * sum(w^2) - 2 d.S, and a swap by
|d|^2 * G - 2 d.(S - S_shifted), where G = 2 * (sum(w^2) - A(offset)) and A is
the autocorrelation of the kernel. Applying a move updates S over the support of
A, which is the only per-move convolution left.
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


def separable_weights(radius: int) -> np.ndarray:
    """Return the normalised 1-D Gaussian whose outer product is the 2-D kernel."""
    sigma = max(radius / 2.0, 0.5)
    axis = np.arange(-radius, radius + 1, dtype=np.float32)
    weights = np.exp(-(axis * axis) / (2.0 * sigma * sigma))
    return np.ascontiguousarray(weights / weights.sum(), dtype=np.float32)


def gaussian_kernel(radius: int) -> np.ndarray:
    """Return a normalised (2r+1) x (2r+1) Gaussian with sigma = radius / 2."""
    weights = separable_weights(radius)
    return np.ascontiguousarray(np.outer(weights, weights), dtype=np.float32)


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


def autocorrelation(kernel: np.ndarray, radius: int) -> np.ndarray:
    """Return A(r) = sum_u w(u) w(u + r) for r in [-2r, 2r]^2."""
    size = 4 * radius + 1
    span = 2 * radius + 1
    out = np.zeros((size, size), dtype=np.float32)
    for i in range(span):
        for j in range(span):
            for i2 in range(span):
                for j2 in range(span):
                    out[i2 - i + 2 * radius, j2 - j + 2 * radius] += kernel[i, j] * kernel[i2, j2]
    return np.ascontiguousarray(out)


def _mix(index: np.ndarray) -> np.ndarray:
    """Return a splitmix64 hash of index, so the visit order is stable across NumPy versions."""
    value = index.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15)
    value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


_ORDER_CACHE: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
_ORDER_CACHE_LIMIT = 4


def pixel_order(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the pixel visit order: a fixed shuffle, so the scan has no directional bias."""
    key = (height, width)
    cached = _ORDER_CACHE.get(key)
    if cached is not None:
        return cached
    order = np.argsort(_mix(np.arange(height * width, dtype=np.int64)), kind="stable")
    ys, xs = np.unravel_index(order, (height, width))
    built = (
        np.ascontiguousarray(ys, dtype=np.int64),
        np.ascontiguousarray(xs, dtype=np.int64),
    )
    if len(_ORDER_CACHE) >= _ORDER_CACHE_LIMIT:
        _ORDER_CACHE.clear()
    _ORDER_CACHE[key] = built
    return built


@njit(cache=True)
def _blur(src: np.ndarray, weights: np.ndarray, radius: int) -> np.ndarray:
    """Correlate a float32 image with a separable Gaussian, dropping out-of-bounds taps."""
    height = src.shape[0]
    width = src.shape[1]
    rows = np.zeros((height, width, 3), dtype=np.float32)
    out = np.zeros((height, width, 3), dtype=np.float32)
    for y in range(height):
        for k in range(-radius, radius + 1):
            weight = weights[k + radius]
            for x in range(width):
                nx = x + k
                if 0 <= nx < width:
                    rows[y, x, 0] += src[y, nx, 0] * weight
                    rows[y, x, 1] += src[y, nx, 1] * weight
                    rows[y, x, 2] += src[y, nx, 2] * weight
    for y in range(height):
        for k in range(-radius, radius + 1):
            weight = weights[k + radius]
            ny = y + k
            if 0 <= ny < height:
                for x in range(width):
                    out[y, x, 0] += rows[ny, x, 0] * weight
                    out[y, x, 1] += rows[ny, x, 1] * weight
                    out[y, x, 2] += rows[ny, x, 2] * weight
    return out


@njit(cache=True)
def _search(
    img: np.ndarray,
    palette: np.ndarray,
    kernel: np.ndarray,
    weights: np.ndarray,
    autocorr: np.ndarray,
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
    target = _blur(img, weights, radius)
    current = _blur(rendered, weights, radius)
    error = np.empty((height, width, 3), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            error[y, x, 0] = target[y, x, 0] - current[y, x, 0]
            error[y, x, 1] = target[y, x, 1] - current[y, x, 1]
            error[y, x, 2] = target[y, x, 2] - current[y, x, 2]
    filtered = _blur(error, weights, radius)
    energy = 0.0
    for ky in range(2 * radius + 1):
        for kx in range(2 * radius + 1):
            weight = kernel[ky, kx]
            energy += weight * weight
    swap_count = offsets.shape[0]
    ac_radius = 2 * radius
    ac_size = autocorr.shape[0]
    swap_energy = np.empty(swap_count, dtype=np.float32)
    for index in range(swap_count):
        oy = offsets[index, 1]
        ox = offsets[index, 0]
        swap_energy[index] = 2.0 * (energy - autocorr[oy + ac_radius, ox + ac_radius])
    for _ in range(iterations):
        for step in range(ys.shape[0]):
            y = ys[step]
            x = xs[step]
            old = halftone[y, x]
            here_r = filtered[y, x, 0]
            here_g = filtered[y, x, 1]
            here_b = filtered[y, x, 2]
            old_r = palette[old, 0]
            old_g = palette[old, 1]
            old_b = palette[old, 2]
            best_delta = 0.0
            best_colour = old
            best_swap = -1
            for candidate in range(count):
                if candidate == old:
                    continue
                dr = palette[candidate, 0] - old_r
                dg = palette[candidate, 1] - old_g
                db = palette[candidate, 2] - old_b
                delta = energy * (dr * dr + dg * dg + db * db) - 2.0 * (
                    here_r * dr + here_g * dg + here_b * db
                )
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
                dr = palette[other, 0] - old_r
                dg = palette[other, 1] - old_g
                db = palette[other, 2] - old_b
                delta = swap_energy[index] * (dr * dr + dg * dg + db * db) - 2.0 * (
                    (here_r - filtered[ny, nx, 0]) * dr
                    + (here_g - filtered[ny, nx, 1]) * dg
                    + (here_b - filtered[ny, nx, 2]) * db
                )
                if delta < best_delta:
                    best_delta = delta
                    best_colour = old
                    best_swap = index
            if best_swap >= 0:
                ny = y + offsets[best_swap, 1]
                nx = x + offsets[best_swap, 0]
                other = halftone[ny, nx]
                dr = palette[other, 0] - palette[old, 0]
                dg = palette[other, 1] - palette[old, 1]
                db = palette[other, 2] - palette[old, 2]
                halftone[y, x] = other
                halftone[ny, nx] = old
                oy = offsets[best_swap, 1]
                ox = offsets[best_swap, 0]
                for i in range(ac_size):
                    qy = y + i - ac_radius
                    if qy < 0 or qy >= height:
                        continue
                    for j in range(ac_size):
                        qx = x + j - ac_radius
                        if qx < 0 or qx >= width:
                            continue
                        value = autocorr[i, j]
                        back_y = i - oy
                        back_x = j - ox
                        if 0 <= back_y < ac_size and 0 <= back_x < ac_size:
                            value -= autocorr[back_y, back_x]
                        filtered[qy, qx, 0] -= value * dr
                        filtered[qy, qx, 1] -= value * dg
                        filtered[qy, qx, 2] -= value * db
            elif best_colour != old:
                dr = palette[best_colour, 0] - palette[old, 0]
                dg = palette[best_colour, 1] - palette[old, 1]
                db = palette[best_colour, 2] - palette[old, 2]
                halftone[y, x] = best_colour
                for i in range(ac_size):
                    qy = y + i - ac_radius
                    if qy < 0 or qy >= height:
                        continue
                    for j in range(ac_size):
                        qx = x + j - ac_radius
                        if qx < 0 or qx >= width:
                            continue
                        value = autocorr[i, j]
                        filtered[qy, qx, 0] -= value * dr
                        filtered[qy, qx, 1] -= value * dg
                        filtered[qy, qx, 2] -= value * db
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
        separable_weights(radius),
        autocorrelation(kernel, radius),
        _SWAP_OFFSETS,
        ys,
        xs,
        radius,
        int(params["iterations"]),
    )
