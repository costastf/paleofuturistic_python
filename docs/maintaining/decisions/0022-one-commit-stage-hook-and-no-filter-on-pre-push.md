# ADR-0022: One commit-stage hook, and no `files:` filter on pre-push

- **Status**: accepted
- **Date**: 2026-09-02 (one hook), 2026-09-08 (no filter on pre-push)
- **Record written**: 2026-11-11 (backfilled)

## Context

Five pre-commit hooks, one per tool, had pre-commit partition the staged files and run the
tools concurrently: five banners, five reads of the index, five verdicts about five subsets of
one commit. Separately, a `files:` filter on the pre-push hook meant a push carrying only
`README.md` and `pyproject.toml`, which is exactly what the recovery loop produces after
`preflight --write`, skipped the gate on the very push meant to prove it green, while CI still
ran it in full.

## Decision

- The commit stage is one hook running `./workflow.cmd preflight.staged`, with
  `pass_filenames: false` because the task reads the index itself. The hook's `files:` pattern
  decides only whether it wakes, and an invariant asserts it is exactly the union of the
  registry's per-step filters.
- The pre-push hook runs `./workflow.cmd preflight` with no `files:` filter and no flag, so it
  is the command the pipeline runs and nothing can pass locally that CI rejects.
- A third commit-stage hook runs `secure.validate-overrides` only when `.security-overrides` is
  staged.

## Consequences

- One verdict per commit, in registry order, cheapest first.
- Launcher startup is about a tenth of a second, so the argument for one hook is legibility, not
  the seconds.
- `SKIP=<id>` suspends one hook and leaves the others; `--no-verify` is documented as the thing
  to avoid.

## References

- Commits `71e37c7` (`preflight.staged`), `4e891d3` (filter removed from pre-push).
- [Configuration files: .pre-commit-config.yaml](../../using/reference/generated-project-tree.md) in the generated docs, ADR-0009.
