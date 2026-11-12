# ADR-0041: Fork pull requests run the gate on the runner's image

- **Status**: accepted
- **Date**: 2026-11-12

## Context

The GitHub workflows triggered on `push` only. A push to a branch of the repository ran the gate
on the commit its pull request would show, so pull requests from the repository's own branches
were covered. A pull request from a fork was not: its pushes land in the fork, and nothing ran
in the repository that would merge it. The hardening how-to had to tell maintainers not to
require `Preflight`, because a required check that never runs leaves an external contribution
unmergeable, and the audit's record (ADR-0013) accepted that a fork's dependency change was
first audited by the schedule, after the merge.

The reason `pull_request` was not simply added is the deps image. Every job runs inside an image
the `build-deps-image` job pushes to ghcr first, and pushing needs `packages: write`. The token a
pull request from a fork receives is read-only on every scope, so that job cannot run, and a job
whose container comes from it cannot start. GitLab has no equivalent problem: a merge request
from a fork runs its pipeline in the fork, with the fork's registry.

## Decision

`continuous-integration.yaml` and `security-audit.yaml` trigger on `pull_request` as well. The
image build is skipped on that event, which skips the container jobs behind it, and a second job
runs the same command on the runner's own image: `actions/checkout`, `astral-sh/setup-uv` reading
`[tool.uv] required-version`, then `./workflow.cmd preflight` or `./workflow.cmd secure.audit`,
with the dependencies installed at job time. The audit's `pull_request` trigger carries the same
`paths` filter as its `push` trigger, repeated because a workflow file cannot share one; an
invariant keeps the two lists equal.

The fork job runs only when the head repository is not this one. A pull request from a branch
of the repository runs nothing on the new trigger, since the push already did.

The fork job carries the same `name` as the container job. A branch rule requires `Preflight`
once, and whichever job did not run is skipped, which the rule reads as passed. Both jobs run
the identical command, so the verdict does not depend on which one ran.

## Consequences

- `Preflight` can be a required check, and the hardening how-to now says to require it.
- A fork's dependency change is audited before the merge, when it touches the surface.
- The fork path is slower: it syncs the environment from the lockfile on every run instead of
  pulling an image that has it. The template's own matrix runs generated projects the same way,
  so the path is exercised on every push to this repository.
- A fork job runs the task code the pull request brings with it. The hardening how-to already
  asked for approval of workflows from external contributors; that setting is what puts a
  maintainer between the diff and the runner.
- Two jobs per workflow now spell the gate command, and `Preflight` is spelled twice. An
  invariant asserts both jobs run the same command and share a name.

## References

- [ADR-0013](0013-the-audit-runs-on-a-schedule-and-the-dependency-surface.md), whose fork
  consequence this changes.
- [ADR-0035](0035-github-reuses-a-deps-tag-gitlab-builds-with-kaniko.md), the image build the
  fork path has to do without.
- [Harden the GitHub repository](../../using/how-to/harden-github-repository.md).
