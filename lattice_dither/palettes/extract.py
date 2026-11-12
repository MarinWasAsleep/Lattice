"""Palette extraction from images (T06)."""

from __future__ import annotations

from typing import Literal

import numpy as np

from lattice_dither.core.color import luminance
from lattice_dither.core.types import Image, Palette

MAX_SAMPLES = 65536
MAX_ITERATIONS = 30
MIN_K = 2
MAX_K = 32


def _subsample(pixels: np.ndarray, seed: int) -> np.ndarray:
    """Return at most MAX_SAMPLES pixels drawn without replacement with default_rng(seed)."""
    if pixels.shape[0] <= MAX_SAMPLES:
        return pixels
    picks = np.random.default_rng(seed).choice(pixels.shape[0], MAX_SAMPLES, replace=False)
    return np.ascontiguousarray(pixels[np.sort(picks)])


def _unique_colors(pixels: np.ndarray) -> np.ndarray:
    """Return the distinct float32 colours of pixels as a (U, 3) array, exactly."""
    data = np.ascontiguousarray(pixels, dtype=np.float32).reshape(-1, 3)
    bits = data.view(np.uint32)
    high = (bits[:, 0].astype(np.uint64) << np.uint64(32)) | bits[:, 1]
    order = np.lexsort((bits[:, 2], high))
    sorted_high = high[order]
    sorted_low = bits[order, 2]
    keep = np.ones(sorted_high.shape[0], dtype=bool)
    keep[1:] = (sorted_high[1:] != sorted_high[:-1]) | (sorted_low[1:] != sorted_low[:-1])
    unique = np.empty((int(keep.sum()), 3), dtype=np.uint32)
    unique[:, 0] = sorted_high[keep] >> np.uint64(32)
    unique[:, 1] = sorted_high[keep] & np.uint64(0xFFFFFFFF)
    unique[:, 2] = sorted_low[keep]
    return unique.view(np.float32)


def _sorted_palette(colors: np.ndarray) -> Palette:
    """Return the colours as a float32 palette sorted by luminance ascending."""
    palette = np.ascontiguousarray(np.clip(colors, 0.0, 1.0), dtype=np.float32)
    order = np.argsort(luminance(palette.reshape(1, -1, 3))[0], kind="stable")
    return np.ascontiguousarray(palette[order])


def _few_colors(unique: np.ndarray) -> Palette:
    """Return the distinct colours, adding black or white when only one exists."""
    if unique.shape[0] == 1:
        color = unique[0]
        to_black = float(np.sum(color * color))
        to_white = float(np.sum((np.float32(1.0) - color) ** 2))
        extra = np.zeros((1, 3), np.float32) if to_black > to_white else np.ones((1, 3), np.float32)
        unique = np.concatenate([unique, extra], axis=0)
    return _sorted_palette(unique)


def _sq_dist(data: np.ndarray, center: np.ndarray) -> np.ndarray:
    """Return the squared euclidean distance of every row of data to one centre."""
    diff = data - center
    return np.einsum("ij,ij->i", diff, diff)


def _kmeans_pp(data: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """Choose k initial centres with the k-means++ rule."""
    centers = np.empty((k, 3), dtype=np.float32)
    centers[0] = data[rng.integers(data.shape[0])]
    closest = _sq_dist(data, centers[0])
    for index in range(1, k):
        total = float(closest.sum())
        if total <= 0.0:
            centers[index] = data[rng.integers(data.shape[0])]
        else:
            centers[index] = data[rng.choice(data.shape[0], p=closest / total)]
        closest = np.minimum(closest, _sq_dist(data, centers[index]))
    return centers


def _assign(data: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Return the index of the closest centre for every row of data."""
    distances = (
        np.einsum("ij,ij->i", data, data)[:, None]
        - 2.0 * (data @ centers.T)
        + np.einsum("ij,ij->i", centers, centers)[None, :]
    )
    return np.argmin(distances, axis=1)


def _update(data: np.ndarray, labels: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Return the mean of every cluster, keeping the old centre for empty clusters."""
    k = centers.shape[0]
    counts = np.bincount(labels, minlength=k).astype(np.float64)
    sums = np.stack(
        [np.bincount(labels, weights=data[:, channel], minlength=k) for channel in range(3)],
        axis=1,
    )
    means = sums / np.maximum(counts, 1.0)[:, None]
    empty = counts == 0
    means[empty] = centers[empty]
    return means.astype(np.float32)


def _kmeans(data: np.ndarray, k: int, seed: int) -> np.ndarray:
    """Run k-means with k-means++ initialisation for at most MAX_ITERATIONS steps."""
    rng = np.random.default_rng(seed)
    centers = _kmeans_pp(data, k, rng)
    for _ in range(MAX_ITERATIONS):
        updated = _update(data, _assign(data, centers), centers)
        converged = np.allclose(updated, centers, atol=1e-6)
        centers = updated
        if converged:
            break
    return centers


def _widest_box(boxes: list[np.ndarray]) -> tuple[int, int] | None:
    """Return the index and channel of the box with the largest channel range."""
    best: tuple[float, int, int] | None = None
    for index, box in enumerate(boxes):
        if box.shape[0] < 2:
            continue
        ranges = box.max(axis=0) - box.min(axis=0)
        channel = int(np.argmax(ranges))
        span = float(ranges[channel])
        if span > 0.0 and (best is None or span > best[0]):
            best = (span, index, channel)
    if best is None:
        return None
    return best[1], best[2]


def _split_at_median(box: np.ndarray, channel: int) -> tuple[np.ndarray, np.ndarray]:
    """Split a box at the median of one channel, falling back to the middle index."""
    values = box[:, channel]
    median = float(np.median(values))
    left = box[values <= median]
    right = box[values > median]
    if left.shape[0] == 0 or right.shape[0] == 0:
        order = np.argsort(values, kind="stable")
        middle = order.shape[0] // 2
        left = box[order[:middle]]
        right = box[order[middle:]]
    return left, right


def _median_cut(data: np.ndarray, k: int) -> np.ndarray:
    """Split the colour cloud at the median of its widest channel until k boxes exist."""
    boxes = [data]
    while len(boxes) < k:
        target = _widest_box(boxes)
        if target is None:
            break
        index, channel = target
        box = boxes.pop(index)
        left, right = _split_at_median(box, channel)
        if left.shape[0] == 0 or right.shape[0] == 0:
            boxes.append(box)
            break
        boxes.extend((left, right))
    return np.array([box.mean(axis=0) for box in boxes], dtype=np.float32)


def extract_palette(
    img: Image, k: int, method: Literal["kmeans", "median_cut"], seed: int = 0
) -> Palette:
    """Extract k colours from img, sorted by luminance ascending."""
    if method not in ("kmeans", "median_cut"):
        raise ValueError(f"unknown extraction method: {method!r}")
    if not MIN_K <= k <= MAX_K:
        raise ValueError(f"k must be in [{MIN_K}, {MAX_K}], got {k}")
    pixels = np.ascontiguousarray(img, dtype=np.float32).reshape(-1, 3)
    if pixels.shape[0] == 0:
        raise ValueError("cannot extract a palette from an empty image")
    data = _subsample(pixels, seed)
    unique = _unique_colors(data)
    if unique.shape[0] < k:
        full = _unique_colors(pixels)
        if full.shape[0] < k:
            return _few_colors(full)
        if full.shape[0] <= MAX_SAMPLES:
            data = full
        else:
            return _few_colors(unique)
    colors = _kmeans(data, k, seed) if method == "kmeans" else _median_cut(data, k)
    return _sorted_palette(colors)
