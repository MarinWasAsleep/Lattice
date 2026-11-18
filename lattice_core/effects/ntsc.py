"""NTSC / VHS effect: a full RGB→YIQ→noise→demodulate signal-emulation chain (CONTRACT §16).

Artefacts emerge from the composite signal rather than from an overlay: snow and
sharpening act on the luma of the YIQ signal before demodulation, and the bandwidth
limit runs along the scan lines. Every distortion is a no-op at its neutral value,
so the whole chain is the identity when all parameters sit at their defaults.
"""

from __future__ import annotations

import math

import numpy as np

from lattice_core.registry import register_effect
from lattice_core.types import Image, ParamSpec

# NTSC YIQ encoding (FCC matrices). Y is unsigned in [0, 1]; I and Q are signed.
_YIQ = np.array(
    [[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]],
    dtype=np.float32,
)
_RGB_FROM_YIQ = np.array(
    [[1.0, 0.956, 0.621], [1.0, -0.272, -0.647], [1.0, -1.106, 1.703]],
    dtype=np.float32,
)
_TAPE_BANDWIDTH = {"sp": 1.0, "lp": 0.72, "ep": 0.55}
_RINGING = ("butterworth", "constant_k")
_TAPE_SPEEDS = ("sp", "lp", "ep")
# Bandwidth kernel: a fixed 21-tap window whose taps are mixed with an impulse by
# `bandwidth`, so the response is continuous in the parameter and exact at 1.0.
_BANDWIDTH_RADIUS = 10
_FILTER_SAMPLES = 512
_BUTTERWORTH_ORDER = 4
# The stochastic stages, each of which draws from its own child generator.
_STAGES: tuple[str, ...] = ("chroma_phase", "luma_noise", "composite", "snow", "tracking")

# Labels are keys of the shared UI catalogue, which this card does not own, so no
# NTSC-specific key can be added here (E1): each label is the catalogue key that
# names its control most nearly, LABEL_NOTES records the honest reading, no two
# parameters share a label, and a catalogue-owning card must add dedicated keys.
_PARAMS = (
    ParamSpec("seed", "Seed", "int", 0, 0, 2**31 - 1, 1),
    ParamSpec("chroma_lowpass", "Pre-blur", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("chroma_phase_noise", "Corruptions", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("luma_smear", "Radius", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("luma_noise", "Intensity", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("composite_noise", "Level", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("bandwidth", "Resolution", "float", 1.0, 0.0, 1.0, 0.02),
    ParamSpec("ringing", "Threshold", "choice", "butterworth", choices=_RINGING),
    ParamSpec("head_switching", "Scale", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("band_height", "Thickness", "float", 0.02, 0.0, 1.0, 0.01),
    ParamSpec("tracking_noise", "Spread", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("snow", "Amount", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("sharpening", "Strength", "float", 0.0, 0.0, 1.0, 0.02),
    ParamSpec("tape_speed", "Quality", "choice", "sp", choices=_TAPE_SPEEDS),
)

# What each label really names, in the user's terms.
LABEL_NOTES: dict[str, str] = {
    "seed": "the noise seed, mixed into the pipeline generator",
    "chroma_lowpass": "a low-pass pre-blur of the chroma planes",
    "chroma_phase_noise": "the amount of chroma phase corruption",
    "luma_smear": "the horizontal smear radius of the luma",
    "luma_noise": "the intensity of the luma noise",
    "composite_noise": "the level of noise on the whole composite signal",
    "bandwidth": "the horizontal resolution left by the bandwidth limit",
    "ringing": "the sharpness of the bandwidth cutoff, i.e. how hard it rings",
    "head_switching": "the scale of the bottom-band displacement (1 = half the width)",
    "band_height": "the thickness of the displaced bottom band",
    "tracking_noise": "the spread of the per-line horizontal jitter",
    "snow": "the amount of monochrome snow",
    "sharpening": "the strength of the luma edge enhancement",
    "tape_speed": "the recording quality: sp, lp or ep",
}

# The simple mode exposes exactly four parameters; everything else is behind the
# advanced toggle. Both tuples are derived from _PARAMS, never duplicated.
_SIMPLE_IDS: tuple[str, ...] = ("bandwidth", "chroma_lowpass", "snow", "head_switching")
MODES: tuple[str, ...] = ("simple", "advanced")
_BY_ID: dict[str, ParamSpec] = {spec.id: spec for spec in _PARAMS}


def params_for_mode(mode: str) -> tuple[ParamSpec, ...]:
    """Return the parameters a UI exposes in mode: four in simple, all in advanced."""
    if mode == "advanced":
        return _PARAMS
    if mode == "simple":
        return tuple(_BY_ID[param_id] for param_id in _SIMPLE_IDS)
    raise ValueError(f"unknown NTSC mode {mode!r}, expected one of {MODES}")


SIMPLE_PARAMS = params_for_mode("simple")
SIMPLE_PARAM_IDS = tuple(spec.id for spec in SIMPLE_PARAMS)

# Six named presets, each a set of non-neutral parameters on top of the defaults.
PRESETS: dict[str, dict] = {
    "Clean Broadcast": {"bandwidth": 0.85, "chroma_lowpass": 0.2, "luma_noise": 0.05},
    "Vintage TV": {"bandwidth": 0.55, "chroma_lowpass": 0.45, "chroma_phase_noise": 0.35},
    "VHS Home": {"tape_speed": "ep", "luma_smear": 0.45, "luma_noise": 0.2, "tracking_noise": 0.7},
    "Static": {"snow": 0.6, "composite_noise": 0.35},
    "Glitch Tape": {
        "head_switching": 0.6,
        "band_height": 0.35,
        "tracking_noise": 0.9,
        "chroma_phase_noise": 0.5,
    },
    "Retro": {"sharpening": 0.7, "chroma_lowpass": 0.35, "luma_noise": 0.12},
}
PRESET_NAMES = tuple(PRESETS)


def preset(name: str) -> dict:
    """Return the parameter overrides of one named preset."""
    if name not in PRESETS:
        raise KeyError(f"unknown NTSC preset: {name!r}")
    return dict(PRESETS[name])


def _copy(img: Image) -> Image:
    """Return a contiguous float32 copy of img, clipped to [0, 1]."""
    out = np.asarray(img, dtype=np.float32)
    return np.clip(out, 0.0, 1.0, out=np.array(out, order="C", copy=True))


def _generator(params: dict, rng: np.random.Generator) -> np.random.Generator:
    """Return the root noise source: `seed` offsets the pipeline rng, so both drive it."""
    return np.random.default_rng([int(params.get("seed", 0)), int(rng.integers(0, 2**32))])


def _stage_rngs(root: np.random.Generator) -> dict[str, np.random.Generator]:
    """Return one child generator per stochastic stage; all seeds are drawn up front."""
    seeds = root.integers(0, 2**32, size=len(_STAGES))
    return {
        name: np.random.default_rng([int(seed), index])
        for index, (name, seed) in enumerate(zip(_STAGES, seeds, strict=True))
    }


def _yiq(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the Y, I and Q planes of a float32 RGB image."""
    h, w, _ = rgb.shape
    stacked = rgb.reshape(-1, 3) @ _YIQ.T
    y, i, q = stacked[:, 0].reshape(h, w), stacked[:, 1].reshape(h, w), stacked[:, 2].reshape(h, w)
    return y, i, q


def _rgb(yi: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    """Demodulate Y, I, Q planes back into a clipped float32 RGB image."""
    y, i, q = yi
    h, w = y.shape
    stacked = np.stack((y, i, q), axis=-1).reshape(-1, 3)
    rgb = stacked @ _RGB_FROM_YIQ.T
    return np.clip(rgb.reshape(h, w, 3), 0.0, 1.0).astype(np.float32)


def _blur_axis(data: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    """Convolve data along one axis with kernel, replicating the edge samples."""
    radius = kernel.size // 2
    pad = [(0, 0)] * data.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(data, pad, mode="edge")
    length = data.shape[axis]
    out = np.zeros(data.shape, dtype=np.float64)
    for index, weight in enumerate(kernel):
        window = [slice(None)] * data.ndim
        window[axis] = slice(index, index + length)
        out += np.float64(weight) * padded[tuple(window)]
    return out.astype(np.float32)


def _gaussian_kernel(sigma: float) -> np.ndarray:
    """Return a normalised 1-D gaussian kernel of radius ceil(3 * sigma)."""
    radius = max(1, int(math.ceil(3.0 * sigma)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(offsets * offsets) / np.float32(2.0 * sigma * sigma))
    return (kernel / kernel.sum()).astype(np.float32)


def _plane_blur(plane: np.ndarray, sigma: float) -> np.ndarray:
    """Separably blur one 2-D plane with replicated edges; sigma <= 0 is a no-op."""
    if not sigma > 0.0:
        return plane
    kernel = _gaussian_kernel(float(sigma))
    out = _blur_axis(plane, kernel, 0)
    return _blur_axis(out, kernel, 1)


def _chroma_lowpass(i: np.ndarray, q: np.ndarray, amount: float) -> tuple[np.ndarray, np.ndarray]:
    """Low-pass and subsample the chroma planes; amount 0 is the identity."""
    if amount <= 0.0:
        return i, q
    i, q = _plane_blur(i, amount), _plane_blur(q, amount)
    factor = max(1, int(round(amount * 8.0)))
    if factor > 1:
        i, q = _subsample(i, factor), _subsample(q, factor)
    return i, q


def _subsample(plane: np.ndarray, factor: int) -> np.ndarray:
    """Hold-sample subsample: block-average factor columns, then replicate each."""
    _, width = plane.shape
    if factor <= 1 or width < 2:
        return plane
    out = np.empty_like(plane)
    for x0 in range(0, width, factor):
        x1 = min(width, x0 + factor)
        out[:, x0:x1] = plane[:, x0:x1].mean(axis=1)[:, None]
    return out.astype(np.float32)


def _phase_noise(
    i: np.ndarray, q: np.ndarray, amount: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Rotate the chroma phasor by a seeded random angle per horizontal strip."""
    if amount <= 0.0:
        return i, q
    height = i.shape[0]
    strips = max(1, min(height, 8))
    angles = rng.uniform(-1.0, 1.0, size=strips).astype(np.float32) * np.float32(amount * math.pi)
    cut = np.linspace(0, height, strips + 1, dtype=int)
    i_out, q_out = i.copy(), q.copy()
    for n in range(strips):
        rows = slice(cut[n], cut[n + 1])
        cos, sin = np.float32(math.cos(float(angles[n]))), np.float32(math.sin(float(angles[n])))
        ia, qa = i[rows], q[rows]
        i_out[rows], q_out[rows] = ia * cos - qa * sin, ia * sin + qa * cos
    return i_out, q_out


def _luma_smear(y: np.ndarray, amount: float) -> np.ndarray:
    """Horizontally smear the luminance plane with a 1-D gaussian."""
    if amount <= 0.0:
        return y
    kernel = _gaussian_kernel(max(0.25, amount * 4.0))
    return _blur_axis(y, kernel, 1)


def _bandwidth_kernel(bw: float, ringing: str) -> np.ndarray:
    """Return a bw-mixed 1-D low-pass kernel; `constant_k` is the brick-wall variant."""
    offsets = np.arange(-_BANDWIDTH_RADIUS, _BANDWIDTH_RADIUS + 1, dtype=np.float32)
    if bw >= 1.0:
        return (offsets == 0).astype(np.float32)
    freqs = np.fft.rfftfreq(_FILTER_SAMPLES)
    cutoff = max(0.5 * bw, 1.0 / _FILTER_SAMPLES)
    if ringing == "constant_k":
        magnitude = (freqs <= cutoff).astype(np.float64)  # brick wall: strongest Gibbs lobes
    else:
        magnitude = 1.0 / np.sqrt(1.0 + (freqs / cutoff) ** (2 * _BUTTERWORTH_ORDER))
    taps = np.fft.irfft(magnitude, n=_FILTER_SAMPLES)
    proto = np.concatenate((taps[-_BANDWIDTH_RADIUS:], taps[: _BANDWIDTH_RADIUS + 1]))
    kernel = bw * (offsets == 0) + (1.0 - bw) * proto
    return (kernel / kernel.sum()).astype(np.float32)


def _bandwidth_filter(
    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
    bw: float,
    ringing: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Limit the horizontal bandwidth of Y, I and Q along the scan lines."""
    if bw >= 1.0:
        return planes
    kernel = _bandwidth_kernel(bw, ringing)
    return tuple(_blur_axis(p, kernel, 1) for p in planes)  # type: ignore[return-value]


def _head_switching(
    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
    amount: float,
    band_height: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Displace the bottom band along the scan lines, the shift growing into the band."""
    if amount <= 0.0 or band_height <= 0.0:
        return planes
    height, width = planes[0].shape
    rows = min(height, max(1, int(round(band_height * height))))
    base = min(float(amount), 1.0) * width * 0.5  # never a whole width: that is the identity
    shifts = [int(round(base * (index + 1) / rows)) for index in range(rows)]
    out = []
    for plane in planes:
        shifted = plane.copy()
        for index, shift in enumerate(shifts):
            if shift:
                row = height - rows + index
                shifted[row] = np.roll(plane[row], shift)
        out.append(shifted)
    return tuple(out)  # type: ignore[return-value]


def _tracking_noise(
    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
    amount: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Jitter each scan line horizontally by a seeded per-line shift."""
    if amount <= 0.0:
        return planes
    height, width = planes[0].shape
    max_shift = min(max(1, int(round(amount * width * 0.25))), max(1, width // 2))
    shifts = rng.integers(-max_shift, max_shift + 1, size=height).astype(np.intp)
    result = []
    for plane in planes:
        shifted = plane.copy()
        for row in np.nonzero(shifts)[0]:
            shifted[row] = np.roll(plane[row], int(shifts[row]))
        result.append(shifted)
    return tuple(result)  # type: ignore[return-value]


def _snow(y: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
    """Inject monochrome white noise into the luminance signal before demodulation."""
    if amount <= 0.0:
        return y
    delta = rng.standard_normal(y.shape).astype(np.float32) * np.float32(amount * 0.5)
    return y + delta


def _sharpen(y: np.ndarray, amount: float) -> np.ndarray:
    """Sharpen the luminance signal horizontally, like a VCR peaking circuit."""
    if amount <= 0.0:
        return y
    blurred = _blur_axis(y, _gaussian_kernel(1.0), 1)
    return y + np.float32(min(amount, 1.0)) * (y - blurred)


def _add_noise(
    y: np.ndarray,
    amount: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Add gaussian luminance noise scaled by amount."""
    if amount <= 0.0:
        return y
    delta = rng.standard_normal(y.shape).astype(np.float32) * np.float32(amount * 0.25)
    return y + delta


def _composite_noise(
    planes: tuple[np.ndarray, np.ndarray, np.ndarray],
    amount: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Add gaussian noise to every YIQ plane (the composite signal)."""
    if amount <= 0.0:
        return planes
    scale = np.float32(amount * 0.25)
    noisy = (p + rng.standard_normal(p.shape).astype(np.float32) * scale for p in planes)
    return tuple(noisy)  # type: ignore[return-value]


@register_effect("ntsc", "NTSC / VHS", _PARAMS)
def ntsc(img: Image, params: dict, rng: np.random.Generator) -> Image:
    """Emulate an NTSC / VHS composite signal chain and return the demodulated RGB."""
    source = _copy(img)
    streams = _stage_rngs(_generator(params, rng))
    y, i, q = _yiq(source)
    i, q = _chroma_lowpass(i, q, float(params["chroma_lowpass"]))
    i, q = _phase_noise(i, q, float(params["chroma_phase_noise"]), streams["chroma_phase"])
    y = _luma_smear(y, float(params["luma_smear"]))
    bw = float(params["bandwidth"]) * _TAPE_BANDWIDTH[str(params["tape_speed"])]
    y, i, q = _bandwidth_filter((y, i, q), bw, str(params["ringing"]))
    y = _add_noise(y, float(params["luma_noise"]), streams["luma_noise"])
    y, i, q = _composite_noise((y, i, q), float(params["composite_noise"]), streams["composite"])
    y = _snow(y, float(params["snow"]), streams["snow"])
    y, i, q = _head_switching(
        (y, i, q), float(params["head_switching"]), float(params["band_height"])
    )
    y, i, q = _tracking_noise((y, i, q), float(params["tracking_noise"]), streams["tracking"])
    y = _sharpen(y, float(params["sharpening"]))
    return _rgb((y, i, q))
