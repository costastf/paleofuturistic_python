# ADR-0053: CI hands the commit-message check the range it cannot infer

- **Status**: accepted; amends ADR-0024 and ADR-0052
- **Date**: 2026-11-17

## Context

`lint.commitizen` checks the commits a push would add, read from the refs pre-commit hands a
pre-push hook, else from the tracking branch, else the tip commit alone (ADR-0024). The parent
adopted the same bound for its own history (ADR-0052). Both records say that in CI the check
reads the commit that arrived.

On a pull request it reads nothing. `actions/checkout` checks out the merge ref at depth 1,
so the clone holds one commit, the merge commit GitHub makes for the event, and commitizen
accepts any subject starting with "Merge". The pull request's own commits are never read. On a
push of several commits the depth-1 clone holds the tip alone, so only that one is read. The
clone cannot tell either of these ranges; the event that triggered the job can.

## Decision

The jobs that run the check export the range as `PRE_COMMIT_FROM_REF` and
`PRE_COMMIT_TO_REF`, the names pre-commit uses, so the task has one reader for the hook and
for CI. On a pull request that is the base and head of the request; on a push it is what the
push added, `github.event.before` to `github.sha`. The checkout fetches full history so both
ends resolve. A first push to a branch has no before, so the task falls through to the
tracking branch and then the tip, as before.

On GitHub this is the parent's `lint` job and a generated project's two `Preflight` jobs. On
GitLab a generated project's `preflight` job exports the merge request's diff base, else
the push's before, to the pipeline's commit, with `GIT_DEPTH: 0` for the same reason.

## Consequences

- A pull request with one bad message among several fails `Preflight`, which is the job a
  branch rule requires. A push of several commits is checked whole.
- The first push of a new branch has an all-zero `before`, which resolves to nothing. The
  range reader then tries the remote's default branch by name, `origin/<default branch>`,
  after `origin/HEAD`, which a CI checkout does not create; with full history fetched, that
  bounds the push to what the branch adds over the default branch.
- The parent reads the same two variables the template does; its range reader is the
  template's again, pre-commit refs included, where ADR-0052 had left those out.
- An invariant holds that every job running the check exports both refs and fetches full
  history, on both hosts.
- The shipped environment reference says CI sets the two variables as well as pre-commit.

## References

- [ADR-0024](0024-commit-messages-are-checked-over-the-unpushed-range.md), whose "the commit
  that arrived" this corrects for pull requests.
- [ADR-0052](0052-the-parent-checks-its-commit-messages-over-the-unpushed-range.md), whose
  shallow-clone consequence this removes.
- [ADR-0041](0041-fork-pull-requests-run-the-gate-on-the-runners-image.md), the fork gate
  this reaches.
