# ADR-0014: A release is the version bump arriving on the default branch

- **Status**: accepted
- **Date**: 2026-11-11, after the GitLab fix of 2026-11-10
- **Record written**: 2026-11-11 (backfilled)

## Context

`./workflow.cmd release` used to create the tag `v<version>` on the release branch and push it
with the branch, and the publish pipeline triggered on tags. Two things went wrong with that:

- On GitLab the tag push published the version before the merge request had been reviewed.
- On both hosts a squash or rebase merge left the tag pointing at a commit the default branch
  never saw, and nothing published.

A tag is the wrong signal: it is created before the review and it does not follow the merge.

## Decision

`release` prepares a `release/<version>` branch, bumps the version with
`cz bump --version-files-only`, refreshes the version badge in the same commit, writes the
changelog, pushes and opens the pull or merge request. It creates no tag.

The publish job runs on every push to the default branch and hands the push to `release.ship`.
That reads `[project].version` at the previous tip and the new one; if it changed, the push
carried a release. `release.ship` then creates the tag on the new tip through the host's Release
API, with the token the job already holds (`GITHUB_TOKEN` with `contents: write`, or
`CI_JOB_TOKEN`), builds, signs the attestations and uploads. With no bump it prints so and exits
0. The Pages workflow asks the same question through `release.detect` before deploying the docs.

## Consequences

- Any merge method publishes, and nothing publishes before review.
- The `pypi` environment is protected by restricting it to the default branch, not by required
  reviewers, which would hold every push. The review that guards a release is the pull request's.
- A tag ruleset must leave creation unrestricted, since the Actions token creates the tag and no
  bypass list is guaranteed to accept it.
- `release.push` lost its purpose and was removed. A release branch opened before the change
  carries a tag that has to be deleted before merging.
- The default branch was spelled `main` in the tasks, the workflows and the badge URL until
  ADR-0040 made it a copier answer.

## References

- Commits `8287f97` (GitLab publishes only once the tag reaches main), `4e278ff` (tag on main from CI), `9f6e054` (tag rulesets).
- [Make your first release](../../using/tutorials/from-zero-to-published-package.md),
  [Upgrading past the tag-on-main release flow](../../using/how-to/update-existing-project-with-copier.md#upgrading-past-the-tag-on-main-release-flow).
