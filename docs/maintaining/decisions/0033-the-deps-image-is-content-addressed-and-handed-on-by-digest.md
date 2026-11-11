# ADR-0033: The deps image is content-addressed over three inputs and handed on by digest

- **Status**: accepted
- **Date**: 2026-08-03 (image caching from 2026-04-10)
- **Record written**: 2026-11-11 (backfilled)

## Context

CI jobs run inside a prebuilt image holding the project's dependencies, so each job starts
warm. The image tag was derived from the lockfile alone, so editing `Dockerfile.deps` or bumping
the base image changed the image's contents without changing its tag, and CI kept running a
stale image. Downstream jobs also consumed the tag, which could be repointed between the build
job and the job that ran inside it.

## Decision

`deps_image_tag()` hashes `uv.lock`, `Dockerfile.deps` and the resolved base-image reference.
Each input is reduced to its own fixed-width digest before being folded into the outer hash, so
no combination of inputs can collide with a different combination and the algorithm is
reproducible in shell with `sha256sum`. `container.publish` resolves the pushed image to
`repository@sha256:…` and writes that to `.deps-image`, so a tag repointed mid-run cannot change
the container a later job runs in.

## Consequences

- A change to any of the three inputs produces a new tag; the same three reuse the image.
- GitLab's pipeline job computes the same tag in shell, and an invariant keeps the two in step
  (ADR-0035).
- The base image carries its own digest (ADR-0008), which is one of the three inputs, so a
  base bump rebuilds rather than serving an image built on the old base.

## References

- Commits `4fbd8fc` (image caching), `607d850` (content-addressed tag, digest pinning).
- *CI framework internals* in the generated-project developer docs.
