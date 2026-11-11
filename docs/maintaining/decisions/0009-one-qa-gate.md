# ADR-0009: One QA gate

- **Status**: accepted
- **Date**: 2026-09-02; the rules stated 2026-09-16
- **Record written**: 2026-11-11 (backfilled)

## Context

The commit hook, the push hook, the aggregator tasks and the CI job each kept their own list of
checks, and the lists disagreed about what "green" meant. Per-tool hooks had pre-commit partition
the staged files and run them concurrently, so one commit got several verdicts about several
subsets of itself. Whole-program checks narrowed to the staged files answered wrongly: ty needs
the callers of a changed signature, pyscn needs every file to know what is dead, and a wheel
builds from the whole tree. And commit latency grew with the project rather than with the change.

## Decision

Every check is declared once, in `STEPS` in `_CI/tasks/preflight.py`, with a scope, a path
filter and whether it writes a derived file. Three consumers read that registry:

- `preflight.staged`, what the commit hook runs: the per-file steps over the staged files, one
  invocation, one verdict.
- `preflight`, what the pre-push hook and the CI job run, character for character: every step
  over the whole project.
- The pre-commit configuration's one `files:` pattern, which an invariant asserts is exactly the
  union of the registry's filters.

Scope decides the tier. A check that answers from the staged files alone runs on every commit;
one that needs the whole program runs on push. Steps run cheapest first, every step runs even
after one fails, and the derived-file steps are skipped once anything has failed. The only flag
that changes what runs is `--audit-dependencies`, which adds the network step. There is no flag
that runs less: `env_list` is what shortens the matrix, and it shortens CI with it.

## Consequences

- Adding a check is one registry entry; it reaches its tier without editing three files.
- The commit hook stays fast as the project grows; the push hook costs about one suite-length.
- `SKIP=preflight git push` is the escape hatch, and CI runs the same command regardless, so a
  skipped check is deferred, never avoided.
- The whole-program steps are the same list in the hook name, the CI comment and the docs, and
  invariants hold those lists to the registry.

## References

- Commits `71e37c7` (the registry and `preflight`), `715fba3` (the rules written down).
- [Design principles: The QA gate](../explanation/design-principles.md#the-qa-gate).
