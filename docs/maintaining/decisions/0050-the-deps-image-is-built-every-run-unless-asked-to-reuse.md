# ADR-0050: The deps image is built every run unless asked to reuse

- **Status**: accepted; narrows ADR-0035
- **Date**: 2026-11-16

## Context

ADR-0035 had GitHub's deps-image job ask the registry whether the content-addressed tag
already existed and pull it instead of building. The GitLab job built every run, because
kaniko cannot ask. The reuse was a speed trade: a tag hit skips a full image build, and in
exchange the pipeline trusts whoever pushed that tag first. An actor able to pre-seed
`<repo>-deps:<tag>` would have every later job run inside their image, the publish job with
its PyPI OIDC token included, and digest pinning would pin their digest. The generated docs
explained the trade-off and told a project how to remove it by editing the task.

What the build costs is known: `Dockerfile.deps` is a `uv sync --frozen` of the lockfile on
the uv base image, so a run downloads every locked wheel once and installs it. Minutes per
gated push, against a manifest inspect and a pull.

## Decision

`container.publish` builds and pushes every run on both hosts. Reusing an existing tag is an
opt-in, `container.publish --reuse`, which a project enables by passing the flag in its own
build job once it has read the trade-off and restricted who can write to the package.

Both host modules implement the flag the same way: with `--reuse`, inspect the manifest and
pull a hit; otherwise, and on a miss, build and push. The returned reference is digest-pinned
either way.

## Consequences

- The default pipeline has no path that runs code it did not build this run. The access
  control the docs ask for is still worth having, but nothing depends on it by default.
- GitHub pays a build per gated push, as GitLab already did: one lockfile sync into a fresh
  image where there was a manifest inspect and a pull.
- The GitLab by-hand path gained the reuse option it lacked, for symmetry; its kaniko pipeline
  job still cannot reuse and is unchanged.
- The generated CI framework reference describes reuse as the opt-in it now is, and an
  invariant holds that `publish_deps_image` builds unless the flag says otherwise.

## References

- [ADR-0035](0035-github-reuses-a-deps-tag-gitlab-builds-with-kaniko.md), whose GitHub
  reuse this makes opt-in.
- [ADR-0033](0033-the-deps-image-is-content-addressed-and-handed-on-by-digest.md), the tag
  and the digest pin this relies on.
