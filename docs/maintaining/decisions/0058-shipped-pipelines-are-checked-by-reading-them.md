# ADR-0058: Shipped pipelines are checked by reading them

- **Status**: accepted
- **Date**: 2026-11-17

## Context

A generated project ships a GitHub workflow set or a GitLab pipeline. The parent never
executes either: its matrix generates a project per cell and runs the project's own tasks,
`preflight --write` then `preflight`, which is what every job in those pipelines runs. The
YAML itself is read by the invariant suite, which holds the jobs to what the records decide:
one gate job per event shape, least-privilege permissions, credential-less checkouts, actions
pinned to a commit with a version comment, the commit-message range exported, the deps image
built every run, and the publish job running `release.ship` and nothing else.

Running the workflows locally with `act`, or the GitLab pipeline with `gitlab-ci-local`, was
on the improvement list. It would execute the glue around the tasks: the triggers, the job
graph, the container image a job runs in, the environment it exports.

## Decision

The pipelines stay checked by reading, not by running.

What a job does is a task, and the matrix runs every task a job runs, in a generated
project, on every push. What is left in the YAML is declarative and small by design (ADR-0014,
ADR-0041), and the invariants read exactly those declarations. `act` runs GitHub's runner
images in Docker, which the matrix would then need on every machine and runner; it does not
reproduce the Pages, OIDC and registry behaviour the jobs exist for; and GitLab has no
equivalent the parent could run for both hosts. The cost is a second toolchain for a layer the
invariants already pin down line by line.

## Consequences

- A change to a shipped pipeline is verified by the invariant that reads the field it
  changed, and by the task it runs, which the matrix runs. A field no invariant reads is
  held by review.
- The first real run of a shipped pipeline is the generated project's own first push. The
  tutorials walk that run, and a defect there is a template defect to fix with an invariant.
- Mutation testing and a release rehearsal stay out for the same reason: `release.ship` is
  exercised with stubbed uploads by the invariants, and the testing-strategy page lists what
  is not shipped.

## References

- [ADR-0014](0014-a-release-is-the-version-bump-arriving-on-the-default-branch.md), which
  made the publish job one command.
- [ADR-0041](0041-fork-pull-requests-run-the-gate-on-the-runners-image.md), the last job
  shape added and read.
- [Test the template](../how-to/test-the-template.md).
