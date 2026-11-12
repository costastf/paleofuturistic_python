# ADR-0035: GitHub reuses an existing deps tag; GitLab's pipeline job builds with kaniko in shell

- **Status**: accepted
- **Date**: 2026-04-10 (GitHub reuse), 2026-04-20 (kaniko), 2026-11-11 (GitLab task uses docker)
- **Record written**: 2026-11-11 (backfilled)

## Context

Building the deps image on every run costs a full image build per gated push. On GitHub the
build job can ask ghcr whether the tag already exists and pull it instead. On GitLab, shared
runners allow no docker daemon, privileged docker-in-docker or user namespaces, which rules out
docker, buildah and podman; kaniko builds in userspace, but its image has no Python or uv, so
`./workflow.cmd` cannot run there.

## Decision

- **GitHub.** `publish_deps_image` inspects the manifest and, when the tag exists, pulls it so a
  repo digest exists locally; otherwise it builds and pushes. Reusing a tag trusts whoever
  pushed it first, so the mitigation is access control: only the deps job holds
  `packages: write`, and the generated docs name the trade-off and how to remove it.
- **GitLab.** The pipeline's deps job is the one job that does not go through the launcher. It
  repeats the tag computation and the push in shell, with kaniko and a Deploy Token scoped to a
  `deps` environment, and hands downstream jobs the digest from `--digest-file`. There is no
  reuse path, so the image can only ever be what that run produced. `container.publish` by hand
  builds the same reference with docker or podman, since November 2026; before that the task
  ran the kaniko executor, which only exists inside the kaniko image where the task cannot start.

## Consequences

- The shell duplicate of the tag algorithm was pinned to the Python one by an invariant until
  ADR-0043 removed it: the tag now reaches kaniko as a dotenv artifact from `container.tag`.
- The Deploy Token variables must be Protected, Masked and scoped to the `deps` environment, or
  a fork's merge request could read a registry write token.

## References

- Commits `4fbd8fc` (GitHub reuse), `ec87192` (kaniko), `607d850` (the trade-off written down), `a668ea0` (GitLab task on docker).
- *Build and push a container* and *CI framework internals* in the generated-project developer docs.
