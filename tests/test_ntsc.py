"""Tests for the NTSC / VHS signal-emulation effect (L17, CONTRACT §16)."""

from __future__ import annotations

import numpy as np
import pytest

from lattice import effects  # noqa: F401  (registers the effect)
from lattice.effects import ntsc as ntsc_effect
from lattice.registry import get_effect, list_effects, resolve_params

NEUTRAL = {  # every parameter at its neutral value
    "seed": 0, "chroma_lowpass": 0.0, "chroma_phase_noise": 0.0, "luma_smear": 0.0,
    "luma_noise": 0.0, "composite_noise": 0.0, "bandwidth": 1.0, "ringing": "butterworth",
    "head_switching": 0.0, "band_height": 0.02, "tracking_noise": 0.0, "snow": 0.0,
    "sharpening": 0.0, "tape_speed": "sp",
}
SHAPES = ((1, 1), (1, 5), (5, 1), (37, 23), (64, 64))
AGGRESSIVE = {
    "chroma_lowpass": 0.8, "chroma_phase_noise": 0.7, "luma_smear": 0.6, "luma_noise": 0.5,
    "composite_noise": 0.5, "bandwidth": 0.4, "ringing": "constant_k", "head_switching": 0.8,
    "band_height": 0.6, "tracking_noise": 0.7, "snow": 0.8, "sharpening": 0.7, "tape_speed": "ep",
}
# Parameters that only act through a companion: `ringing` shapes the bandwidth
# kernel, so it needs a bandwidth below 1; `band_height` sizes the head-switching
# band, so it needs a displacement to size.
GATES: dict[str, dict] = {"ringing": {"bandwidth": 0.4}, "band_height": {"head_switching": 0.8}}
ZERO_STAGES = ("chroma_lowpass", "chroma_phase_noise", "luma_smear", "luma_noise",
               "composite_noise", "tracking_noise", "snow", "sharpening", "head_switching")


def _apply(img: np.ndarray, overrides: dict | None = None, seed: int = 0) -> np.ndarray:
    """Run the registered ntsc effect with resolved parameters and a seeded generator."""
    info = get_effect("ntsc")
    params = dict(NEUTRAL)
    params.update(overrides or {})
    params["seed"] = seed
    return info.fn(img.copy(), resolve_params(info.params, params), np.random.default_rng(seed))


def _random_image(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """Return a seeded random float32 (H, W, 3) image."""
    return np.random.default_rng(seed).random(shape + (3,), dtype=np.float32)


def _luma(rgb: np.ndarray) -> np.ndarray:
    """Return the NTSC luma plane of an RGB float32 array."""
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def _chroma_variance(rgb: np.ndarray) -> float:
    """Return a per-pixel chroma proxy variance (r-b and g-b differences)."""
    return float(((rgb[:, :, 0] - rgb[:, :, 2]).var() + (rgb[:, :, 1] - rgb[:, :, 2]).var()) / 2.0)


def _horizontal_gradient(rgb: np.ndarray) -> float:
    """Return the mean absolute horizontal luma gradient, a measure of fine detail."""
    return float(np.abs(np.diff(_luma(rgb), axis=1)).mean())


def _vertical_edge(width: int = 96, height: int = 8) -> np.ndarray:
    """Return an image with one vertical step edge, constant along every row."""
    edge = np.zeros((height, width, 3), dtype=np.float32)
    edge[:, width // 2 :] = 0.8
    return edge + np.float32(0.1)


def _edge_width(rgb: np.ndarray) -> int:
    """Return how many pixels of row 0 sit strictly between the two edge levels."""
    row = rgb[0, :, 0]
    return int(np.sum((row > 0.1 + 1e-4) & (row < 0.9 - 1e-4)))


def _grey(size: int = 24) -> np.ndarray:
    """Return a flat mid-grey image, where any chroma is noise the effect added."""
    return np.full((size, size, 3), 0.5, dtype=np.float32)


def _band_rows(height: int, band_height: float) -> int:
    """Return the number of bottom rows a band_height fraction covers."""
    return max(1, int(round(band_height * height)))


def _stage_apply(stage: str, planes: tuple, amount: float, rng: np.random.Generator) -> tuple:
    """Return the (Y, I, Q) planes after one private stage at amount, drawing from rng."""
    y, i, q = planes
    calls = {
        "chroma_lowpass": lambda: (y, *ntsc_effect._chroma_lowpass(i, q, amount)),
        "chroma_phase_noise": lambda: (y, *ntsc_effect._phase_noise(i, q, amount, rng)),
        "luma_smear": lambda: (ntsc_effect._luma_smear(y, amount), i, q),
        "luma_noise": lambda: (ntsc_effect._add_noise(y, amount, rng), i, q),
        "composite_noise": lambda: ntsc_effect._composite_noise((y, i, q), amount, rng),
        "tracking_noise": lambda: ntsc_effect._tracking_noise((y, i, q), amount, rng),
        "snow": lambda: (ntsc_effect._snow(y, amount, rng), i, q),
        "sharpening": lambda: (ntsc_effect._sharpen(y, amount), i, q),
        "head_switching": lambda: ntsc_effect._head_switching((y, i, q), amount, 0.2),
    }
    return calls[stage]()


def test_registers_an_ntsc_effect_with_neutral_defaults() -> None:
    """The effect is registered and listed, and its defaults are the neutral values."""
    info = get_effect("ntsc")
    assert (info.id, info.name) == ("ntsc", "NTSC / VHS")
    assert [spec.id for spec in info.params] == list(NEUTRAL)
    assert {spec.id: spec.default for spec in info.params} == NEUTRAL
    assert "ntsc" in {effect.id for effect in list_effects()}


def test_all_parameters_at_neutral_return_the_input() -> None:
    """Neutral parameters are the identity within 1/255, and the input is never written."""
    img = _random_image((48, 36))
    before = img.copy()
    assert np.allclose(_apply(img), img, atol=1.0 / 255.0)
    _apply(img, AGGRESSIVE)
    assert np.array_equal(img, before)


@pytest.mark.parametrize("param_id", [key for key in NEUTRAL if key != "seed"])
def test_every_parameter_changes_the_output_on_its_own(param_id: str) -> None:
    """Each parameter is live: moving it alone away from neutral changes the picture."""
    img, gate = _random_image((32, 32), seed=71), GATES.get(param_id, {})
    base = _apply(img, gate)
    spec = next(spec for spec in get_effect("ntsc").params if spec.id == param_id)
    if spec.kind == "choice":
        value = next(choice for choice in spec.choices if choice != spec.default)
    elif spec.kind == "int":
        assert spec.max is not None
        value = int(spec.max)
    else:
        value = 1.0 if spec.default != 1.0 else 0.0
    assert not np.allclose(_apply(img, {**gate, param_id: value}), base, atol=1e-4), param_id


@pytest.mark.parametrize("shape", SHAPES)
def test_every_size_keeps_its_shape_and_stays_in_range(shape: tuple[int, int]) -> None:
    """Shape and dtype are preserved on every size, and maximum parameters never raise."""
    out = _apply(_random_image(shape), AGGRESSIVE)
    assert (out.shape, out.dtype) == (shape + (3,), np.float32)
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_noise_is_deterministic_and_both_seed_inputs_drive_it() -> None:
    """Same (seed, rng) reproduces the noise; changing either one alone changes it."""
    img = _random_image((24, 24))
    noisy = {"snow": 0.7, "luma_noise": 0.5}
    assert np.array_equal(_apply(img, noisy, seed=5), _apply(img, noisy, seed=5))
    assert not np.array_equal(_apply(img, noisy, seed=5), _apply(img, noisy, seed=6))
    info = get_effect("ntsc")
    params = resolve_params(info.params, {**NEUTRAL, "snow": 0.6, "seed": 11})
    first = info.fn(img.copy(), params, np.random.default_rng(0))
    assert np.array_equal(first, info.fn(img.copy(), params, np.random.default_rng(0)))
    assert not np.array_equal(first, info.fn(img.copy(), params, np.random.default_rng(99)))
    other = resolve_params(info.params, {**NEUTRAL, "snow": 0.6, "seed": 12})
    assert not np.array_equal(first, info.fn(img.copy(), other, np.random.default_rng(0)))


def test_each_stochastic_stage_has_its_own_stream() -> None:
    """The stochastic stages get distinct child generators; enabling one leaves the others alone."""
    streams = ntsc_effect._stage_rngs(ntsc_effect._generator({"seed": 4}, np.random.default_rng(8)))
    assert tuple(streams) == ntsc_effect._STAGES
    before = {name: gen.bit_generator.state["state"]["state"] for name, gen in streams.items()}
    assert len(set(before.values())) == len(before)
    streams["snow"].standard_normal(64)
    after = {name: gen.bit_generator.state["state"]["state"] for name, gen in streams.items()}
    assert [name for name in streams if before[name] != after[name]] == ["snow"]
    img = _grey()
    alone = _apply(img, {"snow": 0.5}) - img
    both = _apply(img, {"snow": 0.5, "chroma_phase_noise": 0.6})
    both = both - _apply(img, {"chroma_phase_noise": 0.6})
    assert float(np.abs(alone - both).max()) < 1e-6


def test_bandwidth_smears_a_vertical_edge_along_the_scan_lines() -> None:
    """`bandwidth < 1` blurs along axis 1; a horizontal edge has no detail to lose."""
    out = _apply(_vertical_edge(), {"bandwidth": 0.3})
    assert _edge_width(out) >= 6
    assert float(np.abs(out - out[0:1]).max()) < 1e-5  # every row smeared alike: axis 1
    edge = np.zeros((32, 32, 3), dtype=np.float32)
    edge[16:] = 0.8
    assert float(np.abs(_apply(edge, {"bandwidth": 0.3}) - edge).max()) < 1e-4
    img = _random_image((32, 64), seed=21)
    widths = (1.0, 0.8, 0.5, 0.2)
    gradients = [_horizontal_gradient(_apply(img, {"bandwidth": bw})) for bw in widths]
    assert gradients == sorted(gradients, reverse=True), gradients
    assert gradients[0] > gradients[-1] * 2.0
    assert float(np.abs(_apply(img, {"bandwidth": 0.999}) - _apply(img)).max()) < 5e-3


def test_ringing_overshoots_a_step_edge() -> None:
    """Both modes overshoot and undershoot a step, and they are different responses."""
    rows = {
        mode: _apply(_vertical_edge(), {"bandwidth": 0.3, "ringing": mode})[0, :, 0]
        for mode in ("butterworth", "constant_k")
    }
    for mode, row in rows.items():
        assert float(row.max()) > 0.9 + 1e-3, (mode, float(row.max()))
        assert float(row.min()) < 0.1 - 1e-3, (mode, float(row.min()))
    assert float(np.abs(rows["butterworth"] - rows["constant_k"]).max()) > 1e-2


@pytest.mark.parametrize(("amount", "band_height"), [(0.6, 0.25), (1.0, 0.1)])
def test_head_switching_displaces_only_the_bottom_band(amount: float, band_height: float) -> None:
    """Head switching moves the bottom band only; the maximum is not the identity."""
    img = _random_image((64, 64))
    rows = _band_rows(img.shape[0], band_height)
    base = _apply(img, {"head_switching": 0.0, "band_height": band_height})
    out = _apply(img, {"head_switching": amount, "band_height": band_height})
    assert float(np.abs(out[:-rows] - base[:-rows]).max()) < 1e-6
    assert float(np.abs(out[-rows:] - base[-rows:]).max()) > 0.1


def test_head_switching_grows_towards_the_bottom_edge() -> None:
    """The displacement is a skew: the last band row moves further than the first one."""
    img = _random_image((64, 64), seed=31)
    rows = _band_rows(img.shape[0], 0.1)
    base = _apply(img, {"head_switching": 0.0, "band_height": 0.1})
    out = _apply(img, {"head_switching": 1.0, "band_height": 0.1})

    def shift(row: int) -> int:
        """Return the horizontal roll that best explains one output row."""
        return min(range(0, img.shape[1] // 2 + 1),
                   key=lambda s: float(np.abs(out[row] - np.roll(base[row], s, axis=0)).max()))

    shifts = [shift(row) for row in range(img.shape[0] - rows, img.shape[0])]
    assert shifts == sorted(shifts), shifts
    assert shifts[-1] > shifts[0]


def test_band_height_is_a_parameter_of_the_displaced_band() -> None:
    """A bigger band height moves a taller bottom slice; the rows between stay intact."""
    img = _random_image((64, 64))
    small_rows, large_rows = _band_rows(64, 0.2), _band_rows(64, 0.5)
    assert large_rows > small_rows
    steps = {"head_switching": 0.8, "band_height": 0.0}
    base, small = _apply(img, steps), _apply(img, {**steps, "band_height": 0.2})
    large = _apply(img, {**steps, "band_height": 0.5})
    between = slice(64 - large_rows, 64 - small_rows)
    assert float(np.abs(small[between] - base[between]).max()) < 1e-6
    assert float(np.abs(large[between] - base[between]).max()) > 0.1


def test_chroma_lowpass_reduces_chroma_variance_keeps_luma() -> None:
    """Low-passing chroma cuts chroma variance while luma variance stays within 5%."""
    img = _random_image((64, 64), seed=3)
    out = _apply(img, {"chroma_lowpass": 0.8})
    assert _chroma_variance(out) < _chroma_variance(img)
    in_luma, out_luma = _luma(img), _luma(out)
    ratio = float(out_luma.var() / in_luma.var()) if in_luma.var() > 0 else 1.0
    assert abs(ratio - 1.0) <= 0.05
    # The luma smear, by contrast, is the stage that lowers luma variance.
    assert float(_luma(_apply(img, {"luma_smear": 0.8})).var()) < float(in_luma.var())


def test_chroma_phase_noise_rotates_the_chroma_planes_only() -> None:
    """Phase noise changes the chroma while the luma plane stays put."""
    img = _random_image((32, 32), seed=5)
    base = _apply(img)
    out = _apply(img, {"chroma_phase_noise": 0.8})
    assert float(np.abs(out - base).max()) > 0.1
    assert float(np.abs(_luma(out) - _luma(base)).max()) < 0.15


def test_luma_noise_adds_monochrome_noise() -> None:
    """`luma_noise` raises luma variance and leaves the chroma planes equal."""
    img = _grey()
    out = _apply(img, {"luma_noise": 0.5})
    delta = out - img
    assert float(_luma(out).var()) > float(_luma(img).var()) * 1.5
    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) < 1e-6


def test_composite_noise_adds_noise_to_every_plane() -> None:
    """`composite_noise` is chromatic: it moves Y, I and Q, so R and G drift apart."""
    img = _grey()
    delta = _apply(img, {"composite_noise": 0.5}) - img
    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) > 0.1


def test_snow_is_injected_in_the_signal_domain_as_monochrome_noise() -> None:
    """Snow is luma noise before demodulation: it is grey, not coloured speckle."""
    img = _grey()
    delta = _apply(img, {"snow": 0.3}) - img
    assert float(delta[:, :, 0].std()) > 0.02
    assert float(np.abs(delta[:, :, 0] - delta[:, :, 1]).max()) < 1e-6
    assert float(np.abs(delta[:, :, 0] - delta[:, :, 2]).max()) < 1e-6


def test_sharpening_raises_the_luma_gradient_without_touching_chroma() -> None:
    """Sharpening is a luma peaking operation: detail up, chroma bit-identical."""
    stripes = np.zeros((16, 96, 3), dtype=np.float32)
    stripes[:, ::6] = 0.65
    stripes[:, 3::6] = 0.65
    stripes += np.float32(0.15)
    base = _apply(stripes)
    out = _apply(stripes, {"sharpening": 0.6})
    assert _horizontal_gradient(out) > _horizontal_gradient(base) * 1.2
    assert float(np.abs(out[:, :, 0] - out[:, :, 1]).max()) < 1e-5


@pytest.mark.parametrize("stage", ZERO_STAGES)
def test_each_stage_is_bit_identical_at_its_neutral_value(stage: str) -> None:
    """Called with amount 0 every stage returns its input untouched, and is live above it."""
    rng = np.random.default_rng(1)
    y, i, q = (rng.random((16, 16), dtype=np.float32) for _ in range(3))
    planes = (y, i - np.float32(0.5), q - np.float32(0.5))
    neutral = _stage_apply(stage, planes, 0.0, np.random.default_rng(4))
    for before, after in zip(planes, neutral, strict=True):
        assert np.array_equal(before, after), stage
    live = _stage_apply(stage, planes, 0.5, np.random.default_rng(4))
    assert any(not np.array_equal(b, a) for b, a in zip(planes, live, strict=True)), stage


def test_tape_speed_narrows_the_bandwidth_in_order() -> None:
    """sp keeps full detail, lp less, ep least; the smeared edge widens in that order."""
    img = _random_image((32, 64), seed=41)
    sp, lp, ep = (_horizontal_gradient(_apply(img, {"tape_speed": s})) for s in ("sp", "lp", "ep"))
    assert sp > lp > ep, (sp, lp, ep)
    widths = [_edge_width(_apply(_vertical_edge(), {"tape_speed": s})) for s in ("sp", "lp", "ep")]
    assert widths[0] == 0, widths  # sp multiplies the bandwidth by 1.0: the edge stays sharp
    assert widths[1] > 0 and widths[2] > widths[1], widths


def test_tracking_noise_shifts_whole_scan_lines_horizontally() -> None:
    """Every row of the output is a horizontal roll of the same row of the base image."""
    img = _random_image((32, 32), seed=51)
    base = _apply(img)
    out = _apply(img, {"tracking_noise": 0.6})
    moved = 0
    for row in range(img.shape[0]):
        best = min(
            float(np.abs(out[row] - np.roll(base[row], s, axis=0)).max()) for s in range(-16, 17)
        )
        assert best < 1e-3, (row, best)
        moved += not np.allclose(out[row], base[row])
    assert moved > img.shape[0] // 2


def test_each_preset_produces_a_distinct_output_on_the_same_input() -> None:
    """The six presets differ from each other and from the input by a real margin."""
    assert len(ntsc_effect.PRESET_NAMES) == 6
    assert set(ntsc_effect.PRESET_NAMES) == set(ntsc_effect.PRESETS)
    img = _random_image((48, 48), seed=11)
    outputs = [_apply(img, ntsc_effect.PRESETS[name]) for name in ntsc_effect.PRESET_NAMES]
    for index, name in enumerate(ntsc_effect.PRESET_NAMES):
        assert float(np.abs(outputs[index] - img).mean()) > 0.01, name
        for other in range(index + 1, len(ntsc_effect.PRESET_NAMES)):
            difference = float(np.abs(outputs[index] - outputs[other]).mean())
            assert difference > 0.02, (name, ntsc_effect.PRESET_NAMES[other], difference)


def test_preset_returns_a_copy_and_rejects_an_unknown_name() -> None:
    """`preset` hands back a fresh dict, and an unknown name raises KeyError naming it."""
    overrides = ntsc_effect.preset("Static")
    assert overrides == ntsc_effect.PRESETS["Static"]
    overrides["snow"] = 0.0
    assert ntsc_effect.PRESETS["Static"]["snow"] == 0.6
    with pytest.raises(KeyError, match="no such tape"):
        ntsc_effect.preset("no such tape")


def test_simple_mode_exposes_four_parameters_and_advanced_mode_all_of_them() -> None:
    """Simple is four real parameters; the advanced toggle reveals all fourteen, same objects."""
    simple = ntsc_effect.params_for_mode("simple")
    advanced = ntsc_effect.params_for_mode("advanced")
    assert len(simple) == 4
    assert tuple(spec.id for spec in simple) == ntsc_effect.SIMPLE_PARAM_IDS
    assert len(set(ntsc_effect.SIMPLE_PARAM_IDS)) == 4
    assert tuple(spec.id for spec in advanced) == tuple(NEUTRAL)
    assert len(advanced) == 14 > len(simple)
    by_id = {spec.id: spec for spec in advanced}
    for spec in simple:
        assert by_id[spec.id] is spec
    assert ntsc_effect.MODES == ("simple", "advanced")
    with pytest.raises(ValueError, match="simple"):
        ntsc_effect.params_for_mode("expert")


def test_simple_mode_parameters_reach_the_effect() -> None:
    """Each simple-mode slider really changes the output on its own."""
    img = _random_image((32, 32), seed=61)
    base = _apply(img)
    for param_id in ntsc_effect.SIMPLE_PARAM_IDS:
        value = 0.4 if param_id == "bandwidth" else 0.5
        assert not np.allclose(_apply(img, {param_id: value}), base, atol=1e-4), param_id


def test_every_parameter_label_is_a_distinct_honest_catalogue_key() -> None:
    """Each label names its own parameter: no two share one, and LABEL_NOTES covers them."""
    info = get_effect("ntsc")
    labels = [spec.label for spec in info.params]
    assert len(set(labels)) == len(labels), labels
    assert set(ntsc_effect.LABEL_NOTES) == set(NEUTRAL)
    assert all(ntsc_effect.LABEL_NOTES[spec.id] for spec in info.params)
