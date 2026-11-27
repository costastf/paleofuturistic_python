# ADR-0065: The deps build pulls a fenced base image with the index identity

- **Status**: accepted; extends ADR-0063 and ADR-0064
- **Date**: 2026-11-27

## Context

A project moved behind Artifactory pointed its `base-image` at a docker remote, as the fence
how-to said, and set `DOCKER_AUTH_CONFIG` at group level with credentials for it. The kaniko
job failed to pull the base image anyway. `DOCKER_AUTH_CONFIG` is read by the GitLab runner,
when it pulls the job's own image before the script starts; kaniko runs inside the job and
reads `/kaniko/.docker/config.json`, which the job wrote itself with one entry, the project
registry and its deploy token. Every other registry kaniko touched was anonymous, and an
Artifactory remote that takes no anonymous reads answers 401.

The same gap existed for every build with an engine: `container.build` by hand and the GitHub
build job logged in to the project registry and nothing else. And the two images the GitLab
jobs run in before the deps image exists, `python:3-slim` and the kaniko executor, were
hardcoded to Docker Hub and gcr.io, which a runner that reaches only Artifactory cannot pull,
with no variable to point them elsewhere.

## Decision

The fence has one identity, and the base image gets it. The index credentials, minted from
the ID token or set as `INDEX_USERNAME` and `INDEX_PASSWORD`, are sent to the base image's
registry when that registry is the index host or one of its subdomains, port or not, which
covers the three ways Artifactory serves a docker repository: by path, by port and by
subdomain. Any other registry, ghcr.io in the open among them, is never sent them, so a
project with a fenced index and an open base image keeps working.

- With an engine, `build_deps_image` is the one entry point: it logs the engine in to the
  base image's registry when the rule matches, then builds with the credentials named on the
  command line as before. `container.build`, the local `container.publish` and both hosts'
  pipeline publish go through it.
- On kaniko, `container.tag --output` adds `BASE_IMAGE_REGISTRY` to the dotenv when the rule
  matches, and the job writes its credential file in three parts: the project registry's
  entry, the base image's entry when the variable is set, with the same `INDEX_*` values the
  builder stage takes, and the closing braces. No JSON is merged, because the kaniko image
  has busybox and no `jq`.
- The two job images become pipeline variables, `PYTHON_IMAGE` and `KANIKO_IMAGE`, with the
  public names as their values in the file, so a group can override them with the names its
  docker remotes serve them under. `DOCKER_AUTH_CONFIG`, set at the same level, is what the
  runner pulls them with; it stays the runner's and never reaches a build. The SBOM reader
  expands the variables from the file, so both images stay recorded.

What the organisation's side provides is written down in the fence how-to as a list: the
OIDC integration and identity mapping; a pypi remote the `<project>-ci` user reads; a docker
remote for ghcr.io the same user reads, which is where the base image moves to; a generic
remote for the interpreters; a local pypi repository the user deploys to; and, only for a
runner inside the fence, docker remotes for Docker Hub and gcr.io with the two variables and
`DOCKER_AUTH_CONFIG` beside them.

## Consequences

- The `<project>-ci` identity needs read on one more repository, the docker remote. One
  identity mapping covers packages, interpreters and the base image.
- A docker registry on a host unrelated to the index gets no credentials from the template.
  Artifactory does not do that; a project with such a registry logs in by hand before it
  builds.
- The digest in `base-image` is kept across the rename, so the tag still content-addresses
  the image the project actually builds on.
- Invariants hold the rule to the index host and its subdomains and away from any other, the
  engine to logging in before the build and only then, the dotenv to carrying the registry,
  the kaniko job to the three-part file with no `DOCKER_AUTH_CONFIG` in it, the job images to
  variables with public defaults, and the SBOM to resolving them.

## References

- [ADR-0063](0063-a-fenced-index-is-a-set-of-group-variables.md), the variables this adds to.
- [ADR-0064](0064-every-job-that-fetches-logs-in-to-the-index.md), which listed the base
  image as outside the fence; it no longer is.
- [ADR-0062](0062-the-deps-image-is-built-in-stages-and-read-back.md), the stage boundary
  the credentials still stop at.
