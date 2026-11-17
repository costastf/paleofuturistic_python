# ADR-0052: The parent checks its commit messages over the unpushed range

- **Status**: accepted; narrows ADR-0048, corrects a consequence of ADR-0024
- **Date**: 2026-11-17

## Context

A generated project's `lint.commitizen` checks the commits a push would add, and falls back to
the tip commit alone, so a message from before the convention cannot fail every later run
(ADR-0024). That record's consequences say this repository's own check still scans full
history. There was no such check: the parent installed no hooks, ran no `cz check` in its lint
task and none in its workflows. The note it referred to was a parked question about which
bounded scope to adopt, which ADR-0024 had already answered for the template.

The parent's history is the case ADR-0024 was written for. Of its 489 commits, 113 early ones
have subjects like "Initial commit" and "update basic docs". A full-history check fails on
them; a check over the tip passes.

## Decision

`./workflow.cmd lint` in this repository runs `cz check` over the range a push would add,
computed the way the template's `unpushed_range` computes it minus the pre-commit refs the
parent never receives: the tracking branch, then the remote's default branch, each skipped
when the range it gives is empty, then `HEAD~1..HEAD`, or `HEAD` alone where there is no
parent to name. commitizen joins the `lint` group at the template's pin, and the invariant
holding the parent's lint pins equal to the template's covers it.

The range is read from the clone at run time, so the check is built by `checks(context)`
rather than listed in the static `CHECKS` table the other commands sit in.

## Consequences

- A commit whose message breaks the convention fails `lint` locally before it is pushed, and
  CI's `lint` job on the commit that arrived. The early history stays as it is.
- The `lint` job's checkout is shallow, so in CI the check reads the tip commit alone, as a
  generated project's does; a bad message already pushed fails until a good one lands on it.
- The pyproject validator is now the only step of a generated project's `lint` the parent does
  not run.

## References

- [ADR-0024](0024-commit-messages-are-checked-over-the-unpushed-range.md), whose scope this
  adopts and whose consequence about this repository it corrects.
- [ADR-0048](0048-the-parent-is-judged-by-the-gate-it-ships.md), the rule this applies to one
  more step.
