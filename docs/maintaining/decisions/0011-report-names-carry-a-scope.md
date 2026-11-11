# ADR-0011: Report names carry a scope

- **Status**: accepted
- **Date**: 2026-09-09, after the per-env split of 2026-09-02
- **Record written**: 2026-11-11 (backfilled)

## Context

Coverage across a version matrix is a union: a line counts as covered if any interpreter ran
it, and version-gated code is covered by no single interpreter. Three bugs came from readers not
knowing which scope a file held:

- Under `tox run-parallel`, five environments wrote one `reports/coverage.json` at once, and the
  badge read whichever finished last, possibly mid-write.
- `test.pytest` outside tox wrote the same file with one interpreter's number, overwriting the
  union the badge and the ratchet had read.
- `fail_under`, set by the ratchet from the union, was enforced by pytest-cov per interpreter,
  and no single interpreter can clear a floor only the union reaches.

It took three passes to find every writer.

## Decision

A report's name says what scope produced it, and whatever writes a name must run at that scope:

- `reports/coverage.json` means the union across `env_list`, and is written only by
  `combine_coverage` after the whole matrix.
- `reports/coverage.<env>.json` is one environment's report; `coverage.local.json` is whatever a
  bare `pytest` happened to use. Nothing reads either.
- Each environment measures into its own `.coverage.<env>` data file.
- `fail_under` is enforced once, against the union; every other coverage command passes
  `--fail-under=0`, `addopts` included.
- `test.tox --env=<one>` writes under that environment's name and refuses `--write`, because one
  interpreter's coverage is not what the badge means.

The same rule covers the CI badge: its value is a fact about a clone, so no run is at the right
scope to judge it, and it is written but never verified (ADR-0010).

## Consequences

- The badge and the ratchet read a filename, not a provenance, and the filename is now enough.
- `coverage erase` leaves per-env data alone, so the matrix task deletes `.coverage.*` and the
  per-env reports by hand before each run, or a dropped environment would inflate the union.
- Trimming `env_list` can lower the measured union and fail the next run. That is the ratchet
  working.

## References

- Commits `a706f2e` (per-env data and combine), `10011e5` (the local report renamed).
- [Testing strategy](../../using/explanation/testing-strategy.md), the module docstring of `template/_CI/tasks/preflight.py`.
