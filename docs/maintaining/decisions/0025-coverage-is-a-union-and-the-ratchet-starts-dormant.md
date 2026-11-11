# ADR-0025: Coverage is a union, `fail_under` is enforced once, and the ratchet starts dormant

- **Status**: accepted
- **Date**: 2026-05-29 (dormant ratchet), 2026-09-02 (union)
- **Record written**: 2026-11-11 (backfilled)

## Context

A coverage floor that only moves up keeps coverage from regressing silently, but two things
made a naive ratchet unusable. The scaffold's smoke test drives a fresh project to 100% on day
one, so a ratchet that engaged immediately locked the bar at 100 and failed the first real
change. And a version matrix produces five coverage numbers, none of which is the project's
coverage: version-gated code is reached by some interpreters and not others, so each reports
a miss on code the matrix as a whole exercises.

## Decision

- Coverage across the matrix is the union: `coverage combine` over the per-environment data
  files, written once to `reports/coverage.json`. A line counts as covered if any interpreter
  ran it. Averaging would be meaningless; coverage is a set of lines, not a noisy measurement.
- `fail_under` is enforced once, by the combine, against the union it was measured from. Every
  other coverage command passes `--fail-under=0`.
- The ratchet is dormant while `def test_sanity` is still in the scaffolded test file
  (`[tool.test-ratchet] mode = "auto-detect"`). Removing it engages the ratchet; once any
  non-zero `fail_under` is written, dormancy is over for good. `mode = "strict"` engages it on
  the first run, for a scaffold seeded into an already-covered codebase.

## Consequences

- The bar only goes up; lowering it is a deliberate, reviewable edit in the same commit as the
  code that needed it.
- Trimming `env_list` can lower the union and fail the next run. That is the ratchet working.
- The template's own matrix needs a matured cell to exercise any of this (ADR-0038).

## References

- Commits `9c0f82b` (dormant ratchet), `a706f2e` (combine per-env data).
- [Testing strategy](../../using/explanation/testing-strategy.md), ADR-0011.
