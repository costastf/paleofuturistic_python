# ADR-0049: `release.publish` is one sequence, and `release.ship` runs it

- **Status**: accepted
- **Date**: 2026-11-16

## Context

ADR-0014 made the publish job a single command, `release.ship`, which detects a release on the
incoming push, tags it, builds, attests and uploads. The by-hand task, `release.publish`, had
grown a different shape in the meantime: it built and uploaded, with a `--prebuilt` flag to
skip the build when something had acted on `dist/` first. The manual equivalent of the
pipeline was therefore three commands, `release.dist`, `release.attest` and
`release.publish --prebuilt`, and the task reference had to say so. An invariant guarded the
flag's one job, never rebuilding over signed files, by checking that the build sat behind an
`if` that mentioned `prebuilt`.

Two tasks describing the same release in two shapes is a drift waiting to happen, and the flag
existed only to let one of them imitate the other.

## Decision

`release.publish` is `release.dist`, `release.attest`, then the upload, in that order and with
nothing between. `release.ship` runs `release.publish` after it has detected and tagged the
release. The `--prebuilt` flag is gone.

`dist/` is left in place by both. The pipeline attests the uploaded files afterwards, and by
hand there is `release.clean`.

## Consequences

- One sequence, in one function. The invariant now reads the two bodies: `publish` calls
  exactly `dist`, `attest`, `upload`, and `ship` ends with the tag and `publish`, building
  nothing itself.
- The by-hand path signs. `release.attest` outside CI opens a browser to Sigstore, so a
  `release.publish` from a laptop asks for a sign-in where it used to upload unsigned files.
  With `UV_PUBLISH_*` credentials set it still signs nothing and uploads with
  `--no-attestations`, as before.
- The task reference row for `release.publish` lost its flag and its three-command recipe.

## References

- [ADR-0014](0014-a-release-is-the-version-bump-arriving-on-the-default-branch.md), which made
  `release.ship` the pipeline's one command.
