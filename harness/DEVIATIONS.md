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
