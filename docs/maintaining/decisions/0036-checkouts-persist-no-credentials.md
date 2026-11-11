# ADR-0036: Checkouts persist no credentials

- **Status**: accepted
- **Date**: 2026-08-03
- **Record written**: 2026-11-11 (backfilled)

## Context

`actions/checkout` bakes a token into the `origin` remote
(`https://x-access-token:<token>@github.com/owner/repo.git`) and leaves it in `.git/config`.
The SBOM reads `origin` for its VCS reference and ships inside the wheel, so a token written
there would become a permanent public artefact on PyPI. The same applies to the badge URL and
to anything else that reads the remote back.

## Decision

Every checkout in the generated workflows sets `persist-credentials: false`, so auth goes into
an `http.extraheader` that is removed once the fetch is done and `origin` stays a clean URL.
The one exception is the Pages deploy job, which pushes to `gh-pages` with those credentials
and builds no SBOM. As a second line, `strip_credentials` removes any userinfo from a remote
before the SBOM, the badge or the release helpers use it. An invariant asserts none of the
checkout copies drifts.

## Consequences

- The publish job cannot push, even if a build step were compromised; `release.tag` creates the
  tag through the API with the token the job holds instead.
- The workflow-level `permissions:` floor is `contents: read`, with each job widening only what
  it needs.

## References

- Commit `2087c73`.
- The note above the jobs in `continuous-integration.yaml`, `strip_credentials` in `template/_CI/tasks/shared.py`.
