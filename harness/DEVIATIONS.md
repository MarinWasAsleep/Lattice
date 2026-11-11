# Deviation protocol and register

A deviation (écart) is any gap between what a task must do and what the contract, the card or the
environment allows. Deviations are declared, never silently worked around.

## Classes

| Class              | Meaning                                                                                                    | Who declares                                         | Coder behaviour                                                             | Resolution                                                                                                                                     | Decider                                        |
| ------------------ | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| E1 Ambiguity       | Contract or card admits several readings                                                                   | coder, reviewer                                      | Pick the most conservative reading, state it under DEVIATIONS, continue     | Reviewer accepts or rejects. Accepted → orchestrator adds a PATCH clarification to CONTRACT                                                    | reviewer                                       |
| E2 Contract defect | An interface is wrong, missing or contradictory; the task cannot be done without changing a frozen section | coder, reviewer                                      | **Stop.** Output no code, only the deviation with a minimal proposed change | Orchestrator drafts a MINOR change and lists impacted tasks (owners and consumers of the section). Change to §3, §4 or §7 needs human approval | orchestrator; human for §3/§4/§7 and any MAJOR |
| E3 Scope           | Edit outside `owns`, extra feature, new dependency                                                         | gate G4, reviewer                                    | Not allowed                                                                 | Automatic rejection; retry with the reminder. New dependency → E5                                                                              | automatic                                      |
| E4 Technical block | Test impossible to satisfy, performance target missed, library bug, defect found in acceptance             | coder after 2 failed attempts, reviewer, human (T16) | Report facts: what was tried, exact error                                   | Sonnet diagnoses: fix itself (≤ 40 changed lines), split into a new task, or relax a criterion (recorded as decision)                          | orchestrator; human if a criterion is relaxed  |
| E5 Environment     | Dependency, interpreter, OS, PhotoCraft behaviour                                                          | anyone                                               | Stop                                                                        | Human                                                                                                                                          | human                                          |

## Retry budget per task

- Gate failures (G1 to G4): up to 3 coder retries, each with the trimmed log (≤ 80 lines). Cheap: no Sonnet call.
- Review FIX: up to 2 cycles. On the 3rd failure the reviewer applies the fix itself if ≤ 40 changed lines,
  otherwise opens E4.
- Any ESCALATE verdict suspends the task (status `blocked`) and frees its slot.

## Impact rule

When a contract change is accepted, every task whose `context` includes the changed section:
- status `todo` or `in_progress` → its prompt is regenerated with the new contract version;
- status `done` → a follow-up task `T<id>-c<n>` (size S, review light) is created only if its code is affected.

## Register

Format: one block per deviation, newest at the bottom. Status: open | accepted | rejected | resolved.

```
### DEV-001
- class: E1 | task: T02 | contract: 1.0.0 | status: open
- raised by: coder | date: 2026-11-xx
- facts: <what conflicts, quote the contract line>
- assumption / proposal: <conservative reading, or minimal change>
- decision: <filled by decider> | by: <reviewer / orchestrator / human>
- impact: <tasks affected, contract version bump>
```

### DEV-001
- class: E2 | task: T00 | contract: 1.0.0-draft | status: resolved
- raised by: T00 (Sonnet) | date: 2026-11-10
- facts: §8 described the headless server (`doc.render`, `doc.place`); the desktop control server has none of the `doc.*` methods.
- assumption / proposal: target the desktop server with `app.save` (get) and `app.open` + `layer.copyToDocument` (send).
- decision: accepted, §8 rewritten, contract 1.1.0-draft; open points tagged PROBE-1..3, resolved by task P00 on the user's instance | by: orchestrator (Opus) on user request
- impact: T08 (acceptance criteria rewritten), T14 (uses the same public API, unchanged)

### DEV-002
- class: E1 (additive) | task: T08, T14 | contract: 1.1.0-draft | status: resolved
- raised by: human (PhotoCraft updates) | date: 2026-11-10
- facts: PhotoCraft is 0.x; an update may rename desktop methods or params used by §8.3/§8.4.
- assumption / proposal: add §8.6: installed version detection via photocraft-cli --version, tested version constant, manual smoke test tool, non-blocking UI warning.
- decision: accepted, contract 1.2.0-draft | by: human
- impact: T08 owns tools/smoke_photocraft.py and new accept items; T14 adds the startup version check.

### DEV-003
- class: E3 (accepted) | task: T14 | contract: 1.2.0-draft | status: resolved
- raised by: T14 coder | date: 2026-11-11
- facts: T10's accept items assert the placeholder tabs and the placeholder slots ("Open image is not wired yet"), but T14's spec requires replacing exactly those placeholders with the three real panels and the wired actions. The two cards are contradictory by construction; T14 cannot satisfy its own spec while leaving T10's tests untouched. The placeholder test also opened a real modal QMessageBox and hung the suite.
- assumption / proposal: T14 rewrites only the two affected tests in tests/test_ui_canvas.py, keeping their intent (the window builds, the actions exist and are wired) and asserting the real panels instead of the placeholders. `placeholder_tabs` stays as an empty dict so T10's `replace_tab` API and its remaining test stay valid.
- decision: accepted; the edit is limited to tests/test_ui_canvas.py and reviewed in the T14 commit | by: orchestrator
- impact: none on the contract; T10's card should have said "placeholder until T14" for those two accept items.

### DEV-004
- class: E1 (additive) | task: T08 | contract: 1.2.0-draft | status: resolved
- raised by: T08 coder, confirmed by the review pass | date: 2026-11-11
- facts: §8.5 lists no raw request entry point, but §8.6's smoke tool needs raw `ui.inspect`, `engine.execute`, `app.open` and `file.close` calls that the three documented methods do not expose.
- assumption / proposal: keep `PhotoCraftClient.call(method, params)` as an additive public method (one authenticated connection, lock, exchange cleanup).
- decision: accepted | by: orchestrator
- impact: none; §8.5 gains a method on the next MINOR bump.

### DEV-005
- class: E4 (technical block) | task: T08 | contract: 1.2.0-draft | status: resolved
- raised by: T08 coder, confirmed by the review pass | date: 2026-11-11
- facts: the T08 card requires a ctypes pid liveness check (OpenProcess + GetExitCodeProcess). No pid source exists: DEV-001 forbids `instance.json` (the only place a pid appears) and the control server exposes none. The check was therefore dead code with no caller.
- assumption / proposal: drop `is_process_alive` and the ctypes constants. Liveness is established by the TCP connect plus the auth handshake, which is what `discover()` already does and what §8.5 specifies.
- decision: accepted; the card item is not applicable as written | by: orchestrator
- impact: T08 card accept item removed; no code impact.

### DEV-006
- class: E1 | task: T07A | contract: 1.2.0-draft | status: resolved
- raised by: the review pass | date: 2026-11-11
- facts: §4 fixes only the effect contract (same shape, float32, [0, 1], deterministic, never raises) and the T07A card says only "bright-pass, blur, screen blend" and "gaussian" noise. Neither fixes the amount-to-sigma factor nor the bright-pass normalisation.
- assumption / proposal: noise standard deviation = amount * 0.5 (`_NOISE_SCALE`); bright pass = clip((data - threshold) / (1 - threshold), 0, 1). Behaviour left unchanged.
- decision: accepted as the reference mapping | by: orchestrator
- impact: none; documents the UI labels and future tuning.

### DEV-007
- class: E1 | task: T09 | contract: 1.2.0-draft | status: resolved
- raised by: the review pass | date: 2026-11-11
- facts: §7 says "effect i gets default_rng(spec.seed + i)" without saying whether i is the list position or the position among enabled effects. The two readings differ once an effect is disabled.
- assumption / proposal: i counts only ENABLED effects, so disabling an effect does not renumber the seeds of the later ones. Pinned by tests/test_pipeline.py::test_disabled_effect_does_not_shift_the_seed.
- decision: accepted | by: orchestrator
- impact: none; a PATCH clarification of §7 is due at the next contract bump.

### DEV-008
- class: E1 (additive) | task: post-T15 | contract: 1.2.0-draft | status: resolved
- raised by: the user, who asked for the algorithms the harness cards left out | date: 2026-11-12
- facts: the cards fix 27 algorithms. Seven more were added afterwards: Ostromoukhov, Fan, Shiau-Fan, Yliluoma 1, Yliluoma 2, dot diffusion and direct binary search. None is covered by CONTRACT.md, so the contract checker validates them only through its generic loop (int32, shape, range, snake_case ids, bounded params).
- assumption / proposal: the published sources are followed where they exist. Ostromoukhov uses the 256-row table of the author's reference implementation (varcoeffED), indexed by the *input* tone, with the right / down-left / down layout of Appendix I. Fan and Shiau-Fan use the left-shifted "extended distribution set" forms. Dot diffusion uses Knuth's class matrix from `dot-diff.w` with a fixed 3x3 diffused kernel normalised over the neighbours that are still unprocessed, because Knuth's co-optimised 8x8 diffused matrix is not reproducible from the sources reachable here. Yliluoma 1 is chroma-blind by construction (plans are indexed by luminance), which is the documented difference from algorithm 2. DBS visits pixels in a splitmix64-hashed order rather than a raster scan, because a raster scan biases the error and overshoots badly on flat areas.
- decision: accepted | by: orchestrator
- impact: none on the existing 27; the UI picks the new algorithms up through the registry. A MINOR contract bump should list them.

