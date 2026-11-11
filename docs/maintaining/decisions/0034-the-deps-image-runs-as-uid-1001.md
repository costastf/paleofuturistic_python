# ADR-0034: The deps image runs as uid 1001

- **Status**: accepted
- **Date**: 2026-08-03
- **Record written**: 2026-11-11 (backfilled)

## Context

Every CI job ran as root inside the deps image. Dropping root is routine hardening, but the
uid is not arbitrary: GitHub's hosted runners own the mounted workspace with uid 1001, and a
mismatch leaves the checkout unwritable to the job.

## Decision

`Dockerfile.deps` ends with `useradd --uid 1001`, `USER 1001` and a home directory. `/app` is
chowned to that user because the image is built with `--no-install-project`, so `uv run`
installs the project into `UV_PROJECT_ENVIRONMENT` at job time and needs to write there, and uv
needs a writable `HOME` for its cache.

## Consequences

- Nothing in CI runs as root.
- A runner with a different uid gets permission errors under the checkout; changing the uid in
  the Dockerfile fixes it and, because the Dockerfile is a tag input (ADR-0033), rebuilds the
  image rather than serving one built for the old uid.
- On GitLab the clone is performed by a helper container, so the project directory can arrive
  root-owned depending on runner configuration; the generated docs say what that looks like.

## References

- Commit `2087c73`, "harden generated pipelines and drop root from the deps image".
- `template/Dockerfile.deps`.
