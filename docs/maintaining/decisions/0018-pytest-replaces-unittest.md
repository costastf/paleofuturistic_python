# ADR-0018: pytest replaces unittest, with xdist at a fixed worker count

- **Status**: accepted
- **Date**: 2024-11-18; `-n 4` fixed on 2026-09-08
- **Record written**: 2026-11-11 (backfilled)

## Context

The original lineage ran `python -m unittest`. Fixtures, parametrisation, coverage integration
and parallel execution all needed either boilerplate or a plugin layer unittest does not have.

## Decision

pytest is the runner, with pytest-cov for branch coverage, pytest-xdist for parallel execution,
pytest-html for the on-demand report and pytest-env for a `.env` file. xdist runs a fixed four
workers rather than `-n auto`: under `tox run-parallel` every environment spawns its own pool,
so `auto` on a sixteen-core machine asked for eighty workers and came out slower than four.
Four is chosen for the suite a project will have, not the two tests it ships with.

## Consequences

- Unittest-style classes still work; pytest discovers them.
- On the scaffold's two tests xdist costs more than it saves; the cost starts paying once a
  suite is large enough to spread. `-n 0` is the knob while a suite is tiny.
- Tests that cannot run in parallel need a marker and a two-pass setup the template does not
  ship, because most projects do not need it.

## References

- Commits `6dbb96f` (pytest from the first commit), `acb1bf9` (fixed worker count).
- [Testing strategy](../../using/explanation/testing-strategy.md),
  [Design principles: pytest, not unittest](../explanation/design-principles.md#pytest-not-unittest).
