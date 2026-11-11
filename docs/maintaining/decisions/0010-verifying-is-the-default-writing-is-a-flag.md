# ADR-0010: Verifying is the default, writing is a flag

- **Status**: accepted
- **Date**: 2026-09-02
- **Record written**: 2026-11-11 (backfilled)

## Context

Tasks used to refresh README badges and the coverage ratchet as a side effect of running. A
hook that writes aborts the push having modified files the author never staged, which is what
teaches people `--no-verify`. A CI job cannot commit a refreshed badge anyway. And wherever the
verifying side was a second implementation of the generating side, the two drifted and the
gate stopped meaning anything.

## Decision

- The bare command compares; `--write` updates. `preflight` with no flag is the gate the hooks
  and the pipeline run, so reproducing a failure needs no flag.
- Every derived value, the four badges and `fail_under`, is written through one function,
  `apply_badge`, with a `write` parameter. What verifying compares is exactly what writing would
  have produced.
- A derived value is written only by the command that measured it: the coverage badge by the
  matrix run, the pyscn badge by the analysis that produced the grade, the version badge by
  `release.bump`. `document` writes no badge, because building docs is not changing a README.
- Names decide. A command named for an inspection may not modify the tree; one named for a
  mutation may, which is why `format` and `release.bump` write without being asked.
- Flags add, never subtract. `--write` and `--audit-dependencies` are the only ones the gate
  takes.

## Consequences

- A freshly generated project needs one `preflight --write` to fill in `coverage-unknown` and
  `pyscn-not rated`, and one more after `git remote add origin`.
- A value that cannot be computed at all fails `--write` too, so "wrote nothing, exited 0" cannot
  let a stale badge reach the default branch.
- The CI badge is only half checked: its URL is a fact about the clone's `origin`, not about the
  tree, so the gate asks only whether the shipped placeholder survives once a remote exists.

## References

- Commit `71e37c7`.
- [Design principles: Who may write what the checks measure](../explanation/design-principles.md#who-may-write-what-the-checks-measure).
