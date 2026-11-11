# ADR-0004: Pipelines run template commands only

- **Status**: accepted
- **Date**: 2026-07-28 (practice since 2026-03-30)
- **Record written**: 2026-11-11 (backfilled)

## Context

A workflow file that carries its own `uv …`, `pip install …` or `properdocs …` lines is a second
implementation of the development cycle: it drifts from what a developer runs, a failing step
cannot be reproduced by typing one command, and the dependencies of a GitHub Action are hidden
inside a `uses:` reference where neither `uv.lock` nor the SBOM sees them.

## Decision

Every CI step is a `./workflow.cmd <task>` call. Behaviour lives in `_CI/tasks/`; the workflow
files are glue. Three actions are the whole exception list: `actions/checkout`,
`astral-sh/setup-uv` where the deps image is not in use, and `actions/attest-build-provenance`,
since only GitHub can record GitHub's provenance attestation. Concretely, docs deploy through
`properdocs gh-deploy` rather than the Pages actions, and tests run through `./workflow.cmd test`
rather than an inline `pytest`.

One pipeline job cannot follow the rule: GitLab's deps-image job runs in the kaniko image, which
has no Python, so it repeats in shell what `container.publish` does, and an invariant keeps the
two tag computations identical.

## Consequences

- Parity. The pre-push hook and the CI job run the same `./workflow.cmd preflight`, character
  for character (ADR-0009), so reproducing a pipeline failure means typing what the log shows.
- Every Python dependency a job uses is pinned in `uv.lock` and listed in the SBOM.
- The Pages deploy goes through the legacy branch flow, which GitHub's own internal pipeline
  then builds; its Node deprecation warning is accepted as the price of keeping deploy logic in
  `document.py`.
- The GitLab shell duplicate is a standing exception, and a candidate for computing the tag in a
  Python job and handing it to kaniko.

## References

- Commit `8aaea04` (workflow test task and CI scaffolding), `5531689` (the principle stated).
- [Design principles: Pipelines run template commands only](../explanation/design-principles.md#pipelines-run-template-commands-only),
  [Publish docs to GitHub Pages](../../using/how-to/publish-docs-to-github-pages.md).
