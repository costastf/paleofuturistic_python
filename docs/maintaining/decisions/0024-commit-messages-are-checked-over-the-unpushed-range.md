# ADR-0024: Commit messages are checked over the unpushed range only

- **Status**: accepted
- **Date**: 2026-09-08
- **Record written**: 2026-11-11 (backfilled)

## Context

`cz check --rev-range HEAD` reads every reachable commit. One message that predates the
convention, a squashed import, history from before the template was applied, a `--no-verify`
from last year, fails every run from then on, with no way past it except skipping the whole
gate. And it is unfixable by design: rewriting published history is worse than the lint it
would satisfy.

## Decision

`lint.commitizen` checks the commits a push would add. The range comes from the most
authoritative source available: `PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF`, which pre-commit
hands to pre-push hooks straight from git; then the tracking branch; then the remote's default
branch. An empty candidate falls through rather than ending the search, because in CI
`actions/checkout` leaves the branch tracking a remote ref that *is* `HEAD`, and the last
resort is the tip commit alone. So something always examines the tip: locally the commit just
made, in CI the commit that arrived.

## Consequences

- A bad message already pushed keeps failing until another commit lands on top, which is bounded
  to one commit rather than to all of history.
- The commit-msg hook catches a bad message as it is written; the gate catches one that arrived
  any other way.
- This repository's own check still scans full history, which is the parked item recorded in
  the maintainer notes.

## References

- Commit `d63ef9f`.
- `unpushed_range` in `template/_CI/tasks/lint.py`.
