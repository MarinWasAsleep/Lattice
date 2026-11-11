# Project state (updated by the orchestrator only)

contract_version: 1.2.0-draft
max_concurrency: 4
last_update: 2026-11-11

## Environment (filled by T00)
- python: 3.15.2 (system, no fallback needed); numpy 2.5.4, numba 0.68.1, Pillow 13.0.0, PySide6 6.12.0, pytest 9.2.0, ruff 0.17.4
- venv: .venv (import check and numba JIT check OK; Qt offscreen OK)
- requirements pinned: yes (requirements.txt, 6 exact pins)
- git: initialised, .gitignore written, one commit per task from T00 onward
- photocraft: 0.22.0; control server 127.0.0.1:47600, token %LOCALAPPDATA%\DitherCraft\control.token,
  automation roots by launch flags via the Desktop shortcut "PhotoCraft (DitherCraft)" (present)
- automation read/write root: %LOCALAPPDATA%\DitherCraft\exchange (exists, empty)

## Tasks

Status: todo | ready | in_progress | gates | review | done | blocked
Counters: g = gate retries used (max 3), r = review cycles used (max 2).

| Task | Wave | Status | g | r | Commit | Note |
|---|---|---|---|---|---|---|
| T00 | 0 | done | 0 | 0 | 824d704 | env + pins + harness kit |
| P00 | 0 | done | 0 | 0 | | PROBE-1..3 verified on the user instance |
| T01 | 0 | done | 0 | 0 | 0a1e4f5 | scaffold, core, check_contract, stubs |
| T02 | 1 | done | 0 | 0 | 9883964 | 10 error-diffusion kernels |
| T03 | 1 | done | 0 | 0 | fa317ca | ordered + blue noise (committed .npy) |
| T04 | 1 | done | 0 | 0 | 6128dd4 | misc + halftone |
| T05 | 1 | done | 0 | 0 | 83b0d87 | 11 built-in palettes, .hex/.gpl IO |
| T06 | 1 | done | 0 | 0 | 0b7cf31 | kmeans + median cut |
| T07A | 1 | done | 0 | 0 | f0cefed | 5 tone effects |
| T07B | 1 | done | 0 | 0 | f5fb328 | 4 glitch effects |
| T08 | 1 | done | 0 | 0 | 6997930 | desktop bridge + smoke tool |
| T09 | 1 | done | 0 | 0 | 5639f52 | pipeline + presets |
| T10 | 1 | done | 0 | 0 | c84f919 | UI shell, canvas, ParamForm |
| T11 | 2 | done | 0 | 0 | 45e094d | algorithm panel |
| T12 | 2 | done | 0 | 0 | e61ddf4 | effects panel |
| T13 | 2 | done | 0 | 0 | 64ef23a | palette panel |
| T14 | 3 | done | 0 | 0 | 0ca8c8c | integration, worker, live preview |
| T15 | 3 | done | 0 | 0 | pending | packaging; script NOT run (H3) |
| T16 | 3 | todo | 0 | 0 | | needs H4, human + PhotoCraft |

## Decisions log
- 2026-11-10: external tool architecture (no PhotoCraft fork), PySide6, images only, live preview,
  result placed as new layer from the flattened render, English UI, name DitherCraft.
- 2026-11-10: ParamForm moved from T11 to T10 so that T11, T12, T13 run fully in parallel.
- 2026-11-10: T00 done. Python 3.15.2 retained. Auth = `auth` method as first request per connection.
- 2026-11-10: DEV-001 accepted, section 8 rewritten for the desktop server.
- 2026-11-10: P00 done. Control server 47600, token file, roots by launch flags; instance.json never used.
- 2026-11-10: DEV-002 accepted. Section 8.6 version check + smoke tool + startup warning.
- 2026-11-11: build executed by a single agent (Mistral Vibe) acting as coder and reviewer, with the
  deterministic gates G1-G4 as the real review. The DeepSeek-coder / Sonnet-reviewer split of the harness
  was not used: no independent reviewer, so the gates carry the quality argument.
- 2026-11-11: waves run with parallel subagents on disjoint `owns` sets (4 then 3 then 1), commits
  serialised by the orchestrator after each wave. No merge conflict occurred.
- 2026-11-11: DEV-003 accepted (T14 rewrote two T10 tests that asserted the placeholders).
- 2026-11-11: T01-T15 done, 431 tests green, ruff clean, check_contract OK.
- NEXT: H2 (run the UI, judge ergonomics), H3 (approve the shortcut script), H4 (T16 acceptance in PhotoCraft).
