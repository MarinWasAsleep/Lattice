# Reviewer prompt template — Lattice harness 0.1

Placeholders in `{{ }}` are filled by the orchestrator. Everything above `{{TASK_CARD}}` is the
stable prefix.

---

You are reviewing one task of the Lattice project: a family of free, open-source image-transformation
applications sharing one engine, each running standalone and also plugging into the ArtCraft suite.
You see the task card, the contract sections it must satisfy, the git diff, the gate results and the
coder's notes. You do not see the rest of the repository, and you do not need to.

The dithering application is frozen and shipped (harness 1.1 feature-complete: 18 cards T17-T34,
~1212 test cases at wave-7 close; its human checkpoints H6-H9 are the 1.1 harness's business),
with a public release. Your job is to decide whether this diff can join it.

WHAT TO CHECK, IN THIS ORDER
1. **Contract conformance.** Names, signatures, dtypes, ranges, ordering, error types. A deviation
   from the contract is a blocker even if the tests pass.
2. **Regression.** Does anything that worked before behave differently? Gate G7 (core regression)
   exists for this. A regression is an E6 deviation and a blocker unless the card explicitly asks
   for the change.
3. **The abstraction holds.** Gate G8 checks that every registered `CellRenderer` satisfies §3. Read
   the invariant list and check the diff against each one, not just the gate result. A renderer that
   mutates its input, or whose output size is off by one, is a blocker.
4. **No abstraction leak.** Does `lattice_core` reference an application? Does an application import
   from another application? That is an E8 deviation and a blocker.
5. **No host coupling.** Does the application still work with no ArtCraft running? A missing token
   file, a refused connection or an absent host must be a normal state. That is an E9 deviation and a
   blocker.
6. **Test quality.** Do the tests actually fail on the old code? A test that passes before and after
   the change proves nothing. Look for assertions that restate the implementation, tests that would
   pass with the feature removed, and missing edge cases named in `accept`.
7. **Correctness of the maths.** For renderer and effect cards, check the formulas against the
   contract, not against intuition. Off-by-one in a kernel, a missing normalisation, a wrong colour
   space, a mask applied in the wrong order.
8. **Product quality** (cards L10, L12, L20, L21 only). Is the control discoverable? Does the default
   surprise? Does the message say what to do next? A task can pass every test and still be an E7.
9. **Hygiene.** File length, function length, typing, docstrings, no dead code, no commented-out
   blocks, no debug prints.

SEVERITY
- **blocker**: wrong result, contract violation, regression, crash, data loss, abstraction leak,
  host coupling.
- **major**: missing acceptance item, test that cannot fail, wrong default, misleading message.
- **minor**: style, naming, a docstring that lies.

VERDICT
- `PASS` — no blocker, no major. Minors are listed but do not block.
- `FIX` — at least one blocker or major. The coder gets one more cycle with your findings.
- `ESCALATE` — the task cannot be done as specified, or the fix needs a contract change. Name the
  deviation class (E2, E4, E6, E7, E8, E9).

OUTPUT FORMAT, nothing else:
```json
{
  "verdict": "PASS | FIX | ESCALATE",
  "findings": [
    {"severity": "blocker|major|minor", "file": "...", "line": 0,
     "what": "...", "why": "...", "fix": "..."}
  ],
  "regression": "none | <what changed vs the frozen behaviour>",
  "renderer_invariants": "all six hold | <which one fails and how>",
  "tests_that_cannot_fail": ["..."],
  "notes": "<≤ 5 lines>"
}
```

CONTRACT EXCERPTS (version {{CONTRACT_VERSION}})
{{CONTRACT_SECTIONS}}

TASK CARD
{{TASK_CARD}}

GATE RESULTS
{{GATE_SUMMARY}}

DIFF
{{DIFF}}

CODER NOTES AND DEVIATIONS
{{CODER_BLOCKS}}



CONTRACT EXCERPTS (version 0.1.0)


## §12 Feedback buffer

The mechanism that makes a glitch tool an instrument rather than a filter.

```
f(n) = decay * T(f(n-1)) + input
```

- `decay` in `[0, 0.99]`. Values at or above 1 are rejected at validation.
- `T` is one of: `translate`, `rotate`, `scale`, `displace`, `identity`. Composable.
- The buffer is normalised per frame so it cannot diverge.
- Stability test: 200 iterations on a fixed input, no NaN, no value outside `[0, 1]`, and the mean
  converges.
- Options: `decay`, `transform`, `amount`, `iterations` (1..8), `blend` (`add` | `max` | `screen`).



## §20 Non-goals

Explicitly out of scope for this contract. Adding any of these requires a new contract version.

- Full video and timeline editing. A shared **N-image loop** (GIF/APNG, card L-LOOP) is in
  scope: variation of seed, offset or feedback iterations across N frames; no timeline, no video.
- Physical-media output (LEGO, beads, cross-stitch, embroidery).
- Print separations (CMYK plates, riso, spot inks, trapping, dot gain). **Assumed bet,
  documented, no promise** (P2, decided 2026-11-16): separations and full animation are
  explicitly out and not foreshadowed in any contract version yet.
- Network access in the core. Palette import is file-based or pasted hex.
- Any dependency beyond numpy, numba, Pillow, and PySide6 under the `[ui]` extra.



CONTRACT EXCERPTS (version 1.1)


## §21 Animation and video

New module `dithercraft/core/animation.py` and `dithercraft/export/video.py`.

```python
def render_sequence(frames: list[Image], spec: PipelineSpec, *, stable: bool = True) -> list[RGB8]
def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None
def export_video(frames: list[RGB8], path: Path, *, fps: int = 12) -> bool
```

- `stable = True` is the temporal-stability mode: ordered matrices are anchored to the canvas (not
  to the frame), the palette is resolved once on the first frame and reused, and the error of frame
  n is not carried into frame n+1 (carrying is explicitly out of scope for 1.1).
- `export_gif` uses Pillow only.
- `export_video` returns `False` and writes nothing when no ffmpeg binary can be found; it never
  raises for a missing ffmpeg. It returns `True` on success.
- The ffmpeg binary comes from the `imageio-ffmpeg` dependency, which ships one inside the wheel, so
  `pip install -r requirements.txt` is enough and no system step is needed. A system ffmpeg is the
  fallback when the dependency is absent. This is the one dependency 1.1 adds; the 1.0 rule "no new
  dependency" is amended here, by human decision, and the PyInstaller bundle ships the binary too.
- No other new dependency. ffmpeg is still invoked as a subprocess, never linked.



TASK CARD
### L-LOOP · N-image loop (GIF/APNG)
- wave: 2 · deps: L20 · executor: OMH capable · review: light · size: S
- owns: `lattice_core/animation.py`, `tests/test_animation_loop.py`
- context: §12 §20 (P4, decided 2026-11-16)
- spec: move `core/animation.py` from Lattice Dither into `lattice_core/animation.py` and
  generalise it into a shared N-image loop: render N frames by varying seed, offset, or
  feedback iterations, emit GIF and APNG. Consumed by the Glitch CLI
  (`render --frames N --format gif|apng`) and by the L20 shell's export. No timeline, no
  video (§20). Lattice Dither's CLI keeps its exports as-is.
- accept:
  - N frames vary only the declared axis (seed/offset/itérations) and are identical otherwise.
  - GIF and APNG open with Pillow and have exactly N frames.
  - `animation.py` sits in lattice_core and imports no application module.
  - the Dither 1.1 exports (video path untouched) still pass their existing tests.

---


GATE RESULTS
GATES (orchestrateur, rejoués) :
- G1 owns : seuls lattice_core/animation.py et tests/test_animation_loop.py sont créés (vérifié, lattice_dither/ intact).
- G2 : 22 passed (tests/test_animation_loop.py, 0,3 s) ; non-régression Dither : 18 passed (tests/test_animation.py — chemin vidéo 1.1 intact).
- G3 ruff (2 fichiers) : All checks passed.
CONTEXTE : carte size S, relecture LIGHT (cycle 1). Le codeur déclare 3 E1 (sémantique des axes : seed = spec.seed+step*i,
offset = np.roll de step*i, iterations = 1er effet feedback activé saturé à 8 ; APNG duration ms/loop/disposal ; doublon
temporaire core/app assumé, résorption par carte dédiée). À VÉRIFIER : les 4 accepts (variation mono-axe réelle, GIF/APNG
N frames, aucun import applicatif, exports Dither 1.1 intacts — rejoué par l'orchestrateur), l'absence de timeline/vidéo (§20),
et l'identité du déplacement (render_sequence identique au module app ?).

DIFF (cumulatif HEAD -> arbre)
diff --git a/lattice_core/animation.py b/lattice_core/animation.py
new file mode 100644
index 0000000..30b50b9
--- /dev/null
+++ b/lattice_core/animation.py
@@ -0,0 +1,149 @@
+"""Shared N-image loop: render N frames varying one axis, then export GIF or APNG.
+
+``render_sequence`` is the 1.1 animation export moved into the core without behavioural
+change (§21). ``render_loop`` generalises it: it renders N frames from one source while
+varying only the declared axis — ``seed``, ``offset`` (a horizontal pixel shift) or
+``iterations`` (the feedback buffer iteration count) — and keeps everything else fixed.
+Stable mode resolves the palette once, on the first frame, so colours cannot flicker.
+"""
+
+from __future__ import annotations
+
+from dataclasses import replace
+from pathlib import Path
+
+import numpy as np
+from PIL import Image as PILImage
+
+from lattice_core.pipeline import (
+    PipelineSpec,
+    prepare_image,
+    render_with_palette,
+    resolve_palette,
+)
+from lattice_core.types import RGB8, Image
+
+AXES = ("seed", "offset", "iterations")
+MAX_ITERATIONS = 8
+
+
+def render_sequence(
+    frames: list[Image], spec: PipelineSpec, *, stable: bool = True
+) -> list[RGB8]:
+    """Render frames through spec, resolving the palette once when stable."""
+    return _render(frames, [spec] * len(frames), stable)
+
+
+def render_loop(
+    src: Image,
+    spec: PipelineSpec,
+    *,
+    count: int,
+    axis: str = "seed",
+    stable: bool = True,
+    step: int = 1,
+) -> list[RGB8]:
+    """Render count frames from src, varying only axis; other spec fields stay fixed."""
+    if axis not in AXES:
+        raise ValueError(f"unknown animation axis: {axis!r}, expected one of {AXES}")
+    if count < 0:
+        raise ValueError(f"count must be >= 0, got {count}")
+    shift = int(step)
+    base = _iterations_base(spec) if axis == "iterations" else 0
+    pairs = [
+        _varied(src, spec, axis, index, shift, base) for index in range(count)
+    ]
+    return _render([pair[0] for pair in pairs], [pair[1] for pair in pairs], stable)
+
+
+def export_gif(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
+    """Write frames to path as an animated GIF, using Pillow only."""
+    duration = _check(frames, fps)
+    images = [_pil(frame) for frame in frames]
+    images[0].save(
+        Path(path),
+        format="GIF",
+        save_all=True,
+        append_images=images[1:],
+        duration=duration,
+        loop=int(loop),
+        optimize=False,
+    )
+
+
+def export_apng(frames: list[RGB8], path: Path, *, fps: int = 12, loop: int = 0) -> None:
+    """Write frames to path as an animated APNG, using Pillow only."""
+    duration = _check(frames, fps)
+    images = [_pil(frame) for frame in frames]
+    images[0].save(
+        Path(path),
+        format="PNG",
+        save_all=True,
+        append_images=images[1:],
+        duration=duration,
+        loop=int(loop),
+        disposal=2,
+    )
+
+
+def _render(frames: list[Image], specs: list[PipelineSpec], stable: bool) -> list[RGB8]:
+    """Render frames against parallel specs, pinning one palette when stable."""
+    if not frames:
+        return []
+    if stable:
+        palette = resolve_palette(specs[0].palette, prepare_image(frames[0], specs[0]))
+        return [
+            render_with_palette(frame, spec, palette)
+            for frame, spec in zip(frames, specs, strict=True)
+        ]
+    return [
+        render_with_palette(frame, spec, resolve_palette(spec.palette, prepare_image(frame, spec)))
+        for frame, spec in zip(frames, specs, strict=True)
+    ]
+
+
+def _varied(
+    src: Image, spec: PipelineSpec, axis: str, index: int, step: int, base: int
+) -> tuple[Image, PipelineSpec]:
+    """Return the source and spec of frame index with only axis changed."""
+    if axis == "seed":
+        return src, replace(spec, seed=int(spec.seed) + step * index)
+    if axis == "offset":
+        return np.roll(src, step * index, axis=1), spec
+    return src, _with_iterations(spec, min(MAX_ITERATIONS, base + step * index))
+
+
+def _iterations_base(spec: PipelineSpec) -> int:
+    """Return the iteration count declared by the first enabled feedback effect."""
+    for effect in (*spec.pre_effects, *spec.post_effects):
+        if effect.effect_id == "feedback" and effect.enabled:
+            return max(1, int(effect.params.get("iterations", 1)))
+    return 1
+
+
+def _with_iterations(spec: PipelineSpec, value: int) -> PipelineSpec:
+    """Return spec with every enabled feedback effect set to value iterations."""
+    def bump(effect):
+        if effect.effect_id != "feedback" or not effect.enabled:
+            return effect
+        return replace(effect, params={**effect.params, "iterations": value})
+
+    return replace(
+        spec,
+        pre_effects=[bump(effect) for effect in spec.pre_effects],
+        post_effects=[bump(effect) for effect in spec.post_effects],
+    )
+
+
+def _check(frames: list[RGB8], fps: int) -> int:
+    """Validate the sequence and return the frame duration in milliseconds."""
+    if not frames:
+        raise ValueError("cannot export an empty sequence")
+    if int(fps) < 1:
+        raise ValueError(f"fps must be >= 1, got {fps}")
+    return int(round(1000.0 / int(fps)))
+
+
+def _pil(frame: RGB8) -> PILImage.Image:
+    """Return one frame as a Pillow RGB image."""
+    return PILImage.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB")
diff --git a/tests/test_animation_loop.py b/tests/test_animation_loop.py
new file mode 100644
index 0000000..fac75a5
--- /dev/null
+++ b/tests/test_animation_loop.py
@@ -0,0 +1,265 @@
+"""Tests for the shared N-image loop and its GIF/APNG exports (card L-LOOP)."""
+
+from __future__ import annotations
+
+import ast
+from dataclasses import replace
+from pathlib import Path
+
+import numpy as np
+import pytest
+from PIL import Image as PILImage
+
+import lattice_core.animation as animation
+import lattice_core.dither  # noqa: F401  (registers the algorithms)
+import lattice_core.effects  # noqa: F401  (registers the effects)
+from lattice_core.animation import (
+    AXES,
+    export_apng,
+    export_gif,
+    render_loop,
+    render_sequence,
+)
+from lattice_core.pipeline import EffectInstance, PaletteSpec, PipelineSpec, render
+from lattice_core.types import RGB8, Image
+
+BW = ["#000000", "#FFFFFF"]
+
+
+def _spec(**overrides: object) -> PipelineSpec:
+    """Return a deterministic two-colour spec with the requested overrides."""
+    base: dict = {
+        "algorithm_id": "bayer_4",
+        "palette": PaletteSpec(source="custom", colors=BW),
+    }
+    base.update(overrides)
+    return PipelineSpec(**base)
+
+
+def _feedback(seed: int = 7) -> PipelineSpec:
+    """Return a spec whose post-effect feedback is seeded and spatially displaced."""
+    effect = EffectInstance(
+        "feedback",
+        {"decay": 0.5, "transform": "displace", "amount": 4.0, "iterations": 1},
+    )
+    return _spec(seed=seed, post_effects=[effect])
+
+
+def _src(size: int = 16) -> Image:
+    """Return a grey image with a bright band, so horizontal shifts are visible."""
+    img = np.full((size, size, 3), 0.25, dtype=np.float32)
+    img[:, :4] = 0.75
+    return img
+
+
+def _gradient(size: int = 16) -> Image:
+    """Return a horizontal ramp whose columns are all distinct."""
+    ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)
+    return np.ascontiguousarray(np.broadcast_to(ramp[None, :, None], (size, size, 3)))
+
+
+def _rgb_frames(count: int = 5) -> list[RGB8]:
+    """Return count distinct uint8 frames, ready for an image writer."""
+    frames = []
+    for index in range(count):
+        frame = np.zeros((16, 16, 3), dtype=np.uint8)
+        frame[:, index * 3 : index * 3 + 3] = 255
+        frames.append(frame)
+    return frames
+
+
+def _with_iterations(spec: PipelineSpec, value: int) -> PipelineSpec:
+    """Build the reference spec used to check the iterations axis independently."""
+    effects = [
+        replace(effect, params={**effect.params, "iterations": value})
+        if effect.effect_id == "feedback"
+        else effect
+        for effect in spec.post_effects
+    ]
+    return replace(spec, post_effects=effects)
+
+
+def test_render_sequence_is_the_moved_dither_function() -> None:
+    """The core function reproduces the Dither 1.1 export on the same input."""
+    from lattice_dither.core.animation import render_sequence as dither_sequence
+
+    frames = [_src() for _ in range(3)]
+    for core, dither in zip(
+        render_sequence(frames, _spec()), dither_sequence(frames, _spec()), strict=True
+    ):
+        assert np.array_equal(core, dither)
+    assert render_sequence([], _spec()) == []
+
+
+def test_seed_axis_changes_only_seed() -> None:
+    """Each frame equals an independent render whose seed alone was incremented."""
+    spec = _feedback()
+    out = render_loop(_src(), spec, count=4, axis="seed")
+    assert len(out) == 4
+    for index, frame in enumerate(out):
+        expected = render(_src(), replace(spec, seed=spec.seed + index))
+        assert np.array_equal(frame, expected)
+    assert any(not np.array_equal(out[0], other) for other in out[1:])
+
+
+def test_iterations_axis_changes_only_feedback_iterations() -> None:
+    """Each frame equals a render whose feedback iteration count alone was incremented."""
+    spec = _feedback()
+    out = render_loop(_src(), spec, count=4, axis="iterations")
+    assert len(out) == 4
+    for index, frame in enumerate(out):
+        expected = render(_src(), _with_iterations(spec, 1 + index))
+        assert np.array_equal(frame, expected)
+    assert any(not np.array_equal(out[0], other) for other in out[1:])
+
+
+def test_iterations_axis_saturates_at_eight() -> None:
+    """Feedback iterations never exceed the contract maximum of eight."""
+    spec = _feedback()
+    out = render_loop(_src(), spec, count=11, axis="iterations")
+    assert len(out) == 11
+    assert all(np.array_equal(out[7], frame) for frame in out[8:])
+
+
+def test_offset_axis_changes_only_a_horizontal_shift() -> None:
+    """Each frame equals a render of the source rolled by the frame index."""
+    spec = _spec()
+    src = _gradient()
+    out = render_loop(src, spec, count=4, axis="offset")
+    for index, frame in enumerate(out):
+        assert np.array_equal(frame, render(np.roll(src, index, axis=1), spec))
+    assert not np.array_equal(out[0], out[1])
+
+
+def test_offset_axis_honours_the_step() -> None:
+    """The step multiplies the horizontal shift without touching the spec."""
+    spec = _spec()
+    src = _gradient()
+    out = render_loop(src, spec, count=3, axis="offset", step=2)
+    for index, frame in enumerate(out):
+        assert np.array_equal(frame, render(np.roll(src, 2 * index, axis=1), spec))
+
+
+def test_loop_is_deterministic_and_does_not_mutate_its_inputs() -> None:
+    """Two identical calls render identical bytes and leave spec and src untouched."""
+    spec = _feedback()
+    src = _src()
+    first = render_loop(src, spec, count=4, axis="seed")
+    second = render_loop(src, spec, count=4, axis="seed")
+    assert all(np.array_equal(a, b) for a, b in zip(first, second, strict=True))
+    assert spec.seed == 7
+    assert spec.post_effects[0].params["iterations"] == 1
+    assert np.array_equal(src, _src())
+
+
+def test_unstable_loop_resolves_the_palette_per_frame(monkeypatch) -> None:
+    """stable=False re-resolves the palette once for every frame."""
+    calls: list[int] = []
+    real = animation.resolve_palette
+
+    def counting(spec, img):
+        calls.append(1)
+        return real(spec, img)
+
+    monkeypatch.setattr(animation, "resolve_palette", counting)
+    render_loop(_src(), _spec(), count=3, axis="offset", stable=False)
+    assert len(calls) == 3
+
+
+def test_unknown_axis_and_negative_count_are_rejected() -> None:
+    """An undeclared axis and a negative count raise ValueError; zero is empty."""
+    with pytest.raises(ValueError, match="axis"):
+        render_loop(_src(), _spec(), count=3, axis="time")
+    with pytest.raises(ValueError, match="count"):
+        render_loop(_src(), _spec(), count=-1)
+    assert render_loop(_src(), _spec(), count=0) == []
+
+
+def test_axis_constants_are_the_three_declared_axes() -> None:
+    """Only seed, offset and feedback iterations are variation axes."""
+    assert AXES == ("seed", "offset", "iterations")
+
+
+def test_gif_has_exactly_n_frames(tmp_path: Path) -> None:
+    """A GIF written from N frames reopens with exactly N frames."""
+    target = tmp_path / "clip.gif"
+    export_gif(_rgb_frames(), target, fps=10)
+    with PILImage.open(target) as written:
+        assert written.format == "GIF"
+        assert written.n_frames == 5
+        assert written.info["duration"] == 100
+
+
+def test_apng_has_exactly_n_frames(tmp_path: Path) -> None:
+    """An APNG written from N frames reopens with exactly N frames."""
+    target = tmp_path / "clip.png"
+    export_apng(_rgb_frames(), target, fps=10)
+    with PILImage.open(target) as written:
+        assert written.format == "PNG"
+        assert written.n_frames == 5
+        assert written.info["duration"] == 100
+
+
+@pytest.mark.parametrize("writer", [export_gif, export_apng])
+def test_exports_honour_the_loop_count(tmp_path: Path, writer) -> None:
+    """Both writers pass the loop count into the file."""
+    target = tmp_path / "clip"
+    writer(_rgb_frames(3), target, fps=10, loop=3)
+    with PILImage.open(target) as written:
+        assert written.info["loop"] == 3
+        assert written.n_frames == 3
+
+
+@pytest.mark.parametrize("writer", [export_gif, export_apng])
+def test_exports_reject_an_empty_sequence(tmp_path: Path, writer) -> None:
+    """An empty sequence is rejected rather than written as a broken file."""
+    with pytest.raises(ValueError, match="empty"):
+        writer([], tmp_path / "clip", fps=10)
+
+
+@pytest.mark.parametrize("writer", [export_gif, export_apng])
+def test_exports_reject_a_bad_fps(tmp_path: Path, writer) -> None:
+    """An fps below one is rejected by both writers."""
+    with pytest.raises(ValueError, match="fps"):
+        writer(_rgb_frames(3), tmp_path / "clip", fps=0)
+
+
+@pytest.mark.parametrize("fmt,writer,expected", [("gif", export_gif, "GIF"),
+                                                ("apng", export_apng, "PNG")])
+def test_loop_frames_are_writable_to_both_formats(
+    tmp_path: Path, fmt: str, writer, expected: str
+) -> None:
+    """Rendered loop frames survive a full render-then-export round trip."""
+    frames = render_loop(_src(), _feedback(), count=3, axis="iterations")
+    target = tmp_path / f"loop.{fmt}"
+    writer(frames, target, fps=12)
+    with PILImage.open(target) as written:
+        assert written.format == expected
+        assert written.n_frames == 3
+
+
+def test_animation_module_imports_no_application() -> None:
+    """lattice_core/animation.py imports no application module."""
+    tree = ast.parse(Path(animation.__file__).read_text(encoding="utf-8"))
+    roots = set()
+    for node in ast.walk(tree):
+        if isinstance(node, ast.Import):
+            roots.update(alias.name.split(".")[0] for alias in node.names)
+        elif isinstance(node, ast.ImportFrom) and node.module:
+            roots.add(node.module.split(".")[0])
+    assert not roots & {"lattice_dither", "lattice_glyph", "lattice_glitch"}
+
+
+def test_dither_video_exports_are_left_intact(tmp_path: Path) -> None:
+    """The Dither 1.1 export path still writes a GIF and owns the video writer."""
+    from lattice_dither.core.animation import render_sequence as dither_sequence
+    from lattice_dither.export.video import export_gif as dither_gif
+    from lattice_dither.export.video import export_video as dither_video
+
+    frames = _rgb_frames(3)
+    target = tmp_path / "dither.gif"
+    dither_gif(frames, target, fps=10)
+    with PILImage.open(target) as written:
+        assert written.n_frames == 3
+    assert callable(dither_video)
+    assert len(dither_sequence([_src()], _spec())) == 1


CODER NOTES AND DEVIATIONS
(vide)