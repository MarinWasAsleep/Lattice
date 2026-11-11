# Project state (updated by the orchestrator only)

contract_version: 1.2.0-draft
max_concurrency: 4
last_update: 2026-11-10

## Environment (filled by T00)
- python: 3.15.2 (system, no fallback needed); numpy 2.5.4, numba 0.68.1, Pillow 13.0.0, PySide6 6.12.0, pytest 9.2.0, ruff 0.17.4
- venv: .venv (import check and numba JIT check OK; Qt offscreen OK)
- requirements pinned: yes (requirements.txt, 6 exact pins)
- git: initialised, .gitignore written, nothing committed
- photocraft: 0.22.0, instance file %APPDATA%\Photocraft\instance.json (stale at T00 time: pid 5192 dead, port refused; desktop app was not running)
- automation read root: NOT configured on the user's app (pending H0). Folder %LOCALAPPDATA%\DitherCraft\exchange exists (empty). Settable only by
  launch flags or env vars PHOTOCRAFT_AUTOMATION_READ_ROOT and PHOTOCRAFT_AUTOMATION_WRITE_ROOT (write root also needed). Not in preferences.json.
- H0 action for the user: set both user env vars to the exchange folder (setx), fully restart PhotoCraft, then re-run a short probe (see CONTRACT §8 TBD-2).
- IMPORTANT: the desktop control server has a different method set from headless (no doc.render, doc.place, doc.inspect, methods). See CONTRACT §8 TBD-1.
  T08 must target the desktop methods (app.save, app.open, engine.execute); contract amendment to §8 needed before T08.

## Tasks

Status: todo | ready | in_progress | gates | review | done | blocked
Counters: g = gate retries used (max 3), r = review cycles used (max 2).

| Task | Wave | Status | g | r | Commit | Note |
|---|---|---|---|---|---|---|
| T00 | 0 | done | 0 | 0 | | steps 1-2 done; desktop check done on a separate instance only; H0 (env vars) pending |
| P00 | 0 | done | 0 | 0 | | PROBE-1..3 verified on user instance, CONTRACT section 8 updated (port 47600, token file, launch flags) |
| T01 | 0 | todo | 0 | 0 | | contract freeze after (H1) |
| T02 | 1 | todo | 0 | 0 | | |
| T03 | 1 | todo | 0 | 0 | | |
| T04 | 1 | todo | 0 | 0 | | |
| T05 | 1 | todo | 0 | 0 | | |
| T06 | 1 | todo | 0 | 0 | | |
| T07A | 1 | todo | 0 | 0 | | |
| T07B | 1 | todo | 0 | 0 | | |
| T08 | 1 | todo | 0 | 0 | | needs T00 TBD facts |
| T09 | 1 | todo | 0 | 0 | | critical path, schedule first |
| T10 | 1 | todo | 0 | 0 | | |
| T11 | 2 | todo | 0 | 0 | | |
| T12 | 2 | todo | 0 | 0 | | |
| T13 | 2 | todo | 0 | 0 | | |
| T14 | 3 | todo | 0 | 0 | | |
| T15 | 3 | todo | 0 | 0 | | H3 |
| T16 | 3 | todo | 0 | 0 | | H4 |

## Decisions log
- 2026-11-10: external tool architecture (no PhotoCraft fork), PySide6, images only, live preview,
  result placed as new layer from the flattened render, English UI, name DitherCraft.
- 2026-11-10: ParamForm moved from T11 to T10 so that T11, T12, T13 run fully in parallel.
- 2026-11-10: T00 done. Python 3.15.2 retained (numba and PySide6 install). Auth = `auth` method as first request per connection.
  Desktop protocol differs from headless (no doc.* methods); bridge must use app.save, app.open, layer.copyToDocument; write root needed too.
- 2026-11-10: DEV-001 accepted. §8 rewritten for the desktop server, contract 1.1.0-draft. T08 blocked until P00 resolves PROBE-1..3.
- 2026-11-10: P00 blocked at step 0. User env vars READ/WRITE_ROOT are set to the exchange folder, but PhotoCraft is not running (stale instance.json). No probe run, CONTRACT §8 unchanged.
- 2026-11-10: P00 still blocked at step 0 after PhotoCraft restart: server listens but replies "not taken" to all requests (even with valid token); preferences.json has allowAgentControl=true. No probe run, CONTRACT §8 unchanged.
- 2026-11-10: P00 still blocked. Control server listens on 127.0.0.1:47600 (preferences integrations.controlPort) and demands auth; instance.json port (65318) is a different listener answering "not taken"; instance.json token is refused on 47600; no token file found in %APPDATA%\Photocraft. No probe run, CONTRACT §8 unchanged.
- 2026-11-10: P00 done. Control server = 127.0.0.1:47600, token in %LOCALAPPDATA%\DitherCraft\control.token, roots by launch flags (shortcut); instance.json is single-instance IPC, never used. PROBE-1..3 OK; send sequence simplified (file.close with explicit document index). CONTRACT section 8 rewritten accordingly; T08 unblocked.
- 2026-11-10: DEV-002 accepted. §8.6 version check + tools/smoke_photocraft.py (T08), startup warning (T14). Contract 1.2.0-draft.
- 2026-11-10: PhotoCraft must be launched from the Desktop shortcut "PhotoCraft (DitherCraft)" (--control 47600, token file, both roots).
  After any PhotoCraft update: relaunch from the shortcut, run tools/smoke_photocraft.py; on FAIL open an E2 deviation on §8.
- NEXT: run T01 through the harness (prompts/ORCHESTRATOR.md, KICKOFF), then checkpoint H1 (freeze contract 1.2.0).
