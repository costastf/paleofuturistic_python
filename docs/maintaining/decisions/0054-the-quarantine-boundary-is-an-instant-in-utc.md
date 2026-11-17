# ADR-0054: The quarantine boundary is an instant in UTC

- **Status**: accepted; narrows ADR-0008 and ADR-0042
- **Date**: 2026-11-17

## Context

`[tool.uv] exclude-newer` was a bare date, `2026-11-10`, stamped at generation and raised by
`develop.refresh-deps` (ADR-0008, ADR-0042). uv reads a bare date as midnight in the local
zone and records that instant in `uv.lock`: this repository's own lock held
`2026-11-10T23:00:00Z`, the previous evening in UTC, because it was written in Amsterdam.

A lock written in one zone therefore failed `uv lock --check` in another. Only the deps image
build runs `--frozen`; the launcher's `uv run` re-locks, so inside the UTC CI container the
lock rewrote itself on every task, and a developer west of UTC and one east of it could not
agree on the file. A review reproduced it with uv 0.13.5.

## Decision

The boundary is written as an RFC 3339 instant in UTC, `YYYY-MM-DDT00:00:00Z`, everywhere it
is written: the template's literal, the stamp `tasks_render.py` applies at generation, and
the value `develop.refresh-deps` writes for today or for `--boundary`. The flag's argument
stays a date; the task spells the instant.

This repository's own boundary keeps the instant its lock already held, `2026-11-10T23:00:00Z`,
so the resolution did not move with the spelling.

## Consequences

- A lock resolves to the same instant wherever it is written, and `uv lock --check` passes
  in every zone it is read in.
- A project generated today excludes releases published today, after midnight UTC, as the
  bare date excluded those after local midnight. The pinned uv is unaffected: its cool-down
  is seven days.
- The invariant that held the boundary to a date now holds it to this form, on both sides.

## References

- [ADR-0008](0008-reproducibility-by-pin.md), the boundary this spells out.
- [ADR-0042](0042-refresh-deps-moves-the-boundary-and-the-pins-together.md), the task that
  moves it.
