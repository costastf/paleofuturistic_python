# ADR-0013: The audit runs on a schedule and on the dependency surface

- **Status**: accepted
- **Date**: 2026-09-02, replacing the every-gate run of 2026-08-03
- **Record written**: 2026-11-11 (backfilled)

## Context

A dependency audit's answer depends on the advisory database on the day it runs, not on the
branch. Three placements were tried or considered, and each had a failure mode:

- Reachable only as a local command, the audit gated nothing, and the expiry dates in
  `.security-overrides` never came due because nothing ran on the day they passed.
- In every automated gate, as it was from August 2026, a docstring change went red for a CVE
  published overnight that its author neither introduced nor could fix, which is the kind of
  noise that teaches people to ignore a red pipeline.
- Inside `build`, a fresh advisory made it impossible to build a wheel from code that had built
  the day before, blocking a hotfix on an unrelated finding.

## Decision

The audit is triggered on the two axes it varies along:

- **Time.** A daily schedule on GitHub (`cron`, off the hour), and a `schedule` pipeline rule on
  GitLab. This is what makes the expiry dates load-bearing.
- **The dependency surface.** A push that touches `uv.lock`, `_CI/lib/vendor.txt`, the vendored
  tree or its patches, or `.security-overrides`. Not `pyproject.toml`: the project runs
  `--frozen`, so an edit that changes what is installed changes the lockfile with it, while a
  ratchet bump or a version bump does not fire a full audit of an untouched dependency set.

Publishing is gated separately: `release.dist` audits before it builds, because that is the
moment the outside world is exposed. `preflight --audit-dependencies` adds the step locally;
the bare gate never runs it. In this repository's own matrix the audit rides with the matured
cell only, so a transient advisory-service error fails one job instead of five.

## Consequences

- A pull request from a fork triggered no audit until ADR-0041; the scheduled run after the
  merge covered it.
- A hand-edited vendored file is watched, not audited: no scanner can read a patched source, so
  the push fires the job to put the diff in front of a human.
- `secure` remains the human-facing aggregator; nothing automated calls it.

## References

- Commits `839734b` (audit in every gate), `0b871d3` (separated from the build, narrowed to schedule and surface).
- [SBOM and security model: Layer 1](../../using/explanation/sbom-and-security-model.md#layer-1-pip-audit).
