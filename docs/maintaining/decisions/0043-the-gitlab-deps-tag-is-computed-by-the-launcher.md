# ADR-0043: The GitLab deps tag is computed by the launcher

- **Status**: accepted
- **Date**: 2026-11-12

## Context

ADR-0004 has every pipeline job run a template command through the launcher, and ADR-0035
recorded the one job that could not: GitLab's deps-image job runs in the kaniko image, which
has no Python, so it repeated `deps_image_tag()` in shell. Three `sha256sum` calls, a `cut`,
and a `sed` reading the base image out of `pyproject.toml` lived in `.gitlab-ci.yml` beside
the Python they mirrored, and an invariant pinned the two to each other. ADR-0035 named the
fix: compute the tag in a job that has Python and hand it to kaniko as a dotenv artifact.

## Decision

`container.tag` is a task on both hosts. It prints the deps image's content-addressed tag, and
with `--output` writes `DEPS_TAG` and `BASE_IMAGE` as `KEY=value` lines to a file.

On GitLab a `plan-deps-image` job runs it first, on the `python:3-slim` image with
`UV_NO_SYNC=1`, and publishes the file as a dotenv artifact. The kaniko job `needs` that job
and pushes to `${CI_REGISTRY_IMAGE}:deps-${DEPS_TAG}` with `--build-arg=BASE_IMAGE`, computing
nothing itself. The shell that remains there is the push: the registry login and the executor
call, which is what kaniko is for.

The plan job installs uv with one line of shell, `pip install "uv==$(sed … pyproject.toml)"`,
reading the pinned version the way copier's generation task does. That line stays because the
launcher is `uv run`, so uv has to exist before the launcher can. `UV_NO_SYNC` keeps the job
from installing every dependency group to hash a file: the tag reads bytes, not packages.

## Consequences

- One implementation of the tag. The invariant that pinned the shell copy to the Python one
  is replaced by one asserting the kaniko job computes nothing: no `sha256sum`, no `sed`, no
  `cut`.
- One more job per GitLab pipeline, before the image build. It pulls a small image, installs
  uv and runs a task that reads three files, so it is seconds rather than the minutes an image
  build costs.
- `python:3-slim` is a floating tag, like the kaniko executor image beside it. Both are the
  pipeline's own infrastructure rather than what the project depends on; the deps image, which
  is, stays pinned by digest (ADR-0033).
- A change to how the tag is computed is now a change to one function, and the pipeline follows
  without an edit.

## References

- [ADR-0004](0004-pipelines-run-template-commands-only.md), whose standing exception this
  narrows to the push.
- [ADR-0035](0035-github-reuses-a-deps-tag-gitlab-builds-with-kaniko.md), which named this fix.
