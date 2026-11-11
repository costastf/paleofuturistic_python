# ADR-0037: Docs deploy on release through `gh-deploy`, with an explicit Pages build request

- **Status**: accepted
- **Date**: 2026-09-07 (on release); build request 2026-07-28; `release.detect` 2026-11-11
- **Record written**: 2026-11-11 (backfilled)

## Context

Three things, in order. GitHub's upload-pages-artifact and deploy-pages actions bring
dependencies that appear in neither `uv.lock` nor the SBOM, and deploy logic that lives in
YAML. A push made with the Actions `GITHUB_TOKEN` to the `gh-pages` branch does not trigger the
legacy deploy-from-branch build, so a deploy that pushed and stopped published nothing. And a
site deployed on every push to the default branch describes code that is in no release yet, so
a reader can reach for something they cannot install.

## Decision

`document.deploy-github` runs `properdocs gh-deploy --force`, a Python command from the
lockfile, then requests a Pages build through the API. The workflow triggers on a push to the
default branch and asks `release.detect` whether the push carried a release, the same question
the publish job asks through `release.ship`, and deploys from the detected commit. Since
November 2026 that detection is the task itself; before, a separate `detect-release-tag.yaml`
did it. `workflow_dispatch` remains so a project that has not released can publish its docs at
all. The deploy job is the one checkout that persists credentials (ADR-0036).

## Consequences

- The site and the package cannot disagree about what counts as released.
- GitHub's own `pages-build-deployment` pipeline prints a Node deprecation warning that this
  template cannot silence without adopting the actions it chose not to; the warning is
  accepted.
- Versioned docs, a `stable` and a `dev` build, would need more machinery than the template
  ships.

## References

- Commits `1e0dd3f` (gh-deploy), `3b1efd6` (Pages build request), `38acf6f` (on release), `4e278ff` (`release.detect`).
- [Publish docs to GitHub Pages](../../using/how-to/publish-docs-to-github-pages.md).
