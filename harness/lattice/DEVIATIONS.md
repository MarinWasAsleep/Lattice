# Deviation protocol and register — Lattice harness 0.1

The protocol is **unchanged** from `harness/DEVIATIONS.md` (DitherCraft 1.0): same five classes E1
to E5, same retry budget (3 gate retries, 2 review cycles), same impact rule. Read that file; it is
not repeated here.

Classes E6 (regression) and E7 (product) from `harness/v1.1/DEVIATIONS.md` also apply, unchanged.

Two additions for the suite:

- **E8 Abstraction leak.** A change that makes an application import from another application, or
  that puts application-specific logic into `lattice_core`. Caught by the L1 test that walks the
  package, or by the reviewer. Never acceptable: core must not know that GlyphCraft exists. The
  resolution is either to move the code into the application, or to generalise it behind a
  documented core interface.
- **E9 Host coupling.** A change that makes an application unusable without ArtCraft: a hard
  dependency on a running host, a crash when the bridge is absent, or a UI that only makes sense
  when bridged. Every application must open a file and render it with no host present. Declared by
  the reviewer or caught at H3, H4 or H5.

## Register

Format: one block per deviation, newest at the bottom. Status: open | accepted | rejected | resolved.

The DitherCraft registers (DEV-001 to DEV-008 in 1.0, DEV-101 onward in 1.1) are closed and stay in
their own files. Nothing is carried over.

```
### DEV-201
- class: E8 | task: Lxx | contract: 0.1.0 | status: open
- raised by: reviewer | date: 2026-11-xx
- facts: <what leaked, quote the import or the file>
- assumption / proposal: <move it, or generalise it behind a core interface>
- decision: <filled by decider> | by: <reviewer / orchestrator / human>
- impact: <tasks affected, contract version bump>
```

## Amendments

Facts discovered during a task that the contract could not have known, recorded here rather than
invented in code. The orchestrator folds them into the contract at the next checkpoint.

```
### AMD-xxx
- task: Lxx | contract: 0.1.0 | date: 2026-11-xx
- section: §n
- discovered: <the real surface, quoted from the host's own `describe` output>
- contract change: <the sentence to add or replace>
```

### AMD-001
- task: none (human decision) | contract: 0.1.0 | date: 2026-11-12
- section: §1, §2, §20
- discovered: the name `DitherCraft` is already in use by three live products, one of them a
  direct Rust competitor (`github.com/shahil-sk/dithercraft`). Recorded in
  `docs/market-research.md` §9.
- contract change: §1 table row becomes `| Lattice Dither | lattice-dither | palette dithering |`;
  the §20 non-goal "Renaming DitherCraft" is removed. The application is renamed Lattice Dither,
  package `lattice_dither`, distribution `lattice-dither`, executable `LatticeDither.exe`.
