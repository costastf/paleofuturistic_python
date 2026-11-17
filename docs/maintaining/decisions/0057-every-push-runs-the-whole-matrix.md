# ADR-0057: Every push runs the whole matrix

- **Status**: accepted
- **Date**: 2026-11-17

## Context

Neither the parent's matrix workflow nor a generated project's gate filters on paths. A
commit that touches only `docs/` runs the five matrix cells here and the full `preflight`
there, which is minutes of runner time for a change that no cell reads. A `paths-ignore` on
the triggers is the usual answer and was on the improvement list.

## Decision

No path filter, on either side.

In a generated project the gate is one command, `preflight`, which the pre-push hook runs
with no filter (ADR-0022). It builds the docs, verifies the README badges and the derived
files, and checks the commit messages, so there is no docs-only change it has nothing to say
about. A filter would make a push green that the hook would have refused.

In the parent, the invariant suite reads `docs/`: every `ADR-NNNN` named anywhere must
resolve to a record, the shipped explanation pages must match their render, no heading may
start with a digit, and the task catalog must name every task. A docs-only commit is exactly
what those tests exist to judge. The matrix cells generate a project, and `template/docs` is
part of what they generate and build.

## Consequences

- A docs-only commit pays the full matrix. That is the cost of having nothing the gate
  skips.
- A branch rule can require the gate without a carve-out for paths that never trigger it.

## References

- [ADR-0022](0022-one-commit-stage-hook-and-no-filter-on-pre-push.md), the hook this keeps
  CI equal to.
